"""Opt-in host security. Project-owned drop-ins only, transactional file/service rollback.

Host DNS and security state are deliberately excluded from portable Backup v3.
"""
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

MARKER = '# Managed by 3x-ui Auto Nginx: VPS Security\n'
DOT = MARKER + '''[Resolve]
DNS=
DNS=1.1.1.1#one.one.one.one 1.0.0.1#one.one.one.one 8.8.8.8#dns.google 8.8.4.4#dns.google
FallbackDNS=
Domains=
Domains=~.
DNSOverTLS=yes
DNSSEC=no
LLMNR=no
MulticastDNS=no
Cache=yes
DNSStubListener=yes
'''
FILES = ('/etc/fail2ban/jail.d/90-3x-ui-auto-nginx.local',
         '/etc/apt/apt.conf.d/99zz-3x-ui-auto-nginx',
         '/etc/systemd/system/apt-daily.timer.d/90-3x-ui-auto-nginx.conf',
         '/etc/systemd/system/apt-daily-upgrade.timer.d/90-3x-ui-auto-nginx.conf',
         '/etc/systemd/resolved.conf.d/90-3x-ui-auto-nginx.conf')
DOT_WARNING = ('Global DoT does not override link/VPN DNS routes or search domains; '
               'queries using link DNS may be unencrypted. Inspect resolvectl status.')
SERVICES = ('fail2ban.service', 'apt-daily.timer', 'apt-daily-upgrade.timer', 'systemd-resolved.service')


def command(*args, check=True):
    output = {'stdout': sys.stderr, 'stderr': sys.stderr} if args[0] == 'apt-get' else {'capture_output': True}
    result = subprocess.run(args, **output, text=True, timeout=1800 if args[0]=='apt-get' else 90,
                            env={**os.environ, 'LC_ALL': 'C', 'DEBIAN_FRONTEND': 'noninteractive',
                                 'NEEDRESTART_MODE': 'l', 'UCF_FORCE_CONFFOLD': '1'})
    if check and result.returncode:
        detail = ': ' + result.stderr.strip()[:400] if args[0] == 'resolvectl' else ''
        raise ValueError('Command failed (exit '+str(result.returncode)+'): ' + ' '.join(args) + detail)
    return (result.stdout or '').strip()


def ssh_ports(effective, socket_listen=''):
    ports = {int(x) for x in re.findall(r'^port (\d+)$', effective, re.M)}
    if socket_listen:
        # systemctl show Listen: "[::]:2222 (Stream) 0.0.0.0:2200 (Stream)".
        matches = re.findall(r'(\S+) \(Stream\)', socket_listen)
        if not matches:
            raise ValueError('Unrecognized ssh.socket Listen property')
        ports = {int(value.rsplit(':', 1)[-1]) for value in matches}
    if not ports or any(not 1 <= port <= 65535 for port in ports):
        raise ValueError('Cannot determine effective SSH ports')
    return sorted(ports)


def password_warning(effective):
    policy = dict(line.split(' ', 1) for line in effective.splitlines() if ' ' in line)
    methods = policy.get('authenticationmethods', 'any')
    candidates = methods == 'any' or any(m in methods for m in ('password', 'keyboard-interactive'))
    return candidates and (policy.get('passwordauthentication') == 'yes' or
                           policy.get('kbdinteractiveauthentication') == 'yes')


def timer(hour):
    hour = hour if ':' in hour else hour + ':30'
    return MARKER + f'''[Timer]
OnCalendar=
OnCalendar=*-*-* {hour}:00
RandomizedDelaySec=0
AccuracySec=1min
Persistent=true
'''


def apt_config(os_id):
    if os_id == 'ubuntu':
        origins = 'origin=Ubuntu,archive=${distro_codename}-security'
    elif os_id == 'debian':
        origins = 'origin=Debian,label=Debian-Security,codename=${distro_codename}-security'
    else:
        raise ValueError('Unsupported security update origin')
    return MARKER + '''APT::Periodic::Enable "1";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-WithUsers "true";
Unattended-Upgrade::Automatic-Reboot-Time "04:38";
// Add the required distro security origin; retain administrator/distro origins.
Unattended-Upgrade::Origins-Pattern { "''' + origins + '''"; };
'''


def apt_origins(dump):
    return set(re.findall(r'Unattended-Upgrade::(Allowed-Origins|Origins-Pattern):: "([^"\n]+)";', dump))


def global_servers(dns):
    # resolvectl wraps its global server list on narrow/noninteractive consoles.
    global_block = re.search(r'^Global:\s*(.*?)(?=^Link |\Z)', dns, re.M | re.S)
    return global_block[1].split() if global_block else []


def preflight(root=Path('/'), files=FILES, services=SERVICES):
    for filename in files:
        path = root / filename.lstrip('/')
        if path.is_symlink() or (path.exists() and (not path.is_file() or not path.read_text().startswith(MARKER))):
            raise ValueError('Unowned project configuration path: ' + filename)
        if path.exists() and (path.stat().st_uid != 0 or path.stat().st_mode & 0o022):
            raise ValueError('Unsafe owner/permissions of project configuration: ' + filename)
    for service in services:
        if command('systemctl', 'is-enabled', service, check=False) not in ('enabled', 'disabled', 'static', 'not-found', ''):
            raise ValueError('Custom/masked service enable state preserved: ' + service)
    info = dict(line.strip().split('=', 1) for line in (root / 'etc/os-release').read_text().splitlines() if '=' in line)
    os_id, version = (info.get(k, '').strip('"') for k in ('ID', 'VERSION_ID'))
    if (os_id, version) not in (('ubuntu', '24.04'), ('ubuntu', '26.04'), ('debian', '13')):
        raise ValueError('Unsupported OS for VPS Security')
    return os_id


class Transaction:
    def __init__(self, root=Path('/'), services=SERVICES, files=FILES):
        self.root = root
        self.temp = tempfile.TemporaryDirectory(prefix='xui-security-')
        os.chmod(self.temp.name, 0o700)
        self.saved = {}
        paths = (*files, '/etc/resolv.conf') if FILES[-1] in files else files
        for index, filename in enumerate(paths):
            path = root / filename.lstrip('/')
            backup = Path(self.temp.name) / str(index)
            if path.exists() or path.is_symlink():
                shutil.copy2(path, backup, follow_symlinks=False)
                self.saved[filename] = backup
            else:
                self.saved[filename] = None
        self.states = {s: (command('systemctl', 'is-active', s, check=False),
                           command('systemctl', 'is-enabled', s, check=False)) for s in services}

    def write(self, filename, text):
        path = self.root / filename.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        # All managed paths were ownership-checked; no global file is rewritten.
        path.write_text(text)
        path.chmod(0o644)

    def save_dns(self, directory):
        # Only the original DNS snapshot crosses installer subprocesses.
        directory=Path(directory)
        shutil.copytree(self.temp.name,directory,symlinks=True)
        directory.chmod(0o700)
        metadata=directory/'state.json'
        metadata.write_text(json.dumps({'saved':{name:backup.name if backup else None for name,backup in self.saved.items()},'states':self.states}))
        metadata.chmod(0o600)

    @classmethod
    def load_dns(cls, directory, root):
        directory=Path(directory); metadata=directory/'state.json'
        if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != 0 or directory.stat().st_mode & 0o077:
            raise ValueError('Unsafe DNS checkpoint directory')
        if metadata.is_symlink() or not metadata.is_file() or metadata.stat().st_uid != 0 or metadata.stat().st_mode & 0o077:
            raise ValueError('Unsafe DNS checkpoint metadata')
        data=json.loads(metadata.read_text())
        names=(FILES[-1],'/etc/resolv.conf')
        if set(data) != {'saved','states'} or set(data['saved']) != set(names) or set(data['states']) != {'systemd-resolved.service'}:
            raise ValueError('Invalid DNS checkpoint scope')
        if data['saved']['/etc/resolv.conf'] != '1':
            raise ValueError('Original resolver file missing from DNS checkpoint')
        values=data['states']['systemd-resolved.service']
        if not isinstance(values,list) or len(values)!=2:
            raise ValueError('Invalid DNS checkpoint service record')
        active,enabled=values
        if active not in ('active','inactive','failed','unknown','') or enabled not in ('enabled','disabled','static','not-found',''):
            raise ValueError('Invalid DNS checkpoint service state')
        expected={'state.json'}
        for index,name in enumerate(names):
            record=data['saved'][name]
            if record is None: continue
            if record != str(index): raise ValueError('Invalid DNS checkpoint path')
            expected.add(record); backup=directory/record
            if backup.is_symlink():
                # Restore the saved link itself; its target is never opened by rollback.
                if name != '/etc/resolv.conf' or backup.lstat().st_uid != 0:
                    raise ValueError('Invalid DNS checkpoint link')
            elif not backup.is_file() or backup.stat().st_uid != 0 or backup.stat().st_mode & 0o022:
                raise ValueError('Unsafe DNS checkpoint file')
        if {p.name for p in directory.iterdir()} != expected:
            raise ValueError('Unexpected DNS checkpoint object')
        txn=cls.__new__(cls); txn.root=root
        txn.temp=tempfile.TemporaryDirectory(prefix='xui-dns-restore-')
        shutil.copytree(directory,txn.temp.name,symlinks=True,dirs_exist_ok=True)
        txn.saved={name:Path(txn.temp.name)/record if record else None for name,record in data['saved'].items()}
        txn.states=data['states']
        return txn

    def rollback(self):
        for filename, backup in self.saved.items():
            path = self.root / filename.lstrip('/')
            path.unlink(missing_ok=True)
            if backup is not None:
                shutil.copy2(backup, path, follow_symlinks=False)
        command('systemctl', 'daemon-reload')
        for service, (active, enabled) in self.states.items():
            if enabled == 'enabled':
                command('systemctl', 'enable', service)
            elif enabled in ('disabled', 'not-found', ''):
                command('systemctl', 'disable', service, check=False)
            if active == 'active':
                command('systemctl', 'restart', service)
            else:
                command('systemctl', 'stop', service, check=False)
            state = command('systemctl', 'is-active', service, check=False)
            if (state == 'active') != (active == 'active'):
                raise ValueError('Service rollback not verified')
            restored = command('systemctl', 'is-enabled', service, check=False)
            if restored != enabled and not (enabled in ('not-found', '') and restored in ('disabled', 'not-found', '')):
                raise ValueError('Service enable-state rollback not verified')
        for filename, backup in self.saved.items():
            path = self.root / filename.lstrip('/')
            if backup is None:
                if path.exists() or path.is_symlink():
                    raise ValueError('New configuration remains after rollback')
            elif backup.is_symlink():
                if not path.is_symlink() or os.readlink(path) != os.readlink(backup):
                    raise ValueError('DNS link rollback not verified')
            elif path.read_bytes() != backup.read_bytes():
                raise ValueError('Configuration rollback not verified')


def verify_fail2ban(ports):
    # No SSH policy is edited here; validate configuration, not its text rendering.
    command('/usr/sbin/sshd', '-t')
    # The distro unit uses Type=simple: restart can return before its socket/jail.
    for attempt in range(10):
        try:
            command('fail2ban-client', 'status', 'sshd')
            break
        except ValueError:
            if attempt == 9:
                raise
            time.sleep(1)
    for key, value in (('maxretry', '5'), ('findtime', '1800'), ('bantime', '3600')):
        if command('fail2ban-client', 'get', 'sshd', key) != value:
            raise ValueError('Ineffective SSH jail setting')
    # The dumped effective action must name actual listeners, never only "ssh".
    dump = command('fail2ban-client', '-d')
    if not all(str(p) in dump for p in ports):
        raise ValueError('SSH jail ports not effective')


def verify_apt(os_id, previous_origins):
    apt = command('apt-config', 'dump')
    for setting in ('Automatic-Reboot "true";', 'Automatic-Reboot-WithUsers "true";', 'Automatic-Reboot-Time "04:38";'):
        if 'Unattended-Upgrade::' + setting not in apt:
            raise ValueError('Automatic reboot policy not effective')
    origins = apt_origins(apt)
    required = ('Origins-Pattern', re.search(r'Origins-Pattern \{ "([^"]+)"', apt_config(os_id))[1])
    if required not in origins or not previous_origins <= origins:
        raise ValueError('Required security origin missing or existing APT origins changed')
    for key in ('Enable','Update-Package-Lists','Unattended-Upgrade'):
        if 'APT::Periodic::'+key+' "1";' not in apt:
            raise ValueError('Effective APT::Periodic::'+key+' is not enabled')
    for service, hour in (('apt-daily.timer', '02:30'), ('apt-daily-upgrade.timer', '02:50')):
        command('systemctl', 'is-active', '--quiet', service)
        command('systemctl', 'is-enabled', '--quiet', service)
        timers = command('systemctl', 'show', service, '-p', 'TimersCalendar', '-p', 'RandomizedDelayUSec')
        if f'{hour}:00' not in timers or 'RandomizedDelayUSec=0' not in timers:
            raise ValueError('APT timer not effective')


def verify_dns():
    mode = command('busctl', 'get-property', 'org.freedesktop.resolve1',
                   '/org/freedesktop/resolve1', 'org.freedesktop.resolve1.Manager', 'DNSOverTLS')
    if mode != 's "yes"':
        raise ValueError('Effective global DNSOverTLS is not strict')
    dns = command('resolvectl', 'dns')
    global_dns = global_servers(dns)
    if global_dns != ['1.1.1.1#one.one.one.one', '1.0.0.1#one.one.one.one', '8.8.8.8#dns.google', '8.8.4.4#dns.google']:
        raise ValueError('Effective TLS names/DNS servers differ')
    command('resolvectl', 'flush-caches')
    # Check resolver functionality without removing provider/VPN DNS policy.
    # Strict TLS applies to global servers, not necessarily to link-routed queries.
    command('resolvectl', 'query', '--cache=no', 'cloudflare.com')
    command('resolvectl', 'query', '--cache=no', 'debian.org')
    command('getent', 'ahosts', 'debian.org')


def prepare_dns(root=Path('/'), state=None):
    # Capture DNS and service state BEFORE package maintainer scripts can change it.
    preflight(root, files=FILES[-1:], services=SERVICES[-1:])
    command('getent', 'ahosts', 'debian.org')
    txn = Transaction(root, services=('systemd-resolved.service',), files=FILES[-1:])
    try:
        stage='saving DNS checkpoint'
        if state is not None: txn.save_dns(state)
        stage='installing systemd-resolved'
        command('apt-get', '-o', 'DPkg::Lock::Timeout=300', '-o', 'Dpkg::Options::=--force-confdef',
                '-o', 'Dpkg::Options::=--force-confold', '--no-remove', '--no-install-recommends', '-y', 'install', 'systemd-resolved')
        stage='writing DNS drop-in and stub link'
        txn.write(FILES[4], DOT)
        resolv=root/'etc/resolv.conf'; resolv.unlink(); resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')
        stage='starting systemd-resolved'
        command('systemctl','daemon-reload')
        command('systemctl','enable','systemd-resolved.service')
        command('systemctl','restart','systemd-resolved.service')
        stage='strict DoT verification'
        verify_dns()
        return {'status':'configured', 'dot':'configured', 'warnings':[DOT_WARNING]}
    except Exception as error:
        status='failed_rolled_back'; rollback_error=''
        try:
            txn.rollback()
            command('getent','ahosts','debian.org')
        except Exception as failure:
            status='failed_unverified'; rollback_error='; rollback error: '+str(failure)
        return {'status':status, 'dot':status, 'warnings':['DNS preparation failed during '+stage+': '+str(error)+'; rollback='+status+rollback_error, 'Package installation is not rolled back; original DNS/service state was restored only if verified.']}
    finally:
        txn.temp.cleanup()


def rollback_dns_checkpoint(state, root=Path('/')):
    txn=None
    try:
        # Do not overwrite administrator changes made during installation.
        resolv=root/'etc/resolv.conf'; policy=root/FILES[-1].lstrip('/')
        if (not resolv.is_symlink() or os.readlink(resolv) != '/run/systemd/resolve/stub-resolv.conf'
                or policy.is_symlink() or not policy.is_file() or policy.stat().st_uid != 0
                or policy.stat().st_mode & 0o022 or policy.read_text() != DOT):
            raise ValueError('Prepared DNS no longer has canonical project ownership')
        txn=Transaction.load_dns(state,root)
        txn.rollback()
        command('getent','ahosts','debian.org')
        return {'status':'failed_rolled_back','warnings':['Original DNS and resolver state restored; package changes remain.']}
    except Exception as error:
        return {'status':'failed_unverified','warnings':['Original DNS rollback not verified: '+str(error)]}
    finally:
        if txn is not None: txn.temp.cleanup()


def ufw_simple_rules(text, ipv6, ports):
    """Accept only the distro boilerplate and project/SSH unrestricted allows."""
    chain = 'ufw6' if ipv6 else 'ufw'
    allowed = {('tcp', 80), ('tcp', 443), ('udp', 443), ('udp', 8443)}
    allowed.update(('tcp', port) for port in ports)
    stock = {
        f'-A {chain}-user-limit -m limit --limit 3/minute -j LOG --log-prefix "[UFW LIMIT BLOCK] "',
        f'-A {chain}-user-limit -j REJECT', f'-A {chain}-user-limit-accept -j ACCEPT',
        f'-I {chain}-logging-deny -m conntrack --ctstate INVALID -j RETURN -m limit --limit 3/min --limit-burst 10',
    }
    for suffix, prefix in (('after-logging-input', 'BLOCK'), ('after-logging-forward', 'BLOCK'),
                           ('logging-deny', 'BLOCK'), ('logging-allow', 'ALLOW')):
        stock.add(f'-A {chain}-{suffix} -j LOG --log-prefix "[UFW {prefix}] " -m limit --limit 3/min --limit-burst 10')
    chains = {'user-input', 'user-output', 'user-forward', 'user-limit', 'user-limit-accept',
              'logging-deny', 'logging-allow'}
    chains.update(f'{when}-logging-{direction}' for when in ('before', 'user', 'after')
                  for direction in ('input', 'output', 'forward'))
    for line in text.splitlines():
        if not line or line.startswith('#') or line in ('*filter', 'COMMIT') or line in stock:
            continue
        if line in {f':{chain}-{name} - [0:0]' for name in chains}:
            continue
        match = re.fullmatch(r'-A '+chain+r'-user-input -p (tcp|udp) --dport ([0-9]+) -j ACCEPT', line)
        if not match or (match[1], int(match[2])) not in allowed:
            raise ValueError('Unsupported UFW user rules; automatic enable refused')


def ufw_preflight(root, ports):
    # No arbitrary firewall interpretation: only packaged defaults and simple allows.
    for name in ('before.rules', 'before6.rules', 'after.rules', 'after6.rules', 'before.init', 'after.init'):
        path = root/'etc/ufw'/name
        if path.is_symlink() or path.read_bytes() != (root/'usr/share/ufw'/name).read_bytes():
            raise ValueError('Custom UFW before/after configuration; automatic enable refused')
    conffiles = command('dpkg-query', '-W', '-f=${Conffiles}', 'ufw')
    for filename in ('/etc/default/ufw', '/etc/ufw/sysctl.conf'):
        match = re.search(r'^ '+re.escape(filename)+r' ([0-9a-f]{32})$', conffiles, re.M)
        path = root/filename.lstrip('/')
        if not match or path.is_symlink() or hashlib.md5(path.read_bytes()).hexdigest() != match[1]:
            raise ValueError('Nonstandard UFW defaults; automatic enable refused')
    config = (root/'etc/ufw/ufw.conf').read_text()
    if re.findall(r'^ENABLED=(.*)$', config, re.M) != ['no'] or re.findall(r'^LOGLEVEL=(.*)$', config, re.M) != ['low']:
        raise ValueError('Nonstandard UFW activation/logging configuration')
    for name, ipv6 in (('user.rules', False), ('user6.rules', True)):
        path = root/'etc/ufw'/name
        if path.is_symlink(): raise ValueError('Symlink UFW rules unsupported')
        ufw_simple_rules(path.read_text(), ipv6, ports)
    for service in ('firewalld.service', 'nftables.service', 'netfilter-persistent.service'):
        if command('systemctl', 'is-active', service, check=False) not in ('inactive', 'failed', 'unknown', ''):
            raise ValueError('Another firewall manager is active; automatic enable refused')
    for tool in ('iptables', 'ip6tables'):
        if '(nf_tables)' not in command(tool, '--version'):
            raise ValueError('Only the standard nft-backed Ubuntu iptables is supported')
    for entry in json.loads(command('nft', '-j', 'list', 'ruleset'))['nftables']:
        if set(entry) == {'metainfo'}: continue
        if set(entry) == {'table'}:
            table = entry['table']
            if table['family'] in ('ip', 'ip6') and table['name'] == 'filter': continue
        if set(entry) == {'chain'}:
            chain = entry['chain']
            if (chain['family'] in ('ip', 'ip6') and chain['table'] == 'filter'
                    and chain['name'] in ('INPUT', 'OUTPUT', 'FORWARD') and chain.get('policy') == 'accept'
                    and chain.get('type') == 'filter' and chain.get('prio') == 0): continue
        raise ValueError('Existing kernel firewall rules are unsupported; automatic enable refused')


def ufw_ssh_ports(root):
    command('/usr/sbin/sshd', '-t')
    effective = command('/usr/sbin/sshd', '-T')
    socket_state = command('systemctl', 'is-active', 'ssh.socket', check=False)
    service_state = command('systemctl', 'is-active', 'ssh.service', check=False)
    if socket_state not in ('active', 'inactive', 'failed') or service_state not in ('active', 'inactive', 'failed'):
        raise ValueError('Ambiguous standard SSH service/socket state')
    listen = command('systemctl', 'show', 'ssh.socket', '-p', 'Listen', '--value') if socket_state == 'active' else ''
    if socket_state == 'active' and (not listen or re.sub(r'\S+ \(Stream\)', '', listen).strip()):
        raise ValueError('Unsupported SSH socket listeners')
    ports = set(ssh_ports(effective, listen))
    pid = int(command('systemctl', 'show', 'ssh.service', '-p', 'MainPID', '--value'))
    owners = {1} if socket_state == 'active' else set()
    if service_state == 'active' and pid > 1:
        if (root/f'proc/{pid}/exe').resolve() != (root/'usr/sbin/sshd').resolve():
            raise ValueError('SSH service is not the standard sshd process')
        owners.add(pid)
    if not owners: raise ValueError('No active standard SSH owner')
    found = set()
    for line in command('ss', '-H', '-ltnp').splitlines():
        fields = line.split()
        address, port = fields[3].rsplit(':', 1)
        pids = {int(p) for p in re.findall(r'pid=(\d+)', line)}
        if int(port) in ports or pids & owners:
            if (address not in ('0.0.0.0', '*', '[::]', '::') or int(port) not in ports
                    or not pids or not pids <= owners):
                raise ValueError('SSH configuration/listener ownership mismatch')
            found.add(int(port))
    if found != ports: raise ValueError('SSH configured ports do not match real listeners')
    connection = os.environ.get('SSH_CONNECTION', '').split()
    if connection and (len(connection) != 4 or int(connection[3]) not in ports):
        raise ValueError('Current SSH connection port differs from confirmed listeners')
    return sorted(ports)


def enable_ufw(root=Path('/')):
    attempted = False
    try:
        status = command('ufw', 'status')
        if status.startswith('Status: active'):
            return {'status': 'preserved', 'warnings': []}
        if status != 'Status: inactive': raise ValueError('Unknown UFW state')
        info = (root/'etc/os-release').read_text()
        if not re.search(r'^ID=ubuntu$', info, re.M) or not re.search(r'^VERSION_ID="?(24\.04|26\.04)"?$', info, re.M):
            raise ValueError('Automatic UFW enable supports Ubuntu 24.04/26.04 only')
        ports = ufw_ssh_ports(root)
        if shutil.which('nft') is None:
            command('apt-get', '-o', 'DPkg::Lock::Timeout=300', '--no-remove', 'install', '-y',
                    '--no-install-recommends', 'nftables')
        ufw_preflight(root, ports)
        for port in ports: command('ufw', 'allow', str(port)+'/tcp')
        attempted = True
        command('ufw', '--force', 'enable')
        if not command('ufw', 'status').startswith('Status: active'):
            raise ValueError('UFW active state not confirmed')
        for tool, chain in (('iptables', 'ufw'), ('ip6tables', 'ufw6')):
            command(tool, '-C', 'INPUT', '-j', chain+'-before-input')
            command(tool, '-C', chain+'-before-input', '-j', chain+'-user-input')
            if '-P INPUT DROP' not in command(tool, '-S', 'INPUT').splitlines():
                raise ValueError('UFW incoming policy not confirmed')
            for port in ports:
                command(tool, '-C', chain+'-user-input', '-p', 'tcp', '--dport', str(port), '-j', 'ACCEPT')
        return {'status': 'configured', 'warnings': []}
    except Exception as error:
        return {'status': 'failed_unverified' if attempted else 'failed', 'warnings': [str(error)]}


def configure(root=Path('/')):
    # DNS was prepared before cleanup. Neither component may change its files/service.
    result = {'status': 'partial', 'warnings': []}
    txn = None
    stage = 'APT preflight'
    try:
        os_id = preflight(root, files=FILES[1:4], services=SERVICES[1:3])
        origins = apt_origins(command('apt-config', 'dump'))
        txn = Transaction(root, files=FILES[1:4], services=SERVICES[1:3])
        stage = 'installing unattended-upgrades'
        command('apt-get', '-o', 'DPkg::Lock::Timeout=300', '-o', 'Dpkg::Options::=--force-confdef',
                '-o', 'Dpkg::Options::=--force-confold', '--no-remove', 'install', '-y', '--no-install-recommends', 'unattended-upgrades')
        stage = 'configuring APT policy and timers'
        txn.write(FILES[1], apt_config(os_id))
        txn.write(FILES[2], timer('02:30')); txn.write(FILES[3], timer('02:50'))
        command('systemctl', 'daemon-reload')
        for service in SERVICES[1:3]:
            command('systemctl', 'enable', service)
            command('systemctl', 'restart', service)
        stage = 'verifying APT policy and timers'
        verify_apt(os_id, origins)
        result['apt'] = 'configured'
    except Exception as error:
        status = 'failed_rolled_back'; rollback_error = ''
        try:
            if txn is not None: txn.rollback()
        except Exception as failure:
            status = 'failed_unverified'; rollback_error = '; rollback error: ' + str(failure)
        result['apt'] = status
        result['warnings'].append('APT failed during '+stage+': '+str(error)+'; rollback='+status+rollback_error+'; continuing other components. Package changes remain.')
    finally:
        if txn is not None: txn.temp.cleanup()

    txn = None
    stage = 'Fail2ban preflight'
    try:
        preflight(root, files=FILES[:1], services=SERVICES[:1])
        effective = command('/usr/sbin/sshd', '-T')
        listen = command('systemctl', 'show', 'ssh.socket', '-p', 'Listen', '--value') if command('systemctl', 'is-active', 'ssh.socket', check=False) == 'active' else ''
        ports = ssh_ports(effective, listen)
        if password_warning(effective):
            result['warnings'].append('SSH PASSWORD AUTHENTICATION IS ENABLED. SSH policy was preserved; review it separately.')
        txn = Transaction(root, files=FILES[:1], services=SERVICES[:1])
        stage = 'installing Fail2ban dependencies'
        command('apt-get', '-o', 'DPkg::Lock::Timeout=300', '-o', 'Dpkg::Options::=--force-confdef',
                '-o', 'Dpkg::Options::=--force-confold', '--no-remove', 'install', '-y', '--no-install-recommends', 'fail2ban', 'python3-systemd', 'nftables')
        stage = 'configuring SSH Fail2ban jail'
        backend = 'systemd' if command('journalctl', '-n', '1', '--no-pager', check=False) else 'auto'
        if backend == 'auto' and not (root / 'var/log/auth.log').is_file():
            raise ValueError('No SSH journaling/log backend')
        txn.write(FILES[0], MARKER + f'''[sshd]
enabled = true
port = {','.join(map(str, ports))}
backend = {backend}
maxretry = 5
findtime = 1800
bantime = 3600
''')
        command('systemctl', 'daemon-reload')
        command('systemctl', 'enable', 'fail2ban.service')
        command('systemctl', 'restart', 'fail2ban.service')
        stage = 'verifying SSH Fail2ban jail'
        verify_fail2ban(ports)
        result['fail2ban'] = 'configured'
    except Exception as error:
        status = 'failed_rolled_back'; rollback_error = ''
        try:
            if txn is not None: txn.rollback()
            command('/usr/sbin/sshd', '-t')
        except Exception as failure:
            status = 'failed_unverified'; rollback_error = '; rollback error: ' + str(failure)
        result['fail2ban'] = status
        result['warnings'].append('Fail2ban failed during '+stage+': '+str(error)+'; rollback='+status+rollback_error+'; other components retained. Package changes remain.')
    finally:
        if txn is not None: txn.temp.cleanup()
    if result['apt'] == result['fail2ban'] == 'configured': result['status'] = 'configured'
    return result


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--preflight']:
            preflight()
            result = {'status': 'compatible', 'warnings': []}
        elif len(sys.argv) in (2,3) and sys.argv[1] == '--prepare-dns':
            result = prepare_dns(state=Path(sys.argv[2]) if len(sys.argv)==3 else None)
        elif len(sys.argv)==3 and sys.argv[1] == '--rollback-dns':
            result = rollback_dns_checkpoint(Path(sys.argv[2]))
        elif sys.argv[1:] == ['--enable-ufw']:
            result = enable_ufw()
        elif sys.argv[1:]:
            raise ValueError('Usage: managed-security.py [--preflight|--prepare-dns [checkpoint]|--rollback-dns checkpoint|--enable-ufw]')
        else:
            result = configure()
    except Exception as error:
        result = {'status': 'failed_rolled_back', 'dot': 'not_configured', 'warnings': [str(error)]}
    print(json.dumps(result))
    restored = len(sys.argv)==3 and sys.argv[1]=='--rollback-dns' and result['status']=='failed_rolled_back'
    sys.exit(0 if result['status'] in ('configured', 'compatible', 'preserved') or restored else 1)
