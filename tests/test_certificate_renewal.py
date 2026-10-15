"""Execute guard, Certbot and deploy-hook paths only on private fixtures."""
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
from configobj import ConfigObj
from certificate_fixtures import INSTALLER, LEGACY, certificates, function, relocate

MOCK = r'''
msg_err() { echo "$*" >&2; }
msg_warn() { echo "$*"; }
msg_inf() { echo "$*"; }
msg_ok() { echo "$*"; }
command() {
    [[ "${NO_CRONTAB:-0}" == 1 && "$*" == '-v crontab' ]] && return 1
    builtin command "$@"
}
systemctl() {
    echo "systemctl $*" >> "$CALLS"
    [[ "$*" != "${FAIL_CERT:-none}" ]]
}
nginx() { echo "nginx $*" >> "$CALLS"; [[ "${FAIL_CERT:-}" != nginx ]]; }
crontab() {
    case "$1" in
        -l)
            [[ "${FAIL_CERT:-}" != cron-read ]] || return 1
            [[ -f "$CRON" ]] || { echo 'no crontab for root' >&2; return 1; }
            cat "$CRON" ;;
        -)
            echo crontab-write >> "$CALLS"
            [[ "${FAIL_CERT:-}" != cron-write ]] || return 1
            cat > "$CRON" ;;
    esac
}
curl() {
    [[ "${FAIL_CERT:-}" != acme ]] || return 1
    local arg host='' url="${!#}"
    for arg in "$@"; do [[ "$arg" != 'Host: '* ]] || host="${arg#Host: }"; done
    if [[ "$url" == *'/.well-known/acme-challenge/'* ]]; then
        cat "$ROOT/var/www/acme/.well-known/acme-challenge/${url##*/}"
    else
        printf '301 https://%s/' "$host"
    fi
}
# Model root-owned deployment metadata for unprivileged CI fixtures; real mode remains checked.
stat() {
    if [[ "$*" == *'%u:%g:%a'* && ( "$EUID" != 0 || "${FAIL_CERT:-}" == owner ) ]]; then
        local mode; mode=$(command stat -c '%a' "${!#}") || return 1
        printf '%s:0:%s\n' "$([[ "${FAIL_CERT:-}" == owner ]] && echo 1000 || echo 0)" "$mode"
    else command stat "$@"; fi
}
install() {
    if [[ "$EUID" == 0 ]]; then command install "$@"; return; fi
    local -a args=()
    while (( $# )); do
        case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac
    done
    command install "${args[@]}"
}
chown() { [[ "$EUID" != 0 ]] || command chown "$@"; }
'''
RENEWAL = ('check_webroot_lineage', 'check_acme_http', 'check_no_legacy_certbot_cron', 'check_certificate_renewal')


class CertificateRenewal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='renewal-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = self.root / 'calls'
        self.env = {**os.environ, 'ROOT': str(self.root), 'CALLS': str(self.calls), 'CRON': str(self.root / 'cron'),
                    'PATH':str(self.root/'health-bin')+':'+os.environ['PATH'], 'LEGACY_CERTBOT_CRON': LEGACY, 'domain': 'example.com', 'reality_domain': 'reality.example.com'}

    def run_functions(self, names, body, mock=MOCK, input=None, **env):
        if 'setup_certificate_renewal' in names:
            names = (*names, 'render_certificate_hook', 'check_xray_runtime')
        script = mock + '\n' + '\n'.join(relocate(function(name), self.root) for name in names) + '\n' + body
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', script], input=input, text=True, capture_output=True,
                              env={**self.env, **env})

    def deploy(self, hook, **env):
        # Services are stateful fixtures; certificate parsing stays real.
        self.calls.unlink(missing_ok=True)
        script = r'''
restarted=0
reloaded=0
systemctl() {
    echo "systemctl $*" >> "$CALLS"
    case "$1" in
        is-active)
            [[ "$*" != "${FAIL_DEPLOY:-}" ]] || return 1
            [[ "${FAIL_DEPLOY:-}" != 'post x-ui' || "$restarted" == 0 || "${!#}" != x-ui ]] || return 1
            [[ "${FAIL_DEPLOY:-}" != 'post nginx' || "$reloaded" == 0 || "${!#}" != nginx ]] || return 1
            [[ "${!#}" != x-ui || "$XUI_ACTIVE" == 1 ]] &&
            [[ "${!#}" != nginx || "$NGINX_ACTIVE" == 1 ]] ;;
        restart|try-restart) restarted=1; [[ "$*" != "${FAIL_DEPLOY:-}" ]] ;;
        reload) reloaded=1; [[ "$*" != "${FAIL_DEPLOY:-}" ]] ;;
        *) return 1 ;;
    esac
}
nginx() { echo "nginx $*" >> "$CALLS"; [[ "${FAIL_DEPLOY:-}" != nginx ]]; }
curl() { echo curl >> "$CALLS"; return 35; }
sleep() { :; }
source "$HOOK"
'''
        result = subprocess.run(['bash', '-c', script], text=True, capture_output=True,
            env={**self.env, 'HOOK': str(hook), 'XUI_ACTIVE':'1', 'NGINX_ACTIVE':'1', **env})
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return result, calls

    def test_deploy_is_independent_of_inbounds_and_preserves_stopped_services(self):
        hook = certificates(self.root)
        ss = self.root/'health-bin/ss'
        # Python subprocess must encounter this real executable, not a shell function.
        ss.write_text('''#!/bin/sh
echo ss >> "$CALLS"
case "$DISABLED" in all|custom-only) exit 0;; esac
case "$*" in
 *-lxnp*) [ "$DISABLED" = xhttp ] || echo 'u_str LISTEN 0 128 '''+str(self.root)+'''/dev/shm/uds2023.sock 0 users:(("xray",pid=43210,fd=1))';;
 *)
 [ "$DISABLED" = reality ] || echo 'tcp LISTEN 0 128 127.0.0.1:8443 *:* users:(("xray",pid=43210,fd=2))'
 [ "$DISABLED" = hysteria2 ] || echo 'udp UNCONN 0 128 *:443 *:* users:(("xray",pid=43210,fd=3))';;
esac
exit 0
''')
        for disabled in ('none','reality','xhttp','hysteria2','all','custom-only'):
            with self.subTest(disabled=disabled):
                result,calls = self.deploy(hook, DISABLED=disabled,
                    RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live/example.com'))
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('systemctl try-restart x-ui',calls)
                self.assertNotIn('ss',calls)
                self.assertNotIn('curl',calls)
        for nginx,xui in (('1','1'),('1','0'),('0','1'),('0','0')):
            with self.subTest(nginx=nginx,xui=xui):
                result,calls = self.deploy(hook, NGINX_ACTIVE=nginx, XUI_ACTIVE=xui,
                    RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live/example.com'))
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual('systemctl reload nginx' in calls,nginx=='1')
                self.assertEqual('nginx -t' in calls,nginx=='1')
                self.assertEqual('systemctl try-restart x-ui' in calls,xui=='1')
                self.assertNotIn('systemctl restart x-ui',calls)
        for lineage,domains in (('foreign','example.com reality.example.com'),
                                ('','example.com'),('reality.example.com','example.com')):
            result,calls = self.deploy(hook, RENEWED_DOMAINS=domains,
                RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live'/lineage) if lineage else '')
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(any('restart' in c for c in calls),calls)
            if lineage!='reality.example.com':self.assertEqual(calls,[])
        for failure in ('nginx','reload nginx','try-restart x-ui'):
            result,calls = self.deploy(hook, FAIL_DEPLOY=failure,
                RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live/example.com'))
            self.assertNotEqual(result.returncode,0,failure)
            self.assertIn('nginx -t' if failure=='nginx' else 'systemctl '+failure,calls)
        for failure in ('post nginx','post x-ui'):
            result,calls=self.deploy(hook,FAIL_DEPLOY=failure,
                RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live/example.com'))
            self.assertNotEqual(result.returncode,0,failure)

    def test_vision_deploy_uses_certificate_and_active_service_only(self):
        certificates(self.root,extra=('vision.example','other.example'))
        result=self.run_functions(('render_vision_hook',),'render_vision_hook vision.example')
        self.assertEqual(result.returncode,0,result.stderr)
        hook=self.root/'vision-hook';hook.write_text(result.stdout)
        lineage=self.root/'etc/letsencrypt/live/vision.example'
        for active in ('1','0'):
            result,calls=self.deploy(hook,XUI_ACTIVE=active,RENEWED_LINEAGE=str(lineage))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertNotIn('curl',calls,'Unavailable/TLS EOF fallback is not a deployment gate')
            self.assertEqual('systemctl try-restart x-ui' in calls,active=='1')
            self.assertNotIn('systemctl restart x-ui',calls)
        result,calls=self.deploy(hook,RENEWED_LINEAGE=str(lineage),FAIL_DEPLOY='try-restart x-ui')
        self.assertNotEqual(result.returncode,0)
        result,calls=self.deploy(hook,RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live/other.example'))
        self.assertEqual(result.returncode,0);self.assertEqual(calls,[])
        original={name:(lineage/name).read_bytes() for name in ('fullchain.pem','privkey.pem')}
        for fault in ('missing','invalid','mismatch','hostname'):
            with self.subTest(fault=fault):
                for name,data in original.items():(lineage/name).write_bytes(data)
                if fault=='missing':(lineage/'fullchain.pem').unlink()
                if fault=='invalid':(lineage/'fullchain.pem').write_text('invalid')
                if fault in ('mismatch','hostname'):
                    shutil.copyfile(self.root/'etc/letsencrypt/live/other.example/privkey.pem',lineage/'privkey.pem')
                if fault=='hostname':
                    shutil.copyfile(self.root/'etc/letsencrypt/live/other.example/fullchain.pem',lineage/'fullchain.pem')
                result,calls=self.deploy(hook,RENEWED_LINEAGE=str(lineage))
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(any('restart' in c for c in calls),calls)

    def test_supported_os_rejects_debian12_before_guard(self):
        for distro, version, allowed in (('ubuntu','24.04',True),('ubuntu','26.04',True),('debian','13',True),
                                        ('debian','12',False),('ubuntu','22.04',False),('other','13',False)):
            with self.subTest(distro=distro, version=version):
                path = self.root / 'etc/os-release'; path.parent.mkdir(exist_ok=True)
                path.write_text(f'ID={distro}\nVERSION_ID="{version}"\n')
                result = self.run_functions(('check_os',), 'check_os\necho reached-guard\n')
                self.assertEqual(result.returncode, 0 if allowed else 1, result.stderr)
                self.assertEqual('reached-guard' in result.stdout, allowed)

    def test_guard_detects_existing_installations_and_requires_exact_yes(self):
        indicators = ('/etc/x-ui', '/usr/local/x-ui/x-ui', '/usr/bin/x-ui', '/etc/systemd/system/x-ui.service',
                      '/usr/local/lib/3x-ui-pro', '/usr/local/bin/x-ui-backup', '/etc/systemd/system/mtr-backend.service',
                      '/etc/nginx/nginx.conf', '/etc/nginx/snippets/includes.conf', '/root/cert/example.com/fullchain.pem',
                      '/etc/letsencrypt/live/example.com/fullchain.pem', '/opt/AdGuardHome/AdGuardHome',
                      '/etc/systemd/system/AdGuardHome.service', '/etc/nginx/snippets/adguard.conf',
                      '/etc/nginx/snippets/x-ui-auto-optional/adguard.conf')
        mock = MOCK + '''\nsystemctl() { [[ "${ACTIVE_SERVICE:-}" == "$3" ]]; }
dpkg-query() { [[ "${NGINX_PACKAGE:-0}" == 1 ]] && echo 'install ok installed'; }
'''
        result = self.run_functions(('detect_existing_installation','confirm_destructive_reinstall'),
                                    'confirm_destructive_reinstall\necho continued', mock=mock, input='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Type YES', result.stdout)
        for marker in indicators:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); path = root / marker.lstrip('/'); path.parent.mkdir(parents=True); path.touch()
                script = mock + '\n' + '\n'.join(relocate(function(n), root) for n in ('detect_existing_installation','confirm_destructive_reinstall'))
                for answer in ('YES\n','yes\n','Yes\n','Y\n','y\n','1\n','YES \n',' YES\n','\n',''):
                    result = subprocess.run(['bash','-euo','pipefail','-c',script+'\nconfirm_destructive_reinstall\necho mutation\n'],
                                            input=answer,text=True,capture_output=True,env=self.env)
                    self.assertEqual(result.returncode, 0 if answer=='YES\n' else 1, result.stderr)
                    self.assertEqual('mutation' in result.stdout, answer=='YES\n')
                    self.assertIn('Type YES', result.stdout)
                    self.assertEqual(path.read_bytes(), b'')
        for env in ({'ACTIVE_SERVICE':'x-ui'},{'NGINX_PACKAGE':'1'}):
            result = self.run_functions(('detect_existing_installation','confirm_destructive_reinstall'),
                                        'confirm_destructive_reinstall\necho mutation',mock=mock,input='',**env)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('mutation',result.stdout)

    def test_install_and_uninstall_have_no_mutations_before_yes(self):
        (self.root / 'etc/x-ui').mkdir(parents=True)
        guard = ('detect_existing_installation','confirm_destructive_reinstall')
        mocks = MOCK + '\nsystemctl() { return 1; }\ndpkg-query() { return 1; }\n'
        operations = ('preflight_base_os','prepare_base_os','prepare_system_dns','finish_initial_reboot','select_security','select_vision','select_client','preflight_integrated_features','select_amneziawg','preflight_amneziawg','preflight_panel_release','select_adguard','cleanup_adguard','validate_domains','clean_previous_install','install_packages','setup_firewall','get_server_ip',
                      'setup_acme_http','get_ssl_certs','install_panel','configure_nginx','configure_xui_db','install_clash_sub',
                      'install_fake_site','install_diagnostics','tune_system','install_backup_tool','setup_certificate_renewal',
                      'check_installation','show_results','uninstall_xui')
        mocks += '\n'.join(n+'() { echo '+n+' >> "$CALLS"; }' for n in operations)
        mocks += '\nINSTALL_AGH=n\nsystemctl() { echo "systemctl $*" >> "$CALLS"; [[ "$*" == "is-enabled --quiet x-ui" ]]; }\nx-ui() { echo x-ui >> "$CALLS"; }\n'
        # Detection must see missing service states rather than mutate them.
        for uninstall in (False,True):
            for answer in ('YES\n','yes\n','\n',''):
                self.calls.unlink(missing_ok=True)
                branch = re.search(r'^if \[\[ \$\{UNINSTALL\}.*?^fi',INSTALLER,re.M|re.S).group()
                body = 'UNINSTALL=y\n'+branch if uninstall else function('main')+'\nmain'
                result = self.run_functions(guard,body,mock=mocks,input=answer)
                mutations = self.calls.read_text().splitlines() if self.calls.exists() else []
                # Read-only systemctl detection queries are allowed before confirmation.
                changes = [c for c in mutations if not c.startswith(('systemctl is-active','systemctl is-enabled'))]
                if answer == 'YES\n':
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('uninstall_xui' if uninstall else 'clean_previous_install',changes)
                else:
                    self.assertNotEqual(result.returncode,0)
                    self.assertEqual(changes,[])
                self.assertTrue((self.root/'etc/x-ui').exists())

    def test_legacy_cron_removal_preserves_unrelated_jobs(self):
        cron = self.root/'cron'
        unrelated = '# admin\n@daily /opt/x-ui-job\n@weekly certbot certificates\n@hourly cloudflareips\n\n'
        cron.write_text(unrelated+LEGACY+'\n'+LEGACY+'\n')
        result = self.run_functions(('remove_legacy_certbot_cron','check_no_legacy_certbot_cron'),
                                    'remove_legacy_certbot_cron\nremove_legacy_certbot_cron\ncheck_no_legacy_certbot_cron')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(cron.read_text(),unrelated)
        self.assertEqual(self.calls.read_text().count('crontab-write'),1)
        for failure in ('cron-read','cron-write'):
            cron.write_text(unrelated+LEGACY+'\n')
            result = self.run_functions(('remove_legacy_certbot_cron',),'remove_legacy_certbot_cron',FAIL_CERT=failure)
            self.assertNotEqual(result.returncode,0)
        for absent_binary in ('0','1'):
            cron.unlink(missing_ok=True)
            result = self.run_functions(('remove_legacy_certbot_cron','check_no_legacy_certbot_cron'),
                                        'remove_legacy_certbot_cron\ncheck_no_legacy_certbot_cron',NO_CRONTAB=absent_binary)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('/etc/cron.d/certbot',INSTALLER)

    def test_confirmed_uninstall_removes_only_project_certbot_hook(self):
        hook=certificates(self.root)
        unrelated=self.root/'etc/letsencrypt/live/unrelated.example/fullchain.pem'
        unrelated.parent.mkdir(parents=True);unrelated.write_text('unrelated certificate')
        other_hook=hook.parent/'administrator';other_hook.write_text('unrelated hook')
        package_cron=self.root/'etc/cron.d/certbot'
        package_cron.parent.mkdir(parents=True);package_cron.write_text('package-owned fallback\n')
        unrelated_cron='# administrator\n@daily /opt/x-ui-job\n@weekly certbot certificates\n@hourly cloudflareips\n\n'
        (self.root/'cron').write_text(unrelated_cron+LEGACY+'\n'+LEGACY+'\n')
        mock=MOCK+'''\nx-ui() { echo "x-ui $*" >> "$CALLS"; }
apt() { echo "apt $*" >> "$CALLS"; }
dpkg-query() { return 1; }
systemctl() { echo "systemctl $*" >> "$CALLS"; [[ "$*" != *AdGuardHome* ]]; }
'''
        branch=re.search(r'^if \[\[ \$\{UNINSTALL\}.*?^fi',INSTALLER,re.M|re.S).group()
        self.assertLess(INSTALLER.index('remove_legacy_certbot_cron()'),INSTALLER.index(branch))
        names=('detect_existing_installation','confirm_destructive_reinstall','remove_legacy_certbot_cron','cleanup_adguard','uninstall_xui')
        for answer in ('no\n','','YES\n'):
            self.calls.unlink(missing_ok=True)
            result=self.run_functions(names,'UNINSTALL=y\nPak=apt\n'+branch,mock=mock,input=answer)
            self.assertEqual(result.returncode,0 if answer=='YES\n' else 1,result.stderr)
            self.assertEqual(hook.exists(),answer!='YES\n')
            self.assertEqual(unrelated.read_text(),'unrelated certificate')
            self.assertEqual(other_hook.read_text(),'unrelated hook')
            self.assertEqual(package_cron.read_text(),'package-owned fallback\n')
            self.assertEqual((self.root/'cron').read_text(),unrelated_cron if answer=='YES\n' else unrelated_cron+LEGACY+'\n'+LEGACY+'\n')
            calls=self.calls.read_text()
            self.assertNotRegex(calls,r'systemctl (stop|disable).*certbot')
            self.assertNotIn('python3-certbot-nginx',calls)
            self.assertNotIn('autoremove',calls)
            self.assertNotRegex(calls,r'apt .* (?:remove|purge).*\bcertbot\b')
            self.assertEqual('crontab-write' in calls,answer=='YES\n')
        for failure in ('cron-read','cron-write'):
            certificates(self.root)
            (self.root/'cron').write_text(unrelated_cron+LEGACY+'\n')
            self.calls.unlink(missing_ok=True)
            result=self.run_functions(names,'UNINSTALL=y\nPak=apt\n'+branch,mock=mock,input='YES\n',FAIL_CERT=failure)
            self.assertNotEqual(result.returncode,0)
            self.assertNotIn('completely uninstalled',result.stdout)
            self.assertIn('Cannot remove the exact legacy',result.stderr)
            self.assertEqual((self.root/'cron').read_text(),unrelated_cron+LEGACY+'\n')
            self.assertTrue(hook.exists())
            self.assertEqual(unrelated.read_text(),'unrelated certificate')
            self.assertEqual(package_cron.read_text(),'package-owned fallback\n')
            self.assertNotRegex(self.calls.read_text(),r'apt |x-ui uninstall|systemctl (stop|disable)')

    def test_webroot_issuance_and_exact_lineage_reconfigure(self):
        template = self.root/'template'; template.mkdir(); certificates(template)
        certbot = r'''
certbot() {
    echo "certbot $*" >> "$CALLS"
    [[ "${FAIL_CERT:-}" != certbot ]] || return 1
    local d='' previous='' arg
    for arg in "$@"; do [[ "$previous" != --cert-name ]] || d="$arg"; previous="$arg"; done
    python3 - "$ROOT" "$TEMPLATE" "$d" <<'COPY'
from pathlib import Path
import shutil,sys
root,template,domain=map(Path,sys.argv[1:])
live=root/'etc/letsencrypt/live'/domain
live.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree(template/'etc/letsencrypt/live'/domain,live,dirs_exist_ok=True)
conf=root/'etc/letsencrypt/renewal'/(str(domain)+'.conf')
conf.parent.mkdir(parents=True,exist_ok=True)
conf.write_text((template/'etc/letsencrypt/renewal'/(str(domain)+'.conf')).read_text().replace(str(template),str(root)))
COPY
}
'''
        names=('check_certificate_identity','check_webroot_lineage','get_ssl_certs')
        for state in ('fresh','valid-webroot','legacy','wrong-webroot'):
            shutil.rmtree(self.root/'etc/letsencrypt', ignore_errors=True)
            shutil.rmtree(self.root/'root/cert', ignore_errors=True)
            if state!='fresh':
                certificates(self.root)
                if state in ('legacy','wrong-webroot'):
                    for config in (self.root/'etc/letsencrypt/renewal').glob('*.conf'):
                        cfg=ConfigObj(str(config))
                        if state=='legacy':cfg['renewalparams']['authenticator']='standalone'
                        else:
                            name=config.stem
                            cfg['renewalparams']['webroot_map'][name]='/wrong'
                        cfg.write()
            self.calls.unlink(missing_ok=True)
            result=self.run_functions(names,'get_ssl_certs',mock=MOCK+certbot,AUTODOMAIN='n',TEMPLATE=str(template))
            self.assertEqual(result.returncode,0,result.stderr)
            calls=self.calls.read_text().splitlines() if self.calls.exists() else []
            self.assertEqual(len(calls),0 if state=='valid-webroot' else 2)
            for call,domain in zip(calls,('example.com','reality.example.com')):
                self.assertIn('certbot certonly' if state=='fresh' else 'certbot reconfigure',call)
                self.assertIn('--cert-name '+domain,call)
                self.assertIn('--webroot --webroot-path '+str(self.root/'var/www/acme'),call)
                self.assertNotIn('--standalone',call)
            self.assertTrue((self.root/'root/cert/example.com/fullchain.pem').is_symlink())
            self.assertFalse((self.root/'root/cert/reality.example.com').exists())
        cfg=ConfigObj(str(self.root/'etc/letsencrypt/renewal/example.com.conf'))
        cfg['renewalparams']['authenticator']='standalone';cfg.write()
        result=self.run_functions(names,'get_ssl_certs',mock=MOCK+certbot,AUTODOMAIN='n',TEMPLATE=str(template),FAIL_CERT='certbot')
        self.assertNotEqual(result.returncode,0)
        for state in ('numbered', 'incomplete', 'wrong-identity'):
            with self.subTest(state=state):
                shutil.rmtree(self.root/'etc/letsencrypt')
                self.calls.unlink(missing_ok=True)
                if state == 'numbered':
                    (self.root/'etc/letsencrypt/live/example.com-0001').mkdir(parents=True)
                elif state == 'incomplete':
                    (self.root/'etc/letsencrypt/live/example.com').mkdir(parents=True)
                else:
                    certificates(self.root)
                    shutil.copyfile(self.root/'etc/letsencrypt/live/reality.example.com/fullchain.pem',
                                    self.root/'etc/letsencrypt/live/example.com/fullchain.pem')
                result=self.run_functions(names,'get_ssl_certs',mock=MOCK+certbot,AUTODOMAIN='n',TEMPLATE=str(template))
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(self.calls.exists(), 'Ambiguous state must not request or reconfigure certificates')
        # No fallback and no nginx stop/port killing are possible in certificate issuance.
        self.assertNotRegex(function('get_ssl_certs'),r'--standalone|systemctl stop|fuser')
        self.assertNotIn('setup_cron()',INSTALLER)
        self.assertNotIn('check_cron()',INSTALLER)

    def test_deploy_hook_decision_matrix_and_fail_closed_order(self):
        hook=certificates(self.root)
        nginx=['systemctl is-active --quiet nginx','nginx -t','systemctl reload nginx','systemctl is-active --quiet nginx']
        panel=nginx+['systemctl is-active --quiet x-ui','systemctl try-restart x-ui','systemctl is-active --quiet x-ui']
        scenarios=(('unrelated.example','unrelated.example',[],''),
                   ('example.com','unrelated.example',[],''),
                   ('','example.com',panel,''),
                   ('reality.example.com','reality.example.com',nginx,''),
                   ('example.com','example.com',panel,''),
                   ('example.com additional.example','example.com',panel,''),
                   ('example.com','example.com',nginx[:2],'nginx'),
                   ('example.com','example.com',nginx[:3],'reload nginx'),
                   ('example.com','example.com',panel[:-1],'try-restart x-ui'),
                   ('example.com','example.com',nginx,'post nginx'),
                   ('example.com','example.com',panel,'post x-ui'))
        for domains,lineage,expected,failure in scenarios:
            result,calls=self.deploy(hook, RENEWED_DOMAINS=domains,
                RENEWED_LINEAGE=str(self.root/'etc/letsencrypt/live'/lineage),FAIL_DEPLOY=failure)
            self.assertEqual(result.returncode,1 if failure else 0,result.stderr)
            self.assertEqual(calls,expected)
        self.assertEqual(hook.stat().st_mode & 0o777,0o755)
        if os.geteuid()==0: self.assertEqual((hook.stat().st_uid,hook.stat().st_gid),(0,0))

    def test_renewal_gate_rejects_broken_timer_hook_config_cron_and_acme(self):
        for mapped in (False,True):
            certificates(self.root,mapped=mapped)
            result=self.run_functions(RENEWAL,'check_certificate_renewal "$domain" "$reality_domain"')
            self.assertEqual(result.returncode,0,result.stderr)
        for failure in ('is-enabled --quiet certbot.timer','is-active --quiet certbot.timer','nginx','acme','owner'):
            certificates(self.root)
            self.calls.unlink(missing_ok=True)
            result=self.run_functions(RENEWAL,'check_certificate_renewal "$domain" "$reality_domain"',FAIL_CERT=failure)
            self.assertNotEqual(result.returncode,0,failure)
            self.assertEqual(list((self.root/'var/www/acme/.well-known/acme-challenge').iterdir()),[])
        for key,value in (('authenticator','standalone'),('webroot_path',['/wrong']),('pre_hook','systemctl stop nginx')):
            certificates(self.root,mapped=False)
            cfg=ConfigObj(str(self.root/'etc/letsencrypt/renewal/example.com.conf'))
            cfg['renewalparams'][key]=value;cfg.write()
            result=self.run_functions(RENEWAL,'check_certificate_renewal "$domain" "$reality_domain"')
            self.assertNotEqual(result.returncode,0)
        certificates(self.root)
        cfg=ConfigObj(str(self.root/'etc/letsencrypt/renewal/example.com.conf'))
        cfg['renewalparams']['webroot_map']['example.com']='/wrong';cfg.write()
        result=self.run_functions(RENEWAL,'check_certificate_renewal "$domain" "$reality_domain"')
        self.assertNotEqual(result.returncode,0)
        certificates(self.root)
        hook=self.root/'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'
        for change in ('mode','syntax','missing'):
            certificates(self.root)
            if change=='mode':hook.chmod(0o644)
            if change=='syntax':hook.write_text('if broken')
            if change=='missing':hook.unlink()
            result=self.run_functions(RENEWAL,'check_certificate_renewal "$domain" "$reality_domain"')
            self.assertNotEqual(result.returncode,0)
        certificates(self.root)
        (self.root/'cron').write_text(LEGACY+'\n')
        result=self.run_functions(RENEWAL,'check_certificate_renewal "$domain" "$reality_domain"')
        self.assertNotEqual(result.returncode,0)

    def test_setup_renewal_enables_vendor_timer_and_validates_chain(self):
        certificates(self.root)
        result=self.run_functions((*RENEWAL,'remove_legacy_certbot_cron','setup_certificate_renewal'),
                                  'setup_certificate_renewal')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('systemctl enable --now certbot.timer',self.calls.read_text())
        main=function('main')
        self.assertLess(main.index('confirm_destructive_reinstall'),main.index('clean_previous_install'))
        self.assertLess(main.index('setup_acme_http'),main.index('get_ssl_certs'))
        self.assertIn('check_certificate_renewal',function('check_installation'))
        self.assertIn('Webroot + systemd timer',function('show_results'))

    def test_real_nginx_acme_precedence_self_test_and_redirect(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        if not nginx:self.skipTest('nginx binary not available')
        from test_personal_xhttp import render
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        self.root.chmod(0o755)
        fragment=render('cat > /etc/nginx/sites-available/80.conf')
        fragment=fragment.replace('listen 80;',f'listen 127.0.0.1:{port};').replace('    listen [::]:80;\n','')
        fragment=fragment.replace('/var/www/acme',str(self.root/'var/www/acme'))
        (self.root/'var/www/acme/.well-known/acme-challenge').mkdir(parents=True)
        temp_paths='\n'.join(f'{kind}_temp_path {self.root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        conf=self.root/'nginx.conf';conf.write_text(f'pid {self.root}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{ access_log off;\n{temp_paths}\n{fragment}\n}}\n')
        command=[nginx,'-e','stderr','-p',str(self.root)+'/', '-c',str(conf)]
        syntax=subprocess.run([*command,'-t'],text=True,capture_output=True)
        self.assertEqual(syntax.returncode,0,syntax.stderr)
        proc=subprocess.Popen([*command,'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            import time
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=0.1):break
                except OSError:time.sleep(0.02)
            script=relocate(function('check_acme_http'),self.root).replace('http://127.0.0.1/',f'http://127.0.0.1:{port}/')
            result=subprocess.run(['bash','-eu','-c',script+'\ncheck_acme_http deploy.example cover.example'],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(list((self.root/'var/www/acme/.well-known/acme-challenge').iterdir()),[])
        finally:
            proc.terminate();proc.communicate(timeout=5)


if __name__=='__main__':unittest.main(verbosity=2)
