"""Targeted supported-VPS regressions; all paths/services stay private fixtures."""
import errno
import http.client
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_personal_xhttp import SOURCE, function, render
from test_integrated_features import helper


def shell(names, body, env=None, stubs='', timeout=15):
    source='\n'.join(function(n) for n in names if n+'() {' in SOURCE)
    return subprocess.run(['bash','-u','-c','msg_err() { echo "$*" >&2; };\n'+source+'\n'+stubs+'\n'+body],
                          env={**os.environ,**(env or {})},capture_output=True,text=True,timeout=timeout)


def root_stat(path, *args, **kwargs):
    fields=list(REAL_STAT(path,*args,**kwargs));fields[4]=fields[5]=0
    return os.stat_result(fields)


REAL_STAT=Path.stat


def complete_function(name):
    # nginx heredocs contain column-zero braces; stop at the next shell function.
    text=SOURCE[SOURCE.index(name+'() {'):]
    headers=list(re.finditer(r'^\w+\(\)\s*\{',text,re.M))
    body = text[:headers[1].start()] if len(headers)>1 else text
    return (function('ui_text') + '\n' if name != 'ui_text' and 'ui_text ' in body else '') + body


def dns_name(length, letter='a'):
    if length <= 63:
        return letter*(length-2)+'.'+letter
    labels=[]
    while length > 63:
        size=min(63,length-2); labels.append(letter*size); length-=size+1
    return '.'.join([*labels,letter*length])


def http_name_configs(root, names, ipv6, ports):
    """Actual installer/ Vision HTTP fragments, with private paths and listeners."""
    from test_personal_xhttp import MAIN, SHARED
    nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
    version=subprocess.run([nginx,'-v'],capture_output=True,text=True,check=True).stderr
    modern=tuple(map(int,re.search(r'nginx/(\d+)\.(\d+)\.(\d+)',version).groups())) >= (1,25,1)
    variables={'domain':names[0],'reality_domain':names[1],
               'diag_token':'AbCdEf0123456789',  # Production gen_random_string(16), not the shorter shared fixture.
               'http2_listen':'' if modern else ' http2','http2_on':'http2 on;' if modern else '',
               'ipv6_listen':'listen [::]:80;' if ipv6 else ''}
    (root/'includes.conf').write_text(render(SHARED,**variables))
    acme=render('cat > /etc/nginx/sites-available/80.conf',**variables)
    core=render('cat > /etc/nginx/sites-available/00-maps.conf',**variables)
    for target in (MAIN,'cat > "/etc/nginx/sites-available/${reality_domain}"'):
        core+=render(target,**variables)
    vision=helper('vision')
    vision_acme=vision.acme_config(names[2],ipv6=ipv6)
    fallback=vision.fallback_config(names[2],31236)
    temporary='\n'.join(f'{kind}_temp_path {root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
    result={}
    for stage,text in (('initial',acme),('core',acme+core),
                       ('vision-acme',acme+core+vision_acme),('fallback',acme+core+vision_acme+fallback)):
        text=text.replace('listen 80;',f'listen 127.0.0.1:{ports[0]};')
        text=text.replace('listen [::]:80;',f'listen [::1]:{ports[0]};')
        for old,port in zip((7443,9443,31236),ports[1:]): text=text.replace(f'127.0.0.1:{old}',f'127.0.0.1:{port}')
        text=text.replace('/etc/nginx/snippets/includes.conf',str(root/'includes.conf'))
        text=text.replace('/etc/nginx/snippets/x-ui-auto-optional',str(root/'optional'))
        text=re.sub(r'/etc/letsencrypt/live/[^/]+/fullchain.pem',str(root/'cert.pem'),text)
        text=re.sub(r'/etc/letsencrypt/live/[^/]+/privkey.pem',str(root/'key.pem'),text)
        text=text.replace('/var/www/acme',str(root/'acme')).replace('/var/www/html',str(root/'html'))
        result[stage]=f'pid {root}/pid; error_log stderr; events {{}} http {{ access_log off; {temporary}\n{text}\n}}'
    return result


def http_name_certificate(root):
    # Syntax-only fixture: nginx -t needs a certificate, without a TLS handshake.
    subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1',
                    '-nodes','-days','1','-subj','/CN=fixture.example','-keyout',str(root/'key.pem'),
                    '-out',str(root/'cert.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def nginx_ipv4_acme(simulate=False):
    """Production renderers plus real nginx; reused by the existing second VM boot."""
    from certificate_fixtures import relocate
    from test_personal_xhttp import FIXTURE
    nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
    if not nginx: raise AssertionError('Real nginx required')
    with tempfile.TemporaryDirectory(prefix='ipv4-acme-') as directory:
        root=Path(directory);root.chmod(0o755)
        (root/'etc/nginx').mkdir(parents=True)
        (root/'etc/nginx/nginx.conf').write_text('events {}\nhttp {}\n')
        stubs="""nginx() { [[ \"${1:-}\" != -v ]] || echo 'nginx version: nginx/1.24.0' >&2; return 0; }
systemctl() { :; }
install() { local -a args=(); while (($#)); do case \"$1\" in -o|-g) shift 2;; *) args+=(\"$1\"); shift;; esac; done; command install \"${args[@]}\"; }
"""
        if simulate: stubs+='ipv6_available() { return 1; };\n'
        source='\n'.join(relocate(complete_function(n),root) for n in ('ipv6_available','prepare_acme_webroot','setup_acme_http','configure_nginx'))
        result=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\nsetup_acme_http && configure_nginx'],
            env={**os.environ,**FIXTURE},capture_output=True,text=True,timeout=15)
        assert result.returncode==0,result.stderr
        main=(root/'etc/nginx/sites-available/80.conf').read_text()
        stream=(root/'etc/nginx/stream-enabled/stream.conf').read_text()
        assert 'listen 80;' in main and 'listen     443;' in stream
        assert '[::]' not in main+stream
        vision=helper('vision')
        config=vision.acme_config('vision.example',ipv6=False) if simulate else vision.acme_config('vision.example')
        assert '[::]' not in config
        with socket.socket() as listener, socket.socket() as stream_listener:
            listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
            stream_listener.bind(('127.0.0.1',0));stream_port=stream_listener.getsockname()[1]
        stream=stream.replace('listen     443;',f'listen 127.0.0.1:{stream_port};')
        main=main.replace('listen 80;',f'listen 127.0.0.1:{port};')
        config=config.replace('listen 80;',f'listen 127.0.0.1:{port};').replace('/var/www/acme',str(root/'var/www/acme'))
        token=root/'var/www/acme/.well-known/acme-challenge/check';token.write_bytes(b'IPv4 ACME OK')
        temporary='\n'.join(f'{kind}_temp_path {root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        conf=root/'test.conf';conf.write_text(f'load_module /usr/lib/nginx/modules/ngx_stream_module.so; pid {root}/pid; error_log stderr; events {{}} stream {{{stream}}} http {{ access_log off; {temporary}\n{main}\n{config}\n}}')
        command=[nginx,'-e','stderr','-p',str(root)+'/', '-c',str(conf)]
        subprocess.run([*command,'-t'],check=True,capture_output=True,timeout=10)
        with (root/'private.log').open('wb') as log:
            child=subprocess.Popen([*command,'-g','daemon off;'],stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+5
                while True:
                    assert child.poll() is None,'nginx exited'
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                    except OSError:
                        if time.monotonic()>=deadline:raise AssertionError('nginx readiness deadline')
                        time.sleep(.02)
                for domain in ('deploy.example','vision.example'):
                    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                    try:
                        connection.request('GET','/.well-known/acme-challenge/check',headers={'Host':domain})
                        response=connection.getresponse()
                        assert response.status==200 and response.read()==b'IPv4 ACME OK'
                    finally:connection.close()
            finally:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)


class InstallerCompatibility(unittest.TestCase):
    def test_real_nginx_http_maps_with_small_cacheline_and_existing_policy(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertTrue(nginx,'Real nginx required')
        qemu=shutil.which('qemu-x86_64')
        self.assertTrue(qemu,'Existing CI qemu-user dependency required')
        # Unmodified packaged amd64 nginx: this CPUID selects nginx's 32-byte
        # cacheline branch. An explicit bucket 32 on a modern CPU rounds to 64.
        commands=([nginx],[qemu,'-cpu','qemu64,vendor=GenuineIntel,family=6,model=6',nginx])
        token='AbCdEf0123456789'
        with tempfile.TemporaryDirectory(prefix='http-map-hash-') as directory:
            root=Path(directory); (root/'optional').mkdir(); http_name_certificate(root)
            configs=http_name_configs(root,('panel.example','cover.example','vision.example'),False,(31231,31232,31233,31234))
            policy=root/'policy.conf';conf=root/'nginx.conf'
            for command in commands:
                for bucket in (None,32,64,128):
                    policy_text=('' if bucket is None else f'map_hash_bucket_size {bucket};\n')
                    policy_text+='map $arg_probe $foreign_map { default 0; fixture 1; }\n'
                    policy.write_text(policy_text)
                    for stage,text in configs.items():
                        with self.subTest(emulated=len(command)>1,bucket=bucket,stage=stage):
                            # Policy in a separate HTTP include, as in distro conf.d;
                            # no assumptions about nginx.conf indentation/line layout.
                            conf.write_text(text.replace('http {',f'http {{ include {policy};',1))
                            result=subprocess.run([*command,'-t','-e','stderr','-p',directory+'/', '-c',str(conf)],capture_output=True,text=True,timeout=15)
                            self.assertEqual(result.returncode,0,result.stderr)
                            self.assertNotIn('[warn]',result.stderr)
                            self.assertEqual(policy.read_text(),policy_text)
                from test_personal_xhttp import MAIN
                main=render(MAIN,diag_token=token)
                diag=re.search(r'map \$cookie_diag_key \$diag_auth \{.*?^\}',main,re.M|re.S).group()
                maps=render('cat > /etc/nginx/sites-available/00-maps.conf')
                with socket.socket() as reserved:
                    reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
                temporary='\n'.join(f'{kind}_temp_path {root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
                conf.write_text(f'pid {root}/pid; error_log stderr; events {{}} http {{ access_log off; {temporary}\n{maps}\n{diag}\nserver {{ listen 127.0.0.1:{port}; return 200 "$diag_auth:$serve_clash_yaml"; }} }}')
                process=subprocess.Popen([*command,'-e','stderr','-p',directory+'/', '-c',str(conf),'-g','daemon off; master_process off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    deadline=time.monotonic()+5
                    while True:
                        self.assertIsNone(process.poll(),'nginx HTTP map startup failed')
                        try:
                            with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                        except OSError:
                            if time.monotonic()>=deadline:self.fail('nginx HTTP map readiness deadline')
                            time.sleep(.02)
                    for cookie,allowed in (('',0),(token,1),(token.lower(),1),(token.upper(),1),('x'+token,0),(token+'x',0),('wrong',0)):
                        connection=http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                        try:
                            connection.request('GET','/',headers={'Cookie':'diag_key='+cookie,'User-Agent':'ClashMeta/1.19.30; mihomo/1.19.30','x-hwid':'fixture'})
                            response=connection.getresponse()
                            self.assertEqual((response.status,response.read()),(200,f'{allowed}:0'.encode()))
                        finally:connection.close()
                finally:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

    def test_repeated_nginx_configuration_preserves_existing_http_policy(self):
        from certificate_fixtures import relocate
        from test_personal_xhttp import FIXTURE
        with tempfile.TemporaryDirectory(prefix='nginx-repeat-') as directory:
            root=Path(directory);nginx=root/'etc/nginx';nginx.mkdir(parents=True)
            policy=nginx/'conf.d/policy.conf';policy.parent.mkdir()
            policy.write_text('map_hash_bucket_size 128;\nmap $arg_probe $foreign_map { default 0; }\n')
            # Distro packages already provide this module declaration.
            (nginx/'modules.conf').write_text('load_module modules/ngx_stream_module.so;\n')
            config=nginx/'nginx.conf';config.write_text(f'events {{}}\n  http  {{ include {policy}; }}\n')
            stubs='''nginx() { [[ "${1:-}" != -v ]] || echo 'nginx version: nginx/1.24.0' >&2; return 0; }
systemctl() { :; }
install() { local -a args=(); while (($#)); do case "$1" in -o|-g) shift 2;; *) args+=("$1"); shift;; esac; done; command install "${args[@]}"; }
'''
            source='\n'.join(relocate(complete_function(n),root) for n in ('ipv6_available','prepare_acme_webroot','setup_acme_http','configure_nginx'))
            snapshots=[]
            for iteration in range(2):
                result=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\nsetup_acme_http && configure_nginx'],env={**os.environ,**FIXTURE},capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr)
                snapshots.append({str(p.relative_to(nginx)):p.read_bytes() for p in nginx.rglob('*') if p.is_file()})
            self.assertEqual(snapshots[0],snapshots[1])
            self.assertEqual(policy.read_text(),'map_hash_bucket_size 128;\nmap $arg_probe $foreign_map { default 0; }\n')
            self.assertEqual(config.read_text().count('http  {'),1)

    def test_real_nginx_http_all_permitted_hostname_lengths(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertTrue(nginx,'Real nginx required')
        cases=[tuple(dns_name(n,c) for c in 'abv') for n in range(3,254)]
        cases += [('a.'*125+'aaa','b.'*125+'bbb','v.'*125+'vvv'),
                  ('.'.join(['xn--e1afmkfd']*11+['xn--p1ai']),'cover.example','vision.example'),
                  ('an.'+dns_name(250),'c0.'+dns_name(250),dns_name(253,'v'))]
        valid=shell(('valid_hostname',),'for name in "$@"; do valid_hostname "$name" || exit 1; done',
                    stubs='set -- '+' '.join(name for names in cases for name in names))
        self.assertEqual(valid.returncode,0,valid.stderr)
        vision=helper('vision')
        families=(False,True) if vision.ipv6_available() else (False,)
        with tempfile.TemporaryDirectory(prefix='http-names-') as directory:
            root=Path(directory); conf=root/'nginx.conf'; http_name_certificate(root)
            with socket.socket() as a,socket.socket() as b,socket.socket() as c,socket.socket() as d:
                for listener in (a,b,c,d): listener.bind(('127.0.0.1',0))
                ports=[listener.getsockname()[1] for listener in (a,b,c,d)]
            for names in cases:
                for name in names: self.assertEqual(vision.domain_name(name),name)
                for ipv6 in families:
                    for stage,text in http_name_configs(root,names,ipv6,ports).items():
                        with self.subTest(length=len(names[0]),prefix=names[0][:4],ipv6=ipv6,stage=stage):
                            conf.write_text(text)
                            result=subprocess.run([nginx,'-t','-e','stderr','-p',directory+'/', '-c',str(conf)],
                                                  capture_output=True,text=True,timeout=10)
                            self.assertEqual(result.returncode,0,result.stderr)
                            if max(map(len,names))<=46: self.assertNotIn('[warn]',result.stderr)

    def test_real_nginx_http_long_host_routing_acme_and_vision_fallback(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertTrue(nginx,'Real nginx required')
        families=(False,True) if helper('vision').ipv6_available() else (False,)
        for length in (13,47,111,239,253):
            names=tuple(dns_name(length,c) for c in 'abv')
            for ipv6 in families:
                with self.subTest(length=length,ipv6=ipv6),tempfile.TemporaryDirectory(prefix='http-routing-') as directory:
                    root=Path(directory); http_name_certificate(root)
                    (root/'acme/.well-known/acme-challenge').mkdir(parents=True)
                    (root/'acme/.well-known/acme-challenge/check').write_bytes(b'ACME exact bytes')
                    (root/'html').mkdir(); (root/'html/index.html').write_bytes(b'Vision fallback exact bytes')
                    # Keep sockets open during allocation so this fixture's TCP ports are distinct.
                    with socket.socket() as a,socket.socket() as b,socket.socket() as c,socket.socket() as d:
                        for listener in (a,b,c,d): listener.bind(('127.0.0.1',0))
                        ports=[listener.getsockname()[1] for listener in (a,b,c,d)]
                    configs=http_name_configs(root,names,ipv6,ports)
                    for stage in ('initial','vision-acme','fallback'):
                        text=configs[stage]
                        access=root/'access.log'; access.unlink(missing_ok=True)
                        text=text.replace('http { access_log off;',f'http {{ log_format selected "$server_name|$host|$request_uri|$status"; access_log {access} selected;')
                        conf=root/'nginx.conf'; conf.write_text(text)
                        command=[nginx,'-e','stderr','-p',directory+'/', '-c',str(conf)]
                        syntax=subprocess.run([*command,'-t'],capture_output=True,text=True,timeout=10)
                        self.assertEqual(syntax.returncode,0,syntax.stderr)
                        with (root/'private.log').open('wb') as log:
                            child=subprocess.Popen([*command,'-g','daemon off;'],stdout=log,stderr=log)
                            expected=[]
                            try:
                                deadline=time.monotonic()+5
                                while True:
                                    self.assertIsNone(child.poll(),'nginx exited: '+(root/'private.log').read_text())
                                    try:
                                        with socket.create_connection(('::1' if ipv6 else '127.0.0.1',ports[0]),timeout=.1): break
                                    except OSError:
                                        if time.monotonic()>=deadline: self.fail('HTTP listener readiness deadline')
                                        time.sleep(.02)
                                for name in (*names,names[2].upper(),'unknown.example'):
                                    selected=names[2] if stage!='initial' and name.lower()==names[2] else names[0]
                                    for path in ('/.well-known/acme-challenge/check?nonce=fixture','/ordinary?keep=1'):
                                        connection=http.client.HTTPConnection('::1' if ipv6 else '127.0.0.1',ports[0],timeout=3)
                                        try:
                                            connection.request('GET',path,headers={'Host':name})
                                            response=connection.getresponse(); body=response.read()
                                            if path.startswith('/.well-known/'):
                                                self.assertEqual((response.status,body),(200,b'ACME exact bytes'))
                                            else:
                                                self.assertEqual(response.status,301)
                                                self.assertEqual(response.getheader('Location'),'https://'+name.lower()+path)
                                            expected.append(f'{selected}|{name.lower()}|{path}|{response.status}')
                                        finally: connection.close()
                                if stage=='fallback':
                                    for name in names:
                                        with socket.create_connection(('127.0.0.1',ports[3]),timeout=3) as client:
                                            client.sendall(('PROXY TCP4 127.0.0.1 127.0.0.1 12345 80\r\nGET / HTTP/1.1\r\nHost: '+name+'\r\nConnection: close\r\n\r\n').encode())
                                            response=http.client.HTTPResponse(client); response.begin(); body=response.read()
                                            self.assertEqual(response.status,200 if name==names[2] else 404)
                                            if name==names[2]: self.assertEqual(body,b'Vision fallback exact bytes')
                                            else: self.assertNotIn(b'Vision fallback exact bytes',body)
                                            expected.append(f'{names[2]}|{name}|/|{response.status}')
                            finally:
                                child.terminate()
                                try: child.wait(timeout=5)
                                except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
                            self.assertEqual(access.read_text().splitlines(),expected)

    def test_real_nginx_stream_all_permitted_hostname_lengths(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertTrue(nginx,'Real nginx required')
        cases=[(dns_name(n),dns_name(n,'b')) for n in range(3,254)]
        cases += [('a.'*125+'aaa','b.'*125+'bbb'),
                  ('.'.join(['xn--e1afmkfd']*11+['xn--p1ai']),'cover.example'),
                  ('an.'+dns_name(250),'c0.'+dns_name(250))]  # Same nginx hash; distinct valid keys.
        maps=render('cat > /etc/nginx/sites-available/00-maps.conf')
        with tempfile.TemporaryDirectory(prefix='stream-names-') as directory:
            root=Path(directory); conf=root/'nginx.conf'
            for panel,reality in cases:
                with self.subTest(panel_length=len(panel),reality_length=len(reality),prefix=panel[:4]):
                    valid=shell(('valid_hostname',),'valid_hostname "$domain" && valid_hostname "$reality_domain"',
                                {'domain':panel,'reality_domain':reality})
                    self.assertEqual(valid.returncode,0,valid.stderr)
                    stream=render('cat > /etc/nginx/stream-enabled/stream.conf',domain=panel,reality_domain=reality,ipv6_listen='')
                    stream=stream.replace('listen     443;','listen 127.0.0.1:31235;')
                    conf.write_text(f'load_module /usr/lib/nginx/modules/ngx_stream_module.so; pid {root}/pid; error_log stderr; events {{}} stream {{{stream}}} http {{ access_log off; {maps} }}')
                    result=subprocess.run([nginx,'-t','-e','stderr','-p',directory+'/', '-c',str(conf)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    if len(panel)<=46 and len(reality)<=46:
                        self.assertNotIn('[warn]',result.stderr)

    def test_real_nginx_stream_sni_vision_and_http_maps(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertTrue(nginx,'Real nginx required')
        class Backend(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                proxy=self.rfile.readline(108)
                header=self.rfile.read(5)
                body=self.rfile.read(int.from_bytes(header[3:5],'big'))
                self.server.received.append((proxy,header+body))
                self.wfile.write(self.server.marker)
        cases=[('panel.example','reality.example'),(dns_name(253),dns_name(253,'b')),
               ('an.'+dns_name(250),'c0.'+dns_name(250))]
        for panel,reality in cases:
            with self.subTest(panel=panel[:16]),tempfile.TemporaryDirectory(prefix='sni-route-') as directory:
                root=Path(directory); servers=[]; threads=[]; child=None
                try:
                    for i in range(3):
                        server=socketserver.ThreadingTCPServer(('127.0.0.1',0),Backend)
                        servers.append(server); server.daemon_threads=True
                        server.marker=f'upstream-{i}'.encode(); server.received=[]
                        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
                        thread.start(); threads.append(thread)
                    with socket.socket() as first,socket.socket() as second:
                        first.bind(('127.0.0.1',0)); second.bind(('127.0.0.1',0))
                        public,http_port=first.getsockname()[1],second.getsockname()[1]
                    stream=render('cat > /etc/nginx/stream-enabled/stream.conf',domain=panel,reality_domain=reality,ipv6_listen='')
                    for old,server in zip(('8443','7443'),servers):
                        stream=stream.replace('127.0.0.1:'+old,'127.0.0.1:'+str(server.server_address[1]))
                    stream=stream.replace('listen     443;',f'listen 127.0.0.1:{public};')
                    vision=dns_name(253,'v')
                    stream=helper('vision').stream_config(stream,vision,servers[2].server_address[1])
                    maps=render('cat > /etc/nginx/sites-available/00-maps.conf')
                    temporary='\n'.join(f'{kind}_temp_path {root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
                    conf=root/'nginx.conf'
                    conf.write_text(f'load_module /usr/lib/nginx/modules/ngx_stream_module.so; pid {root}/pid; error_log stderr; events {{}} stream {{{stream}}} http {{ access_log off; {temporary} {maps} server {{ listen 127.0.0.1:{http_port}; return 200 "$is_clash_ua:$serve_clash_yaml"; }} }}')
                    command=[nginx,'-e','stderr','-p',directory+'/', '-c',str(conf)]
                    result=subprocess.run([*command,'-t'],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr)
                    with (root/'private.log').open('wb') as log:
                        child=subprocess.Popen([*command,'-g','daemon off;'],stdout=log,stderr=log)
                        deadline=time.monotonic()+5
                        while True:
                            self.assertIsNone(child.poll(),'nginx exited')
                            try:
                                with socket.create_connection(('127.0.0.1',http_port),timeout=.1): break
                            except OSError:
                                if time.monotonic()>=deadline: self.fail('nginx listener readiness deadline')
                                time.sleep(.02)
                        # Send real TLS ClientHello bytes; record the selected upstream and PROXY header.
                        context=ssl.create_default_context()
                        for name,index in ((panel,1),(reality,0),(vision,2),('unknown.example',0),(panel.upper(),1)):
                            incoming,outgoing=ssl.MemoryBIO(),ssl.MemoryBIO()
                            tls=context.wrap_bio(incoming,outgoing,server_side=False,server_hostname=name)
                            with self.assertRaises(ssl.SSLWantReadError): tls.do_handshake()
                            hello=outgoing.read()
                            with socket.create_connection(('127.0.0.1',public),timeout=3) as client:
                                client.sendall(hello)
                                received=b''
                                while len(received)<len(servers[index].marker):
                                    block=client.recv(64)
                                    if not block: break
                                    received+=block
                            self.assertEqual(received,servers[index].marker,name)
                            proxy,forwarded=servers[index].received[-1]
                            self.assertTrue(proxy.startswith(b'PROXY TCP4 127.0.0.1 127.0.0.1 '),proxy)
                            self.assertEqual(forwarded,hello)
                        for path,agent,hwid,expected in (
                                ('/','Mihomo','','1:1'),('/?provider=1','Mihomo','','1:0'),('/','ordinary','','0:0'),
                                ('/','ClashMeta/1.19.30; mihomo/1.19.30','fixture','1:0'),
                                ('/?other=1','ClashMeta/2.0.0; mihomo/2.0.0','fixture','1:0'),
                                ('/','ClashMeta/1.19.30; mihomo/1.19.30','','1:1'),
                                ('/','Mihomo','fixture','1:1'),
                                ('/','ClashMetaForAndroid/2.11.33.Meta','fixture','1:1'),
                                ('/','Happ/5.6.0','fixture','0:0')):
                            connection=http.client.HTTPConnection('127.0.0.1',http_port,timeout=3)
                            try:
                                connection.request('GET',path,headers={'User-Agent':agent,'x-hwid':hwid})
                                response=connection.getresponse()
                                self.assertEqual((response.status,response.read()),(200,expected.encode()))
                            finally: connection.close()
                finally:
                    if child is not None:
                        child.terminate()
                        try: child.wait(timeout=5)
                        except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
                    for server in servers: server.shutdown(); server.server_close()
                    for thread in threads: thread.join(timeout=5)

    def test_domain_syntax_canonicalization_and_precleanup_failure(self):
        names=('valid_hostname','validate_domains')
        for panel,reality in (('Panel.Example.COM','Reality.Example.COM'),
                              ('xn--e1afmkfd.xn--p1ai','cover.example'),
                              ('.'.join(['a'*63]*3+['a'*61]),'cover.example'),
                              ('203-0-113-7.sslip.io','reality.203-0-113-7.sslip.io')):
            with self.subTest(panel=panel,reality=reality):
                result=shell(names,'validate_domains || exit 1; printf "%s|%s" "$domain" "$reality_domain"',
                             {'domain':panel,'reality_domain':reality})
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,panel.lower()+'|'+reality.lower())
        bad=('','https://panel.example','panel.example/path','panel.example:443','pan el.example',
             ' panel.example','panel.example ','panel.example\nother.example','panel.\texample','bad_name.example','-bad.example','bad-.example',
             'a..example','panel.example.','панель.example','a'*64+'.example',
             '.'.join(['a'*63]*4))
        stubs='\n'.join(n+'() { :; };' for n in re.findall(r'^(\w+)\(\)\s*\{',SOURCE,re.M)
                        if n not in ('main','validate_domains','valid_hostname','msg_err','ui_text'))
        stubs+='\nclean_previous_install() { echo CLEANUP_REACHED; return 1; };\n'
        for panel,reality in [(b,'reality.example') for b in bad]+[('Panel.Example','panel.example')]:
            with self.subTest(panel=panel):
                result=shell((*names,'main'),'main',{'domain':panel,'reality_domain':reality,
                    'INSTALL_VISION':'n','CREATE_CLIENT':'n','INSTALL_SECURITY':'n','INSTALL_AWG':'n'},stubs)
                self.assertNotEqual(result.returncode,0)
                self.assertNotIn('CLEANUP_REACHED',result.stdout)
                self.assertRegex(result.stderr,'(?i)domain|hostname')

    def test_supported_os_release_quoted_unquoted_and_no_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release=root/'os-release';marker=root/'executed'
            source=function('check_os').replace('/etc/os-release',str(release))
            for distro,version in (('ubuntu','24.04'),('ubuntu','26.04'),('debian','13')):
                for quote in ('','"',"'"):
                    with self.subTest(distro=distro,version=version,quote=quote):
                        release.write_text(f'ID={quote}{distro}{quote}\nVERSION_ID={quote}{version}{quote}')
                        r=subprocess.run(['bash','-u','-c','msg_err() { :; };\n'+source+'\ncheck_os; echo CLEANUP_REACHED'],capture_output=True,text=True)
                        self.assertEqual(r.returncode,0,r.stderr)
                        self.assertIn('CLEANUP_REACHED',r.stdout)
            for data in ('ID=ubuntu\nVERSION_ID=22.04\n','VERSION_ID=13\n',
                         'ID=debian-extra\nVERSION_ID=13\n','ID="debian\nVERSION_ID=13\n',
                         'ID=debian\nVERSION_ID="13\n',f'ID=$(touch {marker})\nVERSION_ID=13\n'):
                release.write_text(data)
                r=subprocess.run(['bash','-u','-c','msg_err() { :; };\n'+source+'\ncheck_os; echo CLEANUP_REACHED'],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('CLEANUP_REACHED',r.stdout)
                self.assertFalse(marker.exists())

    def test_tcp_port_allocation_repeats_occupied_ports_no_nc_and_late_vision(self):
        main=function('main')
        self.assertLess(main.index('preflight_panel_release'),main.index('make_port sub_port'))
        self.assertLess(main.index('make_port sub_port'),main.index('clean_previous_install'))
        with tempfile.TemporaryDirectory() as directory, socket.socket() as occupied:
            root=Path(directory);occupied.bind(('127.0.0.1',0));busy=occupied.getsockname()[1]
            # Deliberately bind without listen: a TCP connect probe would miss it.
            result=shell(('check_free',),'check_free "$BUSY"',{'BUSY':str(busy)},'nc() { return 127; };')
            self.assertEqual(result.returncode,3,result.stderr)
            counter=root/'counter';counter.write_text('0')
            stubs='''get_port() { local n; n=$(cat "$COUNTER"); echo $((n+1)) > "$COUNTER"; if ((n<2)); then echo "$BUSY"; else echo $((30000+(n-2)/2)); fi; }
nc() { echo NC_MUST_NOT_BE_USED >&2; return 127; }
'''
            body='make_port sub_port panel_port ws_port trojan_port mtr_backend_port || exit 1; make_port vision_port fallback_port || exit 1; printf "%s\\n" "$sub_port" "$panel_port" "$ws_port" "$trojan_port" "$mtr_backend_port" "$vision_port" "$fallback_port"'
            r=shell(('check_free','make_port'),body,{'COUNTER':str(counter),'BUSY':str(busy)},stubs)
            self.assertEqual(r.returncode,0,r.stderr)
            ports=list(map(int,r.stdout.split()))
            self.assertEqual(len(ports),7);self.assertEqual(len(set(ports)),7);self.assertNotIn(busy,ports)
            self.assertNotIn('NC_MUST_NOT_BE_USED',r.stderr)
            constant=shell(('check_free','make_port'),body,stubs='get_port() { echo 30000; }; nc() { return 127; };')
            self.assertEqual(constant.returncode,0,constant.stderr)
            repeated=list(map(int,constant.stdout.split()))
            self.assertEqual(len(repeated),7);self.assertEqual(len(set(repeated)),7)

        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            udp.bind(('127.0.0.1',0))
            r=shell(('check_free',),'check_free "$PORT"',{'PORT':str(udp.getsockname()[1])},'nc() { return 127; };')
            self.assertEqual(r.returncode,0,'UDP occupancy must not reserve the TCP namespace')

    def test_port_exhaustion_and_probe_errors_stop_bounded(self):
        for probe in ('check_free() { return 3; };','python3() { return 127; };','python3() { return 1; };'):
            r=shell(('check_free','make_port'),'make_port selected; exit "$?"',
                    stubs='get_port() { echo 32000; };\n'+probe,timeout=4)
            self.assertNotEqual(r.returncode,0)
            self.assertRegex(r.stderr,'(?i)port|probe')

    def test_vision_nat_and_ipv4_only_do_not_require_matching_route_ip(self):
        with tempfile.TemporaryDirectory() as directory:
            stubs='''curl() { if [[ "$*" == *-o* ]]; then printf 'pass\\n' > "${@: -1}"; fi; }
preflight_vision_artifacts() { :; }
get_server_ip() { IP6=''; echo ROUTE_LOOKUP >&2; }
python3() {
    if [[ $# == 6 && $1 == - ]]; then
        command python3 -c 'import socket,sys; socket.getaddrinfo=lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,"",("203.0.113.10",443))]; exec(sys.stdin.read())' "${@:2}"
    else command python3 "$@"; fi
}
'''
            for interface in ('203.0.113.10','10.0.0.10'):
                with self.subTest(interface=interface):
                    env={'PANEL_TAG':'v3.10.0','PANEL_STAGE':directory,'GITHUB_RAW':'https://example.invalid',
                         'INSTALL_VISION':'y','INSTALL_SECURITY':'n','CREATE_CLIENT':'n',
                         'domain':'panel.example','reality_domain':'reality.example','vision_domain':'vision.example',
                         'IP4':interface,'IP6':''}
                    r=shell(('valid_hostname','preflight_integrated_features'),
                            'preflight_integrated_features || exit 1; echo "$vision_domain"',env,stubs)
                    self.assertEqual(r.returncode,0,r.stderr)
                    self.assertEqual(r.stdout.strip(),'vision.example')
                    self.assertNotIn('ROUTE_LOOKUP',r.stderr)
            for bad in ('https://vision.example','panel.EXAMPLE','REALITY.example','vision.example.','bad_.example'):
                r=shell(('valid_hostname','preflight_integrated_features'),
                        'preflight_integrated_features && echo CLEANUP_REACHED', {**env,'vision_domain':bad},stubs)
                self.assertNotEqual(r.returncode,0)
                self.assertNotIn('CLEANUP_REACHED',r.stdout)

    def test_ipv6_family_capability_and_exact_vision_artifacts(self):
        vision=helper('vision');real_socket=socket.socket
        for available in (True,False):
            def create(family,*args,**kwargs):
                if family==socket.AF_INET6 and not available:raise OSError(errno.EAFNOSUPPORT,'disabled')
                return real_socket(family,*args,**kwargs)
            with patch.object(vision.socket,'socket',side_effect=create):
                config=vision.acme_config('vision.example')
            self.assertEqual('listen [::]:80;' in config,available)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);site=root/'site';acme=root/'acme'
            site.write_text(vision.fallback_config('vision.example',12001))
            legacy=vision.MARKER+'server {\n    listen 80;\n    listen [::]:80;\n    server_name vision.example;\n    location ^~ /.well-known/acme-challenge/ { root /var/www/acme; try_files $uri =404; }\n    location / { return 301 https://$host$request_uri; }\n}\n'
            for text in (legacy,legacy.replace('    listen [::]:80;\n','')):
                acme.write_text(text)
                with patch.object(vision,'ipv6_available',return_value=False):
                    self.assertEqual(vision.nginx_artifact_domain(site,acme),'vision.example')
                acme.write_text(text.replace('root /var/www/acme','root /foreign'))
                with self.assertRaises(ValueError):vision.nginx_artifact_domain(site,acme)

    def test_real_nginx_ipv4_main_and_vision_acme(self):
        nginx_ipv4_acme(simulate=True)

    def test_first_nginx_start_preserves_default_only_with_ipv6(self):
        from certificate_fixtures import relocate
        for ipv6 in ('y','n'):
            with self.subTest(ipv6=ipv6),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);default=root/'etc/nginx/sites-enabled/default'
                default.parent.mkdir(parents=True);package=root/'package-default'
                package.write_bytes(b'listen [::]:80;\n');default.symlink_to(package)
                (root/'etc/os-release').write_text('VERSION_ID="26.04"\n')
                stubs='''apt_system() { :; }; python3() { :; }; command() { :; }
ipv6_available() { [[ "$IPV6" == y ]]; }
systemctl() {
    if [[ "$*" == 'enable --now nginx' ]]; then
        if [[ -L "$DEFAULT" ]]; then echo default-present; [[ "$IPV6" == y ]]; else echo default-absent; fi
    fi
}
'''
                result=subprocess.run(['bash','-u','-c',stubs+relocate(function('install_packages'),root)+'\ninstall_packages'],
                    env={**os.environ,'INSTALL':'y','IPV6':ipv6,'DEFAULT':str(default)},
                    capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),'default-present' if ipv6=='y' else 'default-absent')
                self.assertEqual(default.is_symlink(),ipv6=='y')
                self.assertEqual(package.read_bytes(),b'listen [::]:80;\n')

    def test_dns_checkpoint_writer_reader_roundtrip_and_security(self):
        security=helper('security')
        def command(*args,**kwargs):
            if args[1]=='is-active':return 'inactive'
            if args[1]=='is-enabled':return 'disabled'
            return ''
        targets=(None,'/run/systemd/resolve/stub-resolv.conf','../run/systemd/resolve/resolv.conf',
                 '/run/NetworkManager/resolv.conf','/run/resolvconf/resolv.conf','../run/custom-resolver/missing')
        for target in targets:
            with self.subTest(target=target),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'etc').mkdir();resolv=root/'etc/resolv.conf'
                if target is None:resolv.write_text('nameserver 192.0.2.1\n')
                else:resolv.symlink_to(target)
                with patch.object(Path,'stat',root_stat),patch.object(security,'command',side_effect=command):
                    txn=security.Transaction(root,services=('systemd-resolved.service',),files=(security.FILES[-1],))
                    self.addCleanup(txn.temp.cleanup);checkpoint=root/'checkpoint';txn.save_dns(checkpoint)
                    loaded=security.Transaction.load_dns(checkpoint,root);self.addCleanup(loaded.temp.cleanup)
                    resolv.unlink();resolv.write_text('temporary DNS\n');loaded.rollback()
                    if target is None:self.assertEqual(resolv.read_text(),'nameserver 192.0.2.1\n')
                    else:self.assertTrue(resolv.is_symlink());self.assertEqual(os.readlink(resolv),target)
                    # The accepted reader must still reject unrelated objects/metadata/modes.
                    extra=checkpoint/'extra';extra.write_text('foreign')
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    extra.unlink();meta=checkpoint/'state.json';original=meta.read_text()
                    meta.write_text(original.replace('systemd-resolved.service','ssh.service'))
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    meta.write_text(original);meta.chmod(0o666)
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    meta.chmod(0o600);checkpoint.chmod(0o777)
                    with self.assertRaises(ValueError):security.Transaction.load_dns(checkpoint,root)
                    checkpoint.chmod(0o700)
                    for bad_owner in (checkpoint,meta,checkpoint/'1'):
                        def wrong_owner(path,*args,**kwargs):
                            value=root_stat(path,*args,**kwargs)
                            if path==bad_owner:
                                fields=list(value);fields[4]=1000;value=os.stat_result(fields)
                            return value
                        with patch.object(Path,'stat',wrong_owner), self.assertRaises(ValueError):
                            security.Transaction.load_dns(checkpoint,root)


    def test_dns_real_rollback_failure_remains_unverified(self):
        security=helper('security')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'etc').mkdir();resolv=root/'etc/resolv.conf'
            target='/run/NetworkManager/resolv.conf';resolv.symlink_to(target)
            policy=root/security.FILES[-1].lstrip('/');policy.parent.mkdir(parents=True)
            def command(*args,**kwargs):
                if args[0]=='getent':raise OSError('controlled resolution failure')
                if args[1]=='is-active':return 'inactive'
                if args[1]=='is-enabled':return 'disabled'
                return ''
            with patch.object(Path,'stat',root_stat),patch.object(security,'command',side_effect=command):
                txn=security.Transaction(root,services=('systemd-resolved.service',),files=(security.FILES[-1],))
                self.addCleanup(txn.temp.cleanup);checkpoint=root/'checkpoint';txn.save_dns(checkpoint)
                resolv.unlink();resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf');policy.write_text(security.DOT)
                result=security.rollback_dns_checkpoint(checkpoint,root)
                self.assertEqual(result['status'],'failed_unverified')
                self.assertEqual(os.readlink(resolv),target)

    def test_vision_certificate_failure_reaches_acme_and_never_reports_ready(self):
        from certificate_fixtures import relocate
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in ('etc/nginx/sites-available','etc/nginx/sites-enabled','etc/letsencrypt/renewal-hooks/deploy'):
                (root/path).mkdir(parents=True)
            stubs="""nginx() { :; }; systemctl() { :; }; check_installation() { :; }; msg_warn() { :; }
python3() { if [[ $1 == - ]]; then command python3 \"$@\"; else echo '# ACME fixture'; fi; }
certbot() { echo \"$1\" >> \"$MARKER\"; return 33; }
"""
            source='\n'.join(function(n) for n in ('get_port','check_free','make_port'))+'\n'+relocate(function('install_vision'),root)
            body='status=0; install_vision || status=$?; printf "%s|%s" "$status" "$VISION_RESULT"; exit "$status"'
            r=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\n'+body],
                env={**os.environ,'MARKER':str(root/'certbot'),'vision_domain':'vision.example','PANEL_STAGE':str(root)},capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertEqual((root/'certbot').read_text().splitlines(),['certonly'])
            self.assertEqual(r.stdout,'1|failed_rolled_back')
            self.assertFalse((root/'etc/nginx/sites-available/vision-acme.conf').exists())

    def test_actual_vision_allocation_keeps_earlier_project_ports(self):
        from certificate_fixtures import relocate
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);counter=root/'counter';counter.write_text('0')
            (root/'etc/nginx/sites-available').mkdir(parents=True)
            (root/'etc/letsencrypt/renewal-hooks/deploy').mkdir(parents=True)
            stubs="""get_port() { local n; n=$(cat \"$COUNTER\"); echo $((n+1)) > \"$COUNTER\"; echo $((35000+n/2)); }
nginx() { :; }; systemctl() { :; }; check_installation() { :; }; msg_warn() { :; }
python3() { if [[ $1 == - ]]; then command python3 \"$@\"; else return 1; fi; }
"""
            source='\n'.join(function(n) for n in ('check_free','make_port'))+'\n'+relocate(function('install_vision'),root)
            body='make_port sub_port panel_port ws_port trojan_port mtr_backend_port || exit 1; install_vision || :; printf "%s\\n" "${ALLOCATED_TCP_PORTS[@]}"'
            r=subprocess.run(['bash','-u','-c',source+'\n'+stubs+'\n'+body],
                env={**os.environ,'COUNTER':str(counter),'vision_domain':'vision.example','PANEL_STAGE':str(root)},capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            ports=list(map(int,r.stdout.split()));self.assertEqual(len(ports),7);self.assertEqual(len(set(ports)),7)

    def test_vision_port_failure_preserves_target_and_reports_no_unverified_rollback(self):
        from certificate_fixtures import relocate
        for partial in (False,True):
            with self.subTest(partial=partial),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);sentinel=root/'etc/nginx/sites-available/vision-acme.conf'
                sentinel.parent.mkdir(parents=True);sentinel.write_bytes(b'previous configuration\n')
                before=(sentinel.read_bytes(),sentinel.stat())
                source=relocate(function('install_vision'),root)
                stubs='''make_port() { [[ "$PARTIAL" != True ]] || printf -v "$1" 31001; return 1; }
msg_warn() { echo "$*" >&2; }
nginx() { echo MUTATION_REACHED >&2; return 77; }
systemctl() { echo MUTATION_REACHED >&2; return 77; }
python3() { echo MUTATION_REACHED >&2; return 77; }
certbot() { echo MUTATION_REACHED >&2; return 77; }
'''
                result=subprocess.run(['bash','-u','-c',source+'\n'+stubs+
                    '\nstatus=0; install_vision || status=$?; printf "%s|%s" "$status" "$VISION_RESULT"; exit "$status"'],
                    env={**os.environ,'PARTIAL':str(partial),'vision_domain':'vision.example'},
                    capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,1,result.stderr)
                self.assertEqual(result.stdout,'1|failed_rolled_back')
                self.assertNotIn('MUTATION_REACHED',result.stderr)
                self.assertEqual((sentinel.read_bytes(),sentinel.stat()),before)


if __name__=='__main__':unittest.main()
