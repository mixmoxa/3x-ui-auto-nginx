"""Private Backup v3 + real AGH. Systemd/Xray/UFW remain controlled fixtures.

Sudo is used solely for archived ownership validation. All managed absolute
paths are relocated using the existing PersonalBackup fixture.
"""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile

from certificate_fixtures import relocate, function
from test_personal_backup import PersonalBackup
from test_real_services import RealServices, HELPER, question


def run(tools):
    if os.geteuid()!=0:raise RuntimeError('Private ownership fixture requires root')
    RealServices.agh=tools/'AdGuardHome';RealServices.nginx=os.environ['NGINX_BIN']
    def deadline(signum,frame):raise TimeoutError('Private Restore fixture deadline expired')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(220)
    t=RealServices('runTest');f=PersonalBackup('runTest')
    try:
        t.setUp();f.setUp()
        f.seed_vision(); awg_columns, awg_row = f.seed_amneziawg()
        with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
            db.execute("UPDATE inbounds SET remark='🇫🇮 XTLS' WHERE tag='inbound-12000'")
        t.domain='example.com';t.reality='reality.example.com'
        shutil.copytree(t.work,f.path('/opt/AdGuardHome'))
        t.work=f.path('/opt/AdGuardHome');t.config=t.work/'AdGuardHome.yaml'
        meta=json.loads((t.work/'managed.json').read_text());meta['domain']=t.domain
        (t.work/'managed.json').write_text(json.dumps(meta))
        for source,target in (('fullchain.pem',t.cert),('privkey.pem',t.key)):
            shutil.copyfile(f.path('/etc/letsencrypt/live/example.com/'+source),target)
        state=t.work/'data/phase2-state';state.parent.mkdir(exist_ok=True);state.write_bytes(b'archived-data')
        helper=relocate(HELPER.read_text(),f.root)
        # Prevent upstream -s install from writing a real host systemd unit.
        # All config/hash/native/listener/DNS/HTTPS validation stays real.
        unit=f.path('/etc/systemd/system/AdGuardHome.service')
        unit_text=f'ExecStart={t.work}/AdGuardHome -c {t.config} -w {t.work} -s run --no-check-update\n'
        replacement='agh_install_service() {\n    agh_config && printf "%s\\n" '+repr(unit_text.rstrip())+' > '+str(unit)+' && agh_unit && systemctl enable --now AdGuardHome && agh_listeners\n}'
        helper=helper.replace(function('agh_install_service',helper),replacement)
        helper=helper.replace('https://${AGH_DOMAIN}/','https://${AGH_DOMAIN}:'+str(t.https)+'/').replace('${AGH_DOMAIN}:443:','${AGH_DOMAIN}:'+str(t.https)+':')
        f.write('/usr/local/lib/3x-ui-pro/managed-adguard.sh',helper,0o600)
        f.write('/etc/systemd/system/AdGuardHome.service',unit_text)
        snippet=t.shell('source "$1"; AGH_WEB_PORT="$2"; AGH_PATH="$3"; agh_snippet',HELPER,t.web,t.prefix)
        f.write('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf',snippet,0o600)
        config=f.path('/etc/nginx/nginx.conf')
        config.write_text(config.read_text().replace('error_log stderr;', 'error_log /dev/null crit;'))
        config.write_text(config.read_text().replace('location /panel/',f'include {f.path("/etc/nginx/snippets/x-ui-auto-optional/adguard.conf")}; location /panel/'))
        t.start_nginx()
        original=f.bin/'systemctl-fixture';(f.bin/'systemctl').rename(original)
        original.write_text(original.read_text().replace('name = pathlib.Path(sys.argv[0]).name',"name = 'systemctl'"))
        controller=f.bin/'systemctl'
        controller.write_text('#!'+sys.executable+'\n'+f'''import os,pathlib,signal,socket,subprocess,sys,time
root=pathlib.Path({str(f.root)!r});args=sys.argv[1:];pidfile=root/'agh.pid'
def running():
    if not pidfile.exists():return False
    try:return pathlib.Path('/proc/'+pidfile.read_text()+'/stat').read_text().split()[2]!='Z'
    except FileNotFoundError:return False
def halt():
    if running():
        pid=int(pidfile.read_text());os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+8
        while running() and time.monotonic()<deadline:time.sleep(.05)
        if running():os.kill(pid,signal.SIGKILL);raise RuntimeError('AGH bounded stop failed')
    pidfile.unlink(missing_ok=True)
if args[-1:]==['AdGuardHome']:
    if args[0]=='show' and 'MainPID' in args:
        print(pidfile.read_text() if running() else '0');sys.exit(0)
    if args[0]=='stop':halt()
    if args[0]=='start' or args[:2]==['enable','--now']:
        if not running():
            work=root/'opt/AdGuardHome'
            with open(root/'real-agh.log','ab') as log:
                p=subprocess.Popen([str(work/'AdGuardHome'),'-c',str(work/'AdGuardHome.yaml'),'-w',str(work),'--no-check-update'],stdout=log,stderr=log,start_new_session=True)
            pidfile.write_text(str(p.pid));deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if not running():raise RuntimeError('AGH exited before readiness')
                try:
                    with socket.create_connection(('127.0.0.1',{t.web}),timeout=.2):break
                except OSError:time.sleep(.05)
            else:raise RuntimeError('AGH readiness expired')
    if args[0]=='is-active' and not running():
        if '--quiet' not in args:print('inactive')
        sys.exit(3)
os.execv({str(original)!r},['systemctl',*args])
''');controller.chmod(0o755)
        ss=f.bin/'ss';ss.write_text(ss.read_text()+f'\nsubprocess.run([{shutil.which("ss")!r},*args],check=True)\n')
        old_curl=f.bin/'curl-fixture';(f.bin/'curl').rename(old_curl)
        old_curl.write_text(old_curl.read_text().replace('name = pathlib.Path(sys.argv[0]).name',"name = 'curl'"))
        (f.bin/'curl').write_text('#!'+sys.executable+'\n'+f'''import os,sys
args=sys.argv[1:]
if '/dns-query?' in args[-1] or '/login.html' in args[-1]:
    os.execv({shutil.which('curl')!r},['curl','--cacert',{str(t.cert)!r},*args])
os.execv({str(old_curl)!r},['curl',*args])
''');(f.bin/'curl').chmod(0o755)
        def control(*args):return subprocess.run([controller,*args],env=f.env,capture_output=True,text=True,timeout=30)
        t.addCleanup(control,'stop','AdGuardHome')
        result=control('enable','--now','AdGuardHome');t.assertEqual(result.returncode,0,result.stderr)
        client_id,_=t.register_doh_client()
        def healthy():
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.settimeout(5);q=question('restore.service.test');sock.sendto(q,('127.0.0.1',t.native));t.dns_answer(q,sock.recv(4096))
            q=question('restore.doh.test');status,body,_=t.request('/dns-query',q,['-H','Content-Type: application/dns-message'])
            t.assertEqual(status,200);t.dns_answer(q,body)
            jar=t.root/'restore-cookies'
            status,_,_=t.request('/'+t.prefix+'/control/login',json.dumps({'name':'admin','password':t.password}).encode(),['-H','Content-Type: application/json','-c',jar])
            t.assertEqual(status,200)
            status,body,_=t.request('/'+t.prefix+'/control/status',options=['-b',jar])
            t.assertEqual(status,200);t.assertEqual(json.loads(body)['version'],'v0.107.79')
            t.doh_matrix(client_id,jar)
        healthy();archive=f.backup();digest=hashlib.sha256(archive.read_bytes()).digest()
        with tarfile.open(archive) as tar:
            queries=tar.extractfile(f.member('/opt/AdGuardHome/data/querylog.json')).read()
        t.assertIn(b'restore.service.test',queries)
        saved_cert=f.path('/etc/letsencrypt/live/example.com/fullchain.pem').read_bytes()
        state.write_bytes(b'changed-after-backup')
        for _ in range(2):
            result=f.run_tool('restore',archive);t.assertEqual(result.returncode,0,result.stdout+result.stderr)
            t.assertEqual((t.work/'data/querylog.json').read_bytes()[:len(queries)],queries)
            t.assertEqual(state.read_bytes(),b'archived-data');t.assertEqual(f.path('/etc/letsencrypt/live/example.com/fullchain.pem').read_bytes(),saved_cert)
            t.assertEqual(hashlib.sha256(archive.read_bytes()).digest(),digest);healthy()
            with sqlite3.connect(f.path('/etc/x-ui/x-ui.db')) as db:
                t.assertEqual(db.execute("SELECT remark FROM inbounds WHERE tag='inbound-12000'").fetchone()[0],'🇫🇮 XTLS')
                t.assertEqual(dict(zip(awg_columns,db.execute("SELECT * FROM inbounds WHERE tag='inbound-8443-udp'").fetchone())),awg_row)
        bad=t.root/'corrupt.tar.gz'
        with tarfile.open(archive) as src,tarfile.open(bad,'w:gz') as dst:
            for entry in src:
                item=copy.copy(entry);data=src.extractfile(entry).read() if entry.isfile() else None
                if entry.name==f.member('/opt/AdGuardHome/AdGuardHome.yaml'):
                    data=data.replace(b'address: 127.0.0.1:',b'address: 0.0.0.0:');item.size=len(data)
                dst.addfile(item,io.BytesIO(data) if data is not None else None)
        (f.root/'commands').write_text('');pid=(f.root/'agh.pid').read_text()
        protected=[t.config,t.work/'managed.json',f.path('/etc/x-ui/x-ui.db'),f.path('/etc/nginx/nginx.conf'),f.path('/etc/letsencrypt/live/example.com/fullchain.pem')]
        before={p:p.read_bytes() for p in protected}
        result=f.run_tool('restore',bad);t.assertNotEqual(result.returncode,0);t.assertNotIn('Restore completed successfully.',result.stdout)
        t.assertEqual({p:p.read_bytes() for p in protected},before)
        t.assertEqual((f.root/'agh.pid').read_text(),pid);t.assertFalse(any(c[:2]==['systemctl','stop'] for c in f.commands()));healthy()
        state.write_bytes(b'target-before-failed-restore');(f.root/'commands').write_text('')
        result=f.run_tool('restore',archive,FAIL_SYSCTL='1',FAIL_ONCE='1')
        t.assertNotEqual(result.returncode,0);t.assertNotIn('Restore completed successfully.',result.stdout)
        t.assertTrue((f.root/'fault-used').exists());t.assertIn(['sysctl','-p',str(f.path('/etc/sysctl.d/99-3x-ui-pro.conf'))],f.commands())
        t.assertTrue(any(c[:2]==['cp','-aT'] and any('.rollback-' in a for a in c) for c in f.commands()))
        t.assertEqual(state.read_bytes(),b'target-before-failed-restore');healthy()
        t.assertEqual(hashlib.sha256(archive.read_bytes()).digest(),digest)
        print('PRIVATE RESTORE: files/AGH/AWG/XTLS/DNS/DoH/admin/TLS/rollback PASS; systemd/Xray/UFW FIXTURE',flush=True)
    finally:
        signal.alarm(0)
        if not t.doCleanups():raise RuntimeError('Real service fixture cleanup failed')
        if not f.doCleanups():raise RuntimeError('Private filesystem cleanup failed')


if __name__=='__main__':run(Path(sys.argv[1]))
