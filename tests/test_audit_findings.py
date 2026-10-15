"""Focused v1.5 audit regressions, using the existing isolated fixtures."""
import copy
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from certificate_fixtures import relocate

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / 'x-ui-latest.sh').read_text()
BACKUP = (ROOT / 'assets/backup/x-ui-backup.sh').read_text()


def function(name, source=INSTALLER):
    # A SQL JSON value can end with }', which is not the shell function boundary.
    return re.findall(r'^' + name + r'\(\)\s*\{.*?^\}$', source, re.M | re.S)[0]


class AuditInstaller(unittest.TestCase):
    def flag(self, response, failure=False):
        script = ('curl() { cat "$RESPONSE_FILE"; return "$CURL_RESULT"; };\n' +
                  function('country_flag') + '\ncountry_flag')
        with tempfile.NamedTemporaryFile() as fixture:
            fixture.write(response.encode('utf-8') if isinstance(response,str) else response); fixture.flush()
            result = subprocess.run(['bash', '-eu', '-c', script], capture_output=True,
                                    env={**os.environ, 'LC_ALL': 'C', 'RESPONSE_FILE': fixture.name,
                                         'CURL_RESULT': '1' if failure else '0'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr,b'')
        return result.stdout.decode('utf-8')

    def test_country_iso_and_nonfatal_fallback(self):
        for code, expected in [('FI', '🇫🇮'), ('US', '🇺🇸'), ('DE', '🇩🇪')]:
            self.assertEqual(self.flag(json.dumps({'success': True, 'country_code': code})), expected)
        for payload in ('null', '[]', 'bad JSON', '{}', '{"success":false,"country_code":"FI"}'):
            self.assertEqual(self.flag(payload), '🌐')
        self.assertEqual(self.flag('{"success":true,"country_code":"FI"}', failure=True), '🌐')
        self.assertEqual(self.flag(b'{"success":true,"country_code":"\xff\xfe"}'), '🌐')

    def test_country_parser_failure_still_returns_single_fallback(self):
        # Even a parser startup/write failure must not leak partial output or fail installation.
        script = ('curl() { :; }; python3() { printf partial; echo traceback >&2; return 1; };\n' +
                  function('country_flag') + '\ncountry_flag')
        result = subprocess.run(['bash','-eu','-c',script],capture_output=True)
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stdout.decode(),'🌐')
        self.assertEqual(result.stderr,b'')

    def test_generated_panel_and_camouflage_routes_are_separate(self):
        from test_personal_xhttp import render, MAIN
        main = render(MAIN)
        reality = render('cat > "/etc/nginx/sites-available/${reality_domain}"')
        for path in ('/panel/','/panel','= /__diag_auth'):
            block = re.search(r'location ' + re.escape(path) + r' \{(.*?)\n    \}',main,re.S)
            self.assertIsNotNone(block,path)
            self.assertIn('proxy_pass https://127.0.0.1:10002',block[1])
        self.assertNotIn('location /panel',reality)
        self.assertNotIn('127.0.0.1:10002',reality)
        for item in ('listen 127.0.0.1:9443 ssl','root /var/www/html/;',
                     '/etc/letsencrypt/live/cover.example/fullchain.pem',
                     '/etc/letsencrypt/live/cover.example/privkey.pem',
                     'include /etc/nginx/snippets/includes.conf;'):
            self.assertIn(item,reality)

    def test_hostile_country_cannot_inject_sqlite_cli(self):
        self.assertIn('emoji_flag=$(country_flag)',function('configure_xui_db'))
        self.assertNotIn('.flag.emoji',function('configure_xui_db'))
        from test_personal_xhttp import render
        sqlite = shutil.which('sqlite3')
        self.assertIsNotNone(sqlite, 'sqlite3 CLI is required for the injection regression')
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'executed'
            hostile = ["FI'", 'FI\n.shell touch ' + str(marker),
                       "');\n.shell touch " + str(marker) + '\n--', '$(touch ' + str(marker) + ')']
            for value in hostile:
                with self.subTest(value=value):
                    emoji = self.flag(json.dumps({'success': True, 'country_code': value,
                                                  'flag': {'emoji': value}}))
                    self.assertEqual(emoji, '🌐')
                    sql = render('sqlite3 $XUIDB', emoji_flag=emoji)
                    blocks = re.findall(r'^INSERT INTO "inbounds"\s.*?^\);', sql, re.M | re.S)
                    columns = re.search(r'\(("user_id".*?)\)\s*VALUES', blocks[0], re.S)[1]
                    db = Path(tmp) / 'seed.db'
                    db.unlink(missing_ok=True)
                    result = subprocess.run([sqlite, str(db)], input='CREATE TABLE inbounds (id INTEGER PRIMARY KEY,' +
                                            columns + ');\n' + '\n'.join(blocks), text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    with sqlite3.connect(db) as conn:
                        self.assertEqual(conn.execute('SELECT count(*) FROM inbounds').fetchone()[0], 5)
                        self.assertTrue(all(row[0].startswith('🌐 ') for row in conn.execute('SELECT remark FROM inbounds')))
                    self.assertFalse(marker.exists())

    def test_initial_panel_loopback_persisted_before_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / 'usr/local/x-ui/x-ui'
            binary.parent.mkdir(parents=True)
            db = root / 'x-ui.db'
            with sqlite3.connect(db) as conn:
                conn.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT); CREATE TABLE settings(key TEXT,value TEXT);')
            # Model the actual setting/migrate CLI DB contract, not a fictional listen option.
            binary.write_text('''#!/usr/bin/env python3
import os,sqlite3,sys
if sys.argv[1]=='setting':
    args=sys.argv[2:]; values=dict(zip(args[::2],args[1::2]))
    with sqlite3.connect(os.environ['XUIDB']) as db:
        db.execute('INSERT INTO users(username) VALUES(?)',(values['-username'],))
        db.executemany('INSERT INTO settings VALUES(?,?)',[('webListen',''),('webPort',values['-port']),('webBasePath','/'+values['-webBasePath']+'/')])
''')
            binary.chmod(0o755)
            result = subprocess.run(['bash', '-eu', '-c', relocate(function('_panel_initial_config'), root) +
                                     '\n_panel_initial_config\n'], capture_output=True, text=True, env={
                                         **os.environ, 'XUIDB': str(db), 'config_username': 'random-user',
                                         'config_password': 'fixture-password', 'panel_port': '18443', 'panel_path': 'random-path'})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT value FROM settings WHERE key='webListen'").fetchall(), [('127.0.0.1',)])
            self.assertNotRegex(function('install_panel'), r'systemctl\s+(?:start|restart)\s+x-ui')
            self.assertIn("'127.0.0.1'", function('configure_xui_db'))

    def test_final_tls_settings_include_upstream_cert_side_effect(self):
        from test_personal_xhttp import render
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); dbpath = root/'x-ui.db'; binary = root/'x-ui'
            with sqlite3.connect(dbpath) as db:
                db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
                db.executescript(render('sqlite3 $XUIDB').split('INSERT INTO "inbounds"',1)[0])
                self.assertEqual(db.execute("SELECT value FROM settings WHERE key='subCertFile'").fetchone()[0],'')
            # Exact v3.9.0 main.go updateCert: both web AND sub setters receive these paths.
            # https://github.com/MHSanaei/3x-ui/blob/v3.9.0/main.go#L429
            binary.write_text('''#!/usr/bin/env python3
import os,sqlite3,sys
if sys.argv[1]=='cert':
    args=sys.argv[2:]; values=dict(zip(args[::2],args[1::2]))
    with sqlite3.connect(os.environ['XUIDB']) as db:
        for key,flag in [('webCertFile','-webCert'),('webKeyFile','-webCertKey'),
                         ('subCertFile','-webCert'),('subKeyFile','-webCertKey')]:
            db.execute('UPDATE settings SET value=? WHERE key=?',(values[flag],key))
''')
            binary.chmod(0o755)
            tail = function('configure_xui_db').split('    /usr/local/x-ui/x-ui setting',1)[1]
            script = 'finalize() {\n    /usr/local/x-ui/x-ui setting' + tail + '\nfinalize\n'
            result = subprocess.run(['bash','-eu','-c',script.replace('/usr/local/x-ui/x-ui',str(binary))],
                                    capture_output=True,text=True,env={**os.environ,'XUIDB':str(dbpath),
                                    'domain':'example.com','config_username':'fixture-user','config_password':'fixture-password',
                                    'panel_port':'10002','panel_path':'panel'})
            self.assertEqual(result.returncode,0,result.stderr)
            with sqlite3.connect(dbpath) as db: values = dict(db.execute('SELECT key,value FROM settings'))
            for prefix in ('web','sub'):
                self.assertEqual(values[prefix+'Listen'],'127.0.0.1')
                self.assertEqual(values[prefix+'CertFile'],'/root/cert/example.com/fullchain.pem')
                self.assertEqual(values[prefix+'KeyFile'],'/root/cert/example.com/privkey.pem')
            for name in ('install_panel','_panel_initial_config','configure_xui_db'):
                self.assertNotRegex(function(name),r'(?:x-ui\s+(?:start|restart)|systemctl\s+(?:start|restart)\s+x-ui)')
            self.assertLess(function('main').index('configure_xui_db'),function('main').index('x-ui restart'))
            hook = function('render_certificate_hook')
            self.assertIn('systemctl try-restart x-ui',hook)

    def test_fresh_json_subscription_replaces_upstream_seed(self):
        from test_personal_xhttp import render
        setup = re.search(r'^    local json_uri=.*$',function('configure_xui_db'),re.M)[0]
        uri = subprocess.check_output(['bash','-eu','-c',
                                      'emit() {\n' + setup + '\nprintf "%s" "$json_uri"; }; emit'],
                                     text=True,env={**os.environ,'domain':'example.com','json_path':'jsonsub'})
        self.assertEqual(uri,'https://example.com/jsonsub/')
        self.assertNotIn('?name=',function('configure_xui_db'))
        for previous in (None,'false','true'):
            with self.subTest(previous=previous), sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
                db.execute("INSERT INTO settings VALUES('subPath','/sub/')")
                if previous is not None:
                    db.executemany('INSERT INTO settings VALUES(?,?)',[
                        ('subJsonEnable',previous),('subJsonPath','/upstream/'),('subJsonURI','old')])
                db.executescript(render('sqlite3 $XUIDB',json_uri=uri).split('INSERT INTO "inbounds"',1)[0])
                values = dict(db.execute('SELECT key,value FROM settings'))
                self.assertEqual(values['subJsonEnable'],'true')
                self.assertEqual(values['subJsonPath'],'/jsonsub/')
                self.assertEqual(values['subJsonURI'],uri)
                self.assertEqual(values['subEnable'],'true')
                self.assertEqual(values['subPath'],'/subscription/')
                self.assertEqual(values['subURI'],'https://deploy.example/subscription/')
                self.assertEqual(values['subClashEnable'],'false')
                self.assertNotIn('subJsonAutoDetect',values)

    def test_xray_health_requires_live_sockets_and_managed_same_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executable = root / 'usr/local/x-ui/bin/xray-linux-amd64'
            executable.parent.mkdir(parents=True)
            shutil.copy2(shutil.which('sleep'), executable)
            proc = subprocess.Popen([str(executable), '60'])
            self.addCleanup(lambda: proc.wait())
            self.addCleanup(proc.terminate)
            sockpath = root / 'dev/shm/uds2023.sock'
            sockpath.parent.mkdir(parents=True)
            sock = socket.socket(socket.AF_UNIX); sock.bind(str(sockpath)); sock.close()
            # The inode remains, but all health evidence comes from ss and /proc/exe.
            pid = proc.pid
            tcp = f'tcp LISTEN 0 128 127.0.0.1:8443 *:* users:(("xray",pid={pid},fd=2))'
            udp = f'udp UNCONN 0 128 *:443 *:* users:(("xray",pid={pid},fd=3))'
            unix = f'u_str LISTEN 0 128 {sockpath} 0 users:(("xray",pid={pid},fd=4))'
            body = function('check_xray_runtime').replace('/usr/local/x-ui/bin', str(executable.parent)).replace('/dev/shm/uds2023.sock', str(sockpath))
            ss = root / 'ss'
            ss.write_text('#!/bin/sh\nif [ "$2" = -lxnp ]; then printf "%s\\n" "$UNIX"; else printf "%s\\n" "$NETWORK"; fi\n')
            ss.chmod(0o755)
            script = ('systemctl() { return 0; }; sleep() { :; };\n' + body + '\ncheck_xray_runtime\n')
            cases = [(tcp + '\n' + udp, unix, True), ('', '', False), (udp, unix, False),
                     (tcp, unix, False), (tcp + '\n' + udp, '', False),
                     (tcp + '\n' + udp.replace(f'pid={pid}', 'pid=1'), unix, False)]
            for network, uds, expected in cases:
                with self.subTest(network=network, unix=uds):
                    result = subprocess.run(['bash', '-eu', '-c', script], text=True, capture_output=True,
                                            env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'], 'NETWORK': network, 'UNIX': uds})
                    self.assertEqual(result.returncode == 0, expected, result.stderr)
                    self.assertTrue(sockpath.exists())

    def test_canonical_health_used_after_restart_resume_and_rollback(self):
        self.assertEqual(function('check_xray_runtime'), function('check_xray_runtime', BACKUP))
        self.assertEqual(function('render_certificate_hook'), function('render_certificate_hook', BACKUP))
        self.assertIn('check_xray_runtime', function('check_installation', INSTALLER))
        for name in ('check_health','cmd_backup','cleanup','recover_restore_target'):
            self.assertNotIn('check_xray_runtime', function(name, BACKUP))
            self.assertIn('systemctl is-active', function(name, BACKUP))
        # Historical renderings retain exact bytes; the deployed current hook does not.
        from certificate_fixtures import certificates
        with tempfile.TemporaryDirectory() as directory:
            hook=certificates(Path(directory)).read_text()
            self.assertNotIn('check_xray_runtime',hook)
            self.assertNotIn('RENEWED_DOMAINS',hook)

    def test_panel_renewal_fails_when_xray_does_not_resume(self):
        from certificate_fixtures import certificates
        from test_certificate_renewal import CertificateRenewal, MOCK
        f = CertificateRenewal('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        hook = certificates(f.root)
        (f.root/'health-bin/ss').write_text('#!/bin/sh\nexit 0\n')
        result = subprocess.run(['bash','-c',MOCK+'\nsleep() { :; }; source "$HOOK"'],
                                capture_output=True,text=True,env={**f.env,'HOOK':str(hook),
                                'RENEWED_DOMAINS':'example.com','RENEWED_LINEAGE':str(f.root/'etc/letsencrypt/live/example.com')})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('Xray must own',result.stderr)
        result,calls=f.deploy(hook,FAIL_DEPLOY='try-restart x-ui',
            RENEWED_LINEAGE=str(f.root/'etc/letsencrypt/live/example.com'))
        self.assertNotEqual(result.returncode,0)
        self.assertIn('systemctl try-restart x-ui',calls)

    def test_real_nginx_verified_https_api_token_and_tls_subscriptions(self):
        from test_personal_xhttp import render, SHARED, MAIN
        nginx = os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertIsNotNone(nginx, 'real nginx is required')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                            '-subj','/CN=deploy.example','-addext','subjectAltName=DNS:deploy.example,DNS:cover.example',
                            '-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            requests = []
            with sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
                db.execute("INSERT INTO settings VALUES('subPath','/sub/')")
                db.executescript(render('sqlite3 $XUIDB').split('INSERT INTO "inbounds"',1)[0])
                settings = dict(db.execute('SELECT key,value FROM settings'))
            class Backend(BaseHTTPRequestHandler):
                def do_GET(self):
                    requests.append((self.server.kind, self.path, self.headers.get('Authorization'), self.headers.get('Host')))
                    # Model the exact v3.9.0 enabled JSON :subid route, not an unconditional 200.
                    if self.server.kind == 'sub-https':
                        path = urlsplit(self.path).path
                        if path.startswith('/jsonsub'):
                            if settings['subJsonEnable'] != 'true' or path != settings['subJsonPath'] + 'fixture':
                                self.send_error(404); return
                        elif path != settings['subPath'] + 'fixture':
                            self.send_error(404); return
                    body = json.dumps({'backend':self.server.kind,'path':self.path}).encode()
                    self.send_response(200); self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
                def log_message(self, *args): pass
            panel = ThreadingHTTPServer(('127.0.0.1',0), Backend); panel.kind = 'panel-https'
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(root/'cert.pem',root/'key.pem')
            panel.socket = tls.wrap_socket(panel.socket, server_side=True)
            sub = ThreadingHTTPServer(('127.0.0.1',0), Backend); sub.kind = 'sub-https'
            sub.socket = tls.wrap_socket(sub.socket, server_side=True)
            # Run the actual local Clash generator against its actual installed template.
            tpl = root/'clash.yaml.tpl'
            tpl.write_text((ROOT/'assets/clash/clash.yaml').read_text().replace('${DOMAIN}','deploy.example')
                           .replace('${SUB_PATH}','subscription'))
            backend_source = (ROOT/'assets/diagnostics/mtr-backend.py').read_text()
            namespace = {'__name__':'clash_fixture'}
            exec(compile(backend_source.replace('"/var/www/subpage/clash.yaml.tpl"',repr(str(tpl))),
                         'mtr-backend-fixture.py','exec'),namespace)
            clash = ThreadingHTTPServer(('127.0.0.1',0),namespace['Handler'])
            for server in (panel, sub, clash):
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
            with socket.socket() as s, socket.socket() as r:
                s.bind(('127.0.0.1',0)); public_port = s.getsockname()[1]
                r.bind(('127.0.0.1',0)); reality_port = r.getsockname()[1]
            shared = render(SHARED, panel_port=str(panel.server_port), sub_port=str(sub.server_port))
            self.assertEqual(shared.count(f'proxy_pass https://127.0.0.1:{sub.server_port};'),7)
            self.assertNotIn(f'proxy_pass http://127.0.0.1:{sub.server_port};',shared)
            (root/'includes.conf').write_text(shared)
            vhost = render(MAIN, panel_port=str(panel.server_port), sub_port=str(sub.server_port),
                           mtr_backend_port=str(clash.server_port))
            self.assertIn(f'proxy_pass https://127.0.0.1:{panel.server_port};',vhost)
            # Fixture direct TLS entry bypasses only the outer stream/proxy-protocol hop.
            vhost = re.sub(r'127\.0\.0\.1:7443 ssl(?: http2)? proxy_protocol', f'127.0.0.1:{public_port} ssl', vhost)
            vhost = re.sub(r'/etc/letsencrypt/live/[^/]+/fullchain.pem', str(root/'cert.pem'), vhost)
            vhost = re.sub(r'/etc/letsencrypt/live/[^/]+/privkey.pem', str(root/'key.pem'), vhost)
            vhost = vhost.replace('/etc/nginx/snippets/includes.conf',str(root/'includes.conf')).replace('/etc/nginx/snippets/x-ui-auto-optional',str(root/'optional'))
            reality = render('cat > "/etc/nginx/sites-available/${reality_domain}"',
                             panel_port=str(panel.server_port), sub_port=str(sub.server_port))
            reality = re.sub(r'127\.0\.0\.1:9443 ssl(?: http2)?', f'127.0.0.1:{reality_port} ssl', reality)
            reality = re.sub(r'/etc/letsencrypt/live/[^/]+/fullchain.pem', str(root/'cert.pem'), reality)
            reality = re.sub(r'/etc/letsencrypt/live/[^/]+/privkey.pem', str(root/'key.pem'), reality)
            reality = reality.replace('/etc/nginx/snippets/includes.conf',str(root/'includes.conf')).replace('/var/www/html/',str(root/'site')+'/')
            (root/'site').mkdir(); (root/'site/index.html').write_text('camouflage')
            maps = render('cat > /etc/nginx/sites-available/00-maps.conf')
            temp_paths = '\n'.join(f'{kind}_temp_path {root}/{kind};'
                                   for kind in ('client_body', 'proxy', 'fastcgi', 'uwsgi', 'scgi'))
            (root/'nginx.conf').write_text(f'pid {root}/nginx.pid; error_log {root}/error.log; events {{}} http {{ access_log off; {temp_paths}\n{maps}\n{vhost}\n{reality}\n}}')
            cmd = [nginx,'-p',str(root)+'/', '-c',str(root/'nginx.conf')]
            syntax = subprocess.run([*cmd,'-t'],capture_output=True,text=True)
            self.assertEqual(syntax.returncode,0,syntax.stderr)
            process = subprocess.Popen([*cmd,'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.addCleanup(lambda: process.wait()); self.addCleanup(process.terminate)
            for _ in range(50):
                try:
                    with socket.create_connection(('127.0.0.1', public_port), timeout=.1): break
                except OSError: time.sleep(.02)
            for path, kind in [('/panel/panel/api/inbounds/list?node=Fixture&token=query','panel-https'),
                               ('/subscription/fixture','sub-https'),('/jsonsub/fixture','sub-https'),
                               ('/subscription/fixture?provider=1','sub-https')]:
                result = subprocess.run(['curl','--noproxy','*','-fsS','--max-time','5',
                                         '--cacert',str(root/'cert.pem'),'--resolve',f'deploy.example:{public_port}:127.0.0.1',
                                         '-H','Authorization: Bearer fixture-api-token',f'https://deploy.example:{public_port}{path}'],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads(result.stdout), {'backend':kind,'path':path})
                self.assertEqual(requests[-1], (kind,path,'Bearer fixture-api-token','deploy.example'))
            # Clash/Mihomo gets the full template; its provider URL must bypass that rewrite.
            for user_agent in ('Clash','Mihomo'):
                before = list(requests)
                result = subprocess.run(['curl','--noproxy','*','-fsS','--max-time','5',
                                         '--cacert',str(root/'cert.pem'),'--resolve',f'deploy.example:{public_port}:127.0.0.1',
                                         '-A',user_agent,f'https://deploy.example:{public_port}/subscription/fixture'],
                                        capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,tpl.read_text().replace('${SUB_ID}','fixture'))
                self.assertIn('https://deploy.example/subscription/fixture?provider=1',result.stdout)
                self.assertEqual(requests,before)
                provider = subprocess.run(['curl','--noproxy','*','-fsS','--max-time','5',
                                           '--cacert',str(root/'cert.pem'),'--resolve',f'deploy.example:{public_port}:127.0.0.1',
                                           '-A',user_agent,f'https://deploy.example:{public_port}/subscription/fixture?provider=1'],
                                          capture_output=True,text=True)
                self.assertEqual(provider.returncode,0,provider.stderr)
                self.assertEqual(json.loads(provider.stdout),{'backend':'sub-https','path':'/subscription/fixture?provider=1'})
            for enabled, path in [('true','/jsonsub?name=fixture'),('false','/jsonsub/fixture')]:
                settings['subJsonEnable'] = enabled
                negative = subprocess.run(['curl','--noproxy','*','-sS','--max-time','5','-o','/dev/null','-w','%{http_code}',
                                           '--cacert',str(root/'cert.pem'),'--resolve',f'deploy.example:{public_port}:127.0.0.1',
                                           f'https://deploy.example:{public_port}{path}'],capture_output=True,text=True)
                self.assertEqual(negative.returncode,0,negative.stderr)
                self.assertEqual(negative.stdout,'404')
            settings['subJsonEnable'] = 'true'
            before = list(requests)
            result = subprocess.run(['curl','--noproxy','*','-sS','--max-time','5',
                                     '--cacert',str(root/'cert.pem'),'--resolve',f'cover.example:{reality_port}:127.0.0.1',
                                     '-H','Authorization: Bearer fixture-api-token',
                                     f'https://cover.example:{reality_port}/panel/panel/api/inbounds/list?node=Fixture'],
                                    capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(requests,before,'camouflage request reached a managed backend')
            errors = (root/'error.log').read_text().lower()
            for error in ('wrong version number','ssl_do_handshake() failed','unsupported http version'):
                self.assertNotIn(error,errors)


class AuditRecovery(unittest.TestCase):
    def setUp(self):
        from test_personal_backup import PersonalBackup
        self.fixture = PersonalBackup('runTest'); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.env['NGINX_BIN'] = os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.fixture.write('/var/www/html/recovery-marker','original')

    def modified(self, archive, updates):
        f = self.fixture
        target = Path(f.temp.name) / ('modified-' + str(time.time_ns()) + '.tar.gz')
        with tarfile.open(archive) as src, tarfile.open(target,'w:gz') as dst:
            for entry in src:
                entry = copy.copy(entry)
                data = src.extractfile(entry).read() if entry.isfile() else None
                if entry.name in updates: data = updates[entry.name]
                if data is not None: entry.size = len(data)
                dst.addfile(entry, io.BytesIO(data) if data is not None else None)
        return target

    def assert_untouched(self, result, services):
        f = self.fixture
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(f.path('/var/www/html/recovery-marker').read_text(),'original')
        self.assertEqual(json.loads((f.root/'services.json').read_text()),services)
        self.assertFalse(any(c[:2] == ['systemctl','stop'] for c in f.commands()))
        self.assertNotIn('Restore completed successfully.',result.stdout)

    def legacy_panel_blocks(self):
        return ''.join('''    location %s {
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass http://127.0.0.1:10002;
    }
''' % path for path in ('/panel/', '/panel'))

    def user_state(self, f):
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            return {name: db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

    def assert_round_trip(self, f, expected):
        archive = f.backup(); original = archive.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        for _ in range(2):
            result = f.run_tool('restore', archive)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.user_state(f), expected)
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone(), ('ok',))
            self.assertEqual(archive.read_bytes(), original)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), digest)

    def test_json_user_choices_survive_backup_restore(self):
        from test_personal_backup import PersonalBackup
        for enabled, uri in (('true','https://example.com/jsonsub/'),
                             ('false','https://example.com/jsonsub/'),
                             ('false','https://custom.example/export?name=mine'),
                             ('false',''), ('true','https://custom.example/export/'),
                             ('true',''), (None,''), (None,None),
                             ('false','https://example.com/jsonsub?name='),
                             (None,'https://example.com/jsonsub?name='),
                             ('true','https://example.com/jsonsub?name=')):
            with self.subTest(enabled=enabled, uri=uri):
                f = PersonalBackup('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    db.execute('DELETE FROM settings WHERE key=?', ('subJsonEnable',))
                    if enabled is not None:
                        db.execute('INSERT INTO settings VALUES(?,?)', ('subJsonEnable', enabled))
                    if uri is None: db.execute("DELETE FROM settings WHERE key='subJsonURI'")
                    else: db.execute('UPDATE settings SET value=? WHERE key=?', (uri,'subJsonURI'))
                expected = self.user_state(f)
                if enabled == 'true' and uri == 'https://example.com/jsonsub?name=':
                    expected['settings'] = [(k,'https://example.com/jsonsub/' if k=='subJsonURI' else v)
                                            for k,v in expected['settings']]
                self.assert_round_trip(f, expected)

    def test_vision_user_state_is_not_project_ownership(self):
        from test_personal_backup import PersonalBackup
        for scenario in ('disabled','edited','extra-host','no-host','deleted'):
            with self.subTest(scenario=scenario):
                f = PersonalBackup('runTest'); f.setUp(); self.addCleanup(f.doCleanups); f.seed_vision()
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    iid = db.execute("SELECT id FROM inbounds WHERE tag='inbound-12000'").fetchone()[0]
                    if scenario == 'disabled': db.execute('UPDATE inbounds SET enable=0 WHERE id=?',(iid,))
                    if scenario == 'edited':
                        stream = json.loads(db.execute('SELECT stream_settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
                        stream['tlsSettings'].update(serverName='user.example', alpn=['h2','http/1.1'])
                        db.execute('UPDATE inbounds SET remark=?,tag=?,stream_settings=? WHERE id=?',
                                   ('user vision','user-tag',json.dumps(stream),iid))
                        db.execute("UPDATE hosts SET address='user.example',port=2443,sni='user.example',alpn='[\"h2\"]' WHERE inbound_id=?",(iid,))
                    if scenario == 'extra-host':
                        db.execute('INSERT INTO hosts SELECT * FROM hosts WHERE inbound_id=?',(iid,))
                    if scenario in ('no-host','deleted'): db.execute('DELETE FROM hosts WHERE inbound_id=?',(iid,))
                    if scenario == 'deleted': db.execute('DELETE FROM inbounds WHERE id=?',(iid,))
                    db.execute("UPDATE clients SET uuid='synthetic-preserved-client'")
                    db.execute('INSERT INTO settings VALUES(?,?)', ('xrayTemplateConfig',json.dumps({
                        'outbounds':[{'tag':'user-direct','protocol':'freedom'}],
                        'routing':{'rules':[{'type':'field','inboundTag':['user-tag'],'outboundTag':'user-direct'}]}})))
                self.assert_round_trip(f, self.user_state(f))

    def test_modified_missing_encryption_is_not_an_old_managed_identity(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            for iid, text, stream_json in db.execute("SELECT id,settings,stream_settings FROM inbounds WHERE protocol='vless'").fetchall():
                settings = json.loads(text); settings.pop('encryption',None)
                stream = json.loads(stream_json); stream['userField'] = 'preserved'
                db.execute('UPDATE inbounds SET tag=?,remark=?,settings=?,stream_settings=? WHERE id=?',
                           ('user-'+str(iid),'user profile',json.dumps(settings),json.dumps(stream),iid))
            db.execute("UPDATE hosts SET address='custom.example',port=2443")
            db.execute("DELETE FROM inbounds WHERE protocol='trojan'")
            db.execute("DELETE FROM hosts WHERE remark='trojan'")
        self.assert_round_trip(f, self.user_state(f))

    def test_user_paths_with_matching_nginx_routes_are_preserved(self):
        f = self.fixture
        replacements = (('/panel/', '/my-panel_v2/'),
                        ('/subscription', '/feeds/public'), ('/jsonsub', '/exports/json'))
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            for key, value in (('webBasePath','/my-panel_v2/'), ('subPath','/feeds/public/'),
                               ('subJsonPath','/exports/json/'), ('subJsonURI','https://custom.example/json/')):
                db.execute('UPDATE settings SET value=? WHERE key=?',(value,key))
        for name in ('/etc/nginx/nginx.conf','/etc/nginx/snippets/includes.conf'):
            path = f.path(name); text = path.read_text()
            for old, new in replacements: text = text.replace(old,new)
            path.write_text(text)
        self.assert_round_trip(f, self.user_state(f))

    def test_vision_artifact_security_is_independent_of_editable_inbounds(self):
        f = self.fixture; f.seed_vision()
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("DELETE FROM inbounds WHERE tag='inbound-12000'")
        archive = f.backup(); digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        original = self.user_state(f)
        site = f.path('/etc/nginx/sites-available/vision.conf')
        stream = f.path('/etc/nginx/stream-enabled/stream.conf')
        hook = f.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision')
        cases = {str(hook): (hook.read_bytes()+b'echo untrusted\n','Invalid staged Vision hook'),
                 str(f.path('/etc/letsencrypt/live/vision.example.com/privkey.pem')):
                     (f.path('/etc/letsencrypt/live/example.com/privkey.pem').read_bytes(),'Certificate/private key mismatch'),
                 str(site): (site.read_bytes().replace(b'listen 127.0.0.1:',b'listen 0.0.0.0:'),'Invalid plaintext Vision fallback'),
                 str(stream): (stream.read_bytes().replace(b'server 127.0.0.1:',b'server 192.0.2.1:'),'Vision SNI mapping mismatch')}
        services = json.loads((f.root/'services.json').read_text())
        for name, (data, error) in cases.items():
            with self.subTest(artifact=Path(name).name):
                candidate = self.modified(archive, {'files/'+name.lstrip('/'): data})
                (f.root/'commands').write_text('')
                result = f.run_tool('restore',candidate)
                self.assert_untouched(result, services)
                self.assertIn(error,result.stderr)
                self.assertEqual(self.user_state(f), original)
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)

    def test_missing_user_tls_file_cannot_fall_back_to_target(self):
        f = self.fixture; f.seed_vision()
        local_only = f.path('/etc/administrator-only/cert.pem')
        local_only.parent.mkdir()
        local_only.write_bytes(f.path('/etc/letsencrypt/live/vision.example.com/fullchain.pem').read_bytes())
        foreign = f.path('/etc/letsencrypt/live/foreign.example/fullchain.pem')
        foreign.parent.mkdir()
        foreign.write_bytes(local_only.read_bytes())
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            iid = db.execute("SELECT id FROM inbounds WHERE tag='inbound-12000'").fetchone()[0]
            stream = json.loads(db.execute('SELECT stream_settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
            stream['tlsSettings']['certificates'][0]['certificateFile'] = str(local_only)
            db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),iid))
        archive = f.backup(); state = self.user_state(f)
        original_db = f.path('/etc/x-ui/x-ui.db').read_bytes()
        services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
        for path, error in ((str(local_only),'Missing staged file'),
                            ('/'+'../'*32+str(local_only).lstrip('/'),'Staged path escaped private state'),
                            (str(foreign),'Unowned staged Certbot TLS reference')):
            with self.subTest(path_kind=error):
                edited = Path(f.temp.name)/'tls-reference.db'; edited.write_bytes(original_db)
                with sqlite3.connect(edited) as db:
                    stream['tlsSettings']['certificates'][0]['certificateFile'] = path
                    db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),iid))
                candidate = self.modified(archive,{f.member('/etc/x-ui/x-ui.db'):edited.read_bytes()})
                (f.root/'commands').write_text('')
                result = f.run_tool('restore',candidate)
                self.assert_untouched(result, services)
                self.assertIn(error,result.stderr)
                self.assertEqual(self.user_state(f),state)

    def test_tls_references_must_survive_selective_certificate_restore(self):
        f = self.fixture; f.seed_vision()
        live = f.path('/etc/letsencrypt/live/vision.example.com')
        version = f.path('/etc/letsencrypt/archive/vision.example.com/fullchain1.pem')
        version.parent.mkdir(parents=True)
        version.write_bytes((live/'fullchain.pem').read_bytes())
        custom = live/'custom.pem'; custom.write_bytes(version.read_bytes())
        foreign = f.path('/etc/letsencrypt/live/foreign.example/fullchain.pem')
        foreign.parent.mkdir(parents=True); foreign.symlink_to(version)
        alias = version.with_name('fullchain2.pem'); alias.symlink_to(version)
        indirect = live/'cert.pem'; indirect.symlink_to(foreign)
        archive = f.backup(); original = archive.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        state = self.user_state(f); original_db = f.path('/etc/x-ui/x-ui.db').read_bytes()
        services = json.loads((f.root/'services.json').read_text())
        for path in (custom, foreign, alias, indirect):
            with self.subTest(reference=str(path.relative_to(f.root))):
                edited = Path(f.temp.name)/'tls-portability.db'; edited.write_bytes(original_db)
                with sqlite3.connect(edited) as db:
                    iid, text = db.execute("SELECT id,stream_settings FROM inbounds WHERE tag='inbound-12000'").fetchone()
                    stream = json.loads(text)
                    stream['tlsSettings']['certificates'][0]['certificateFile'] = str(path)
                    db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),iid))
                candidate = self.modified(archive,{f.member('/etc/x-ui/x-ui.db'):edited.read_bytes()})
                (f.root/'commands').write_text('')
                result = f.run_tool('restore',candidate)
                self.assert_untouched(result,services)
                self.assertIn('staged Certbot TLS reference',result.stderr)
                self.assertEqual(self.user_state(f),state)
                self.assertEqual(archive.read_bytes(),original)
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)

    def test_copied_live_archive_and_compatibility_tls_references_restore(self):
        f = self.fixture; f.seed_vision()
        pairs = []; versions = []
        for domain in ('example.com','reality.example.com','vision.example.com'):
            live = f.path('/etc/letsencrypt/live/'+domain)
            archived = f.path('/etc/letsencrypt/archive/'+domain)
            archived.mkdir(parents=True)
            for name in ('cert','chain','fullchain','privkey'):
                source = live/('privkey.pem' if name=='privkey' else 'fullchain.pem')
                version = archived/(name+'1.pem'); version.write_bytes(source.read_bytes())
                versions.append(version)
            for name in ('cert','chain','fullchain','privkey'):
                link = live/(name+'.pem'); link.unlink(missing_ok=True)
                link.symlink_to('../../archive/'+domain+'/'+name+'1.pem')
            for base, suffix in ((live,''),(archived,'1')):
                pairs.append({'certificateFile':str(base/('fullchain'+suffix+'.pem')),
                              'keyFile':str(base/('privkey'+suffix+'.pem'))})
        compat = f.path('/root/cert/example.com')
        pairs.append({'certificateFile':str(compat/'fullchain.pem'),'keyFile':str(compat/'privkey.pem')})
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            iid, text = db.execute("SELECT id,stream_settings FROM inbounds WHERE tag='inbound-12000'").fetchone()
            stream = json.loads(text); stream['tlsSettings']['certificates'] = pairs
            db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),iid))
        state = self.user_state(f); archive = f.backup(); original = archive.read_bytes()
        for _ in range(2):
            # A successful restore must actually supply the PEMs, not borrow target files.
            for version in versions: version.unlink()
            result = f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Restore completed successfully.',result.stdout)
            for pair in pairs:
                for path in pair.values(): self.assertTrue(Path(path).is_file(),path)
            self.assertEqual(self.user_state(f),state)
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
            self.assertEqual(archive.read_bytes(),original)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),hashlib.sha256(original).hexdigest())

    def test_old_managed_vless_encryption_is_normalized_only_in_staging(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            managed = [row[0] for row in db.execute(
                "SELECT inbound_id FROM hosts WHERE remark IN ('reality','ws','xhttp') ORDER BY id")]
            for index, iid in enumerate(managed):
                settings = json.loads(db.execute('SELECT settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
                settings.pop('encryption')
                if index == 1: settings['encryption'] = ''
                settings['clients'] = [{'id':'preserved-client','flow':'custom-field'}]
                settings['custom'] = {'preserved':True}
                db.execute('UPDATE inbounds SET settings=? WHERE id=?',(json.dumps(settings),iid))
            # Custom VLESS is intentionally outside the managed Host/tag/transport topology.
            custom = dict(zip([c[0] for c in db.execute('SELECT * FROM inbounds').description],
                              db.execute('SELECT * FROM inbounds WHERE id=?',(managed[1],)).fetchone()))
            custom.update(id=77, tag='custom-vless', port=39000, remark='custom ws',
                          settings='{"clients":[{"id":"custom-client"}],"custom":true}')
            db.execute('INSERT INTO inbounds VALUES ('+','.join('?' for _ in custom)+')',list(custom.values()))
            before = {row[0]:row[1:] for row in db.execute('SELECT * FROM inbounds')}
            columns = [c[0] for c in db.execute('SELECT * FROM inbounds').description]
            settings_index = columns.index('settings') - 1
        archive = f.backup(); original = archive.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        for _ in range(2):
            result = f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Restore completed successfully.',result.stdout)
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                after = {row[0]:row[1:] for row in db.execute('SELECT * FROM inbounds')}
                for iid, original_row in before.items():
                    expected = list(original_row)
                    if iid in managed:
                        settings = json.loads(expected[settings_index]); settings['encryption'] = 'none'
                        self.assertEqual(json.loads(after[iid][settings_index]),settings)
                        expected[settings_index] = after[iid][settings_index]
                    self.assertEqual(after[iid],tuple(expected),'unrelated inbound state changed')
            self.assertEqual(archive.read_bytes(),original)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
            self.assertFalse(list(f.path('/var/backups/x-ui').glob('.rollback-*')))
            states = json.loads((f.root/'services.json').read_text())
            self.assertTrue(all(states[name]=='active' for name in ('x-ui','nginx','mtr-backend','certbot.timer')))

    def test_custom_ws_missing_encryption_is_not_a_managed_candidate(self):
        from test_personal_backup import PersonalBackup
        for old_managed in (False, True):
            with self.subTest(old_managed=old_managed):
                f = PersonalBackup('runTest'); f.setUp()
                self.addCleanup(f.doCleanups)
                f.env['NGINX_BIN'] = self.fixture.env['NGINX_BIN']
                with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                    iid = db.execute("SELECT inbound_id FROM hosts WHERE remark='ws'").fetchone()[0]
                    row = db.execute('SELECT * FROM inbounds WHERE id=?',(iid,)).fetchone()
                    custom = dict(zip([c[0] for c in db.execute('SELECT * FROM inbounds').description],row))
                    stream = json.loads(custom['stream_settings'])
                    stream['wsSettings']['path']='/39000/userpath'
                    if old_managed: stream['wsSettings']['host']='user.example'
                    custom.update(id=77,tag='inbound-39000',port=39000,remark='user ws',
                                  stream_settings=json.dumps(stream),settings='{"clients":[],"custom":true}')
                    db.execute('INSERT INTO inbounds VALUES ('+','.join('?' for _ in custom)+')',list(custom.values()))
                    host = dict(zip([c[0] for c in db.execute('SELECT * FROM hosts').description],
                                    db.execute('SELECT * FROM hosts WHERE inbound_id=?',(iid,)).fetchone()))
                    host.update(id=77,inbound_id=77,remark='user ws')
                    if old_managed: host['address']='user.example'
                    db.execute('INSERT INTO hosts VALUES ('+','.join('?' for _ in host)+')',list(host.values()))
                    if old_managed:
                        settings=json.loads(db.execute('SELECT settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
                        settings.pop('encryption')
                        db.execute('UPDATE inbounds SET settings=? WHERE id=?',(json.dumps(settings),iid))
                    before_custom=db.execute('SELECT * FROM inbounds WHERE id=77').fetchone()
                    before_hosts=db.execute('SELECT * FROM hosts').fetchall()
                archive=f.backup(); original=archive.read_bytes()
                for _ in range(2):
                    result=f.run_tool('restore',archive)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                        self.assertEqual(db.execute('SELECT * FROM inbounds WHERE id=77').fetchone(),before_custom)
                        self.assertEqual(db.execute('SELECT * FROM hosts').fetchall(),before_hosts)
                        self.assertEqual(json.loads(db.execute('SELECT settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])['encryption'],'none')
                        self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                    self.assertEqual(archive.read_bytes(),original)

    def test_nonempty_managed_vless_encryption_is_preserved(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            iid = db.execute("SELECT inbound_id FROM hosts WHERE remark='ws'").fetchone()[0]
            settings = json.loads(db.execute('SELECT settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
            settings['encryption'] = 'custom-nonempty-value'
            original = json.dumps(settings)
            db.execute('UPDATE inbounds SET settings=? WHERE id=?',(original,iid))
        result = f.run_tool('restore',f.backup())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            self.assertEqual(db.execute('SELECT settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0],original)

    def test_valid_vless_with_user_modified_hosts_needs_no_migration(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("UPDATE hosts SET address='user.example',remark='user-host',port=2443 WHERE remark='ws'")
            db.execute("UPDATE hosts SET address='alternate.example' WHERE remark='xhttp'")
            before = db.execute('SELECT * FROM hosts').fetchall()
            inbounds = db.execute('SELECT * FROM inbounds').fetchall()
        archive = f.backup(); original = archive.read_bytes()
        for _ in range(2):
            result = f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                self.assertEqual(db.execute('SELECT * FROM hosts').fetchall(),before)
                self.assertEqual(db.execute('SELECT * FROM inbounds').fetchall(),inbounds)
            self.assertEqual(archive.read_bytes(),original)

    def legacy_grpc(self):
        from test_personal_xhttp import render, SHARED
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            iid = db.execute("SELECT inbound_id FROM hosts WHERE remark='trojan'").fetchone()[0]
            stream = json.loads(db.execute('SELECT stream_settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
            stream['grpcSettings']['serviceName'] = '/10004/trojan'
            db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),iid))
        block = re.search(r'^    location = /10004/trojan \{.*?^    \}',render(SHARED),re.M|re.S)[0]
        include = f.path('/etc/nginx/snippets/includes.conf')
        include.write_text(include.read_text() + block + '\n')
        config = f.path('/etc/nginx/nginx.conf')
        config.write_text(config.read_text().replace('http {','http { map $host $hack { default 0; }',1))
        return iid

    def test_legacy_grpc_is_normalized_only_in_staging_and_custom_is_preserved(self):
        f = self.fixture; iid = self.legacy_grpc()
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            original_row = db.execute('SELECT * FROM inbounds WHERE id=?',(iid,)).fetchone()
            columns = [c[0] for c in db.execute('SELECT * FROM inbounds').description]
            custom = dict(zip(columns,original_row))
            custom.update(id=77,tag='custom-grpc',remark='custom grpc',port=39000)
            db.execute('INSERT INTO inbounds VALUES ('+','.join('?' for _ in custom)+')',list(custom.values()))
            before = db.execute('SELECT * FROM inbounds').fetchall()
            hosts = db.execute('SELECT * FROM hosts').fetchall()
        archive=f.backup(); original=archive.read_bytes(); digest=hashlib.sha256(original).hexdigest()
        for _ in range(2):
            result=f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0],'ok')
                for row in db.execute('SELECT * FROM inbounds'):
                    expected=list(next(r for r in before if r[0]==row[0]))
                    if row[0]==iid:
                        index=columns.index('stream_settings'); stream=json.loads(expected[index])
                        stream['grpcSettings']['serviceName']='/10004/trojan|trojan-multi'
                        self.assertEqual(json.loads(row[index]),stream); expected[index]=row[index]
                    self.assertEqual(row,tuple(expected))
                self.assertEqual(db.execute('SELECT * FROM hosts').fetchall(),hosts)
            self.assertEqual(archive.read_bytes(),original)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
            self.assertIn('location = /10004/trojan {',f.path('/etc/nginx/snippets/includes.conf').read_text())
            self.assertTrue(all(json.loads((f.root/'services.json').read_text())[name]=='active'
                                for name in ('x-ui','nginx','mtr-backend','certbot.timer')))

    def test_user_grpc_service_is_not_a_legacy_route_migration(self):
        f = self.fixture; iid = self.legacy_grpc()
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            stream = json.loads(db.execute('SELECT stream_settings FROM inbounds WHERE id=?',(iid,)).fetchone()[0])
            stream['grpcSettings']['serviceName'] = '/10004/userService'
            db.execute('UPDATE inbounds SET stream_settings=?,enable=0 WHERE id=?',(json.dumps(stream),iid))
        self.assert_round_trip(f, self.user_state(f))

    def test_ambiguous_legacy_grpc_identity_fails_before_mutation(self):
        f=self.fixture; self.legacy_grpc()
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("INSERT INTO hosts SELECT * FROM hosts WHERE remark='trojan'")
        archive=f.backup(); original=f.path('/etc/x-ui/x-ui.db').read_bytes()
        services=json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
        result=f.run_tool('restore',archive)
        self.assert_untouched(result,services)
        self.assertEqual(f.path('/etc/x-ui/x-ui.db').read_bytes(),original)
        self.assertIn('managed gRPC',result.stderr)

    def test_ambiguous_managed_vless_identity_fails_before_mutation(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            for iid, text in db.execute("SELECT id,settings FROM inbounds WHERE protocol='vless'").fetchall():
                settings=json.loads(text); settings.pop('encryption')
                db.execute('UPDATE inbounds SET settings=? WHERE id=?',(json.dumps(settings),iid))
        archive = f.backup()
        original = f.path('/etc/x-ui/x-ui.db').read_bytes()
        services = json.loads((f.root/'services.json').read_text())
        for sql in ("INSERT INTO hosts SELECT * FROM hosts WHERE remark='ws'",
                    "INSERT INTO inbounds SELECT * FROM inbounds WHERE tag='inbound-8443'"):
            with self.subTest(sql=sql):
                dbfile = Path(f.temp.name)/'ambiguous.db'; dbfile.write_bytes(original)
                with sqlite3.connect(dbfile) as db: db.execute(sql)
                bad = self.modified(archive,{f.member('/etc/x-ui/x-ui.db'):dbfile.read_bytes()})
                (f.root/'commands').write_text('')
                result = f.run_tool('restore',bad)
                self.assert_untouched(result,services)
                self.assertEqual(f.path('/etc/x-ui/x-ui.db').read_bytes(),original)
                self.assertIn('managed VLESS',result.stderr)

    def test_custom_reality_panel_route_and_invalid_basepath_fail_before_mutation(self):
        f = self.fixture; archive = f.backup()
        reality = f.path('/etc/nginx/sites-available/reality.example.com').read_text()
        for blocks in (self.legacy_panel_blocks().replace('proxy_redirect off;', 'proxy_redirect default;'),
                       '    location = "/panel/" { proxy_pass https://127.0.0.1:10002; }\n'):
            bad = self.modified(archive,{f.member('/etc/nginx/sites-available/reality.example.com'):
                                        reality.replace('    include ',blocks + '    include ',1).encode()})
            services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
            result = f.run_tool('restore',bad)
            self.assert_untouched(result,services)
            self.assertIn('Unexpected REALITY panel location',result.stderr)
        for value in (None, '/panel/../unsafe/', '/panel/duplicate/'):
            dbfile = Path(f.temp.name)/'invalid-path.db'; shutil.copy2(f.path('/etc/x-ui/x-ui.db'),dbfile)
            with sqlite3.connect(dbfile) as db:
                if value is None: db.execute("DELETE FROM settings WHERE key='webBasePath'")
                elif value.endswith('duplicate/'): db.execute("INSERT INTO settings VALUES('webBasePath',?)",(value,))
                else: db.execute("UPDATE settings SET value=? WHERE key='webBasePath'",(value,))
            bad = self.modified(archive,{f.member('/etc/x-ui/x-ui.db'):dbfile.read_bytes()})
            services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
            self.assert_untouched(f.run_tool('restore',bad),services)

    def test_broken_staged_nginx_rejected_before_any_service_stop(self):
        f = self.fixture; archive = f.backup()
        configs = [(b'invalid_nginx_directive;\n','Staged nginx -t failed'),
                   (('error_log ' + str(f.path('/var/www/html/recovery-marker')) + ';\ninclude /etc/passwd;\n').encode(),
                    'outside private staged state')]
        for config, message in configs:
            with self.subTest(config=config):
                bad = self.modified(archive,{f.member('/etc/nginx/nginx.conf'):config})
                digest = hashlib.sha256(bad.read_bytes()).hexdigest()
                services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
                result = f.run_tool('restore',bad)
                self.assert_untouched(result,services)
                self.assertIn(message,result.stderr)
                self.assertEqual(hashlib.sha256(bad.read_bytes()).hexdigest(),digest)

    def test_unused_distro_snakeoil_and_other_configs_restore_idempotently(self):
        f = self.fixture
        distro_files = ('snippets/snakeoil.conf','snippets/fastcgi-php.conf','sites-available/default',
                        'fastcgi.conf','fastcgi_params','proxy_params','scgi_params','uwsgi_params',
                        'mime.types','koi-utf','koi-win','win-utf')
        for name in distro_files:
            source = Path('/etc/nginx')/name
            self.assertTrue(source.is_file(),name)
            f.write('/etc/nginx/'+name,source.read_text())
        snippet = f.path('/etc/nginx/snippets/snakeoil.conf').read_bytes()
        self.assertIn(b'/etc/ssl/certs/ssl-cert-snakeoil.pem',snippet)
        self.assertIn(b'/etc/ssl/private/ssl-cert-snakeoil.key',snippet)
        archive = f.backup(); digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        main = f.path('/etc/nginx/nginx.conf').read_bytes()
        for _ in range(2):
            (f.root/'commands').write_text('')
            result = f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Restore completed successfully.',result.stdout)
            self.assertTrue(any(c[0]=='nginx' and '-c' in c and any('nginx-validation' in a for a in c)
                                for c in f.commands()))
            self.assertEqual(f.path('/etc/nginx/snippets/snakeoil.conf').read_bytes(),snippet)
            self.assertEqual(f.path('/etc/nginx/nginx.conf').read_bytes(),main)
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)

    def test_active_exact_and_wildcard_snakeoil_fail_before_mutation(self):
        f = self.fixture
        snippet = Path('/etc/nginx/snippets/snakeoil.conf').read_text()
        f.write('/etc/nginx/snippets/snakeoil.conf',snippet)
        archive = f.backup()
        main = f.path('/etc/nginx/nginx.conf').read_text()
        for suffix in ('snakeoil.conf','*.conf'):
            with self.subTest(include=suffix):
                include = str(f.path('/etc/nginx/snippets'))+'/'+suffix
                config = main.replace('server {', 'server { include '+include+';',1)
                bad = self.modified(archive,{f.member('/etc/nginx/nginx.conf'):config.encode()})
                digest = hashlib.sha256(bad.read_bytes()).hexdigest()
                services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
                result = f.run_tool('restore',bad)
                self.assert_untouched(result,services)
                self.assertIn('unknown directive "xui_untrusted_resource_',result.stderr)
                self.assertIn('Untrusted nginx resource in snippets/snakeoil.conf:',result.stderr)
                self.assertIn('ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem',result.stderr)
                self.assertEqual(f.path('/etc/nginx/nginx.conf').read_text(),main)
                self.assertEqual(f.path('/etc/nginx/snippets/snakeoil.conf').read_text(),snippet)
                self.assertEqual(hashlib.sha256(bad.read_bytes()).hexdigest(),digest)

    def test_active_external_resources_never_open_live_files(self):
        f = self.fixture; archive = f.backup()
        external = Path(f.temp.name)/'outside-nginx'; external.mkdir()
        cert, key, config = external/'cert.pem',external/'key.pem',external/'valid.conf'
        shutil.copy2(f.path('/etc/letsencrypt/live/example.com/fullchain.pem'),cert)
        shutil.copy2(f.path('/etc/letsencrypt/live/example.com/privkey.pem'),key)
        config.write_text('server { listen 127.0.0.1:10123; }\n')
        # Watch actual readable live files: even a failing preflight must never open them.
        libc = ctypes.CDLL(None,use_errno=True)
        libc.inotify_add_watch.argtypes = (ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32)
        descriptor = libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        self.assertGreaterEqual(descriptor,0)
        self.addCleanup(os.close,descriptor)
        for path in (cert,key,config):
            self.assertGreaterEqual(libc.inotify_add_watch(descriptor,os.fsencode(path),0x20),0)  # IN_OPEN
        main = f.path('/etc/nginx/nginx.conf').read_bytes()
        cases = [('ssl_certificate',cert),('ssl_certificate_key',key),('include',config),('error_log',config)]
        for directive, path in cases:
            with self.subTest(directive=directive):
                nginx = 'events {} http { '+directive+' "'+str(path)+'"; }\n'
                bad = self.modified(archive,{f.member('/etc/nginx/nginx.conf'):nginx.encode()})
                digest = hashlib.sha256(bad.read_bytes()).hexdigest()
                services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
                result = f.run_tool('restore',bad)
                self.assert_untouched(result,services)
                self.assertIn('unknown directive "xui_untrusted_resource_',result.stderr)
                self.assertIn('Untrusted nginx resource in nginx.conf: '+directive+' '+str(path),result.stderr)
                self.assertEqual(f.path('/etc/nginx/nginx.conf').read_bytes(),main)
                self.assertEqual(hashlib.sha256(bad.read_bytes()).hexdigest(),digest)
                try: opened = os.read(descriptor,8192)
                except BlockingIOError: opened = b''
                self.assertEqual(opened,b'','private preflight opened a live external resource')

    def test_broken_staged_tls_and_hook_rejected_before_mutation(self):
        f = self.fixture; archive = f.backup()
        cases = [('/etc/letsencrypt/live/example.com/fullchain.pem',b'invalid PEM'),
                 ('/etc/letsencrypt/live/example.com/privkey.pem',f.path('/etc/letsencrypt/live/reality.example.com/privkey.pem').read_bytes()),
                 ('/etc/letsencrypt/live/example.com/fullchain.pem',f.path('/etc/letsencrypt/live/reality.example.com/fullchain.pem').read_bytes()),
                 ('/etc/letsencrypt/renewal/example.com.conf',b'authenticator = standalone'),
                 ('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx',b'#!/bin/bash\ntouch /tmp/never-execute-incoming-hook\n')]
        for path, data in cases:
            with self.subTest(path=path):
                bad = self.modified(archive,{f.member(path):data})
                services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
                self.assert_untouched(f.run_tool('restore',bad),services)
        self.assertFalse(Path('/tmp/never-execute-incoming-hook').exists())

    def test_subscription_tls_reference_and_http_route_fail_before_mutation(self):
        f = self.fixture; archive = f.backup()
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        original_db = f.path('/etc/x-ui/x-ui.db').read_bytes()
        for key,value in [('subCertFile',None),('subKeyFile',''),
                          ('subCertFile',str(f.path('/etc/letsencrypt/live/reality.example.com/fullchain.pem'))),
                          ('subKeyFile',str(f.path('/root/cert/example.com/fullchain.pem')))]:
            dbfile = Path(f.temp.name)/'bad-sub-tls.db'; dbfile.write_bytes(original_db)
            with sqlite3.connect(dbfile) as db:
                if value is None: db.execute('DELETE FROM settings WHERE key=?',(key,))
                else: db.execute('UPDATE settings SET value=? WHERE key=?',(value,key))
            bad = self.modified(archive,{f.member('/etc/x-ui/x-ui.db'):dbfile.read_bytes()})
            services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
            self.assert_untouched(f.run_tool('restore',bad),services)
            self.assertEqual(f.path('/etc/x-ui/x-ui.db').read_bytes(),original_db)
        shared = f.path('/etc/nginx/snippets/includes.conf').read_text()
        for count in (1,7):
            bad = self.modified(archive,{f.member('/etc/nginx/snippets/includes.conf'):
                                        shared.replace('https://127.0.0.1:10003','http://127.0.0.1:10003',count).encode()})
            services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
            result = f.run_tool('restore',bad)
            self.assert_untouched(result,services)
            self.assertIn('Subscription TLS DB requires HTTPS nginx backend',result.stderr)
            self.assertEqual(f.path('/etc/nginx/snippets/includes.conf').read_text(),shared)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)

    def test_old_v3_normalization_and_new_v3_idempotency(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("UPDATE settings SET value='' WHERE key='webListen'")
            db.execute("UPDATE settings SET value='false' WHERE key='subJsonEnable'")
            db.execute("UPDATE settings SET value='https://example.com/jsonsub?name=' WHERE key='subJsonURI'")
        reality_path = f.path('/etc/nginx/sites-available/reality.example.com')
        normalized_reality = reality_path.read_text()
        reality_path.write_text(normalized_reality.replace('    include ',self.legacy_panel_blocks() + '    include ',1))
        main = f.path('/etc/nginx/nginx.conf').read_bytes()
        with f.path('/etc/nginx/snippets/includes.conf').open('a') as includes:
            includes.write('location ^~ /Session7AbC/ { grpc_pass unix:/dev/shm/uds2023.sock; }\n')
        shared = f.path('/etc/nginx/snippets/includes.conf').read_text()
        # Original v1.5.0 hook lacks the new runtime health, but its exact managed body is trusted.
        result = subprocess.run(['bash','-eu','-c',f.script.read_text().split('cmd_restore() {')[0] +
                                 '\nrender_certificate_hook example.com reality.example.com legacy\n'],env=f.env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        f.write('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx',result.stdout.decode(),0o755)
        archive = f.backup(); digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        for _ in range(2):
            result = f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                self.assertEqual(db.execute("SELECT value FROM settings WHERE key='webListen'").fetchone()[0],'127.0.0.1')
                values = dict(db.execute('SELECT key,value FROM settings'))
                self.assertEqual(values['subJsonEnable'],'false')
                self.assertEqual(values['subJsonPath'],'/jsonsub/')
                self.assertEqual(values['subJsonURI'],'https://example.com/jsonsub?name=')
            includes = f.path('/etc/nginx/snippets/includes.conf').read_text()
            self.assertEqual(includes.count('proxy_pass https://127.0.0.1:10003;'),7)
            self.assertNotIn('proxy_pass http://127.0.0.1:10003;',includes)
            self.assertEqual(includes,shared)
            self.assertEqual(reality_path.read_text(),normalized_reality)
            self.assertNotIn('location /panel',reality_path.read_text())
            self.assertEqual(f.path('/etc/nginx/nginx.conf').read_bytes(),main)
            self.assertIn('proxy_pass https://127.0.0.1:10002;',f.path('/etc/nginx/nginx.conf').read_text())
            self.assertNotIn('check_xray_runtime',f.path('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx').read_text())
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
            archive.unlink(); archive = f.backup(); digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_legacy_json_missing_enable_is_migrated_only_in_staging(self):
        f = self.fixture
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("DELETE FROM settings WHERE key='subJsonEnable'")
            db.execute("UPDATE settings SET value='https://example.com/jsonsub?name=' WHERE key='subJsonURI'")
        archive = f.backup(); digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        original = f.path('/etc/x-ui/x-ui.db').read_bytes()
        shared = f.path('/etc/nginx/snippets/includes.conf').read_bytes()
        result = f.run_tool('restore',archive)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='subJsonEnable'").fetchall(),[])
            self.assertEqual(db.execute("SELECT value FROM settings WHERE key='subJsonURI'").fetchone()[0],
                             'https://example.com/jsonsub?name=')
        self.assertEqual(f.path('/etc/nginx/snippets/includes.conf').read_bytes(),shared)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
        with tarfile.open(archive) as src:
            self.assertEqual(src.extractfile(f.member('/etc/x-ui/x-ui.db')).read(),original)

    def test_custom_or_inconsistent_json_state_rejected_before_mutation(self):
        f = self.fixture; archive = f.backup()
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        original = f.path('/etc/x-ui/x-ui.db').read_bytes()
        # Custom/disabled values are covered by round trips; duplicates and malformed booleans are corruption.
        cases = ["INSERT INTO settings VALUES('subJsonEnable','true')",
                 "INSERT INTO settings VALUES('subJsonURI','https://custom.example/')",
                 "UPDATE settings SET value='not-a-boolean' WHERE key='subJsonEnable'"]
        for sql in cases:
            with self.subTest(sql=sql):
                dbfile = Path(f.temp.name)/'bad-json.db'; dbfile.write_bytes(original)
                with sqlite3.connect(dbfile) as db: db.execute(sql)
                bad = self.modified(archive,{f.member('/etc/x-ui/x-ui.db'):dbfile.read_bytes()})
                services = json.loads((f.root/'services.json').read_text()); (f.root/'commands').write_text('')
                self.assert_untouched(f.run_tool('restore',bad),services)
                self.assertEqual(f.path('/etc/x-ui/x-ui.db').read_bytes(),original)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)

    def test_wal_target_snapshot_and_repeated_restore_succeed(self):
        f = self.fixture; archive = f.backup()
        dbfile = f.path('/etc/x-ui/x-ui.db')
        for _ in range(2):
            with self.subTest(restore=_ + 1):
                db = sqlite3.connect(dbfile)
                try:
                    self.assertEqual(db.execute('PRAGMA journal_mode=WAL').fetchone()[0], 'wal')
                    db.execute('CREATE TABLE IF NOT EXISTS rollback_wal_fixture (value TEXT)')
                    db.execute("INSERT INTO rollback_wal_fixture VALUES ('pending WAL data')")
                    db.commit()
                    self.assertEqual(dbfile.read_bytes()[18:20], b'\x02\x02')
                    for suffix in ('-wal', '-shm'):
                        self.assertTrue(Path(str(dbfile) + suffix).is_file())
                    result = f.run_tool('restore', archive)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('Restore completed successfully.', result.stdout)
                    # Incoming, rollback and restored databases passed the real SQLite CLI check.
                    self.assertEqual(result.stdout.count('SQLite database is consistent'), 3)
                finally:
                    db.close()
                with sqlite3.connect(dbfile) as restored:
                    self.assertEqual(restored.execute('PRAGMA quick_check').fetchone()[0], 'ok')
                    self.assertIsNone(restored.execute("SELECT name FROM sqlite_master WHERE name='rollback_wal_fixture'").fetchone())

    def test_post_replacement_failed_xui_start_restores_and_verifies_old_state(self):
        f = self.fixture; archive = f.backup()
        incoming = self.modified(archive,{f.member('/var/www/html/recovery-marker'):b'incoming'})
        old_db = f.path('/etc/x-ui/x-ui.db').read_bytes()
        old_nginx = f.path('/etc/nginx/snippets/includes.conf').read_bytes()
        old_states = (f.root/'services.json').read_bytes()
        result = f.run_tool('restore',incoming,FAIL_INCOMING_XUI='1')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Previous managed state/service states restored and checked',result.stderr)
        self.assertEqual(f.path('/var/www/html/recovery-marker').read_text(),'original')
        self.assertEqual(f.path('/etc/x-ui/x-ui.db').read_bytes(),old_db)
        self.assertEqual(f.path('/etc/nginx/snippets/includes.conf').read_bytes(),old_nginx)
        self.assertEqual(json.loads((f.root/'services.json').read_bytes()),json.loads(old_states))
        self.assertFalse(list(f.path('/var/backups/x-ui').glob('.rollback-*')))
        self.assertNotIn('Restore completed successfully.',result.stdout)

    def test_unverified_rollback_keeps_private_material_and_reports_exact_path(self):
        f = self.fixture; archive = f.backup()
        result = f.run_tool('restore',archive,FAIL_XUI_START='1')
        self.assertNotEqual(result.returncode,0)
        material = list(f.path('/var/backups/x-ui').glob('.rollback-*'))
        self.assertEqual(len(material),1,result.stdout+result.stderr)
        self.assertEqual(material[0].stat().st_mode & 0o777,0o700)
        self.assertTrue((material[0]/'ready').is_file())
        self.assertIn(str(material[0]),result.stderr)
        self.assertIn('could not be verified',result.stderr)
        self.assertNotIn('Restore completed successfully.',result.stdout)

    def test_post_replacement_failure_preserves_previous_agh_and_requires_its_health(self):
        from test_adguard_backup import AdGuardBackup
        agh = AdGuardBackup('runTest'); agh.setUp(); self.addCleanup(agh.doCleanups)
        agh.install_fixture()
        f = agh.fixture
        f.env['NGINX_BIN'] = os.environ.get('NGINX_BIN') or shutil.which('nginx')
        f.write('/var/www/html/recovery-marker','original')
        archive = f.backup()
        # Use this fixture's archive member paths, retaining the authenticated AGH binary fixture.
        original = self.fixture; self.fixture = f
        incoming = self.modified(archive,{f.member('/var/www/html/recovery-marker'):b'incoming'})
        self.fixture = original
        config = f.path('/opt/AdGuardHome/AdGuardHome.yaml').read_bytes()
        result = f.run_tool('restore',incoming,FAIL_INCOMING_XUI='1')
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Previous managed state/service states restored and checked',result.stderr)
        self.assertEqual(f.path('/opt/AdGuardHome/AdGuardHome.yaml').read_bytes(),config)
        self.assertEqual(f.path('/opt/AdGuardHome/data/querylog.json').read_text(),'persistent query state')
        self.assertEqual(json.loads((f.root/'services.json').read_text())['AdGuardHome'],'active')
        self.assertIn('binary --version',(f.root/'binary-calls').read_text())
        self.assertNotIn('Restore completed successfully.',result.stdout)
