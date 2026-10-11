"""v2 optional features: isolated preflight, protocol validation and failure ownership."""
import importlib.util
import json
import os
import select
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_personal_xhttp import ROOT, function


def helper(name):
    spec = importlib.util.spec_from_file_location('v2_' + name, ROOT / 'assets' / name / 'managed.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class IntegratedFeatures(unittest.TestCase):
    def test_apt_progress_is_live_and_preserves_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            release=Path(directory)/'release'
            script='apt-get() { echo package-output-fixture; while [[ ! -e "$RELEASE" ]]; do sleep .05; done; return 100; };\n'
            script+=function('apt_system')+'\napt_system -y dist-upgrade'
            process=subprocess.Popen(['bash','-eu','-c',script],env={**os.environ,'RELEASE':str(release)},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                ready=select.select([process.stdout],[],[],2)[0]
                early=process.stdout.readline() if ready else ''
                running=process.poll() is None
            finally:
                release.touch()
                _,errors=process.communicate(timeout=5)
            self.assertIn('APT: working',early,'No progress before the APT command finished')
            self.assertNotIn('package-output-fixture',early,'Raw package output must stay private until completion')
            self.assertTrue(running)
            self.assertEqual(process.returncode,100,errors)
            self.assertIn('package-output-fixture',errors)
            broken_capture='apt-get() { echo package-output-fixture; }; tee() { cat >/dev/null; return 73; };\n'
            result=subprocess.run(['bash','-eu','-c',broken_capture+function('apt_system')+'\napt_system -y dist-upgrade'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1,'An output-capture error must not become successful APT')
            self.assertNotIn('package-output-fixture',result.stdout)

    def test_minimal_image_security_preflight_and_dns_rollback(self):
        security=helper('security')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'etc').mkdir()
            (root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="26.04"\n')
            resolv=root/'etc/resolv.conf'; original='nameserver 8.8.4.4\nnameserver 8.8.8.8\nnameserver 2001:4860:4860::8844\nnameserver 2001:4860:4860::8888\n'; resolv.write_text(original)
            global_policy=root/'etc/systemd/resolved.conf'; global_policy.parent.mkdir(parents=True)
            original_policy='[Resolve]\nDNS=8.8.4.4 8.8.8.8 2001:4860:4860::8844 2001:4860:4860::8888\n'
            global_policy.write_text(original_policy)
            network=root/'etc/network/interfaces'; network.parent.mkdir(parents=True)
            network.write_text('iface eth0 inet dhcp\n    dns-nameservers 8.8.8.8 2001:4860:4860::8888\n')
            def command(*args,**kwargs):
                if args[0]=='/usr/sbin/sshd': return 'port 22'
                if args[0]=='journalctl': return 'SSH journal'
                if args[:2]==('systemctl','is-active'): return 'active' if args[-1] in ('ssh.service','ssh.socket') else 'inactive'
                if args[:2]==('systemctl','show'): return '[::]:22 (Stream)'
                if args[:2]==('systemctl','is-enabled'): return 'not-found'
                if args[0]=='dpkg-query': return 'rc '
                if args[0]=='getent': return '203.0.113.7 STREAM debian.org'
                return ''
            actual_stat=Path.stat
            def stat(path,*args,**kwargs):
                value=actual_stat(path,*args,**kwargs)
                fields=list(value); fields[4]=0; fields[5]=0; return os.stat_result(fields)
            with patch.object(Path,'stat',stat), patch.object(security.shutil,'which',side_effect=lambda name:name), patch.object(security,'command',side_effect=command):
                self.assertEqual(security.preflight(root)[0],'ubuntu')
                self.assertEqual(resolv.read_text(),original)
                other='nameserver 9.9.9.9\nsearch provider.example\noptions rotate\n'
                resolv.write_text(other)
                self.assertEqual(security.preflight(root)[0],'ubuntu')
                self.assertEqual(resolv.read_text(),other)
                resolv.write_text(original)
                with patch.object(security,'verify_dns',side_effect=ValueError('TLS unavailable')):
                    result=security.prepare_dns(root)
                self.assertEqual(result['status'],'failed_rolled_back',result)
                self.assertTrue(any('strict DoT verification' in w and 'rollback=failed_rolled_back' in w for w in result['warnings']),result)
                self.assertFalse(resolv.is_symlink()); self.assertEqual(resolv.read_text(),original)
                self.assertFalse((root/security.FILES[4].lstrip('/')).exists())
                self.assertEqual(global_policy.read_text(),original_policy)

    def test_new_nightly_update_and_reboot_policy(self):
        security=helper('security')
        for distro in ('ubuntu','debian'):
            config=security.apt_config(distro)
            for setting in ('Automatic-Reboot "true"','Automatic-Reboot-WithUsers "true"','Automatic-Reboot-Time "04:38"'):
                self.assertIn(setting,config)
            self.assertNotIn('#clear',config)
        self.assertIn('02:30:00',security.timer('02:30'))
        self.assertIn('02:50:00',security.timer('02:50'))

    def test_late_security_failure_restores_initial_dns_checkpoint(self):
        import inspect
        security=helper('security')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'etc').mkdir(); (root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="26.04"\n')
            resolv=root/'etc/resolv.conf'; original='nameserver 8.8.4.4\nnameserver 8.8.8.8\nnameserver 2001:4860:4860::8844\nnameserver 2001:4860:4860::8888\n'; resolv.write_text(original)
            global_policy=root/'etc/systemd/resolved.conf'; global_policy.parent.mkdir(parents=True)
            original_policy='[Resolve]\nDNS=8.8.4.4 8.8.8.8 2001:4860:4860::8844 2001:4860:4860::8888\n'
            global_policy.write_text(original_policy)
            checkpoint=root/'checkpoint'; state={'active':False,'enabled':'not-found','installed':False}
            def command(*args,**kwargs):
                if args[0]=='/usr/sbin/sshd': return 'port 22'
                if args[0]=='journalctl': return 'SSH journal'
                if args[0]=='dpkg-query': return 'ii' if state['installed'] and args[-1]=='systemd-resolved' else 'rc'
                if args[0]=='apt-get' and 'systemd-resolved' in args: state['installed']=True
                if args[:2]==('systemctl','is-active'): return 'active' if args[-1]=='systemd-resolved.service' and state['active'] else 'inactive'
                if args[:2]==('systemctl','is-enabled'): return state['enabled'] if args[-1]=='systemd-resolved.service' else 'not-found'
                if args[0]=='systemctl' and args[-1]=='systemd-resolved.service':
                    if args[1]=='enable': state['enabled']='enabled'
                    if args[1]=='disable': state['enabled']='disabled'
                    if args[1]=='restart': state['active']=True
                    if args[1]=='stop': state['active']=False
                if args[0]=='getent': return '203.0.113.7 STREAM debian.org'
                return ''
            actual_stat=Path.stat
            def stat(path,*a,**kw):
                fields=list(actual_stat(path,*a,**kw)); fields[4]=0; fields[5]=0; return os.stat_result(fields)
            with patch.object(Path,'stat',stat), patch.object(security.shutil,'which',side_effect=lambda name:name), patch.object(security,'command',side_effect=command), patch.object(security,'verify_dns'):
                # Compatibility adapter allows the same regression to expose
                # the real missing rollback on the pre-checkpoint implementation.
                options={'state':checkpoint} if 'state' in inspect.signature(security.prepare_dns).parameters else {}
                self.assertEqual(security.prepare_dns(root,**options)['status'],'configured')
                with patch.object(security,'verify',side_effect=ValueError('late TLS failure')):
                    self.assertTrue(security.configure(root)['status'].startswith('failed'))
                if hasattr(security,'rollback_dns_checkpoint'):
                    metadata=checkpoint/'state.json'; saved_metadata=metadata.read_text()
                    data=json.loads(saved_metadata); data['states']['ssh.service']=['active','enabled']
                    metadata.write_text(json.dumps(data))
                    self.assertEqual(security.rollback_dns_checkpoint(checkpoint,root)['status'],'failed_unverified')
                    self.assertTrue(resolv.is_symlink(),'Invalid checkpoint must not change DNS')
                    metadata.write_text(saved_metadata)
                    policy=root/security.FILES[-1].lstrip('/'); policy.write_text(security.DOT+'# administrator change\n')
                    self.assertEqual(security.rollback_dns_checkpoint(checkpoint,root)['status'],'failed_unverified')
                    self.assertIn('administrator change',policy.read_text())
                    policy.write_text(security.DOT)
                    self.assertEqual(security.rollback_dns_checkpoint(checkpoint,root)['status'],'failed_rolled_back')
                self.assertFalse(resolv.is_symlink(),'Late failure retained the new strict DNS instead of the initial scheme')
                self.assertEqual(resolv.read_text(),original)
                self.assertEqual(global_policy.read_text(),original_policy)
                self.assertFalse((root/security.FILES[-1].lstrip('/')).exists())
                self.assertFalse(state['active']); self.assertTrue(state['installed'],'No claim of package rollback')

    def test_base_preparation_precedes_cleanup_and_reboot_follows_report(self):
        main=function('main')
        self.assertLess(main.index('preflight_base_os'),main.index('prepare_base_os'))
        self.assertLess(main.index('prepare_base_os'),main.index('cleanup_adguard'))
        self.assertLess(main.index('prepare_system_dns'),main.index('cleanup_adguard'))
        self.assertLess(main.index('show_results'),main.index('finish_initial_reboot'))
        preparation=function('prepare_base_os')
        self.assertIn('dist-upgrade',preparation)
        self.assertIn('--no-remove',function('apt_system'))
        self.assertIn('--force-confold',function('apt_system'))
        self.assertIn('DPkg::Lock::Timeout',function('apt_system'))

    def test_preparation_errors_preserve_deployment_and_reboot_is_success_only(self):
        names=('confirm_destructive_reinstall','validate_domains','select_security','select_vision','select_amneziawg',
               'select_adguard','select_client','preflight_base_os','preflight_panel_release','preflight_amneziawg',
               'preflight_integrated_features','prepare_base_os','prepare_system_dns')
        base='\n'.join(n+'() { echo '+n+'; };' for n in names)
        base+='\nmsg_err() { echo "$*" >&2; }; msg_warn() { :; }; cleanup_adguard() { echo CLEANUP; exit 19; };\n'
        for failure in ('preflight_base_os','preflight_integrated_features','prepare_base_os','prepare_system_dns'):
            result=subprocess.run(['bash','-eu','-c',base+function('main')+'\n'+failure+'() { return 1; }; main'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertNotIn('CLEANUP',result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            flag=Path(directory)/'reboot-required'; log=Path(directory)/'calls'
            # Lists-lock errors retry; an ordinary update error fails once.
            apt_mocks='apt-get() { echo "$*" >> "$CALLS"; if [[ ! -f "$STATE" ]]; then touch "$STATE"; echo "$APT_ERROR" >&2; return 100; fi; }; sleep() { :; };\n'
            for message,retries in (('Could not get lock /var/lib/apt/lists/lock',2),('Failed to fetch repository',1)):
                state=Path(directory)/'lock'; state.unlink(missing_ok=True); log.unlink(missing_ok=True)
                result=subprocess.run(['bash','-eu','-c',apt_mocks+function('apt_system')+'\napt_system -o APT::Update::Error-Mode=any update'],env={**os.environ,'CALLS':str(log),'STATE':str(state),'APT_ERROR':message},capture_output=True,text=True)
                self.assertEqual(result.returncode,0 if retries==2 else 100,result.stderr)
                self.assertEqual(len(log.read_text().splitlines()),retries)
            fn=function('finish_initial_reboot').replace('/var/run/reboot-required',str(flag))
            mocks='msg_warn() { echo "$*"; }; msg_err() { echo "$*" >&2; }; shutdown() { echo "$*" >> "$CALLS"; };\n'
            for required,code in ((False,0),(True,1),(True,0)):
                flag.unlink(missing_ok=True); log.unlink(missing_ok=True)
                if required: flag.touch()
                result=subprocess.run(['bash','-eu','-c',mocks+fn+f'\necho REPORT; finish_initial_reboot {code}'],env={**os.environ,'CALLS':str(log)},capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(log.exists(),required and code==0)
                if log.exists():
                    self.assertEqual(log.read_text(),'-r +1\n')
                    self.assertLess(result.stdout.index('REPORT'),result.stdout.index('Scheduling'))
                    self.assertIn('post-reboot acceptance is pending',result.stdout)

    def test_security_readonly_preflight_blocks_cleanup_for_known_conflicts(self):
        from test_personal_backup import relocated
        cases = ('jail', 'jail-conf', 'disabled-apt', 'compatible', 'declined')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root/'etc').mkdir()
                (root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
                resolv = root/'etc/resolv.conf'
                resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')
                if case in ('jail','jail-conf'):
                    jail=root/('etc/fail2ban/jail.local' if case=='jail' else 'etc/fail2ban/jail.d/provider.conf'); jail.parent.mkdir(parents=True)
                    jail.write_text('[sshd]\nmaxretry=2\n')
                stage=root/'stage'; stage.mkdir()
                source=(ROOT/'assets/security/managed.py').read_text()
                # Execute the real helper CLI against private files and read-only
                # command fixtures. No installer/global paths are executed.
                override = "shutil.which = lambda tool: tool\ndef command(*args, **kwargs):\n    if args[0]=='/usr/sbin/sshd': return 'port 22'\n    if args[0]=='journalctl': return 'SSH journal'\n    if args[:2]==('systemctl','is-active'): return %r if args[-1]=='systemd-resolved.service' else 'inactive'\n    if args[:2]==('systemctl','is-enabled'): return 'enabled'\n    return ''\n" % 'active'
                if case=='disabled-apt': override=override.replace("    return ''\n","    if args[0]=='apt-config': return 'APT::Periodic::Enable \"0\";'\n    return ''\n")
                prefix, cli=source.split("if __name__ == '__main__':",1)
                (root/'helper.py').write_text(prefix.replace("root=Path('/')", 'root=Path('+repr(str(root))+')')+override+"if __name__ == '__main__':"+cli)
                names=('confirm_destructive_reinstall','validate_domains','select_vision','select_amneziawg','select_adguard','select_client',
                       'preflight_panel_release','preflight_amneziawg','preflight_vision_artifacts','preflight_base_os','prepare_base_os','prepare_system_dns','finish_initial_reboot')
                stubs='\n'.join(name+'() { :; }' for name in names)
                stubs+='\nselect_security() { INSTALL_SECURITY='+('n' if case=='declined' else 'y')+'; }; msg_err() { echo "$*" >&2; }; msg_warn() { :; };\n'
                stubs+='curl() { cp "$FIXTURE_HELPER" "${@: -1}"; }; cleanup_adguard() { echo CLEANUP; exit 19; }; clean_previous_install() { echo DESTRUCTION; };\n'
                script=stubs+function('preflight_integrated_features')+'\n'+function('main')+'\nINSTALL_VISION=n; CREATE_CLIENT=n; main'
                env={**os.environ,'PANEL_STAGE':str(stage),'GITHUB_RAW':'https://fixture.invalid','FIXTURE_HELPER':str(root/'helper.py')}
                before={str(p.relative_to(root)):os.readlink(p) if p.is_symlink() else p.read_bytes() for p in (root/'etc').rglob('*') if p.is_file() or p.is_symlink()}
                result=subprocess.run(['bash','-eu','-c',script],env=env,capture_output=True,text=True)
                after={str(p.relative_to(root)):os.readlink(p) if p.is_symlink() else p.read_bytes() for p in (root/'etc').rglob('*') if p.is_file() or p.is_symlink()}
                self.assertEqual(before,after)
                if case in ('compatible','declined','disabled-apt'):
                    self.assertEqual(result.returncode,19,result.stderr)
                    self.assertIn('CLEANUP',result.stdout)
                else:
                    self.assertEqual(result.returncode,1,result.stderr)
                    self.assertNotIn('CLEANUP',result.stdout)
                    self.assertNotIn('DESTRUCTION',result.stdout)
                    self.assertIn('preflight',result.stderr.lower())

    def test_selected_security_overrides_disabled_periodic_apt(self):
        security=helper('security')
        self.assertIn('APT::Periodic::Enable "1";',security.apt_config('ubuntu'))
        for key in ('Enable','Update-Package-Lists','Unattended-Upgrade'):
            with self.subTest(key=key):
                self.assertEqual(security.apt_origins('APT::Periodic::'+key+' "0";'),set())
        # A project marker cannot authorize removal of administrator origins
        # appended to the managed file itself.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'etc').mkdir()
            (root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
            (root/'etc/resolv.conf').symlink_to('/run/systemd/resolve/stub-resolv.conf')
            owned=root/security.FILES[1].lstrip('/'); owned.parent.mkdir(parents=True)
            owned.write_text(security.apt_config('ubuntu')+'Unattended-Upgrade::Origins-Pattern { "origin=Provider,label=Provider-Security"; };\n')
            actual_stat=Path.stat
            def stat(path,*args,**kwargs):
                value=actual_stat(path,*args,**kwargs)
                if path==owned:
                    fields=list(value); fields[4]=0; return os.stat_result(fields)
                return value
            def command(*args,**kwargs):
                if args[0]=='/usr/sbin/sshd': return 'port 22'
                if args[0]=='journalctl': return 'SSH journal'
                if args[0]=='apt-config': return 'APT::Periodic::Enable "0";'
                if args[:2]==('systemctl','is-active'): return 'active' if args[-1]=='systemd-resolved.service' else 'inactive'
                if args[:2]==('systemctl','is-enabled'): return 'enabled'
                return ''
            with patch.object(Path,'stat',stat), patch.object(security.shutil,'which',side_effect=lambda name:name), patch.object(security,'command',side_effect=command):
                with self.assertRaisesRegex(ValueError,'APT.*preserved'): security.preflight(root)
                self.assertIn('origin=Provider',owned.read_text())
                current=security.apt_config('ubuntu')
                previous=current.replace('Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-WithUsers "true";\nUnattended-Upgrade::Automatic-Reboot-Time "04:38";', 'Automatic-Reboot "false";')
                legacy=previous.replace('// Add the required distro security origin; retain administrator/distro origins.',
                    '// Reset effective origins in this final managed drop-in; preserve administrator files.\n#clear Unattended-Upgrade::Allowed-Origins;\n#clear Unattended-Upgrade::Origins-Pattern;')
                for canonical in (current,previous,legacy,current.replace('APT::Periodic::Enable "1";\n','')):
                    owned.write_text(canonical); security.preflight(root)
        self.assertEqual(security.apt_origins(''),set())
        self.assertEqual(security.apt_origins('Unattended-Upgrade::Origins-Pattern:: "origin=Provider,label=Provider-Security";'),{('Origins-Pattern','origin=Provider,label=Provider-Security')})

    def test_main_stops_after_mandatory_setup_failure(self):
        names=('confirm_destructive_reinstall','validate_domains','select_security','select_vision','select_amneziawg',
               'select_adguard','select_client','preflight_base_os','preflight_panel_release','preflight_amneziawg',
               'preflight_integrated_features','prepare_base_os','prepare_system_dns','cleanup_adguard','clean_previous_install',
               'install_packages','setup_firewall','get_server_ip','setup_acme_http','get_ssl_certs','install_panel',
               'configure_nginx','configure_xui_db','install_clash_sub','install_fake_site','install_diagnostics','tune_system',
               'install_backup_tool','setup_certificate_renewal','check_installation','show_results','finish_initial_reboot')
        stubs='\n'.join(n+'() { echo '+n+'; };' for n in names)
        stubs+='\nmsg_err() { echo "$*" >&2; }; msg_warn() { :; }; systemctl() { :; }; x-ui() { :; };\n'
        for failed in ('clean_previous_install','get_server_ip','configure_nginx','install_clash_sub','install_fake_site','install_diagnostics','install_backup_tool'):
            with self.subTest(stage=failed):
                script=stubs+function('main')+'\n'+failed+'() { echo FAILURE; return 73; }; main'
                result=subprocess.run(['bash','-u','-c',script],env={**os.environ,'INSTALL_SECURITY':'n','INSTALL_VISION':'n','INSTALL_AWG':'n','INSTALL_AGH':'n','CREATE_CLIENT':'n'},capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0,result.stdout)
                self.assertNotIn('show_results',result.stdout)
                self.assertIn('exit 73',result.stderr)

    def test_required_download_failure_does_not_report_success(self):
        for name in ('install_clash_sub','install_fake_site','install_diagnostics'):
            with self.subTest(stage=name), tempfile.TemporaryDirectory() as directory:
                script=function(name)
                for path in ('/var/www','/usr/local/lib','/etc/systemd/system'):
                    script=script.replace(path,directory+path)
                (Path(directory)/'etc/systemd/system').mkdir(parents=True)
                mocks='curl() { echo download-failed >&2; return 73; }; msg_ok() { echo SUCCESS; }; msg_err() { echo "$*" >&2; }; sed() { :; }; dd() { :; }; chown() { :; }; chmod() { :; }; id() { return 0; }; setcap() { :; }; systemctl() { :; };\n'
                result=subprocess.run(['bash','-u','-c',mocks+script+'\n'+name],env={**os.environ,'GITHUB_RAW':'https://fixture.invalid','FAKE_SITE_COUNT':'1','diag_path':'/diagnostics/','domain':'panel.example','IP4':'203.0.113.7','mtr_backend_port':'10005','panel_path':'panel'},capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0,result.stdout)
                self.assertNotIn('SUCCESS',result.stdout)

    def test_runtime_security_repeats_preflight_before_any_mutation(self):
        security=helper('security')
        with patch.object(security,'preflight',side_effect=ValueError('State changed')), patch.object(security,'command') as command, patch.object(security,'Transaction') as transaction:
            with self.assertRaisesRegex(ValueError,'State changed'): security.configure()
            command.assert_not_called(); transaction.assert_not_called()

    def test_apt_dropin_preserves_effective_admin_and_distro_origins(self):
        security=helper('security')
        defaults={
            'ubuntu24': ('ubuntu','Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}"; "${distro_id}:${distro_codename}-security"; "${distro_id}ESMApps:${distro_codename}-apps-security"; "${distro_id}ESM:${distro_codename}-infra-security"; };'),
            'ubuntu26': ('ubuntu','Unattended-Upgrade::Allowed-Origins { "${distro_id}:${distro_codename}"; "${distro_id}:${distro_codename}-security"; "${distro_id}ESMApps:${distro_codename}-apps-security"; "${distro_id}ESM:${distro_codename}-infra-security"; };'),
            'empty': ('ubuntu',''),
            'debian13': ('debian','Unattended-Upgrade::Origins-Pattern { "origin=Debian,codename=${distro_codename},label=Debian"; "origin=Debian,codename=${distro_codename},label=Debian-Security"; "origin=Debian,codename=${distro_codename}-security,label=Debian-Security"; };')}
        for label,(os_id,stock) in defaults.items():
            with self.subTest(distro=label), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); parts=root/'parts'; parts.mkdir()
                bootstrap=root/'apt.conf'; bootstrap.write_text(f'Dir::Etc::parts "{parts}"; Dir::Etc::main "{root}/absent";')
                admin=parts/'50unattended-upgrades'; admin.write_text(stock+'\nAPT::Periodic::Enable "0";\nAPT::Periodic::Update-Package-Lists "0";\nAPT::Periodic::Unattended-Upgrade "0";\nUnattended-Upgrade::Origins-Pattern { "origin=Provider,label=Provider-Security"; };\n')
                dump=lambda: subprocess.check_output(['apt-config','dump'],env={**os.environ,'APT_CONFIG':str(bootstrap)},text=True)
                before=dump(); self.assertIn('origin=Provider,label=Provider-Security',before); owned=parts/'99zz-3x-ui-auto-nginx'; owned.write_text(security.apt_config(os_id)); after=dump()
                for line in before.splitlines():
                    if 'Unattended-Upgrade::' in line and ':: "' in line:
                        self.assertIn(line,after,'Existing effective origin removed')
                self.assertIn('origin=Provider,label=Provider-Security',after)
                self.assertIn('Unattended-Upgrade::Automatic-Reboot "true";',after)
                for key in ('Enable','Update-Package-Lists','Unattended-Upgrade'):
                    self.assertIn('APT::Periodic::'+key+' "1";',after)
                owned.write_text(security.apt_config(os_id)); self.assertEqual(dump(),after)
                owned.unlink(); self.assertEqual(dump(),before)

    def test_service_dns_fixture_retries_tcp_udp_port_collision(self):
        import socket
        import test_real_services as services
        blocker=socket.socket(); blocker.bind(('127.0.0.1',0)); blocker.listen()
        self.addCleanup(blocker.close)
        constructor=services.socketserver.ThreadingUDPServer; addresses=[]
        def udp(address,handler):
            chosen=blocker.getsockname() if not addresses else address
            result=constructor(chosen,handler); addresses.append(result.server_address)
            return result
        instance=services.RealServices('test_real_project_deploy_hook_and_nginx_reload')
        instance.agh=Path('/bin/true')
        check_output=services.subprocess.check_output
        def output(args,**kwargs):
            return b'admin:fixture-hash' if args[0]=='htpasswd' else check_output(args,**kwargs)
        try:
            with patch.object(services.socketserver,'ThreadingUDPServer',side_effect=udp), patch.object(services.subprocess,'check_output',side_effect=output), patch.object(instance,'shell'):
                instance.setUp()
            self.assertGreater(len(addresses),1)
            self.assertNotEqual(instance.dns.server_address,blocker.getsockname())
        finally:
            instance.doCleanups()

    def test_concise_installer_question_sequence(self):
        names=('validate_domains','select_security','select_vision','select_amneziawg','select_adguard','select_client')
        script='domain=; reality_domain=; msg_err() { echo "$*" >&2; }; msg_inf() { echo "$*"; };\n'
        script+='\n'.join(function(name) for name in names)+'\n'+'; '.join(names)
        result=subprocess.run(['bash','-eu','-c',script],input='panel.example.com\nreality.example.com\ny\ny\nvision.example.com\nn\nn\ny\n',text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'Enter the domain for your 3X-UI panel: Enter the domain for VLESS REALITY: Enhance VPS security? [Y/n]: Set up an additional VLESS Vision connection? (requires a separate domain) [y/N]: Enter the domain for VLESS Vision (must differ from the panel and REALITY domains): Set up an additional AmneziaWG connection? [y/N]: Install and configure AdGuard Home? [y/N]: Create a client in 3X-UI and display a subscription link after installation? [Y/n]: ')

    def test_prompt_defaults_decline_and_eof(self):
        for name, variable, default in (('select_security', 'INSTALL_SECURITY', 'y'),
                                         ('select_client', 'CREATE_CLIENT', 'y'),
                                         ('select_vision', 'INSTALL_VISION', 'n'),
                                         ('select_amneziawg', 'INSTALL_AWG', 'n'),
                                         ('select_adguard', 'INSTALL_AGH', 'n')):
            for answer, expected in (('\n', default), ('n\n', 'n'), ('N\n', 'n'), ('', 'n')):
                result = subprocess.run(['bash', '-eu', '-c', function(name) + f'; {name}; echo RESULT=${variable}'],
                                        input=answer, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('RESULT=' + expected, result.stdout)
                if variable=='INSTALL_VISION' and expected=='n':
                    self.assertNotIn('Enter the domain for VLESS Vision',result.stdout)

    def test_all_choices_and_preflights_before_destruction(self):
        text = function('main')
        for name in ('select_security', 'select_vision', 'select_client', 'select_amneziawg', 'select_adguard', 'preflight_integrated_features'):
            self.assertLess(text.index(name), text.index('cleanup_adguard'))
        self.assertLess(text.index('install_vision'), text.index('install_security'))
        self.assertLess(text.index('install_adguard'), text.index('install_security'))
        self.assertLess(text.index('install_security'), text.index('install_initial_client'))

    def test_ssh_ports_and_password_warning(self):
        security = helper('security')
        self.assertEqual(security.ssh_ports('port 2222\nport 2200\n'), [2200, 2222])
        self.assertEqual(security.ssh_ports('port 22\n', '[::]:2222 (Stream) 0.0.0.0:2200 (Stream)'), [2200, 2222])
        for bad in ('', 'port 0', 'port 99999'):
            with self.assertRaises(ValueError): security.ssh_ports(bad)
        for policy in ('passwordauthentication yes\nauthenticationmethods any',
                       'passwordauthentication no\nkbdinteractiveauthentication yes\nauthenticationmethods publickey,keyboard-interactive:pam'):
            self.assertTrue(security.password_warning(policy))
        self.assertFalse(security.password_warning('passwordauthentication yes\nauthenticationmethods publickey'))

    def test_dns_route_conflicts_preserve_interface_policy(self):
        security = helper('security')
        security.dns_routes('Global: 1.1.1.1#one.one.one.one\nLink 2 (eth0): 8.8.8.8', 'Global: ~.\nLink 2 (eth0):')
        for domains in ('Link 2 (eth0): ~.', 'Link 3 (vpn): ~corp.example', 'Link 2 (eth0): example.com'):
            with self.assertRaises(ValueError): security.dns_routes('', domains)
        with self.assertRaises(ValueError): security.dns_routes('Link 3 (vpn): 127.0.0.1', '')

    def test_security_refuses_unsupported_service_enable_state_without_mutation(self):
        security=helper('security'); calls=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'etc').mkdir()
            resolv=root/'etc/resolv.conf'; resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')
            def command(*args,**kwargs):
                calls.append(args)
                if args[0]=='resolvectl': return ''
                if args[1]=='is-active': return 'active'
                return 'enabled-runtime' if args[-1]=='apt-daily.timer' else 'enabled'
            with patch.object(security,'command',side_effect=command), self.assertRaises(ValueError): security.preflight(root)
            self.assertEqual(os.readlink(resolv),'/run/systemd/resolve/stub-resolv.conf')
            self.assertFalse(any(arg[1] in ('enable','disable','restart') for arg in calls))

    def test_security_snapshot_restores_symlink_file_and_service_states(self):
        security = helper('security')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'etc').mkdir()
            resolv = root / 'etc/resolv.conf'; resolv.symlink_to('/run/systemd/resolve/resolv.conf')
            path = root / security.FILES[0].lstrip('/'); path.parent.mkdir(parents=True); path.write_text(security.MARKER + 'original')
            def command(*args, **kwargs):
                if args[1] == 'is-active': return 'active'
                if args[1] == 'is-enabled': return 'enabled'
                return ''
            with patch.object(security, 'command', side_effect=command):
                txn = security.Transaction(root)
                self.addCleanup(txn.temp.cleanup)
                txn.write(security.FILES[0], security.MARKER + 'new')
                txn.write(security.FILES[4], security.DOT)
                resolv.unlink(); resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')
                txn.rollback()
                self.assertEqual(path.read_text(), security.MARKER + 'original')
                self.assertEqual(os.readlink(resolv), '/run/systemd/resolve/resolv.conf')
                self.assertFalse((root / security.FILES[4].lstrip('/')).exists())

    def test_security_update_origins_and_local_timer_contract(self):
        security = helper('security')
        self.assertIn('archive=${distro_codename}-security', security.apt_config('ubuntu'))
        self.assertIn('label=Debian-Security,codename=${distro_codename}-security', security.apt_config('debian'))
        self.assertIn('Automatic-Reboot "true"', security.apt_config('ubuntu'))
        self.assertIn('OnCalendar=*-*-* 02:30:00', security.timer('02'))
        self.assertNotIn('UTC', security.timer('02'))

    def test_security_waits_for_sshd_jail_after_asynchronous_service_start(self):
        security=helper('security'); attempts=[]; effective='port 22\n'
        dns='Global: 1.1.1.1#one.one.one.one 1.0.0.1#one.one.one.one 8.8.8.8#dns.google 8.8.4.4#dns.google'
        def command(*args,**kwargs):
            if args[0]=='/usr/sbin/sshd': return effective
            if args[:2]==('fail2ban-client','status'):
                attempts.append(1)
                if len(attempts)<3: raise ValueError('Socket not ready')
            if args[:2]==('fail2ban-client','get'): return {'maxretry':'5','findtime':'1800','bantime':'3600'}[args[-1]]
            if args[:2]==('fail2ban-client','-d'): return 'port 22'
            if args[0]=='apt-config': return 'APT::Periodic::Enable "1";\nAPT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\nUnattended-Upgrade::Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-WithUsers "true";\nUnattended-Upgrade::Automatic-Reboot-Time "04:38";\nUnattended-Upgrade::Origins-Pattern:: "origin=Ubuntu,archive=${distro_codename}-security";'
            if args[:2]==('systemctl','show'): return ('02:50' if args[2]=='apt-daily-upgrade.timer' else '02:30')+':00\nRandomizedDelayUSec=0'
            if args[0]=='busctl': return 's "yes"'
            if args[:2]==('resolvectl','dns'): return dns
            return ''
        with patch.object(security,'command',side_effect=command):
            security.verify([22],effective,'ubuntu')
        self.assertEqual(len(attempts),3)

    def test_effective_dot_native_dns_output_wraps_long_server_list(self):
        security = helper('security')
        output = 'Global: 1.1.1.1#one.one.one.one 1.0.0.1#one.one.one.one 8.8.8.8#dns.google\n        8.8.4.4#dns.google\nLink 2 (eth0): 10.0.0.1'
        self.assertEqual(security.global_servers(output), ['1.1.1.1#one.one.one.one','1.0.0.1#one.one.one.one','8.8.8.8#dns.google','8.8.4.4#dns.google'])

    def test_vision_domain_stream_and_plaintext_fallback(self):
        vision = helper('vision')
        for bad in ('panel.example/evil', 'bad_name.example', '-bad.example', 'example', 'a..example'):
            with self.assertRaises(ValueError): vision.domain_name(bad)
        text = 'map $ssl_preread_server_name $sni_name {\n    hostnames;\n    panel.example www;\n    reality.example xray;\n}\n'
        rendered = vision.stream_config(text, 'vision.example', 12000)
        self.assertIn('panel.example www;', rendered); self.assertIn('reality.example xray;', rendered)
        self.assertIn('vision.example vision;', rendered)
        with self.assertRaises(ValueError): vision.stream_config(rendered, 'vision.example', 12000)
        fallback = vision.fallback_config('vision.example', 12001)
        self.assertIn('listen 127.0.0.1:12001 proxy_protocol', fallback)
        self.assertNotIn('proxy_pass', fallback); self.assertNotIn('include', fallback)
        row = vision.inbound('vision.example', 12000, 12001, '/cert.pem', '/key.pem')
        self.assertEqual(row['streamSettings']['network'], 'tcp')
        self.assertTrue(row['streamSettings']['rawSettings']['acceptProxyProtocol'])
        self.assertEqual(row['settings']['fallbacks'][0]['dest'], '127.0.0.1:12001')

    def test_wrong_certificate_rejected(self):
        vision = helper('vision')
        with tempfile.TemporaryDirectory() as directory:
            cert, key = (Path(directory) / name for name in ('cert.pem', 'key.pem'))
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-subj', '/CN=vision.example', '-addext', 'subjectAltName=DNS:vision.example',
                            '-out', cert, '-keyout', key], check=True, capture_output=True)
            vision.certificate('vision.example', cert, key)
            with self.assertRaises(ValueError): vision.certificate('wrong.example', cert, key)
            with self.assertRaises(OSError): vision.certificate('vision.example', cert, Path(directory) / 'absent')

    def test_vision_certificate_uses_utc_validity(self):
        import datetime
        vision=helper('vision')
        with tempfile.TemporaryDirectory() as directory:
            cert,key=[Path(directory)/name for name in ('cert','key')]
            subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1',
                '-nodes','-days','1','-subj','/CN=vision.example','-addext','subjectAltName=DNS:vision.example',
                '-out',cert,'-keyout',key],check=True,capture_output=True)
            leaf=vision.x509.load_pem_x509_certificate(cert.read_bytes())
            now=datetime.datetime.now(datetime.timezone.utc)
            class UTCLeaf:
                extensions=leaf.extensions
                not_valid_before_utc=now-datetime.timedelta(minutes=1)
                not_valid_after_utc=now+datetime.timedelta(minutes=1)
                def public_key(self): return leaf.public_key()
                @property
                def not_valid_before(self): raise AssertionError('Deprecated naive certificate property used')
                @property
                def not_valid_after(self): raise AssertionError('Deprecated naive certificate property used')
            value=UTCLeaf()
            with patch.object(vision.x509,'load_pem_x509_certificate',return_value=value):
                vision.certificate('vision.example',cert,key)
                value.not_valid_after_utc=now-datetime.timedelta(seconds=1)
                with self.assertRaisesRegex(ValueError,'validity'): vision.certificate('vision.example',cert,key)
                value.not_valid_after_utc=now+datetime.timedelta(minutes=2)
                value.not_valid_before_utc=now+datetime.timedelta(minutes=1)
                with self.assertRaisesRegex(ValueError,'validity'): vision.certificate('vision.example',cert,key)

    def test_vision_readiness_is_bounded_and_errors_are_private(self):
        vision=helper('vision')
        with patch.object(vision.socket,'create_connection',side_effect=ConnectionRefusedError), \
             patch.object(vision.time,'monotonic',side_effect=[0,0,10]),patch.object(vision.time,'sleep') as sleep:
            with self.assertRaisesRegex(ValueError,'within 10 seconds'): vision.wait_inbound(12000)
            self.assertEqual(sleep.call_count,1)
        private='private-session-cookie https://panel.example/sub/secret'
        for error in (ValueError(private),subprocess.CalledProcessError(35,['curl',private],private,private),
                      subprocess.TimeoutExpired(['curl',private],40,output=private,stderr=private)):
            with self.subTest(error=type(error).__name__):
                message=str(vision.Failure('failed_unverified','restarting Xray',vision.safe_reason(error),
                                          'restoring nginx: '+vision.safe_reason(error)))
                self.assertNotIn(private,message)
                self.assertIn('restarting Xray',message); self.assertIn('rollback failure:',message)

    def test_vision_early_acme_failure_removes_only_new_artifacts(self):
        from test_personal_backup import relocated
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ('etc/nginx/sites-available','etc/nginx/sites-enabled','etc/letsencrypt/renewal-hooks/deploy'):
                (root/path).mkdir(parents=True)
            source = (ROOT/'x-ui-latest.sh').read_text()
            script = relocated('install_vision() {'+source.split('install_vision() {',1)[1].split('\ninstall_security()',1)[0],root)
            stubs = 'python3() { echo \'# render fixture\'; }; ln() { return 1; }; nginx() { :; }; systemctl() { :; }; check_installation() { :; }; msg_warn() { :; }; make_port() { echo $((RANDOM+10000)); };\n'
            result = subprocess.run(['bash','-eu','-c',stubs+script+'\nPANEL_STAGE=/stage; vision_domain=vision.example; install_vision || :; echo "$VISION_RESULT"'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'failed_rolled_back')
            self.assertFalse((root/'etc/nginx/sites-available/vision-acme.conf').exists())

    def test_vision_unverified_api_rollback_retains_required_certificate(self):
        from test_personal_backup import relocated
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in ('etc/nginx/sites-available','etc/nginx/sites-enabled','etc/letsencrypt/renewal-hooks/deploy','etc/letsencrypt/live/vision.example'):
                (root/path).mkdir(parents=True)
            source=(ROOT/'x-ui-latest.sh').read_text()
            script=relocated('install_vision() {'+source.split('install_vision() {',1)[1].split('\ninstall_security()',1)[0],root)
            stubs='nginx() { :; }; systemctl() { :; }; check_installation() { :; }; check_webroot_lineage() { :; }; msg_warn() { :; }; make_port() { echo $((RANDOM+10000)); }; render_vision_hook() { echo "#!/bin/bash"; }; chown() { :; }; certbot() { echo CERTIFICATE_DELETED; }; python3() { if [[ \"$*\" == *--render-acme* ]]; then echo \'# render fixture\'; return 0; fi; echo \'{"status":"failed_unverified"}\'; return 1; };\n'
            result=subprocess.run(['bash','-eu','-c',stubs+script+'\nVISION_OWNED_LINEAGE=vision.example; vision_domain=vision.example; domain=panel.example; panel_path=test; config_username=test; config_password=test; PANEL_STAGE=/stage; AWG_HELPER=/helper; install_vision || :; echo "$VISION_RESULT"'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue((root/'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision').exists())
            self.assertTrue((root/'etc/nginx/sites-available/vision-acme.conf').exists())
            self.assertNotIn('CERTIFICATE_DELETED',result.stdout)
            # An interrupted helper may have changed the API but emitted no JSON.
            for name in ('etc/nginx/sites-enabled/vision-acme.conf','etc/nginx/sites-available/vision-acme.conf',
                         'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision'):
                (root/name).unlink()
            empty=stubs.replace('echo \'{"status":"failed_unverified"}\';',':;')
            result=subprocess.run(['bash','-eu','-c',empty+script+'\nVISION_OWNED_LINEAGE=vision.example; vision_domain=vision.example; domain=panel.example; panel_path=test; config_username=test; config_password=test; PANEL_STAGE=/stage; AWG_HELPER=/helper; install_vision || :; echo "$VISION_RESULT"'],capture_output=True,text=True)
            self.assertEqual(result.stdout.strip(),'failed_unverified',result.stderr)
            self.assertTrue((root/'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision').exists())
            self.assertNotIn('CERTIFICATE_DELETED',result.stdout)

    def test_vision_fallback_failure_keeps_authenticated_session_for_rollback(self):
        vision=helper('vision'); rows=[]; authenticated=[True]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); stream,site,enabled=[root/name for name in ('stream','site','enabled')]
            original='map $ssl_preread_server_name $sni_name {\n    hostnames;\n}\n'; stream.write_text(original)
            class Panel:
                def request(self,path,data=None):
                    if not authenticated[0]: raise ValueError('Session invalidated by panel restart')
                    if path.endswith('/inbounds/list'): return {'obj':rows}
                    if path.endswith('/inbounds/add'):
                        rows.append({**data,'id':42}); return {'obj':rows[0]}
                    if path.endswith('/inbounds/del/42'): rows.clear()
                    return {'obj':None}
            def run(*args):
                if args==('systemctl','restart','x-ui'): authenticated[0]=False
                if args[0]=='curl': raise subprocess.CalledProcessError(60,args,output=b'private-response',stderr=b'private-cookie')
            with patch.object(vision,'certificate'),patch.object(vision,'wait_inbound'),patch.object(vision,'run',side_effect=run),self.assertRaises(vision.Failure) as failed:
                vision.configure(Panel(),'vision.example',12000,12001,stream,site,enabled,'/cert','/key')
            self.assertEqual(failed.exception.status,'failed_rolled_back')
            self.assertIn('HTTPS fallback',str(failed.exception))
            self.assertIn('certificate verification',str(failed.exception))
            self.assertNotIn('private-response',str(failed.exception)); self.assertNotIn('private-cookie',str(failed.exception))
            self.assertEqual(rows,[]); self.assertEqual(stream.read_text(),original)

    def test_vision_api_uncertainty_and_failure_respect_artifact_ownership(self):
        vision = helper('vision')
        for changed in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory); cert, key = root/'cert.pem', root/'key.pem'
                subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:prime256v1',
                    '-nodes','-days','1','-subj','/CN=vision.example','-addext','subjectAltName=DNS:vision.example',
                    '-out',cert,'-keyout',key],check=True,capture_output=True)
                stream, site, enabled = [root/name for name in ('stream.conf','site.conf','enabled')]
                original = 'map $ssl_preread_server_name $sni_name {\n    hostnames;\n    panel.example www;\n    reality.example xray;\n}\n'
                stream.write_text(original)
                calls, records = [], []
                class Panel:
                    def request(self,path,data=None):
                        calls.append(path)
                        if path.endswith('/inbounds/list'): return {'obj':records}
                        if path.endswith('/inbounds/add'):
                            records.append({**data,'id':42})
                            if changed: records[0]['settings']['clients']=[{'email':'administrator'}]
                            raise subprocess.TimeoutExpired('curl',25)
                        if path.endswith('/inbounds/del/42'): records.clear()
                        return {'obj':None}
                with patch.object(vision,'run'), self.assertRaises(vision.Failure) as failed:
                    vision.configure(Panel(),'vision.example',12000,12001,stream,site,enabled,cert,key)
                self.assertEqual(failed.exception.status,'failed_unverified' if changed else 'failed_rolled_back')
                self.assertEqual(bool(records),changed)
                self.assertEqual(calls.count('panel/api/inbounds/add'),1)
                self.assertEqual(stream.read_text(),original)
                self.assertFalse(site.exists()); self.assertFalse(enabled.is_symlink())

    def test_vision_reinstall_accepts_owned_files_and_refuses_foreign_files(self):
        from test_personal_backup import relocated
        vision=helper('vision')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); available=root/'etc/nginx/sites-available'; available.mkdir(parents=True)
            enabled=root/'etc/nginx/sites-enabled'; enabled.mkdir()
            site=available/'vision.conf'; valid=vision.fallback_config('vision.example',12001)
            site.write_text(valid); site.chmod(0o644)
            link=enabled/'vision.conf'; link.symlink_to(site)
            # UID/GID fixture only; file modes and symlinks are actually checked.
            stubs='stat() { case "$2" in *%a*) echo "${OWNER:-0}:0:$(/usr/bin/stat -c %a "$3")";; *) echo "${OWNER:-0}:0";; esac; }; msg_err() { echo "$*" >&2; }; msg_warn() { :; };\n'
            script=stubs+relocated(function('preflight_vision_artifacts'),root)+'\npreflight_vision_artifacts'
            env={**os.environ,'PANEL_STAGE':str(ROOT/'assets/vision')}
            # Helper filename follows the staged installer convention.
            stage=root/'stage'; stage.mkdir(); (stage/'managed-vision.py').write_text((ROOT/'assets/vision/managed.py').read_text())
            env['PANEL_STAGE']=str(stage)
            run=lambda: subprocess.run(['bash','-eu','-c',script],env=env,capture_output=True,text=True)
            self.assertEqual(run().returncode,0)
            for bad in (valid.replace(vision.MARKER,'# Administrator config\n'),valid.replace('root /var/www/html;','root /etc;'),valid.replace('set_real_ip_from 127.0.0.1;','set_real_ip_from 0.0.0.0/0;'),valid.replace('try_files $uri $uri/ =404;','proxy_pass http://127.0.0.1:10002;')):
                with self.subTest(content=bad.splitlines()[0]):
                    site.write_text(bad); self.assertNotEqual(run().returncode,0)
                    self.assertEqual(site.read_text(),bad)
            site.write_text(valid); site.chmod(0o666); self.assertNotEqual(run().returncode,0)
            site.chmod(0o644); site.unlink(); site.symlink_to(root/'foreign'); self.assertNotEqual(run().returncode,0)
            site.unlink(); site.write_text(valid); site.chmod(0o644); self.assertEqual(run().returncode,0)
            env['OWNER']='1000'; self.assertNotEqual(run().returncode,0)
            env['OWNER']='0'; self.assertEqual(run().returncode,0)

    def test_vision_runtime_refuses_unapproved_lineage_without_touching_artifacts(self):
        from test_personal_backup import relocated
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('etc/nginx/sites-available','etc/nginx/sites-enabled','etc/letsencrypt/live/vision.example','etc/letsencrypt/renewal-hooks/deploy'):
                (root/name).mkdir(parents=True)
            cert=root/'etc/letsencrypt/live/vision.example/fullchain.pem'; cert.write_text('foreign certificate')
            hook=root/'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision'; hook.write_text('foreign hook')
            script=relocated(function('install_vision'),root)
            stubs='make_port() { echo $((RANDOM+10000)); }; python3() { echo "# rendering"; }; ln() { return 1; }; nginx() { :; }; systemctl() { :; }; check_installation() { :; }; msg_warn() { :; }; certbot() { return 1; };\n'
            result=subprocess.run(['bash','-eu','-c',stubs+script+'\nPANEL_STAGE=/stage; vision_domain=vision.example; install_vision'],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(cert.read_text(),'foreign certificate')
            self.assertTrue(hook.exists(),'Unapproved foreign hook removed on failure')
            self.assertEqual(hook.read_text(),'foreign hook')
            self.assertFalse((root/'etc/nginx/sites-available/vision-acme.conf').exists())

    def test_vision_existing_lineage_requires_complete_project_ownership(self):
        from test_personal_backup import relocated
        vision=helper('vision')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); stage=root/'stage'; stage.mkdir()
            (stage/'managed-vision.py').write_text((ROOT/'assets/vision/managed.py').read_text())
            available=root/'etc/nginx/sites-available'; available.mkdir(parents=True)
            (root/'etc/nginx/sites-enabled').mkdir()
            hook=root/'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision'; hook.parent.mkdir(parents=True)
            lineage=root/'etc/letsencrypt/live/vision.example'; lineage.mkdir(parents=True)
            (lineage/'fullchain.pem').write_text('administrator certificate')
            stubs='stat() { case "$2" in *%a*) echo "${OWNER:-0}:0:$(/usr/bin/stat -c %a "$3")";; *) echo "${OWNER:-0}:0";; esac; }; msg_err() { echo "$*" >&2; }; msg_warn() { :; };\n'
            functions=relocated(function('render_vision_hook')+'\n'+function('preflight_vision_artifacts'),root)
            run=lambda: subprocess.run(['bash','-eu','-c',stubs+functions+'\ncheck_webroot_lineage() { :; }; INSTALL_VISION=y; vision_domain=vision.example; preflight_vision_artifacts'],env={**os.environ,'PANEL_STAGE':str(stage)},capture_output=True,text=True)
            self.assertNotEqual(run().returncode,0,'Foreign existing lineage adopted')
            hook.write_text(subprocess.check_output(['bash','-c',relocated(function('render_vision_hook'),root)+'\nrender_vision_hook vision.example'],text=True)); hook.chmod(0o755)
            self.assertNotEqual(run().returncode,0,'Incomplete old ownership adopted')
            (available/'vision.conf').write_text(vision.fallback_config('vision.example',12001))
            # The canonical ACME generator is introduced by the ownership fix.
            acme='# Managed by 3x-ui Auto Nginx: Vision\nserver {\n    listen 80;\n    listen [::]:80;\n    server_name vision.example;\n    location ^~ /.well-known/acme-challenge/ { root /var/www/acme; try_files $uri =404; }\n    location / { return 301 https://$host$request_uri; }\n}\n'
            (available/'vision-acme.conf').write_text(acme)
            self.assertEqual(run().returncode,0)
            self.assertEqual((lineage/'fullchain.pem').read_text(),'administrator certificate')

    def test_initial_client_random_subscription_and_no_plaintext_success(self):
        client = helper('client')
        ids = {client.random_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)
        for value in ids: self.assertRegex(value, r'^[a-z0-9]{16}$')
        for bad in (b'', b'not-base64', b'vless://abc@host:443?allowInsecure=1'):
            with self.assertRaises(Exception): client.decode_subscription(bad)

    def test_subscription_secret_url_is_not_in_process_arguments(self):
        from types import SimpleNamespace
        client=helper('client'); url='https://panel.example/sub/private-identity'
        with patch.object(client.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=b'profile')) as run:
            self.assertEqual(client.fetch(SimpleNamespace(options=[]),url),b'profile')
            self.assertNotIn(url,run.call_args.args[0])
            self.assertIn(url.encode(),run.call_args.kwargs['input'])

    def test_declined_features_never_mutate_system(self):
        declined=subprocess.run(['bash','-eu','-c','python3() { echo MUTATION; return 1; };\n'+function('prepare_system_dns')+'\nINSTALL_SECURITY=n; prepare_system_dns'],capture_output=True,text=True)
        self.assertEqual(declined.returncode,0,declined.stderr); self.assertNotIn('MUTATION',declined.stdout)
        names = ('confirm_destructive_reinstall', 'validate_domains', 'select_amneziawg', 'select_adguard',
                 'preflight_panel_release', 'preflight_amneziawg', 'cleanup_adguard', 'clean_previous_install',
                 'install_packages', 'setup_firewall', 'get_server_ip', 'setup_acme_http', 'get_ssl_certs',
                 'install_panel', 'configure_nginx', 'configure_xui_db', 'install_clash_sub', 'install_fake_site',
                 'install_diagnostics', 'tune_system', 'install_backup_tool', 'setup_certificate_renewal', 'check_installation', 'show_results', 'preflight_vision_artifacts','preflight_base_os','prepare_base_os','prepare_system_dns','finish_initial_reboot')
        stubs = '\n'.join(name + '() { :; }' for name in names)
        stubs += '\nmsg_warn() { :; }; select_security() { INSTALL_SECURITY=n; }; select_vision() { INSTALL_VISION=n; }; select_client() { CREATE_CLIENT=n; }; systemctl() { :; }; x-ui() { :; }\n'
        for name in ('install_security', 'install_vision', 'install_initial_client'):
            stubs += name + '() { echo MUTATION; return 1; };\n'
        result = subprocess.run(['bash', '-eu', '-c', stubs + function('preflight_integrated_features') + '\n' + function('main') + '\nINSTALL_AGH=n; main'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('MUTATION', result.stdout)

    def test_client_partial_and_uncertain_api_results_are_reconciled_once(self):
        client = helper('client')
        for uncertain, attach_failure in ((False,False),(True,False),(False,True)):
            calls, records = [], []
            rows = [{'id':i,'enable':True,'protocol':'vless','remark':name,
                     'settings':{'clients':[]},'streamSettings':stream} for i,name,stream in (
                         (1,'reality',{'network':'tcp','security':'reality'}),
                         (2,'xhttp',{'network':'xhttp','security':'none'}))]
            class Panel:
                def request(self,path,data=None):
                    calls.append(path)
                    if path.endswith('/inbounds/list'): return {'obj':rows}
                    if path.endswith('/clients/list'): return {'obj':[r['client'] for r in records]}
                    if path.endswith('/clients/add'):
                        c={**data['client'],'id':'3e967ef2-5fcb-4a2e-88b5-67d6f2489fc3'}
                        rows[0]['settings']['clients']=[c]
                        records.append({'client':{**data['client'],'id':7},'inboundIds':[1]})
                        if uncertain: raise subprocess.TimeoutExpired('curl',20)
                        raise ValueError('Partial failure')
                    if '/clients/get/' in path: return {'obj':records[0]}
                    if path.endswith('/attach'):
                        if attach_failure: raise ValueError('Remaining inbound failed')
                        rows[1]['settings']['clients']=[{**rows[0]['settings']['clients'][0],'flow':''}]
                        records[0]['inboundIds']=[1,2]
                    return {'obj':None}
            with patch.object(client,'subscription',return_value='https://panel.example/sub/id') as sub:
                if attach_failure:
                    with self.assertRaises(ValueError): client.create(Panel())
                    sub.assert_not_called()
                else:
                    result=client.create(Panel())
                    self.assertEqual(result['id'],7)
            self.assertEqual(calls.count('panel/api/clients/add'),1)
            self.assertEqual(sum(path.endswith('/attach') for path in calls),1)
            self.assertFalse(any('/del/' in path for path in calls))

    def test_client_identity_collision_never_posts(self):
        client=helper('client')
        from unittest.mock import Mock
        api=Mock()
        api.request.side_effect=[{'obj':[{'id':1,'enable':True,'protocol':'vless','remark':'reality'}]},
                                 {'obj':[{'email':'administrator','subId':'a'*16}]}]
        with patch.object(client,'random_id',return_value='a'*16), self.assertRaises(ValueError): client.create(api)
        self.assertEqual(api.request.call_count,2)

    def test_six_option_combinations_keep_lifecycle_order(self):
        # Security, Vision, AWG, AGH, Client; exact required six combinations.
        scenarios=('nnnnn','ynnny','nynny','ynnyy','nyyny','yyyyy')
        names=('confirm_destructive_reinstall','validate_domains','select_security','select_vision','select_amneziawg',
               'select_adguard','select_client','preflight_panel_release','preflight_amneziawg','preflight_integrated_features',
               'cleanup_adguard','clean_previous_install','install_packages','setup_firewall','get_server_ip','setup_acme_http',
               'get_ssl_certs','install_panel','configure_nginx','configure_xui_db','install_clash_sub','install_fake_site',
               'install_diagnostics','tune_system','install_backup_tool','setup_certificate_renewal','check_installation','show_results','preflight_base_os','prepare_base_os','prepare_system_dns','finish_initial_reboot')
        stubs='\n'.join(name+'() { :; }' for name in names)+'\nmsg_warn() { :; }; systemctl() { :; }; x-ui() { :; }\n'
        for name in ('install_security','install_vision','install_amneziawg','install_adguard','install_initial_client'):
            stubs+=name+'() { echo '+name+'; };\n'
        for flags in scenarios:
            variables=dict(zip(('INSTALL_SECURITY','INSTALL_VISION','INSTALL_AWG','INSTALL_AGH','CREATE_CLIENT'),flags))
            result=subprocess.run(['bash','-eu','-c',stubs+function('main')+'\nmain'],env={**os.environ,**variables},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            expected=[name for name,key in (('install_vision','INSTALL_VISION'),('install_amneziawg','INSTALL_AWG'),
                ('install_adguard','INSTALL_AGH'),('install_security','INSTALL_SECURITY'),('install_initial_client','CREATE_CLIENT')) if variables[key]=='y']
            self.assertEqual(result.stdout.splitlines(),['','Preparing system...']+expected)
        # An uncertain Vision inbound may still be enabled but lack its SNI
        # route. Do not attach a new client or publish it as ready in that state.
        failure_stubs=stubs+'\ninstall_vision() { VISION_RESULT=failed_unverified; return 1; }; show_results() { echo "$CLIENT_RESULT"; };'
        variables=dict(zip(('INSTALL_SECURITY','INSTALL_VISION','INSTALL_AWG','INSTALL_AGH','CREATE_CLIENT'),'nynny'))
        result=subprocess.run(['bash','-eu','-c',failure_stubs+function('main')+'\nmain'],env={**os.environ,**variables},capture_output=True,text=True)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertNotIn('install_initial_client',result.stdout)
        self.assertIn('failed_unverified',result.stdout)
