"""Real loopback services; host installation and systemd remain outside this suite."""
import base64
import errno
import hashlib
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import ssl
import sys
import struct
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

from certificate_fixtures import ROOT, function
from test_real_integration import download, port, stop

AGH_VERSION = 'v0.107.79'
PEBBLE_VERSION = 'v2.10.1'
AGH_SHA = 'c48f4a43000665484c5ec28177de11a004759b620dae8f77b2aabefc9ef3687f'
PEBBLE_SHA = '4f2fcb5bca8c85c9cf73ad140fccfc0d2be40bd81ab99879c79b7b8a0b4f70ed'
HELPER = ROOT/'assets/adguard/managed.sh'


def question(name, ident=0x1234):
    labels = b''.join(bytes([len(label)])+label.encode() for label in name.split('.'))+b'\0'
    return struct.pack('!6H',ident,0x100,1,0,0,0)+labels+struct.pack('!HH',1,1)


class RealServices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='service-tools-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.tools = Path(cls.temp.name)
        cached = os.environ.get('SERVICES_ARTIFACTS')
        artifacts = (
            ('agh.tar.gz',AGH_SHA,f'https://github.com/AdguardTeam/AdGuardHome/releases/download/{AGH_VERSION}/AdGuardHome_linux_amd64.tar.gz','AdGuardHome/AdGuardHome','AdGuardHome'),
            ('pebble.tar.gz',PEBBLE_SHA,f'https://github.com/letsencrypt/pebble/releases/download/{PEBBLE_VERSION}/pebble-linux-amd64.tar.gz','pebble-linux-amd64/linux/amd64/pebble','pebble'),
        )
        if os.uname().machine != 'x86_64': raise RuntimeError('Pinned service tools require amd64')
        for name,digest,url,member,target in artifacts:
            archive=cls.tools/name
            if cached: shutil.copyfile(Path(cached)/name,archive)
            else: download(url,archive)
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest: raise ValueError(name+' checksum mismatch')
            with tarfile.open(archive) as tar:
                entries=[m for m in tar if m.name.removeprefix('./')==member]
                if len(entries)!=1: raise ValueError('Missing/duplicate release binary')
                entry=entries[0]
                if not entry.isfile(): raise ValueError('Expected regular executable')
                binary=cls.tools/target
                binary.write_bytes(tar.extractfile(entry).read());binary.chmod(0o755)
        cls.agh,cls.pebble=cls.tools/'AdGuardHome',cls.tools/'pebble'
        cls.nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        for binary in ('certbot','openssl','curl','htpasswd','ss'):
            if not shutil.which(binary): raise RuntimeError('Required service test dependency: '+binary)
        if not cls.nginx: raise RuntimeError('Real nginx required')
        if subprocess.check_output([cls.agh,'--version'],text=True).strip()!='AdGuard Home, version '+AGH_VERSION:
            raise ValueError('Unexpected AdGuard Home version')
        print('\nREAL SERVICES:',Path('/etc/os-release').read_text().split('PRETTY_NAME=')[1].splitlines()[0])
        print('AdGuard Home',AGH_VERSION,'Pebble',PEBBLE_VERSION,flush=True)
        print(subprocess.check_output(['certbot','--version'],text=True).strip(),flush=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='real-services-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.allocated=set();self.upstream_requests=[]
        requests=self.upstream_requests
        def dns_response(packet):
            offset=12;labels=[]
            while packet[offset]:
                length=packet[offset];offset+=1
                labels.append(packet[offset:offset+length].decode('ascii'));offset+=length
            offset+=1;kind,klass=struct.unpack('!HH',packet[offset:offset+4]);end=offset+4
            name='.'.join(labels);requests.append((name,kind))
            address='127.0.0.1' if name in ('panel.example.test','reality.example.test','vision.example.test','broken.example.test','unrelated.example.test','example.com','reality.example.com') else '198.51.100.42'
            data=struct.pack('!6H',int.from_bytes(packet[:2],'big'),0x8180,1,1 if kind==1 else 0,0,0)+packet[12:end]
            if kind==1:data+=b'\xc0\x0c'+struct.pack('!HHIH',1,klass,60,4)+socket.inet_aton(address)
            return data
        class DNS(socketserver.BaseRequestHandler):
            def handle(handler):
                packet,sock=handler.request
                if len(packet)>=12:sock.sendto(dns_response(packet),handler.client_address)
        class DNSTCP(socketserver.BaseRequestHandler):
            def handle(handler):
                handler.request.settimeout(5)
                def exact(size):
                    data=b''
                    while len(data)<size:
                        chunk=handler.request.recv(size-len(data))
                        if not chunk:raise EOFError('DNS TCP EOF')
                        data+=chunk
                    return data
                length=int.from_bytes(exact(2),'big');response=dns_response(exact(length))
                handler.request.sendall(len(response).to_bytes(2,'big')+response)
        for attempt in range(10):
            self.dns=socketserver.ThreadingUDPServer(('127.0.0.1',0),DNS)
            try:
                tcp=socketserver.ThreadingTCPServer(self.dns.server_address,DNSTCP)
                break
            except OSError as error:
                self.dns.server_close()
                if error.errno != errno.EADDRINUSE or attempt == 9:
                    raise
        self.allocated.add(self.dns.server_address[1])
        for server in (self.dns,tcp):
            threading.Thread(target=server.serve_forever,daemon=True).start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        self.http,self.https,self.web,self.native=[port(self.allocated) for _ in range(4)]
        self.acme,self.management=[port(self.allocated) for _ in range(2)]
        self.domain='panel.example.test';self.reality='reality.example.test';self.prefix='adg-AbCdEf123456'
        self.password=os.urandom(16).hex()
        self.cert,self.key=self.root/'cert.pem',self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1','-nodes','-days','2',
                        '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,DNS:'+self.domain+',DNS:'+self.reality,
                        '-out',self.cert,'-keyout',self.key],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
        self.work=self.root/'AdGuardHome';self.work.mkdir()
        shutil.copyfile(self.agh,self.work/'AdGuardHome');(self.work/'AdGuardHome').chmod(0o755)
        self.config=self.work/'AdGuardHome.yaml'
        template=re.search(r'cat > /opt/AdGuardHome/AdGuardHome.yaml <<EOFAGH\n(.*?)\nEOFAGH',function('adguard_stage'),re.S)[1]
        self.assertIn('address: 127.0.0.1:${AGH_WEB_PORT}',template)
        self.assertIn('    - 127.0.0.1',template);self.assertIn('schema_version: 34',template)
        self.assertIn('enabled: false',template);self.assertIn('insecure_enabled: true',template)
        hashed=subprocess.check_output(['htpasswd','-niB','-C','12','admin'],input=(self.password+'\n').encode(),timeout=20).decode().strip().split(':',1)[1]
        template=template.replace('${AGH_WEB_PORT}',str(self.web)).replace('${AGH_DNS_PORT}',str(self.native)).replace('${hash}',hashed)
        template=re.sub(r'  upstream_dns:\n.*?(?=  trusted_proxies:)',f'  upstream_dns:\n    - 127.0.0.1:{self.dns.server_address[1]}\n',template,flags=re.S)
        template=re.sub(r'filters:\n.*?(?=tls:)', 'filters: []\n',template,flags=re.S)
        self.config.write_text(template+'\n');self.config.chmod(0o600)
        (self.work/'managed.json').write_text(json.dumps(dict(version=AGH_VERSION,arch='amd64',domain=self.domain,path=self.prefix,web_port=self.web,dns_port=self.native)))
        self.shell('source "$1"; AGH_DIR="$2"; agh_config',HELPER,self.work)
        self.webroot=self.root/'var/www/acme';(self.webroot/'.well-known/acme-challenge').mkdir(parents=True)

    def shell(self,source,*args):
        result=subprocess.run(['bash','-c',source,'fixture',*map(str,args)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.replace(self.password,'[redacted]'))
        return result.stdout

    def launch(self,args,label,env=None):
        log=open(self.root/(label+'.log'),'wb');self.addCleanup(log.close)
        process=subprocess.Popen(list(map(str,args)),cwd=self.root,env=env,stdout=log,stderr=log,start_new_session=True)
        self.addCleanup(stop,process)
        return process

    def ready(self,process,number):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            self.assertIsNone(process.poll(),'Service exited before readiness')
            try:
                with socket.create_connection(('127.0.0.1',number),timeout=.2):return
            except OSError: time.sleep(.05)
        self.fail('Service readiness deadline expired on port '+str(number))

    def start_agh(self):
        p=self.launch([self.work/'AdGuardHome','-c',self.config,'-w',self.work,'--no-check-update'],'agh')
        self.ready(p,self.web)
        listing=subprocess.check_output(['ss','-H','-lntup'],text=True,timeout=5)
        self.shell('source "$1"; AGH_WEB_PORT="$2"; AGH_DNS_PORT="$3"; fixture_pid="$4"; systemctl() { printf "%s\\n" "$fixture_pid"; }; agh_listeners',HELPER,self.web,self.native,p.pid)
        owned=[line.split() for line in listing.splitlines() if f'pid={p.pid},' in line]
        self.assertTrue(owned);self.assertEqual({row[4] for row in owned},{f'127.0.0.1:{self.web}',f'127.0.0.1:{self.native}'})
        self.assertTrue(any(row[0]=='udp' for row in owned));return p

    def start_nginx(self):
        snippet=self.shell('source "$1"; AGH_WEB_PORT="$2"; AGH_PATH="$3"; agh_snippet',HELPER,self.web,self.prefix)
        from test_personal_xhttp import render
        acme=render('cat > /etc/nginx/sites-available/80.conf')
        self.assertIn('listen 80;',acme)
        acme=acme.replace('listen 80;',f'listen 127.0.0.1:{self.http};').replace('    listen [::]:80;\n','')
        acme=acme.replace('/var/www/acme',str(self.webroot))
        temp='\n'.join(f'{kind}_temp_path {self.root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        path=self.root/'nginx.conf'
        path.write_text(f'pid {self.root}/nginx.pid; error_log {self.root}/nginx-error.log; events {{}} http {{ access_log {self.root}/access.log; {temp} {acme} server {{ listen 127.0.0.1:{self.https} ssl; server_name {self.domain}; ssl_certificate {self.cert}; ssl_certificate_key {self.key}; {snippet} location / {{ return 404; }} }} }}')
        subprocess.run([self.nginx,'-t','-p',str(self.root)+'/', '-c',path],check=True,capture_output=True,timeout=15)
        p=self.launch([self.nginx,'-p',str(self.root)+'/', '-c',path,'-g','daemon off;'],'nginx')
        self.ready(p,self.https);self.ready(p,self.http);return p

    def request(self,path,data=None,options=()):
        args=['curl','--noproxy','*','-sS','--connect-timeout','5','--max-time','15','--cacert',str(self.cert),
              '--resolve',f'{self.domain}:{self.https}:127.0.0.1', '-D',str(self.root/'headers'),'-o',str(self.root/'body'),'-w','%{http_code}',*map(str,options)]
        if data is not None:
            payload=self.root/'payload';payload.write_bytes(data);payload.chmod(0o600)
            args+=['--data-binary','@'+str(payload)]
        result=subprocess.run(args+[f'https://{self.domain}:{self.https}'+path],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        return int(result.stdout),(self.root/'body').read_bytes(),(self.root/'headers').read_text()

    def dns_answer(self,query,response):
        self.assertGreaterEqual(len(response),len(query)+16)
        ident,flags,qd,an,_,_=struct.unpack('!6H',response[:12])
        self.assertEqual(ident,int.from_bytes(query[:2],'big'));self.assertEqual(flags&0x800f,0x8000)
        self.assertEqual((qd,an),(1,1));self.assertEqual(response[12:len(query)],query[12:])
        self.assertEqual(response[-4:],socket.inet_aton('198.51.100.42'))

    def register_doh_client(self):
        client_id='client-'+os.urandom(6).hex()
        jar=self.root/'client-cookies'
        status,_,_=self.request('/'+self.prefix+'/control/login',
            json.dumps({'name':'admin','password':self.password}).encode(),
            ('-H','Content-Type: application/json','-c',jar))
        self.assertEqual(status,200)
        status,_,_=self.request('/'+self.prefix+'/control/clients/add',
            json.dumps({'name':client_id,'ids':[client_id],'use_global_settings':True}).encode(),
            ('-H','Content-Type: application/json','-b',jar))
        self.assertEqual(status,200)
        return client_id,jar

    def doh_matrix(self,client_id,jar):
        for suffix in ('','/'+client_id):
            for method in ('GET','POST'):
                name=method.lower()+'-'+os.urandom(6).hex()+'.example.test'
                query=question(name,ident=int.from_bytes(os.urandom(2),'big'))
                path='/dns-query'+suffix
                url=path+'?dns='+base64.urlsafe_b64encode(query).decode().rstrip('=') if method=='GET' else path
                status,body,headers=self.request(url,query if method=='POST' else None,('-H','Content-Type: application/dns-message'))
                self.assertEqual(status,200,(method,path))
                self.assertIn('content-type: application/dns-message',headers.lower())
                self.dns_answer(query,body);self.assertIn((name,1),self.upstream_requests)
                status,body,_=self.request('/'+self.prefix+'/control/querylog?search='+name,options=('-b',jar))
                self.assertEqual(status,200)
                entries=[entry for entry in json.loads(body)['data'] if entry['question']['name'].rstrip('.')==name]
                self.assertEqual(len(entries),1)
                self.assertEqual(entries[0]['client_proto'],'doh')
                self.assertEqual(entries[0].get('client_id',''),client_id if suffix else '')
                if suffix:self.assertEqual(entries[0]['client_info']['name'],client_id)
        print('DoH GET/POST exact + registered random ClientID: DNS/upstream/querylog PASS',flush=True)

    def test_real_adguard_dns_doh_and_admin(self):
        self.start_agh();self.start_nginx()
        query=question('native.example.test')
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(10);sock.sendto(query,('127.0.0.1',self.native));answer=sock.recv(65535)
        self.dns_answer(query,answer);self.assertIn(('native.example.test',1),self.upstream_requests)
        client_id,jar=self.register_doh_client()
        self.doh_matrix(client_id,jar)
        for url,data in (('/dns-query?dns=broken',None),('/dns-query',b'bad')):
            status,_,_=self.request(url,data,('-H','Content-Type: application/dns-message'))
            self.assertGreaterEqual(status,400)
        status,_,headers=self.request('/'+self.prefix+'/');self.assertEqual(status,302)
        location=next(line.split(':',1)[1].strip() for line in headers.splitlines() if line.lower().startswith('location:'))
        self.assertEqual(urlsplit(location).path,'/'+self.prefix+'/login.html')
        status,_,_=self.request('/'+self.prefix+'/login.html');self.assertEqual(status,200)
        status,_,_=self.request('/not-the-admin/control/status');self.assertEqual(status,404)
        status,_,_=self.request('/'+self.prefix+'/control/status');self.assertIn(status,(401,403))
        jar=self.root/'cookies'
        status,_,headers=self.request('/'+self.prefix+'/control/login',json.dumps({'name':'admin','password':self.password}).encode(),('-H','Content-Type: application/json','-c',jar))
        self.assertEqual(status,200)
        cookies=SimpleCookie()
        for line in headers.splitlines():
            if line.lower().startswith('set-cookie:'):cookies.load(line.split(':',1)[1])
        self.assertEqual(cookies['agh_session']['path'],'/'+self.prefix+'/');self.assertTrue(cookies['agh_session']['secure'])
        status,body,_=self.request('/'+self.prefix+'/control/status',options=('-b',jar))
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['version'],AGH_VERSION)
        status,_,_=self.request('/'+self.prefix+'/control/status',options=('-H','Cookie: agh_session=invalid'))
        self.assertIn(status,(401,403))

    def test_adguard_bad_config_and_listener_contract(self):
        original=self.config.read_text()
        self.config.write_text('http: [invalid YAML')
        result=subprocess.run([self.agh,'-c',self.config,'-w',self.work,'--no-check-update','--check-config'],capture_output=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.config.write_text(original)
        process=self.start_agh()
        script='source "$1"; AGH_DIR="$2"; agh_config'
        self.config.write_text(original.replace(f'127.0.0.1:{self.web}',f'0.0.0.0:{self.web}'))
        result=subprocess.run(['bash','-c',script,'fixture',str(HELPER),str(self.work)],capture_output=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.config.write_text(original)
        # Actual safe loopback process, but wrong expected endpoint must be rejected by the real socket table.
        wrong=port(self.allocated)
        script='source "$1"; AGH_WEB_PORT="$2"; AGH_DNS_PORT="$3"; fixture_pid="$4"; systemctl() { printf "%s\\n" "$fixture_pid"; }; agh_listeners'
        result=subprocess.run(['bash','-c',script,'fixture',str(HELPER),str(wrong),str(self.native),str(process.pid)],capture_output=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.assertIsNone(process.poll())

    def start_pebble(self):
        config=self.root/'pebble.json'
        config.write_text(json.dumps({'pebble':dict(listenAddress=f'127.0.0.1:{self.acme}',
            managementListenAddress=f'127.0.0.1:{self.management}',certificate=str(self.cert),privateKey=str(self.key),
            httpPort=self.http,tlsPort=port(self.allocated),ocspResponderURL='',externalAccountBindingRequired=False,
            retryAfter={'authz':1,'order':1})}))
        env={**os.environ,'PEBBLE_VA_NOSLEEP':'1','PEBBLE_VA_ALWAYS_VALID':'0',
             'PEBBLE_WFE_NONCEREJECT':'0','PEBBLE_AUTHZREUSE':'0',
             'NO_PROXY':'.example.test,localhost,127.0.0.1,example.com,reality.example.com'}
        process=self.launch([self.pebble,'-config',config,'-dnsserver',f'127.0.0.1:{self.dns.server_address[1]}'],'pebble',env)
        self.ready(process,self.acme)
        return process

    def certbot(self,*args,success=True):
        command=['certbot','--non-interactive','--server',f'https://localhost:{self.acme}/dir',
                 '--config-dir',str(self.root/'etc/letsencrypt'),'--work-dir',str(self.root/'certbot-work'),
                 '--logs-dir',str(self.root/'certbot-logs'),*map(str,args)]
        env={**os.environ,'REQUESTS_CA_BUNDLE':str(self.cert),'NO_PROXY':'localhost,127.0.0.1',**getattr(self,'certbot_extra_env',{})}
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=120)
        if success:self.assertEqual(result.returncode,0,(result.stdout+result.stderr)[-2500:])
        else:self.assertNotEqual(result.returncode,0)
        return result

    def lineage(self,domain):
        from configobj import ConfigObj
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import load_pem_private_key,Encoding,PublicFormat
        root=self.root/'etc/letsencrypt';live=root/'live'/domain
        cert=x509.load_pem_x509_certificate((live/'cert.pem').read_bytes())
        key=load_pem_private_key((live/'privkey.pem').read_bytes(),password=None)
        self.assertEqual(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName),[domain])
        self.assertEqual(cert.public_key().public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo),
                         key.public_key().public_bytes(Encoding.DER,PublicFormat.SubjectPublicKeyInfo))
        cfg=ConfigObj(str(root/'renewal'/(domain+'.conf')))
        renewal=cfg['renewalparams']
        self.assertEqual(renewal['authenticator'],'webroot')
        self.assertEqual(renewal['server'],f'https://localhost:{self.acme}/dir')
        self.assertEqual(renewal['webroot_map'][domain],str(self.webroot))
        for name in ('cert.pem','chain.pem','fullchain.pem','privkey.pem'):
            self.assertTrue((live/name).is_symlink());self.assertTrue((live/name).is_file())
        for key in ('pre_hook','post_hook','renew_hook'):
            self.assertFalse(renewal.get(key),'Unexpected lineage hook')
        return cert.serial_number

    def issue(self,domain,webroot=None,success=True):
        return self.certbot('certonly','--agree-tos','--email','integration@example.test','--no-eff-email',
                            '--webroot','-w',webroot or self.webroot,'--cert-name',domain,'-d',domain,success=success)

    def test_real_certbot_pebble_http01_issuance_renewal_and_negative(self):
        nginx=self.start_nginx();self.start_pebble()
        domains = (self.domain, self.reality, 'vision.example.test')
        # Use the production separate Vision webroot vhost on the same HTTP listener.
        from test_integrated_features import helper
        vision = helper('vision').acme_config(domains[2])
        vision = vision.replace('listen 80;', f'listen 127.0.0.1:{self.http};').replace('    listen [::]:80;\n','').replace('/var/www/acme', str(self.webroot))
        config = self.root/'nginx.conf'; config.write_text(config.read_text().replace('http {', 'http {\n'+vision, 1))
        subprocess.run([self.nginx, '-t', '-p', str(self.root)+'/', '-c', config], check=True, capture_output=True, timeout=15)
        subprocess.run([self.nginx, '-s', 'reload', '-p', str(self.root)+'/', '-c', config], check=True, capture_output=True, timeout=15)
        for domain in domains:self.issue(domain)
        # Exercise the production allowlist merge on actual Certbot/Pebble
        # lineages and account JSON, then renew from the restored state.
        from certificate_fixtures import relocate
        import shlex
        certroot=self.root/'etc/letsencrypt'; hooks=certroot/'renewal-hooks/deploy'; hooks.mkdir(parents=True,exist_ok=True)
        generator='\n'.join(relocate(function(name),self.root) for name in ('check_xray_runtime','render_certificate_hook','render_vision_hook'))
        core_hook=subprocess.check_output(['bash','-c',generator+'\nrender_certificate_hook "$1" "$2"','fixture',self.domain,self.reality],text=True)
        vision_hook=subprocess.check_output(['bash','-c',generator+'\nrender_vision_hook "$1"','fixture',domains[2]],text=True)
        for name,body in (('3x-ui-auto-nginx',core_hook),('3x-ui-auto-nginx-vision',vision_hook),('foreign-import','#!/bin/sh\nexit 77\n')):
            (hooks/name).write_text(body); (hooks/name).chmod(0o755)
        accounts={str(p.relative_to(certroot)):p.read_bytes() for p in (certroot/'accounts').rglob('*.json')}
        self.assertTrue(accounts,'Real Certbot did not create account metadata')
        saved=self.root/'saved-certbot'; certroot.rename(saved)
        certroot.mkdir(); (certroot/'renewal-hooks/deploy').mkdir(parents=True)
        target_hook=certroot/'renewal-hooks/deploy/administrator'; target_hook.write_text('#!/bin/sh\nexit 0\n'); target_hook.chmod(0o755)
        backup_source=(ROOT/'assets/backup/x-ui-backup.sh').read_text()
        script='\n'.join(relocate(function(name,backup_source),self.root) for name in ('restored_certificate_domains','restored_vision_domain','render_vision_hook','project_certbot_accounts','restore_project_certificates'))
        subprocess.run(['bash','-eu','-c','die() { echo "$*" >&2; exit 1; };\n'+script+'\nrestore_project_certificates '+shlex.quote(str(saved))],check=True,capture_output=True,text=True)
        self.assertFalse((certroot/'renewal-hooks/deploy/foreign-import').exists())
        self.assertEqual(target_hook.read_text(),'#!/bin/sh\nexit 0\n')
        self.assertEqual({str(p.relative_to(certroot)):p.read_bytes() for p in (certroot/'accounts').rglob('*.json')},accounts)
        before={domain:self.lineage(domain) for domain in domains}
        access=(self.root/'access.log').read_text()
        self.assertGreaterEqual(len(re.findall(r'GET /\.well-known/acme-challenge/[^ ]+ HTTP/1.1" 200',access)),2)
        for domain in domains:
            self.certbot('renew','--cert-name',domain,'--force-renewal','--no-random-sleep-on-renew','--no-directory-hooks')
            self.assertNotEqual(self.lineage(domain),before[domain])
            self.assertIsNone(nginx.poll(),'Renewal must not stop nginx')
        empty=self.root/'wrong-webroot';empty.mkdir()
        result=self.issue('broken.example.test',empty,success=False)
        self.assertIn('unauthorized',result.stderr.lower()+result.stdout.lower())
        # DNS uses the same local deterministic resolver, and nginx must actually return challenge 404.
        self.assertIn(('broken.example.test',1),self.upstream_requests)
        self.assertRegex((self.root/'access.log').read_text(),r'GET /\.well-known/acme-challenge/[^ ]+ HTTP/1.1" 404')
        self.assertFalse((self.root/'etc/letsencrypt/live/broken.example.test').exists())

    def test_real_project_deploy_hook_and_nginx_reload(self):
        from certificate_fixtures import certificates,relocate
        nginx=self.start_nginx();self.start_pebble()
        for domain in (self.domain,self.reality,'unrelated.example.test'):self.issue(domain)
        # Existing Xray process/socket fixture remains explicitly FIXTURE: Phase 2 does not rerun Xray.
        context=self.root/'hook-context';context.mkdir()
        certificates(context)
        for directory in ('usr/local/x-ui','proc','health-bin'):
            shutil.copytree(context/directory,self.root/directory,symlinks=True)
        link=self.root/'proc/43210/exe';link.unlink();link.symlink_to(self.root/'usr/local/x-ui/bin/xray-linux-amd64')
        health=self.root/'health-bin'
        ss=health/'ss';ss.write_text(ss.read_text().replace(str(context),str(self.root)))
        source='\n'.join(relocate(function(name),self.root) for name in ('check_xray_runtime','render_certificate_hook'))
        hook=self.root/'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'
        hook.parent.mkdir(parents=True,exist_ok=True)
        hook.write_text(self.shell(source+'\nrender_certificate_hook "$1" "$2"',self.domain,self.reality));hook.chmod(0o755)
        config=self.root/'nginx.conf'
        current=config.read_text().replace(str(self.cert),str(self.root/'etc/letsencrypt/live'/self.domain/'fullchain.pem')).replace(str(self.key),str(self.root/'etc/letsencrypt/live'/self.domain/'privkey.pem'))
        config.write_text(current)
        subprocess.run([self.nginx,'-p',str(self.root)+'/', '-c',config,'-s','reload'],check=True,capture_output=True,timeout=15)
        calls=self.root/'hook-calls'
        wrapper=health/'nginx'
        wrapper.write_text(f'#!/bin/sh\nexec "{self.nginx}" -p "{self.root}/" -c "{config}" "$@"\n');wrapper.chmod(0o755)
        controller=health/'systemctl'
        controller.write_text('#!'+sys.executable+'\n'+f"""import json,os,pathlib,subprocess,sys
root=pathlib.Path({str(self.root)!r});args=sys.argv[1:]
with open(root/'hook-calls','a') as log:log.write(json.dumps(args)+'\\n')
if args==['reload','nginx']:
    sys.exit(subprocess.call([{self.nginx!r},'-p',str(root)+'/', '-c',str(root/'nginx.conf'),'-s','reload']))
if args[0]=='is-active' and args[-1]=='nginx':
    if (root/'fail-service').exists():sys.exit(1)
    os.kill({nginx.pid},0)
elif args not in (['restart','x-ui'],['is-active','--quiet','x-ui']):sys.exit(1)
""");controller.chmod(0o755)
        self.certbot_extra_env={'PATH':str(health)+':'+os.environ['PATH']}
        roots=subprocess.check_output(['curl','-fsS','--noproxy','*','--max-time','10','--cacert',str(self.cert),
                                      f'https://localhost:{self.management}/roots/0'],timeout=15)
        # Reload is asynchronous: old workers may still serve the known initial
        # test certificate. Verify both trusted generations, then require the
        # new serial below; never disable TLS verification or retry a test.
        trust=self.root/'pebble-ca.pem';trust.write_bytes(roots+self.cert.read_bytes())
        def served(serial):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                ctx=ssl.create_default_context(cafile=str(trust))
                with socket.create_connection(('127.0.0.1',self.https),timeout=5) as raw:
                    with ctx.wrap_socket(raw,server_hostname=self.domain) as connection:
                        from cryptography import x509
                        if x509.load_der_x509_certificate(connection.getpeercert(binary_form=True)).serial_number==serial:return
                time.sleep(.05)
            self.fail('nginx reload did not serve the renewed certificate')
        served(self.lineage(self.domain))
        for names in ((self.domain,),(self.reality,),(self.domain,self.reality),('unrelated.example.test',)):
            calls.unlink(missing_ok=True)
            for name in names:
                self.certbot('renew','--force-renewal','--no-random-sleep-on-renew','--cert-name',name)
            recorded=[json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            self.assertEqual(recorded.count(['reload','nginx']),0 if names==('unrelated.example.test',) else len(names))
            self.assertEqual(recorded.count(['restart','x-ui']),int(self.domain in names))
            self.assertFalse(any(call[0]=='stop' for call in recorded));self.assertIsNone(nginx.poll())
            served(self.lineage(self.domain))
        for fault in ('fail-nginx','fail-service'):
            marker=self.root/fault;marker.touch();calls.unlink(missing_ok=True)
            valid=config.read_text()
            if fault=='fail-nginx':config.write_text(valid+'\ninvalid_directive;\n')
            result=subprocess.run([hook],env={**os.environ,**self.certbot_extra_env,
                'RENEWED_LINEAGE':str(self.root/'etc/letsencrypt/live'/self.domain)},capture_output=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            recorded=[json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []
            self.assertNotIn(['restart','x-ui'],recorded)
            if fault=='fail-nginx':self.assertNotIn(['reload','nginx'],recorded)
            config.write_text(valid);marker.unlink();self.assertIsNone(nginx.poll())

    def test_private_backup_restore_with_real_adguard_and_failure_recovery(self):
        result=subprocess.run(['sudo','--preserve-env=NGINX_BIN',sys.executable,
            str(ROOT/'tests/services_restore.py'),str(self.tools)],capture_output=True,text=True,timeout=240)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PRIVATE RESTORE:',result.stdout)
        print(result.stdout.strip(),flush=True)
