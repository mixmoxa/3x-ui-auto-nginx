"""Installed-stack, Backup UI and actual subscription consumer checks in the guest."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import stat
import struct
import subprocess
import tempfile
import time
import urllib.request
import uuid
import ssl

from diagnostics import probe_dns, validate_dns

ROOT = Path('/root/pilot')
os.umask(0o077)

def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=45)


def restore_content():
    """Private content digests, never credentials or database rows in reports."""
    import hashlib
    with sqlite3.connect('/etc/x-ui/x-ui.db') as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        content = {name: db.execute('SELECT * FROM '+name+' ORDER BY rowid').fetchall()
                   for name in ('settings','inbounds','users','clients') if name in tables}
    result = {'sqlite': hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()}
    for name in ('/etc/x-ui/pr2-persist', '/root/cert/panel.example.test/fullchain.pem',
                 '/root/cert/panel.example.test/privkey.pem'):
        result[name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
    return result


def restore_source():
    Path('/etc/x-ui/pr2-persist').write_text('PR2-lite persistent data\n')
    result = subprocess.run(['bash','/usr/local/bin/x-ui-backup','backup','--json'],
                            capture_output=True, timeout=150)
    (ROOT/'source-backup.private.log').write_bytes(result.stderr)
    assert result.returncode == 0
    archive = json.loads(result.stdout)['archive']
    assert json.loads(run('bash','/usr/local/bin/x-ui-backup','inspect',archive))['format_version'] == 3
    (ROOT/'restore-archive-path').write_text(archive)
    (ROOT/'restore-expected.json').write_text(json.dumps(restore_content()))
    return {'real_backup_v3':True, 'minimal_source':True}


def restore_target():
    assert not Path('/usr/local/x-ui').exists() and not Path('/etc/x-ui').exists()
    fixture = Path('/etc/letsencrypt/cli.ini')
    assert fixture.read_text() == 'server = https://10.0.2.2:14000/dir\n'
    fixture.unlink()
    env = {**os.environ, **json.loads((ROOT/'environment.json').read_text()),
           'CURL_CA_BUNDLE':'/etc/ssl/certs/ca-certificates.crt'}
    subprocess.run(['update-ca-certificates'], check=True, capture_output=True, timeout=120)
    # Real socket activation, including a nonstandard port, with both forwarded
    # SSH endpoints checked by the host after UFW and after a fresh QEMU boot.
    drop = Path('/etc/systemd/system/ssh.socket.d/90-pilot.conf'); drop.parent.mkdir(exist_ok=True)
    drop.write_text('[Socket]\nListenStream=\nListenStream=0.0.0.0:22\nListenStream=0.0.0.0:2222\n')
    run('systemctl','daemon-reload')
    run('systemctl','stop','ssh.service','ssh.socket')
    run('systemctl','enable','--now','ssh.socket')
    # Stopping ssh.service removes its RuntimeDirectory. Start the standard
    # socket-backed daemon before validating sshd, even in this retained session.
    run('systemctl','start','ssh.service')
    assert Path('/run/sshd').is_dir()
    log = ROOT/'restore-security.private.log'
    # Retain private progress even if Restore/Security exceeds its deadline.
    with log.open('wb', buffering=0) as output:
        try:
            result = subprocess.run(['bash','-c','source "$1"; backup_action restore','fixture',str(ROOT/'x-ui-latest.sh')],
                                    input=b'/root/pilot/restore.tar.gz\ny\ny\nYES\n', stdout=output,
                                    stderr=subprocess.STDOUT, env=env, timeout=1500)
        finally:
            os.fsync(output.fileno())
    text = log.read_text(errors='replace')
    if result.returncode:
        # Only the helper's fixed statuses/sanitized warnings cross the failure
        # boundary; never publish the installer/Restore log or database contents.
        for line in text.splitlines():
            if line.startswith(('Restore:', 'APT:', 'Fail2ban:', 'UFW:', 'Security:', 'Overall:', 'Security warning:')):
                print(line, flush=True)
    assert result.returncode == 0, 'Restore/Security failed; private log retained'
    for line in ('Restore: SUCCESS','APT: CONFIGURED','Fail2ban: CONFIGURED','UFW: CONFIGURED','Overall: SUCCESS'):
        assert line in text
    assert restore_content() == json.loads((ROOT/'restore-expected.json').read_text())
    (ROOT/'restore-boot-id').write_text(Path('/proc/sys/kernel/random/boot_id').read_text())
    return {'clean_target_restore':True, 'security_without_dot':True, 'socket_and_nonstandard_ssh':True,
            'restored_content_preserved':True}


def restore_verified(cold=False):
    assert restore_content() == json.loads((ROOT/'restore-expected.json').read_text())
    for service in ('x-ui','nginx','mtr-backend','certbot.timer','fail2ban','apt-daily.timer','apt-daily-upgrade.timer'):
        run('systemctl','is-active','--quiet',service)
    assert run('ufw','status').startswith('Status: active')
    assert not Path('/etc/systemd/resolved.conf.d/90-3x-ui-auto-nginx.conf').exists()
    security = load('current-security')
    security.verify_fail2ban([22,2222])
    security.verify_apt('ubuntu', set())
    before = {str(p):p.read_bytes() for p in Path('/etc/ufw').rglob('*') if p.is_file()}
    assert json.loads(run('/usr/bin/python3','-I',str(ROOT/'current-security.py'),'--enable-ufw'))['status'] == 'preserved'
    assert before == {str(p):p.read_bytes() for p in Path('/etc/ufw').rglob('*') if p.is_file()}
    if cold:
        assert Path('/proc/sys/kernel/random/boot_id').read_text() != (ROOT/'restore-boot-id').read_text()
    return {'services_active':True, 'ufw_active':True, 'restored_content_preserved':True, 'boot_verified':True}

def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def adguard_state(rewrite=None):
    """Private API assertions; never publish AGH credentials or configuration."""
    metadata=json.loads(Path('/opt/AdGuardHome/managed.json').read_text())
    log=re.sub(r'\x1b\[[0-9;]*m','',(ROOT/'installer.raw.log').read_text())
    password=re.search(r'Login: admin\n Password: (\S+)',log)[1]
    headers={'Authorization':'Basic '+base64.b64encode(('admin:'+password).encode()).decode(),
             'Content-Type':'application/json'}
    def request(path,body=None):
        req=urllib.request.Request(f'http://127.0.0.1:{metadata["web_port"]}/control/'+path,
            data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=10) as response:data=response.read()
        return json.loads(data) if data else None
    if rewrite is not None:request('rewrite/add',rewrite)
    dns=request('dns_info')
    return {'upstreams':{k:dns[k] for k in ('upstream_dns','bootstrap_dns','fallback_dns','upstream_mode') if k in dns},
            'rewrites':request('rewrite/list')}

def installed(cold=False):
    root=ROOT; checks={}
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-','')
    if cold:
        assert boot!=(root/'first-boot-id').read_text().strip()
        checks['new_boot_id']=True
    units=('ssh','nginx','x-ui','mtr-backend','AdGuardHome','fail2ban','apt-daily.timer','apt-daily-upgrade.timer','certbot.timer','systemd-resolved')
    deadline=time.monotonic()+90
    while True:
        missing=[u for u in units if subprocess.run(['systemctl','is-active','--quiet',u],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode]
        if not missing:break
        if time.monotonic()>deadline:raise AssertionError('Native boot readiness deadline: '+','.join(missing))
        time.sleep(0.5)
    for unit in units:run('systemctl','is-enabled','--quiet',unit)
    checks['services_enabled_active']=True
    if cold:
        fixture=int(run('systemctl','show','pilot-external-network','-p','ActiveEnterTimestampMonotonic','--value'))
        agh=int(run('systemctl','show','AdGuardHome','-p','ActiveEnterTimestampMonotonic','--value'))
        assert 0<fixture<agh,'External DNS fixture must be ready before AGH starts'
        checks['test_DNS_fixture_ready_before_AGH']=True
    run('/usr/sbin/sshd','-t');checks['ssh_configuration']=True
    baseline=json.loads((root/'baseline.json').read_text())
    xui_version=re.search(r'[0-9]+\.[0-9]+\.[0-9]+',run('/usr/local/x-ui/x-ui','-v'))[0]
    xray_version=re.search(r'[0-9]+\.[0-9]+\.[0-9]+',run('/usr/local/x-ui/bin/xray-linux-amd64','version'))[0]
    assert xui_version==baseline['version'][1:] and xray_version==baseline['xray']
    checks['installed_verified_baseline']=True
    run('nginx','-t');checks['nginx_syntax']=True
    assert run('busctl','get-property','org.freedesktop.resolve1','/org/freedesktop/resolve1','org.freedesktop.resolve1.Manager','DNSOverTLS').strip()=='s "yes"'
    assert 'tech0.ru' in run('resolvectl','domain')
    run('resolvectl','query','--cache=no','cloudflare.com');run('getent','ahosts','debian.org');checks['native_DNS_DoT_search_domain']=True
    deadline=time.monotonic()+45
    while True:
        try:
            xui=int(run('systemctl','show','x-ui','-p','MainPID','--value'))
            children=[int(value) for value in run('pgrep','-P',str(xui)).split()]
            xray=[pid for pid in children if Path(f'/proc/{pid}/exe').readlink().name.startswith('xray-linux-')]
            assert len(xray)==1
            listing=run('ss','-H','-lntup')
            for protocol,port,pid in (('tcp',8443,xray[0]),('udp',443,xray[0]),('udp',8443,xui)):
                assert any(line.startswith(protocol+' ') and line.split()[4].rsplit(':',1)[-1]==str(port) and f'pid={pid},' in line for line in listing.splitlines())
            assert stat.S_ISSOCK(Path('/dev/shm/uds2023.sock').stat().st_mode)
            unix=run('ss','-H','-lxnp')
            assert any('/dev/shm/uds2023.sock' in line.split() and f'pid={xray[0]},' in line
                       for line in unix.splitlines())
            agh=int(run('systemctl','show','AdGuardHome','-p','MainPID','--value'))
            metadata=json.loads(Path('/opt/AdGuardHome/managed.json').read_text())
            for protocol,port in (('tcp',metadata['web_port']),('udp',metadata['dns_port'])):
                assert any(line.startswith(protocol+' ') and line.split()[4]==f'127.0.0.1:{port}'
                           and f'pid={agh},' in line for line in listing.splitlines())
            break
        except (AssertionError, OSError, subprocess.CalledProcessError):
            if time.monotonic()>=deadline:raise AssertionError('Installed Xray/AWG listener readiness deadline')
            time.sleep(.1)
    checks['Xray_and_AWG_listeners']=True
    for domain in ('panel.example.test','reality.example.test','vision.example.test'):
        cert=Path('/etc/letsencrypt/live')/domain/'fullchain.pem';key=cert.with_name('privkey.pem')
        run('openssl','x509','-in',str(cert),'-noout','-checkend','0')
        assert 'does match certificate' in run('openssl','x509','-in',str(cert),'-noout','-checkhost',domain)
        assert run('openssl','x509','-in',str(cert),'-noout','-pubkey')==run('openssl','pkey','-in',str(key),'-pubout')
    checks['three_certificate_lineages']=True
    log=re.sub(r'\x1b\[[0-9;]*m','',(root/'installer.raw.log').read_text())
    username=re.search(r'^ Username: (\S+)$',log,re.M)[1];password=re.search(r'^ Password: (\S+)$',log,re.M)[1]
    with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True) as db:
        settings=dict(db.execute('SELECT key,value FROM settings'))
    with tempfile.TemporaryDirectory(prefix='cold-session-') as directory:
        panel=load('session').Panel('https://panel.example.test'+settings['webBasePath'],username,password,directory,['--resolve','panel.example.test:443:127.0.0.1'])
        client=load('client');rows=client.active_inbounds(panel)
        identity=json.loads(Path('/etc/x-ui/initial-client.json').read_text())['identity']
        client.validate_credentials(rows,identity['email'])
        client.subscription(panel,identity['subId'],rows,identity['email'])
    checks['panel_login_and_real_RAW_JSON_subscription']=True
    metadata=json.loads(Path('/opt/AdGuardHome/managed.json').read_text())
    ident=os.urandom(2);name='cold-'+os.urandom(6).hex()+'.example.com'
    question=b''.join(bytes([len(label)])+label.encode() for label in name.split('.'))+b'\0'+struct.pack('!HH',1,1)
    packet=ident+struct.pack('!5H',0x100,1,0,0,0)+question
    def publish_dns(metrics):
        with (root/'dns-diagnostics.jsonl').open('a') as output:
            output.write(json.dumps(metrics)+'\n')
    def native_query():
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as dns:
            dns.settimeout(10);dns.sendto(packet,('127.0.0.1',metadata['dns_port']))
            return dns.recv(4096)
    probe_dns('native_udp', ident, native_query, publish_dns)
    context=ssl.create_default_context()
    for method in ('GET','POST'):
        def doh_query():
            url='https://panel.example.test/dns-query'
            if method=='GET':url+='?dns='+base64.urlsafe_b64encode(packet).decode().rstrip('=')
            request=urllib.request.Request(url,data=packet if method=='POST' else None,headers={'Content-Type':'application/dns-message'})
            with urllib.request.urlopen(request,context=context,timeout=15) as response:
                assert response.status==200 and response.headers['Content-Type'].startswith('application/dns-message')
                return response.read()
        probe_dns('doh_'+method.lower(), ident, doh_query, publish_dns)
    checks['AGH_native_DNS_and_HTTPS_DoH_GET_POST']=True
    baseline=root/'backup-adguard.private.json'
    if baseline.exists():
        saved=json.loads(baseline.read_text())
        assert adguard_state()==saved,'AGH upstream/rewrite settings changed after Backup or reboot'
        rewrite=next(r for r in saved['rewrites'] if r['domain'].startswith('backup-persist-'))
        question=b''.join(bytes([len(label)])+label.encode() for label in rewrite['domain'].split('.'))+b'\0'+struct.pack('!HH',1,1)
        packet=ident+struct.pack('!5H',0x100,1,0,0,0)+question
        validate_dns(native_query(),ident,'native_udp',0)
        checks['AGH_Backup_upstreams_and_rewrite_persisted']=True
    run('fail2ban-client','status','sshd')
    for unit in ('apt-daily.timer','apt-daily-upgrade.timer'):run('systemctl','is-active','--quiet',unit)
    checks['fail2ban_APT_timers']=True
    from install import mtr_api
    mtr_api();checks['restricted_mtr_http']=True
    assert Path('/usr/local/bin/x-ui-backup').is_file();checks['backup_tool_present']=True
    return checks

def transports(vision=True, panel_domain='panel.example.test', positive_only=False):
    root=ROOT; results={}
    binary=next(Path("/usr/local/x-ui/bin").glob("xray-linux-amd64"))
    rule=["iptables","-t","nat","-A","OUTPUT","-d","8.8.8.9","-p","tcp","--dport","18081","-j","DNAT","--to-destination","10.0.2.2:18081"]
    subprocess.run(rule,check=True,timeout=10)
    try:
        log=re.sub(r'\x1b\[[0-9;]*m','',(root/'installer.raw.log').read_text())
        username=re.search(r'^ Username: (\S+)$',log,re.M)[1];password=re.search(r'^ Password: (\S+)$',log,re.M)[1]
        with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True) as db:settings=dict(db.execute('SELECT key,value FROM settings'))
        with tempfile.TemporaryDirectory(prefix='installed-consumer-') as directory:
            directory=Path(directory)
            panel=load('session').Panel('https://'+panel_domain+settings['webBasePath'],username,password,directory,['--resolve',panel_domain+':443:127.0.0.1'])
            client=load('client');identity=json.loads(Path('/etc/x-ui/initial-client.json').read_text())['identity']
            public=panel.request('panel/api/setting/defaultSettings',{})['obj']
            configs=json.loads(client.fetch(panel,public['subJsonURI']+identity['subId']))
            selected={}
            for config in configs:
                out=next(o for o in config['outbounds'] if o['protocol'] in ('vless','hysteria'))
                stream=out['streamSettings']
                name='REALITY' if stream['security']=='reality' else 'XHTTP' if stream['network']=='xhttp' else 'Hysteria2' if out['protocol']=='hysteria' else 'Vision'
                assert name not in selected;selected[name]=config
            assert set(selected)==({'REALITY','XHTTP','Hysteria2','Vision'} if vision else {'REALITY','XHTTP','Hysteria2'})
            for name,original in selected.items():
                for variant in (('positive',) if positive_only else ('positive','credentials') if name=='REALITY' else ('positive','credentials','untrusted-ca','wrong-sni')):
                    negative=variant!='positive'
                    config=json.loads(json.dumps(original));out=next(o for o in config['outbounds'] if o['protocol'] in ('vless','hysteria'));stream=out['streamSettings']
                    if name!='REALITY':
                        tls=stream['tlsSettings']
                        assert tls.get('allowInsecure',False) is False
                        tls['allowInsecure']=False
                        destination=out['settings']
                        destination=destination['vnext'][0] if 'vnext' in destination else destination['servers'][0] if 'servers' in destination else destination
                        expected_sni='vision.example.test' if name=='Vision' else panel_domain
                        assert (tls.get('serverName') or destination['address'])==expected_sni
                        tls['serverName']=expected_sni
                        ca=Path('/usr/local/share/ca-certificates/pilot-pebble.crt')
                        assert ca.is_file()
                        tls['certificates']=[{'certificateFile':str(ca),'usage':'verify'}]
                        if variant=='untrusted-ca':tls['certificates']=[{'certificateFile':'/root/pilot/fixture.crt','usage':'verify'}]
                        if variant=='wrong-sni':tls['serverName']='wrong.example.test'
                    if variant=='credentials':
                        if name=='REALITY':
                            assert stream['realitySettings']['shortId']!='0011223344556677'
                            stream['realitySettings']['shortId']='0011223344556677'
                        elif name=='Hysteria2':stream['hysteriaSettings']['auth']='invalid-fresh-acceptance-auth'
                        else:
                            dest=out['settings'];dest=dest['vnext'][0] if 'vnext' in dest else dest['servers'][0] if 'servers' in dest else dest
                            user=dest['users'][0] if 'users' in dest else dest;user['id']=str(uuid.uuid4())
                    with socket.socket() as probe:probe.bind(('127.0.0.1',0));socks=probe.getsockname()[1]
                    config['inbounds']=[{'listen':'127.0.0.1','port':socks,'protocol':'socks','settings':{'auth':'noauth'}}]
                    path=directory/(name+'-'+variant+'.json');path.write_text(json.dumps(config))
                    subprocess.run([binary,'run','-test','-c',path],check=True,capture_output=True,timeout=30)
                    with (directory/(path.stem+'.log')).open('wb') as output:
                        process=subprocess.Popen([binary,'run','-c',path],stdout=output,stderr=subprocess.STDOUT)
                        try:
                            deadline=time.monotonic()+15
                            while True:
                                assert process.poll() is None,'Xray consumer exited before SOCKS readiness'
                                try:
                                    with socket.create_connection(('127.0.0.1',socks),timeout=0.3):break
                                except OSError:
                                    if time.monotonic()>deadline:raise AssertionError('Xray consumer SOCKS readiness deadline')
                                    time.sleep(0.05)
                            request_path='/'+name+'/'+os.urandom(8).hex();expected=('FRESH-INSTALL-'+request_path).encode()
                            response=subprocess.run(['curl','-q','-fsS','--proxy',f'socks5h://127.0.0.1:{socks}','--noproxy','','--connect-timeout','5','--max-time','8' if negative else '30','http://8.8.8.9:18081'+request_path],capture_output=True,timeout=40)
                            mismatch=(response.returncode==0 or expected in response.stdout) if negative else (response.returncode!=0 or response.stdout!=expected)
                            if mismatch:
                                import shutil
                                evidence=root/'transport-first-failure';evidence.mkdir(mode=0o700,exist_ok=True)
                                (evidence/'expected.bin').write_bytes(expected);(evidence/'received.bin').write_bytes(response.stdout)
                                (evidence/'curl-stderr.private.txt').write_bytes(response.stderr)
                                shutil.copy2(path,evidence/'client.private.json');shutil.copy2(directory/(path.stem+'.log'),evidence/'xray-client.private.log')
                            if negative:assert response.returncode!=0 and expected not in response.stdout,'Wrong transport credentials carried origin traffic'
                            else:assert response.returncode==0 and response.stdout==expected,'Installed transport failed byte-exact origin response'
                            results[name+'_'+variant]=True
                        finally:
                            if process.poll() is None:
                                process.terminate()
                                try:process.wait(timeout=5)
                                except subprocess.TimeoutExpired:process.kill();process.wait()
    except Exception as error:
        (root/'transport-error.private.txt').write_text(type(error).__name__+': '+str(error))
        raise
    finally:
        delete=rule.copy();delete[3]='-D';subprocess.run(delete,check=True)
        (root/'transport-result.json').write_text(json.dumps(results))
    return results

def amneziawg():
    root=ROOT; results={}
    with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro', uri=True) as source:
        rows = source.execute("SELECT port,settings FROM inbounds WHERE protocol='amneziawg' AND enable=1").fetchall()
        assert len(rows) == 1 and rows[0][0] == 8443
        settings = json.loads(rows[0][1])
        assert len(settings['clients']) == 1
        peer, server = settings['clients'][0], settings['server']
        with tempfile.TemporaryDirectory(prefix='installed-awg-consumer-') as temporary:
            temporary = Path(temporary)
            for name in ('db', 'bin', 'logs'):
                (temporary / name).mkdir(mode=0o700)
            target = temporary / 'db/x-ui.db'
            with sqlite3.connect(target) as db:
                source.backup(db)
                db.execute('DELETE FROM inbounds')
                # Only private client state changes; the installed server is untouched.
                obfuscation = {k:v for k,v in server.items() if k not in
                    ('privateKey','publicKey','subnetIp','subnetCidr','primaryDns','secondaryDns')}
                outbound = {**obfuscation, 'secretKey':peer['privateKey'], 'address':peer['allowedIPs'],
                    'peers':[{'publicKey':server['publicKey'],'allowedIPs':['0.0.0.0/0'],
                              'endpoint':'127.0.0.1:8443'}]}
                allocated = set()
                def port():
                    for _ in range(100):
                        with socket.socket() as probe:
                            probe.bind(('127.0.0.1',0))
                            value = probe.getsockname()[1]
                        if value not in allocated:
                            allocated.add(value)
                            return value
                    raise RuntimeError('No distinct client port available')
                socks, panel, sub = port(), port(), port()
                template = {'log':{'loglevel':'warning'}, 'inbounds':[
                    {'listen':'127.0.0.1','port':socks,'protocol':'socks',
                     'settings':{'auth':'noauth','udp':True}}], 'outbounds':[
                    {'tag':'installed-awg','protocol':'amneziawg','settings':outbound}]}
                for key,value in {'webListen':'127.0.0.1','webPort':str(panel),
                                  'subPort':str(sub),'subEnable':'false',
                                  'xrayTemplateConfig':json.dumps(template)}.items():
                    db.execute('DELETE FROM settings WHERE key=?',(key,))
                    db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(key,value))
            binary = next(Path('/usr/local/x-ui/bin').glob('xray-linux-amd64'))
            shutil.copy2(binary, temporary / 'bin' / binary.name)
            rule = ['iptables','-t','nat','-A','OUTPUT','-d','8.8.8.9','-p','tcp',
                    '--dport','18081','-j','DNAT','--to-destination','10.0.2.2:18081']
            subprocess.run(rule,check=True,timeout=10)
            try:
                with (temporary/'client.private.log').open('wb') as log:
                    process = subprocess.Popen(['/usr/local/x-ui/x-ui'], stdout=log,stderr=log,
                        start_new_session=True, env={**os.environ,
                            'XUI_DB_FOLDER':str(temporary/'db'),'XUI_BIN_FOLDER':str(temporary/'bin'),
                            'XUI_LOG_FOLDER':str(temporary/'logs')})
                    try:
                        deadline = time.monotonic()+20
                        while True:
                            assert process.poll() is None, 'AWG consumer exited before readiness'
                            try:
                                with socket.create_connection(('127.0.0.1',socks),timeout=.3):
                                    break
                            except OSError:
                                if time.monotonic() >= deadline:
                                    raise AssertionError('AWG consumer SOCKS readiness deadline')
                                time.sleep(.05)
                        nonce = '/AWG/'+os.urandom(8).hex()
                        response = subprocess.run(['curl','-q','-fsS','--noproxy','',
                            '--proxy',f'socks5h://127.0.0.1:{socks}','--max-time','30',
                            'http://8.8.8.9:18081'+nonce],capture_output=True,timeout=40)
                        assert response.returncode == 0 and response.stdout == ('FRESH-INSTALL-'+nonce).encode(), \
                            'Installed AWG did not transfer byte-exact origin response'
                        results['AWG_payload'] = True
                    finally:
                        try: os.killpg(process.pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: pass
                        try: os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                        process.wait(timeout=5)
            finally:
                rule[3]='-D'
                subprocess.run(rule,check=True,timeout=10)
    return results

def search_domain_regression():
    assert 'tech0.ru' in run('resolvectl','domain')
    try:
        load('old-security').verify_dns()
    except ValueError as error:
        assert str(error)=='Interface/VPN DNS route overrides global DoT; preserved'
    else:
        raise AssertionError('Old tech0.ru failure did not reproduce')
    load('current-security').verify_dns()
    return {'tech0_old_RED':True,'tech0_current_GREEN':True}


def renewal():
    certificates = [Path('/etc/letsencrypt/live')/domain/'fullchain.pem' for domain in
                    ('panel.example.test','reality.example.test','vision.example.test')]
    before = [run('openssl','x509','-in',str(cert),'-noout','-serial') for cert in certificates]
    result = subprocess.run(['certbot','renew','--force-renewal','--non-interactive','--no-random-sleep-on-renew',
        '--server','https://10.0.2.2:14000/dir'], capture_output=True,timeout=180)
    (ROOT/'renewal.private.log').write_bytes(result.stdout+result.stderr)
    assert result.returncode == 0, 'Installed Certbot renewal/deploy hooks failed'
    after = [run('openssl','x509','-in',str(cert),'-noout','-serial') for cert in certificates]
    assert all(a != b for a,b in zip(before,after)), 'Renewal did not replace every managed certificate'
    return {'three_real_renewals':True, **installed()}


def manager_backup():
    """Actual Bash menu on a TTY, actual installed Backup, private raw output."""
    import pty, select
    state=json.loads(Path('/etc/x-ui/auto-nginx-managed.json').read_text())
    assert state['format']==1 and re.fullmatch('[0-9a-f]{40}',state['source_ref'])
    assert state['features']==dict(adguard=True,vision=True,amneziawg=True)
    assert set(state['inbound_roles'])=={'reality','ws','xhttp','grpc','hysteria2','vision','amneziawg'}
    agh=adguard_state({'domain':'backup-persist-'+os.urandom(6).hex()+'.example.test','answer':'203.0.113.7'})
    (ROOT/'backup-adguard.private.json').write_text(json.dumps(agh))
    before={unit:run('systemctl','is-active',unit) for unit in ('x-ui','nginx','AdGuardHome','certbot.timer')}
    existing=set(Path('/var/backups/x-ui').glob('*.tar.gz'))
    master,slave=pty.openpty()
    proc=subprocess.Popen(['bash',str(ROOT/'x-ui-latest.sh')],stdin=slave,stdout=slave,stderr=slave,
                          env={**os.environ,'TERM':'dumb','NO_COLOR':'1'})
    os.close(slave); output=bytearray();deadline=time.monotonic()+120
    os.write(master,b'1\n3\n1\n2\n0\n0\n')
    try:
        while time.monotonic()<deadline:
            if select.select([master],[],[],.2)[0]:
                try:part=os.read(master,65536)
                except OSError:break
                if not part:break
                output.extend(part)
            if proc.poll() is not None:break
        proc.wait(timeout=2)
        assert proc.returncode==0,'Backup menu failed (private output retained in guest)'
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
        os.close(master)
        (ROOT/'manager-backup.private.log').write_bytes(output)
    text=output.decode(errors='replace')
    assert text.count('BACKUPS')>=2 and 'FAILED' not in text
    created=set(Path('/var/backups/x-ui').glob('*.tar.gz'))-existing
    assert len(created)==1
    archive=next(iter(created));assert archive.is_file() and archive.stat().st_mode&0o777==0o600
    assert 'BACKUP CREATED' in text and archive.name in text and re.search(r'(KiB|MiB|GiB)',text)
    assert text.count('1. Installation')==2, 'Create/list escaped their Backup submenu'
    inspected=json.loads(run('bash','/usr/local/bin/x-ui-backup','inspect',str(archive)))
    assert inspected['format_version']==3 and inspected['adguard_home'] is True
    for unit,value in before.items():assert run('systemctl','is-active',unit)==value
    assert adguard_state()==agh,'Backup changed AGH upstream/rewrite settings'
    # The next consumer phase verifies that the resumed official Xray still transfers data.
    return {'actual_menu_backup_and_list':True,'service_states_preserved':True,'managed_state':True,
            'AGH_upstreams_and_nonempty_rewrite_preserved':True}


def change_domains():
    """Same installed VM: actual menu, Backup, Pebble, SQL and real consumers."""
    import hashlib, pty, select
    env={**os.environ,**json.loads((ROOT/'environment.json').read_text()),'TERM':'dumb','NO_COLOR':'1'}
    protected=('/etc/nginx/sites-available/vision.conf','/etc/nginx/sites-available/vision-acme.conf',
               '/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision',
               '/etc/letsencrypt/live/vision.example.test/fullchain.pem','/etc/letsencrypt/live/vision.example.test/privkey.pem',
               '/etc/letsencrypt/live/panel.example.test/fullchain.pem','/etc/letsencrypt/live/panel.example.test/privkey.pem',
               '/etc/letsencrypt/live/reality.example.test/fullchain.pem','/etc/letsencrypt/live/reality.example.test/privkey.pem',
               '/etc/ssh/sshd_config','/etc/ufw/user.rules','/etc/ufw/user6.rules','/etc/x-ui/initial-client.json',
               '/usr/local/x-ui/x-ui','/usr/bin/x-ui')
    def hashes():return {name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in protected}
    def database():
        with sqlite3.connect('file:/etc/x-ui/x-ui.db?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            return {table:[dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                    for table in ('users','clients','client_inbounds','inbounds','hosts','settings')}
    original_hashes=hashes();agh=adguard_state();before=database();result={}
    (ROOT/'before-domains-files.json').write_text(json.dumps(dict(files=original_hashes,adguard=agh)))
    panel,reality='panel.example.test','reality.example.test'
    for choice,new_panel,new_reality in (('1','panel-next.example.test',reality),
                                         ('2','panel-next.example.test','reality-next.example.test'),
                                         ('3','panel-final.example.test','reality-final.example.test')):
        marker=json.loads(Path('/etc/x-ui/auto-nginx-managed.json').read_text());roles=marker['inbound_roles']
        old_certificates={name:hashlib.sha256((Path('/etc/letsencrypt/live')/name/'fullchain.pem').read_bytes()).hexdigest() for name in (panel,reality)}
        original=set(Path('/var/backups/x-ui').glob('*.tar.gz'))
        master,slave=pty.openpty();output=bytearray()
        process=subprocess.Popen(['bash',str(ROOT/'x-ui-latest.sh')],stdin=slave,stdout=slave,stderr=slave,env=env)
        os.close(slave)
        language='1' if choice=='1' else '2'
        answers=language+'\n2\n'+choice+'\n'+(new_panel+'\n' if choice in ('1','3') else '')+(new_reality+'\n' if choice in ('2','3') else '')+'YES\n0\n'
        # Full Backup v3 alone is slow in TCG; include ACME and verified health.
        os.write(master,answers.encode());deadline=time.monotonic()+360
        try:
            while time.monotonic()<deadline:
                if select.select([master],[],[],.2)[0]:
                    try:part=os.read(master,65536)
                    except OSError:break
                    if not part:break
                    output.extend(part)
                if process.poll() is not None:break
            process.wait(timeout=2)
            assert process.returncode==0,'Change Domains failed; private output retained in guest'
        finally:
            if process.poll() is None:process.kill();process.wait()
            os.close(master);(ROOT/('domains-'+choice+'.private.log')).write_bytes(output)
        assert b'ROLLBACK_UNVERIFIED' not in output and b'SUCCESS: Panel=' in output
        created=set(Path('/var/backups/x-ui').glob('*.tar.gz'))-original
        assert len(created)==1 and json.loads(run('bash','/usr/local/bin/x-ui-backup','inspect',str(next(iter(created)))))['format_version']==3
        if choice=='1':(ROOT/'before-domains-archive').write_text(str(next(iter(created))))
        for name,value in old_certificates.items():assert hashlib.sha256((Path('/etc/letsencrypt/live')/name/'fullchain.pem').read_bytes()).hexdigest()==value
        after=database()
        for table in before:assert len(before[table])==len(after[table]),'SQLite row identities changed'
        for table in ('users','clients','client_inbounds'):assert before[table]==after[table],'Client/authentication identity changed'
        old_settings={r['key']:r['value'] for r in before['settings']};new_settings={r['key']:r['value'] for r in after['settings']}
        allowed={'webCertFile','webKeyFile','subCertFile','subKeyFile','subURI','subJsonURI','webDomain','subDomain'} if new_panel!=panel else set()
        for key,value in old_settings.items():
            if key not in allowed:assert new_settings[key]==value,'Unrelated panel setting changed'
        for previous,current in zip(before['hosts'],after['hosts']):
            for key in previous:
                if key=='address' and previous['inbound_id'] in [roles[n] for n in ('reality','ws','grpc','xhttp','hysteria2')]:
                    assert current[key]==new_panel
                else:assert previous[key]==current[key],'Host ID, metadata or v3.11 field changed'
        for previous,current in zip(before['inbounds'],after['inbounds']):
            for key in previous:
                if key in ('up','down'):
                    assert current[key]>=previous[key],'Traffic counters decreased'
                elif key=='stream_settings':
                    old_stream=json.loads(previous[key] or '{}');new_stream=json.loads(current[key] or '{}')
                    if previous['id']==roles['reality']:
                        assert new_stream['realitySettings']['serverNames']==[new_reality]
                        old_stream['realitySettings'].pop('serverNames');new_stream['realitySettings'].pop('serverNames')
                    elif previous['id']==roles['ws']:
                        assert new_stream['wsSettings']['host']==new_panel
                        old_stream['wsSettings'].pop('host');new_stream['wsSettings'].pop('host')
                    elif previous['id']==roles['grpc']:
                        assert new_stream['grpcSettings']['authority']==new_panel
                        old_stream['grpcSettings'].pop('authority');new_stream['grpcSettings'].pop('authority')
                    elif previous['id']==roles['hysteria2']:
                        assert new_stream['tlsSettings']['serverName']==new_panel
                        for item in new_stream['tlsSettings']['certificates']:
                            assert item['certificateFile']=='/root/cert/'+new_panel+'/fullchain.pem'
                            assert item['keyFile']=='/root/cert/'+new_panel+'/privkey.pem'
                        for stream in (old_stream,new_stream):
                            stream['tlsSettings'].pop('serverName')
                            for item in stream['tlsSettings']['certificates']:
                                item.pop('certificateFile');item.pop('keyFile')
                    assert old_stream==new_stream,'Unrelated transport or private key settings changed'
                elif key=='share_addr' and previous['id']==roles['amneziawg']:
                    assert current[key]==new_panel
                else:assert previous[key]==current[key],'Inbound identity/configuration changed'
        marker=json.loads(Path('/etc/x-ui/auto-nginx-managed.json').read_text())
        assert marker['domains']==dict(panel=new_panel,reality=new_reality,vision='vision.example.test')
        assert marker['inbound_roles']==roles and not Path('/var/lib/3x-ui-auto-nginx/change-domains/journal.json').exists()
        assert hashes()==original_hashes and adguard_state()==agh,'Vision, binaries, SSH/firewall or AGH state changed'
        assert json.loads(Path('/opt/AdGuardHome/managed.json').read_text())['domain']==new_panel
        transports(panel_domain=new_panel,positive_only=True)
        panel,reality=new_panel,new_reality;before=database();result['domains_'+choice]=True
    return {**result,'full_Backup_before_each_switch':True,'client_Host_Vision_AGH_preservation':True,
            'real_Pebble_and_native_services':True,'post_switch_real_consumers':True}


def restore_before_domains():
    """Restore the real pre-switch archive on the same installed, switched VM."""
    import hashlib,tarfile
    archive=Path((ROOT/'before-domains-archive').read_text())
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    source=ROOT/'before-domains-sqlite';source.mkdir(mode=0o700)
    with tarfile.open(archive) as saved:
        for suffix in ('','-wal','-shm'):
            try:member=saved.extractfile('files/etc/x-ui/x-ui.db'+suffix)
            except KeyError:
                assert suffix,'Archive SQLite is missing'
                continue
            assert member is not None
            target=source/('x-ui.db'+suffix);target.write_bytes(member.read());target.chmod(0o600)
        manifest=saved.extractfile('files/etc/x-ui/auto-nginx-managed.json').read()
    def database(path):
        with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            return {table:[dict(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                    for table in ('users','clients','client_inbounds','inbounds','hosts','settings','client_traffics') if table in names}
    expected=database(source/'x-ui.db')
    def mtr_packages():
        assert run('dpkg-query','-W','-f=${Status}','mtr-tiny')=='install ok installed'
        heavy=subprocess.run(['dpkg-query','-W','-f=${Status}','mtr'],capture_output=True,text=True)
        assert heavy.stdout!='install ok installed','Heavy mtr replaced mtr-tiny'
        assert all(shutil.which(name) for name in ('mtr','mtr-packet'))
    mtr_packages()
    env={**os.environ,**json.loads((ROOT/'environment.json').read_text())}
    log=ROOT/'restore-before-domains.private.log'
    with log.open('wb',buffering=0) as output:
        result=subprocess.run(['bash','-c','source "$1"; backup_action restore','fixture',str(ROOT/'x-ui-latest.sh')],
                              input=(str(archive)+'\nn\nn\nYES\n').encode(),stdout=output,stderr=subprocess.STDOUT,
                              env=env,timeout=480)
        os.fsync(output.fileno())
    assert result.returncode==0,'Pre-Change Domains Restore failed; private log retained'
    assert 'Restore: SUCCESS' in log.read_text() and 'Overall: SUCCESS' in log.read_text()
    actual=database('/etc/x-ui/x-ui.db')
    assert actual.keys()==expected.keys()
    for table,rows in expected.items():
        assert len(actual[table])==len(rows),'Restored row count changed: '+table
        for previous,current in zip(rows,actual[table]):
            for key,value in previous.items():
                if table in ('inbounds','client_traffics') and key in ('up','down'):
                    assert current[key]>=value,'Archived traffic counters decreased'
                else:assert current[key]==value,'Restored SQLite field changed: '+table+'.'+key
    assert Path('/etc/x-ui/auto-nginx-managed.json').read_bytes()==manifest
    evidence=json.loads((ROOT/'before-domains-files.json').read_text())
    assert all(hashlib.sha256(Path(name).read_bytes()).hexdigest()==value for name,value in evidence['files'].items())
    assert adguard_state()==evidence['adguard']
    assert json.loads(Path('/opt/AdGuardHome/managed.json').read_text())['domain']=='panel.example.test'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
    mtr_packages();installed();transports(positive_only=True);amneziawg()
    return dict(original_Backup_restored_after_Both=True,original_SQLite_clients_keys_Vision_AGH=True,
                native_services_and_consumers=True,mtr_tiny_preserved=True,source_archive_unchanged=True)
