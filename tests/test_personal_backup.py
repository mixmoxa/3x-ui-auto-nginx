"""Exercise the Bash utility on private fixtures, with host services mocked.

Only filesystem roots are relocated in a temporary copy of the source. tar/gzip,
SQLite and (when NGINX_BIN is set) nginx are real; no installer is executed.
"""
import copy
import hashlib
import io
import json
import os
import pwd
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from configobj import ConfigObj
from certificate_fixtures import certificates

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "assets/backup/x-ui-backup.sh").read_text()
INSTALLER = (ROOT / "x-ui-latest.sh").read_text()
CRON = ('@monthly certbot renew --non-interactive --pre-hook "systemctl stop nginx" '
        '--post-hook "systemctl start nginx" > /dev/null 2>&1')
PARAMS = [
    "net.core.default_qdisc=fq", "net.ipv4.tcp_congestion_control=bbr", "fs.file-max=2097152",
    "net.ipv4.tcp_timestamps=1", "net.ipv4.tcp_sack=1", "net.ipv4.tcp_window_scaling=1",
    "net.core.rmem_max=16777216", "net.core.wmem_max=16777216",
    "net.ipv4.tcp_rmem=4096 87380 16777216", "net.ipv4.tcp_wmem=4096 65536 16777216",
]


def relocated(source, root):
    # Apply a single pass so replacements cannot recursively match themselves.
    return re.sub(r"/(?:proc|opt|etc|root|var|usr/local|usr/bin/x-ui|dev/shm)(?=[/\s\"';,)}]|$)",
                  lambda m: str(root) + m[0], source)


def function(name):
    matches = re.findall(r"^" + re.escape(name) + r"\(\)\s*\{.*?^\}", INSTALLER, re.M | re.S)
    if len(matches) != 1:
        raise AssertionError(f"Expected one {name} function")
    return matches[0]


# These stubs model outcomes/record calls, not production systemd or firewall.
MOCK = r'''#!/usr/bin/env python3
import json, os, pathlib, socket, subprocess, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ['FIXTURE_ROOT'])
with open(root / 'commands', 'a') as log:
    log.write(json.dumps([name, *args]) + '\n')
def fault():
    if os.environ.get('FAIL_ONCE'):
        (root/'fault-used').touch()
if os.environ.get('FAIL_ONCE') and (root/'fault-used').exists():
    for key in ('FAIL_NGINX','FAIL_HEALTH_SERVICE','CORRUPT_RUNNING_DB','MISSING_SOCKET','FAIL_SYSCTL',
                'FAIL_CERTBOT_ENABLE','FAIL_CRON_WRITE','BREAK_FINAL_RENEWAL'):
        os.environ.pop(key, None)
installed_path = root / 'installed-packages'
installed = set(installed_path.read_text().split()) if installed_path.exists() else set()
if name in ('python3', 'gzip', 'tar') and name in os.environ.get('MISSING_PACKAGES', '').split() and name not in installed:
    sys.exit(127)
if name == 'systemctl':
    path = root / 'services.json'
    services = json.loads(path.read_text())
    command, service = args[0], args[-1]
    enabled_path = root / 'enabled.json'
    enabled = json.loads(enabled_path.read_text()) if enabled_path.exists() else {}
    if command == 'enable':
        if service == 'certbot.timer' and os.environ.get('FAIL_CERTBOT_ENABLE'):
            fault(); sys.exit(1)
        enabled[service] = True
        enabled_path.write_text(json.dumps(enabled))
        if '--now' in args:
            services[service] = 'active'
            path.write_text(json.dumps(services))
        if service == 'certbot.timer' and '--now' in args:
            broken = os.environ.get('BREAK_FINAL_RENEWAL')
            if broken:
                fault()
                with open(root/'commands','a') as log: log.write(json.dumps(['fault','renewal',broken])+'\n')
            if broken == 'active':
                services[service] = 'inactive'
                path.write_text(json.dumps(services))
            elif broken == 'enabled':
                enabled[service] = False
                enabled_path.write_text(json.dumps(enabled))
            elif broken == 'hook':
                (root / 'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx').unlink(missing_ok=True)
            elif broken == 'authenticator':
                conf = root / 'etc/letsencrypt/renewal/example.com.conf'
                conf.write_text(conf.read_text().replace('authenticator = webroot', 'authenticator = standalone'))
            elif broken == 'legacy':
                with open(root / 'crontab', 'a') as out:
                    out.write('@monthly certbot renew --non-interactive --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx" > /dev/null 2>&1\n')
    if command == 'is-enabled':
        sys.exit(0 if enabled.get(service) else 1)
    if command == 'is-active':
        state = services.get(service, 'inactive')
        active = state == 'active'
        if '--quiet' in args and os.environ.get('FAIL_HEALTH_SERVICE') == service:
            fault(); active = False
            if os.environ.get('CONCURRENT_ACME'):
                (root/'var/www/acme/.well-known/independent-file').write_text('keep independent data')
            if os.environ.get('CONCURRENT_CRON'):
                with open(root/'crontab','a') as out: out.write('@daily administrator-change\n')
        if '--quiet' not in args:
            print(state)
        sys.exit(0 if active else 3)
    if command == 'show' and service == 'AdGuardHome':
        print(str(root / 'etc/systemd/system/AdGuardHome.service') if 'FragmentPath' in ' '.join(args) else '12345')
    if command == 'show' and service == 'x-ui':
        print('54321')
    if command == 'disable':
        enabled[service] = False; enabled_path.write_text(json.dumps(enabled))
    if command == 'cat':
        if service == 'AdGuardHome' and (root / 'etc/systemd/system/AdGuardHome.service').exists():
            print((root / 'etc/systemd/system/AdGuardHome.service').read_text())
        sys.exit(0 if (root / ('etc/systemd/system/' + service + '.service')).exists() or service == 'nginx' else 1)
    if command in ('start', 'stop'):
        if command == 'start' and service == 'x-ui' and (os.environ.get('FAIL_XUI_START') or
            (os.environ.get('FAIL_INCOMING_XUI') and (root/'var/www/html/recovery-marker').read_text() == 'incoming')):
            sys.exit(1)
        if service == 'certbot.timer' and os.environ.get('FAIL_TIMER_OPERATION') == command:
            sys.exit(1)
        services[service] = 'active' if command == 'start' else 'inactive'
        path.write_text(json.dumps(services))
        if command == 'start' and service == 'x-ui':
            sock = root / 'dev/shm/uds2023.sock'
            sock.parent.mkdir(parents=True, exist_ok=True)
            sock.unlink(missing_ok=True)
            if os.environ.get('MISSING_SOCKET'):
                fault()
                with open(root/'commands','a') as log: log.write(json.dumps(['fault','missing-socket'])+'\n')
            if not os.environ.get('MISSING_SOCKET'):
                s = socket.socket(socket.AF_UNIX)
                s.bind(str(sock))
                s.close()
            if os.environ.get('CORRUPT_RUNNING_DB'):
                fault()
                with open(root/'commands','a') as log: log.write(json.dumps(['fault','running-db'])+'\n')
                (root / 'etc/x-ui/x-ui.db').write_bytes(b'corrupt')
elif name == 'ss':
    if '-ltnp' in args:
        if os.environ.get('PANEL_LISTENER') != 'missing':
            address = '0.0.0.0' if os.environ.get('PANEL_LISTENER') == 'public' else '127.0.0.1'
            pid = 99999 if os.environ.get('PANEL_LISTENER') == 'foreign' else 54321
            print(f'LISTEN 0 128 {address}:10002 0.0.0.0:* users:(("x-ui",pid={pid},fd=1))')
        sys.exit(0)
    services = json.loads((root/'services.json').read_text())
    if services.get('x-ui') == 'active':
        broken = os.environ.get('DEAD_XRAY') or (os.environ.get('FAIL_INCOMING_XRAY') and
                    (root/'var/www/html/recovery-marker').read_text() == 'incoming')
        if not broken:
            if '-lxnp' in args:
                if not os.environ.get('MISSING_SOCKET') and (not os.environ.get('FAIL_ONCE') or (root/'dev/shm/uds2023.sock').exists()):
                    print(f'u_str LISTEN 0 128 {root}/dev/shm/uds2023.sock 0 users:(("xray",pid=43210,fd=1))')
            else:
                print('tcp LISTEN 0 128 127.0.0.1:8443 0.0.0.0:* users:(("xray",pid=43210,fd=2))')
                print('udp UNCONN 0 128 *:443 *:* users:(("xray",pid=43210,fd=3))')
    if (root / 'opt/AdGuardHome/managed.json').exists() and '-lxnp' not in args:
        m=json.loads((root / 'opt/AdGuardHome/managed.json').read_text())
        for protocol, key in (('tcp', 'web_port'), ('udp', 'dns_port')):
            print(f'{protocol} LISTEN 0 128 127.0.0.1:{m[key]} 0.0.0.0:* users:(("AdGuardHome",pid=12345,fd=5))')
elif name == 'crontab':
    path = root / 'crontab'
    if args == ['-l']:
        if not path.exists():
            print('no crontab for root', file=sys.stderr)
            sys.exit(1)
        print(path.read_text(), end='')
    elif args == ['-']:
        if os.environ.get('FAIL_CRON_WRITE') or (os.environ.get('FAIL_CRON_RECOVERY') and (root/'fault-used').exists()):
            fault(); sys.exit(1)
        path.write_text(sys.stdin.read())
    else:
        sys.exit(2)
elif name == 'ip':
    if os.environ.get('NO_IP'):
        sys.exit(1)
    print('8.8.8.8 via 192.0.2.1 src ' + os.environ.get('TEST_IPV4', '192.0.2.10'))
elif name == 'curl':
    if os.environ.get('FAIL_ACME'):
        sys.exit(1)
    url = args[-1]
    if '/dns-query?' in url:
        if os.environ.get('FAIL_AGH_HEALTH'): sys.exit(1)
        pathlib.Path(args[args.index('-D') + 1]).write_text('Content-Type: application/dns-message\r\n')
        pathlib.Path(args[args.index('-o') + 1]).write_bytes(bytes.fromhex('000080000001000100000000'))
        print('200', end=''); sys.exit(0)
    if '/login.html' in url:
        print('<html><script src="login.fixture.js"></script></html>'); sys.exit(0)
    if url == 'https://vision.example.com/' and os.environ.get('FAIL_VISION_TLS'):
        print('curl: (35) TLS unexpected eof while reading',file=sys.stderr); sys.exit(35)
    if url == 'https://vision.example.com/':
        print('vision cover'); sys.exit(0)
    if url.startswith('http://127.0.0.1/'):
        if '/.well-known/acme-challenge/' in url:
            print((root / 'var/www/acme/.well-known/acme-challenge' / url.rsplit('/', 1)[1]).read_text(), end='')
        else:
            host = next(a[6:] for a in args if a.startswith('Host: '))
            print('301 https://' + host + '/', end='')
    else:
        sys.exit(1)
elif name == 'dpkg-query':
    if args[-1] in os.environ.get('MISSING_PACKAGES', '').split() and args[-1] not in installed:
        sys.exit(1)
    print('install ok installed', end='')
elif name == 'apt-get':
    if os.environ.get('FAIL_APT') and (os.environ['FAIL_APT'] != 'install' or args[0] == 'install'):
        sys.exit(1)
    if args[0] == 'install':
        installed.update(arg for arg in args[1:] if not arg.startswith('-'))
        installed_path.write_text('\n'.join(sorted(installed)))
elif name in ('python3', 'gzip'):
    if name == 'python3' and args == ['-c', 'import configobj, cryptography'] and os.environ.get('FAIL_PYTHON_IMPORT'):
        sys.exit(1)
    sys.exit(subprocess.call([os.environ['REAL_' + name.upper()], *args]))
elif name == 'ufw':
    if args == ['status']:
        print('Status: ' + os.environ.get('UFW_STATE', 'inactive'))
    elif args[:1] == ['allow'] and os.environ.get('SCOPED_EFFECTS'):
        for name in ('user.rules','user6.rules'):
            with open(root/'etc/ufw'/name,'a') as out: out.write('allow '+args[1]+'\n')
    elif args == ['reload'] and os.environ.get('FAIL_UFW_RECOVERY'):
        sys.exit(1)
elif name == 'nginx':
    if os.environ.get('FAIL_NGINX'):
        fault(); sys.exit(1)
    if os.environ.get('NGINX_BIN') and '-c' in args:
        sys.exit(subprocess.call([os.environ['NGINX_BIN'], *args]))
    if os.environ.get('NGINX_BIN'):
        sys.exit(subprocess.call([os.environ['NGINX_BIN'], *args, '-p', str(root) + '/',
                                 '-c', str(root / 'etc/nginx/nginx.conf')]))
elif name == 'cp':
    if os.environ.get('FAIL_AGH_COPY') and any(a == str(root / 'opt/AdGuardHome') for a in args):
        sys.exit(1)
    if os.environ.get('FAIL_COPY') and any(a == str(root / 'usr/local/x-ui') for a in args):
        sys.exit(1)
    sys.exit(subprocess.call([os.environ['REAL_CP'], *args]))
elif name == 'dd':
    # Real zero data with sparse allocation keeps repetitive fixture tests small.
    sys.exit(subprocess.call([os.environ['REAL_DD'], *args, 'conv=sparse']))
elif name == 'install':
    # Non-root runs keep real copy/mode semantics while skipping root chown.
    filtered = []
    while args:
        arg = args.pop(0)
        if arg in ('-o', '-g'):
            args.pop(0)
        else:
            filtered.append(arg)
    sys.exit(subprocess.call([os.environ['REAL_INSTALL'], *filtered]))
elif name == 'tar':
    result = subprocess.call([os.environ['REAL_TAR'], *args])
    if not result and args[0] == '-czf' and os.environ.get('CORRUPT_ARCHIVE'):
        pathlib.Path(args[1]).write_bytes(b'bad archive')
    sys.exit(result)
elif name == 'id':
    sys.exit(1 if os.environ.get('MTR_ABSENT') else 0)
elif name == 'sysctl':
    if args[0] == '-p' and os.environ.get('FAIL_SYSCTL'): fault(); sys.exit(1)
    state=root/'runtime-sysctl.json'
    values=json.loads(state.read_text()) if state.exists() else {}
    if args[0] == '-n': print(values.get(args[1],'1'))
    elif args[0] == '-p':
        if '.rollback-' in args[1] and os.environ.get('FAIL_SYSCTL_RECOVERY'): sys.exit(1)
        for line in pathlib.Path(args[1]).read_text().splitlines():
            if '=' in line:
                key,value=line.split('=',1);values[key.strip()]=value.strip()
        state.write_text(json.dumps(values))
    sys.exit(0)
elif name == 'setcap':
    sys.exit(1 if pathlib.Path(args[-1]).name in os.environ.get('FAIL_SETCAP', '').split() else 0)
# useradd and non-root chown only record calls; no host mutation.
'''


class PersonalBackup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="personal-backup-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "host"
        self.root.mkdir()
        self.bin = Path(self.temp.name) / "mock-bin"
        self.bin.mkdir()
        commands = ['systemctl', 'crontab', 'ip', 'curl', 'dpkg-query', 'apt-get',
                    'ufw', 'nginx', 'ss', 'cp', 'dd', 'tar', 'python3', 'id', 'useradd', 'setcap', 'sysctl', 'mtr', 'mtr-packet']
        if os.geteuid() != 0:
            commands += ['chown', 'install']
        for name in commands:
            path = self.bin / name
            path.write_text(MOCK.replace('#!/usr/bin/env python3', '#!' + sys.executable, 1))
            path.chmod(0o755)
        sqlite = os.environ.get('SQLITE3_BIN') or shutil.which('sqlite3')
        if not sqlite:
            self.fail('sqlite3 CLI is required (CI installs it; local runs may set SQLITE3_BIN).')
        (self.bin / 'sqlite3').symlink_to(sqlite)
        self.script = Path(self.temp.name) / 'backup.sh'
        script=relocated(SOURCE, self.root)
        lock=re.search(r'^acquire_stack_lock\(\) \{.*?^\}',script,re.M|re.S)[0]
        script=script.replace(lock,lock.replace(str(self.root)+'/proc','/proc').replace('/run/3x-ui-auto-nginx',str(self.root)+'/run/3x-ui-auto-nginx'))
        (self.root/'run').mkdir()
        self.script.write_text(script)
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'FIXTURE_ROOT': str(self.root), 'REAL_CP': shutil.which('cp'),
                    'REAL_PYTHON3': sys.executable,
                    'REAL_DD': shutil.which('dd'), 'REAL_INSTALL': shutil.which('install'), 'REAL_TAR': shutil.which('tar')}
        self.write('/etc/os-release', Path('/etc/os-release').read_text())
        self.write('/etc/nginx/nginx.conf', f'pid {self.root}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{}}\n')
        for path in ('/usr/local/x-ui/bin', '/etc/letsencrypt/live/example.com',
                     '/root/cert/example.com', '/var/www/html', '/var/www/subpage'):
            self.path(path).mkdir(parents=True)
        db = self.path('/etc/x-ui/x-ui.db')
        db.parent.mkdir(parents=True)
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE settings (key TEXT, value TEXT)')
            conn.execute('INSERT INTO settings VALUES (?, ?)',
                         ('webCertFile', str(self.path('/root/cert/example.com/fullchain.pem'))))
            conn.executemany('INSERT INTO settings VALUES (?,?)', [
                ('webListen','127.0.0.1'), ('webPort','10002'), ('webBasePath','/panel/'),
                ('webKeyFile',str(self.path('/root/cert/example.com/privkey.pem'))),
                ('subListen','127.0.0.1'), ('subPort','10003'), ('subPath','/subscription/'),
                ('subJsonEnable','true'), ('subJsonPath','/jsonsub/'),
                ('subJsonURI','https://example.com/jsonsub/'),
                ('subCertFile',str(self.path('/root/cert/example.com/fullchain.pem'))),
                ('subKeyFile',str(self.path('/root/cert/example.com/privkey.pem')))])
            conn.execute('CREATE TABLE clients (uuid TEXT)')
            conn.execute("INSERT INTO clients VALUES ('fixture-secret-not-for-output')")
            # Real installer-derived managed transport/Host state, as restored on a v1.6 host.
            from test_personal_xhttp import seed
            inbounds, hosts = seed(domain='example.com', reality_domain='reality.example.com')
            for table, records in (('inbounds', list(inbounds.values())), ('hosts', hosts)):
                keys = list(records[0])
                conn.execute('CREATE TABLE '+table+' ('+','.join(keys)+')')
                for row in records:
                    conn.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in keys)+')',
                                 [relocated(value, self.root) if isinstance(value,str) else value
                                  for value in row.values()])
        self.write('/usr/local/x-ui/x-ui', '#!/bin/sh\necho 3.9.0\n', 0o755)
        self.path('/proc/54321').mkdir(parents=True)
        self.path('/proc/54321/exe').symlink_to(self.path('/usr/local/x-ui/x-ui'))
        self.write('/usr/local/x-ui/bin/xray-linux-amd64', '#!/bin/sh\necho Xray 26.9.30\n', 0o755)
        self.write('/usr/bin/x-ui', '#!/bin/sh\necho 3.9.0\n', 0o755)
        self.write('/usr/local/lib/3x-ui-pro/mtr-backend.py', '# backend\n', 0o755)
        self.write('/etc/systemd/system/x-ui.service', '[Service]\nExecStart=/usr/local/x-ui/x-ui\n')
        self.write('/etc/systemd/system/mtr-backend.service', '[Service]\nNoNewPrivileges=yes\n')
        for name in ('fullchain.pem', 'privkey.pem'):
            self.write('/etc/letsencrypt/live/example.com/' + name, 'fixture-cert\n', 0o600)
            self.path('/root/cert/example.com/' + name).symlink_to(self.path('/etc/letsencrypt/live/example.com/' + name))
        certificates(self.root)
        locations = ('/subscription/', '= /subscription', '~ ^/subscription/(?<clash_sub_id>[^/]+)$',
                     '/assets', '/assets/', '/jsonsub', '/jsonsub/')
        includes = '\n'.join('location ' + name + ' { proxy_pass https://127.0.0.1:10003; }' for name in locations)
        self.write('/etc/nginx/snippets/includes.conf', includes + '\n')
        from test_personal_xhttp import render
        self.write('/etc/nginx/sites-available/reality.example.com', relocated(
            render('cat > "/etc/nginx/sites-available/${reality_domain}"',
                   domain='example.com', reality_domain='reality.example.com'), self.root))
        self.write('/etc/nginx/nginx.conf', f'pid {self.root}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{ server {{ listen 127.0.0.1:10080; include {self.root}/etc/nginx/snippets/includes.conf; location /panel/ {{ proxy_pass https://127.0.0.1:10002; }} }} }}\n')
        self.write('/var/www/html/index.html', '192.0.2.10 unchanged')
        self.write('/var/www/subpage/clash.yaml', '192.0.2.10 unchanged')
        self.write('/var/www/diagnostics/index.html',
                   '<span id="server-ip">192.0.2.10</span><code id="server-ip-step">192.0.2.10</code>'
                   '<a href="https://192.0.2.10/">unchanged</a>')
        for name in ('speedtest.js', 'speedtest_worker.js'):
            self.write('/var/www/diagnostics/' + name, 'fixture-js')
        for name, size in (('test-1g.bin', 1024**3), ('test-512m.bin', 512*1024**2)):
            path = self.path('/var/www/diagnostics/testfiles/' + name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'wb') as f:
                f.truncate(size)
        self.write('/etc/sysctl.d/99-3x-ui-pro.conf', '\n'.join(PARAMS) + '\n')
        self.write('/etc/sysctl.d/99-proms-network.conf', 'bootstrap preserved\n')
        self.write('/etc/sysctl.conf', 'legacy sysctl preserved\n')
        self.write('/etc/ssh/sshd_config', 'bootstrap preserved\n')
        self.write('/etc/ufw/user.rules', 'SSH preserved\n')
        self.write('/etc/cron.d/unrelated', 'unrelated preserved\n')
        (self.root / 'crontab').write_text('@hourly /opt/unrelated\n')
        (self.root / 'services.json').write_text(json.dumps({'x-ui': 'active', 'nginx': 'active', 'mtr-backend': 'active',
                                                          'certbot.timer': 'active', 'certbot.service': 'inactive'}))
        (self.root / 'enabled.json').write_text(json.dumps({name: True for name in
                                                          ('x-ui','nginx','mtr-backend','certbot.timer')}))

    def path(self, absolute):
        return self.root / absolute.lstrip('/')

    def write(self, path, contents, mode=0o644):
        path = self.path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        path.chmod(mode)

    def run_tool(self, *args, **env):
        # Sourcing allows a root-check stub for unprivileged fixture execution.
        result = subprocess.run(['bash', '-c', 'source "$1"; shift; require_root() { :; }; '+('acquire_stack_lock() { :; }; ' if os.geteuid()!=0 else '')+'main "$@"',
                                 'fixture', str(self.script), *map(str, args)],
                                env={**self.env, **env}, text=True, capture_output=True)
        self.assertNotIn('fixture-secret-not-for-output', result.stdout + result.stderr)
        return result

    def commands(self):
        path = self.root / 'commands'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def backup(self, **env):
        result = self.run_tool('backup', **env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Backup completed successfully.', result.stdout)
        return next(self.path('/var/backups/x-ui').glob('*.tar.gz'))

    def member(self, path):
        return 'files/' + str(self.path(path)).lstrip('/')

    def changed_archive(self, archive, metadata=None, extra=None, db=None, omit=None, omit_metadata=()):
        fd, target = tempfile.mkstemp(dir=self.temp.name, suffix='.tar.gz')
        os.close(fd)
        target = Path(target)
        with tarfile.open(archive) as src, tarfile.open(target, 'w:gz') as dst:
            for item in src:
                if omit and (item.name == omit or item.name.startswith(omit + '/')):
                    continue
                data = src.extractfile(item).read() if item.isfile() else None
                if item.name == 'meta.json' and (metadata or omit_metadata):
                    meta = json.loads(data)
                    meta.update(metadata or {})
                    for key in omit_metadata: meta.pop(key, None)
                    data = json.dumps(meta).encode()
                if item.name == self.member('/etc/x-ui/x-ui.db') and db is not None:
                    data = db
                item = copy.copy(item)
                if data is not None:
                    item.size = len(data)
                dst.addfile(item, io.BytesIO(data) if data is not None else None)
            if extra:
                dst.addfile(extra, io.BytesIO(b'bad') if extra.isfile() else None)
        return target

    def test_restore_ignores_foreign_archived_certbot_objects(self):
        for vision in (False,True):
            with self.subTest(vision=vision):
                if vision: self.seed_vision()
                imported=('/etc/letsencrypt/renewal-hooks/deploy/foreign-import',
                          '/etc/letsencrypt/renewal-hooks/pre/foreign-import',
                          '/etc/letsencrypt/renewal-hooks/post/foreign-import',
                          '/etc/letsencrypt/live/foreign-import.example/fullchain.pem',
                          '/etc/letsencrypt/renewal/foreign-import.example.conf',
                          '/etc/letsencrypt/accounts/foreign.example/dir/unused/private_key.json',
                          '/etc/letsencrypt/cli.ini')
                for name in imported: self.write(name,'foreign archived artifact\n',0o755)
                archive=self.backup()
                for name in imported: self.path(name).unlink()
                preserved=('/etc/letsencrypt/renewal-hooks/deploy/target-admin',
                           '/etc/letsencrypt/live/target-admin.example/fullchain.pem',
                           '/etc/letsencrypt/renewal/target-admin.example.conf',
                           '/etc/letsencrypt/cli.ini')
                for name in preserved: self.write(name,'target administrator data\n',0o600)
                before={name:self.path(name).read_bytes() for name in preserved}
                result=self.run_tool('restore',archive)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                for name in imported:
                    if name not in preserved: self.assertFalse(self.path(name).exists(),'Foreign archived object imported: '+name)
                self.assertEqual({name:self.path(name).read_bytes() for name in preserved},before)
                for name in ('example.com','reality.example.com')+ (('vision.example.com',) if vision else ()):
                    self.assertTrue(self.path('/etc/letsencrypt/live/'+name+'/fullchain.pem').is_file())
                self.assertTrue(self.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx').is_file())
                self.assertEqual(self.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision').is_file(),vision)
                archive.unlink()

    def test_restore_account_conflict_refuses_before_service_stop(self):
        account='a'*32
        account_root='/etc/letsencrypt/accounts/acme.example.test/dir/'+account
        for name in ('meta.json','private_key.json','regr.json'):
            self.write(account_root+'/'+name,'{}\n',0o600)
        for name in ('example.com','reality.example.com'):
            cfg=ConfigObj(str(self.path('/etc/letsencrypt/renewal/'+name+'.conf')))
            cfg['renewalparams']['server']='https://acme.example.test/dir'
            cfg['renewalparams']['account']=account; cfg.write()
        archive=self.backup()
        self.write(account_root+'/private_key.json','{"target":true}\n',0o600)
        self.write('/etc/x-ui/marker','keep target')
        (self.root/'commands').write_text('')
        result=self.run_tool('restore',archive)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.path(account_root+'/private_key.json').read_text(),'{"target":true}\n')
        self.assertEqual(self.path('/etc/x-ui/marker').read_text(),'keep target')
        self.assertFalse(any(c[:2]==['systemctl','stop'] for c in self.commands()))

    def test_restore_preserves_foreign_certificate_lineages(self):
        archive = self.backup()
        foreign = self.path('/etc/letsencrypt/live/administrator.example/fullchain.pem')
        foreign.parent.mkdir(parents=True); foreign.write_text('administrator-owned certificate')
        result = self.run_tool('restore', str(archive))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(foreign.exists(), 'Restore deleted a foreign target lineage')
        self.assertEqual(foreign.read_text(), 'administrator-owned certificate')

    def test_old_archive_custom_vision_remark_is_not_project_ownership(self):
        with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("UPDATE inbounds SET remark='vision' WHERE id=(SELECT id FROM inbounds LIMIT 1)")
        archive=self.backup()
        result=self.run_tool('restore',archive)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM inbounds WHERE remark='vision'").fetchone()[0],1)

    def test_restore_refuses_foreign_project_named_deploy_hook_before_change(self):
        archive=self.backup()
        hook=self.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision')
        hook.write_text('#!/bin/sh\n# administrator hook\nexit 0\n'); hook.chmod(0o755)
        self.write('/etc/x-ui/marker','keep-target')
        (self.root/'commands').write_text('')
        result=self.run_tool('restore',archive)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('administrator hook',hook.read_text())
        self.assertEqual(self.path('/etc/x-ui/marker').read_text(),'keep-target')
        self.assertFalse(any(c[:2]==['systemctl','stop'] for c in self.commands()))

    def test_historical_hooks_restore_as_current_without_changing_archive(self):
        import hashlib
        from certificate_fixtures import historical_hook
        for mode in ('legacy','previous','current'):
            with self.subTest(mode=mode):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups);f.seed_vision()
                hooks={kind:f.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'+
                    ('-vision' if kind=='vision' else '')) for kind in ('panel','vision')}
                expected={kind:path.read_bytes() for kind,path in hooks.items()}
                if mode!='current':
                    for kind,path in hooks.items():path.write_text(historical_hook(f.root,kind,mode=='legacy'))
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    original=db.execute('SELECT * FROM inbounds ORDER BY id').fetchall()
                archive=f.backup();digest=hashlib.sha256(archive.read_bytes()).hexdigest()
                f.write('/etc/letsencrypt/renewal-hooks/deploy/administrator','# administrator hook\n',0o755)
                result=f.run_tool('restore',archive)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                for kind,path in hooks.items():self.assertEqual(path.read_bytes(),expected[kind])
                self.assertNotIn(b'check_xray_runtime',hooks['panel'].read_bytes())
                self.assertNotIn(b'curl',hooks['vision'].read_bytes())
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    self.assertEqual(db.execute('SELECT * FROM inbounds ORDER BY id').fetchall(),original)
                self.assertEqual(f.path('/etc/letsencrypt/renewal-hooks/deploy/administrator').read_text(),'# administrator hook\n')

    def test_update_hooks_is_scoped_idempotent_and_rolls_back_write_failure(self):
        from certificate_fixtures import historical_hook
        for scenario in ('legacy','previous','current','no-vision','unknown','symlink','mode','owner','write'):
            with self.subTest(scenario=scenario):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups)
                if scenario!='no-vision':f.seed_vision()
                hooks=[f.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx')]
                if scenario!='no-vision':hooks.append(f.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision'))
                expected={path:path.read_bytes() for path in hooks}
                if scenario!='current':
                    for path,kind in zip(hooks,('panel','vision')):
                        path.write_text(historical_hook(f.root,kind,scenario=='legacy'))
                if scenario=='unknown':hooks[-1].write_text(hooks[-1].read_text()+'\necho executed > "$FIXTURE_ROOT/untrusted-executed"\n')
                if scenario=='symlink':
                    target=f.root/'administrator-hook';target.write_bytes(hooks[-1].read_bytes());hooks[-1].unlink();hooks[-1].symlink_to(target)
                if scenario=='mode':hooks[-1].chmod(0o644)
                if scenario=='owner':os.chown(hooks[-1],1000,1000)
                if scenario=='write':
                    # One real rename fails after the first hook replacement; recovery must restore both.
                    wrapper=f.bin/'mv';wrapper.write_text('#!/bin/bash\nif [[ "${!#}" == *-vision && ! -e "$FIXTURE_ROOT/rename-failed" ]]; then touch "$FIXTURE_ROOT/rename-failed"; exit 1; fi\nexec /bin/mv "$@"\n');wrapper.chmod(0o755)
                before={path:path.read_bytes() for path in hooks}
                services=(f.root/'services.json').read_bytes();enabled=(f.root/'enabled.json').read_bytes()
                db=f.path('/etc/x-ui/x-ui.db').read_bytes();(f.root/'commands').write_text('')
                result=f.run_tool('update-hooks')
                if scenario in ('unknown','symlink','mode','owner','write'):
                    self.assertNotEqual(result.returncode,0)
                    self.assertEqual({p:p.read_bytes() for p in hooks},before)
                    self.assertNotIn('Hooks updated successfully',result.stdout)
                    if scenario=='write':self.assertTrue((f.root/'rename-failed').exists(),'Failure must reach second replacement')
                    if scenario=='symlink':self.assertTrue(hooks[-1].is_symlink())
                else:
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual({p:p.read_bytes() for p in hooks},expected)
                    stamps={p:p.stat().st_mtime_ns for p in hooks}
                    result=f.run_tool('update-hooks');self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual({p:p.stat().st_mtime_ns for p in hooks},stamps)
                    for p in hooks:self.assertEqual(p.stat().st_mode & 0o777,0o755)
                self.assertEqual((f.root/'services.json').read_bytes(),services)
                self.assertEqual((f.root/'enabled.json').read_bytes(),enabled)
                self.assertEqual(f.path('/etc/x-ui/x-ui.db').read_bytes(),db)
                self.assertFalse((f.root/'untrusted-executed').exists())
                self.assertFalse(any(c[0] in ('systemctl','curl','nginx','ss') for c in f.commands()))
                if scenario=='no-vision':self.assertFalse(f.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision').exists())

    def seed_vision(self):
        from test_integrated_features import helper
        vision = helper('vision')
        certificates(self.root, extra=('vision.example.com',))
        row = vision.inbound('vision.example.com', 12000, 12001,
                str(self.path('/etc/letsencrypt/live/vision.example.com/fullchain.pem')),
                str(self.path('/etc/letsencrypt/live/vision.example.com/privkey.pem')))
        with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
            iid = db.execute('SELECT max(id)+1 FROM inbounds').fetchone()[0]
            db.execute('INSERT INTO inbounds(id,user_id,remark,enable,listen,port,protocol,settings,stream_settings,tag,sniffing) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (iid,1,'vision',1,row['listen'],row['port'],row['protocol'],json.dumps(row['settings']),json.dumps(row['streamSettings']),row['tag'],json.dumps(row['sniffing'])))
            columns = {r[1] for r in db.execute('PRAGMA table_info(hosts)')}
            for column in ('sni', 'allow_insecure'):
                if column not in columns: db.execute('ALTER TABLE hosts ADD COLUMN '+column)
            db.execute('INSERT INTO hosts(inbound_id,sort_order,remark,address,port,security,sni,alpn,allow_insecure) VALUES(?,?,?,?,?,?,?,?,?)',
                (iid,0,'vision','vision.example.com',443,'same','vision.example.com','["http/1.1"]',0))
        self.write('/etc/nginx/sites-available/vision.conf', vision.fallback_config('vision.example.com',12001,str(self.path('/var/www/html'))))
        self.path('/etc/nginx/sites-enabled').mkdir(exist_ok=True)
        self.path('/etc/nginx/sites-enabled/vision.conf').symlink_to(self.path('/etc/nginx/sites-available/vision.conf'))
        self.write('/etc/nginx/sites-available/vision-acme.conf', '# Managed by 3x-ui Auto Nginx: Vision\n')
        self.write('/etc/nginx/stream-enabled/stream.conf','map $ssl_preread_server_name $sni_name {\n    hostnames;\n    vision.example.com vision;\n}\nupstream vision { server 127.0.0.1:12000; }\n')
        source = relocated(function('render_vision_hook'),self.root)
        body = subprocess.check_output(['bash','-c',source+'\nrender_vision_hook vision.example.com'],text=True)
        self.write('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision',body,0o755)

    def test_vision_backup_round_trip_and_missing_third_certificate_rejected(self):
        self.seed_vision()
        archive = self.backup()
        result = self.run_tool('restore',str(archive))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(self.path('/etc/letsencrypt/live/vision.example.com/fullchain.pem').is_file())
        hook = self.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision')
        current = hook.read_bytes()
        source = relocated(function('render_vision_hook'), self.root)
        hook.write_text(subprocess.check_output(['bash','-c',source+'\nrender_vision_hook vision.example.com legacy'],text=True))
        archive = self.backup()
        result = self.run_tool('restore',str(archive))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(hook.read_bytes(),current,'Old canonical archives must restore the ready-checking hook')
        broken = self.changed_archive(archive,omit=self.member('/etc/letsencrypt/live/vision.example.com/fullchain.pem'))
        marker = self.path('/etc/x-ui/preserved'); marker.write_text('current healthy state')
        result = self.run_tool('restore',str(broken))
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(marker.read_text(),'current healthy state')

    def test_vision_restore_uses_trusted_host_not_display_name(self):
        self.seed_vision()
        archive = self.backup()
        original = self.path('/etc/x-ui/x-ui.db').read_bytes()
        for remark, fault in (('vision',None),('🇷🇺 XTLS',None),('🇫🇮 XTLS',None),('🌐 XTLS',None),
                              ('🌐 XTLS','additional-host'),('🌐 XTLS','edited-inbound')):
            with self.subTest(remark=remark, fault=fault):
                edited = Path(self.temp.name)/'edited.db'; edited.write_bytes(original)
                with sqlite3.connect(edited) as db:
                    db.execute("UPDATE inbounds SET remark=? WHERE tag='inbound-12000'", (remark,))
                    columns = [r[1] for r in db.execute('PRAGMA table_info(inbounds)')]
                    row = dict(zip(columns,db.execute("SELECT * FROM inbounds WHERE tag='inbound-12000'").fetchone()))
                    row.update(id=200,remark='🇷🇺 XTLS',tag='administrator-inbound',port=12002)
                    db.execute('INSERT INTO inbounds ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',
                               [row[k] for k in columns])
                    if fault == 'additional-host':
                        db.execute("INSERT INTO hosts(inbound_id,address,port,security,sni,alpn,allow_insecure) VALUES(200,'vision.example.com',443,'same','vision.example.com','[\"http/1.1\"]',0)")
                    elif fault == 'edited-inbound':
                        db.execute("UPDATE inbounds SET protocol='trojan',enable=0 WHERE tag='inbound-12000'")
                candidate = self.changed_archive(archive, db=edited.read_bytes())
                marker = self.path('/etc/x-ui/preserved'); marker.write_text('target state')
                (self.root/'commands').write_text('')
                result = self.run_tool('restore',candidate)
                # Additional Hosts and a user-edited protocol do not establish ownership.
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                with sqlite3.connect(edited) as before, sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as after:
                    for table in ('inbounds','hosts'):
                        self.assertEqual(after.execute('SELECT * FROM '+table).fetchall(),
                                         before.execute('SELECT * FROM '+table).fetchall())

    def test_installer_integration(self):
        tuning = function('tune_system')
        self.assertNotIn('/etc/sysctl.conf', tuning)
        self.assertNotIn('sysctl --system', tuning)
        self.assertIn('/etc/sysctl.d/99-3x-ui-pro.conf', tuning)
        # Supported-kernel fixture; unavailable keys/BBR are covered separately.
        (self.root/'runtime-sysctl.json').write_text(json.dumps({'net.ipv4.tcp_available_congestion_control':'reno cubic bbr'}))
        run = 'msg_warn() { echo "$*" >&2; };\n' + relocated(tuning, self.root) + '\ntune_system; echo TUNING=$TUNING_RESULT\n'
        result = subprocess.run(['bash', '-eu', '-c', run], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = self.path('/etc/sysctl.d/99-3x-ui-pro.conf')
        self.assertEqual(path.read_text().splitlines(), PARAMS)
        self.assertIn('TUNING=applied',result.stdout)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual([c for c in self.commands() if c[0] == 'sysctl'],
                         [['sysctl','-n','net.ipv4.tcp_available_congestion_control']] +
                         [call for line in PARAMS for call in
                          (['sysctl','-n',line.split('=',1)[0]],['sysctl','-q','-w',line])])
        tool = function('install_backup_tool')
        self.assertIn('${GITHUB_RAW}/assets/backup/x-ui-backup.sh', tool)
        self.assertNotIn('mozaroc', tool)
        self.assertRegex(function('main'), r'    install_backup_tool \|\| \{ msg_err [^\n]*; exit 1; \}')
        download = Path(self.temp.name) / 'download.sh'
        download.write_text('#!/bin/bash\necho \"xui-backup:1 inspect backup-json lock-fd9\"\n')
        mock = ('backup_helper_compatible() { :; }; curl() { [[ "$2" == "$GITHUB_RAW/assets/backup/x-ui-backup.sh" ]] || return 9; '
                'cp "$DOWNLOAD" "$4"; }\nmsg_err() { echo "$*" >&2; }\n')
        install = relocated(function('backup_helper_path_safe')+'\n'+tool, self.root)
        result = subprocess.run(['bash', '-eu', '-c', mock + install + '\ninstall_backup_tool\n'],
                                env={**self.env, 'GITHUB_RAW': 'https://fixture.example/personal', 'DOWNLOAD': str(download)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        binary = self.path('/usr/local/bin/x-ui-backup')
        self.assertEqual(binary.read_text(), download.read_text())
        self.assertEqual(stat.S_IMODE(binary.stat().st_mode), 0o755)
        # Failed downloads preserve an already installed executable.
        result = subprocess.run(['bash', '-eu', '-c', mock + install + '\ncurl() { return 22; }; install_backup_tool\n'],
                                env={**self.env, 'GITHUB_RAW': 'https://fixture.example/personal'},
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(binary.read_text(), download.read_text())

    def test_archive_scope_permissions_and_active_service(self):
        archive = self.backup()
        self.assertEqual(stat.S_IMODE(archive.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(archive.stat().st_mode), 0o600)
        if os.geteuid() == 0:
            self.assertEqual((archive.stat().st_uid, archive.stat().st_gid), (0, 0))
            self.assertEqual((archive.parent.stat().st_uid, archive.parent.stat().st_gid), (0, 0))
        with tarfile.open(archive) as tar:
            names = tar.getnames()
            for path in ('/etc/x-ui/x-ui.db', '/usr/local/x-ui/x-ui', '/usr/bin/x-ui',
                         '/etc/nginx/nginx.conf', '/root/cert/example.com/privkey.pem',
                         '/etc/systemd/system/mtr-backend.service', '/etc/sysctl.d/99-3x-ui-pro.conf'):
                self.assertIn(self.member(path), names)
            self.assertFalse(any('testfiles' in n or '/etc/ufw' in n or '/etc/cron.d' in n or '/etc/ssh' in n
                                 or '99-proms-network' in n for n in names))
            self.assertNotIn('managed-root-cron', names)
            self.assertIn(self.member('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'), names)
            self.assertFalse(any('/var/www/acme/' in n for n in names))
            self.assertEqual(json.load(tar.extractfile('meta.json'))['format_version'], 3)
        calls = self.commands()
        stop = calls.index(['systemctl', 'stop', 'x-ui'])
        start = calls.index(['systemctl', 'start', 'x-ui'])
        later_copy = next(i for i, c in enumerate(calls) if c[0] == 'cp' and str(self.path('/etc/nginx')) in c)
        self.assertLess(stop, start)
        self.assertLess(start, later_copy)
        self.assertEqual(json.loads((self.root / 'services.json').read_text())['x-ui'], 'active')
        self.assertEqual(self.run_tool('list').returncode, 0)

    def test_service_states_survive_backup_and_repeated_restore(self):
        for service, active, enabled in (('x-ui','inactive',True), ('x-ui','active',False),
                ('x-ui','failed',False), ('nginx','inactive',False),
                ('mtr-backend','inactive',False), ('certbot.timer','inactive',False)):
            with self.subTest(service=service,active=active,enabled=enabled):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups)
                states=json.loads((f.root/'services.json').read_text());states[service]=active
                flags=json.loads((f.root/'enabled.json').read_text());flags[service]=enabled
                (f.root/'services.json').write_text(json.dumps(states))
                (f.root/'enabled.json').write_text(json.dumps(flags))
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    expected={name:db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                archive=f.backup(DEAD_XRAY='1',FAIL_ACME='1',FAIL_NGINX='1')
                original=archive.read_bytes();digest=hashlib.sha256(original).digest()
                self.assertEqual(json.loads((f.root/'services.json').read_text()),states)
                for _ in range(2):
                    (f.root/'services.json').write_text(json.dumps({name:'active' for name in flags} | {'certbot.service':'inactive'}))
                    (f.root/'enabled.json').write_text(json.dumps({name:True for name in flags}))
                    (f.root/'commands').write_text('')
                    result=f.run_tool('restore',archive,DEAD_XRAY='1',FAIL_ACME='1',FAIL_VISION_TLS='1')
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    restored=json.loads((f.root/'services.json').read_text())
                    for name,state in states.items():
                        self.assertEqual(restored.get(name,'inactive'),'inactive' if state=='failed' else state)
                    self.assertEqual(json.loads((f.root/'enabled.json').read_text()),flags)
                    if active!='active':self.assertNotIn(['systemctl','start',service],f.commands())
                    self.assertFalse(any(c[0] == 'curl' for c in f.commands()))
                    for call in f.commands():
                        if call[0] == 'ss':
                            self.assertEqual(call, ['ss','-H','-ltnp','sport = :10002'])
                    if states['x-ui'] != 'active':
                        self.assertFalse(any(c[0] == 'ss' for c in f.commands()))
                    with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                        self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                        self.assertEqual({name:db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                            for name in expected},expected)
                    self.assertEqual(archive.read_bytes(),original)
                    self.assertEqual(hashlib.sha256(archive.read_bytes()).digest(),digest)
                with tarfile.open(archive) as saved:
                    meta=json.load(saved.extractfile('meta.json'))
                self.assertEqual(meta['format_version'],3)
                self.assertEqual(meta['service_states'],{name:{'active':states[name],'enabled':value} for name,value in flags.items()})
                if service=='x-ui' and active=='inactive':
                    target={name:'active' for name in flags} | {'certbot.service':'inactive'}
                    target_enabled={name:name=='certbot.timer' for name in flags}
                    (f.root/'services.json').write_text(json.dumps(target))
                    (f.root/'enabled.json').write_text(json.dumps(target_enabled))
                    f.write('/etc/x-ui/target-only','previous target')
                    result=f.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1')
                    self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertNotIn('Restore completed successfully.',result.stdout)
                    self.assertTrue((f.root/'fault-used').exists(),'Intended service-health fault was not reached')
                    self.assertEqual(f.path('/etc/x-ui/target-only').read_text(),'previous target')
                    self.assertEqual(json.loads((f.root/'services.json').read_text()),target)
                    self.assertEqual(json.loads((f.root/'enabled.json').read_text()),target_enabled)
                    self.assertIn('Previous managed state/service states restored and checked',result.stderr)
                    self.assertFalse(list(f.path('/var/backups/x-ui').glob('.rollback-*')))
                    self.assertEqual(archive.read_bytes(),original)

    def test_service_metadata_rejects_invalid_state_before_target_mutation(self):
        archive=self.backup()
        valid={name:{'active':'active','enabled':True} for name in ('x-ui','nginx','mtr-backend','certbot.timer')}
        for bad in (None, [], {}, {**valid,'ssh':{'active':'active','enabled':True}},
                    {**valid,'x-ui':{'active':'activating','enabled':True}},
                    {**valid,'x-ui':{'active':'active','enabled':'false'}},
                    {**valid,'x-ui':{'active':'active','enabled':True,'command':'arbitrary'}}):
            with self.subTest(metadata=bad):
                candidate=self.changed_archive(archive,metadata={'service_states':bad})
                before=self.path('/etc/x-ui/x-ui.db').read_bytes()
                states=(self.root/'services.json').read_bytes();enabled=(self.root/'enabled.json').read_bytes()
                (self.root/'commands').write_text('')
                result=self.run_tool('restore',candidate)
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertIn('service-state metadata',result.stderr)
                self.assertEqual(self.path('/etc/x-ui/x-ui.db').read_bytes(),before)
                self.assertEqual((self.root/'services.json').read_bytes(),states)
                self.assertEqual((self.root/'enabled.json').read_bytes(),enabled)
                self.assertFalse(any(c[:2]==['systemctl','stop'] for c in self.commands()))

    def test_legacy_v3_without_service_metadata_keeps_original_startup_contract(self):
        archive=self.changed_archive(self.backup(),omit_metadata=('service_states',))
        with tarfile.open(archive) as saved:self.assertNotIn('service_states',json.load(saved.extractfile('meta.json')))
        original=archive.read_bytes()
        (self.root/'services.json').write_text(json.dumps({'certbot.service':'inactive'}))
        (self.root/'enabled.json').write_text('{}')
        result=self.run_tool('restore',archive)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        states=json.loads((self.root/'services.json').read_text());enabled=json.loads((self.root/'enabled.json').read_text())
        for name in ('x-ui','nginx','mtr-backend','certbot.timer'):
            self.assertEqual(states[name],'active');self.assertIs(enabled[name],True)
        self.assertEqual(archive.read_bytes(),original)

    def test_recreatable_cert_links_are_optional_but_original_data_is_required(self):
        for name in ('fullchain.pem','privkey.pem'):self.path('/root/cert/example.com/'+name).unlink()
        archive=self.backup();result=self.run_tool('restore',archive)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for name in ('fullchain.pem','privkey.pem'):self.assertTrue(self.path('/root/cert/example.com/'+name).is_file())
        self.path('/usr/bin/x-ui').unlink()
        result=self.run_tool('backup')
        self.assertNotEqual(result.returncode,0);self.assertIn('Required managed path is missing',result.stderr)
        self.assertNotIn('Backup completed successfully.',result.stdout)

    def test_inactive_service_is_not_started(self):
        state = self.root / 'services.json'
        services=json.loads(state.read_text());services['x-ui']='inactive';state.write_text(json.dumps(services))
        self.backup()
        self.assertNotIn(['systemctl', 'start', 'x-ui'], self.commands())
        self.assertNotIn(['systemctl', 'stop', 'x-ui'], self.commands())
        self.assertEqual(json.loads(state.read_text())['x-ui'], 'inactive')

    def test_incomplete_final_archive_is_not_kept(self):
        result = self.run_tool('backup', CORRUPT_ARCHIVE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Backup completed successfully.', result.stdout)
        self.assertEqual(list(self.path('/var/backups/x-ui').iterdir()), [])
        self.assertEqual(json.loads((self.root / 'services.json').read_text())['x-ui'], 'active')

    def test_backup_failures_restore_service_and_remove_archive(self):
        for failure in ('collection', 'database'):
            with self.subTest(failure=failure):
                if failure == 'database':
                    self.path('/etc/x-ui/x-ui.db').write_bytes(b'corrupt')
                result = self.run_tool('backup', FAIL_COPY='1' if failure == 'collection' else '')
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Backup completed successfully.', result.stdout)
                self.assertEqual(json.loads((self.root / 'services.json').read_text())['x-ui'], 'active')
                self.assertIn(['systemctl', 'start', 'x-ui'], self.commands())
                self.assertEqual(list(self.path('/var/backups/x-ui').iterdir()), [])

    def test_restore_accepts_managed_dev_null_error_log_with_real_nginx(self):
        import hashlib
        self.assertTrue(os.environ.get('NGINX_BIN'), 'This regression requires real nginx -t')
        config = self.path('/etc/nginx/nginx.conf')
        original = config.read_text().replace('error_log stderr;', 'error_log /dev/null crit;')
        config.write_text(original)
        archive = self.backup()
        digest = hashlib.sha256(archive.read_bytes()).digest()
        result = self.run_tool('restore', archive)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(config.read_text(), original, 'Preflight must only change its private nginx representation')
        self.assertEqual(hashlib.sha256(archive.read_bytes()).digest(), digest)

    def test_restore_preflight_rejects_before_replacement(self):
        archive = self.backup()
        corrupt = Path(self.temp.name) / 'corrupt.tar.gz'
        corrupt.write_bytes(b'not gzip')
        cases = [(corrupt, {}), (archive, {'format_version': 1}), (archive, {'format_version': 2}), (archive, {'os_id': 'other'}),
                 (archive, {'os_version': '99'}), (archive, {'arch': 'other'})]
        cases.append((self.changed_archive(archive, omit=self.member('/usr/local/x-ui/bin/xray-linux-amd64')), {}))
        unsafe_location = self.path('/etc/nginx/input.tar.gz')
        shutil.copy2(archive, unsafe_location)
        cases.append((unsafe_location, {}))
        marker = self.path('/etc/x-ui/preserved')
        marker.write_text('untouched')
        for file, meta in cases:
            with self.subTest(metadata=meta, file=file.name):
                (self.root / 'commands').write_text('')
                candidate = self.changed_archive(file, metadata=meta) if meta else file
                result = self.run_tool('restore', candidate)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(marker.read_text(), 'untouched')
                self.assertFalse(any(c[:2] == ['systemctl', 'stop'] or c[0] == 'apt-get' for c in self.commands()))
        bad_db = self.changed_archive(archive, db=b'corrupt')
        result = self.run_tool('restore', bad_db)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), 'untouched')

    def test_archive_paths_and_links_are_validated(self):
        archive = self.backup()
        for name, target in (('../escape', None), ('managed-root-cron', None), ('files/etc/ssh/injected', None),
                             (self.member('/etc/nginx/evil'), '/etc/ssh')):
            with self.subTest(name=name):
                extra = tarfile.TarInfo(name)
                if target:
                    extra.type = tarfile.SYMTYPE
                    extra.linkname = target
                else:
                    extra.size = 3
                result = self.run_tool('restore', self.changed_archive(archive, extra=extra))
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Restore completed successfully.', result.stdout)

    def seed_amneziawg(self):
        import base64
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
        key = X25519PrivateKey.generate()
        server = {
            'privateKey':base64.b64encode(key.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),
            'publicKey':base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode(),
            'headerProtectionKey':base64.b64encode(os.urandom(32)).decode(),
            'subnetIp':'10.8.1.0','subnetCidr':24,'primaryDns':'8.8.8.8','secondaryDns':'8.8.4.4',
            'jc':4,'jmin':60,'jmax':180,'s1':30,'s2':40,'s3':20,'s4':15,
            'h1':'12345','h2':'600000000','h3':'1200000000','h4':'1800000000','i1':'<r 64>',
            'contentPaddingAddition':'12-24','rekeyAfterTime':'110-130','rejectAfterTime':'170-220',
            'rekeyTimeout':'4-7','keepaliveTimeout':'10-16','maxHandshakeAttempts':'20-30',
            'randomTrailers':True,'disableCookies':True,'ipv6Enabled':False,'routeThroughXray':False,
        }
        with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
            keys = [row[1] for row in db.execute('PRAGMA table_info(inbounds)')]
            row = dict(zip(keys,db.execute('SELECT * FROM inbounds LIMIT 1').fetchone()))
            row.update(id=db.execute('SELECT max(id)+1 FROM inbounds').fetchone()[0], tag='inbound-8443-udp',protocol='amneziawg',port=8443,
                       listen='0.0.0.0',enable=1,settings=json.dumps({'server':server,'clients':[]}))
            db.execute('INSERT INTO inbounds ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',
                       [row[k] for k in keys])
        return keys, row

    def test_amneziawg_backup_restore_preserves_state_and_firewall(self):
        import hashlib
        keys, row = self.seed_amneziawg()
        archive = self.backup()
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        for _ in range(2):
            result = self.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
                restored = dict(zip(keys,db.execute("SELECT * FROM inbounds WHERE tag='inbound-8443-udp'").fetchone()))
                self.assertTrue(restored == row,"AWG settings changed during restore")
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone(),('ok',))
            self.assertIn(['ufw','allow','8443/udp'],self.commands())
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)

    def test_native_awg_empty_stream_survives_restore(self):
        self.seed_amneziawg()
        with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("UPDATE inbounds SET stream_settings='' WHERE protocol='amneziawg'")
            saved = db.execute("SELECT * FROM inbounds WHERE protocol='amneziawg'").fetchall()
        archive = self.backup()
        result = self.run_tool('restore', archive)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with sqlite3.connect(self.path('/etc/x-ui/x-ui.db')) as db:
            self.assertEqual(db.execute("SELECT * FROM inbounds WHERE protocol='amneziawg'").fetchall(), saved)
            db.execute("UPDATE inbounds SET protocol='hysteria2' WHERE protocol='amneziawg'")
        archive.unlink()
        invalid = self.backup()
        (self.root/'commands').write_text('')
        result = self.run_tool('restore', invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[:2] == ['systemctl','stop'] and c[-1] == 'x-ui' for c in self.commands()))

    def test_panel_listener_failure_recovers_and_stopped_panel_stays_stopped(self):
        archive = self.backup()
        self.write('/etc/x-ui/target-marker', 'previous target')
        for fault in ('missing', 'foreign', 'public'):
            with self.subTest(fault=fault):
                result = self.run_tool('restore', archive, PANEL_LISTENER=fault)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Previous managed state/service states restored and checked', result.stderr)
                self.assertEqual(self.path('/etc/x-ui/target-marker').read_text(), 'previous target')
        states = json.loads((self.root/'services.json').read_text())
        states['x-ui'] = 'inactive'
        (self.root/'services.json').write_text(json.dumps(states))
        archive.unlink()
        archive = self.backup()
        result = self.run_tool('restore', archive, PANEL_LISTENER='missing')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads((self.root/'services.json').read_text())['x-ui'], 'inactive')

    def test_round_trip_cron_firewall_diagnostics_and_sysctl(self):
        self.write('/var/www/acme/.well-known/acme-challenge/stale', 'stale challenge must not be archived')
        archive = self.backup()
        self.write('/var/www/html/index.html', 'modified')
        self.write('/etc/nginx/stale', 'stale')
        self.path('/root/cert/example.com/fullchain.pem').unlink()
        preserved = {p: self.path(p).read_bytes() for p in ('/etc/ssh/sshd_config', '/etc/ufw/user.rules',
                    '/etc/cron.d/unrelated', '/etc/sysctl.d/99-proms-network.conf', '/etc/sysctl.conf',
                    '/etc/systemd/system/mtr-backend.service')}
        (self.root / 'crontab').write_text('@hourly /opt/current-unrelated\n' + CRON + '\n')
        (self.root / 'commands').write_text('')
        result = self.run_tool('restore', archive, TEST_IPV4='198.51.100.20', MTR_ABSENT='1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Restore completed successfully.', result.stdout)
        self.assertFalse(self.path('/etc/nginx/stale').exists())
        self.assertEqual(self.path('/var/www/html/index.html').read_text(), '192.0.2.10 unchanged')
        self.assertEqual(self.path('/var/www/subpage/clash.yaml').read_text(), '192.0.2.10 unchanged')
        for path, content in preserved.items():
            self.assertEqual(self.path(path).read_bytes(), content)
        self.assertEqual((self.root / 'crontab').read_text(), '@hourly /opt/current-unrelated\n')
        self.assertTrue(self.path('/var/www/acme/.well-known/acme-challenge').is_dir())
        self.assertEqual(list(self.path('/var/www/acme/.well-known/acme-challenge').iterdir()), [])
        html = self.path('/var/www/diagnostics/index.html').read_text()
        self.assertIn('id="server-ip">198.51.100.20<', html)
        self.assertIn('id="server-ip-step">198.51.100.20<', html)
        self.assertIn('https://192.0.2.10/', html)
        for name, size in (('test-15k.bin', 15*1024), ('test-17k.bin', 17*1024),
                           ('test-100m.bin', 100*1024**2), ('test-1g.bin', 1024**3)):
            self.assertEqual(self.path('/var/www/diagnostics/testfiles/' + name).stat().st_size, size)
        self.assertFalse(self.path('/var/www/diagnostics/testfiles/test-512m.bin').exists())
        calls = self.commands()
        self.assertEqual([c for c in calls if c[0] == 'ufw'], [
            ['ufw', 'status'], ['ufw', 'allow', '80/tcp'], ['ufw', 'allow', '443/tcp'], ['ufw', 'allow', '443/udp'], ['ufw', 'status']])
        self.assertEqual([c for c in calls if c[0] == 'sysctl'],
                         [['sysctl','-n',line.split('=',1)[0]] for line in PARAMS] +
                         [['sysctl', '-p', str(self.path('/etc/sysctl.d/99-3x-ui-pro.conf'))]])
        self.assertFalse(any(c[0] == 'apt-get' for c in calls))
        self.assertIn(['useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'mtr-backend'], calls)
        self.assertEqual(len([c for c in calls if c[0] == 'setcap']), 2)
        self.assertEqual(stat.S_IMODE(self.path('/etc/sysctl.d/99-3x-ui-pro.conf').stat().st_mode), 0o644)
        if os.geteuid() == 0:
            managed = self.path('/etc/sysctl.d/99-3x-ui-pro.conf').stat()
            self.assertEqual((managed.st_uid, managed.st_gid), (0, 0))
            diagnostics = self.path('/var/www/diagnostics/index.html').stat()
            self.assertEqual(diagnostics.st_uid, pwd.getpwnam('www-data').pw_uid)
        self.assertTrue(stat.S_ISSOCK(self.path('/dev/shm/uds2023.sock').stat().st_mode))
        self.assertIn('[WARN] UFW is inactive', result.stderr)
        # Same archive is safe to apply twice, and is never modified.
        digest = archive.read_bytes()
        again = self.run_tool('restore', archive, TEST_IPV4='198.51.100.20')
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(archive.read_bytes(), digest)

    def test_package_failure_is_before_managed_replacement(self):
        archive = self.backup()
        self.write('/etc/x-ui/marker', 'preserve')
        (self.root / 'commands').write_text('')
        result = self.run_tool('restore', archive, MISSING_PACKAGES='sqlite3 mtr', FAIL_APT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.path('/etc/x-ui/marker').exists())
        self.assertFalse(any(c[:2] == ['systemctl', 'stop'] for c in self.commands()))
        result = self.run_tool('restore', archive, MISSING_PACKAGES='sqlite3 mtr')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        installs = [c for c in self.commands() if c[:2] == ['apt-get', 'install']]
        self.assertEqual(installs, [['apt-get', 'install', '-y', '--no-install-recommends', 'sqlite3', 'mtr']])

    def test_clean_host_restore_repairs_missing_panel_links(self):
        archive = self.changed_archive(self.backup(), omit=self.member('/root/cert'))
        for path in ('/etc/x-ui', '/usr/local/x-ui', '/etc/nginx', '/etc/letsencrypt', '/root/cert',
                     '/usr/local/lib/3x-ui-pro', '/var/www/html', '/var/www/subpage', '/var/www/diagnostics'):
            shutil.rmtree(self.path(path))
        for path in ('/usr/bin/x-ui', '/etc/systemd/system/x-ui.service', '/etc/systemd/system/mtr-backend.service'):
            self.path(path).unlink()
        (self.root / 'crontab').unlink()
        result = self.run_tool('restore', archive, NO_IP='1', MTR_ABSENT='1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.path('/root/cert/example.com/fullchain.pem').is_symlink())
        self.assertTrue(self.path('/root/cert/example.com/privkey.pem').exists())
        self.assertIn('192.0.2.10', self.path('/var/www/diagnostics/index.html').read_text())
        self.assertIn('Cannot detect current IPv4', result.stderr)
        self.assertFalse((self.root / 'crontab').exists())

    def test_restore_dependencies_and_timer_contract(self):
        archive = self.backup()
        missing = 'certbot python3-configobj python3-cryptography procps iproute2 tar gzip tzdata'
        (self.root / 'commands').write_text('')
        (self.root / 'crontab').write_text('@hourly /opt/unrelated\n' + CRON + '\n' + CRON + '\n')
        result = self.run_tool('restore', archive, MISSING_PACKAGES=missing)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.commands()
        packages = [package for c in calls if c[:2] == ['apt-get', 'install'] for package in c[4:]]
        self.assertCountEqual(packages, missing.split())
        self.assertNotIn('cron', packages)
        self.assertNotIn('python3-certbot-nginx', packages)
        activation = calls.index(['systemctl', 'enable', '--now', 'certbot.timer'])
        self.assertGreater(activation, calls.index(['systemctl', 'start', 'nginx']))
        for command in ('is-active', 'is-enabled'):
            self.assertIn(['systemctl', command, '--quiet', 'certbot.timer'], calls)
        self.assertEqual((self.root / 'crontab').read_text(), '@hourly /opt/unrelated\n')
        self.assertEqual(json.loads((self.root / 'services.json').read_text())['certbot.timer'], 'active')
        self.assertTrue(json.loads((self.root / 'enabled.json').read_text())['certbot.timer'])

    def test_restore_bootstraps_archive_tools_before_first_use(self):
        archive = self.backup()
        saved_archive = archive.read_bytes()
        self.write('/etc/x-ui/marker', 'unchanged')
        for name in ('python3', 'gzip'):
            wrapper = self.bin / name
            wrapper.write_text(MOCK.replace('#!/usr/bin/env python3', '#!' + sys.executable, 1))
            wrapper.chmod(0o755)
        self.env.update(REAL_PYTHON3=sys.executable, REAL_GZIP=shutil.which('gzip'))
        for failed in (True, False):
            with self.subTest(bootstrap_failure=failed):
                (self.root / 'commands').write_text('')
                result = self.run_tool('restore', archive, MISSING_PACKAGES='python3 gzip tar',
                                       FAIL_APT='install' if failed else '')
                calls = self.commands()
                self.assertEqual(archive.read_bytes(), saved_archive)
                if failed:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('Restore completed successfully.', result.stdout)
                    self.assertEqual(self.path('/etc/x-ui/marker').read_text(), 'unchanged')
                    self.assertFalse(any(c[0] in ('python3', 'gzip', 'tar') or c[:2] == ['systemctl', 'stop'] for c in calls))
                else:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('Restore completed successfully.', result.stdout)
                    install = calls.index(['apt-get', 'install', '-y', '--no-install-recommends', 'python3', 'gzip', 'tar'])
                    gzip_test = next(i for i, c in enumerate(calls) if c[:2] == ['gzip', '-t'])
                    validation = next(i for i, c in enumerate(calls) if c[:3] == ['python3', '-', str(archive)])
                    extraction = next(i for i, c in enumerate(calls) if c[:2] == ['tar', '-xzf'])
                    self.assertLess(install, gzip_test)
                    self.assertLess(gzip_test, validation)
                    self.assertLess(validation, extraction)

    def test_restore_renewal_failures_never_report_success(self):
        for env in ({'FAIL_CERTBOT_ENABLE': '1'}, {'FAIL_CRON_WRITE': '1'}, {'FAIL_HEALTH_SERVICE': 'certbot.timer'},
                    *({'BREAK_FINAL_RENEWAL': state} for state in ('active', 'enabled'))):
            with self.subTest(failure=env):
                f = PersonalBackup('runTest'); f.setUp()
                self.addCleanup(f.doCleanups)
                archive = f.backup()
                f.write('/etc/x-ui/target-marker', 'previous target')
                initial_services = json.loads((f.root/'services.json').read_text())
                initial_enabled = json.loads((f.root/'enabled.json').read_text())
                (f.root / 'commands').write_text('')
                (f.root / 'crontab').write_text((CRON+'\n' if 'FAIL_CRON_WRITE' in env else '')+'@daily unrelated\n')
                result = f.run_tool('restore', archive, FAIL_ONCE='1', **env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Restore completed successfully.', result.stdout)
                self.assertIn('[FAIL]', result.stderr)

                calls = f.commands()
                self.assertEqual(f.path('/etc/x-ui/target-marker').read_text(), 'previous target')
                self.assertEqual(json.loads((f.root/'services.json').read_text()), initial_services)
                self.assertEqual({k for k,v in json.loads((f.root/'enabled.json').read_text()).items() if v},
                                 {k for k,v in initial_enabled.items() if v})
                self.assertFalse(list(f.path('/var/backups/x-ui').glob('.restore-*')))
                if 'FAIL_CRON_WRITE' in env:
                    self.assertIn(['crontab','-'], calls)
                else:
                    self.assertIn(['systemctl','enable','--now','certbot.timer'], calls)
                if 'BREAK_FINAL_RENEWAL' in env:
                    self.assertIn(['fault','renewal',env['BREAK_FINAL_RENEWAL']], calls)
                retained = False
                self.assertEqual(bool(list(f.path('/var/backups/x-ui').glob('.rollback-*'))), retained)
                self.assertIn('Automatic rollback could not be verified' if retained else
                              'Previous managed state/service states restored and checked', result.stderr)
                self.assertIn('@daily unrelated\n', (f.root/'crontab').read_text())
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')

    def test_v2_is_explicitly_rejected_without_extraction(self):
        archive = self.changed_archive(self.backup(), metadata={'format_version': 2})
        (self.root / 'commands').write_text('')
        self.write('/etc/x-ui/marker', 'unchanged')
        result = self.run_tool('restore', archive)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Legacy backup format 2 is not supported', result.stderr)
        self.assertIn('matching older x-ui-backup version', result.stderr)
        self.assertEqual(self.path('/etc/x-ui/marker').read_text(), 'unchanged')
        self.assertFalse(any(c[:2] == ['tar', '-xzf'] or c[:2] == ['systemctl', 'stop'] for c in self.commands()))

    def test_backup_host_support_matrix(self):
        for os_id,version,accepted in (('ubuntu','24.04',True),('ubuntu','26.04',True),('debian','13',True),('debian','12',False),('ubuntu','22.04',False)):
            with self.subTest(os_id=os_id,version=version):
                self.write('/etc/os-release', f'ID={os_id}\nVERSION_ID="{version}"\n')
                result = subprocess.run(['bash','-c','source "$1"; host_identity; echo accepted','fixture',str(self.script)],
                                        env=self.env,text=True,capture_output=True)
                self.assertEqual(result.returncode,0 if accepted else 1,result.stderr)
                self.assertEqual('accepted' in result.stdout,accepted)

    def test_backup_preserves_unhealthy_or_inactive_user_state(self):
        for scenario in ('tls-eof','vision-disabled','transports-disabled','timer-disabled',
                         'timer-inactive','acme','nginx','stopped','renewal-config'):
            with self.subTest(scenario=scenario):
                f=PersonalBackup('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
                if scenario in ('tls-eof','vision-disabled'): f.seed_vision()
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    if scenario=='vision-disabled': db.execute("UPDATE inbounds SET enable=0 WHERE tag='inbound-12000'")
                    if scenario=='transports-disabled': db.execute("UPDATE inbounds SET enable=0 WHERE protocol IN ('vless','hysteria')")
                    expected=db.execute('SELECT id,enable,settings,stream_settings FROM inbounds ORDER BY id').fetchall()
                services=json.loads((f.root/'services.json').read_text())
                if scenario=='stopped': services['x-ui']='inactive'
                if scenario=='timer-inactive': services['certbot.timer']='inactive'
                (f.root/'services.json').write_text(json.dumps(services))
                enabled={'certbot.timer':scenario!='timer-disabled'}
                (f.root/'enabled.json').write_text(json.dumps(enabled))
                if scenario=='renewal-config':
                    conf=f.path('/etc/letsencrypt/renewal/example.com.conf')
                    conf.write_text(conf.read_text().replace('authenticator = webroot','authenticator = standalone'))
                flags={'FAIL_VISION_TLS':'1'} if scenario=='tls-eof' else {}
                if scenario=='transports-disabled': flags['DEAD_XRAY']='1'
                if scenario=='acme': flags['FAIL_ACME']='1'
                if scenario=='nginx': flags['FAIL_NGINX']='1'
                archive=f.backup(**flags)
                self.assertEqual(json.loads((f.root/'services.json').read_text()),services)
                self.assertEqual(json.loads((f.root/'enabled.json').read_text()),enabled)
                calls=f.commands()
                self.assertFalse(any(c[0] in ('curl','ss','nginx') for c in calls),calls)
                if scenario=='stopped': self.assertNotIn(['systemctl','start','x-ui'],calls)
                with tarfile.open(archive) as saved:
                    copied=Path(f.temp.name)/'archived.db'
                    copied.write_bytes(saved.extractfile(f.member('/etc/x-ui/x-ui.db')).read())
                with sqlite3.connect(copied) as db:
                    self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                    self.assertEqual(db.execute('SELECT id,enable,settings,stream_settings FROM inbounds ORDER BY id').fetchall(),expected)

    def test_restore_and_rollback_preserve_disabled_transports_without_network(self):
        f=self; f.seed_vision()
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("UPDATE inbounds SET enable=0 WHERE protocol IN ('vless','hysteria')")
            expected=db.execute('SELECT id,enable,settings,stream_settings FROM inbounds ORDER BY id').fetchall()
        archive=f.backup()
        original=archive.read_bytes()
        for failure in (False,True):
            with self.subTest(rollback=failure):
                marker=f.path('/etc/x-ui/target-marker'); marker.write_text('previous')
                (f.root/'commands').write_text('')
                result=f.run_tool('restore',archive,DEAD_XRAY='1',FAIL_VISION_TLS='1',FAIL_ACME='1',
                                  FAIL_HEALTH_SERVICE='mtr-backend' if failure else '',FAIL_ONCE='1' if failure else '')
                self.assertEqual(result.returncode,1 if failure else 0,result.stdout+result.stderr)
                if failure:
                    self.assertEqual(marker.read_text(),'previous')
                    self.assertIn('Previous managed state/service states restored and checked',result.stderr)
                else: self.assertIn('Restore completed successfully.',result.stdout)
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                    self.assertEqual(db.execute('SELECT id,enable,settings,stream_settings FROM inbounds ORDER BY id').fetchall(),expected)
                self.assertEqual(archive.read_bytes(),original)
                self.assertFalse(any(c[0] == 'curl' for c in f.commands()))
                for call in f.commands():
                    if call[0] == 'ss':
                        self.assertEqual(call, ['ss','-H','-ltnp','sport = :10002'])
                self.assertFalse(list(f.path('/var/backups/x-ui').glob('.rollback-*')))

    def test_backup_still_fails_for_corrupt_db_or_failed_service_resume(self):
        for failure in ('database','resume','copy-cleanup'):
            with self.subTest(failure=failure):
                f=PersonalBackup('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
                flags={}
                if failure=='database': f.path('/etc/x-ui/x-ui.db').write_bytes(b'not sqlite')
                if failure=='resume': flags['FAIL_HEALTH_SERVICE']='x-ui'
                if failure=='copy-cleanup': flags.update(FAIL_COPY='1',FAIL_HEALTH_SERVICE='x-ui')
                result=f.run_tool('backup',**flags)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('Backup completed successfully.',result.stdout)
                self.assertFalse(list(f.path('/var/backups/x-ui').glob('*.tar.gz')))
                self.assertFalse(list(f.path('/var/backups/x-ui').glob('*.partial')))
                if failure!='database': self.assertIn('Cannot',result.stderr)

    def test_backup_pauses_certbot_before_collection_and_resumes_on_success(self):
        self.backup()
        calls=self.commands()
        pause=calls.index(['systemctl','stop','certbot.timer'])
        idle=calls.index(['systemctl','is-active','certbot.service'])
        collection=next(i for i,c in enumerate(calls) if c[0]=='cp' and str(self.path('/etc/letsencrypt')) in c)
        resume=calls.index(['systemctl','start','certbot.timer'])
        self.assertLess(pause,idle);self.assertLess(idle,collection);self.assertLess(collection,resume)
        self.assertEqual(json.loads((self.root/'services.json').read_text())['certbot.timer'],'active')
        self.assertTrue(json.loads((self.root/'enabled.json').read_text())['certbot.timer'])
        self.assertNotIn(['systemctl','stop','certbot.service'],calls)

    def test_active_certbot_prevents_backup_and_restore_without_killing_it(self):
        archive=self.backup()
        for operation in ('backup','restore'):
            states=(('active','active'),('activating','active'))
            if operation=='restore':states+=(('active','inactive'),)
            for running,timer_state in states:
                with self.subTest(operation=operation,running=running,timer_state=timer_state):
                    services=json.loads((self.root/'services.json').read_text())
                    services['certbot.service']=running
                    services['certbot.timer']=timer_state
                    (self.root/'services.json').write_text(json.dumps(services))
                    self.write('/etc/x-ui/marker','unchanged')
                    (self.root/'commands').write_text('')
                    args=('backup',) if operation=='backup' else ('restore',archive)
                    result=self.run_tool(*args)
                    self.assertNotEqual(result.returncode,0)
                    self.assertIn('retry after it finishes',result.stderr)
                    self.assertNotIn('completed successfully.',result.stdout)
                    self.assertEqual(self.path('/etc/x-ui/marker').read_text(),'unchanged')
                    calls=self.commands()
                    self.assertFalse(any(c[0]=='cp' for c in calls))
                    self.assertNotIn(['systemctl','stop','certbot.service'],calls)
                    state=json.loads((self.root/'services.json').read_text())
                    self.assertEqual(state['certbot.service'],running)
                    self.assertEqual(state['certbot.timer'],timer_state)
                    self.assertEqual(list(self.path('/var/backups/x-ui').glob('*.tar.gz')),[archive])

    def test_backup_failure_restores_timer_and_resume_failure_is_fatal(self):
        for failure in ({'FAIL_COPY':'1'},{'CORRUPT_ARCHIVE':'1'},{'FAIL_TIMER_OPERATION':'stop'},
                        {'FAIL_TIMER_OPERATION':'start'}):
            with self.subTest(failure=failure):
                services=json.loads((self.root/'services.json').read_text());services['certbot.timer']='active'
                (self.root/'services.json').write_text(json.dumps(services))
                (self.root/'commands').write_text('')
                result=self.run_tool('backup',**failure)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('Backup completed successfully.',result.stdout)
                self.assertIn(['systemctl','start','certbot.timer'],self.commands())
                if failure.get('FAIL_TIMER_OPERATION')!='start':
                    self.assertEqual(json.loads((self.root/'services.json').read_text())['certbot.timer'],'active')
                else:self.assertIn('Cannot restore certbot.timer',result.stderr)
                self.assertFalse(list(self.path('/var/backups/x-ui').glob('*.tar.gz')))

    def test_restore_pauses_certbot_before_replacement_and_validates_after_activation(self):
        archive=self.backup()
        (self.root/'commands').write_text('')
        result=self.run_tool('restore',archive)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        calls=self.commands()
        pause=calls.index(['systemctl','stop','certbot.timer'])
        idle=calls.index(['systemctl','is-active','certbot.service'])
        replacement=next(i for i,c in enumerate(calls) if c[0]=='cp' and c[-1]==str(self.path('/etc/letsencrypt/renewal/example.com.conf')))
        activation=calls.index(['systemctl','enable','--now','certbot.timer'])
        health=calls.index(['systemctl','is-enabled','--quiet','certbot.timer'],activation)
        self.assertLess(pause,idle);self.assertLess(idle,replacement)
        self.assertLess(replacement,activation);self.assertLess(activation,health)
        for failure in ({'FAIL_TIMER_OPERATION':'stop'},{'FAIL_PYTHON_IMPORT':'1'}):
            self.write('/etc/x-ui/marker','unchanged')
            (self.root/'commands').write_text('')
            result=self.run_tool('restore',archive,**failure)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('Restore completed successfully.',result.stdout)
            self.assertEqual(self.path('/etc/x-ui/marker').read_text(),'unchanged')
            self.assertFalse(any(c[0]=='cp' for c in self.commands()))

    def test_setcap_failure_is_best_effort_but_service_health_is_required(self):
        archive = self.backup()
        expected_calls = [['setcap', 'cap_net_raw+ep', str(self.bin / name)] for name in ('mtr', 'mtr-packet')]
        for binary in ('mtr', 'mtr-packet'):
            with self.subTest(binary=binary):
                (self.root / 'commands').write_text('')
                result = self.run_tool('restore', archive, FAIL_SETCAP=binary)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('Restore completed successfully.', result.stdout)
                self.assertIn(f'[WARN] Could not set CAP_NET_RAW file capability on {binary};', result.stderr)
                self.assertIn('systemd AmbientCapabilities', result.stderr)
                self.assertNotIn('[FAIL]', result.stdout + result.stderr)
                calls = self.commands()
                self.assertEqual([c for c in calls if c[0] == 'setcap'], expected_calls)
                health = calls.index(['systemctl', 'is-active', '--quiet', 'mtr-backend'])
                self.assertGreater(health, calls.index(['systemctl', 'start', 'mtr-backend']))

        result = self.run_tool('restore', archive, FAIL_SETCAP='mtr mtr-packet', FAIL_HEALTH_SERVICE='mtr-backend')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[FAIL] mtr-backend is not active', result.stderr)
        self.assertNotIn('Restore completed successfully.', result.stdout)

    def test_rollback_preserves_stopped_invalid_nginx_and_active_failure_is_unverified(self):
        self.assertTrue(os.environ.get('NGINX_BIN'),'Real nginx is required for this rollback regression')
        for active in ('inactive','active'):
            with self.subTest(original=active):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups)
                archive=f.backup();before=archive.read_bytes()
                states=json.loads((f.root/'services.json').read_text());states['nginx']=active
                (f.root/'services.json').write_text(json.dumps(states))
                f.write('/etc/nginx/nginx.conf','invalid old nginx;\n')
                result=f.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1')
                self.assertNotEqual(result.returncode,0)
                self.assertTrue((f.root/'fault-used').exists(),'post-mutation health fault reached')
                self.assertEqual(f.path('/etc/nginx/nginx.conf').read_text(),'invalid old nginx;\n')
                self.assertEqual(archive.read_bytes(),before)
                self.assertNotIn('Restore completed successfully',result.stdout)
                if active=='inactive':
                    self.assertEqual(json.loads((f.root/'services.json').read_text())['nginx'],'inactive')
                    self.assertNotIn(['systemctl','start','nginx'],f.commands())
                    self.assertIn('Previous managed state/service states restored and checked',result.stderr)
                    self.assertFalse(list(f.path('/var/backups/x-ui').glob('.rollback-*')))
                else:
                    self.assertIn('Automatic rollback could not be verified',result.stderr)
                    self.assertTrue(list(f.path('/var/backups/x-ui').glob('.rollback-*')))

    def test_rollback_restores_ufw_rules_without_enabling_inactive_firewall(self):
        for state,failure in (('inactive',False),('active',False),('active',True)):
            with self.subTest(state=state,recovery_failure=failure):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups)
                archive=f.backup()
                for name in ('user.rules','user6.rules'):
                    f.write('/etc/ufw/'+name,'SSH administrator rule\ncustom administrator rule\n',0o640)
                original={name:(f.path('/etc/ufw/'+name).read_bytes(),f.path('/etc/ufw/'+name).stat()) for name in ('user.rules','user6.rules')}
                result=f.run_tool('restore',archive,SCOPED_EFFECTS='1',UFW_STATE=state,
                                  FAIL_UFW_RECOVERY='1' if failure else '',FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1')
                self.assertNotEqual(result.returncode,0)
                self.assertTrue((f.root/'fault-used').exists())
                self.assertIn(['ufw','allow','443/udp'],f.commands())
                for name,(data,metadata) in original.items():
                    path=f.path('/etc/ufw/'+name);self.assertEqual(path.read_bytes(),data)
                    self.assertEqual((path.stat().st_uid,path.stat().st_gid,stat.S_IMODE(path.stat().st_mode)),
                                     (metadata.st_uid,metadata.st_gid,stat.S_IMODE(metadata.st_mode)))
                self.assertFalse(any(c[0]=='ufw' and any(v in c for v in ('enable','disable','reset')) for c in f.commands()))
                if state=='active':self.assertIn(['ufw','reload'],f.commands())
                self.assertIn('Automatic rollback could not be verified' if failure else 'Previous managed state/service states restored and checked',result.stderr)
                self.assertEqual(bool(list(f.path('/var/backups/x-ui').glob('.rollback-*'))),failure)
                if failure:
                    recovery=next(f.path('/var/backups/x-ui').glob('.rollback-*'))
                    self.assertEqual(stat.S_IMODE(recovery.stat().st_mode),0o700)
                    self.assertEqual((recovery/'ufw/user.rules').read_bytes(),original['user.rules'][0])
                self.assertNotIn('Restore completed successfully',result.stdout)

    def test_rollback_restores_only_its_legacy_cron_edit_and_detects_conflict(self):
        for scenario in ('legacy','unrelated','absent','concurrent','write-failure'):
            with self.subTest(scenario=scenario):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups)
                archive=f.backup();cron=f.root/'crontab'
                if scenario=='absent':cron.unlink()
                else:cron.write_text('@hourly unrelated\n'+(CRON+'\n' if scenario in ('legacy','concurrent','write-failure') else ''))
                original=cron.read_bytes() if cron.exists() else None
                result=f.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1',CONCURRENT_CRON='1' if scenario=='concurrent' else '',
                                  FAIL_CRON_RECOVERY='1' if scenario=='write-failure' else '')
                self.assertNotEqual(result.returncode,0);self.assertTrue((f.root/'fault-used').exists())
                writes=[c for c in f.commands() if c==['crontab','-']]
                if scenario in ('concurrent','write-failure'):
                    self.assertEqual(cron.read_text(),'@hourly unrelated\n'+('@daily administrator-change\n' if scenario=='concurrent' else ''))
                    self.assertIn('Automatic rollback could not be verified',result.stderr)
                    self.assertTrue(list(f.path('/var/backups/x-ui').glob('.rollback-*')))
                else:
                    self.assertEqual(cron.read_bytes() if cron.exists() else None,original)
                    self.assertEqual(len(writes),2 if scenario=='legacy' else 0)
                    self.assertIn('Previous managed state/service states restored and checked',result.stderr)
                self.assertNotIn('Restore completed successfully',result.stdout)

    def test_rollback_restores_actual_sysctl_values_not_previous_file_values(self):
        for scenario in ('different','no-old-file','recovery-failure'):
            with self.subTest(scenario=scenario):
                f=PersonalBackup('runTest');f.setUp();self.addCleanup(f.doCleanups)
                archive=f.backup();file=f.path('/etc/sysctl.d/99-3x-ui-pro.conf')
                if scenario=='no-old-file':file.unlink()
                else:file.write_text('net.ipv4.tcp_sack=0\n')
                old=file.read_bytes() if file.exists() else None
                runtime={line.split('=',1)[0]:'7' for line in PARAMS};runtime['unrelated.value']='unchanged'
                (f.root/'runtime-sysctl.json').write_text(json.dumps(runtime))
                result=f.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1',
                                  FAIL_SYSCTL_RECOVERY='1' if scenario=='recovery-failure' else '')
                self.assertNotEqual(result.returncode,0);self.assertTrue((f.root/'fault-used').exists())
                self.assertEqual(file.read_bytes() if file.exists() else None,old)
                self.assertTrue(any(c[:2]==['sysctl','-p'] for c in f.commands()))
                if scenario!='recovery-failure':self.assertEqual(json.loads((f.root/'runtime-sysctl.json').read_text()),runtime)
                self.assertIn('Automatic rollback could not be verified' if scenario=='recovery-failure' else 'Previous managed state/service states restored and checked',result.stderr)
                self.assertEqual(bool(list(f.path('/var/backups/x-ui').glob('.rollback-*'))),scenario=='recovery-failure')
                if scenario=='recovery-failure':
                    recovery=next(f.path('/var/backups/x-ui').glob('.rollback-*'))
                    self.assertEqual(stat.S_IMODE(recovery.stat().st_mode),0o700)
                    self.assertIn('fs.file-max=7', (recovery/'sysctl.before').read_text())
                self.assertNotIn('Restore completed successfully',result.stdout)

    def test_rollback_restores_preexisting_acme_challenge_directory(self):
        archive=self.backup();before=archive.read_bytes()
        self.write('/var/www/acme/.well-known/acme-challenge/administrator-token','original challenge',0o640)
        self.write('/var/www/acme/foreign-resource','preserved')
        parents=[self.path('/var/www/acme'),self.path('/var/www/acme/.well-known')]
        for index,parent in enumerate(parents):
            os.chown(parent,12340+index,12350+index);parent.chmod(0o710+index)
        metadata=[(p.stat().st_uid,p.stat().st_gid,stat.S_IMODE(p.stat().st_mode)) for p in parents]
        directory=self.path('/var/www/acme/.well-known/acme-challenge');directory.chmod(0o710)
        result=self.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1')
        self.assertNotEqual(result.returncode,0);self.assertTrue((self.root/'fault-used').exists())
        self.assertIn('Previous managed state/service states restored and checked',result.stderr)
        self.assertEqual([(p.stat().st_uid,p.stat().st_gid,stat.S_IMODE(p.stat().st_mode)) for p in parents],metadata)
        self.assertEqual((directory/'administrator-token').read_text(),'original challenge')
        self.assertEqual(self.path('/var/www/acme/foreign-resource').read_text(),'preserved')
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode),0o710)
        self.assertEqual(stat.S_IMODE((directory/'administrator-token').stat().st_mode),0o640)
        self.assertEqual(archive.read_bytes(),before)
        with tarfile.open(archive) as tar:self.assertFalse(any('acme-challenge' in m.name for m in tar))
        self.assertIn('Previous managed state/service states restored and checked',result.stderr)
        self.assertNotIn('Restore completed successfully',result.stdout)

    def test_rollback_removes_only_empty_acme_parents_created_by_restore(self):
        archive=self.backup();before=archive.read_bytes()
        for path in ('/var/www/acme/.well-known/acme-challenge','/var/www/acme/.well-known','/var/www/acme'):
            self.path(path).rmdir()
        self.assertFalse(self.path('/var/www/acme').exists())
        result=self.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1')
        self.assertNotEqual(result.returncode,0);self.assertTrue((self.root/'fault-used').exists())
        self.assertIn('Previous managed state/service states restored and checked',result.stderr)
        self.assertFalse(self.path('/var/www/acme').exists())
        self.assertFalse(list(self.path('/var/backups/x-ui').glob('.rollback-*')))
        self.assertEqual(archive.read_bytes(),before)
        self.assertNotIn('Restore completed successfully',result.stdout)

    def test_rollback_preserves_independent_acme_file_and_reports_unverified(self):
        archive=self.backup()
        for path in ('/var/www/acme/.well-known/acme-challenge','/var/www/acme/.well-known','/var/www/acme'):
            self.path(path).rmdir()
        result=self.run_tool('restore',archive,FAIL_HEALTH_SERVICE='mtr-backend',FAIL_ONCE='1',CONCURRENT_ACME='1')
        self.assertNotEqual(result.returncode,0);self.assertTrue((self.root/'fault-used').exists())
        self.assertEqual(self.path('/var/www/acme/.well-known/independent-file').read_text(),'keep independent data')
        self.assertIn('Automatic rollback could not be verified',result.stderr)
        self.assertNotIn('Previous managed state/service states restored and checked',result.stderr)
        recovery=next(self.path('/var/backups/x-ui').glob('.rollback-*'))
        self.assertEqual(stat.S_IMODE(recovery.stat().st_mode),0o700)
        self.assertTrue((recovery/'ready').is_file())
        self.assertFalse(self.path('/var/www/acme/.well-known/acme-challenge').exists())
        self.assertNotIn('Restore completed successfully',result.stdout)

    def test_mandatory_health_and_sysctl_failures_never_report_success(self):
        for env in ({'FAIL_NGINX': '1'}, {'FAIL_HEALTH_SERVICE': 'mtr-backend'},
                    {'CORRUPT_RUNNING_DB': '1'}, {'FAIL_HEALTH_SERVICE': 'x-ui'}, {'FAIL_SYSCTL': '1'}):
            with self.subTest(failure=env):
                f = PersonalBackup('runTest'); f.setUp()
                self.addCleanup(f.doCleanups)
                archive = f.backup()
                f.write('/etc/x-ui/target-marker', 'previous target')
                initial_services = json.loads((f.root/'services.json').read_text())
                initial_enabled = json.loads((f.root/'enabled.json').read_text())
                (f.root / 'commands').write_text('')
                result = f.run_tool('restore', archive, FAIL_ONCE='1', **env)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Restore completed successfully.', result.stdout)
                if 'FAIL_NGINX' in env:
                    self.assertNotIn(['systemctl', 'start', 'nginx'], f.commands())

                calls = f.commands()
                self.assertEqual(f.path('/etc/x-ui/target-marker').read_text(), 'previous target')
                self.assertEqual(json.loads((f.root/'services.json').read_text()), initial_services)
                self.assertEqual({k for k,v in json.loads((f.root/'enabled.json').read_text()).items() if v},
                                 {k for k,v in initial_enabled.items() if v})
                self.assertFalse(list(f.path('/var/backups/x-ui').glob('.restore-*')))
                if 'FAIL_NGINX' in env:
                    self.assertTrue(any(c[0]=='nginx' and '-c' in c for c in calls), 'private nginx fault reached')
                    self.assertFalse(any(c[:2]==['systemctl','stop'] for c in calls))
                else:
                    self.assertIn(['systemctl','start','x-ui'], calls)
                    if 'FAIL_HEALTH_SERVICE' in env:
                        self.assertIn(['systemctl','is-active','--quiet',env['FAIL_HEALTH_SERVICE']], calls)
                    if 'CORRUPT_RUNNING_DB' in env:
                        self.assertIn(['fault','running-db'], calls)
                    if 'MISSING_SOCKET' in env:
                        self.assertIn(['fault','missing-socket'], calls)
                    if 'FAIL_SYSCTL' in env:
                        self.assertTrue(any(c[0]=='sysctl' for c in calls))
                    self.assertIn('Previous managed state/service states restored and checked', result.stderr)
                    self.assertFalse(list(f.path('/var/backups/x-ui').glob('.rollback-*')))
                    with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                        self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')


from test_adguard_backup import AdGuardBackup

from test_audit_findings import AuditRecovery


if __name__ == '__main__':
    unittest.main(verbosity=2)
