"""Native systemd and authenticated DNS-over-TLS in an isolated disposable VM.

No Internet DoT dependency. Production resolver addresses exist only on container
loopback; their TLS servers use a generated test CA in this VM's trust store.
"""
import importlib.util
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit


def nightly_after_cold_boot():
    """Second real kernel/systemd boot; invoked by the existing QEMU harness."""
    run=lambda *a: subprocess.check_output(a,text=True,stderr=subprocess.STDOUT,timeout=90)
    run('modprobe','9pnet_virtio')
    Path('/mnt/xui-ci').mkdir(exist_ok=True)
    run('mount','-t','9p','-o','trans=virtio,version=9p2000.L','xui-ci','/mnt/xui-ci')
    assert Path('/proc/sys/kernel/random/boot_id').read_text()!=Path('/mnt/xui-ci/pre-boot-id').read_text()
    from test_integrated_features import helper
    security=helper('security'); dump=run('apt-config','dump')
    for value in ('Automatic-Reboot "true";', 'Automatic-Reboot-WithUsers "true";', 'Automatic-Reboot-Time "04:38";'):
        assert 'Unattended-Upgrade::'+value in dump, value
    for key in ('Enable','Update-Package-Lists','Unattended-Upgrade'):
        assert 'APT::Periodic::'+key+' "1";' in dump, key
    expected={tuple(v) for v in json.loads(Path('/mnt/xui-ci/expected-origins.json').read_text())}
    assert expected <= security.apt_origins(dump)
    for service,when in (('apt-daily.timer','02:30:00'),('apt-daily-upgrade.timer','02:50:00')):
        run('systemctl','is-active','--quiet',service); run('systemctl','is-enabled','--quiet',service)
        assert when in run('systemctl','show',service,'-p','TimersCalendar')
    print('REAL second boot: effective APT origins / reboot policy / enabled active local-time timers: PASS',flush=True)


class SecuritySystemd(unittest.TestCase):
    def test_verified_panel_native_sandbox_and_initial_configuration(self):
        if Path('/proc/1/comm').read_text().strip() != 'systemd':
            self.fail('Requires the existing disposable systemd VM')
        import stat
        import re
        from test_personal_xhttp import function, FIXTURE, SOURCE
        from test_integrated_features import helper
        from release_contract import baseline
        run=lambda *args: subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=90)
        certdir=Path('/root/cert/deploy.example'); certdir.mkdir(parents=True)
        cert,key=certdir/'fullchain.pem',certdir/'privkey.pem'
        run('openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1','-nodes','-days','1',
            '-subj','/CN=deploy.example','-addext','subjectAltName=DNS:deploy.example,IP:127.0.0.1',
            '-out',str(cert),'-keyout',str(key))
        Path('/etc/x-ui').mkdir(exist_ok=True); Path('/var/log/x-ui').mkdir(exist_ok=True)
        env={**os.environ,**FIXTURE,'PANEL_TAG':baseline()['version'],'PANEL_ARCHIVE':'/opt/xui-ci/panel.tar.gz',
             'XUIDB':'/etc/x-ui/x-ui.db','config_username':'integration','config_password':'temporary-fixture-password'}
        code='msg_ok() { :; }; msg_err() { echo "$*" >&2; }; _arch() { echo amd64; }; country_flag() { echo 🌐; }; x-ui() { :; };\n'
        code+='\n'.join(function(n) for n in ('gen_random_string','gen_group_id','_panel_initial_config','install_panel'))
        # JSON closing braces inside SQL heredocs are not Bash function ends.
        configure=re.search(r'^configure_xui_db\(\).*?^}\n\n#',SOURCE,re.M|re.S).group().removesuffix('\n\n#')
        code+='\n'+configure
        subprocess.run(['bash','-n','-c',code],check=True,capture_output=True,text=True)
        result=subprocess.run(['bash','-eu','-c',code+'\ninstall_panel && configure_xui_db'],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stderr)
        run('systemd-analyze','verify','/etc/systemd/system/x-ui.service')
        self.addCleanup(lambda: subprocess.run(['systemctl','stop','x-ui'],check=False))
        run('systemctl','start','x-ui')
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            try:
                response=run('curl','-q','-fsS','--cacert',str(cert),'--connect-timeout','2','--max-time','3',f'https://127.0.0.1:{FIXTURE["panel_port"]}/{FIXTURE["panel_path"]}/')
                if response: break
            except subprocess.CalledProcessError: pass
            time.sleep(.1)
        else: self.fail('Sandboxed panel HTTPS not ready: '+run('journalctl','-u','x-ui','--no-pager','-n','40'))
        run('systemctl','is-active','--quiet','x-ui')
        props=dict(line.split('=',1) for line in run('systemctl','show','x-ui','-p','ProtectSystem','-p','ProtectHome','-p','NoNewPrivileges','-p','SystemCallFilter','-p','ReadWritePaths','-p','CapabilityBoundingSet').splitlines())
        self.assertEqual(props['ProtectSystem'],'full'); self.assertEqual(props['ProtectHome'],'read-only')
        self.assertEqual(props['NoNewPrivileges'],'yes')
        groups={}
        def expand(group):
            if group not in groups:
                values=set()
                for line in run('systemd-analyze','syscall-filter',group).splitlines():
                    name=line.strip()
                    if not name or name.startswith('#') or name==group: continue
                    if name.startswith('@'): values.update(expand(name))
                    else: values.add(name)
                groups[group]=values
            return groups[group]
        self.assertFalse(props['SystemCallFilter'].startswith('~'),'Expected an allowlist')
        self.assertEqual(set(props['SystemCallFilter'].split()),expand('@system-service'))
        pid=run('systemctl','show','x-ui','-p','MainPID','--value').strip()
        status=Path('/proc/'+pid+'/status').read_text()
        self.assertRegex(status,r'(?m)^Seccomp:\s+2$')
        self.assertRegex(status,r'(?m)^NoNewPrivs:\s+1$')
        writable={p.removeprefix('-') for p in props['ReadWritePaths'].split()}
        self.assertTrue({'/etc/x-ui','/usr/local/x-ui','/var/log/x-ui'} <= writable)
        self.assertTrue(writable.isdisjoint({'/usr','/etc','/root'}))
        self.assertEqual(set(props['CapabilityBoundingSet'].lower().split()),{'cap_dac_override','cap_net_admin','cap_net_bind_service','cap_net_raw'})
        with tempfile.TemporaryDirectory() as directory:
            panel=helper('amneziawg').Panel(f'https://127.0.0.1:{FIXTURE["panel_port"]}/{FIXTURE["panel_path"]}/','integration','temporary-fixture-password',directory,('--cacert',str(cert)))
            panel.create('deploy.example')
        for restarted in (False,True):
            if restarted: run('systemctl','restart','x-ui')
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                sock=Path('/dev/shm/uds2023.sock')
                listeners=run('ss','-H','-lntup')
                if sock.exists() and stat.S_ISSOCK(sock.stat().st_mode) and 'uds2023.sock' in run('ss','-H','-lxnp') and 'xray' in listeners and any(':443 ' in line and line.startswith('udp') for line in listeners.splitlines()) and any(':8443 ' in line and line.startswith('udp') and 'x-ui' in line for line in listeners.splitlines()):
                    break
                time.sleep(.1)
            else: self.fail('Sandboxed Xray/UDS/Hysteria2/AWG not ready: '+run('journalctl','-u','x-ui','--no-pager','-n','40'))
        self.assertEqual(run('sqlite3','/etc/x-ui/x-ui.db','PRAGMA quick_check;').strip(),'ok')
        print('REAL baseline CLI → production SQL/cert → sandboxed HTTPS/Xray/UDS/Hysteria2/AWG/restart: PASS',flush=True)

    def test_real_security_strict_tls_and_rollback(self):
        if Path('/proc/1/comm').read_text().strip() != 'systemd':
            self.fail('Requires real systemd PID 1 in a disposable VM; never mocked PASS')
        from test_integrated_features import helper
        security = helper('security')
        run = lambda *args: subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=90)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cert, key = root/'cert.pem', root/'key.pem'
            run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                '-subj', '/CN=Test DNS CA', '-addext', 'subjectAltName=DNS:one.one.one.one,DNS:dns.google,IP:127.0.0.1',
                '-addext', 'basicConstraints=critical,CA:TRUE', '-out', str(cert), '-keyout', str(key))
            ca = Path('/usr/local/share/ca-certificates/xui-ci-dot.crt'); ca.write_bytes(cert.read_bytes())
            # Offline fixture trusts its generated CA only. Avoid hashing every
            # public CA under TCG; hostname/chain verification stays real.
            Path('/etc/ca-certificates.conf').write_text('')
            run('update-ca-certificates','--fresh')
            # getaddrinfo/resolved need a non-loopback configured address. A
            # guest-only dummy interface supplies it without any outside network.
            run('modprobe','dummy')
            run('ip','link','add','xui-test','type','dummy')
            run('ip','address','add','192.0.2.10/24','dev','xui-test')
            run('ip','link','set','xui-test','up')
            seen, errors, stop = [], [], threading.Event()
            fail_tls=threading.Event()
            route_policy=threading.Event()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert, key)
            servers = []
            for ip in ('1.1.1.1', '1.0.0.1', '8.8.8.8', '8.8.4.4'):
                run('ip', 'address', 'add', ip+'/32', 'dev', 'lo')
                listener = socket.socket(); listener.bind((ip, 853)); listener.listen(); listener.settimeout(.5)
                servers.append(listener)
                def serve(listener=listener):
                    while not stop.is_set():
                        try:
                            conn, _ = listener.accept()
                        except socket.timeout: continue
                        except OSError: return
                        def answer(conn=conn):
                            try:
                                if fail_tls.is_set():
                                    conn.close(); return
                                with context.wrap_socket(conn, server_side=True) as tls:
                                    tls.settimeout(5)
                                    while not stop.is_set():
                                        size = tls.recv(2)
                                        if not size: break
                                        if len(size)!=2: raise ValueError('Short DNS length')
                                        count = struct.unpack('!H', size)[0]; packet = b''
                                        while len(packet)<count: packet += tls.recv(count-len(packet))
                                        if stop.is_set(): break
                                        end=12
                                        while packet[end]: end += packet[end]+1
                                        end += 5
                                        typ=struct.unpack('!H', packet[end-4:end-2])[0]
                                        question=packet[12:end]
                                        addr=socket.inet_aton('203.0.113.7') if typ==1 else socket.inet_pton(socket.AF_INET6, '2001:db8::7') if typ==28 else None
                                        response=packet[:2]+struct.pack('!HHHHH',0x8180,1,int(addr is not None),0,0)+question
                                        if addr: response += b'\xc0\x0c'+struct.pack('!HHIH',typ,1,1,len(addr))+addr
                                        seen.append((tls.version(), question))
                                        tls.sendall(struct.pack('!H',len(response))+response)
                            except (OSError, ssl.SSLError): pass
                            except Exception as exc: errors.append(str(exc))
                        threading.Thread(target=answer, daemon=True).start()
                threading.Thread(target=serve, daemon=True).start()
            self.addCleanup(stop.set)
            for listener in servers: self.addCleanup(listener.close)
            with socket.create_connection(('1.1.1.1',853),timeout=5) as plain:
                with ssl.create_default_context().wrap_socket(plain,server_hostname='one.one.one.one') as tls:
                    self.assertIn(tls.version(),('TLSv1.2','TLSv1.3'))
            # Start from the reported minimum VPS state, not a prepared resolver.
            self.assertFalse(Path('/etc/resolv.conf').is_symlink())
            original_dns=Path('/etc/resolv.conf').read_bytes()
            self.assertEqual(original_dns,b'nameserver 8.8.4.4\nnameserver 8.8.8.8\nnameserver 2001:4860:4860::8844\nnameserver 2001:4860:4860::8888\n')
            original_policy=Path('/etc/systemd/resolved.conf').read_bytes()
            self.assertEqual(original_policy,b'[Resolve]\nDNS=8.8.4.4 8.8.8.8 2001:4860:4860::8844 2001:4860:4860::8888\n')
            original_network=Path('/etc/network/interfaces').read_bytes()
            self.assertIn(b'dns-nameservers 8.8.8.8 2001:4860:4860::8888',original_network)
            self.assertFalse(Path('/usr/bin/resolvectl').exists())
            self.assertFalse(Path('/usr/sbin/ufw').exists())
            self.assertEqual(run('dpkg-query','-W','-f=${Status}','systemd-resolved'),'deinstall ok config-files')
            run('systemctl','enable','--now','ssh.socket')
            with socket.create_connection(('127.0.0.1',22),timeout=5) as ssh:
                self.assertTrue(ssh.recv(200).startswith(b'SSH-2.0-'))
            self.assertEqual(run('systemctl','is-active','ssh.service','ssh.socket').splitlines(),['active','active'])
            # Original plain external DNS works before takeover and after rollback.
            from test_real_services import question
            plain_servers=[]; plain_seen=[]; plain_stop=threading.Event()
            self.addCleanup(plain_stop.set)
            run('ip','address','add','9.9.9.9/32','dev','lo')
            for ip in ('8.8.8.8','8.8.4.4','9.9.9.9'):
                udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); udp.bind((ip,53)); udp.settimeout(.5)
                plain_servers.append(udp); self.addCleanup(udp.close)
                def answer_plain(udp=udp):
                    while not plain_stop.is_set():
                        try: packet,peer=udp.recvfrom(4096)
                        except socket.timeout: continue
                        except OSError: return
                        end=12
                        while packet[end]: end+=packet[end]+1
                        end+=5; kind=struct.unpack('!H',packet[end-4:end-2])[0]
                        response=packet[:2]+struct.pack('!HHHHH',0x8180,1,int(kind==1),0,0)+packet[12:end]
                        if kind==1: response+=b'\xc0\x0c'+struct.pack('!HHIH',1,1,1,4)+socket.inet_aton('203.0.113.7')
                        plain_seen.append(packet); udp.sendto(response,peer)
                threading.Thread(target=answer_plain,daemon=True).start()
            # Public DNS stand-ins exist only inside this offline VM.
            production_command=security.command
            plain_at_restart=[]
            def command(*args,**kwargs):
                if args==('systemctl','restart','systemd-resolved.service'):
                    plain_at_restart.append(len(plain_seen))
                result=production_command(*args,**kwargs)
                if args==('systemctl','restart','systemd-resolved.service') and route_policy.is_set():
                    # Model a provider/VPN reapplying its real link route.
                    run('resolvectl','dns','xui-test','127.0.0.1')
                    run('resolvectl','domain','xui-test','~.')
                return result
            security.command=command
            # An offline local APT repository contains real distro resolved/UFW
            # packages and two tiny upgrade/retention packages. No host upgrade.
            run('dpkg','-i','/opt/xui-ci/apt/xui-ci-upgrade-1.deb','/opt/xui-ci/apt/xui-ci-retained-1.deb')
            sources=root/'sources.list'; sources.write_text('deb [trusted=yes] file:/opt/xui-ci/apt ./\n')
            apt_boot=root/'apt.conf'; apt_boot.write_text(f'Dir::Etc::sourcelist "{sources}"; Dir::Etc::sourceparts "{root}/absent";')
            os.environ['APT_CONFIG']=str(apt_boot)
            self.addCleanup(os.environ.pop,'APT_CONFIG',None)
            # Docker disables periodic APT in its image, unlike native distro
            # defaults. Prove preflight accepts it, then use a native numeric
            # provider drop-in so the production managed file takes precedence.
            disabled = Path('/etc/apt/apt.conf.d/docker-disable-periodic-update')
            if disabled.exists():
                security.preflight()
                disabled.unlink()
            disabled=Path('/etc/apt/apt.conf.d/20ci-disabled-periodic')
            disabled_policy=b'APT::Periodic::Enable "0";\nAPT::Periodic::Update-Package-Lists "0";\nAPT::Periodic::Unattended-Upgrade "0";\n'
            disabled.write_bytes(disabled_policy)
            self.addCleanup(disabled.unlink,missing_ok=True)
            stock_origins = security.apt_origins(run('apt-config', 'dump'))
            self.assertTrue(stock_origins, 'Native unattended-upgrades defaults missing')
            admin = Path('/etc/apt/apt.conf.d/51ci-additional-security')
            admin.write_text('Unattended-Upgrade::Origins-Pattern { "origin=Provider,label=Provider-Security"; };\n')
            self.addCleanup(admin.unlink, missing_ok=True)
            expected_origins = security.apt_origins(run('apt-config', 'dump'))
            self.assertTrue(stock_origins <= expected_origins)
            files_before = {str(p): p.read_bytes() for p in Path('/etc/apt/apt.conf.d').glob('*') if p.is_file()}
            prepared_os=security.preflight()[0]
            self.assertEqual({str(p): p.read_bytes() for p in Path('/etc/apt/apt.conf.d').glob('*') if p.is_file()}, files_before)
            effective = run('/usr/sbin/sshd', '-T')
            before = {p: p.read_bytes() for p in Path('/etc/ssh').rglob('*') if p.is_file()}
            from test_personal_xhttp import function
            shell='\n'.join(function(n) for n in ('apt_system','preflight_base_os','verify_base_os','prepare_base_os'))
            run('bash','-eu','-c','msg_err() { echo "$*" >&2; }; msg_warn() { echo "$*"; };\n'+shell+'\npreflight_base_os; prepare_base_os')
            self.assertEqual(run('dpkg-query','-W','-f=${Version}','xui-ci-upgrade'),'2')
            self.assertTrue(run('dpkg-query','-W','-f=${db:Status-Abbrev}','xui-ci-retained').startswith('ii'))
            self.assertTrue(Path('/usr/sbin/ufw').exists())
            self.assertTrue(run('ufw','status').startswith('Status: inactive'))
            self.assertFalse(Path('/usr/bin/resolvectl').exists())
            # Install actual resolved, make strict TLS query fail, and require a
            # verified return to the original regular file and working libc DNS.
            fail_tls.set()
            try: failed=security.prepare_dns()
            finally: fail_tls.clear()
            self.assertEqual(failed['status'],'failed_rolled_back',failed)
            self.assertFalse(Path('/etc/resolv.conf').is_symlink())
            self.assertEqual(Path('/etc/resolv.conf').read_bytes(),original_dns)
            self.assertIn('203.0.113.7',run('getent','ahosts','debian.org'))
            self.assertEqual(Path('/etc/systemd/resolved.conf').read_bytes(),original_policy)
            self.assertEqual(Path('/etc/network/interfaces').read_bytes(),original_network)
            # A different provider also passes real preparation and round-trip
            # rollback; no Google/Cloudflare ownership classification remains.
            other_dns=b'nameserver 9.9.9.9\n'
            Path('/etc/resolv.conf').write_bytes(other_dns)
            other_checkpoint=root/'other-dns-checkpoint'
            other=security.prepare_dns(state=other_checkpoint)
            self.assertEqual(other['status'],'configured',other)
            self.assertEqual(len(plain_seen),plain_at_restart[-1],'Plaintext DNS after provider takeover')
            restored=security.rollback_dns_checkpoint(other_checkpoint)
            self.assertEqual(restored['status'],'failed_rolled_back',restored)
            self.assertEqual(Path('/etc/resolv.conf').read_bytes(),other_dns)
            self.assertIn('203.0.113.7',run('getent','ahosts','debian.org'))
            Path('/etc/resolv.conf').write_bytes(original_dns)
            print('REAL other provider DNS / strict DoT / original DNS rollback: PASS',flush=True)
            # Package remains installed by design; remove it only in this VM to
            # recreate the original missing-package state for the success path.
            run('dpkg','-r','systemd-resolved')
            dns_checkpoint=root/'dns-checkpoint'
            success=security.prepare_dns(state=dns_checkpoint)
            self.assertEqual(success['status'],'configured',success)
            security.preflight()
            self.assertEqual(Path('/etc/systemd/resolved.conf').read_bytes(),original_policy)
            self.assertEqual(Path('/etc/network/interfaces').read_bytes(),original_network)
            self.assertTrue(seen,'No authenticated TLS query during preparation')
            self.assertEqual(len(plain_seen),plain_at_restart[-1],'Plaintext DNS after strict preparation')
            print('REAL minimal OS / residual resolved.conf preserved / full no-remove upgrade / missing UFW / DNS preparation and rollback: PASS',flush=True)
            # Snapshot before applying the production security function, restore afterwards.
            snapshot = security.Transaction()
            self.addCleanup(snapshot.temp.cleanup)
            capture = subprocess.Popen(['tcpdump','-i','lo','-n','-U','-w',str(root/'dns.pcap'),
                        'dst port 53 and (dst host 1.1.1.1 or dst host 1.0.0.1 or dst host 8.8.8.8 or dst host 8.8.4.4)'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                result = security.configure()
                self.assertEqual(disabled.read_bytes(),disabled_policy)
                if result['status'] != 'configured': print('TLS queries observed:',len(seen),'server errors:',errors,flush=True)
                self.assertEqual(result['status'], 'configured', result)
                self.assertEqual(result['dot'], 'configured')
                self.assertTrue(expected_origins <= security.apt_origins(run('apt-config','dump')))
                self.assertEqual(admin.read_text(),'Unattended-Upgrade::Origins-Pattern { "origin=Provider,label=Provider-Security"; };\n')
                self.assertTrue(seen, 'No actual TLS DNS query observed')
                self.assertFalse(errors, errors)
                self.assertTrue(all(version in ('TLSv1.2','TLSv1.3') for version,_ in seen))
                self.assertEqual(run('/usr/sbin/sshd','-T'), effective)
                self.assertEqual({p:p.read_bytes() for p in before}, before)
                for name,value in (('maxretry','5'),('findtime','1800'),('bantime','3600')):
                    self.assertEqual(run('fail2ban-client','get','sshd',name).strip(),value)
                run('fail2ban-client','status','sshd')
                # Run real AGH alongside strict resolved, with a trusted offline
                # HTTPS DNS upstream. Neither system DNS nor AGH uses the other.
                from test_real_services import question
                doh_queries=[]
                class DoH(BaseHTTPRequestHandler):
                    def do_POST(handler):
                        packet=handler.rfile.read(int(handler.headers['Content-Length']))
                        handler.answer(packet)
                    def do_GET(handler):
                        encoded=parse_qs(urlsplit(handler.path).query)['dns'][0]
                        handler.answer(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
                    def answer(handler,packet):
                        doh_queries.append(packet)
                        end=12
                        while packet[end]: end+=packet[end]+1
                        end+=5; kind=struct.unpack('!H',packet[end-4:end-2])[0]
                        response=packet[:2]+struct.pack('!HHHHH',0x8180,1,int(kind==1),0,0)+packet[12:end]
                        if kind==1: response+=b'\xc0\x0c'+struct.pack('!HHIH',1,1,60,4)+socket.inet_aton('203.0.113.7')
                        handler.send_response(200); handler.send_header('Content-Type','application/dns-message')
                        handler.send_header('Content-Length',str(len(response))); handler.end_headers(); handler.wfile.write(response)
                    def log_message(handler,*args): pass
                doh=ThreadingHTTPServer(('127.0.0.1',0),DoH)
                doh.socket=context.wrap_socket(doh.socket,server_side=True)
                threading.Thread(target=doh.serve_forever,daemon=True).start()
                self.addCleanup(doh.server_close); self.addCleanup(doh.shutdown)
                agh_config=root/'AdGuardHome.yaml'
                agh_config.write_text(json.dumps({'schema_version':34,'http':{'address':'127.0.0.1:8383'},
                    'dns':{'bind_hosts':['127.0.0.1'],'port':53,'upstream_dns':[f'https://127.0.0.1:{doh.server_port}/dns-query'],
                           'bootstrap_dns':[],'cache_size':4096},'filters':[],'tls':{'enabled':False}}))
                agh_log=open(root/'agh.log','wb'); self.addCleanup(agh_log.close)
                agh=subprocess.Popen(['/opt/xui-ci/AdGuardHome','-c',str(agh_config),'-w',str(root), '--no-check-update'],
                                     stdout=agh_log,stderr=agh_log)
                def stop_agh():
                    if agh.poll() is None: agh.terminate(); agh.wait(timeout=20)
                self.addCleanup(stop_agh)
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as dns:
                    dns.settimeout(2)
                    for attempt in range(15):
                        self.assertIsNone(agh.poll(),'Real AGH exited before DNS readiness: '+(root/'agh.log').read_text())
                        dns.sendto(question('adguard.example'),('127.0.0.1',53))
                        try: reply=dns.recv(4096); break
                        except socket.timeout:
                            if attempt==14: raise
                    self.assertTrue(doh_queries,'AGH did not reach its trusted HTTPS upstream: '+(root/'agh.log').read_text())
                    self.assertEqual(reply[-4:],socket.inet_aton('203.0.113.7'),(root/'agh.log').read_text())
                before_dot,before_doh=len(seen),len(doh_queries)
                run('resolvectl','query','--cache=no','system-with-adguard.example')
                self.assertGreater(len(seen),before_dot)
                self.assertEqual(len(doh_queries),before_doh,'System resolved unexpectedly routed into AGH')
                managed_before={name:Path(name).read_bytes() for name in security.FILES}
                run('resolvectl','dns','xui-test','127.0.0.1'); run('resolvectl','domain','xui-test','~.')
                route_policy.set()
                try: route_failure=security.configure()
                finally: route_policy.clear()
                self.assertEqual(route_failure['status'],'failed_rolled_back',route_failure)
                self.assertTrue(any('Interface/VPN DNS route' in warning for warning in route_failure['warnings']))
                self.assertEqual({name:Path(name).read_bytes() for name in security.FILES},managed_before)
                self.assertIsNone(agh.poll())
                run('resolvectl','revert','xui-test')
                print('REAL AdGuard Home HTTPS upstream + system DoT coexistence / loop refusal: PASS',flush=True)
                # Real socket activation overrides sshd's configured port. This
                # fixture changes only its socket; production must merely detect it.
                socket_drop = Path('/etc/systemd/system/ssh.socket.d/99-xui-ci.conf')
                socket_drop.parent.mkdir(exist_ok=True)
                socket_drop.write_text('[Socket]\nListenStream=\nListenStream=127.0.0.1:2222\n')
                run('systemctl','stop','ssh.socket','ssh.service')
                run('systemctl','daemon-reload')
                run('systemctl','enable','--now','ssh.socket')
                with socket.create_connection(('127.0.0.1',2222),timeout=5) as ssh:
                    self.assertTrue(ssh.recv(200).startswith(b'SSH-2.0-'))
                self.assertEqual(security.configure()['status'],'configured')
                self.assertEqual(security.ssh_ports(effective,run('systemctl','show','ssh.socket','-p','Listen','--value')),[2222])
                self.assertIn('2222',run('fail2ban-client','-d'))
                self.assertEqual(run('/usr/sbin/sshd','-T'),effective)
                # Real socket state, private UFW recorder: never enable the
                # guest's firewall or modify its SSH policy for this regression.
                firewall=root/'firewall-calls'
                mock='ufw() { echo "$*" >> "$FIREWALL_LOG"; [[ "$*" != status ]] || echo "Status: inactive"; }; msg_err() { echo "$*" >&2; };\n'
                subprocess.run(['bash','-eu','-c',mock+function('setup_firewall')+'\nsetup_firewall'],check=True,capture_output=True,text=True,timeout=15,
                    env={**os.environ,'SSH_CONNECTION':'','INSTALL_SECURITY':'n','FIREWALL_LOG':str(firewall)})
                calls=firewall.read_text().splitlines()
                self.assertIn('allow 2222/tcp',calls); self.assertNotIn('allow 22/tcp',calls)
                self.assertLess(calls.index('allow 2222/tcp'),calls.index('--force enable'))
                # No silent downgrade when authenticated TLS endpoints become unavailable.
                stop.set()
                for listener in servers: listener.close()
                run('resolvectl','flush-caches')
                failure = subprocess.run(['timeout','20','resolvectl','query','--cache=no','unavailable.example'],capture_output=True)
                self.assertNotEqual(failure.returncode,0)
                capture.terminate(); capture.wait(timeout=10)
                snapshot.rollback()
                self.assertEqual(run('/usr/sbin/sshd','-T'),effective)
                # Invoke production rollback after a real unavailable TLS upstream,
                # rather than relying only on a manually restored snapshot.
                failed = security.configure()
                self.assertEqual(failed['status'],'failed_rolled_back',failed)
                self.assertTrue(all(not Path(name).exists() for name in security.FILES[:-1]))
                self.assertEqual(Path(security.FILES[-1]).read_text(),security.DOT)
                self.assertEqual(os.readlink('/etc/resolv.conf'),'/run/systemd/resolve/stub-resolv.conf')
                self.assertEqual(run('/usr/sbin/sshd','-T'),effective)
                restored=security.rollback_dns_checkpoint(dns_checkpoint)
                self.assertEqual(restored['status'],'failed_rolled_back',restored)
                self.assertFalse(Path('/etc/resolv.conf').is_symlink())
                self.assertEqual(Path('/etc/resolv.conf').read_bytes(),original_dns)
                self.assertEqual(Path('/etc/systemd/resolved.conf').read_bytes(),original_policy)
                self.assertIn('203.0.113.7',run('getent','ahosts','debian.org'))
                print('REAL late TLS failure: original pre-install DNS checkpoint restored and libc resolution works: PASS',flush=True)
            finally:
                if capture.poll() is None: capture.terminate(); capture.wait(timeout=10)
                if any((Path(name)).exists() for name in security.FILES): snapshot.rollback()
            plaintext = subprocess.check_output(['tcpdump','-nn','-r',str(root/'dns.pcap')],text=True,stderr=subprocess.DEVNULL,timeout=20)
            self.assertEqual(plaintext.strip(),'','Plaintext DNS reached an upstream')
            print('REAL systemd / sshd jail / timers / authenticated TLS DNS / no plaintext / rollback: PASS')
            # Persist only the tested policy into the next disposable boot. This
            # is not a full VPS recovery/reboot acceptance claim.
            for filename,text in ((security.FILES[1],security.apt_config(prepared_os)),
                                  (security.FILES[2],security.timer('02:30')),(security.FILES[3],security.timer('02:50'))):
                path=Path(filename); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text)
            run('systemctl','daemon-reload')
            run('systemctl','enable','--now','apt-daily.timer','apt-daily-upgrade.timer')
            # Initial reboot is manual even after a failed installation. The
            # harness still cold-boots to verify the independent nightly policy.
            self.assertTrue(Path('/run/reboot-required').exists())
            reboot_shell=function('finish_initial_reboot')
            for code in (0,1):
                notice=run('bash','-eu','-c','msg_warn() { echo "$*"; }; msg_err() { echo "$*" >&2; };\n'+reboot_shell+f'\necho INSTALLATION_REPORT; finish_initial_reboot {code}')
                self.assertIn('sudo reboot',notice)
                self.assertFalse(Path('/run/systemd/shutdown/scheduled').exists(),'Initial installation scheduled a reboot')
            run('modprobe','9pnet_virtio'); Path('/mnt/xui-ci').mkdir(exist_ok=True)
            run('mount','-t','9p','-o','trans=virtio,version=9p2000.L','xui-ci','/mnt/xui-ci')
            Path('/mnt/xui-ci/pre-boot-id').write_text(Path('/proc/sys/kernel/random/boot_id').read_text())
            Path('/mnt/xui-ci/expected-origins.json').write_text(json.dumps(sorted(expected_origins)))
            run('tar','-C','/','-cf','/mnt/xui-ci/reboot-policy.tar',
                *[f.lstrip('/') for f in security.FILES[1:4]], str(admin).lstrip('/'),
                'etc/systemd/system/timers.target.wants/apt-daily.timer',
                'etc/systemd/system/timers.target.wants/apt-daily-upgrade.timer')
