"""Private Change Domains fixtures; real SQLite, certificates and nginx syntax."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from certificate_fixtures import function
from test_personal_xhttp import ROOT, MAIN, SHARED, render, seed
from test_integrated_features import helper

SOURCE = 'b'*40


def rendered_hook(panel, reality, source=None):
    renderer=function('render_certificate_hook',source) if source is not None else function('render_certificate_hook')
    return subprocess.check_output(['bash', '-c', renderer+'\nrender_certificate_hook "$1" "$2"',
                                    'fixture', panel, reality], text=True)


class DomainFixture:
    def __init__(self, root, legacy=False, optional=False):
        self.root = Path(root); self.module = helper('domains')
        self.version='3.10.2' if legacy else '3.11.0'
        self.source=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'show','v2.1.7:x-ui-latest.sh'],cwd=ROOT,text=True) if legacy else (ROOT/'x-ui-latest.sh').read_text()
        self.calls = []; self.fault = None; self.fault_used = False
        self.services = {'x-ui': 'active', 'nginx': 'active', 'mtr-backend': 'active', 'certbot.timer': 'active'}
        self.panel = 'deploy.example'; self.reality = 'cover.example'
        for name in ('etc/x-ui', 'etc/nginx/sites-available', 'etc/nginx/sites-enabled', 'etc/nginx/snippets',
                     'etc/nginx/stream-enabled', 'etc/letsencrypt/renewal-hooks/deploy', 'root/cert/deploy.example',
                     'var/lib', 'var/backups/x-ui', 'var/www/acme', 'usr/local/x-ui/bin'):
            self.p('/'+name).mkdir(parents=True, exist_ok=True)
        self.write('/etc/os-release', 'ID=ubuntu\nVERSION_ID="24.04"\n')
        self.write('/usr/local/x-ui/x-ui', '#!/bin/sh\necho '+self.version+'\n', 0o755)
        self.write('/usr/bin/x-ui', '#!/bin/sh\nexit 0\n', 0o755)
        self.write('/etc/systemd/system/x-ui.service', '[Service]\nExecStart=/usr/local/x-ui/x-ui\nWorkingDirectory=/usr/local/x-ui/\n')
        self.p('/proc/54321').mkdir(parents=True)
        self.p('/proc/54321/exe').symlink_to(self.p('/usr/local/x-ui/x-ui'))
        self.write('/proc/54321/environ','')
        self.cert(self.panel); self.cert(self.reality)
        for name in ('fullchain.pem', 'privkey.pem'):
            self.p('/root/cert/'+self.panel+'/'+name).symlink_to('/etc/letsencrypt/live/'+self.panel+'/'+name)
        self.write(self.module.HOOK, rendered_hook(self.panel, self.reality,self.source), 0o755)
        for name, text in ((self.module.STREAM, render('cat > /etc/nginx/stream-enabled/stream.conf',self.source)),
                           (self.module.HTTP, render('cat > /etc/nginx/sites-available/80.conf',self.source)),
                           ('/etc/nginx/snippets/includes.conf', render(SHARED,self.source)),
                           ('/etc/nginx/sites-available/'+self.panel, render(MAIN,self.source)),
                           ('/etc/nginx/sites-available/'+self.reality, render('cat > "/etc/nginx/sites-available/${reality_domain}"',self.source))):
            self.write(name, text)
        for name in (self.panel, self.reality, '80.conf'):
            self.p('/etc/nginx/sites-enabled/'+name).symlink_to('/etc/nginx/sites-available/'+name)
        self.write('/etc/nginx/nginx.conf', 'load_module /usr/lib/nginx/modules/ngx_stream_module.so;\n'
                   'pid /run/nginx.pid; error_log stderr;\nevents {}\nhttp { include /etc/nginx/sites-enabled/*; }\n'
                   'stream { include /etc/nginx/stream-enabled/*.conf; }\n')
        # The actual map file is a dependency of the actual panel vhost.
        self.write('/etc/nginx/sites-available/00-maps.conf', render('cat > /etc/nginx/sites-available/00-maps.conf'))
        self.p('/etc/nginx/sites-enabled/00-maps.conf').symlink_to('/etc/nginx/sites-available/00-maps.conf')
        self.p('/etc/nginx/snippets/x-ui-auto-optional').mkdir()
        self.write(self.module.CLASH, (ROOT/'assets/clash/clash.yaml').read_text().replace('${DOMAIN}', self.panel).replace('${SUB_PATH}', 'subscription'))
        self.write(self.module.DIAGNOSTICS, (ROOT/'assets/diagnostics/index.html').read_text().replace('__SERVER_DOMAIN__', self.panel))
        rows, hosts = seed(group_id=True,source=self.source)
        with sqlite3.connect(self.p(self.module.DB)) as db:
            for table, records in (('inbounds', list(rows.values())), ('hosts', hosts)):
                names = list(records[0])
                extras = {'inbounds': {'node_id': 0, 'share_addr_strategy': '', 'share_addr': ''},
                          'hosts': {'snis': '[]', 'sni_shared_random': 1, 'host_header': '', 'cipher_suites': '["fixture-cipher"]',
                                    'mihomo_x25519': 1, 'override_sni_from_address': 0, 'keep_sni_blank': 0}}
                for key in extras[table]:
                    if key not in names: names.append(key)
                db.execute('CREATE TABLE '+table+' ('+','.join(name+(' INTEGER PRIMARY KEY' if name == 'id' else
                    ' INTEGER' if name in ('port', 'inbound_id', 'enable', 'node_id', 'sni_shared_random', 'mihomo_x25519',
                                          'override_sni_from_address', 'keep_sni_blank') else ' TEXT') for name in names)+')')
                for row in records:
                    values = {**extras[table], **row}
                    db.execute('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in names)+')', [values[k] for k in names])
            db.execute('CREATE TABLE settings(id INTEGER PRIMARY KEY,key TEXT UNIQUE,value TEXT)')
            settings = dict(webListen='127.0.0.1', subListen='127.0.0.1', webPort='10002', subPort='10001',
                            webBasePath='/panel/', subPath='/subscription/', subJsonPath='/jsonsub/',
                            subURI='https://deploy.example/subscription/', subJsonURI='https://deploy.example/jsonsub/',
                            webDomain='', subDomain='', sessionMaxAge='171', fixtureUserSetting='preserve')
            for key in ('webCertFile', 'subCertFile', 'webKeyFile', 'subKeyFile'):
                settings[key] = '/root/cert/'+self.panel+'/'+('privkey.pem' if 'Key' in key else 'fullchain.pem')
            db.executemany('INSERT INTO settings(key,value) VALUES(?,?)', settings.items())
            db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT,password TEXT,two_factor TEXT)')
            db.execute("INSERT INTO users VALUES(1,'fixture-user','fixture-hash','fixture-two-factor')")
            db.execute('CREATE TABLE clients(id INTEGER PRIMARY KEY,email TEXT,uuid TEXT,password TEXT,sub_id TEXT,client_host_rule_ids TEXT,enable INTEGER)')
            db.execute("INSERT INTO clients VALUES(77,'fixture','fixture-uuid','fixture-password','fixture-sub','[\"fixture-host\"]',1)")
            db.execute('CREATE TABLE client_inbounds(client_id INTEGER,inbound_id INTEGER,flow_override TEXT)')
            db.executemany('INSERT INTO client_inbounds VALUES(77,?,?)', [(r['id'], 'preserve-flow') for r in rows.values()])
            db.execute('CREATE TABLE client_traffics(id INTEGER,up INTEGER,down INTEGER)')
            db.execute('INSERT INTO client_traffics VALUES(77,123456,654321)')
        if optional:
            self.optional()
        self.operation = self.worker()
        context = self.operation.discover()
        if not legacy:
            marker = dict(format=1, layout='nginx-stream-v1', installed_by='source@'+SOURCE, source_ref=SOURCE,
                          **self.module.Operation.summary(context))
            self.write(self.module.MANIFEST, json.dumps(marker), 0o600)

    def p(self, path):
        return self.root/path.lstrip('/')

    def write(self, name, content, mode=0o644):
        path = self.p(name); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content); path.chmod(mode)

    def cert(self, name):
        archive = self.p('/etc/letsencrypt/archive/'+name); archive.mkdir(parents=True, exist_ok=True)
        live = self.p('/etc/letsencrypt/live/'+name); live.mkdir(parents=True, exist_ok=True)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                        '-days', '1', '-subj', '/CN='+name, '-addext', 'subjectAltName=DNS:'+name,
                        '-out', str(archive/'fullchain1.pem'), '-keyout', str(archive/'privkey1.pem')], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for file in ('fullchain', 'privkey'):
            (live/(file+'.pem')).symlink_to('../../archive/'+name+'/'+file+'1.pem')
        self.write('/etc/letsencrypt/renewal/'+name+'.conf',
                   'fullchain = /etc/letsencrypt/live/'+name+'/fullchain.pem\nprivkey = /etc/letsencrypt/live/'+name+'/privkey.pem\n'
                   '[renewalparams]\nauthenticator = webroot\nwebroot_path = /var/www/acme\naccount = '+('a'*32)+'\nserver = https://acme.fixture/directory\n')
        for file in ('meta.json','private_key.json','regr.json'):
            account='/etc/letsencrypt/accounts/acme.fixture/directory/'+('a'*32)+'/'+file
            if not self.p(account).exists():self.write(account,'{}\n',0o600)

    def optional(self):
        vision = helper('vision'); domain = 'vision.example'; self.cert(domain)
        row = vision.inbound(domain, 14500, 14501, '/etc/letsencrypt/live/'+domain+'/fullchain.pem', '/etc/letsencrypt/live/'+domain+'/privkey.pem')
        with sqlite3.connect(self.p(self.module.DB)) as db:
            db.execute('INSERT INTO inbounds(id,protocol,listen,port,settings,stream_settings,enable,node_id) VALUES(99,?,?,?,?,?,?,0)',
                       (row['protocol'],row['listen'],row['port'],json.dumps(row['settings']),json.dumps(row['streamSettings']),1))
            db.execute("INSERT INTO hosts(id,inbound_id,group_id,address,port,security,sni) VALUES(99,99,'vision-group',?,443,'same',?)", (domain,domain))
            db.execute("INSERT INTO inbounds(id,protocol,listen,port,settings,stream_settings,enable,node_id,share_addr_strategy,share_addr) VALUES(100,'amneziawg','0.0.0.0',8443,'{}','',1,0,'custom',?)", (self.panel,))
        self.write(self.module.STREAM, vision.stream_config(self.p(self.module.STREAM).read_text(),domain,14500))
        self.write('/etc/nginx/sites-available/vision.conf', vision.fallback_config(domain,14501))
        self.write('/etc/nginx/sites-available/vision-acme.conf', vision.acme_config(domain,False))
        for name in ('vision.conf','vision-acme.conf'):
            self.p('/etc/nginx/sites-enabled/'+name).symlink_to('/etc/nginx/sites-available/'+name)
        self.write('/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision', '# fixture retained '+domain+'\n',0o755)
        self.write(self.module.AGH, json.dumps(dict(domain=self.panel, path='adg-AbCdEf123456', data='preserve', version='v0.107.79')),0o600)
        self.write('/opt/AdGuardHome/AdGuardHome.yaml','users: [fixture-private-data]\n',0o600)
        self.write('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf','# fixture AdGuard route\n')
        self.write('/usr/local/lib/3x-ui-pro/managed-adguard.sh','# fixture installed helper; never executed\n',0o600)
        self.services['AdGuardHome'] = 'active'

    def worker(self):
        fixture = self
        class Worker(self.module.Operation):
            def run(self, *args, **kwargs):
                args = list(map(str,args)); fixture.calls.append((self.stage,args))
                key = ('backup' if args[:3] == ['bash','fixture-backup','backup'] else
                       'issue-'+args[args.index('--cert-name')+1] if args[0] == 'certbot' else
                       self.stage+':'+':'.join(args[:3]))
                if fixture.fault and not fixture.fault_used and (fixture.fault == key or fixture.fault == self.stage):
                    fixture.fault_used = True
                    raise subprocess.CalledProcessError(1,args)
                if args[0] == 'bash':
                    archive = fixture.p('/var/backups/x-ui/fixture.tar.gz'); archive.write_bytes(b'fixture-full-backup')
                    return json.dumps(dict(status='success',archive=str(archive))).encode() if args[2] == 'backup' else b'{}'
                if args[0].endswith('/usr/local/x-ui/x-ui'):
                    return (fixture.version+'\n').encode()
                if args[0] == 'certbot':
                    fixture.cert(args[args.index('--cert-name')+1]); return b''
                if args[0] == 'systemctl':
                    if args[1] == 'show':
                        if 'UnitFileState' in args:
                            return ('ActiveState='+fixture.services[args[2]]+'\nUnitFileState=enabled\n').encode()
                        return (b'/etc/systemd/system/x-ui.service\n' if 'FragmentPath' in args else b'\n' if 'DropInPaths' in args else b'54321\n' if 'MainPID' in args else b'inactive\n')
                    if args[1] in ('stop','start'):
                        fixture.services[args[2]] = 'inactive' if args[1] == 'stop' else 'active'
                    return b''
                if args[0] == 'nginx':
                    if args[1]=='-T':
                        text=''
                        for path in fixture.p('/etc/nginx/sites-enabled').iterdir():
                            text+='# configuration file /etc/nginx/sites-enabled/'+path.name+':\n'+fixture.p(os.readlink(path)).read_text()+'\n'
                        return text.encode()
                    return b''
                raise AssertionError('Unexpected fixture command')
            def check(self, action, *args):
                fixture.calls.append((self.stage,[action,*args]))
                if fixture.fault == self.stage and not fixture.fault_used:
                    fixture.fault_used=True
                    raise subprocess.CalledProcessError(1,[action])
                if action == 'render-hook':
                    return rendered_hook(*args)
                if action == 'hook':
                    if fixture.p(fixture.module.HOOK).read_text() != rendered_hook(*args):
                        raise fixture.module.Refusal('Unowned project hook.')
                if action == 'health':
                    if not all(v == 'active' for v in fixture.services.values()):
                        raise fixture.module.Refusal('Original services are unhealthy.')
                return ''
            def https_checks(self, context):
                fixture.calls.append((self.stage,['https',context['domains']['panel'],context['domains']['reality']]))
        return Worker('fixture-checks','fixture-backup',self.root)

    def state(self):
        with sqlite3.connect(self.p(self.module.DB)) as db:
            return {name: db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def change(self, panel=None, reality=None):
        context = self.operation.discover(); old = context['domains']
        with patch.object(self.module.socket, 'getaddrinfo', return_value=[(2,1,6,'',('192.0.2.7',443))],
                          side_effect=socket_error() if self.fault=='dns' else None):
            self.operation.change(panel or old['panel'],reality or old['reality'],old['panel'],old['reality'],SOURCE)


class Domains(unittest.TestCase):
    def fixture(self, **kwargs):
        temporary = tempfile.TemporaryDirectory(prefix='domain-operation-'); self.addCleanup(temporary.cleanup)
        return DomainFixture(temporary.name, **kwargs)

    def test_panel_reality_both_preserve_client_keys_ids_new_fields_and_optional_state(self):
        for mode in ('panel','reality','both'):
            with self.subTest(mode=mode):
                f=self.fixture(optional=True); before=f.state(); oldcert=f.p('/etc/letsencrypt/archive/deploy.example/privkey1.pem').read_bytes()
                guards=f.operation.guards(f.operation.discover()); agh=f.p('/opt/AdGuardHome/AdGuardHome.yaml').read_bytes()
                f.change('new-panel.example' if mode!='reality' else None,'new-cover.example' if mode!='panel' else None)
                after=f.state()
                for table in ('clients','users','client_inbounds','client_traffics'):
                    self.assertTrue(before[table]==after[table],table+' changed')
                with f.operation.connection(True) as db:
                    context=f.operation.discover()
                    for previous,current in zip(before['hosts'],after['hosts']):
                        columns=[r[1] for r in db.execute('PRAGMA table_info(hosts)')]; address=columns.index('address')
                        self.assertTrue(previous[:address]+previous[address+1:]==current[:address]+current[address+1:],'Host metadata/IDs changed')
                    for name in ('reality','ws','grpc','hysteria2'):
                        iid=context['inbound_roles'][name]
                        previous=json.loads(next(r for r in before['inbounds'] if r[0]==iid)[list(context['rows'][iid]).index('stream_settings')])
                        current=context['streams'][iid]
                        if name=='reality':
                            previous['realitySettings'].pop('serverNames'); current=copy.deepcopy(current);current['realitySettings'].pop('serverNames')
                            self.assertTrue(previous==current,'REALITY secrets/target changed')
                self.assertEqual(f.operation.guards(context),guards);self.assertEqual(f.p('/opt/AdGuardHome/AdGuardHome.yaml').read_bytes(),agh)
                self.assertTrue(f.p('/etc/letsencrypt/archive/deploy.example/privkey1.pem').read_bytes()==oldcert,'Old certificate key changed')
                self.assertFalse(f.p(f.module.STATE+'/journal.json').exists())
                self.assertTrue(all(v=='active' for v in f.services.values()))

    def test_legacy_adoption_and_repeated_switch_without_reinstall(self):
        f=self.fixture(legacy=True)
        self.assertFalse(f.p(f.module.MANIFEST).exists())
        f.change('second.example','second-cover.example')
        self.assertEqual(json.loads(f.p(f.module.MANIFEST).read_text())['installed_by'],'legacy-v2.1.7-layout')
        f.change('third.example')
        self.assertEqual(f.operation.discover()['domains']['panel'],'third.example')
        self.assertFalse(any('migrate' in args or 'install' in args for _,args in f.calls))

    def test_official_archive_orphan_owner_is_preserved_and_live_owners_are_refused(self):
        import pwd
        for legacy in (False,True):
            f=self.fixture(legacy=legacy)
            for name in ('/usr/local/x-ui','/usr/local/x-ui/x-ui'):os.chown(f.p(name),1001,1001)
            with patch.object(pwd,'getpwuid',side_effect=KeyError):f.change('new.example')
            self.assertEqual(f.p('/usr/local/x-ui/x-ui').stat().st_uid,1001)
        for kind in ('account','process','other-uid'):
            f=self.fixture();uid=1002 if kind=='other-uid' else 1001
            for name in ('/usr/local/x-ui','/usr/local/x-ui/x-ui'):os.chown(f.p(name),uid,uid)
            if kind=='process':f.write('/proc/77/status','Uid:\t1001\t1001\t1001\t1001\n')
            before=f.state()
            with patch.object(pwd,'getpwuid',**({'return_value':object()} if kind=='account' else {'side_effect':KeyError})),self.assertRaises(f.module.Refusal):
                f.change('new.example')
            self.assertTrue(f.state()==before,'Unknown binary owner changed SQLite')
            self.assertFalse(any(args[:3]==['bash','fixture-backup','backup'] for _,args in f.calls))

    def test_invalid_unchanged_swap_vision_conflict_foreign_cert_and_overrides_refuse_before_backup(self):
        cases=('unchanged','invalid','same','swap','vision','foreign','manifest','sni','r-sni-blank','unknown-stream','duplicate-host','schema','kernel','nginx-name')
        for case in cases:
            with self.subTest(case=case):
                f=self.fixture(optional=True); panel='new.example'; reality=f.reality
                if case=='unchanged': panel=f.panel
                if case=='invalid': panel='bad.example/'
                if case=='same': panel=reality
                if case=='swap': panel,reality=f.reality,f.panel
                if case=='vision': panel='vision.example'
                if case=='r-sni-blank': panel,reality=f.panel,'new-cover.example'
                if case=='foreign': f.cert(panel)
                if case=='nginx-name':
                    f.write('/etc/nginx/sites-available/foreign.conf','server { server_name new.example; }\n')
                    f.p('/etc/nginx/sites-enabled/foreign.conf').symlink_to('/etc/nginx/sites-available/foreign.conf')
                if case=='manifest':
                    value=json.loads(f.p(f.module.MANIFEST).read_text());value['domains']['panel']='wrong.example';f.write(f.module.MANIFEST,json.dumps(value),0o600)
                if case=='unknown-stream': f.write(f.module.STREAM,f.p(f.module.STREAM).read_text()+'upstream foreign { server 127.0.0.1:12345; }\n')
                with sqlite3.connect(f.p(f.module.DB)) as db:
                    if case=='sni':db.execute("UPDATE hosts SET sni='custom.example' WHERE id=1")
                    if case=='r-sni-blank':db.execute('UPDATE hosts SET keep_sni_blank=1 WHERE id=1')
                    if case=='duplicate-host':
                        db.execute("INSERT INTO hosts(id,group_id,inbound_id,address,port,security) SELECT 501,'other-group',inbound_id,address,port,security FROM hosts WHERE id=1")
                    if case=='schema':db.execute('ALTER TABLE hosts RENAME COLUMN group_id TO unknown')
                    if case=='kernel':db.execute('UPDATE inbounds SET settings=? WHERE id=100',(json.dumps({'server':{'kernelMode':True}}),))
                before=f.state()
                with self.assertRaises(f.module.Refusal): f.change(panel,reality)
                self.assertTrue(f.state()==before,'Refusal changed SQLite')
                self.assertFalse(any(args[:3]==['bash','fixture-backup','backup'] for _,args in f.calls))
                self.assertFalse(f.p(f.module.STATE+'/journal.json').exists())

    def test_failures_backup_dns_second_acme_nginx_sqlite_and_start_preserve_original(self):
        for failure in ('backup','dns','issue-new-cover.example','validating complete candidate nginx','switching:nginx:-t',
                        'switching:systemctl:start:x-ui','sqlite'):
            with self.subTest(failure=failure):
                f=self.fixture(optional=True);before=f.state();manifest=f.p(f.module.MANIFEST).read_bytes();old=f.operation.guards(f.operation.discover())
                f.fault=failure
                if failure=='dns':
                    context=patch.object(f.module.socket,'getaddrinfo',side_effect=socket_error())
                elif failure=='sqlite':
                    original=f.operation.database_update
                    def update(record,forward):
                        if forward:raise sqlite3.OperationalError('fixture')
                        return original(record,forward)
                    context=patch.object(f.operation,'database_update',side_effect=update)
                else:context=patch.object(f,'fault',failure)
                with context, self.assertRaises(Exception): f.change('new-panel.example','new-cover.example')
                if failure not in ('dns','sqlite'):self.assertTrue(f.fault_used,'Requested failure point was not exercised')
                self.assertTrue(f.state()==before,'Failure changed SQLite')
                self.assertEqual(f.p(f.module.MANIFEST).read_bytes(),manifest)
                self.assertEqual(f.operation.guards(f.operation.discover()),old)
                self.assertTrue(all(v=='active' for v in f.services.values()))
                self.assertFalse(f.p(f.module.STATE+'/journal.json').exists())
                if failure=='issue-new-cover.example':self.assertTrue(f.p('/etc/letsencrypt/live/new-panel.example').is_dir())
        f=self.fixture();before=f.state();run=f.operation.run
        def failed_backup(*args,**kwargs):
            if list(args[:3])==['bash','fixture-backup','backup']:
                f.services['x-ui']='inactive'
                raise subprocess.CalledProcessError(1,args)
            return run(*args,**kwargs)
        with patch.object(f.operation,'run',side_effect=failed_backup),self.assertRaisesRegex(f.module.Refusal,'ROLLBACK_UNVERIFIED'):
            f.change('new.example')
        self.assertTrue(f.state()==before,'Failed Backup cleanup modified SQLite')
        self.assertFalse(any(args[0]=='certbot' for _,args in f.calls))

    def test_sigkill_switching_recovers_idempotently_before_another_change(self):
        for phase in ('prepared','switching'):
            with self.subTest(phase=phase):
                f=self.fixture(); before=f.state()
                pid=os.fork()
                if pid==0:
                    if phase=='switching':
                        original=f.operation.database_update
                        def crash(record,forward):
                            original(record,forward)
                            if forward: os.kill(os.getpid(),signal.SIGKILL)
                        f.operation.database_update=crash
                    else:
                        original=f.operation.issue
                        def crash(name,previous):
                            original(name,previous)
                            os.kill(os.getpid(),signal.SIGKILL)
                        f.operation.issue=crash
                    try:f.change('new-panel.example','new-cover.example')
                    finally:os._exit(3)
                _,status=os.waitpid(pid,0)
                self.assertEqual(os.waitstatus_to_exitcode(status),-signal.SIGKILL)
                self.assertEqual(json.loads(f.p(f.module.STATE+'/journal.json').read_text())['phase'],phase)
                self.assertTrue(f.operation.recover());self.assertFalse(f.operation.recover())
                self.assertTrue(f.state()==before,'Crash recovery did not preserve the original DB')
                f.change('again.example','again-cover.example')

    def test_real_complete_nginx_candidate_observes_included_dependencies(self):
        nginx=os.environ.get('NGINX_BIN')
        self.assertTrue(nginx,'Real nginx is required for domain candidate validation')
        f=self.fixture();context=f.operation.discover()
        files,marker=f.operation.file_plan(context,'new.example','new-cover.example',SOURCE)
        record=dict(format=1,phase='prepared',old=f.operation.summary(context),new={},files=files,database=[],guards={},backup='fixture')
        f.operation.journal(record);f.cert('new.example');f.cert('new-cover.example')
        def real(*args,**kwargs):
            if args[0]!='nginx':raise AssertionError('Unexpected command')
            tree=Path(args[-1]).parent
            for path in tree.rglob('*'):
                if path.is_file() and not path.is_symlink():
                    text=path.read_text()
                    text=text.replace('/etc/letsencrypt/live/',str(f.p('/etc/letsencrypt/live'))+'/')
                    path.write_text(text)
            return subprocess.check_output([nginx,*map(str,args[1:])],stderr=subprocess.STDOUT,timeout=30)
        with patch.object(f.operation,'run',side_effect=real):f.operation.candidate_nginx(record)
        old=f.p(f.module.STREAM).read_bytes()
        f.write('/etc/nginx/snippets/includes.conf','xui_fixture_invalid_directive on;\n')
        with patch.object(f.operation,'run',side_effect=real),self.assertRaises(subprocess.CalledProcessError):
            f.operation.candidate_nginx(record)
        self.assertEqual(f.p(f.module.STREAM).read_bytes(),old)

    def test_sqlite_wal_and_unhealthy_source_before_mutations(self):
        f=self.fixture(); connection=sqlite3.connect(f.p(f.module.DB));self.addCleanup(connection.close)
        self.assertEqual(connection.execute('PRAGMA journal_mode=WAL').fetchone()[0],'wal')
        before=f.state();f.change('new.example')
        self.assertTrue(f.state()['clients']==before['clients'],'WAL client state changed')
        self.assertEqual(connection.execute('PRAGMA quick_check').fetchone(),('ok',))
        f=self.fixture();f.services['nginx']='inactive';before=f.state()
        with self.assertRaises(f.module.Refusal):f.change('new.example')
        self.assertTrue(f.state()==before,'Unhealthy source was modified')
        self.assertFalse(any(args[:3]==['bash','fixture-backup','backup'] for _,args in f.calls))

    def test_busy_wal_failure_recovers_without_overwriting_unchanged_database(self):
        f=self.fixture();writer=sqlite3.connect(f.p(f.module.DB));self.addCleanup(writer.close)
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute("UPDATE settings SET value='one' WHERE key='fixtureUserSetting'");writer.commit()
        reader=sqlite3.connect(f.p(f.module.DB));self.addCleanup(reader.close)
        reader.execute('BEGIN');reader.execute('SELECT * FROM settings').fetchall()
        writer.execute("UPDATE settings SET value='two' WHERE key='fixtureUserSetting'");writer.commit()
        before=f.state();connect=f.operation.connection
        def connection(readonly=False):
            db=connect(readonly);db.execute('PRAGMA busy_timeout=50');return db
        with patch.object(f.operation,'connection',side_effect=connection),self.assertRaises(f.module.Refusal):
            f.change('new.example')
        reader.rollback()
        self.assertTrue(f.state()==before,'Busy WAL recovery wrote unrelated data')
        self.assertFalse(f.p(f.module.STATE+'/journal.json').exists())
        self.assertTrue(all(value=='active' for value in f.services.values()))

    def test_interrupted_backup_child_can_finish_its_existing_cleanup(self):
        f=self.fixture();started=f.root/'backup-started';restored=f.root/'backup-cleaned'
        script=f.root/'backup-child.sh'
        script.write_text('trap \'touch "$2"; exit 143\' TERM\ntouch "$1"\nwhile :; do sleep .05; done\n')
        pid=os.fork()
        if pid==0:
            fd=os.open(f.root/'lock',os.O_CREAT|os.O_RDWR,0o600);os.dup2(fd,9)
            def interrupted(signum,frame):raise f.module.Refusal('fixture interruption')
            signal.signal(signal.SIGTERM,interrupted)
            try:f.module.Operation('unused','unused',f.root).run('bash',script,started,restored,inherit_lock=True,timeout=20)
            except f.module.Refusal:os._exit(0)
            except BaseException:os._exit(4)
            os._exit(3)
        deadline=time.monotonic()+8
        try:
            while not started.exists() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue(started.exists(),'Private Backup child did not start')
            os.kill(pid,signal.SIGTERM)
            while time.monotonic()<deadline:
                completed,status=os.waitpid(pid,os.WNOHANG)
                if completed:break
                time.sleep(.02)
            else:self.fail('Backup interruption cleanup did not finish')
            pid=0
            self.assertEqual(os.waitstatus_to_exitcode(status),0)
            self.assertTrue(restored.exists(),'Backup was killed before its existing service cleanup could run')
        finally:
            if pid:
                os.kill(pid,signal.SIGKILL);os.waitpid(pid,0)

    def backup_fixture(self, f):
        from test_personal_backup import PersonalBackup, relocated
        backup=PersonalBackup('runTest');backup.setUp();self.addCleanup(backup.doCleanups)
        def sync():
            for name in ('/etc/x-ui','/etc/nginx','/etc/letsencrypt','/root/cert','/var/www/subpage'):
                shutil.rmtree(backup.path(name));shutil.copytree(f.p(name),backup.path(name),symlinks=True)
            for name in ('/etc/nginx','/etc/letsencrypt','/root/cert','/var/www/subpage'):
                for path in backup.path(name).rglob('*'):
                    if path.is_symlink():
                        target=os.readlink(path)
                        if target.startswith('/'):
                            path.unlink();path.symlink_to(relocated(target,backup.root))
                    elif path.is_file() and path.suffix!='.pem':
                        path.write_text(relocated(path.read_text(),backup.root))
            with sqlite3.connect(backup.path(f.module.DB)) as db:
                for key,value in db.execute('SELECT key,value FROM settings').fetchall():
                    db.execute('UPDATE settings SET value=? WHERE key=?',(relocated(value,backup.root),key))
                for iid,stream in db.execute('SELECT id,stream_settings FROM inbounds').fetchall():
                    db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(relocated(stream,backup.root),iid))
            # Relocating fixture paths changes renewal bytes, but not their ownership.
            marker=backup.path(f.module.MANIFEST);data=json.loads(marker.read_text())
            for name in data.get('retained_domains',{}):
                data['retained_domains'][name]=hashlib.sha256(backup.path('/etc/letsencrypt/renewal/'+name+'.conf').read_bytes()).hexdigest()
            marker.write_text(json.dumps(data))
        def state():
            with sqlite3.connect(backup.path(f.module.DB)) as db:
                return {name:db.execute('SELECT * FROM "'+name+'" ORDER BY rowid').fetchall()
                        for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        sync()
        return backup,sync,state

    def test_updated_state_round_trips_through_existing_backup_v3(self):
        f=self.fixture();f.change('new.example','new-cover.example')
        backup,_,state=self.backup_fixture(f)
        before=state();archive=backup.backup()
        with sqlite3.connect(backup.path(f.module.DB)) as db:db.execute("UPDATE clients SET password='fixture-damage'")
        result=backup.run_tool('restore',archive)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(state()==before,'Backup v3 did not preserve the post-switch SQLite state')

    def test_original_backup_restores_after_both_and_repeated_restore(self):
        f=self.fixture();backup,sync,state=self.backup_fixture(f)
        before=state();archive=backup.backup();saved=archive.read_bytes()
        certificates={str(path.relative_to(backup.root)):path.read_bytes()
                      for name in (f.panel,f.reality) for path in backup.path('/etc/letsencrypt/archive/'+name).glob('*.pem')}
        f.change('new.example','new-cover.example');sync()
        self.assertNotEqual(state(),before)
        # A legitimate renewal may replace PEM/key bytes without changing the
        # recorded renewal configuration. Restore must still restore its archive.
        for name in (f.panel,f.reality):
            directory=backup.path('/etc/letsencrypt/archive/'+name)
            subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1',
                '-nodes','-days','1','-subj','/CN='+name,'-addext','subjectAltName=DNS:'+name,
                '-out',str(directory/'fullchain1.pem'),'-keyout',str(directory/'privkey1.pem')],
                check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(2):
            result=backup.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertTrue(state()==before,'Restore changed original SQLite/client/inbound/key state')
            self.assertTrue(all((backup.root/name).read_bytes()==value for name,value in certificates.items()),'Original certificates changed')
            self.assertEqual(json.loads(backup.path(f.module.MANIFEST).read_text())['domains']['panel'],f.panel)
            self.assertTrue(archive.read_bytes()==saved,'Restore modified the source archive')

    def test_retained_lineage_preflight_refuses_tampered_or_unowned_state(self):
        f=self.fixture();backup,sync,state=self.backup_fixture(f);archive=backup.backup()
        f.change('new.example','new-cover.example');sync();before=state()
        stage=backup.root/'ownership-stage'
        extracted=backup.run_tool('extract',archive,stage)
        self.assertEqual(extracted.returncode,0,extracted.stderr)
        marker=backup.path(f.module.MANIFEST);config=backup.path('/etc/letsencrypt/renewal/'+f.panel+'.conf')
        original=marker.read_bytes();renewal=config.read_bytes()
        live=backup.path('/etc/letsencrypt/live/'+f.panel+'/fullchain.pem');link=os.readlink(live)
        key=backup.path('/etc/letsencrypt/archive/'+f.panel+'/privkey1.pem');private=key.read_bytes()
        cert=backup.path('/etc/letsencrypt/archive/'+f.panel+'/fullchain1.pem');public=cert.read_bytes()
        def preflight():
            return subprocess.run(['bash','-c','source "$1"; STAGING=$2; preflight_target_certbot_ownership',
                'fixture',str(backup.script),str(stage)],env=backup.env,capture_output=True,text=True)
        self.assertEqual(preflight().returncode,0,'Valid retained ownership was refused')
        staged_marker=stage/'files'/str(marker).lstrip('/');staged_original=staged_marker.read_bytes()
        for fault in ('missing-record','archive-evidence-only','wrong-hash','renewal-edit','invalid-renewal','per-lineage-hook',
                      'wrong-current-domains','unknown-format','invalid-source','duplicate-key','public-manifest',
                      'unowned-manifest','manifest-symlink','manifest-hardlink','unsafe-parent',
                      'wrong-san','wrong-key','escaped-live-link'):
            with self.subTest(fault=fault):
                data=json.loads(original)
                if fault in ('missing-record','archive-evidence-only'):
                    if fault=='archive-evidence-only':staged_marker.write_bytes(original)
                    data['retained_domains'].pop(f.panel)
                elif fault=='wrong-hash':data['retained_domains'][f.panel]='0'*64
                elif fault=='wrong-current-domains':data['domains']['panel']='foreign.example'
                elif fault=='unknown-format':data['format']=99
                elif fault=='invalid-source':data['domain_change_source']=int('1'*40)
                elif fault in ('renewal-edit','invalid-renewal','per-lineage-hook'):
                    config.write_bytes(renewal+(b'\n# independent edit\n' if fault=='renewal-edit' else
                        b'\n[broken\n' if fault=='invalid-renewal' else b'\ndeploy_hook = /bin/true\n'))
                    if fault!='renewal-edit':data['retained_domains'][f.panel]=hashlib.sha256(config.read_bytes()).hexdigest()
                marker.write_text(json.dumps(data))
                if fault=='duplicate-key':marker.write_text('{"format":1,'+marker.read_text()[1:])
                elif fault=='public-manifest':marker.chmod(0o644)
                elif fault=='unowned-manifest':os.chown(marker,1001,1001)
                elif fault=='manifest-symlink':marker.rename(marker.with_suffix('.saved'));marker.symlink_to(marker.with_suffix('.saved'))
                elif fault=='manifest-hardlink':os.link(marker,marker.with_suffix('.linked'))
                elif fault=='unsafe-parent':marker.parent.chmod(0o777)
                elif fault=='wrong-san':
                    for target,name in ((cert,'fullchain1.pem'),(key,'privkey1.pem')):
                        target.write_bytes(backup.path('/etc/letsencrypt/archive/new.example/'+name).read_bytes())
                elif fault=='wrong-key':key.write_bytes(backup.path('/etc/letsencrypt/archive/'+f.reality+'/privkey1.pem').read_bytes())
                elif fault=='escaped-live-link':live.unlink();live.symlink_to(backup.path('/etc/letsencrypt/archive/'+f.reality+'/fullchain1.pem'))
                try:
                    result=preflight()
                    self.assertNotEqual(result.returncode,0,'Unverified retained ownership accepted: '+fault)
                    self.assertTrue(state()==before,'Ownership preflight mutated SQLite')
                finally:
                    marker.parent.chmod(0o755)
                    if marker.is_symlink():marker.unlink();marker.with_suffix('.saved').rename(marker)
                    marker.with_suffix('.linked').unlink(missing_ok=True)
                    os.chown(marker,0,0);marker.chmod(0o600);marker.write_bytes(original)
                    config.write_bytes(renewal);cert.write_bytes(public);key.write_bytes(private)
                    staged_marker.write_bytes(staged_original)
                    if os.readlink(live)!=link:live.unlink();live.symlink_to(link)
        self.assertEqual(preflight().returncode,0,'Preflight was not repeatable')
        for fault in ('missing-record','renewal-edit'):
            with self.subTest(full_restore_refusal=fault):
                data=json.loads(original)
                if fault=='missing-record':data['retained_domains'].pop(f.panel)
                else:config.write_bytes(renewal+b'\n# independent edit\n')
                marker.write_text(json.dumps(data));(backup.root/'commands').write_text('')
                try:
                    result=backup.run_tool('restore',archive)
                    self.assertNotEqual(result.returncode,0)
                    self.assertTrue(state()==before,'Failed ownership check mutated SQLite')
                    self.assertFalse(any(c[:2]==['systemctl','stop'] for c in backup.commands()))
                finally:
                    marker.write_bytes(original);config.write_bytes(renewal)

    def test_unverified_recovery_retains_journal_and_refuses_independent_file_changes(self):
        f=self.fixture();f.fault='verifying new stack'
        original=f.operation.recover
        with patch.object(f.operation,'recover',side_effect=OSError('fixture')),self.assertRaises(f.module.Refusal):
            f.change('new-panel.example','new-cover.example')
        self.assertTrue(f.p(f.module.STATE+'/journal.json').exists())
        f.write(f.module.STREAM,f.p(f.module.STREAM).read_text()+'# independent administrator edit\n')
        with self.assertRaises(f.module.Refusal):original()
        self.assertTrue(f.p(f.module.STATE+'/journal.json').exists())

    def test_recovery_refuses_an_independently_changed_panel_version(self):
        f=self.fixture();f.fault='verifying new stack'
        with patch.object(f.operation,'recover',side_effect=OSError('fixture')),self.assertRaises(f.module.Refusal):
            f.change('new-panel.example','new-cover.example')
        before=f.state();f.version='9.9.9'
        with self.assertRaises(f.module.Refusal):f.operation.recover()
        self.assertTrue(f.state()==before,'Recovery wrote an independently changed installation')
        self.assertTrue(f.p(f.module.STATE+'/journal.json').exists())

    def test_committed_cleanup_failure_never_rolls_back_healthy_new_stack(self):
        f=self.fixture();original=f.operation.finish
        with patch.object(f.operation,'finish',side_effect=OSError('fixture')):
            f.change('new-panel.example','new-cover.example')
        self.assertEqual(json.loads(f.p(f.module.STATE+'/journal.json').read_text())['phase'],'committed')
        self.assertEqual(f.operation.discover()['domains']['panel'],'new-panel.example')
        with patch.object(f.operation,'finish',side_effect=original):self.assertTrue(f.operation.recover())
        self.assertEqual(f.operation.discover()['domains']['panel'],'new-panel.example')


def socket_error():
    import socket
    return socket.gaierror('fixture DNS failure')
