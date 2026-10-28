"""Actual entrypoint/TTY acceptance and private Backup management contracts."""
import os
from pathlib import Path
import pty
import select
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def tty_run(script, answers, timeout=8, env=None):
    master, slave = pty.openpty()
    process = subprocess.Popen(['bash', str(script)], stdin=slave, stdout=slave, stderr=slave,
                               env={**os.environ, **(env or {}), 'TERM':'dumb', 'NO_COLOR':'1'})
    os.close(slave)
    output = bytearray()
    os.write(master, answers)
    deadline = time.monotonic()+timeout
    try:
        while time.monotonic()<deadline:
            if select.select([master],[],[],.1)[0]:
                try: chunk=os.read(master,65536)
                except OSError: break
                if not chunk: break
                output.extend(chunk)
            if process.poll() is not None: break
        process.wait(timeout=2)
    finally:
        if process.poll() is None: process.kill(); process.wait()
        os.close(master)
    return process.returncode, output.decode(errors='replace')


class Manager(unittest.TestCase):
    def test_import_has_no_effects_and_preserves_traps(self):
        import re
        pattern=r'^acquire_stack_lock\(\) \{.*?^\}'
        self.assertEqual(re.search(pattern,(ROOT/'x-ui-latest.sh').read_text(),re.M|re.S)[0],
                         re.search(pattern,(ROOT/'assets/backup/x-ui-backup.sh').read_text(),re.M|re.S)[0])
        result=subprocess.run(['bash','-c','trap ":" EXIT; before=$(trap -p); source "$1"; '
            '[[ $(trap -p) == "$before" && -z ${config_password:-} && -z ${IP4:-} ]]',
            'fixture',str(ROOT/'x-ui-latest.sh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(result.stdout,'')

    def test_real_entrypoint_tty_exit_back_invalid_and_no_tty(self):
        for answers in (b'0\n',b'2\n3\n0\n0\n'):
            code,text=tty_run(ROOT/'x-ui-latest.sh',answers)
            self.assertEqual(code,0,text)
            self.assertIn('1. Installation',text)
            self.assertIn('3. Backups',text)
            self.assertNotIn('\x1b',text)
            self.assertNotIn('Change Domains',text)
        result=subprocess.run(['bash',str(ROOT/'x-ui-latest.sh')],input='1\n',text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('TTY',result.stdout+result.stderr)

    def test_menu_failure_status_and_mutable_source_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'entry.sh'
            script.write_text('source "'+str(ROOT/'x-ui-latest.sh')+'"\nrun_installation() { return 42; }; manager_menu\n')
            code,text=tty_run(script,b'1\n')
            self.assertEqual(code,42,text);self.assertIn('FAILED (exit 42)',text);self.assertNotIn('SUCCESS',text)
            for match in (True,False):
                downloaded=Path(tmp)/'source';downloaded.write_bytes((ROOT/'x-ui-latest.sh').read_bytes() if match else b'wrong source')
                code='source "$1"; curl() { if [[ "$*" == *api.github.com* ]]; then echo \'{"sha":"'+('b'*40)+'"}\'; else command cp "$2" "${@: -1}"; fi; }; pin_project_source'
                # Give curl fixture access to its own source argument through a global.
                code=code.replace('command cp "$2"','command cp "$DOWNLOAD"')
                result=subprocess.run(['bash','-c',code,'fixture',str(ROOT/'x-ui-latest.sh')],capture_output=True,text=True,env={**os.environ,'DOWNLOAD':str(downloaded)})
                self.assertEqual(result.returncode,0 if match else 1,result.stderr)


class ManagerBackup(unittest.TestCase):
    def setUp(self):
        from test_personal_backup import PersonalBackup
        self.f=PersonalBackup('runTest');self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_post_restore_security_trust_cleanup_status_lock_and_partial_result(self):
        from test_personal_backup import relocated
        root = self.f.root
        library = relocated((ROOT/'x-ui-latest.sh').read_text(), root)
        library = library.replace(str(root)+'/proc/', '/proc/').replace('/run/xui-restore-security', str(root)+'/run/xui-restore-security')
        library = library.replace('/run/3x-ui-auto-nginx', str(root)+'/run/3x-ui-auto-nginx')
        script = root/'manager.sh'; script.write_text(library)
        helper = self.f.path('/usr/local/bin/x-ui-backup'); helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text('''#!/bin/bash
case $1 in
 inspect) exit 0 ;;
 restore)
   printf restored > "$FIXTURE_ROOT/restored"
   mkdir -p "$FIXTURE_ROOT/usr/local/lib/3x-ui-pro"
   printf 'raise RuntimeError("ARCHIVE HELPER EXECUTED")' > "$FIXTURE_ROOT/usr/local/lib/3x-ui-pro/managed-security.py"
   echo 'Restore completed successfully.'
   trap 'exit "${RESTORE_EXIT:-0}"' EXIT ;;
esac
'''); helper.chmod(0o755)
        trusted = root/'trusted.py'
        trusted.write_text('''import json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ['FIXTURE_ROOT'])
assert sys.flags.isolated and pathlib.Path(__file__).parent.stat().st_mode & 0o777 == 0o700
assert (root/'restored').read_text() == 'restored'
assert subprocess.run(['flock','-n',str(root/'run/3x-ui-auto-nginx/operation.lock'),'true']).returncode != 0
with (root/'security-ran').open('a') as out: out.write('ufw' if sys.argv[1:] else 'apt')
if sys.argv[1:]: result = dict(status='preserved')
else: result = dict(status='partial' if os.environ.get('SECURITY_FAIL') else 'configured',
                   apt='failed_rolled_back' if os.environ.get('SECURITY_FAIL') else 'configured', fail2ban='configured')
print(json.dumps(result))
sys.exit(1 if result['status']=='partial' else 0)
''')
        code = '''source "$1"
prepare_backup_helper() { :; }
pin_project_source() { PROJECT_SOURCE_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; PROJECT_REF=$PROJECT_SOURCE_SHA; GITHUB_RAW=https://source.invalid/$PROJECT_SOURCE_SHA; }
curl() { [[ ${PREP_FAIL:-0} != 1 && "$*" == *aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/assets/security/managed.py* ]] || return 1; cp "$TRUSTED_HELPER" "${@: -1}"; touch "$FIXTURE_ROOT/prepared"; }
manager_menu
'''
        for scenario, answers, flags, expected, ran in (
            ('none', 'n\nn\nYES\n', {}, 0, ''),
            ('success', 'y\ny\nYES\n', {}, 0, 'aptufw'),
            ('partial', 'y\ny\nYES\n', {'SECURITY_FAIL':'1'}, 1, 'aptufw'),
            ('cleanup', 'y\ny\nYES\n', {'RESTORE_EXIT':'42'}, 42, ''),
            ('prep-continue', 'y\ny\nYES\ny\n', {'PREP_FAIL':'1'}, 0, ''),
            ('prep-cancel', 'y\ny\nYES\nn\n', {'PREP_FAIL':'1'}, 0, ''),
        ):
            with self.subTest(scenario=scenario):
                for name in ('security-ran', 'prepared', 'restored'): (root/name).unlink(missing_ok=True)
                result = subprocess.run(['bash','-c',code,'fixture',str(script)],
                    input='3\n3\n/archive.tar.gz\n'+answers+'0\n', text=True, capture_output=True,
                    env={**self.f.env, 'TRUSTED_HELPER':str(trusted), 'PYTHONPATH':str(root), **flags})
                self.assertEqual(result.returncode, expected, result.stdout+result.stderr)
                self.assertEqual((root/'security-ran').read_text() if (root/'security-ran').exists() else '', ran)
                self.assertFalse(list((root/'run').glob('xui-restore-security.*')))
                if scenario == 'partial':
                    self.assertIn('Restore: SUCCESS', result.stdout)
                    self.assertIn('Overall: PARTIAL', result.stdout)
                    self.assertNotIn('Overall: SUCCESS', result.stdout)
                    self.assertNotIn('Restore: FAILED', result.stdout)
                    self.assertEqual((root/'restored').read_text(), 'restored')
                elif scenario == 'cleanup':
                    self.assertNotIn('Restore: SUCCESS', result.stdout)
                elif scenario == 'none':
                    self.assertFalse((root/'prepared').exists())
                    self.assertIn('UFW: NOT_REQUESTED', result.stdout)
                elif scenario == 'prep-cancel': self.assertFalse((root/'restored').exists())

    def test_inherited_backup_json_keeps_default_cli(self):
        result=self.f.run_tool('backup',BACKUP_JSON='1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Backup completed successfully.',result.stdout)
        self.assertNotIn('"status": "success"',result.stdout)
        archive=next(self.f.path('/var/backups/x-ui').glob('*.tar.gz'))
        self.assertEqual(self.f.run_tool('inspect',archive).returncode,0)

    def test_helper_refuses_writable_target_ancestry_before_execution_or_replacement(self):
        from test_personal_backup import function, relocated
        names=('backup_helper_path_safe','backup_helper_compatible','install_backup_tool','prepare_backup_helper')
        helpers='\n'.join(relocated(function(n),self.f.root).replace(' /usr ', ' '+str(self.f.root/'usr')+' ')
                          for n in names if n+'() {' in (ROOT/'x-ui-latest.sh').read_text())
        target=self.f.path('/usr/local/bin/x-ui-backup');target.parent.mkdir(parents=True,exist_ok=True)
        executed=self.f.root/'helper-executed'
        source='#!/bin/bash\ntouch "'+str(executed)+'"\ncase $1 in capabilities) echo "xui-backup:1 inspect backup-json lock-fd9";; lock-check) [[ -e /proc/$$/fd/9 ]] || exit 75;; esac\n'
        setup='msg_err() { echo "$*" >&2; }; pin_project_source() { GITHUB_RAW=https://source.invalid/exact; }; curl() { command cp "'+str(self.f.script)+'" "${@: -1}"; };\n'
        for directory in (target.parent,target.parent.parent,self.f.root/'usr'):
            for action in ('backup_helper_compatible','install_backup_tool','prepare_backup_helper'):
                with self.subTest(directory=directory.relative_to(self.f.root),action=action):
                    target.write_text(source);target.chmod(0o755);executed.unlink(missing_ok=True)
                    directory.chmod(0o775)
                    try:
                        result=subprocess.run(['bash','-c',self.lock_script('acquire_stack_lock || exit $?')+'\n'+helpers+'\n'+setup+action],capture_output=True,text=True)
                        self.assertNotEqual(result.returncode,0,result.stderr)
                        self.assertFalse(executed.exists(),'Helper in writable ancestry was executed')
                        self.assertEqual(target.read_text(),source)
                        self.assertEqual(directory.stat().st_mode&0o777,0o775)
                    finally:directory.chmod(0o755)

    def test_restore_menu_failure_stops_session_and_preserves_recovery_contract(self):
        import json
        from test_personal_backup import relocated
        archive=self.f.backup()
        self.f.write('/etc/x-ui/target-marker','previous target')
        before=json.loads((self.f.root/'services.json').read_text())
        helper=self.f.path('/usr/local/bin/x-ui-backup');helper.parent.mkdir(parents=True,exist_ok=True)
        helper.write_bytes(self.f.script.read_bytes());helper.chmod(0o755)
        library=relocated((ROOT/'x-ui-latest.sh').read_text(),self.f.root)
        library=library.replace(str(self.f.root)+'/proc/','/proc/').replace('/run/3x-ui-auto-nginx',str(self.f.root)+'/run/3x-ui-auto-nginx')
        library=library.replace(' /usr ', ' '+str(self.f.root/'usr')+' ')
        script=self.f.root/'menu.sh';script.write_text(library)
        for scenario,flags in (('pre-mutation',{'FAIL_NGINX':'1'}),
                               ('verified',{'FAIL_HEALTH_SERVICE':'mtr-backend','FAIL_ONCE':'1'}),
                               ('unverified',{'FAIL_HEALTH_SERVICE':'mtr-backend'})):
            with self.subTest(scenario=scenario):
                (self.f.root/'commands').write_text('');(self.f.root/'fault-used').unlink(missing_ok=True)
                code,text=tty_run(script,b'3\n3\n'+str(archive).encode()+b'\nn\nn\nYES\n1\n',timeout=90,env={**self.f.env,**flags})
                self.assertNotEqual(code,0,text)
                self.assertIn('Restore: FAILED (exit ',text);self.assertNotIn('SUCCESS',text)
                self.assertEqual(text.count('1. Installation'),1)
                self.assertEqual(text.count('BACKUPS'),1)
                self.assertEqual(self.f.path('/etc/x-ui/target-marker').read_text(),'previous target')
                self.assertEqual(json.loads((self.f.root/'services.json').read_text()),before)
                retained=list(self.f.path('/var/backups/x-ui').glob('.rollback-*'))
                self.assertEqual(bool(retained),scenario=='unverified')
                if scenario=='pre-mutation':
                    self.assertFalse(any(c[:2]==['systemctl','stop'] for c in self.f.commands()))
                elif scenario=='verified':self.assertIn('Previous managed state/service states restored and checked',text)
                else:self.assertIn('Automatic rollback could not be verified',text)

    def test_inspect_machine_result_marker_and_historical_roundtrip(self):
        import hashlib,json
        marker=self.f.path('/etc/x-ui/auto-nginx-managed.json')
        marker.write_text('{"format":1,"installed_by":"source@fixture"}\n');marker.chmod(0o600)
        result=self.f.run_tool('backup','--json')
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout);self.assertEqual(value['status'],'success')
        archive=Path(value['archive']);self.assertTrue(archive.is_file())
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        inspect=self.f.run_tool('inspect',archive)
        self.assertEqual(inspect.returncode,0,inspect.stderr)
        self.assertEqual(json.loads(inspect.stdout)['format_version'],3)
        self.assertNotIn('hostname',json.loads(inspect.stdout))
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),digest)
        marker.unlink()
        restore=self.f.run_tool('restore',archive)
        self.assertEqual(restore.returncode,0,restore.stderr)
        self.assertEqual(marker.read_text(),'{"format":1,"installed_by":"source@fixture"}\n')
        self.assertEqual(marker.stat().st_mode&0o777,0o600)

    def test_inspect_untrusted_metadata_and_failure_result_preserves_archive(self):
        import gzip,io,json,tarfile
        archive=self.f.backup();rewritten=archive.with_name('unsafe-display.tar.gz')
        with tarfile.open(archive) as src,tarfile.open(rewritten,'w:gz') as dst:
            for member in src:
                data=src.extractfile(member).read() if member.isfile() else None
                if member.name=='meta.json':
                    meta=json.loads(data);meta['created']='\x1b[31m\nsecret';meta.pop('service_states',None)
                    data=json.dumps(meta).encode();member.size=len(data)
                dst.addfile(member,io.BytesIO(data) if data is not None else None)
        result=self.f.run_tool('inspect',rewritten)
        self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('\x1b',result.stdout)
        self.assertEqual(json.loads(result.stdout)['created'],'\x1b[31m\nsecret')
        # Close the result writer's descriptor only after archive publication.
        before=set(self.f.path('/var/backups/x-ui').glob('*.tar.gz'))
        script="source \"$1\"; python3() { if [[ $# == 2 && $2 == *.tar.gz ]]; then command python3 -c 'import os,sys; os.close(1); exec(sys.stdin.read())' \"${@:2}\"; else command python3 \"$@\"; fi; }; main backup --json"
        result=subprocess.run(['bash','-c',script,'fixture',str(self.f.script)],env=self.f.env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        published=set(self.f.path('/var/backups/x-ui').glob('*.tar.gz'))-before
        self.assertEqual(len(published),1)
        self.assertEqual(self.f.run_tool('inspect',published.pop()).returncode,0)

    def lock_script(self,tail):
        from test_personal_backup import function
        lock=function('acquire_stack_lock').replace('/run/3x-ui-auto-nginx',str(self.f.root)+'/run/3x-ui-auto-nginx')
        return lock+'\n'+tail

    def test_real_concurrent_operation_pairs_and_nested_ownership(self):
        import itertools,signal
        # Every production mutating dispatcher calls the same boundary.
        from test_personal_backup import function
        self.assertIn('acquire_stack_lock',(ROOT/'x-ui-latest.sh').read_text().split('run_installation() (')[1].split('manager_menu()')[0])
        self.assertIn('acquire_stack_lock',(ROOT/'assets/backup/x-ui-backup.sh').read_text().split('main() {')[1])
        def dispatch(operation, hold):
            action=': > "$READYFILE"; read -r done' if hold else 'echo MUTATED'
            if operation in ('backup','restore'):
                return 'source "'+str(self.f.script)+'"; cmd_backup() { '+action+'; }; cmd_restore() { '+action+'; }; main '+operation
            library=(ROOT/'x-ui-latest.sh').read_text()
            library=library[:library.rindex('if [[ ${BASH_SOURCE[0]}')]
            library=library.replace('/run/3x-ui-auto-nginx',str(self.f.root)+'/run/3x-ui-auto-nginx')
            copy=self.f.root/'installer.sh';copy.write_text(library)
            return 'source \"'+str(copy)+'\"; check_os() { :; }; check_cpu() { :; }; initialize_installation() { :; }; ip() { echo \"src 127.0.0.1\"; }; confirm_destructive_reinstall() { :; }; main() { '+action+'; }; uninstall_xui() { '+action+'; }; run_installation '+('-uninstall y' if operation=='uninstall' else '-install y')
        for first,second in itertools.product(('backup','restore','install','uninstall'),repeat=2):
            with self.subTest(first=first,second=second):
                ready=self.f.root/'ready';ready.unlink(missing_ok=True)
                holder=subprocess.Popen(['bash','-c',dispatch(first,True),'fixture',str(ready)],
                                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'READYFILE':str(ready)})
                try:
                    deadline=time.monotonic()+3
                    while not ready.exists() and holder.poll() is None and time.monotonic()<deadline:time.sleep(.01)
                    self.assertTrue(ready.exists())
                    other=subprocess.run(['bash','-c',dispatch(second,False)],capture_output=True,text=True)
                    self.assertEqual(other.returncode,75,other.stderr);self.assertNotIn('MUTATED',other.stdout)
                finally:holder.communicate('\n',timeout=5)
        # Real nested helper inherits fd 9; an independent open description cannot fake it.
        result=subprocess.run(['bash','-c',self.lock_script('acquire_stack_lock || exit $?; bash "$1" lock-check; exit $?'),
                               'fixture',str(self.f.script)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        # An environment flag never bypasses contention; no such input exists.
        result=subprocess.run(['bash','-c',self.lock_script('acquire_stack_lock || exit $?; bash "$1" lock-check 9>&-; exit $?'),
                               'fixture',str(self.f.script)],capture_output=True,text=True,env={**os.environ,'XUI_SKIP_LOCK':'1'})
        self.assertEqual(result.returncode,75,result.stderr)

    def test_lock_lasts_through_child_failure_and_is_released_by_kernel(self):
        ready=self.f.root/'ready'
        child=self.f.root/'child'
        child.write_text(self.lock_script('acquire_stack_lock || exit $?; : > "$1"; read -r done; exit 42'))
        proc=subprocess.Popen(['bash','-c',self.lock_script('acquire_stack_lock || exit $?; bash "$1" "$2"; exit $?'),
                               'fixture',str(child),str(ready)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline=time.monotonic()+3
        while not ready.exists() and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(ready.exists());proc.terminate();proc.wait(timeout=3)
        blocked=self.f.run_tool('lock-check');self.assertEqual(blocked.returncode,75,blocked.stderr)
        proc.stdin.write('\n');proc.stdin.flush();proc.stdin.close()
        # Wait for the inherited writer to finish without arbitrary readiness sleep.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=self.f.run_tool('lock-check')
            if result.returncode==0:break
        self.assertEqual(result.returncode,0,result.stderr)
        proc.stdout.close();proc.stderr.close()

    def test_managed_state_actual_roles_partial_features_and_atomic_failure(self):
        import json,sqlite3
        from test_personal_backup import function
        from test_personal_xhttp import inbounds
        dbpath=self.f.path('/etc/x-ui/x-ui.db')
        with sqlite3.connect(dbpath) as db:
            db.execute('DROP TABLE inbounds');db.execute('DROP TABLE hosts')
            db.execute('CREATE TABLE inbounds(id INTEGER PRIMARY KEY,protocol,listen,port,stream_settings,share_addr_strategy,share_addr)')
            db.execute('CREATE TABLE hosts(inbound_id,address,port)')
            for key,name in (('webCertFile','fullchain.pem'),('webKeyFile','privkey.pem'),('subCertFile','fullchain.pem'),('subKeyFile','privkey.pem')):
                db.execute('UPDATE settings SET value=? WHERE key=?',('/root/cert/example.com/'+name,key))
            for iid,(role,row) in enumerate(inbounds(domain='example.com',reality_domain='reality.example.com').items(),20):
                db.execute('INSERT INTO inbounds VALUES(?,?,?,?,?,?,?)',(iid,row['protocol'],row['listen'],int(row['port']),row['stream_settings'],'',''))
                db.execute('INSERT INTO hosts VALUES(?,?,443)',(iid,'example.com'))
        code='CORE_RESULT=configured; PROJECT_SOURCE_SHA='+('a'*40)+'; domain=example.com; reality_domain=reality.example.com; XUIDB="$1"; VISION_RESULT=failed_rolled_back; AWG_RESULT=not_requested; AGH_RESULT=failed_unverified;\n'+function('write_managed_state')+'\nwrite_managed_state'
        result=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        marker=dbpath.parent/'auto-nginx-managed.json';old=marker.read_bytes();state=json.loads(old)
        self.assertEqual(set(state['inbound_roles']),{'reality','ws','grpc','xhttp','hysteria2'})
        self.assertTrue(all(i>=20 for i in state['inbound_roles'].values()))
        self.assertFalse(any(state['features'].values()));self.assertIsNone(state['domains']['vision'])
        self.assertEqual(marker.stat().st_mode&0o777,0o600)
        # Official 3x-ui normalizes native AWG stream_settings to the empty string.
        with sqlite3.connect(dbpath) as db:
            db.execute('INSERT INTO inbounds VALUES(?,?,?,?,?,?,?)',(777,'amneziawg','0.0.0.0',8443,'','custom','example.com'))
        native=subprocess.run(['bash','-c',code.replace('AWG_RESULT=not_requested','AWG_RESULT=configured'),'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(native.returncode,0,native.stderr)
        native_state=json.loads(marker.read_bytes())
        self.assertTrue(native_state['features']['amneziawg']);self.assertEqual(native_state['inbound_roles']['amneziawg'],777)
        restored=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(restored.returncode,0,restored.stderr)
        self.assertEqual(marker.read_bytes(),old)
        with sqlite3.connect(dbpath) as db:
            db.execute('ALTER TABLE inbounds DROP COLUMN share_addr_strategy')
            db.execute('ALTER TABLE inbounds DROP COLUMN share_addr')
        legacy=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertEqual(legacy.returncode,0,legacy.stderr)
        self.assertEqual(marker.read_bytes(),old)
        fault="python3() { command python3 -c 'import os,sys; os.replace=lambda *a: (_ for _ in ()).throw(OSError(5,\"fixture\")); exec(sys.stdin.read())' \"${@:2}\"; };\n"
        result=subprocess.run(['bash','-c',fault+code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(marker.read_bytes(),old)
        self.assertFalse(list(marker.parent.glob('.managed-*')))
        with sqlite3.connect(dbpath) as db:db.execute("UPDATE hosts SET address='other.example' WHERE inbound_id=?",(state['inbound_roles']['ws'],))
        result=subprocess.run(['bash','-c',code,'fixture',str(dbpath)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(marker.read_bytes(),old)

    def test_legacy_helper_upgrade_offline_reuse_download_and_replace_failure(self):
        from test_personal_backup import function, relocated
        # Keep the real /proc view in the common lock routine.
        lock=self.lock_script('acquire_stack_lock || exit $?')
        helpers='\n'.join(relocated(function(n),self.f.root) for n in
                         ('backup_helper_path_safe','backup_helper_compatible','install_backup_tool','prepare_backup_helper'))
        old=self.f.path('/usr/local/bin/x-ui-backup');old.parent.mkdir(parents=True,exist_ok=True)
        old.write_text('#!/bin/bash\nexit 0\n');old.chmod(0o755);original=old.read_bytes()
        # Candidate is the actual relocated utility, not a mocked capability string.
        candidate=self.f.script
        setup='msg_err() { echo "$*" >&2; }; pin_project_source() { GITHUB_RAW=https://source.invalid/exact; };\n'
        def invoke(extra):
            return subprocess.run(['bash','-c',lock+'\n'+helpers+'\n'+setup+extra+'\nprepare_backup_helper'],capture_output=True,text=True)
        failed=invoke('curl() { return 22; };')
        self.assertNotEqual(failed.returncode,0);self.assertEqual(old.read_bytes(),original)
        download='curl() { command cp "'+str(candidate)+'" "${@: -1}"; };'
        failed=invoke(download+'\nmv() { return 1; };')
        self.assertNotEqual(failed.returncode,0);self.assertEqual(old.read_bytes(),original)
        result=invoke(download)
        self.assertEqual(result.returncode,0,result.stderr)
        result=invoke('curl() { echo UNEXPECTED_DOWNLOAD >&2; return 22; }; pin_project_source() { return 9; };')
        self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('UNEXPECTED_DOWNLOAD',result.stderr)

    def test_legacy_running_peer_and_unsafe_lock_target(self):
        script=self.f.root/'x-ui-backup';ready=self.f.root/'ready'
        script.write_text(': > "$2"; read -r done\n')
        peer=subprocess.Popen(['bash',str(script),'backup',str(ready)],stdin=subprocess.PIPE)
        try:
            deadline=time.monotonic()+3
            while not ready.exists() and time.monotonic()<deadline:time.sleep(.01)
            result=self.f.run_tool('lock-check');self.assertEqual(result.returncode,75,result.stderr)
        finally:peer.communicate(b'\n',timeout=3)
        path=self.f.root/'run/3x-ui-auto-nginx/operation.lock';path.unlink()
        foreign=self.f.root/'foreign';foreign.write_text('untouched')
        path.symlink_to(foreign)
        result=self.f.run_tool('lock-check');self.assertNotEqual(result.returncode,0)
        self.assertEqual(foreign.read_text(),'untouched');self.assertTrue(path.is_symlink())
