"""Optional AWG installer contracts; no host installation is executed."""
import os
from pathlib import Path
import subprocess
import unittest
from test_personal_xhttp import function, SOURCE

class AmneziaWG(unittest.TestCase):
    def test_adguard_cleanup_failure_recovers_only_early_stopped_xui(self):
        import tempfile
        names=('confirm_destructive_reinstall','validate_domains','select_security','select_vision','select_amneziawg',
               'select_adguard','select_client','preflight_base_os','preflight_panel_release','make_port','preflight_amneziawg',
               'preflight_integrated_features','prepare_base_os','prepare_system_dns','install_packages','setup_firewall',
               'get_server_ip','setup_acme_http','get_ssl_certs','install_panel','configure_nginx','configure_xui_db',
               'install_clash_sub','install_fake_site','install_diagnostics','tune_system','install_backup_tool',
               'setup_certificate_renewal','check_installation','install_amneziawg','finish_initial_reboot','write_managed_state')
        stubs='\n'.join(name+'() { :; }' for name in names)
        stubs+='''
msg_err() { echo "$*" >&2; }
msg_warn() { echo "$*" >&2; }
check_awg_reinstall_owner() { echo owner >> "$CALLS"; }
awg_port_available() { echo port-free >> "$CALLS"; }
systemctl() {
    echo "systemctl $*" >> "$CALLS"
    case "$*" in
        'stop x-ui') echo stopped > "$STATE";;
        'start x-ui')
            [[ "$FAULT" != start-failed ]] || return 1
            [[ "$FAULT" == inactive ]] || echo active > "$STATE";;
        'is-active --quiet x-ui') [[ "$(cat "$STATE")" == active ]];;
        'is-enabled --quiet x-ui') return 0;;
        *) return 1;;
    esac
}
cleanup_adguard() { echo cleanup_adguard >> "$CALLS"; [[ "$FAULT" == success ]]; }
clean_previous_install() { echo clean_previous_install >> "$CALLS"; }
x-ui() { echo "x-ui $*" >> "$CALLS"; }
show_results() { echo INSTALLATION_SUCCESS; }
'''
        for fault, awg, reinstall in (('restored','y','y'),('start-failed','y','y'),('inactive','y','y'),
                                       ('declined','n','n'),('not-stopped','y','n'),('success','y','y')):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); root.chmod(0o700)
                config=root/'x-ui.db'; unit=root/'x-ui.service'
                config.write_bytes(b'private previous configuration'); unit.write_bytes(b'previous unit')
                state=root/'state'; state.write_text('active\n'); calls=root/'calls'
                result=subprocess.run(['bash','-eu','-c',stubs+'\n'+function('prepare_awg_reinstall')+'\n'+function('main')+'\nmain'],
                    env={**os.environ,'CALLS':str(calls),'STATE':str(state),'FAULT':fault,'INSTALL_AWG':awg,
                         'AWG_REINSTALL':reinstall,'INSTALL_SECURITY':'n','INSTALL_VISION':'n','INSTALL_AGH':'n','CREATE_CLIENT':'n'},
                    capture_output=True,text=True,timeout=5)
                actions=calls.read_text().splitlines()
                self.assertEqual(config.read_bytes(),b'private previous configuration')
                self.assertEqual(unit.read_bytes(),b'previous unit')
                self.assertEqual(result.returncode,0 if fault=='success' else 1,result.stderr)
                self.assertEqual('clean_previous_install' in actions,fault=='success')
                self.assertEqual('INSTALLATION_SUCCESS' in result.stdout,fault=='success')
                stopped=reinstall=='y'
                self.assertEqual('systemctl stop x-ui' in actions,stopped)
                self.assertEqual('systemctl start x-ui' in actions,stopped and fault!='success')
                self.assertEqual('systemctl is-active --quiet x-ui' in actions,fault in ('restored','inactive'))
                if stopped:
                    self.assertEqual(actions[:4],['owner','systemctl stop x-ui','port-free','cleanup_adguard'])
                if fault=='restored':
                    self.assertEqual(state.read_text(),'active\n')
                    self.assertIn('previous x-ui is active',result.stderr)
                    self.assertIn('AdGuard Home may require inspection',result.stderr)
                elif fault in ('start-failed','inactive'):
                    self.assertEqual(state.read_text(),'stopped\n')
                    self.assertIn('sudo systemctl start x-ui',result.stderr)
                elif fault in ('declined','not-stopped'):
                    self.assertEqual(state.read_text(),'active\n')
                else:
                    self.assertEqual(actions[4:6],['clean_previous_install','systemctl is-enabled --quiet x-ui'])

    def test_owned_awg_reinstall_and_foreign_or_uncertain_listener_refusal(self):
        import shutil, signal, sqlite3, sys, tempfile, time
        for fault in ('owned','foreign','unknown','database','stuck','stuck_ipv6'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); managed=root/'usr/local/x-ui'; (managed/'bin').mkdir(parents=True)
                panel=managed/'x-ui'; xray=managed/'bin/xray-linux-amd64'
                for executable in (panel,xray): shutil.copy2(sys.executable,executable)
                unit=root/'etc/systemd/system/x-ui.service'; unit.parent.mkdir(parents=True); unit.write_text('[Service]\nExecStart='+str(panel)+'\n')
                ready=root/'ready'; child_code='import socket,time,pathlib; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("0.0.0.0",8443)); pathlib.Path('+repr(str(ready))+').touch(); time.sleep(60)'
                child=str(Path(sys.executable).resolve()) if fault=='foreign' else str(xray)
                parent_code='import subprocess,time,pathlib; p=subprocess.Popen('+repr([child,'-c',child_code])+'); pathlib.Path('+repr(str(root/'child-pid'))+').write_text(str(p.pid)); time.sleep(60)'
                process=subprocess.Popen([str(panel),'-c',parent_code],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                try:
                    deadline=time.monotonic()+5
                    while not ready.exists() and time.monotonic()<deadline: time.sleep(.02)
                    self.assertTrue(ready.exists(),'Private UDP listener not ready')
                    dbfile=root/'x-ui.db'
                    with sqlite3.connect(dbfile) as db:
                        db.execute('CREATE TABLE inbounds(protocol,listen,port,tag,enable)')
                        db.execute('INSERT INTO inbounds VALUES(?,?,?,?,?)',('amneziawg','0.0.0.0',8443,'inbound-8443-udp',0 if fault=='database' else 1))
                    commands=root/'commands'; bindir=root/'tools'; bindir.mkdir()
                    controller=bindir/'systemctl'
                    controller.write_text('#!'+sys.executable+'\n'+'''import os,pathlib,signal,subprocess,sys,time
r=pathlib.Path(os.environ['REINSTALL_ROOT']); args=sys.argv[1:]
with open(r/'commands','a') as out: out.write(' '.join(args)+'\\n')
if args==['show','x-ui','-p','MainPID','--value']: print(os.environ['PANEL_PID'])
elif args==['is-active','--quiet','x-ui']: pass
elif args==['stop','x-ui']:
    os.killpg(int(os.environ['PANEL_PID']),signal.SIGTERM)
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        probe=__import__('socket').socket(__import__('socket').AF_INET,__import__('socket').SOCK_DGRAM)
        try: probe.bind(('0.0.0.0',8443)); break
        except OSError: time.sleep(.02)
        finally: probe.close()
    if os.environ['FAULT'] in ('stuck','stuck_ipv6'):
        code='import socket,time,pathlib; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("0.0.0.0",8443)); pathlib.Path('+repr(str(r/'hog-ready'))+').touch(); time.sleep(60)'
        if os.environ['FAULT']=='stuck_ipv6': code=code.replace('socket.AF_INET,','socket.AF_INET6,').replace('0.0.0.0','::')
        p=subprocess.Popen([sys.executable,'-c',code],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (r/'hog-pid').write_text(str(p.pid))
        deadline=time.monotonic()+3
        while not (r/'hog-ready').exists() and time.monotonic()<deadline: time.sleep(.02)
elif args==['start','x-ui']: sys.exit(1)
else: sys.exit(1)
'''); controller.chmod(0o755)
                    ss=bindir/'ss'; ss.write_text('#!'+sys.executable+'\nimport os,re,subprocess,sys\ns=subprocess.check_output('+repr([shutil.which('ss')])+'+sys.argv[1:],text=True)\nprint(re.sub(r"pid=\\d+","owner=unknown",s) if os.environ["FAULT"]=="unknown" else s)\n'); ss.chmod(0o755)
                    names=('awg_port_available','check_awg_reinstall_owner','prepare_awg_reinstall','preflight_amneziawg')
                    body='\n'.join(function(n) for n in names if n+'() {' in SOURCE).replace('/usr/local/x-ui',str(managed)).replace('/etc/systemd/system/x-ui.service',str(unit))
                    script='msg_err() { echo "$*" >&2; }; msg_warn() { echo "$*" >&2; }; curl() { :; };\n'+body+'\npreflight_amneziawg || exit 1; '+('prepare_awg_reinstall || exit 1; ' if fault in ('owned','stuck','stuck_ipv6') and 'prepare_awg_reinstall() {' in SOURCE else '')+'echo DESTRUCTIVE'
                    result=subprocess.run(['bash','-eu','-c',script],env={**os.environ,'PATH':str(bindir)+':'+os.environ['PATH'],'PANEL_PID':str(process.pid),'REINSTALL_ROOT':str(root),'FAULT':fault,'XUIDB':str(dbfile),'PANEL_STAGE':str(root),'PANEL_TAG':'v3.9.0','INSTALL_AWG':'y','GITHUB_RAW':'https://example.invalid/ref'},capture_output=True,text=True,timeout=15)
                    self.assertEqual(result.returncode==0,fault=='owned',result.stderr)
                    self.assertEqual('DESTRUCTIVE' in result.stdout,fault=='owned')
                    self.assertTrue(dbfile.exists()); self.assertTrue(unit.exists())
                    calls=commands.read_text() if commands.exists() else ''
                    self.assertEqual('stop x-ui' in calls,fault in ('owned','stuck','stuck_ipv6'))
                finally:
                    for pid in [process.pid]+([int((root/'hog-pid').read_text())] if (root/'hog-pid').exists() else []):
                        try: os.killpg(pid,signal.SIGTERM)
                        except ProcessLookupError: pass
                    process.wait(timeout=5)

    def test_opt_in_defaults_and_eof(self):
        for answer, expected in [('', 'n'), ('\n','n'), ('N\n','n'), ('y\n','y'), ('Y\n','y'), ('invalid\nN\n','n')]:
            result = subprocess.run(['bash','-eu','-c', 'msg_inf() { :; }; '+function('select_amneziawg')+'; select_amneziawg; echo RESULT=$INSTALL_AWG'],input=answer,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('RESULT='+expected,result.stdout)
    def test_preflight_precedes_cleanup_and_does_not_create_client(self):
        main=function('main')
        self.assertLess(main.index('preflight_amneziawg'),main.index('prepare_awg_reinstall'))
        self.assertLess(main.index('prepare_awg_reinstall'),main.index('cleanup_adguard'))
        self.assertLess(main.index('select_amneziawg'),main.index('select_adguard'))
        self.assertIn('3X-UI AUTO NGINX',SOURCE)
        helper=Path(__file__).resolve().parents[1]/'assets/amneziawg/managed.py'
        self.assertTrue(helper.exists())
        self.assertIn("'settings': {}",helper.read_text())

    def test_port_conflict_is_rejected_without_mutation(self):
        import socket
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as occupied:
            occupied.bind(('127.0.0.1',8443))
            result=subprocess.run(['bash','-eu','-c','\n'.join(function(n) for n in ('awg_port_available','check_awg_reinstall_owner','preflight_amneziawg'))+'; PANEL_TAG=v3.9.0; INSTALL_AWG=y; preflight_amneziawg; echo DESTRUCTIVE'],text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('DESTRUCTIVE',result.stdout)
        free=subprocess.run(['bash','-eu','-c','curl() { :; }; '+'\n'.join(function(n) for n in ('awg_port_available','check_awg_reinstall_owner','preflight_amneziawg'))+'; PANEL_STAGE=/unused-fixture; GITHUB_RAW=https://example.invalid/ref; PANEL_TAG=v3.9.0; INSTALL_AWG=y; preflight_amneziawg'],capture_output=True)
        self.assertEqual(free.returncode,0,free.stderr)
        result=subprocess.run(['bash','-eu','-c','\n'.join(function(n) for n in ('awg_port_available','check_awg_reinstall_owner','preflight_amneziawg'))+'; INSTALL_AWG=n; preflight_amneziawg'],capture_output=True)
        self.assertEqual(result.returncode,0)

    def test_native_validation_failure_removes_created_record(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('awg',Path(__file__).resolve().parents[1]/'assets/amneziawg/managed.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        panel=object.__new__(module.Panel)
        with patch.object(panel,'request',side_effect=[{'obj':{'id':42,'protocol':'invalid'}},{'success':True}]) as request:
            with self.assertRaises(ValueError):panel.create('panel.example.com')
            self.assertEqual(request.call_args.args,('panel/api/inbounds/del/42',{}))
            body=request.call_args_list[0].args[1]
            self.assertEqual((body['port'],body['tag'],body['settings']),(8443,'inbound-8443-udp',{}))
        with patch.object(panel,'create',return_value={'id':42}), patch.object(panel,'request') as request, patch.object(module.subprocess,'run') as run:
            run.side_effect=subprocess.CalledProcessError(1,['ufw'])
            with self.assertRaises(ValueError):module.configure(panel,'panel.example.com')
            request.assert_called_once_with('panel/api/inbounds/del/42',{})
            self.assertEqual(run.call_args.args[0],['ufw','allow','8443/udp'])
            self.assertEqual(run.call_count,1)

    def test_decline_does_not_configure_or_show_warning(self):
        main=function('main')
        self.assertIn('if [[ "${INSTALL_AWG:-n}" == y ]]',main)
        self.assertNotIn('8443/udp',function('setup_firewall'))
        summary=function('show_results')
        self.assertIn('Configured (UDP/8443)',summary)
        self.assertNotIn('AmneziaWG              Running',summary)

    def test_failed_firewall_allow_preserves_administrator_rules(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('awg',Path(__file__).resolve().parents[1]/'assets/amneziawg/managed.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        panel=object.__new__(module.Panel)
        for existing in ('ufw allow proto udp from any to any port 8443',
                         "ufw allow 8443/udp comment 'administrator VPN'", ''):
            with self.subTest(existing=existing):
                rules=[existing] if existing else []
                def command(argv, **kwargs):
                    if argv[1:]==['show','added']:
                        return subprocess.CompletedProcess(argv,0,stdout='\n'.join(rules))
                    if argv[1:]==['allow','8443/udp']:
                        raise subprocess.CalledProcessError(1,argv)
                    if 'delete' in argv:
                        rules.clear()
                        return subprocess.CompletedProcess(argv,0)
                    self.fail('Unexpected firewall command')
                with patch.object(panel,'create',return_value={'id':42}), patch.object(panel,'request') as request, patch.object(module.subprocess,'run',side_effect=command) as run:
                    with self.assertRaises(ValueError):module.configure(panel,'panel.example.com')
                    request.assert_called_once_with('panel/api/inbounds/del/42',{})
                    self.assertEqual(rules,[existing] if existing else [])
                    self.assertFalse(any('delete' in call.args[0] for call in run.call_args_list))

    def test_summary_describes_configuration_without_claiming_listener(self):
        helpers='\n'.join(function(n) if n == 'show_results' else '' for n in ('show_results',))
        messages='msg_ok() { printf "\\033[32m%s\\033[0m\\n" "$*"; }; msg_warn() { printf "\\033[33m%s\\033[0m\\n" "$*"; }; msg_inf() { echo "$*"; }; ufw() { echo "Status: active"; };'
        for state in ('configured','failed','not_requested'):
            result=subprocess.run(['bash','-c',messages+helpers+'; show_results'],text=True,capture_output=True,
                env={**os.environ,'AWG_RESULT':state,'domain':'panel.example.com','reality_domain':'reality.example.com',
                     'panel_path':'fixture','config_username':'user','config_password':'password'})
            self.assertEqual(result.returncode,0,result.stderr)
            lines=[line for line in result.stdout.splitlines() if 'AmneziaWG' in line]
            if state == 'not_requested':self.assertEqual(lines,[])
            elif state == 'configured':
                self.assertIn('Configured (UDP/8443)',lines[0]);self.assertIn('\x1b[32m',lines[0])
            else:
                self.assertIn('Not configured',lines[0]);self.assertIn('\x1b[33m',lines[0])
            self.assertIn('Password: password',result.stdout)

    def test_api_credentials_use_stdin_and_private_temporary_state(self):
        import importlib.util
        import io
        import json
        import tempfile
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('awg',Path(__file__).resolve().parents[1]/'assets/amneziawg/managed.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            replies=[{'success':True,'obj':'csrf'}, {'success':True}, {'success':True,'obj':'csrf'}]
            with patch.object(module.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,stdout=json.dumps(r).encode()) for r in replies]) as run:
                module.Panel('https://panel.example.com/path/','admin','unique-private-password',directory)
                for call in run.call_args_list:
                    self.assertNotIn('unique-private-password',' '.join(call.args[0]))
                    self.assertEqual(call.args[0][:2],['curl','-q'])
                self.assertIn(b'unique-private-password',run.call_args_list[1].kwargs['input'])
                self.assertEqual((Path(directory)/'cookies').stat().st_mode & 0o777,0o600)
        self.assertFalse(Path(directory).exists())
        directories=[]
        def fail(*args):
            directories.append(args[3]);raise ValueError('fixture login failed')
        with patch.object(module,'Panel',side_effect=fail),patch.object(module.sys,'argv',['managed.py','panel.example.com','path','admin']),patch.object(module.sys,'stdin',io.StringIO('unique-private-password')):
            with self.assertRaises(ValueError):module.main()
        self.assertTrue(directories)
        self.assertFalse(Path(directories[0]).exists())

    def test_canary_identity_includes_exercised_awg_helper(self):
        import tempfile
        from unittest.mock import patch
        import upstream_canary
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            paths=('tests/test_fixture.py','x-ui-latest.sh','assets/clash/clash.yaml',
                   'assets/diagnostics/mtr-backend.py','.github/workflows/upstream-canary.yml',
                   'assets/amneziawg/managed.py','assets/vision/managed.py','assets/client/managed.py')
            for name in paths:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            with patch.object(upstream_canary,'ROOT',root):
                original=upstream_canary.fingerprint()
                (root/'assets/amneziawg/managed.py').write_text('changed AWG contract')
                self.assertNotEqual(original,upstream_canary.fingerprint())

    def test_helper_download_precedes_cleanup_and_is_reused(self):
        import tempfile
        script='\n'.join(function(n) for n in ('awg_port_available','check_awg_reinstall_owner','preflight_amneziawg','install_amneziawg','release_panel_preflight'))
        with tempfile.TemporaryDirectory() as directory:
            for failed in ('0','1'):
                with self.subTest(download_failed=failed):
                    stage=Path(directory)/failed;stage.mkdir()
                    result=subprocess.run(['bash','-eu','-c',script+'''
trap release_panel_preflight EXIT
curl() {
    printf '%s\\n' "$*" >> "$LOG"
    [[ "$FAILED" == 0 ]] || return 22
    printf 'print(42)\\n' > "${@: -1}"
}
preflight_amneziawg || exit 1
printf 'CLEANUP\\n' >> "$LOG"
curl() { echo UNEXPECTED_DOWNLOAD >&2; return 1; }
install_amneziawg
echo "$AWG_RESULT"
'''],capture_output=True,text=True,env={**os.environ,'PANEL_STAGE':str(stage),
                        'GITHUB_RAW':'https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/'+'a'*40,
                        'PANEL_TAG':'v3.9.0','INSTALL_AWG':'y','FAILED':failed,'LOG':str(Path(directory)/(failed+'.log')),
                        'config_password':'fixture-secret','config_username':'user','domain':'panel.example.com','panel_path':'fixture'})
                    log=(Path(directory)/(failed+'.log')).read_text()
                    self.assertIn('/'+'a'*40+'/assets/amneziawg/managed.py',log)
                    self.assertFalse(stage.exists())
                    if failed=='1':
                        self.assertNotEqual(result.returncode,0)
                        self.assertNotIn('CLEANUP',log)
                    else:
                        self.assertEqual(result.returncode,0,result.stderr)
                        self.assertIn('configured',result.stdout)
                        self.assertEqual(len(log.splitlines()),2)
                        self.assertEqual(log.splitlines()[-1],'CLEANUP')
