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

def transports(vision=True):
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
            panel=load('session').Panel('https://panel.example.test'+settings['webBasePath'],username,password,directory,['--resolve','panel.example.test:443:127.0.0.1'])
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
                for variant in (('positive','credentials') if name=='REALITY' else ('positive','credentials','untrusted-ca','wrong-sni')):
                    negative=variant!='positive'
                    config=json.loads(json.dumps(original));out=next(o for o in config['outbounds'] if o['protocol'] in ('vless','hysteria'));stream=out['streamSettings']
                    if name!='REALITY':
                        tls=stream['tlsSettings']
                        assert tls.get('allowInsecure',False) is False
                        tls['allowInsecure']=False
                        destination=out['settings']
                        destination=destination['vnext'][0] if 'vnext' in destination else destination['servers'][0] if 'servers' in destination else destination
                        expected_sni='vision.example.test' if name=='Vision' else 'panel.example.test'
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
    import ast, pty, select
    state=json.loads(Path('/etc/x-ui/auto-nginx-managed.json').read_text())
    assert state['format']==1 and re.fullmatch('[0-9a-f]{40}',state['source_ref'])
    assert state['features']==dict(adguard=True,vision=True,amneziawg=True)
    assert set(state['inbound_roles'])=={'reality','ws','xhttp','grpc','hysteria2','vision','amneziawg'}
    agh=adguard_state({'domain':'backup-persist-'+os.urandom(6).hex()+'.example.test','answer':'203.0.113.7'})
    (ROOT/'backup-adguard.private.json').write_text(json.dumps(agh))
    before={unit:run('systemctl','is-active',unit) for unit in ('x-ui','nginx','AdGuardHome','certbot.timer')}
    master,slave=pty.openpty()
    proc=subprocess.Popen(['bash',str(ROOT/'x-ui-latest.sh')],stdin=slave,stdout=slave,stderr=slave,
                          env={**os.environ,'TERM':'dumb','NO_COLOR':'1'})
    os.close(slave); output=bytearray();deadline=time.monotonic()+120
    os.write(master,b'3\n1\n3\n2\n0\n')
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
    exact=ast.literal_eval(re.search(r'Created archive: ([^\r\n]+)',text)[1])
    archive=Path(exact);assert archive.is_file() and archive.stat().st_mode&0o777==0o600
    inspected=json.loads(run('bash','/usr/local/bin/x-ui-backup','inspect',str(archive)))
    assert inspected['format_version']==3 and inspected['adguard_home'] is True
    for unit,value in before.items():assert run('systemctl','is-active',unit)==value
    assert adguard_state()==agh,'Backup changed AGH upstream/rewrite settings'
    # The next consumer phase verifies that the resumed official Xray still transfers data.
    return {'actual_menu_backup_and_list':True,'service_states_preserved':True,'managed_state':True,
            'AGH_upstreams_and_nonempty_rewrite_preserved':True}
