"""Production HTTP/3 cover and native Disable/Enable regression.

Uses the existing RealIntegration fixture and official panel/Xray. No installation,
private responses or credentials are published. Invoke through tests/run_ci.py.
"""
import asyncio
import base64
import copy
import hashlib
import http.client
import json
import os
import re
import socket
import sqlite3
import ssl
import subprocess
import time
from urllib.parse import urlsplit,parse_qs
from http3 import request as http3_request
from test_cover_sites import helper
from test_integrated_features import helper as feature
from test_personal_xhttp import function as installer_function
from test_real_integration import ROOT,port,stop


def run_profile(f):
    generator=helper().module('generate')
    for role,code in (('panel','A1'),('reality','B1')):generator.generate(code,f.root/'www/html'/('cover-'+role),[0,0,0,0])
    cover=f.root/'www/html/cover-reality';socket_path=f.root/'hysteria-cover.sock'
    expected=(cover/'index.html').read_bytes()
    import socketserver,threading
    class Echo(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(8)
            try:
                while data:=self.request.recv(4096):self.request.sendall(data)
            except (OSError,socket.timeout):pass
    echo=socketserver.ThreadingTCPServer(('127.0.0.1',0),Echo);echo.daemon_threads=True
    f.addCleanup(echo.server_close);f.addCleanup(echo.shutdown);threading.Thread(target=echo.serve_forever,daemon=True).start()
    with sqlite3.connect(f.root/'db/x-ui.db') as db:
        ids={name:db.execute("SELECT id FROM inbounds WHERE remark=?",(row['remark'],)).fetchone()[0] for name,row in f.rows.items()}
        real=(ids['reality'],);hy=(ids['hysteria2'],)
        key='xrayTemplateConfig';template=json.loads(db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()[0])
        # Restore the official panel's local Handler API removed by the base
        # transport-only fixture; setEnable uses this actual gRPC API.
        template['log']={'loglevel':'debug'}
        template['outbounds'][0]['settings']['finalRules'][0]['port']+=','+str(echo.server_address[1])
        template['api']={'tag':'api','services':['HandlerService','LoggerService','StatsService','RoutingService']}
        template['inbounds']=[dict(listen='127.0.0.1',port=62789,protocol='tunnel',settings=dict(rewriteAddress='127.0.0.1'),tag='api')]
        template['routing']={'rules':[dict(type='field',inboundTag=['api'],outboundTag='api')]}
        db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(template),key))
        # Replace the transport fixture's SQL-only synthetic client with
        # genuine native API clients, including their native runtime cache.
        db.execute('DELETE FROM client_inbounds');db.execute('DELETE FROM client_traffics');db.execute('DELETE FROM clients')
        db.execute("UPDATE settings SET value=? WHERE key='subURI'",(f'https://deploy.example:{f.public}/subscription/',))
        db.execute("UPDATE settings SET value=? WHERE key='subJsonURI'",(f'https://deploy.example:{f.public}/jsonsub/',))
    roles={name:ids[name] for name in ('reality','hysteria2','xhttp')}
    nginx=f.nginx_config()
    env={**os.environ,'XUI_DB_FOLDER':str(f.root/'db'),'XUI_BIN_FOLDER':str(f.root/'bin'),'XUI_LOG_FOLDER':str(f.root/'logs')}
    def panel_start():
        p=f.launch([f.xui],'toggle-panel',env);f.ready(p,('127.0.0.1',f.backends['panel']));return p
    panel=panel_start()
    api=feature('amneziawg').Panel(f'https://deploy.example:{f.public}/panel/','integration',f.auth,f.root,
        ['--cacert',str(f.cert),'--resolve',f'deploy.example:{f.backends["panel"]}:127.0.0.1','--resolve',f'deploy.example:{f.public}:127.0.0.1'])
    created=feature('client').create(api);neighbor=feature('client').create(api)
    subscription=created['subId']
    # The official panel normalizes this supported non-Xray role to an empty
    # stream_settings string. Health must still validate the three core roles.
    awg=api.create('deploy.example',port(f.allocated_ports,udp=True))
    with sqlite3.connect(f.root/'db/x-ui.db') as db:
        if db.execute('SELECT stream_settings FROM inbounds WHERE id=?',(awg['id'],)).fetchone()[0]!='':
            raise AssertionError('Native AmneziaWG empty-stream fixture changed')
    with sqlite3.connect(f.root/'db/x-ui.db') as db:
        counts={name:db.execute("SELECT json_array_length(settings,'$.clients') FROM inbounds WHERE id=?",(iid,)).fetchone()[0] for name,iid in roles.items()}
    print('NATIVE_CLIENT_SETUP '+json.dumps(dict(stored_client_counts=counts)),flush=True)
    def native_pid():
        return int(subprocess.check_output(['pgrep','-P',str(panel.pid),'-f','xray-linux-'],text=True).strip())
    def state():
        tcp=subprocess.check_output(['ss','-H','-lnt'],text=True)
        udp=subprocess.check_output(['ss','-H','-lnu'],text=True)
        unix=subprocess.check_output(['ss','-H','-lxnp'],text=True)
        return (f"127.0.0.1:{f.backends['reality']}" in tcp,
                bool(re.search(r'(?:127\.0\.0\.1|\*|0\.0\.0\.0|\[::\]|:::):'+str(f.hysteria_port)+r'\s',udp)),
                str(f.uds) in unix)
    def settled(*expected):
        deadline=time.monotonic()+10
        while state()!=expected:
            if time.monotonic()>deadline:raise AssertionError('Native API listeners did not converge')
            time.sleep(.05)
    settled(True,True,True)
    def exports(sub_id=None):
        result=[]
        for path in ('subscription','jsonsub'):
            c=http.client.HTTPConnection('127.0.0.1',f.backends['sub'],timeout=10)
            c.sock=ssl.create_default_context(cafile=str(f.cert)).wrap_socket(socket.create_connection(('127.0.0.1',f.backends['sub']),timeout=10),server_hostname='deploy.example')
            try:
                c.request('GET','/'+path+'/'+(sub_id or subscription),headers={'Host':'deploy.example'});response=c.getresponse();body=response.read()
                if response.status!=200:raise AssertionError('Native export unavailable')
                result.append(body)
            finally:c.close()
        return result[0],json.loads(result[1])
    raw,configs=exports()
    clients={}
    for c in configs:
        out=next(o for o in c['outbounds'] if o.get('protocol') in ('vless','trojan','hysteria'))
        if out['protocol']=='hysteria':clients['hysteria2']=c
        elif out.get('streamSettings',{}).get('network')=='xhttp':clients['xhttp']=c
        elif out.get('streamSettings',{}).get('security')=='reality':clients['reality']=c
    def client_start(name,selected=None):
        c=copy.deepcopy((selected or clients)[name]);out=next(o for o in c['outbounds'] if o.get('protocol') in ('vless','hysteria'))
        settings=out['settings'];dest=settings['servers'][0] if 'servers' in settings else settings
        dest.update(address='127.0.0.1',port=f.hysteria_port if name=='hysteria2' else f.public)
        if out['streamSettings'].get('security')=='tls':out['streamSettings']['tlsSettings'].update(serverName='cover.example' if name=='hysteria2' else 'deploy.example',allowInsecure=False,certificates=[{'certificateFile':str(f.cert),'usage':'verify'}])
        socks=port(f.allocated_ports);c['inbounds']=[dict(listen='127.0.0.1',port=socks,protocol='socks',settings=dict(auth='noauth',udp=True))]
        c['outbounds']=[out];c.pop('routing',None);c.pop('dns',None);c['log']={'loglevel':'debug'}
        p=f.launch([f.xray,'run','-c',f.validate(c,'toggle-'+name)],'toggle-'+name);f.ready(p,('127.0.0.1',socks))
        return p,socks
    def client(name,enabled,timeout=3,selected=None):
        p,socks=client_start(name,selected)
        before=len(f.origin_requests)
        try:
            result=subprocess.run(['curl','-q','-fsS','--noproxy','','--max-time',str(timeout),'--socks5-hostname',f'127.0.0.1:{socks}',
                f'http://127.0.0.1:{f.origin.server_port}/toggle-'+name],capture_output=True,timeout=timeout+3)
            good=result.returncode==0 and result.stdout==f.marker.encode() and len(f.origin_requests)==before+1
            if not enabled and (good or len(f.origin_requests)!=before):raise AssertionError('Disabled inbound still carried data')
            return good
        finally:stop(p)
    def tls(host='cover.example',sni='cover.example',spoof=False,path='/'):
        c=http.client.HTTPConnection('127.0.0.1',443,timeout=4)
        ctx=ssl.create_default_context(cafile=str(f.cert))
        if sni=='wrong.example':ctx.check_hostname=False  # Adversarial client only; certificate still trusted.
        try:
            c.sock=ctx.wrap_socket(socket.create_connection(('127.0.0.1',f.public),timeout=4,source_address=('127.0.0.2',0)),server_hostname=sni)
            headers={'Host':host}
            if spoof:headers.update({'X-Real-IP':'203.0.113.55','X-Forwarded-For':'203.0.113.56'})
            c.request('GET',path,headers=headers);r=c.getresponse();body=r.read()
            return r.status,body==expected
        except (OSError,ssl.SSLError,http.client.HTTPException):return 0,False
        finally:c.close()
    def untrusted_proxy():
        # A remote client cannot prepend its own PROXY header to TCP/443.
        raw=socket.create_connection(('127.0.0.1',f.public),timeout=4,source_address=('127.0.0.2',0))
        try:
            raw.sendall(b'PROXY TCP4 203.0.113.99 127.0.0.1 12345 443\r\n')
            try:
                secure=ssl.create_default_context(cafile=str(f.cert)).wrap_socket(raw,server_hostname='cover.example')
                secure.close()
            except (OSError,ssl.SSLError):return True
            return False
        finally:raw.close()
    def snapshot():
        with sqlite3.connect(f.root/'db/x-ui.db') as db:
            db.row_factory=sqlite3.Row;data={}
            for table in ('inbounds','hosts','users','clients','client_inbounds','settings'):
                records=[]
                for row in db.execute('SELECT * FROM '+table+' ORDER BY rowid'):
                    record=dict(row)
                    for key in ('up','down'):record.pop(key,None)
                    if table=='inbounds' and record['id'] in roles.values():record.pop('enable',None)
                    for key in ('settings','stream_settings','sniffing'):
                        if key in record:
                            try:record[key]=json.loads(record[key])
                            except (ValueError,TypeError):pass
                    records.append(record)
                data[table]=records
            return data
    public_files=[f.cert,f.key,*[p for p in (f.root/'www/html').rglob('*') if p.is_file()]]
    immutable={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in public_files}
    before=snapshot()
    if not client('reality',True):raise AssertionError('Initial REALITY failed before any native toggle')
    def toggle(name,value):
        current=next(r for r in api.request('panel/api/inbounds/list')['obj'] if r['id']==roles[name])
        if current['enable']==value:return
        api.request('panel/api/inbounds/setEnable/'+str(current['id']),{'enable':value})
        with sqlite3.connect(f.root/'db/x-ui.db') as db:
            saved=db.execute('SELECT enable FROM inbounds WHERE id=?',(current['id'],)).fetchone()[0]
        if bool(saved)!=value:raise AssertionError('Native setEnable did not save the flag')
    def h3(path='/',**kwargs):
        return asyncio.run(http3_request('127.0.0.1',f.hysteria_port,'cover.example',f.cert,path,**kwargs))
    def runtime():
        # The production metadata is restored in a private DB copy; only test
        # address relocation is undone in actual kernel ss output, never owners.
        from test_personal_xhttp import seed
        canonical,_=seed(private_key=f.private,public_key=f.public_key)
        target=f.root/'health.db'
        with sqlite3.connect(f.root/'db/x-ui.db') as db,sqlite3.connect(target) as output:
            db.backup(output)
            for name,iid in roles.items():
                row=canonical[name]
                output.execute('UPDATE inbounds SET listen=?,port=?,stream_settings=? WHERE id=?',
                    (row['listen'],row['port'],row['stream_settings'],iid))
            output.execute("UPDATE settings SET value='/root/cert/deploy.example/fullchain.pem' WHERE key='webCertFile'")
        code=installer_function('check_configured_xray_runtime').replace('/usr/local/x-ui/bin',str(f.root/'bin'))
        for original,actual in (('127.0.0.1:8443',f"127.0.0.1:{f.backends['reality']}"),
                                ('0.0.0.0:443','127.0.0.1:'+str(f.hysteria_port)),('/dev/shm/uds2023.sock',str(f.uds))):
            code=code.replace("network = subprocess.check_output(['ss','-H','-lntup'],text=True)",
                "network = subprocess.check_output(['ss','-H','-lntup'],text=True)"+f'.replace({actual!r},{original!r})') if original!='/dev/shm/uds2023.sock' else code.replace(
                "unix = subprocess.check_output(['ss','-H','-lxnp'],text=True)",
                "unix = subprocess.check_output(['ss','-H','-lxnp'],text=True)"+f'.replace({actual!r},{original!r})')
        result=subprocess.run(['bash','-c',code+'\nsystemctl() { return 0; }; sleep() { :; }; XUIDB="$1"; check_configured_xray_runtime','fixture',str(target)],capture_output=True,timeout=12)
        if result.returncode:raise AssertionError('Maintenance health rejected native enabled/disabled roles')
        if not any(state()):
            with sqlite3.connect(target) as db:
                db.execute("UPDATE inbounds SET stream_settings=json_set(stream_settings,'$.hysteriaSettings.version',1) WHERE id=?",(roles['hysteria2'],))
            bad=subprocess.run(['bash','-c',code+'\nsystemctl() { return 0; }; sleep() { :; }; XUIDB="$1"; check_configured_xray_runtime','fixture',str(target)],capture_output=True,timeout=12)
            if bad.returncode==0:raise AssertionError('Disabled unknown Hysteria version accepted by maintenance')

        strict=installer_function('check_xray_runtime').replace('/usr/local/x-ui/bin',str(f.root/'bin'))
        network_relocation=f".replace({('127.0.0.1:'+str(f.backends['reality']))!r},'127.0.0.1:8443').replace({('127.0.0.1:'+str(f.hysteria_port))!r},'0.0.0.0:443')"
        strict=re.sub(r"(network = subprocess.check_output\([^\n]+\))",lambda m:m[0]+network_relocation,strict)
        strict=re.sub(r"(unix = subprocess.check_output\([^\n]+\))",lambda m:m[0]+f".replace({str(f.uds)!r},'/dev/shm/uds2023.sock')",strict)
        result=subprocess.run(['bash','-c',strict+'\nsystemctl() { return 0; }; sleep() { :; }; check_xray_runtime'],capture_output=True,timeout=12)
        if (result.returncode==0)!=all(state()):raise AssertionError('Fresh health no longer strictly requires all roles')

    # Fresh Change Domains restarts with all roles disabled, then hot-enables
    # them. The startup config.json may legitimately omit those runtime inbounds.
    for name in roles:toggle(name,False)
    settled(False,False,False)
    stop(panel);f.release_subscription_socket();panel=panel_start();settled(False,False,False)
    for name in roles:toggle(name,True)
    settled(True,True,True)
    def persisted_cover():
        with sqlite3.connect(f.root/'db/x-ui.db') as db:
            enabled,raw=db.execute('SELECT enable,stream_settings FROM inbounds WHERE id=?',
                                   (roles['hysteria2'],)).fetchone()
        stream=json.loads(raw)
        assert enabled and stream['hysteriaSettings']['masquerade']=={
            'type':'proxy','url':'unix:'+str(socket_path),'rewriteHost':False}
        assert stream['tlsSettings']['serverName']=='cover.example'
        assert h3()[0][b':status']==b'200' and socket_path.is_socket()
    persisted_cover()
    stop(panel);f.release_subscription_socket();panel=panel_start();settled(True,True,True)
    persisted_cover()
    assert str(socket_path) in (f.root/'bin/config.json').read_text()
    assert client('hysteria2',True)
    print('Native hot Enable persistence / startup rebuild / HTTP3 client PASS',flush=True)
    hot_pid=native_pid()
    # Gray order reaches all eight combinations and exercises reverse enables.
    for r,h,x in ((1,1,1),(0,1,1),(0,0,1),(1,0,1),(1,0,0),(1,1,0),(0,1,0),(0,0,0),(1,1,1)):
        for name,value in zip(roles,(r,h,x)):toggle(name,bool(value))
        settled(bool(r),bool(h),bool(x))
        for name,enabled in zip(roles,(r,h,x)):
            if client(name,bool(enabled))!=bool(enabled):raise AssertionError('Enabled transport failed: '+name)
        if tls(spoof=True)!=(200,True):raise AssertionError('TCP cover lost on native Disable')
        if tls(host='attacker.example')[0]!=404 or tls(sni='wrong.example')[0]!=421:raise AssertionError('TCP Host/SNI guard lost')
        if not untrusted_proxy():raise AssertionError('Untrusted PROXY prelude accepted')
        if '127.0.0.2|127.0.0.2' not in (f.root/'reality-access.log').read_text().splitlines()[-3:]:raise AssertionError('TCP backup lost trusted visitor IP')
        if h:
            headers,body,_=h3()
            if headers.get(b':status')!=b'200' or body!=expected:raise AssertionError('HTTP3 cover lost on peer Disable')
        raw,current=exports()
        links=[urlsplit(value) for value in base64.b64decode(raw,validate=True).decode().splitlines()]
        raw_states=(any(parse_qs(v.query).get('security')==['reality'] for v in links),
                    any(v.scheme in ('hy2','hysteria2') for v in links),
                    any(parse_qs(v.query).get('type')==['xhttp'] for v in links))
        outs=[o for c in current for o in c['outbounds']]
        json_states=(any(o.get('streamSettings',{}).get('security')=='reality' for o in outs),
                     any(o.get('protocol')=='hysteria' for o in outs),
                     any(o.get('streamSettings',{}).get('network')=='xhttp' for o in outs))
        if raw_states!=(bool(r),bool(h),bool(x)) or json_states!=raw_states:raise AssertionError('Native RAW/JSON ignored enable flags')
        if snapshot()!=before:raise AssertionError('Native Disable changed clients/settings or neighboring inbound')
        if native_pid()!=hot_pid:raise AssertionError('Native Disable restarted neighboring transports')
        runtime()
    # Keep actual flows alive while each other protocol switches off and on.
    for name in roles:
        process,socks=client_start(name)
        try:
            with socket.create_connection(('127.0.0.1',socks),timeout=5) as channel:
                channel.settimeout(5);channel.sendall(b'\x05\x01\x00')
                if channel.recv(2)!=b'\x05\x00':raise AssertionError('Held SOCKS greeting')
                channel.sendall(b'\x05\x01\x00\x01'+socket.inet_aton('127.0.0.1')+echo.server_address[1].to_bytes(2,'big'))
                if channel.recv(10)[:2]!=b'\x05\x00':raise AssertionError('Held SOCKS connect')
                for peer in roles:
                    if peer==name:continue
                    for enabled in (False,True):
                        toggle(peer,enabled)
                        payload=os.urandom(32);channel.sendall(payload);received=b''
                        while len(received)<len(payload):
                            part=channel.recv(len(payload)-len(received))
                            if not part:raise AssertionError('Neighbor Disable disconnected held transport')
                            received+=part
                        if received!=payload:raise AssertionError('Held payload changed')
        finally:stop(process)
    _,neighbor_configs=exports(neighbor['subId']);neighbor_clients={}
    for config in neighbor_configs:
        out=next(o for o in config['outbounds'] if o.get('protocol') in ('vless','trojan','hysteria'))
        stream=out.get('streamSettings',{})
        name='hysteria2' if out['protocol']=='hysteria' else 'reality' if stream.get('security')=='reality' else 'xhttp' if stream.get('network')=='xhttp' else None
        if name:neighbor_clients[name]=config
    if any(not client(name,True,selected=neighbor_clients) for name in roles):raise AssertionError('Neighbor credentials lost after toggles')
    # Real UDP payloads through the imported native Hysteria outbound.
    udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind(echo.server_address)
    f.addCleanup(udp.close)
    def udp_echo():
        try:
            while True:
                payload,address=udp.recvfrom(65536);udp.sendto(payload,address)
        except OSError:pass
    threading.Thread(target=udp_echo,daemon=True).start()
    process,socks=client_start('hysteria2')
    try:
        with socket.create_connection(('127.0.0.1',socks),timeout=5) as control:
            control.sendall(b'\x05\x01\x00')
            if control.recv(2)!=b'\x05\x00':raise AssertionError('UDP SOCKS greeting')
            control.sendall(b'\x05\x03\x00\x01'+socket.inet_aton('127.0.0.1')+b'\x00\x00')
            response=control.recv(10)
            if response[:4]!=b'\x05\x00\x00\x01':raise AssertionError('UDP associate failed')
            relay=(socket.inet_ntoa(response[4:8]),int.from_bytes(response[8:10],'big'))
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as tunnel:
                tunnel.settimeout(10)
                prefix=b'\x00\x00\x00\x01'+socket.inet_aton('127.0.0.1')+echo.server_address[1].to_bytes(2,'big')
                for size in (32,512,1200):
                    payload=os.urandom(size);tunnel.sendto(prefix+payload,relay)
                    data,_=tunnel.recvfrom(65536)
                    if data!=prefix+payload:raise AssertionError('Native Hysteria UDP payload changed')
    finally:stop(process)
    # Focused production-cover regressions; the previous 176-probe research is
    # not repeated. GET/HEAD, methods, directory redirects, privacy and SNI.
    directory=next(p.parent for p in cover.rglob('index.html') if p.parent!=cover)
    relative='/'+str(directory.relative_to(cover))
    for path,status,method in (('/',200,'GET'),('/index.html',200,'HEAD'),('/',405,'POST'),
                               (relative,301,'GET'),(relative+'/',200,'GET'),('/static/',403,'GET'),
                               ('/missing',404,'GET'),('/panel/',404,'GET'),('/diagnostics/',404,'GET'),
                               ('/assets/',404,'GET'),('/.env',404,'GET'),('/etc/x-ui/x-ui.db',404,'GET')):
        headers,body,_=h3(path,method=method)
        if int(headers[b':status'])!=status:raise AssertionError('Unexpected HTTP3 static status at '+path)
        if method=='HEAD' and body:raise AssertionError('HTTP3 HEAD returned body')
        if status==301 and headers.get(b'location')!=(relative+'/').encode():raise AssertionError('HTTP3 leaked internal redirect')
        if b'set-cookie' in headers or any(b'hysteria' in key.lower() for key in headers):raise AssertionError('HTTP3 application fingerprint')
    for path in sorted((cover/'static').iterdir()):
        if path.is_file():
            headers,body,_=h3('/static/'+path.name)
            if headers[b':status']!=b'200' or body!=path.read_bytes() or b'content-type' not in headers:raise AssertionError('HTTP3 static resource mismatch')
    if h3(authority='attacker.example')[0][b':status']!=b'404':raise AssertionError('HTTP3 accepted wrong Host')
    try:asyncio.run(http3_request('127.0.0.1',f.hysteria_port,'wrong.example',f.cert,verify=False))
    except (ConnectionError,TimeoutError):pass
    else:raise AssertionError('Server accepted unknown SNI')
    if immutable!={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in public_files}:raise AssertionError('Sites or certificates changed')
    # Imported native client retains the server masquerade; it does not need
    # the server socket. Transport/negative tests above use that unmodified JSON.
    native=clients['hysteria2'];f.validate(native,'native-json-unchanged')
    exported=json.dumps(native)
    if 'hysteria-cover.sock' not in exported or f.private in exported or 'PRIVATE KEY' in exported:raise AssertionError('Unexpected native export content')
    toggle('reality',False);toggle('xhttp',False);settled(False,True,False)
    stop(panel);f.release_subscription_socket();stop(nginx)
    nginx=f.nginx_config();panel=panel_start();settled(False,True,False)
    if tls()!=(200,True) or h3()[0][b':status']!=b'200' or not client('hysteria2',True):raise AssertionError('Restart lost disabled flags or cover socket')
    if socket_path.stat().st_mode&0o777!=0o666:raise AssertionError('Unexpected Unix socket permissions')
    print('Managed HTTP3: eight native states, live peers, RAW/JSON, static privacy and process restart PASS',flush=True)
    api=feature('amneziawg').Panel(f'https://deploy.example:{f.public}/panel/','integration',f.auth,f.root,
        ['--cacert',str(f.cert),'--resolve',f'deploy.example:{f.public}:127.0.0.1'])
    # Same native certificate reread path, bounded to two seconds in this test
    # only. The unmodified 3600-second default is separately measured/documented.
    leaf,key=f.root/'renew-leaf.pem',f.root/'renew-key.pem'
    leaf.write_bytes(f.cert.read_bytes());key.write_bytes(f.key.read_bytes())
    with sqlite3.connect(f.root/'db/x-ui.db') as db:
        stream=json.loads(db.execute('SELECT stream_settings FROM inbounds WHERE id=?',(roles['hysteria2'],)).fetchone()[0])
        stream['tlsSettings']['certificates'][0].update(certificateFile=str(leaf),keyFile=str(key),oneTimeLoading=False,ocspStapling=2)
        db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),roles['hysteria2']))
    api.request('panel/api/server/restartXrayService',{});settled(False,True,False)
    initial=h3()[2];renew_pid=native_pid()
    process,socks=client_start('hysteria2')
    try:
        with socket.create_connection(('127.0.0.1',socks),timeout=5) as channel:
            channel.settimeout(5);channel.sendall(b'\x05\x01\x00')
            if channel.recv(2)!=b'\x05\x00':raise AssertionError('Renewal SOCKS greeting')
            channel.sendall(b'\x05\x01\x00\x01'+socket.inet_aton('127.0.0.1')+echo.server_address[1].to_bytes(2,'big'))
            if channel.recv(10)[:2]!=b'\x05\x00':raise AssertionError('Renewal SOCKS connect')
            csr=f.root/'renew.csr';newkey=f.root/'renew-new-key.pem';newcert=f.root/'renew-new.pem';extensions=f.root/'renew.ext'
            extensions.write_text('subjectAltName=DNS:cover.example\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n')
            subprocess.run(['openssl','req','-new','-newkey','rsa:2048','-nodes','-subj','/CN=cover.example','-keyout',str(newkey),'-out',str(csr)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            subprocess.run(['openssl','x509','-req','-in',str(csr),'-CA',str(f.cert),'-CAkey',str(f.key),'-set_serial','998899','-days','1','-extfile',str(extensions),'-out',str(newcert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
            newkey.replace(key);newcert.replace(leaf)
            deadline=time.monotonic()+12
            while True:
                payload=os.urandom(32);channel.sendall(payload);received=b''
                while len(received)<len(payload):
                    chunk=channel.recv(len(payload)-len(received))
                    if not chunk:raise AssertionError('Native renewal disconnected Hysteria')
                    received+=chunk
                if received!=payload:raise AssertionError('Native renewal changed payload')
                serial=h3()[2]
                if serial==998899:break
                if serial!=initial or time.monotonic()>deadline:raise AssertionError('Native TLS reread failed')
                time.sleep(.2)
        if native_pid()!=renew_pid or state()!=(False,True,False):raise AssertionError('Native renewal restarted core or changed flags')
    finally:stop(process)
    # A single enabled Xray profile is a native JSON object, not an array.
    # Exercise the actual maintenance HTTPS gate through nginx and 3x-ui.
    for name in ('ws','trojan-grpc'):
        api.request('panel/api/inbounds/setEnable/'+str(ids[name]),{'enable':False})
    _,single=exports()
    if not isinstance(single,dict) or not single.get('outbounds'):raise AssertionError('Native single-profile JSON contract changed')
    f.validate(single,'single-native-hysteria-export')
    if not client('hysteria2',True,selected={'hysteria2':single}):raise AssertionError('Native single-profile client failed')
    from http.server import ThreadingHTTPServer
    from unittest.mock import patch
    template=f.root/'health-clash.yaml.tpl'
    template.write_text((ROOT/'assets/clash/clash.yaml').read_text().replace('${DOMAIN}','deploy.example').replace('${SUB_PATH}','subscription'))
    source=(ROOT/'assets/diagnostics/mtr-backend.py').read_text().replace('"/var/www/subpage/clash.yaml.tpl"',repr(str(template)))
    namespace={'__name__':'maintenance_clash'};exec(compile(source,'maintenance-clash.py','exec'),namespace)
    clash=ThreadingHTTPServer(('127.0.0.1',f.backends['api']),namespace['Handler'])
    f.addCleanup(clash.server_close);f.addCleanup(clash.shutdown)
    threading.Thread(target=clash.serve_forever,daemon=True).start()
    domains=feature('domains');operation=domains.Operation('unused','unused',f.root)
    def connection(readonly=False):
        db=sqlite3.connect('file:'+str(f.root/'db/x-ui.db')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
    def run(*args):
        if args==('systemctl','show','x-ui','-p','MainPID','--value'):return str(panel.pid).encode()
        return subprocess.check_output(args,timeout=15)
    def request(domain,path,certificate,headers=None):
        body_file=f.root/'health-response';body_file.touch(mode=0o600)
        command=['curl','-q','-sS','--noproxy','*','--cacert',str(f.cert),'--resolve',f'{domain}:{f.public}:127.0.0.1',
                 '--max-time','15','-o',str(body_file),'-w','%{http_code}']
        for key,value in (headers or {}).items():command+=['-H',key+': '+value]
        code=subprocess.check_output(command+[f'https://{domain}:{f.public}'+path],timeout=20)
        return int(code),body_file.read_bytes()
    context=dict(domains=dict(panel='deploy.example',reality='cover.example',vision=None),hysteria_cover=True,
                 rows={roles['reality']:{'enable':0}},inbound_roles=roles)
    with patch.object(operation,'connection',side_effect=connection),patch.object(operation,'run',side_effect=run),patch.object(operation,'request',side_effect=request):
        operation.https_checks(context)
        def error_json(domain,path,certificate,headers=None):
            if path.startswith('/jsonsub/'):return 200,b'{"success":false}'
            return request(domain,path,certificate,headers)
        with patch.object(operation,'request',side_effect=error_json),f.assertRaises(domains.Refusal):
            operation.https_checks(context)
        # Native RAW-only WireGuard clients must not be selected for JSON health.
        api.request('panel/api/clients/add',{'client':{'email':'maintenance-wg-only','enable':True},'inboundIds':[awg['id']]})
        toggle('hysteria2',False);settled(False,False,False)
        operation.https_checks(context)
    print('Maintenance native single JSON / RAW-only AWG / all Xray roles OFF PASS',flush=True)
