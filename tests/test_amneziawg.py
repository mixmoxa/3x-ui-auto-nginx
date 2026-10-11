"""Optional AWG installer contracts; no host installation is executed."""
import os
from pathlib import Path
import subprocess
import unittest
from test_personal_xhttp import function, SOURCE

class AmneziaWG(unittest.TestCase):
    def test_opt_in_defaults_and_eof(self):
        for answer, expected in [('', 'n'), ('\n','n'), ('N\n','n'), ('y\n','y'), ('Y\n','y'), ('invalid\nN\n','n')]:
            result = subprocess.run(['bash','-eu','-c', 'msg_inf() { :; }; '+function('select_amneziawg')+'; select_amneziawg; echo RESULT=$INSTALL_AWG'],input=answer,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('RESULT='+expected,result.stdout)
    def test_preflight_precedes_cleanup_and_does_not_create_client(self):
        main=function('main')
        self.assertLess(main.index('preflight_amneziawg'),main.index('cleanup_adguard'))
        self.assertLess(main.index('select_amneziawg'),main.index('select_adguard'))
        self.assertIn('3X-UI AUTO NGINX',SOURCE)
        helper=Path(__file__).resolve().parents[1]/'assets/amneziawg/managed.py'
        self.assertTrue(helper.exists())
        self.assertIn("'settings': {}",helper.read_text())

    def test_port_conflict_is_rejected_without_mutation(self):
        import socket
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as occupied:
            occupied.bind(('127.0.0.1',8443))
            result=subprocess.run(['bash','-eu','-c',function('preflight_amneziawg')+'; PANEL_TAG=v3.9.0; INSTALL_AWG=y; preflight_amneziawg; echo DESTRUCTIVE'],text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('DESTRUCTIVE',result.stdout)
        free=subprocess.run(['bash','-eu','-c','curl() { :; }; '+function('preflight_amneziawg')+'; PANEL_STAGE=/unused-fixture; GITHUB_RAW=https://example.invalid/ref; PANEL_TAG=v3.9.0; INSTALL_AWG=y; preflight_amneziawg'],capture_output=True)
        self.assertEqual(free.returncode,0,free.stderr)
        result=subprocess.run(['bash','-eu','-c',function('preflight_amneziawg')+'; INSTALL_AWG=n; preflight_amneziawg'],capture_output=True)
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
        script='\n'.join(function(n) for n in ('preflight_amneziawg','install_amneziawg','release_panel_preflight'))
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
