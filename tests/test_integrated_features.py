"""v2 optional features: isolated preflight, protocol validation and failure ownership."""
import importlib.util
import json
import os
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
    def test_security_readonly_preflight_blocks_cleanup_for_known_conflicts(self):
        from test_personal_backup import relocated
        cases = ('inactive', 'resolv', 'dns', 'jail', 'jail-conf', 'apt', 'compatible', 'declined')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); (root/'etc').mkdir()
                (root/'etc/os-release').write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
                resolv = root/'etc/resolv.conf'
                resolv.symlink_to('/provider/resolv.conf' if case=='resolv' else '/run/systemd/resolve/stub-resolv.conf')
                if case=='dns':
                    policy=root/'etc/systemd/resolved.conf'; policy.parent.mkdir(parents=True)
                    policy.write_text('[Resolve]\nDNS=10.0.0.1\n')
                if case in ('jail','jail-conf'):
                    jail=root/('etc/fail2ban/jail.local' if case=='jail' else 'etc/fail2ban/jail.d/provider.conf'); jail.parent.mkdir(parents=True)
                    jail.write_text('[sshd]\nmaxretry=2\n')
                stage=root/'stage'; stage.mkdir()
                source=(ROOT/'assets/security/managed.py').read_text()
                # Execute the real helper CLI against private files and read-only
                # command fixtures. No installer/global paths are executed.
                override = "shutil.which = lambda tool: tool\ndef command(*args, **kwargs):\n    if args[0]=='/usr/sbin/sshd': return 'port 22'\n    if args[0]=='journalctl': return 'SSH journal'\n    if args[:2]==('systemctl','is-active'): return %r if args[-1]=='systemd-resolved.service' else 'inactive'\n    if args[:2]==('systemctl','is-enabled'): return 'enabled'\n    return ''\n" % ('inactive' if case=='inactive' else 'active')
                if case=='apt': override=override.replace("    return ''\n","    if args[0]=='apt-config': return 'APT::Periodic::Enable \"0\";'\n    return ''\n")
                prefix, cli=source.split("if __name__ == '__main__':",1)
                (root/'helper.py').write_text(prefix.replace("root=Path('/')", 'root=Path('+repr(str(root))+')')+override+"if __name__ == '__main__':"+cli)
                names=('confirm_destructive_reinstall','validate_domains','select_vision','select_amneziawg','select_adguard','select_client',
                       'preflight_panel_release','preflight_amneziawg','preflight_vision_artifacts')
                stubs='\n'.join(name+'() { :; }' for name in names)
                stubs+='\nselect_security() { INSTALL_SECURITY='+('n' if case=='declined' else 'y')+'; }; msg_err() { echo "$*" >&2; };\n'
                stubs+='curl() { cp "$FIXTURE_HELPER" "${@: -1}"; }; cleanup_adguard() { echo CLEANUP; exit 19; }; clean_previous_install() { echo DESTRUCTION; };\n'
                script=stubs+function('preflight_integrated_features')+'\n'+function('main')+'\nINSTALL_VISION=n; CREATE_CLIENT=n; main'
                env={**os.environ,'PANEL_STAGE':str(stage),'GITHUB_RAW':'https://fixture.invalid','FIXTURE_HELPER':str(root/'helper.py')}
                before={str(p.relative_to(root)):os.readlink(p) if p.is_symlink() else p.read_bytes() for p in (root/'etc').rglob('*') if p.is_file() or p.is_symlink()}
                result=subprocess.run(['bash','-eu','-c',script],env=env,capture_output=True,text=True)
                after={str(p.relative_to(root)):os.readlink(p) if p.is_symlink() else p.read_bytes() for p in (root/'etc').rglob('*') if p.is_file() or p.is_symlink()}
                self.assertEqual(before,after)
                if case in ('compatible','declined'):
                    self.assertEqual(result.returncode,19,result.stderr)
                    self.assertIn('CLEANUP',result.stdout)
                else:
                    self.assertEqual(result.returncode,1,result.stderr)
                    self.assertNotIn('CLEANUP',result.stdout)
                    self.assertNotIn('DESTRUCTION',result.stdout)
                    self.assertIn('preflight',result.stderr.lower())

    def test_security_apt_conflict_refuses_before_configuration(self):
        security=helper('security')
        for key in ('Enable','Update-Package-Lists','Unattended-Upgrade'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'administrator policy'):
                security.apt_preflight('APT::Periodic::'+key+' "0";')
        self.assertEqual(security.apt_preflight(''),set())
        self.assertEqual(security.apt_preflight('Unattended-Upgrade::Origins-Pattern:: "origin=Provider,label=Provider-Security";'),{('Origins-Pattern','origin=Provider,label=Provider-Security')})

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
                admin=parts/'50unattended-upgrades'; admin.write_text(stock+'\nUnattended-Upgrade::Origins-Pattern { "origin=Provider,label=Provider-Security"; };\n')
                dump=lambda: subprocess.check_output(['apt-config','dump'],env={**os.environ,'APT_CONFIG':str(bootstrap)},text=True)
                before=dump(); self.assertIn('origin=Provider,label=Provider-Security',before); owned=parts/'99zz-3x-ui-auto-nginx'; owned.write_text(security.apt_config(os_id)); after=dump()
                for line in before.splitlines():
                    if 'Unattended-Upgrade::' in line and ':: "' in line:
                        self.assertIn(line,after,'Existing effective origin removed')
                self.assertIn('origin=Provider,label=Provider-Security',after)
                self.assertIn('Unattended-Upgrade::Automatic-Reboot "false";',after)
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

    def test_prompt_defaults_decline_and_eof(self):
        for name, variable, default in (('select_security', 'INSTALL_SECURITY', 'y'),
                                         ('select_client', 'CREATE_CLIENT', 'y'),
                                         ('select_vision', 'INSTALL_VISION', 'n')):
            for answer, expected in (('\n', default), ('n\n', 'n'), ('N\n', 'n'), ('', 'n')):
                result = subprocess.run(['bash', '-eu', '-c', function(name) + f'; {name}; echo RESULT=${variable}'],
                                        input=answer, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('RESULT=' + expected, result.stdout)

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

    def test_dns_preflight_refuses_regular_custom_links_and_provider_policy(self):
        security = helper('security')
        with tempfile.TemporaryDirectory() as directory, patch.object(security, 'command', return_value='active'):
            root = Path(directory); (root / 'etc').mkdir()
            resolv = root / 'etc/resolv.conf'; resolv.write_text('nameserver 8.8.8.8\n')
            with self.assertRaises(ValueError): security.preflight(root)
            self.assertEqual(resolv.read_text(), 'nameserver 8.8.8.8\n')
            resolv.unlink(); resolv.symlink_to('/custom/provider/resolv.conf')
            with self.assertRaises(ValueError): security.preflight(root)
            self.assertEqual(os.readlink(resolv), '/custom/provider/resolv.conf')
            resolv.unlink(); resolv.symlink_to('/run/systemd/resolve/stub-resolv.conf')
            config = root / 'etc/systemd/resolved.conf'; config.parent.mkdir(); config.write_text('[Resolve]\nDNS=10.0.0.1\n')
            with self.assertRaises(ValueError): security.preflight(root)
            self.assertIn('10.0.0.1', config.read_text())

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
        self.assertIn('Automatic-Reboot "false"', security.apt_config('ubuntu'))
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
            if args[0]=='apt-config': return 'Unattended-Upgrade::Automatic-Reboot "false";\nUnattended-Upgrade::Origins-Pattern:: "origin=Ubuntu,archive=${distro_codename}-security";'
            if args[:2]==('systemctl','show'): return ('03' if args[2]=='apt-daily-upgrade.timer' else '02')+':30:00\nRandomizedDelayUSec=0'
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
                if args[0]=='curl': raise ValueError('Fallback unavailable')
            with patch.object(vision,'certificate'),patch.object(vision,'run',side_effect=run),self.assertRaises(vision.Failure) as failed:
                vision.configure(Panel(),'vision.example',12000,12001,stream,site,enabled,'/cert','/key')
            self.assertEqual(failed.exception.status,'failed_rolled_back')
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
            stubs='stat() { case "$2" in *%a*) echo "${OWNER:-0}:0:$(/usr/bin/stat -c %a "$3")";; *) echo "${OWNER:-0}:0";; esac; }; msg_err() { echo "$*" >&2; };\n'
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
            stubs='stat() { case "$2" in *%a*) echo "${OWNER:-0}:0:$(/usr/bin/stat -c %a "$3")";; *) echo "${OWNER:-0}:0";; esac; }; msg_err() { echo "$*" >&2; };\n'
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
        names = ('confirm_destructive_reinstall', 'validate_domains', 'select_amneziawg', 'select_adguard',
                 'preflight_panel_release', 'preflight_amneziawg', 'cleanup_adguard', 'clean_previous_install',
                 'install_packages', 'setup_firewall', 'get_server_ip', 'setup_acme_http', 'get_ssl_certs',
                 'install_panel', 'configure_nginx', 'configure_xui_db', 'install_clash_sub', 'install_fake_site',
                 'install_diagnostics', 'tune_system', 'install_backup_tool', 'setup_certificate_renewal', 'check_installation', 'show_results', 'preflight_vision_artifacts')
        stubs = '\n'.join(name + '() { :; }' for name in names)
        stubs += '\nselect_security() { INSTALL_SECURITY=n; }; select_vision() { INSTALL_VISION=n; }; select_client() { CREATE_CLIENT=n; }; systemctl() { :; }; x-ui() { :; }\n'
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
               'install_diagnostics','tune_system','install_backup_tool','setup_certificate_renewal','check_installation','show_results')
        stubs='\n'.join(name+'() { :; }' for name in names)+'\nsystemctl() { :; }; x-ui() { :; }\n'
        for name in ('install_security','install_vision','install_amneziawg','install_adguard','install_initial_client'):
            stubs+=name+'() { echo '+name+'; };\n'
        for flags in scenarios:
            variables=dict(zip(('INSTALL_SECURITY','INSTALL_VISION','INSTALL_AWG','INSTALL_AGH','CREATE_CLIENT'),flags))
            result=subprocess.run(['bash','-eu','-c',stubs+function('main')+'\nmain'],env={**os.environ,**variables},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            expected=[name for name,key in (('install_vision','INSTALL_VISION'),('install_amneziawg','INSTALL_AWG'),
                ('install_adguard','INSTALL_AGH'),('install_security','INSTALL_SECURITY'),('install_initial_client','CREATE_CLIENT')) if variables[key]=='y']
            self.assertEqual(result.stdout.splitlines(),expected)
        # An uncertain Vision inbound may still be enabled but lack its SNI
        # route. Do not attach a new client or publish it as ready in that state.
        failure_stubs=stubs+'\ninstall_vision() { VISION_RESULT=failed_unverified; return 1; }; show_results() { echo "$CLIENT_RESULT"; };'
        variables=dict(zip(('INSTALL_SECURITY','INSTALL_VISION','INSTALL_AWG','INSTALL_AGH','CREATE_CLIENT'),'nynny'))
        result=subprocess.run(['bash','-eu','-c',failure_stubs+function('main')+'\nmain'],env={**os.environ,**variables},capture_output=True,text=True)
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertNotIn('install_initial_client',result.stdout)
        self.assertIn('failed_unverified',result.stdout)
