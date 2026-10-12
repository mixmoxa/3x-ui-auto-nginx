"""Offline loopback integration with authenticated official binaries, never host services."""
import base64
import copy
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import socket
import socketserver
import ssl
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid
from urllib.parse import parse_qs, quote, urlsplit

from test_personal_xhttp import ROOT, FIXTURE, render, seed, SHARED, MAIN, function as installer_function
from release_contract import selection, verify, validate_layout

MIHOMO_VERSION = 'v1.19.32'
MIHOMO_SHA256 = 'ba3ce607747a07f948fc35780e108a4a7c7f552a38b9bd4d115f313ebcb89c20'


def port(allocated, udp=False):
    for _ in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', 0))
            number = sock.getsockname()[1]
        if number not in allocated:
            allocated.add(number)
            return number
    raise RuntimeError('Could not allocate a distinct fixture port')


def download(url, target):
    subprocess.run(['curl','-fLsS','--retry','3','--connect-timeout','15','--max-time','180',
                    url,'-o',str(target)], check=True, timeout=600)


def stop(process):
    if getattr(process, '_integration_stopped', False):
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    # Also reap any descendant left after the parent exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)
    process._integration_stopped = True


class RealIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.geteuid() == 0:
            raise RuntimeError('Real integration requires non-root')
        cls.temp = tempfile.TemporaryDirectory(prefix='real-tools-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tools = Path(cls.temp.name)
        cls.release = selection()
        version, digest = cls.release['version'], cls.release['sha256']
        cached = os.environ.get('INTEGRATION_ARTIFACTS')
        archive, sidecar, mihomo = [cls.tools/n for n in ('x-ui.tar.gz','x-ui.sha256','mihomo.gz')]
        urls = (
            f'https://github.com/MHSanaei/3x-ui/releases/download/{version}/x-ui-linux-amd64.tar.gz',
            f'https://github.com/MHSanaei/3x-ui/releases/download/{version}/x-ui-linux-amd64.tar.gz.sha256',
            f'https://github.com/MetaCubeX/mihomo/releases/download/{MIHOMO_VERSION}/mihomo-linux-amd64-compatible-{MIHOMO_VERSION}.gz')
        for target, url in zip((archive,sidecar,mihomo),urls):
            if cls.release['candidate'] and target != mihomo:
                shutil.copyfile(Path(os.environ['UPSTREAM_CANDIDATE']).parent/target.name, target)
            elif cached:
                shutil.copyfile(Path(cached)/target.name, target)
            else:
                download(url, target)
        verify(archive, sidecar, digest)
        validate_layout(archive, 'amd64')
        print('Production archive layout: PASS', flush=True)
        if hashlib.sha256(mihomo.read_bytes()).hexdigest() != MIHOMO_SHA256:
            raise ValueError('Pinned Mihomo checksum mismatch')
        if os.uname().machine != 'x86_64':
            raise RuntimeError('Pinned integration artifacts require linux amd64')
        # Extract only the verified executable pair; runtime state is always private.
        with tarfile.open(archive) as bundle:
            for member in ('x-ui/x-ui','x-ui/bin/xray-linux-amd64'):
                entry = bundle.getmember(member)
                if not entry.isfile():
                    raise ValueError('Expected regular release binary')
                target = cls.tools/Path(member).name
                target.write_bytes(bundle.extractfile(entry).read()); target.chmod(0o755)
        cls.xui, cls.xray = cls.tools/'x-ui', cls.tools/'xray-linux-amd64'
        cls.mihomo = cls.tools/'mihomo'
        cls.mihomo.write_bytes(gzip.decompress(mihomo.read_bytes())); cls.mihomo.chmod(0o755)
        cls.nginx = os.environ.get('NGINX_BIN') or shutil.which('nginx')
        if not cls.nginx:
            raise RuntimeError('Real nginx is required')
        xray_version = subprocess.check_output([cls.xray,'version'], text=True,timeout=20)
        if cls.release['xray'] and not xray_version.startswith('Xray '+cls.release['xray']+' '):
            raise ValueError('Unexpected bundled Xray version')
        xui_version = subprocess.check_output([cls.xui,'-v'], text=True,timeout=20).strip()
        if xui_version != version[1:]:
            raise ValueError('Archive binary version does not match selected 3x-ui release: '+xui_version)
        versions = {'3x-ui':xui_version, 'bundled_xray':xray_version.splitlines()[0]}
        print('\n3x-ui '+('CANARY candidate' if cls.release['candidate'] else 'verified baseline')+':',version,
              '\nArchive SHA-256:',digest, '\n'+xray_version.splitlines()[0])
        print(subprocess.check_output([cls.mihomo,'-v'],text=True,timeout=20).strip())
        print(subprocess.run([cls.nginx,'-v'],capture_output=True,text=True,check=True,timeout=20).stderr.strip(),flush=True)
        # All required downloads finish before the Canary preparation marker.
        cls.qemu_arm=shutil.which('qemu-arm')
        if not cls.qemu_arm: raise RuntimeError('Explicit integration dependency qemu-user is missing')
        cls.expected_xray=xray_version.split()[1]
        cls.arm_tools={}
        from release_contract import baseline
        manifest=baseline()
        if cls.release['candidate']:
            metadata=cls.tools/'arm-release.json'
            download(f'https://api.github.com/repos/MHSanaei/3x-ui/releases/tags/{version}',metadata)
            release=json.loads(metadata.read_text())
            if release['tag_name']!=version or release['draft'] or release['prerelease']:
                raise ValueError('Not the selected official stable ARM release')
        for arch in ('armv5','armv6','armv7'):
            name=f'x-ui-linux-{arch}.tar.gz'; archive=cls.tools/name; sidecar=cls.tools/(name+'.sha256')
            if cls.release['candidate']:
                assets=[a for a in release['assets'] if a['name']==name]
                if len(assets)!=1: raise ValueError('Missing/ambiguous ARM asset: '+name)
                digest=assets[0]['digest'].removeprefix('sha256:')
            else: digest=manifest['archives'][arch]
            download(f'https://github.com/MHSanaei/3x-ui/releases/download/{version}/{name}',archive)
            download(f'https://github.com/MHSanaei/3x-ui/releases/download/{version}/{name}.sha256',sidecar)
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest or sidecar.read_text().split()!=[digest,name]:
                raise ValueError('Official ARM archive/sidecar mismatch: '+arch)
            validate_layout(archive,arch)
            folder=cls.tools/arch; folder.mkdir()
            with tarfile.open(archive) as bundle:
                panel,binary=folder/'x-ui',folder/'xray-linux-arm32'
                panel.write_bytes(bundle.extractfile('x-ui/x-ui').read()); panel.chmod(0o755)
                binary.write_bytes(bundle.extractfile('x-ui/bin/xray-linux-'+arch).read()); binary.chmod(0o755)
            cls.arm_tools[arch]=(panel,binary)
        cls.passed = []
        # Publish readiness only after every required artifact/tool is prepared.
        if os.environ.get('UPSTREAM_REPORT'):
            Path(os.environ['UPSTREAM_REPORT']).write_text(json.dumps({**versions,'preparation_complete':True})+'\n')

    @classmethod
    def tearDownClass(cls):
        print('\nREAL XRAY INTEGRATION\n'+'\n'.join(f'{name:24} PASS' for name in cls.passed),flush=True)

    def test_official_arm32_runtime_binary_contract(self):
        config=self.root/'arm-config.json'
        config.write_text(json.dumps({'inbounds':[],'outbounds':[{'protocol':'freedom'}]}))
        for arch,(panel,binary) in self.arm_tools.items():
            panel_version=subprocess.check_output([self.qemu_arm,str(panel),'-v'],text=True,timeout=45).strip()
            self.assertEqual(panel_version,self.release['version'].removeprefix('v'))
            output=subprocess.check_output([self.qemu_arm,str(binary),'version'],text=True,timeout=45)
            self.assertTrue(output.startswith('Xray '+self.expected_xray+' '))
            keys=subprocess.check_output([self.qemu_arm,str(binary),'x25519'],text=True,timeout=45)
            self.assertTrue('PrivateKey:' in keys and 'Password' in keys,'X25519 output contract mismatch')
            subprocess.run([self.qemu_arm,str(binary),'run','-test','-config',str(config)],check=True,capture_output=True,timeout=45)
            print(arch+': authenticated ARM32 version / X25519 / real config validation PASS',flush=True)
        self.passed.append('ARM32 runtime contract')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='real-core-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.uds = self.root/'xhttp.sock'
        self.marker = 'FREE-INTEGRATION-'+os.urandom(12).hex()
        marker = self.marker.encode()
        self.origin_requests = []
        self.origin_responses = {}
        requests = self.origin_requests
        responses = self.origin_responses
        class Origin(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200); self.send_header('Content-Length',str(len(marker)))
                self.end_headers(); self.wfile.write(marker)
            def log_message(self,*args): pass
        class FragmentedOrigin(socketserver.BaseRequestHandler):
            def handle(handler):
                handler.request.settimeout(15)
                request = b''
                while b'\r\n\r\n' not in request:
                    chunk = handler.request.recv(4096)
                    if not chunk: return
                    request += chunk
                    if len(request) > 65536: raise ValueError('Oversized origin request')
                nonce = request.split(b' ',2)[1].decode('ascii')
                requests.append(nonce)
                headers = (f'HTTP/1.1 200 OK\r\nX-Forensic-Nonce: {nonce}\r\n'
                           f'Content-Length: {len(marker)}\r\nConnection: close\r\n\r\n').encode()
                responses[nonce] = headers + marker
                # Deliberately separate header fragments and body. No delay or retry.
                for chunk in (headers[:5], headers[5:23], headers[23:], marker):
                    handler.request.sendall(chunk)
        origin_type = socketserver.ThreadingTCPServer if ('grpc_fragmented' in self._testMethodName or 'mihomo' in self._testMethodName) else ThreadingHTTPServer
        self.origin = origin_type(('127.0.0.1',0),FragmentedOrigin if origin_type is socketserver.ThreadingTCPServer else Origin)
        if origin_type is socketserver.ThreadingTCPServer:
            self.origin.server_port = self.origin.server_address[1]
        self.addCleanup(self.origin.server_close)
        self.allocated_ports = {self.origin.server_port}
        self.public = port(self.allocated_ports)
        self.hysteria_port = port(self.allocated_ports, udp=True)
        self.backends = {k:port(self.allocated_ports) for k in ('reality','ws','trojan-grpc','tls','cover','panel','sub','api')}
        threading.Thread(target=self.origin.serve_forever,daemon=True).start()
        self.addCleanup(self.origin.shutdown)
        self.cert,self.key = self.root/'cert.pem',self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=deploy.example','-addext','subjectAltName=DNS:deploy.example,DNS:cover.example',
                        '-keyout',str(self.key),'-out',str(self.cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        pair = subprocess.check_output([self.xray,'x25519'], text=True,timeout=10)
        self.private = re.search(r'^PrivateKey: (.+)$',pair,re.M)[1]
        self.public_key = re.search(r'^Password \(PublicKey\): (.+)$',pair,re.M)[1]
        self.uuid = subprocess.check_output([self.xray,'uuid'],text=True,timeout=10).strip()
        self.auth = os.urandom(16).hex()
        self.rows,self.hosts = seed(private_key=self.private,public_key=self.public_key)
        # Existing render helper uses a..h placeholders; production uses openssl rand -hex 8.
        self.short_ids = [os.urandom(8).hex() for _ in range(8)]
        reality = json.loads(self.rows['reality']['stream_settings'])
        self.assertEqual(reality['realitySettings']['shortIds'], list('abcdefgh'))
        reality['realitySettings']['shortIds'] = self.short_ids
        self.rows['reality']['stream_settings'] = json.dumps(reality)
        self.build_subscriptions()

    def launch(self, argv, label, env=None):
        log = open(self.root/(label+'.log'),'wb')
        self.addCleanup(log.close)
        process = subprocess.Popen(list(map(str,argv)),cwd=self.root,env=env,stdout=log,stderr=log,start_new_session=True)
        self.addCleanup(stop,process)
        return process

    def ready(self, process, address=None, path=None, udp_port=None, udp_address="127.0.0.1"):
        deadline = time.monotonic()+15
        description = f'pid={process.pid}, TCP={address}, UDS={path}, UDP={udp_port}'
        udp_state = ''
        while time.monotonic()<deadline:
            self.assertIsNone(process.poll(), 'component exited before readiness: '+description)
            if path and path.is_socket(): return
            if udp_port:
                result = subprocess.run(['ss','-H','-lunp','sport = :'+str(udp_port)],
                                        capture_output=True,text=True,check=True,timeout=2)
                udp_state = result.stdout
                # Linux socket table plus owning PID proves a bound listener, not UDP connect().
                if any(len(fields := line.split()) >= 5 and fields[3] == f'{udp_address}:{udp_port}'
                       and f'pid={process.pid},' in line for line in udp_state.splitlines()):
                    return
            if address:
                try:
                    with socket.create_connection(address,timeout=0.2): return
                except OSError: pass
            time.sleep(0.05)
        self.fail('component readiness deadline expired: '+description+'; ss: '+udp_state)

    def validate(self, config, name):
        path = self.root/(name+'.json'); path.write_text(json.dumps(config))
        result = subprocess.run([self.xray,'run','-test','-c',path],capture_output=True,text=True,timeout=20)
        # Do not dump configs/private credentials into CI logs.
        self.assertEqual(result.returncode,0, name+' rejected: '+(result.stdout+result.stderr)[-2000:])
        return path

    def release_subscription_socket(self):
        """Release only an inactive UDS left by the stopped private x-ui fixture."""
        self.assertEqual(self.root,Path(self.temp.name))
        self.assertEqual(self.uds,self.root/'xhttp.sock')
        try:
            mode = self.uds.lstat().st_mode
        except FileNotFoundError:
            return
        self.assertTrue(stat.S_ISSOCK(mode),'Expected a private subscription UDS, not a file/symlink')
        table = subprocess.check_output(['ss','-H','-xlpn'],text=True,timeout=2)
        self.assertFalse(any(str(self.uds) in line.split() for line in table.splitlines()),
                         'Cannot remove active subscription UDS: '+str(self.uds))
        self.uds.unlink()

    def build_subscriptions(self):
        """Real bundled x-ui, native private state overrides, actual installer SQL."""
        dbdir,bindir,logs = [self.root/n for n in ('db','bin','logs')]
        for directory in (dbdir,bindir,logs): directory.mkdir()
        shutil.copyfile(self.xray,bindir/self.xray.name); (bindir/self.xray.name).chmod(0o755)
        env = {**os.environ,'XUI_DB_FOLDER':str(dbdir),'XUI_BIN_FOLDER':str(bindir),'XUI_LOG_FOLDER':str(logs)}
        initial = installer_function('_panel_initial_config').replace('/usr/local/x-ui/x-ui', shlex.quote(str(self.xui)))
        env.update(XUIDB=str(dbdir/'x-ui.db'), config_username='integration',
                   config_password=self.auth, panel_port=str(self.backends['panel']), panel_path='panel')
        subprocess.run(['bash','-u','-c', 'msg_err() { echo "$*" >&2; }\n'+initial+'\n_panel_initial_config'],
                       env=env, check=True, stdout=subprocess.DEVNULL, timeout=30)
        with sqlite3.connect(dbdir/'x-ui.db') as db:
            # Native CLI exit 0 alone does not prove setting persistence. Validate
            # the exact bootstrap contract before any test-runtime substitutions.
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone(), ('ok',))
            values = dict(db.execute("SELECT key,value FROM settings WHERE key IN ('webPort','webBasePath','webListen')"))
            self.assertEqual(values, {'webPort':str(self.backends['panel']), 'webBasePath':'/panel/', 'webListen':'127.0.0.1'})
            user = db.execute('SELECT username,password FROM users ORDER BY id LIMIT 1').fetchone()
            self.assertEqual(user[0], 'integration')
            self.assertNotEqual(user[1], self.auth)
            self.assertTrue(user[1].startswith(('$2a$','$2b$','$2y$')), 'Expected persisted bcrypt credentials')
            sql = render('sqlite3 $XUIDB',private_key=self.private,public_key=self.public_key)
            for placeholder, short_id in zip('abcdefgh', self.short_ids):
                sql = sql.replace('\"'+placeholder+'\"', '\"'+short_id+'\"')
            db.executescript(sql)
            db.execute('INSERT INTO clients(email,sub_id,uuid,password,auth,flow,enable) VALUES(?,?,?,?,?,?,1)',
                       ('integration','fixture',self.uuid,self.auth,self.auth,'xtls-rprx-vision'))
            cid = db.execute('SELECT id FROM clients WHERE email=?',('integration',)).fetchone()[0]
            for row in db.execute('SELECT id,remark,listen,port,stream_settings FROM inbounds').fetchall():
                iid,remark,listen,number,stream_json = row
                name = remark.split()[-1]
                stream = json.loads(stream_json)
                self.assertEqual(json.loads(self.rows[name]['settings'])['clients'],[])
                db.execute('INSERT INTO client_inbounds(client_id,inbound_id,flow_override) VALUES(?,?,?)',
                           (cid,iid,'xtls-rprx-vision' if name=='reality' else ''))
                if name=='xhttp':
                    self.assertEqual(listen,'/dev/shm/uds2023.sock,0666')
                    listen = str(self.uds)+',0666'
                elif name=='hysteria2':
                    self.assertEqual((listen,number),('',443))
                    listen='127.0.0.1'; number=self.hysteria_port
                    self.assertEqual(stream['tlsSettings']['serverName'],'deploy.example')
                    self.assertEqual(stream['tlsSettings']['alpn'],['h3'])
                    self.assertEqual(stream['tlsSettings']['certificates'][0]['certificateFile'], '/root/cert/deploy.example/fullchain.pem')
                    self.assertEqual(stream['tlsSettings']['certificates'][0]['keyFile'], '/root/cert/deploy.example/privkey.pem')
                    stream['tlsSettings']['certificates'][0].update(certificateFile=str(self.cert),keyFile=str(self.key))
                else:
                    self.assertEqual(listen,'127.0.0.1'); number=self.backends[name]
                if name=='reality':
                    self.assertEqual(stream['realitySettings']['target'],'127.0.0.1:9443')
                    stream['realitySettings']['target']=f"127.0.0.1:{self.backends['cover']}"
                db.execute('UPDATE inbounds SET listen=?,port=?,stream_settings=?,enable=1 WHERE id=?',
                           (listen,number,json.dumps(stream),iid))
            updates = {'webListen':'127.0.0.1','subListen':'127.0.0.1','subPort':str(self.backends['sub']),
                       'webCertFile':str(self.cert),'webKeyFile':str(self.key),
                       'subCertFile':str(self.cert),'subKeyFile':str(self.key),
                       'xrayTemplateConfig':json.dumps({'log':{'loglevel':'warning'},'inbounds':[],
                            'outbounds':[{'protocol':'freedom','tag':'direct','settings':{'finalRules':[
                                # Xray defaults block private targets. Only this test origin is allowed.
                                {'action':'allow','ip':['127.0.0.1'],'port':str(self.origin.server_port)}]}}],'routing':{'rules':[]}})}
            for key,value in updates.items():
                db.execute('DELETE FROM settings WHERE key=?',(key,))
                db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(key,value))
        process = self.launch([self.xui],'subscription-server',env=env)
        self.ready(process,('127.0.0.1',self.backends['sub']))
        def get(path):
            return subprocess.check_output(['curl','-fsS','--noproxy','*','--cacert',str(self.cert),
                       '--resolve',f"deploy.example:{self.backends['sub']}:127.0.0.1",'--max-time','15',
                       f"https://deploy.example:{self.backends['sub']}/{path}/fixture"],timeout=20)
        self.raw = get('subscription')
        self.json_subscription = json.loads(get('jsonsub'))
        self.provider = subprocess.check_output([
            'curl','-fsS','--noproxy','*','--cacert',str(self.cert),'--resolve',
            f"deploy.example:{self.backends['sub']}:127.0.0.1",'--max-time','15',
            f"https://deploy.example:{self.backends['sub']}/subscription/fixture?provider=1"],timeout=20)
        stop(process)
        self.release_subscription_socket()
        # The subscription process group is stopped; use its authoritative generated config.
        self.server = json.loads((bindir/'config.json').read_text())
        self.server.setdefault('log', {})['loglevel']='debug'
        self.validate(self.server,'server')
        self.client_configs = self.json_subscription if isinstance(self.json_subscription,list) else [self.json_subscription]
        self.assertEqual(len(self.client_configs),5, 'all managed profiles must be public')
        self.clients = {}
        for config in self.client_configs:
            outbound = next(o for o in config['outbounds'] if o['protocol'] in ('vless','trojan','hysteria'))
            stream = outbound['streamSettings']; network=stream['network']
            name = 'reality' if stream['security']=='reality' else {'ws':'ws','xhttp':'xhttp','grpc':'trojan-grpc','hysteria':'hysteria2'}[network]
            self.validate(config, name+'-public-subscription')
            self.clients[name] = config
        self.assertEqual(set(self.clients),set(self.rows))
        if 'Config validation' not in self.passed:
            self.passed.append('Config validation')

    def nginx_config(self):
        shared = render(SHARED, sub_port=str(self.backends['sub']), ws_port=str(self.backends['ws']),trojan_port=str(self.backends['trojan-grpc']))
        # Match backend relationship while keeping the seeded public paths unchanged.
        shared = shared.replace(f"/{self.backends['ws']}/websocket",'/10003/websocket').replace(
            f"/{self.backends['trojan-grpc']}/trojan",'/10004/trojan').replace('/dev/shm/uds2023.sock',str(self.uds))
        (self.root/'shared.conf').write_text(shared)
        main = render(MAIN,panel_port=str(self.backends['panel']),sub_port=str(self.backends['sub']))
        main = main.replace('127.0.0.1:7443',f"127.0.0.1:{self.backends['tls']}")
        main = main.replace('/etc/nginx/snippets/includes.conf',str(self.root/'shared.conf'))
        main = re.sub(r'include /etc/nginx/snippets/x-ui-auto-optional/\*\.conf;', '', main)
        main = re.sub(r'/etc/letsencrypt/live/[^/]+/fullchain.pem',str(self.cert),main)
        main = re.sub(r'/etc/letsencrypt/live/[^/]+/privkey.pem',str(self.key),main)
        main = main.replace('/var/www',str(self.root/'www'))
        stream = render('cat > /etc/nginx/stream-enabled/stream.conf')
        stream = stream.replace('127.0.0.1:8443',f"127.0.0.1:{self.backends['reality']}").replace(
            '127.0.0.1:7443',f"127.0.0.1:{self.backends['tls']}")
        stream = stream.replace('listen     443;',f'listen 127.0.0.1:{self.public};').replace('listen     [::]:443;','')
        if hasattr(self, 'vision_artifacts'):
            stream_file, _, enabled = self.vision_artifacts
            stream_file.write_text(stream)
            stream = f'include {stream_file};'
            self.vision_site = f'include {enabled.parent}/*.conf;'
        elif hasattr(self, 'vision_module'):
            stream = self.vision_module.stream_config(stream, 'vision.example', self.vision_port)
        temp = '\n'.join(f'{kind}_temp_path {self.root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        maps = render('cat > /etc/nginx/sites-available/00-maps.conf')
        cover = f"server {{ listen 127.0.0.1:{self.backends['cover']} ssl http2; ssl_certificate {self.cert}; ssl_certificate_key {self.key}; ssl_protocols TLSv1.3; return 200 'cover'; }}"
        config = f'''load_module /usr/lib/nginx/modules/ngx_stream_module.so;
worker_processes 1; daemon off; pid {self.root}/nginx.pid; error_log {self.root}/nginx-error.log;
events {{ worker_connections 256; }}
stream {{ {stream} }}
http {{ access_log {getattr(self, 'http_access_log', 'off')}; {temp} {maps} {main} {cover} {getattr(self, 'vision_site', '')} }}
'''
        path = self.root/'nginx.conf';path.write_text(config)
        result = subprocess.run([self.nginx,'-t','-p',str(self.root)+'/', '-c',path],text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        process = self.launch([self.nginx,'-p',str(self.root)+'/', '-c',path],'nginx')
        self.ready(process,('127.0.0.1',self.public))

    def client(self, name, negative=False, server_log="xray-server.log"):
        config = copy.deepcopy(self.clients[name])
        outbound = next(o for o in config['outbounds'] if o['protocol'] in ('vless','trojan','hysteria'))
        settings,stream = outbound['settings'],outbound['streamSettings']
        dest = settings['servers'][0] if 'servers' in settings else settings
        self.assertEqual((dest['address'],dest['port']),('deploy.example',443))
        dest.update(address='127.0.0.1',port=self.hysteria_port if name=='hysteria2' else self.public)
        if stream['security']=='tls':
            self.assertEqual(stream['tlsSettings'].get('serverName') or 'deploy.example','deploy.example')
            stream['tlsSettings']['serverName']='deploy.example'
            stream['tlsSettings']['allowInsecure']=False
            stream['tlsSettings']['certificates']=[{'certificateFile':str(self.cert),'usage':'verify'}]
        if negative:
            if name=='reality': stream['realitySettings']['shortId']='ffffffffffffffff'
            elif name=='xhttp': stream['xhttpSettings']['path']='/wrong-path'
            elif name=='ws': stream['wsSettings']['path']='/wrong-path'
            elif name=='trojan-grpc': stream['grpcSettings']['serviceName']='/wrong-service'
            else: stream['hysteriaSettings']['auth']='wrong-auth'
        socks=port(self.allocated_ports)
        config.setdefault('log', {})['loglevel']='debug'
        config['inbounds']=[{'listen':'127.0.0.1','port':socks,'protocol':'socks','settings':{'auth':'noauth'}}]
        config['outbounds']=[outbound]
        config.pop('routing',None);config.pop('dns',None)
        path=self.validate(config, name+('-negative' if negative else '-positive'))
        process=self.launch([self.xray,'run','-c',path],name+('-bad-client' if negative else '-client'))
        self.ready(process,('127.0.0.1',socks))
        before=len(self.origin_requests)
        result=subprocess.run(['curl','-fsS','--trace-ascii',str(self.root/(name+'-curl.trace')),'--noproxy','','--socks5-hostname',f'127.0.0.1:{socks}',
                '--connect-timeout','5','--max-time','12',f'http://127.0.0.1:{self.origin.server_port}/{name}'],
                capture_output=True,text=True,timeout=18)
        stop(process)
        if negative:
            self.assertNotEqual(result.returncode,0,'bad transport credentials/path unexpectedly worked')
            self.assertNotIn(self.marker,result.stdout)
            self.assertEqual(len(self.origin_requests),before,'negative transport reached origin')
        else:
            self.assertEqual(result.returncode,0,(self.root/(name+'-curl.trace')).read_text()[-1000:]+result.stderr+'; '+(self.root/(name+'-client.log')).read_text()[-1500:]+'; server '+(self.root/server_log).read_text()[-2500:])
            self.assertEqual(result.stdout,self.marker)
            self.assertEqual(len(self.origin_requests),before+1)

    def transport(self,name):
        self.nginx_config()
        process=self.launch([self.xray,'run','-c',self.root/'server.json'],'xray-server')
        if name == 'xhttp':
            self.ready(process,path=self.uds)
            self.assertTrue(self.uds.is_socket(),'UDS must be created by the real Xray process')
        elif name == 'hysteria2':
            self.ready(process,udp_port=self.hysteria_port)
        else:
            self.ready(process,('127.0.0.1',self.backends[name]))
        self.client(name)
        self.client(name,negative=True)
        self.passed.append(name+' positive/negative')

    def test_reality(self): self.transport('reality')

    def test_vision_deploy_hook_waits_for_delayed_xray(self):
        from certificate_fixtures import certificates, function, relocate
        from test_integrated_features import helper
        self.vision_module = helper('vision')
        self.vision_port, fallback = port(self.allocated_ports), port(self.allocated_ports)
        certificates(self.root, extra=('vision.example',))
        lineage = self.root/'etc/letsencrypt/live/vision.example'
        cover = self.root/'vision-site'; cover.mkdir(); (cover/'index.html').write_text('vision-cover')
        self.vision_site = self.vision_module.fallback_config('vision.example', fallback, str(cover))
        self.nginx_config()
        inbound = self.vision_module.inbound('vision.example', self.vision_port, fallback,
            str(lineage/'fullchain.pem'), str(lineage/'privkey.pem'))
        config = self.validate({'inbounds': [inbound], 'outbounds': [{'protocol': 'freedom'}]}, 'hook-vision')
        backup = (ROOT/'assets/backup/x-ui-backup.sh').read_text()
        self.assertEqual(function('render_vision_hook'), function('render_vision_hook', backup))
        generator = relocate(function('render_vision_hook'), self.root)
        body = subprocess.check_output(['bash', '-c', generator+'\nrender_vision_hook vision.example'], text=True)
        # Only host service control, privileged port and private CA are mapped;
        # the rendered hook, curl, nginx stream, TLS and Xray fallback are real.
        trigger, pidfile = self.root/'restart', self.root/'service-pid'
        failures = []
        def restart():
            try:
                deadline = time.monotonic()+10
                while not trigger.exists():
                    if time.monotonic() >= deadline: raise RuntimeError('Hook did not restart its service')
                    time.sleep(.01)
                process = self.launch(['bash', '-c', 'sleep 1.2; exec "$@"', 'delayed-xray',
                    self.xray, 'run', '-c', config], 'hook-xray')
                pidfile.write_text(str(process.pid))
            except Exception as error:
                failures.append(type(error).__name__)
        worker = threading.Thread(target=restart, daemon=True); worker.start()
        mapping = '''systemctl() {
    if [[ "$*" == 'restart x-ui' ]]; then
        touch "$TRIGGER"
        for attempt in {1..100}; do [[ ! -f "$PIDFILE" ]] || return 0; sleep .01; done
        return 1
    fi
    [[ "$*" == 'is-active --quiet x-ui' ]] && kill -0 "$(cat "$PIDFILE")"
}
curl() { command curl --cacert "$TRUST" "$@"; }
'''
        body = body.replace('$VISION_DOMAIN:443:', f'$VISION_DOMAIN:{self.public}:').replace(
            'https://$VISION_DOMAIN/', f'https://$VISION_DOMAIN:{self.public}/')
        env = {**os.environ, 'TRIGGER': str(trigger), 'PIDFILE': str(pidfile), 'TRUST': str(lineage/'fullchain.pem'),
               'RENEWED_LINEAGE': str(lineage)}
        started = time.monotonic()
        result = subprocess.run(['bash', '-c', mapping+body], env=env, capture_output=True, text=True, timeout=18)
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive()); self.assertEqual(failures, [])
        self.assertEqual(result.returncode, 0, 'Delayed Xray readiness: '+result.stderr)
        self.assertGreaterEqual(time.monotonic()-started, 1.2)
        self.assertIn('curl:', result.stderr, 'The regression must actually attempt HTTPS before Xray is ready')
        # A genuinely untrusted certificate remains fail-closed within the bound.
        env['TRUST'] = str(self.cert)
        result = subprocess.run(['bash', '-c', 'systemctl() { return 0; };\ncurl() { command curl --cacert "$TRUST" "$@"; }\n'+body],
            env=env, capture_output=True, text=True, timeout=18)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('certificate', result.stderr.lower())
        self.assertNotIn('--insecure', body)
        self.passed.append('Vision deploy-hook delayed Xray / strict TLS')

    def test_vision_and_initial_client_official_api(self):
        from test_integrated_features import helper
        client, awg, self.vision_module = helper('client'), helper('amneziawg'), helper('vision')
        self.http_access_log = str(self.root/'http-access.log')
        self.vision_port, fallback = port(self.allocated_ports), port(self.allocated_ports)
        vision_cert, vision_key = self.root/'vision.pem', self.root/'vision.key'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=vision.example','-addext','subjectAltName=DNS:vision.example',
                        '-out',vision_cert,'-keyout',vision_key],check=True,capture_output=True,timeout=20)
        self.vision_module.certificate('vision.example', vision_cert, vision_key)
        cover_root = self.root/'vision-site'; cover_root.mkdir(); (cover_root/'index.html').write_text('vision-cover')
        self.vision_site = self.vision_module.fallback_config('vision.example', fallback, str(cover_root))
        self.vision_site = self.vision_site.replace('    server_tokens off;',
            f'    access_log {self.root}/vision-access.log;\n    server_tokens off;')
        self.vision_artifacts = (self.root/'vision-stream.conf', self.root/'vision.conf', self.root/'enabled/vision.conf')
        self.vision_artifacts[2].parent.mkdir()
        # The real child starts asynchronously. Widen its startup window so
        # readiness is tested reliably, rather than depending on runner speed.
        core = self.root/'bin'/self.xray.name
        core.rename(core.with_suffix('.real'))
        core.write_text('#!/bin/sh\ncase "$1" in -c|run) sleep 1.2;; esac\nexec '+shlex.quote(str(core.with_suffix('.real')))+' "$@"\n')
        core.chmod(0o755)
        with sqlite3.connect(self.root/'db/x-ui.db') as db:
            db.execute("UPDATE inbounds SET enable=0 WHERE protocol='trojan' OR json_extract(stream_settings,'$.network')='ws'")
            for key, value in {'subURI':f'https://deploy.example:{self.public}/subscription/',
                               'subJsonURI':f'https://deploy.example:{self.public}/jsonsub/'}.items():
                db.execute('UPDATE settings SET value=? WHERE key=?', (value,key))
        self.nginx_config()
        env = {**os.environ, 'XUI_DB_FOLDER':str(self.root/'db'), 'XUI_BIN_FOLDER':str(self.root/'bin'), 'XUI_LOG_FOLDER':str(self.root/'logs')}
        server = self.launch([self.xui], 'vision-panel', env)
        self.ready(server, ('127.0.0.1', self.backends['panel']))
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            api = awg.Panel(f'https://deploy.example:{self.public}/panel/', 'integration', self.auth, directory,
                ['--cacert', str(self.cert), '--resolve', f'deploy.example:{self.public}:127.0.0.1'])
            # Distinguish CSRF rejection from invalid-body/API validation failure.
            before_csrf = api.request('panel/api/clients/list')['obj']
            active = api.request('panel/api/inbounds/list')['obj']
            missing_csrf = subprocess.check_output(['curl','-q','-sS','--noproxy','*',*api.options,
                '--resolve',f'deploy.example:{self.backends["panel"]}:127.0.0.1',
                '--cookie',str(api.cookie),'--header','Content-Type: application/json','--data-binary','@-',
                '--max-time','20','-o','/dev/null','-w','%{http_code}',
                f'https://deploy.example:{self.backends["panel"]}/panel/panel/api/clients/add'],
                input=json.dumps({'client':{'email':'csrf-negative','enable':True},'inboundIds':[active[0]['id']]}).encode(),timeout=25)
            # Native 403 is checked directly: nginx deliberately masks it as 404.
            self.assertEqual(missing_csrf,b'403')
            self.assertEqual(api.request('panel/api/clients/list')['obj'],before_csrf)
            wrong_trust = [True]
            def production_run(*args):
                # Private process/config paths and test CA replace host services;
                # nginx validation/reload and HTTPS still execute real binaries.
                if args == ('nginx','-t'):
                    args=(self.nginx,'-t','-p',str(self.root)+'/', '-c',str(self.root/'nginx.conf'))
                elif args == ('systemctl','reload','nginx'):
                    args=(self.nginx,'-s','reload','-p',str(self.root)+'/', '-c',str(self.root/'nginx.conf'))
                elif args == ('systemctl','is-active','--quiet','x-ui'):
                    self.assertIsNone(server.poll()); return
                elif args[0]=='curl':
                    args=tuple(arg.replace('vision.example:443:',f'vision.example:{self.public}:')
                               .replace('https://vision.example/',f'https://vision.example:{self.public}/') for arg in args)
                    args+=('--cacert',str(self.cert if wrong_trust[0] else vision_cert))
                subprocess.run(args,check=True,capture_output=True,timeout=40)
            with patch.object(self.vision_module,'run',side_effect=production_run), \
                 patch.object(self.vision_module,'fallback_config',return_value=self.vision_module.fallback_config('vision.example',fallback,str(cover_root)).replace(
                     '    server_tokens off;',f'    access_log {self.root}/vision-access.log;\n    server_tokens off;')):
                original_stream=self.vision_artifacts[0].read_bytes()
                with self.assertRaises(self.vision_module.Failure) as failed:
                    self.vision_module.configure(api,'vision.example',self.vision_port,fallback,
                        *self.vision_artifacts,str(vision_cert),str(vision_key))
                self.assertEqual(failed.exception.status,'failed_rolled_back')
                self.assertIn('certificate verification failed',str(failed.exception))
                self.assertEqual(self.vision_artifacts[0].read_bytes(),original_stream)
                self.assertFalse(self.vision_artifacts[1].exists()); self.assertFalse(self.vision_artifacts[2].is_symlink())
                self.assertEqual({r['id'] for r in api.request('panel/api/inbounds/list')['obj']},{r['id'] for r in active})
                self.ready(server,('127.0.0.1',self.backends['reality']))
                for name in ('reality','xhttp'): self.client(name,server_log='vision-panel.log')
                print('REAL production Vision TLS failure / owned rollback / REALITY and XHTTP preserved: PASS',flush=True)
                wrong_trust[0]=False
                iid=self.vision_module.configure(api,'vision.example',self.vision_port,fallback,
                    *self.vision_artifacts,str(vision_cert),str(vision_key),flag='🇫🇮')
            created = next(r for r in api.request('panel/api/inbounds/list')['obj'] if r['id']==iid)
            self.assertEqual(created['remark'],'🇫🇮 XTLS')
            with sqlite3.connect(self.root/'db/x-ui.db') as db:
                self.assertEqual(db.execute('SELECT remark FROM hosts WHERE inbound_id=?',(iid,)).fetchone()[0],'vision')
            self.assertTrue(self.vision_artifacts[2].is_symlink())
            print('REAL production Vision configure / nginx reload / delayed Xray readiness / trusted HTTPS: PASS',flush=True)
            awg_row = api.create('deploy.example', port(self.allocated_ports, udp=True))
            api.request('panel/api/server/restartXrayService', {})
            self.ready(server, ('127.0.0.1', self.vision_port))
            try:
                result = client.create(api)
            except Exception:
                # Non-secret diagnostics: compare routing with the native backend.
                latest = api.request('panel/api/clients/list')['obj'][-1]['subId']
                rec = api.request('panel/api/clients/list')['obj'][-1]
                actual_links = client.decode_subscription(client.fetch(api,f'https://deploy.example:{self.public}/subscription/'+latest))
                official_links = api.request('panel/api/clients/links/'+rec['email'])['obj']
                for label, values in (('subscription',actual_links), ('API',official_links)):
                    print(label+' link metadata: '+str([(urlsplit(link).scheme,urlsplit(link).hostname if not link.startswith('vpn://') else 'AWG',
                        sorted(parse_qs(urlsplit(link).query))) for link in values]),flush=True)
                for target, name in ((f'https://deploy.example:{self.public}/subscription/', 'nginx'),
                                     (f'https://deploy.example:{self.backends["sub"]}/subscription/', 'native')):
                    status = subprocess.check_output(['curl','-sS','--noproxy','*','--cacert',str(self.cert),
                        '--resolve',f'deploy.example:{urlsplit(target).port}:127.0.0.1', '-o','/dev/null','-w','%{http_code}',target+latest],timeout=20)
                    print(name+' subscription HTTP: '+status.decode(),flush=True)
                raise
            again = client.create(api, {'email':result['email'], 'subId':result['subId']})
            self.assertEqual(again['email'], result['email'])
            self.assertEqual(stat.S_IMODE((self.root/'db/x-ui.db').stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE((self.root/'bin/config.json').stat().st_mode),0o600)
            expected = client.active_inbounds(api)
            self.assertEqual(len(expected),5)
            record = api.request('panel/api/clients/get/'+result['email'])['obj']
            self.assertEqual(set(record['inboundIds']), {r['id'] for r in expected})
            for key in ('totalGB','expiryTime','limitIp','limitHwid','tgId'):
                self.assertEqual(record['client'][key],0,key)
            self.assertTrue(record['client']['enable']); self.assertRegex(record['client']['subId'],r'^[a-z0-9]{16}$')
            self.assertNotIn('ws', result['protocols']); self.assertNotIn('trojan-grpc', result['protocols'])
            links = client.decode_subscription(client.fetch(api,result['url']))
            vision_links = [link for link in links if urlsplit(link).hostname=='vision.example']
            self.assertEqual(len(vision_links),1)
            query = parse_qs(urlsplit(vision_links[0]).query)
            self.assertEqual(query['flow'],['xtls-rprx-vision']); self.assertEqual(query['security'],['tls'])
            self.assertIn(query.get('type',['tcp'])[0],('tcp','raw'))
            raw = api.request('panel/api/setting/defaultSettings',{})['obj']
            configs = json.loads(client.fetch(api,raw['subJsonURI']+result['subId']))
            core_profiles = set()
            for native in configs:
                for outgoing in native.get('outbounds',[]):
                    stream = outgoing.get('streamSettings',{})
                    name = ('reality' if stream.get('security')=='reality' else
                            'xhttp' if stream.get('network')=='xhttp' else
                            'hysteria2' if outgoing.get('protocol')=='hysteria' else None)
                    if name:
                        self.clients[name] = native; core_profiles.add(name)
                        if name=='xhttp':
                            vless = outgoing['settings']
                            vless = vless['servers'][0] if 'servers' in vless else vless
                            user = vless.get('users',[vless])[0]
                            self.assertFalse(user.get('flow'),'JSON XHTTP inherited Vision flow')
            self.assertEqual(core_profiles,{'reality','xhttp','hysteria2'})
            for name in sorted(core_profiles): self.client(name,server_log='vision-panel.log')
            vision_config = next(config for config in configs if any(
                o.get('streamSettings',{}).get('tlsSettings',{}).get('serverName')=='vision.example' for o in config.get('outbounds',[])))
            outbound = next(o for o in vision_config['outbounds'] if o['protocol']=='vless')
            settings = outbound['settings']; dest=settings['servers'][0] if 'servers' in settings else settings
            self.assertEqual((dest['address'],dest['port']),('vision.example',443))
            dest.update(address='127.0.0.1',port=self.public)
            outbound['streamSettings']['tlsSettings'].update(allowInsecure=False, certificates=[{'certificateFile':str(vision_cert),'usage':'verify'}])
            socks=port(self.allocated_ports)
            config={'inbounds':[{'listen':'127.0.0.1','port':socks,'protocol':'socks','settings':{'auth':'noauth'}}], 'outbounds':[outbound]}
            process=self.launch([self.xray,'run','-c',self.validate(config,'vision-client')],'vision-client')
            self.ready(process,('127.0.0.1',socks))
            delivered=subprocess.run(['curl','-fsS','--noproxy','','--socks5-hostname',f'127.0.0.1:{socks}',
                '--connect-timeout','5','--max-time','15',f'http://127.0.0.1:{self.origin.server_port}/vision'],capture_output=True,text=True,timeout=20)
            self.assertEqual(delivered.returncode,0,delivered.stderr); self.assertEqual(delivered.stdout,self.marker)
            stop(process)
            # A wrong UUID must not carry a proxied request to the internal origin.
            bad = json.loads(json.dumps(config))
            bad_dest = bad['outbounds'][0]['settings']
            if 'servers' in bad_dest: bad_dest = bad_dest['servers'][0]
            if 'users' in bad_dest: bad_dest['users'][0]['id'] = str(uuid.uuid4())
            else: bad_dest['id'] = str(uuid.uuid4())
            bad_process = self.launch([self.xray,'run','-c',self.validate(bad,'vision-invalid-client')],'vision-invalid-client')
            self.ready(bad_process,('127.0.0.1',socks))
            denied = subprocess.run(['curl','-fsS','--noproxy','','--socks5-hostname',f'127.0.0.1:{socks}',
                '--connect-timeout','3','--max-time','5',f'http://127.0.0.1:{self.origin.server_port}/denied'],capture_output=True,timeout=10)
            self.assertNotEqual(denied.returncode,0); self.assertNotIn(self.marker.encode(),denied.stdout)
            stop(bad_process)
            # Import the official URI provider through real Mihomo, including TLS trust and flow.
            provider = self.root/'vision-provider.txt'
            provider.write_text(vision_links[0].replace('@vision.example:443',f'@vision.example:{self.public}'))
            mixed, control = port(self.allocated_ports), port(self.allocated_ports)
            mihomo_config = self.root/'vision-mihomo.yaml'
            mihomo_config.write_text(f'''mixed-port: {mixed}
external-controller: 127.0.0.1:{control}
bind-address: 127.0.0.1
hosts:
  vision.example: 127.0.0.1
tls:
  custom-certifactes:
    - {json.dumps(vision_cert.read_text())}
proxy-providers:
  sub:
    type: file
    path: {provider}
proxy-groups:
  - name: VPN
    type: select
    proxies: [DIRECT]
    use: [sub]
rules:
  - MATCH,VPN
''')
            mihomo = self.launch([self.mihomo,'-d',self.root,'-f',mihomo_config],'vision-mihomo')
            self.ready(mihomo,('127.0.0.1',control)); self.ready(mihomo,('127.0.0.1',mixed))
            # A direct option must never satisfy the Vision transfer assertion.
            from urllib.request import build_opener, ProxyHandler, Request
            from urllib.error import URLError
            controller=build_opener(ProxyHandler({}))
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                self.assertIsNone(mihomo.poll(),'Mihomo exited before provider readiness')
                try:
                    with controller.open(f'http://127.0.0.1:{control}/providers/proxies/sub',timeout=1) as response:
                        proxies=json.load(response).get('proxies',[])
                    if len(proxies)==1 and proxies[0].get('type','').lower()=='vless':
                        break
                except (URLError,TimeoutError): pass
                time.sleep(.05)
            else: self.fail('Official Vision provider did not load in Mihomo')
            selection=Request(f'http://127.0.0.1:{control}/proxies/VPN',
                              data=json.dumps({'name':proxies[0]['name']}).encode(),
                              headers={'Content-Type':'application/json'},method='PUT')
            with controller.open(selection,timeout=3) as response:
                self.assertEqual(response.status,204)
            with controller.open(f'http://127.0.0.1:{control}/proxies/VPN',timeout=3) as response:
                selected=json.load(response)
            self.assertEqual(selected['now'],proxies[0]['name'],'Mihomo did not select the imported VLESS Vision profile')
            imported = subprocess.run(['curl','-fsS','--noproxy','','--socks5-hostname',f'127.0.0.1:{mixed}',
                '--connect-timeout','5','--max-time','10',f'http://127.0.0.1:{self.origin.server_port}/mihomo-vision'],capture_output=True,text=True,timeout=15)
            self.assertEqual(imported.returncode,0,imported.stderr); self.assertEqual(imported.stdout,self.marker)
            stop(mihomo)
            self.assertFalse(result['subId'] in (self.root/'http-access.log').read_text(), 'Subscription identifier leaked into nginx access log')
            self.assertFalse(result['subId'] in (self.root/'nginx-error.log').read_text(), 'Subscription identifier leaked into nginx error log')
            # A failed subscription upstream must not leak the original secret
            # URI when nginx internally redirects to its generic error page.
            shared=self.root/'shared.conf'; original=shared.read_text()
            failed_port=port(self.allocated_ports)
            shared.write_text(original.replace(f'https://127.0.0.1:{self.backends["sub"]}',f'https://127.0.0.1:{failed_port}'))
            reload=[self.nginx,'-p',str(self.root)+'/', '-c',self.root/'nginx.conf','-s','reload']
            subprocess.run(reload,check=True,capture_output=True,timeout=15)
            time.sleep(.2)
            try:
                with self.assertRaises(ValueError): client.fetch(api,result['url'])
                self.assertFalse(result['subId'] in (self.root/'http-access.log').read_text(),'Failed subscription leaked into access log')
                self.assertFalse(result['subId'] in (self.root/'nginx-error.log').read_text(),'Failed subscription leaked into error log')
            finally:
                shared.write_text(original); subprocess.run(reload,check=True,capture_output=True,timeout=15)
            # Official JSON changes neither XHTTP flow nor TLS verification.
            client.validate_credentials(client.active_inbounds(api),result['email'])
        browser=['curl','-q','-fsS','--noproxy','*','--http1.1','--cacert',str(vision_cert),
                 '--resolve',f'vision.example:{self.public}:127.0.0.1','--max-time','10']
        self.assertEqual(subprocess.check_output(browser+[f'https://vision.example:{self.public}/'],timeout=15),b'vision-cover')
        self.assertEqual(subprocess.check_output(browser+['--interface','127.0.0.2',f'https://vision.example:{self.public}/'],timeout=15),b'vision-cover')
        self.assertIn('127.0.0.2 - ',(self.root/'vision-access.log').read_text(), 'Source IP lost in nginx / Xray / fallback PROXY chain')
        untrusted = subprocess.run([a for a in browser if a not in ('--cacert',str(vision_cert))]+[f'https://vision.example:{self.public}/'],capture_output=True,timeout=15)
        self.assertNotEqual(untrusted.returncode,0)
        wrong_sni = subprocess.run(browser+['--resolve',f'wrong.example:{self.public}:127.0.0.1',f'https://wrong.example:{self.public}/'],capture_output=True,timeout=15)
        self.assertNotEqual(wrong_sni.returncode,0)
        tls = ssl.create_default_context(cafile=str(vision_cert)); tls.set_alpn_protocols(['h2'])
        try:
            with socket.create_connection(('127.0.0.1',self.public),timeout=5) as plain:
                with tls.wrap_socket(plain,server_hostname='vision.example') as encrypted:
                    self.assertNotEqual(encrypted.selected_alpn_protocol(),'h2')
        except ssl.SSLError:
            pass  # A rejected, unsupported ALPN handshake is also a safe outcome.
        for path in ('panel/', 'subscription/fixture', 'dns-query', '__clash_api'):
            response=subprocess.run(browser+[f'https://vision.example:{self.public}/{path}'],capture_output=True,timeout=15)
            self.assertNotEqual(response.returncode,0); self.assertNotIn(self.auth.encode(),response.stdout)
        # Certbot renewal is exercised with Pebble in services. Here verify the
        # pinned native x-ui/Xray restart actually consumes a replaced Vision cert.
        from cryptography import x509
        old_cert = vision_cert.read_bytes()
        serial = x509.load_pem_x509_certificate(old_cert).serial_number + 1
        subprocess.run(['openssl','req','-x509','-new','-key',vision_key,'-days','1','-set_serial',str(serial),
            '-subj','/CN=vision.example','-addext','subjectAltName=DNS:vision.example','-out',vision_cert],
            check=True,capture_output=True,timeout=20)
        previous_trust = self.root/'vision-previous-trust.pem'; previous_trust.write_bytes(old_cert)
        def served_serial(trust):
            ctx = ssl.create_default_context(cafile=str(trust)); ctx.set_alpn_protocols(['http/1.1'])
            with socket.create_connection(('127.0.0.1',self.public),timeout=5) as plain:
                with ctx.wrap_socket(plain,server_hostname='vision.example') as connection:
                    return x509.load_der_x509_certificate(connection.getpeercert(binary_form=True)).serial_number
        self.assertNotEqual(served_serial(previous_trust),serial)
        stop(server)
        server=self.launch([self.xui], 'vision-panel-restarted', env)
        self.ready(server,('127.0.0.1',self.vision_port))
        self.assertEqual(subprocess.check_output(browser+[f'https://vision.example:{self.public}/'],timeout=15),b'vision-cover')
        self.assertEqual(served_serial(vision_cert),serial)
        for name in ('reality','xhttp','hysteria2'): self.client(name,server_log='vision-panel-restarted.log')
        self.passed.extend(['RAW TLS Vision + fallback','Initial client API / CSRF / subscriptions'])
    def test_xhttp(self): self.transport('xhttp')
    def test_websocket(self): self.transport('ws')
    def test_trojan_grpc(self): self.transport('trojan-grpc')

    def test_amneziawg_tcp_udp_and_panel_restart(self):
        # Same checksum-verified official x-ui as the existing integration baseline.
        import importlib.util
        spec = importlib.util.spec_from_file_location('awg_managed',ROOT/'assets/amneziawg/managed.py')
        managed = importlib.util.module_from_spec(spec); spec.loader.exec_module(managed)
        env = {**os.environ,'XUI_DB_FOLDER':str(self.root/'db'),'XUI_BIN_FOLDER':str(self.root/'bin'),
               'XUI_LOG_FOLDER':str(self.root/'logs')}
        server = self.launch([self.xui],'awg-panel',env)
        self.ready(server,('127.0.0.1',self.backends['panel']))
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            api = managed.Panel(f"https://deploy.example:{self.backends['panel']}/panel/",
                'integration',self.auth,directory,['--cacert',str(self.cert),
                '--resolve',f"deploy.example:{self.backends['panel']}:127.0.0.1"])
            awg_port = port(self.allocated_ports,udp=True)
            inbound = api.create('deploy.example',awg_port)
            self.assertEqual(inbound['settings']['clients'],[])
            second = api.create('deploy.example',port(self.allocated_ports,udp=True))
            for key in ('privateKey','publicKey','headerProtectionKey'):
                self.assertTrue(inbound['settings']['server'][key] != second['settings']['server'][key],
                                'Official API reused an AWG key')
            api.request('panel/api/inbounds/del/'+str(second['id']),{})
            api.request('panel/api/clients/add',{'client':{'email':'awg-integration','enable':True},
                                               'inboundIds':[inbound['id']]})
        stop(server)
        with sqlite3.connect(self.root/'db/x-ui.db') as db:
            settings = json.loads(db.execute('SELECT settings FROM inbounds WHERE id=?',(inbound['id'],)).fetchone()[0])
            self.assertEqual(len(settings['clients']),1)
            peer = settings['clients'][0]; parameters = settings['server']
        # A raw UDP echo origin proves payload delivery, not merely a bound VPN socket.
        udp = socket.socket(socket.AF_INET,socket.SOCK_DGRAM); udp.bind(('127.0.0.1',0))
        self.addCleanup(udp.close); udp.settimeout(1)
        udp_port = udp.getsockname()[1]; self.allocated_ports.add(udp_port)
        done = threading.Event(); self.addCleanup(done.set)
        def echo():
            while not done.is_set():
                try:
                    data,address = udp.recvfrom(65536); udp.sendto(data,address)
                except socket.timeout: pass
                except OSError: return
        threading.Thread(target=echo,daemon=True).start()
        with sqlite3.connect(self.root/'db/x-ui.db') as db:
            template = json.loads(db.execute("SELECT value FROM settings WHERE key='xrayTemplateConfig'").fetchone()[0])
            # gVisor rejects loopback destinations inside an IP tunnel. Route a
            # documentation/test address to the same private origins in test Xray only.
            template['outbounds'][0]['settings']['finalRules'][0]['port'] += ','+str(udp_port)
            template['outbounds'][0]['settings']['redirect'] = '127.0.0.1:0'
            db.execute("UPDATE settings SET value=? WHERE key='xrayTemplateConfig'",(json.dumps(template),))
        server = self.launch([self.xui],'awg-panel-active',env)
        self.ready(server,udp_port=awg_port,udp_address="0.0.0.0")
        self.ready(server,('127.0.0.1',self.backends['sub']))
        # The installer's owner check uses actual native AWG /proc ownership
        # and ss sockets; only systemd control, unit path and port are mapped.
        unit=self.root/'x-ui.service'; unit.write_text('[Service]\nExecStart='+str(self.xui)+'\n')
        controls=self.root/'owner-controls'; controls.mkdir()
        control=controls/'systemctl'
        control.write_text(f'#!/bin/sh\ncase "$*" in "is-active --quiet x-ui") kill -0 {server.pid};; "show x-ui -p MainPID --value") echo {server.pid};; *) exit 1;; esac\n'); control.chmod(0o755)
        owner=installer_function('check_awg_reinstall_owner').replace('/etc/systemd/system/x-ui.service',str(unit)).replace(
            '/usr/local/x-ui/bin',str(self.root/'bin')).replace('/usr/local/x-ui/x-ui',str(self.xui)).replace('8443',str(awg_port))
        verified=subprocess.run(['bash','-eu','-c',owner+'\ncheck_awg_reinstall_owner'],
            env={**os.environ,'PATH':str(controls)+':'+os.environ['PATH'],'XUIDB':str(self.root/'db/x-ui.db')},capture_output=True,text=True,timeout=10)
        self.assertEqual(verified.returncode,0,'Native managed AWG owner check failed')
        # Verify the real upstream export, including the public share host and 3.1 parameters.
        import configparser
        raw = subprocess.check_output(['curl','-fsS','--noproxy','*','--cacert',str(self.cert),
            '--resolve',f"deploy.example:{self.backends['sub']}:127.0.0.1",'--max-time','15',
            f"https://deploy.example:{self.backends['sub']}/subscription/{peer['subId']}"],timeout=20)
        if not raw.startswith(b'vpn://'):
            raw = base64.b64decode(raw)
        links = [line for line in raw.decode().splitlines() if line.startswith('vpn://')]
        self.assertEqual(len(links),1,'Expected one actual AWG client export')
        payload = links[0][6:]
        text = base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)).decode()
        exported = configparser.ConfigParser(interpolation=None); exported.read_string(text)
        self.assertEqual(exported['Peer']['Endpoint'],f'deploy.example:{awg_port}')
        self.assertTrue(exported['Peer']['PublicKey'] == parameters['publicKey'],'AWG export key mismatch')
        self.assertTrue(exported['Interface']['PrivateKey'] == peer['privateKey'],'AWG client key mismatch')
        self.assertTrue(exported['Interface']['HeaderProtectionKey'] == parameters['headerProtectionKey'],
                        'AWG 3.1 export mismatch')
        client_root = self.root/'awg-client'; client_root.mkdir()
        for name in ('db','bin','logs'): (client_root/name).mkdir()
        shutil.copyfile(self.xray,client_root/'bin'/self.xray.name)
        (client_root/'bin'/self.xray.name).chmod(0o755)
        client_env = {**os.environ,'XUI_DB_FOLDER':str(client_root/'db'),
            'XUI_BIN_FOLDER':str(client_root/'bin'),'XUI_LOG_FOLDER':str(client_root/'logs')}
        panel_port,socks = port(self.allocated_ports),port(self.allocated_ports)
        subprocess.run([self.xui,'setting','-username','fixture','-password',self.auth,
            '-port',str(panel_port),'-webBasePath','fixture'],env=client_env,
            check=True,stdout=subprocess.DEVNULL,timeout=30)
        obfuscation = {k:v for k,v in parameters.items() if k not in
                      ('privateKey','publicKey','subnetIp','subnetCidr','primaryDns','secondaryDns')}
        outbound = {**obfuscation,'secretKey':peer['privateKey'],'address':peer['allowedIPs'],
            'peers':[{'publicKey':parameters['publicKey'],'allowedIPs':['0.0.0.0/0'],
                      'endpoint':f'127.0.0.1:{awg_port}'}]}
        template = {'log':{'loglevel':'warning'},'inbounds':[{'listen':'127.0.0.1','port':socks,
            'protocol':'socks','settings':{'auth':'noauth','udp':True}}],
            'outbounds':[{'tag':'awg-test','protocol':'amneziawg','settings':outbound}]}
        with sqlite3.connect(client_root/'db/x-ui.db') as db:
            for key,value in {'webListen':'127.0.0.1','xrayTemplateConfig':json.dumps(template)}.items():
                db.execute('DELETE FROM settings WHERE key=?',(key,))
                db.execute('INSERT INTO settings(key,value) VALUES(?,?)',(key,value))
        client = self.launch([self.xui],'awg-client',client_env)
        self.ready(client,('127.0.0.1',socks))
        def transfer():
            result = subprocess.run(['curl','-fsS','--noproxy','','--max-time','20',
                '--socks5-hostname',f'127.0.0.1:{socks}',f'http://198.18.0.1:{self.origin.server_port}/awg'],
                capture_output=True,timeout=25)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout,self.marker.encode())
            with socket.create_connection(('127.0.0.1',socks),timeout=5) as control:
                control.sendall(b'\x05\x01\x00'); self.assertEqual(control.recv(2),b'\x05\x00')
                control.sendall(b'\x05\x03\x00\x01'+socket.inet_aton('127.0.0.1')+b'\x00\x00')
                response = control.recv(10); self.assertEqual(response[:4],b'\x05\x00\x00\x01')
                relay = (socket.inet_ntoa(response[4:8]),int.from_bytes(response[8:10],'big'))
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as tunnel:
                    tunnel.settimeout(20)
                    prefix = b'\x00\x00\x00\x01'+socket.inet_aton('198.18.0.1')+udp_port.to_bytes(2,'big')
                    tunnel.sendto(prefix+self.marker.encode(),relay)
                    data,_ = tunnel.recvfrom(65536)
                    self.assertEqual(data[10:],self.marker.encode())
        transfer()
        self.client('hysteria2',server_log='awg-panel-active.log')  # Existing UDP/443 profile still transfers while AWG is active.
        # Reconnect with a fresh client session after the server loses volatile WG sessions.
        stop(client)
        stop(server); self.release_subscription_socket()
        server = self.launch([self.xui],'awg-panel-restarted',env)
        self.ready(server,udp_port=awg_port,udp_address="0.0.0.0")
        client = self.launch([self.xui],"awg-client-reconnected",client_env)
        self.ready(client,("127.0.0.1",socks))
        transfer()
        with sqlite3.connect(self.root/'db/x-ui.db') as db:
            self.assertTrue(json.loads(db.execute('SELECT settings FROM inbounds WHERE id=?',
                (inbound['id'],)).fetchone()[0]) == settings,'AWG state changed after panel restart')
            self.assertEqual(db.execute('PRAGMA quick_check').fetchone(),('ok',))
        # Wrong header protection is a genuine cryptographic negative, with no retries.
        stop(client)
        outbound['headerProtectionKey'] = base64.b64encode(os.urandom(32)).decode()
        with sqlite3.connect(client_root/'db/x-ui.db') as db:
            db.execute("UPDATE settings SET value=? WHERE key='xrayTemplateConfig'",(json.dumps(template),))
        client = self.launch([self.xui],'awg-client-invalid',client_env)
        self.ready(client,('127.0.0.1',socks))
        before = len(self.origin_requests)
        result = subprocess.run(['curl','-fsS','--noproxy','','--max-time','8','--socks5-hostname',
            f'127.0.0.1:{socks}',f'http://198.18.0.1:{self.origin.server_port}/awg-negative'],
            capture_output=True,timeout=12)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(len(self.origin_requests),before,'Bad AWG key reached origin')
        self.passed.append('AWG TCP/UDP/restart/negative')

    def test_subscription_handoff_removes_only_inactive_private_socket(self):
        from unittest.mock import patch
        original_stop = stop
        fixture = RealIntegration('test_xhttp')
        def leave_inactive_socket(process):
            original_stop(process)
            self.assertEqual(fixture.uds, fixture.root/'xhttp.sock')
            table = subprocess.check_output(['ss','-H','-xlpn'],text=True,timeout=2)
            self.assertFalse(any(str(fixture.uds) in line.split() for line in table.splitlines()))
            if not fixture.uds.exists():
                with socket.socket(socket.AF_UNIX) as old:
                    old.bind(str(fixture.uds))
            self.assertTrue(fixture.uds.is_socket())
        try:
            with patch(__name__+'.stop',side_effect=leave_inactive_socket):
                fixture.setUp()
            self.assertFalse(fixture.uds.exists(),'Stopped subscription backend left its private UDS')
        finally:
            fixture.doCleanups()
        # An active private socket must be retained, not unlinked to make Xray start.
        with socket.socket(socket.AF_UNIX) as active:
            active.bind(str(self.uds)); active.listen(1)
            with self.assertRaisesRegex(AssertionError,'active subscription UDS'):
                self.release_subscription_socket()
            self.assertTrue(self.uds.is_socket())
            with socket.socket(socket.AF_UNIX) as probe:
                probe.connect(str(self.uds))
        self.uds.unlink()

    def grpc_fragmented(self, direct, count):
        if not direct: self.nginx_config()
        server = self.launch([self.xray,'run','-c',self.root/'server.json'],'xray-server')
        self.ready(server,('127.0.0.1',self.backends['trojan-grpc']))
        raw_link = next(urlsplit(line) for line in base64.b64decode(self.raw).decode().splitlines()
                        if urlsplit(line).scheme == 'trojan')
        query = parse_qs(raw_link.query)
        for consumer in ('JSON','RAW') if not direct else ('JSON',):
            config = copy.deepcopy(self.clients['trojan-grpc'])
            outbound = next(o for o in config['outbounds'] if o['protocol']=='trojan')
            endpoint, stream = outbound['settings']['servers'][0], outbound['streamSettings']
            if consumer == 'RAW':
                self.assertEqual(query['type'],['grpc'])
                self.assertEqual((raw_link.hostname,raw_link.port),('deploy.example',443))
                self.assertEqual(raw_link.username,endpoint['password'])
                self.assertEqual(query['serviceName'],[stream['grpcSettings']['serviceName']])
                endpoint['password'] = raw_link.username
                stream['grpcSettings']['serviceName'] = query['serviceName'][0]
            endpoint.update(address='127.0.0.1',port=self.backends['trojan-grpc'] if direct else self.public)
            if direct:
                stream['security']='none'; stream.pop('tlsSettings',None)
            else:
                stream['tlsSettings'].update(serverName='deploy.example',allowInsecure=False,
                                             certificates=[{'certificateFile':str(self.cert),'usage':'verify'}])
            socks = port(self.allocated_ports)
            config['inbounds']=[{'listen':'127.0.0.1','port':socks,'protocol':'socks','settings':{'auth':'noauth'}}]
            config['outbounds']=[outbound]; config.pop('routing',None); config.pop('dns',None)
            path = self.validate(config,'fragmented-'+consumer)
            client = self.launch([self.xray,'run','-c',path],'fragmented-'+consumer)
            self.ready(client,('127.0.0.1',socks))
            try:
                for iteration in range(count if direct else count//2):
                    nonce = '/'+consumer+'-'+str(iteration)+'-'+os.urandom(8).hex()
                    def exact(connection,size):
                        data=b''
                        while len(data)<size:
                            chunk=connection.recv(size-len(data))
                            if not chunk: raise EOFError('SOCKS handshake EOF')
                            data+=chunk
                        return data
                    with socket.create_connection(('127.0.0.1',socks),timeout=5) as connection:
                        connection.settimeout(15)
                        connection.sendall(b'\x05\x01\x00')
                        self.assertEqual(exact(connection,2),b'\x05\x00')
                        connection.sendall(b'\x05\x01\x00\x01'+socket.inet_aton('127.0.0.1')+
                                           self.origin.server_port.to_bytes(2,'big'))
                        reply=exact(connection,4); self.assertEqual(reply[:2],b'\x05\x00')
                        exact(connection,4 if reply[3]==1 else 16 if reply[3]==4 else exact(connection,1)[0])
                        exact(connection,2)
                        connection.sendall(f'GET {nonce} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n'.encode())
                        received=b''
                        while chunk:=connection.recv(65536): received+=chunk
                    # Save the unparsed response before any assertion/HTTP interpretation.
                    (self.root/'fragmented-received.bin').write_bytes(received)
                    expected=self.origin_responses[nonce]
                    (self.root/'fragmented-expected.bin').write_bytes(expected)
                    self.assertEqual(received,expected,f'{consumer} fragmented iteration {iteration+1}')
                    self.assertEqual(self.origin_requests.count(nonce),1)
            finally: stop(client)
        self.passed.append(f'gRPC fragmented {"direct" if direct else "nginx RAW/JSON"}: {count}')

    def test_grpc_fragmented_full(self): self.grpc_fragmented(False,100)
    def test_grpc_fragmented_direct(self): self.grpc_fragmented(True,50)
    def test_hysteria2(self):
        self.transport('hysteria2')
        self.assertIn(f'dialing to udp:127.0.0.1:{self.hysteria_port}',
                      (self.root/'hysteria2-client.log').read_text())
        # Actual Xray Hysteria configuration is UDP; no TCP listener may substitute it.
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1',self.hysteria_port),timeout=0.3)

    def test_public_subscription_semantics(self):
        raw=base64.b64decode(self.raw,validate=True).decode()
        links=[urlsplit(line) for line in raw.splitlines() if line]
        self.assertEqual(len(links),5)
        for link in links:
            self.assertIn(link.scheme,('vless','trojan','hysteria2'))
            self.assertEqual((link.hostname,link.port),('deploy.example',443))
            self.assertTrue(link.username == (self.uuid if link.scheme=='vless' else self.auth), 'public credential mismatch')
            query=parse_qs(link.query)
            if link.scheme == 'vless': self.assertEqual(query.get('encryption'),['none'])
            self.assertIn(query.get('sni',[link.hostname])[0] or link.hostname,('deploy.example','cover.example'))
            if query.get('security')==['reality']:
                self.assertEqual(query['pbk'],[self.public_key]);self.assertIn(query['sid'][0],json.loads(self.rows['reality']['stream_settings'])['realitySettings']['shortIds'])
            if query.get('type')==['ws']: self.assertEqual(query['path'],['/10003/websocket'])
            if query.get('type')==['xhttp']: self.assertEqual(query['path'],['/Session7AbC'])
            if query.get('type')==['grpc']: self.assertEqual(query['serviceName'],['/10004/trojan|trojan-multi'])
        for name, config in self.clients.items():
            outbound=next(o for o in config['outbounds'] if o['protocol'] in ('vless','trojan','hysteria'))
            settings=outbound['settings'];stream=outbound['streamSettings']
            endpoint=settings['servers'][0] if 'servers' in settings else settings
            self.assertEqual((endpoint['address'],endpoint['port']),('deploy.example',443))
            if outbound['protocol']=='vless':
                self.assertTrue(settings['id']==self.uuid,'JSON UUID mismatch')
                self.assertEqual(settings['encryption'],'none')
            if name=='reality':
                reality=stream['realitySettings']
                self.assertEqual(reality['serverName'],'cover.example')
                self.assertTrue(reality['publicKey']==self.public_key,'REALITY public key mismatch')
                self.assertIn(reality['shortId'],self.short_ids)
                self.assertEqual(reality['fingerprint'],'firefox')
                self.assertEqual(settings['flow'],'xtls-rprx-vision')
            else:
                self.assertEqual(stream['tlsSettings'].get('serverName') or endpoint['address'],'deploy.example')
                if name=='ws':
                    self.assertEqual(stream['network'],'ws')
                    self.assertEqual(stream['wsSettings']['path'],'/10003/websocket')
                    self.assertEqual(stream['tlsSettings']['alpn'],['http/1.1'])
                elif name=='xhttp':
                    self.assertEqual(stream['network'],'xhttp')
                    self.assertEqual(stream['xhttpSettings']['path'],'/Session7AbC')
                    self.assertEqual(stream['xhttpSettings']['mode'],'stream-up')
                elif name=='trojan-grpc':
                    self.assertEqual(stream['network'],'grpc')
                    self.assertEqual(stream['grpcSettings']['serviceName'],'/10004/trojan|trojan-multi')
                    self.assertIs(stream['grpcSettings']['multiMode'],False)
                    self.assertTrue(endpoint['password']==self.auth,'JSON Trojan credential mismatch')
                else:
                    self.assertEqual(stream['network'],'hysteria')
                    self.assertEqual(settings['version'],2)
                    self.assertTrue(stream['hysteriaSettings']['auth']==self.auth,'JSON Hysteria credential mismatch')
                    self.assertEqual(stream['tlsSettings']['alpn'],['h3'])
        self.passed.append('Subscription semantics')

    def test_public_outputs_do_not_leak_internal_endpoints(self):
        raw=base64.b64decode(self.raw,validate=True).decode()
        # Public outbound endpoints only: local SOCKS inbounds are legal client state.
        provider=base64.b64decode(self.provider,validate=True).decode()
        self.assertEqual(len(provider.splitlines()),5)
        for link in (urlsplit(line) for output in (raw,provider) for line in output.splitlines()):
            self.assertEqual((link.hostname,link.port),('deploy.example',443))
        public_values=[raw,provider]
        for config in self.client_configs:
            for outbound in config['outbounds']:
                if outbound['protocol'] in ('vless','trojan','hysteria'):
                    public_values.append(json.dumps(outbound))
        for output in public_values:
            for forbidden in ('127.0.0.1','localhost','/dev/shm/','uds2023.sock'):
                self.assertNotIn(forbidden,output)
            internal_ports = {str(p) for p in self.backends.values()} | {'8443','7443','9443'}
            internal_ports.update(FIXTURE[k] for k in ('panel_port','sub_port','mtr_backend_port','ws_port','trojan_port'))
            for internal in internal_ports:
                # Numeric WS/gRPC path components are the public managed route, not endpoint ports.
                self.assertNotRegex(output,rf'(?:\"port\"\s*:\s*|:){internal}(?:\D|$)')
        self.passed.append('No internal endpoint leak')

    def test_real_mihomo_generated_template(self):
        # Execute the actual project endpoint that substitutes the subscription ID.
        template=self.root/'clash.yaml.tpl'
        template.write_text((ROOT/'assets/clash/clash.yaml').read_text().replace('${DOMAIN}','deploy.example').replace('${SUB_PATH}','subscription'))
        source=(ROOT/'assets/diagnostics/mtr-backend.py').read_text().replace('"/var/www/subpage/clash.yaml.tpl"',repr(str(template)))
        namespace={'__name__':'integration_clash'}
        exec(compile(source,'mtr-backend.py','exec'),namespace)
        server=ThreadingHTTPServer(('127.0.0.1',0),namespace['Handler'])
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        yaml=subprocess.check_output(['curl','-fsS','--noproxy','*','--max-time','10',f'http://127.0.0.1:{server.server_port}/api/clash?sub_id=fixture'],timeout=15)
        self.assertNotIn(b'${',yaml);self.assertIn(b'https://deploy.example/subscription/fixture?provider=1',yaml)
        path=self.root/'mihomo.yaml';path.write_bytes(yaml)
        result=subprocess.run([self.mihomo,'-t','-d',self.root/'mihomo-state','-f',path],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        # provider=1 intentionally returns base64 URIs, not a standalone YAML config.
        self.assertEqual(len(base64.b64decode(self.provider,validate=True).decode().splitlines()),5)
        self.passed.append('Mihomo validation')
        self.nginx_config()
        xray=self.launch([self.xray,'run','-c',self.root/'server.json'],'mihomo-xray')
        self.ready(xray,('127.0.0.1',self.backends['trojan-grpc']))
        # The real x-ui provider remains the input; only public test endpoints are relocated.
        provider=base64.b64decode(self.provider,validate=True).decode()
        self.assertEqual(provider.count('@deploy.example:443'),5)
        payload=base64.b64encode(provider.replace('@deploy.example:443',f'@deploy.example:{self.public}').encode())
        class Provider(BaseHTTPRequestHandler):
            def do_GET(handler):
                handler.send_response(200); handler.send_header('Content-Length',str(len(payload)))
                handler.end_headers(); handler.wfile.write(payload)
            def log_message(handler,*args): pass
        provider_server=ThreadingHTTPServer(('127.0.0.1',0),Provider)
        threading.Thread(target=provider_server.serve_forever,daemon=True).start()
        self.addCleanup(provider_server.server_close);self.addCleanup(provider_server.shutdown)
        expression='(select(.network == "grpc") | .["grpc-opts"]["grpc-service-name"]) |= (split("|") | .[0])'
        snapshots=[]
        for enabled in (False,True):
            socks,controller=port(self.allocated_ports),port(self.allocated_ports)
            # Keep the actual generated template/provider overrides/groups. Replace external DNS/rules
            # and automatic probes only in this offline fixture, forcing the selected provider route.
            runtime=yaml.decode()
            for section in ('dns','rule-providers','rules'):
                runtime=re.sub(r'^'+section+r':.*?(?=^[A-Za-z][^\n]*:|\Z)','',runtime,flags=re.M|re.S)
            runtime=runtime.replace('mixed-port: 10000',f'mixed-port: {socks}').replace('allow-lan: true','allow-lan: false')
            runtime=runtime.replace('https://deploy.example/subscription/fixture?provider=1',
                                    f'http://127.0.0.1:{provider_server.server_port}/provider')
            runtime=runtime.replace('      enable: true','      enable: false').replace('    type: url-test','    type: select')
            runtime=re.sub(r'(url: )https://(?:www.gstatic.com|cp.cloudflare.com)/generate_204',
                           rf'\g<1>http://127.0.0.1:{self.origin.server_port}/health',runtime)
            if not enabled:
                runtime=runtime.replace("        - '"+expression+"'\n",'')
            # Read the *actual post-override mapping* through a harmless test-only name export.
            # Both variants use the same export. No test-side subscription/YAML proxy generator.
            runtime=runtime.replace('    health-check:',"        - '.name = tostring'\n    health-check:",1)
            runtime+=f'\nexternal-controller: 127.0.0.1:{controller}\nbind-address: 127.0.0.1\nrules:\n  - MATCH,🌍 VPN\n'
            runtime+='hosts:\n  deploy.example: 127.0.0.1\n'
            runtime+='tls:\n  custom-certifactes:\n    - '+json.dumps(self.cert.read_text())+'\n'
            path=self.root/f'mihomo-{enabled}.yaml';path.write_text(runtime)
            process=self.launch([self.mihomo,'-d',self.root/f'mihomo-{enabled}','-f',path],f'mihomo-{enabled}')
            self.ready(process,('127.0.0.1',controller));self.ready(process,('127.0.0.1',socks))
            def api(route,body=None):
                args=['curl','-fsS','--noproxy','*','--max-time','10']
                if body is not None: args+=['-X','PUT','--data-binary','@-','-H','Content-Type: application/json']
                return subprocess.check_output(args+[f'http://127.0.0.1:{controller}'+route],
                                               input=json.dumps(body).encode() if body is not None else None,timeout=15)
            deadline=time.monotonic()+15
            while True:
                proxies=json.loads(api('/providers/proxies/sub'))['proxies']
                if proxies: break
                self.assertIsNone(process.poll(),'Mihomo exited before provider readiness')
                if time.monotonic()>=deadline:
                    log=(self.root/f'mihomo-{enabled}.log').read_text().replace(self.auth,'[redacted]').replace(self.uuid,'[redacted]')
                    self.fail('Mihomo provider readiness deadline expired: '+log[-3000:])
                time.sleep(0.05)
            self.assertEqual(len(proxies),5)
            mappings={p['name'].split('\nname: ',1)[-1].split('\n',1)[0]:p['name'] for p in proxies}
            snapshots.append(mappings)
            grpc=next(p['name'] for p in proxies if 'type: trojan' in p['name'])
            api('/proxies/'+quote('🌍 VPN',safe=''),{'name':grpc})
            try:
                for iteration in range(10 if enabled else 1):
                    nonce='/mihomo-'+str(enabled)+'-'+str(iteration)+'-'+os.urandom(8).hex()
                    with socket.create_connection(('127.0.0.1',socks),timeout=5) as connection:
                        connection.settimeout(15)
                        def exact(size):
                            data=b''
                            while len(data)<size:
                                chunk=connection.recv(size-len(data))
                                if not chunk: raise EOFError('Mihomo SOCKS handshake EOF')
                                data+=chunk
                            return data
                        connection.sendall(b'\x05\x01\x00');self.assertEqual(exact(2),b'\x05\x00')
                        connection.sendall(b'\x05\x01\x00\x01'+socket.inet_aton('127.0.0.1')+self.origin.server_port.to_bytes(2,'big'))
                        reply=exact(4);self.assertEqual(reply[:2],b'\x05\x00')
                        exact(4 if reply[3]==1 else 16 if reply[3]==4 else exact(1)[0]);exact(2)
                        connection.sendall(f'GET {nonce} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n'.encode())
                        received=b''
                        while chunk:=connection.recv(65536): received+=chunk
                    if enabled:
                        self.assertIn(nonce,self.origin_responses,'Mihomo did not reach origin')
                        self.assertEqual(received,self.origin_responses[nonce],'Mihomo fragmented response differs')
                        self.assertEqual(self.origin_requests.count(nonce),1)
                    else:
                        self.assertNotIn(nonce,self.origin_requests,'Unmodified pipe must not reach Tun-only nginx route')
                        self.assertNotIn(self.marker.encode(),received)
            finally: stop(process)
        self.assertEqual(snapshots[0].keys(),snapshots[1].keys())
        for name,before in snapshots[0].items():
            after=snapshots[1][name]
            # Mihomo's URI converter injects a random WS User-Agent before either override.
            # Compare every supplied/profile field; normalize only that consumer-generated default.
            if 'network: ws\n' in before:
                before=re.sub(r'(?m)^        User-Agent: .+$','        User-Agent: [consumer-random]',before)
                after=re.sub(r'(?m)^        User-Agent: .+$','        User-Agent: [consumer-random]',after)
            expected=before.replace('grpc-service-name: /10004/trojan|trojan-multi','grpc-service-name: /10004/trojan') if 'type: trojan' in before else before
            self.assertTrue(after==expected,'Provider changed unrelated settings: '+name)
        self.assertTrue(any('grpc-service-name: /10004/trojan\n' in m for m in snapshots[1].values()))
        self.passed.append('Mihomo provider gRPC: 10 byte-exact responses; other profiles unchanged')
