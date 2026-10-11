"""Execute integrated AGH paths only on private fixtures; no live installation."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from certificate_fixtures import function, relocate

ROOT = Path(__file__).resolve().parents[1]
HELPER = (ROOT / 'assets/adguard/managed.sh').read_text()
OFFICIAL_AMD64_SHA = '7e247573e63ce771a5925d16ca4ca9344e6e888673244289dc302f0fdfdfbf4e'
INSTALLER = (ROOT / 'x-ui-latest.sh').read_text()

MOCK = r'''
msg_err() { echo "$*" >&2; }
msg_warn() { echo "$*"; }
msg_ok() { echo "$*"; }
msg_inf() { echo "$*"; }
check_installation() { echo core-health >> "$CALLS"; }
uname() { echo "${TEST_ARCH:-x86_64}"; }
apt-get() { echo "package $*" >> "$CALLS"; [[ "${FAIL:-}" != package ]]; }
chown() { :; }
install() {
    local -a args=()
    while (( $# )); do case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac; done
    command install "${args[@]}"
}
gen_random_string() {
    [[ "${FAIL:-}" != random-exit ]] || return 1
    [[ "${FAIL:-}" != path || "$1" != 12 ]] || { echo short; return; }
    [[ "${FAIL:-}" != random ]] || { echo short; return; }
    printf '%*s' "$1" '' | tr ' ' A
}
htpasswd() {
    echo "bcrypt $*" >> "$CALLS"
    [[ "$*" == '-niB -C 12 admin' ]] || return 1
    local pass; IFS= read -r pass
    [[ "$pass" == AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA && "${FAIL:-}" != bcrypt ]] || return 1
    printf 'admin:$2y$12$'; printf '%053d\n' 0
}
python3() {
    [[ "${FAIL:-}" != extraction || "$*" != *extracted* ]] || return 1
    command python3 "$@"
}
sha256sum() {
    [[ "${FAIL:-}" != checksum ]] || { echo wrong; return; }
    if [[ "$1" == *archive ]]; then
        echo "c48f4a43000665484c5ec28177de11a004759b620dae8f77b2aabefc9ef3687f  $1"
    else command sha256sum "$@"; fi
}
systemctl() {
    echo "systemctl $*" >> "$CALLS"
    local verb=$1 unit="${!#}"
    case "$verb" in
        cat) [[ -f "$ROOT/etc/systemd/system/AdGuardHome.service" ]] || return 1; cat "$ROOT/etc/systemd/system/AdGuardHome.service" ;;
        show)
            if [[ "$*" == *FragmentPath* ]]; then echo "$ROOT/etc/systemd/system/AdGuardHome.service";
            else echo 12345; fi ;;
        is-active) [[ -e "$ROOT/active" ]]; return $? ;;
        is-enabled) [[ -e "$ROOT/enabled" ]]; return $? ;;
        enable) [[ "${FAIL:-}" != start ]] || return 1; touch "$ROOT/enabled" "$ROOT/active" ;;
        stop) [[ "${FAIL:-}" != cleanup ]] || return 1; rm -f "$ROOT/active" ;;
        disable) rm -f "$ROOT/enabled" ;;
        reload)
            if [[ "${FAIL:-}" == reload && ! -e "$ROOT/reload-failed" ]]; then touch "$ROOT/reload-failed"; return 1; fi ;;
    esac
    return 0
}
nginx() {
    echo nginx-test >> "$CALLS"
    [[ "${FAIL:-}" != nginx || ! -e "$ROOT/etc/nginx/snippets/x-ui-auto-optional/adguard.conf" ]]
}
ss() {
    echo "tcp LISTEN 0 128 ${LISTEN_WEB:-127.0.0.1}:${AGH_WEB_PORT} 0.0.0.0:* users:((\"AdGuardHome\",pid=${LISTEN_PID:-12345},fd=5))"
    echo "${DNS_PROTOCOL:-udp} UNCONN 0 0 ${LISTEN_DNS:-127.0.0.1}:${AGH_DNS_PORT} 0.0.0.0:* users:((\"AdGuardHome\",pid=${LISTEN_PID:-12345},fd=6))"
}
curl() {
    echo "curl $*" >> "$CALLS"
    local arg prev='' output='' headers='' cookies='' session='' payload='' url="${!#}"
    for arg in "$@"; do
        [[ "$prev" != -o ]] || output=$arg
        [[ "$prev" != -D ]] || headers=$arg
        [[ "$prev" != -c ]] || cookies=$arg
        [[ "$prev" != -b ]] || session=$arg
        [[ "$prev" != --data-binary ]] || payload=${arg#@}
        prev=$arg
    done
    if [[ "$*" == *assets/adguard/managed.sh* ]]; then cp "$HELPER_FIXTURE" "$output"; return; fi
    if [[ "$*" == *AdGuardHome_linux_* ]]; then
        [[ "${FAIL:-}" != download ]] || return 1
        cp "$ARCHIVE_FIXTURE" "$output"; return
    fi
    if [[ "$url" == */control/login ]]; then
        [[ "${FAIL:-}" != login ]] || return 1
        [[ "$(stat -c '%a' "$payload")" == 600 && "$(stat -c '%a' "${payload%/*}")" == 700 ]] || return 1
        python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); sys.exit(0 if p == {"name":"admin","password":"A"*32} else 1)' "$payload" || return 1
        if [[ "${FAIL:-}" == login-status ]]; then printf 403; return; fi
        [[ "${FAIL:-}" != cookie ]] || { printf 200; return; }
        printf '# Netscape HTTP Cookie File\n%s\tFALSE\t/%s/\tTRUE\t9999999999\tagh_session\tfixture-session\n' "$domain" "$AGH_PATH" > "$cookies"
        [[ "${FAIL:-}" != cookie-insecure ]] || sed -i 's/\tTRUE\t/\tFALSE\t/' "$cookies"
        [[ "${FAIL:-}" != cookie-representation ]] || sed -i "s#${domain}#.${domain}#" "$cookies"
        printf 200; return
    fi
    if [[ "$url" == */control/status ]]; then
        [[ "${FAIL:-}" != auth-status ]] || return 1
        # Model the backend requiring a usable curl session, not cookie serialization fields.
        if [[ ! -s "$session" || "${FAIL:-}" == cookie-unusable || "${FAIL:-}" == auth-http ]]; then printf 401; return; fi
        if [[ "${FAIL:-}" == auth-json ]]; then printf invalid > "$output";
        elif [[ "${FAIL:-}" == auth-response ]]; then printf '{}' > "$output";
        else printf '{"version":"v0.107.79","running":true,"http_port":%s,"dns_port":%s}' "$AGH_WEB_PORT" "$AGH_DNS_PORT" > "$output"; fi
        printf 200; return
    fi
    if [[ "$url" == *login.html ]]; then
        [[ "${FAIL:-}" != admin ]] || return 1
        [[ "${FAIL:-}" != admin-body ]] || { echo '<html>unrelated cover page</html>'; return; }
        echo '<html><script src="login.fixture.js"></script></html>'; return
    fi
    if [[ "$url" == http:* ]]; then [[ "${FAIL:-}" != backend ]] || return 1;
    else [[ "${FAIL:-}" != public ]] || return 1; fi
    printf 'Content-Type: application/dns-message\r\n' > "$headers"
    printf '\000\000\200\000\000\001\000\001\000\000\000\000' > "$output"
    [[ "${FAIL:-}" != dns-body ]] || printf corrupt > "$output"
    [[ "${FAIL:-}" != dns-failed ]] || printf '\000\000\200\002\000\001\000\001\000\000\000\000' > "$output"
    printf 200
}
'''

BINARY = '''#!/bin/bash
echo "binary $*" >> "$CALLS"
if [[ "$*" == --version ]]; then
    [[ "${FAIL:-}" != version ]] || { echo wrong; exit; }
    echo 'AdGuard Home, version v0.107.79'
elif [[ "$*" == *--check-config* ]]; then
    [[ "${FAIL:-}" != config ]] || exit 1
elif [[ "$*" == *'-s install'* ]]; then
    [[ "${FAIL:-}" != service ]] || exit 1
    mkdir -p "$ROOT/etc/systemd/system"
    printf 'ExecStart=%s/opt/AdGuardHome/AdGuardHome -c %s/opt/AdGuardHome/AdGuardHome.yaml -w %s/opt/AdGuardHome -s run --no-check-update\\n' "$ROOT" "$ROOT" "$ROOT" > "$ROOT/etc/systemd/system/AdGuardHome.service"
    touch "$ROOT/active"
else exit 1; fi
'''


FIXTURE_BINARY_SHA = hashlib.sha256(BINARY.encode()).hexdigest()


class AdGuardInstaller(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agh-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.calls = self.root / 'calls'
        for directory in ('opt', 'usr/local/lib/3x-ui-pro', 'etc/nginx/snippets/x-ui-auto-optional'):
            (self.root / directory).mkdir(parents=True)
        self.helper = self.root / 'helper'
        # Change only the trusted expected digest in the private test copy, not sha256 execution.
        self.helper.write_text(relocate(HELPER, self.root).replace(OFFICIAL_AMD64_SHA, FIXTURE_BINARY_SHA))
        self.certificate_state = self.root / 'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'
        self.certificate_state.parent.mkdir(parents=True)
        self.certificate_state.write_bytes(b'frozen renewal hook fixture')
        self.archive = self.root / 'archive.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as tar:
            d = tarfile.TarInfo('./AdGuardHome'); d.type = tarfile.DIRTYPE; tar.addfile(d)
            f = tarfile.TarInfo('./AdGuardHome/AdGuardHome'); b = BINARY.encode(); f.size = len(b); f.mode = 0o755; tar.addfile(f, io.BytesIO(b))
        self.env = {**os.environ, 'ROOT': str(self.root), 'CALLS': str(self.calls), 'HELPER_FIXTURE': str(self.helper),
                    'ARCHIVE_FIXTURE': str(self.archive), 'GITHUB_RAW': 'https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/' + 'a' * 40,
                    'domain': 'example.com', 'INSTALL_AGH': 'n'}

    def run_shell(self, names, body, input=None, **env):
        if 'adguard_stage' in names:
            names = (*names, 'adguard_admin_probe')
        source = MOCK + '\n' + '\n'.join(relocate(function(n), self.root) for n in names)
        return subprocess.run(['bash', '-eu', '-c', source + '\n' + body], input=input, text=True,
                              capture_output=True, env={**self.env, **env})

    def test_prompt_default_yes_reprompt_and_arch_gate(self):
        for answer, expected in (('\n','n'),('n\n','n'),('N\n','n'),('','n'),('y\n','y'),('Y\n','y'),('bad\ny\n','y')):
            r = self.run_shell(('select_adguard',), 'select_adguard; echo selection=$INSTALL_AGH', input=answer)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('selection=' + expected, r.stdout)
            self.assertFalse(self.calls.exists())
        r = self.run_shell(('select_adguard',), 'select_adguard; echo destruction', input='y\n', TEST_ARCH='mips64')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('destruction', r.stdout)
        r = self.run_shell(('select_adguard',), 'select_adguard', input='n\n', TEST_ARCH='mips64')
        self.assertEqual(r.returncode, 0)
        main = function('main')
        self.assertLess(main.index('select_adguard'), main.index('clean_previous_install'))
        self.assertLess(main.index('check_installation'), main.index('install_adguard'))
        self.assertLess(main.index('install_adguard'), main.index('show_results'))

    def test_pinned_architecture_hashes(self):
        for arch in ('x86_64','amd64','aarch64','arm64'):
            r = subprocess.run(['bash','-eu','-c',HELPER+'\nagh_release "$TEST_ARCH"; echo "$AGH_ARCH $AGH_SHA"'],
                               text=True,capture_output=True,env={**os.environ,'TEST_ARCH':arch})
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertRegex(r.stdout,r'^(amd64|arm64) [0-9a-f]{64}\n$')
        self.assertNotIn('releases/latest', function('adguard_stage'))
        self.assertIn('tar.extractall', function('adguard_stage'))
        self.assertLess(function('adguard_stage').index('sha256sum'), function('adguard_stage').index('tar.extractall'))
        self.assertNotIn('AdGuardHome', function('setup_certificate_renewal'))

    def test_success_config_service_routes_and_password(self):
        r = self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'), 'install_adguard; echo "path=$AGH_PATH"')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        config = (self.root/'opt/AdGuardHome/AdGuardHome.yaml').read_text()
        self.assertIn('schema_version: 34',config)
        self.assertIn('insecure_enabled: true',config)
        self.assertIn('      - GET /dns-query\n      - POST /dns-query',config)
        self.assertNotIn('allow_unencrypted_doh',config)
        self.assertNotIn('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',config)
        m = json.loads((self.root/'opt/AdGuardHome/managed.json').read_text())
        self.assertNotEqual(m['web_port'],m['dns_port'])
        self.assertGreaterEqual(m['web_port'],10000);self.assertGreaterEqual(m['dns_port'],10000)
        self.assertEqual(m['path'],'adg-'+'A'*12)
        log = self.calls.read_text()
        self.assertNotIn('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',log)
        self.assertIn('bcrypt -niB -C 12 admin',log)
        self.assertIn(self.env['GITHUB_RAW'] + '/assets/adguard/managed.sh', log)
        self.assertLess(log.index('--check-config'),log.index('-s install'))
        self.assertIn('--no-check-update -s install',log)
        self.assertIn('--resolve example.com:443:127.0.0.1',log)
        snippet=(self.root/'etc/nginx/snippets/x-ui-auto-optional/adguard.conf').read_text()
        self.assertIn('location = /dns-query',snippet)
        self.assertIn('location ^~ /adg-'+'A'*12+'/',snippet)
        self.assertNotIn('$fwdport',snippet)
        self.assertNotIn('releases/latest',log)

    def test_failure_matrix_rolls_back_without_false_success(self):
        for failure in ('package','download','checksum','extraction','version','random','random-exit','path','bcrypt','config','service','start','nginx','reload','backend','public','admin','admin-body'):
            with self.subTest(failure=failure):
                self.calls.write_text(''); (self.root/'reload-failed').unlink(missing_ok=True)
                r=self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'),
                                 'install_adguard; echo Installation-Complete',FAIL=failure)
                self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
                self.assertNotIn('Installation-Complete',r.stdout)
                self.assertIn('Core 3x-ui stack remains operational.',r.stdout)
                self.assertFalse((self.root/'opt/AdGuardHome').exists())
                self.assertFalse((self.root/'etc/nginx/snippets/x-ui-auto-optional/adguard.conf').exists())
                self.assertFalse((self.root/'etc/systemd/system/AdGuardHome.service').exists())
                self.assertIn('core-health',self.calls.read_text())
                self.assertEqual(self.certificate_state.read_bytes(), b'frozen renewal hook fixture')
                self.assertNotRegex(self.calls.read_text(), r'systemctl (stop|disable) (x-ui|nginx|mtr-backend|certbot)')
                if failure=='nginx': self.assertNotIn('reload nginx',self.calls.read_text())
        for data in (b'corrupt',None):
            if data is not None:self.archive.write_bytes(data)
            else:
                with tarfile.open(self.archive,'w:gz') as tar:
                    f=tarfile.TarInfo('../escape');f.size=1;tar.addfile(f,io.BytesIO(b'x'))
            r=self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'),'install_adguard; echo Installation-Complete')
            self.assertNotEqual(r.returncode,0)
            self.assertFalse((self.root/'opt/AdGuardHome').exists())
            self.assertNotIn('binary ',self.calls.read_text().split('core-health')[-1])

    def test_cleanup_precedes_core_and_preserves_core_on_failure(self):
        main=function('main'); uninstall=function('uninstall_xui')
        self.assertLess(main.index('cleanup_adguard'),main.index('clean_previous_install'))
        self.assertLess(uninstall.index('cleanup_adguard'),uninstall.index('remove_legacy_certbot_cron'))
        r=self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'),'install_adguard')
        self.assertEqual(r.returncode,0,r.stderr)
        r=self.run_shell(('cleanup_adguard',),'cleanup_adguard; echo core-destruction',FAIL='cleanup')
        self.assertNotEqual(r.returncode,0);self.assertNotIn('core-destruction',r.stdout)
        r=self.run_shell(('cleanup_adguard',),'cleanup_adguard')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertFalse((self.root/'opt/AdGuardHome').exists())

    def test_core_first_and_opt_out_has_no_optional_installation(self):
        operations=('preflight_base_os','prepare_base_os','prepare_system_dns','finish_initial_reboot','select_security','select_vision','select_client','preflight_integrated_features','select_amneziawg','preflight_amneziawg','preflight_panel_release','confirm_destructive_reinstall','validate_domains','clean_previous_install','install_packages',
                    'setup_firewall','get_server_ip','setup_acme_http','get_ssl_certs','install_panel','configure_nginx',
                    'configure_xui_db','install_clash_sub','install_fake_site','install_diagnostics','tune_system',
                    'install_backup_tool','setup_certificate_renewal','check_installation','show_results')
        stubs='\n'.join(n+'() { echo '+n+' >> "$CALLS"; }' for n in operations)
        stubs+='\ninstall_adguard() { echo optional-AGH >> "$CALLS"; }\nx-ui() { :; }\n'
        for answer, expected in (('\n',False),('n\n',False),('N\n',False),('y\n',True),('Y\n',True)):
            self.calls.write_text('')
            r=self.run_shell(('select_adguard','cleanup_adguard','main'),stubs+'\nmain',input=answer)
            self.assertEqual(r.returncode,0,r.stderr)
            log=self.calls.read_text()
            self.assertEqual('optional-AGH' in log,expected)
            self.assertNotIn('apache2-utils',log)
            self.assertFalse((self.root/'opt/AdGuardHome').exists())
            self.assertFalse((self.root/'etc/nginx/snippets/x-ui-auto-optional/adguard.conf').exists())
            if expected:self.assertLess(log.index('check_installation'),log.index('optional-AGH'))

    def test_optional_summary_and_unit_contract(self):
        for choice in ('n','y'):
            r=self.run_shell(('show_results',), ('AGH_RESULT=installed; ' if choice=='y' else 'AGH_RESULT=not_requested; ') + 'AGH_PATH=adg-ABCDEFGHIJKL; AGH_PASSWORD=single-secret; panel_path=panel; config_username=user; config_password=panel-pass; reality_domain=cover.example; ufw() { echo "Status: active"; }; show_results',INSTALL_AGH=choice)
            self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual('AdGuard Home:' in r.stdout,choice=='y')
            self.assertEqual(r.stdout.count('single-secret'),1 if choice=='y' else 0)
            if choice=='y':self.assertIn('https://example.com/dns-query',r.stdout)
        r=self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'),'install_adguard')
        self.assertEqual(r.returncode,0,r.stderr)
        unit=self.root/'etc/systemd/system/AdGuardHome.service'
        unit.write_text(unit.read_text().replace('--no-check-update',''))
        r=subprocess.run(['bash','-c',MOCK+'\nsource "$HELPER_FIXTURE"; agh_unit'],text=True,capture_output=True,env=self.env)
        self.assertNotEqual(r.returncode,0)

    def test_optimization_preserves_archive_and_port_allocation_checks(self):
        original = self.archive.read_bytes()
        for kind in ('unexpected', 'symlink', 'duplicate', 'wrong-directory-type', 'missing-binary'):
            with self.subTest(kind=kind):
                with tarfile.open(self.archive, 'w:gz') as tar:
                    directory = tarfile.TarInfo('AdGuardHome')
                    directory.type = tarfile.REGTYPE if kind == 'wrong-directory-type' else tarfile.DIRTYPE
                    tar.addfile(directory, io.BytesIO(b'') if directory.isfile() else None)
                    binary = tarfile.TarInfo('AdGuardHome/AdGuardHome')
                    binary.mode = 0o755
                    binary.size = len(BINARY.encode())
                    if kind == 'symlink':
                        binary.type = tarfile.SYMTYPE; binary.linkname = '/tmp/escape'; binary.size = 0
                    if kind != 'missing-binary':
                        tar.addfile(binary, io.BytesIO(BINARY.encode()) if binary.isfile() else None)
                    if kind == 'duplicate': tar.addfile(binary, io.BytesIO(BINARY.encode()))
                    if kind == 'unexpected': tar.addfile(tarfile.TarInfo('AdGuardHome/unknown'))
                self.calls.write_text('')
                r = self.run_shell(('cleanup_adguard', 'adguard_stage', 'install_adguard'),
                                   'install_adguard; echo Installation-Complete', PYTHONOPTIMIZE='1')
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn('Installation-Complete', r.stdout)
                self.assertNotIn('binary ', self.calls.read_text())
                self.assertFalse((self.root/'opt/AdGuardHome').exists())
        self.archive.write_bytes(original)
        allocator = re.search(r"ports=\$\(python3 - <<'PY'\n(.*?)\nPY", function('adguard_stage'), re.S)[1]
        blocked = ('import socket\nclass Busy:\n def __init__(self,*args): pass\n'
                   ' def bind(self,*args): raise OSError("port busy")\n def close(self): pass\n'
                   'socket.socket=Busy\n')
        r = subprocess.run(['python3', '-c', blocked + allocator], capture_output=True, text=True,
                           env={**os.environ, 'PYTHONOPTIMIZE': '1'})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('allocation of two TCP/UDP ports', r.stderr)

    def test_optimization_preserves_config_unit_listener_and_dns_checks(self):
        r = self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'), 'install_adguard', PYTHONOPTIMIZE='1')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        yaml = self.root/'opt/AdGuardHome/AdGuardHome.yaml'
        metadata = self.root/'opt/AdGuardHome/managed.json'
        unit = self.root/'etc/systemd/system/AdGuardHome.service'
        original_yaml, original_meta, original_unit = yaml.read_text(), metadata.read_text(), unit.read_text()
        def call(operation, **env):
            return subprocess.run(['bash', '-eu', '-c', MOCK + '\nsource "$HELPER_FIXTURE"; ' + operation],
                                  env={**self.env, 'PYTHONOPTIMIZE': '1', **env}, capture_output=True, text=True)
        self.assertEqual(call('agh_health').returncode, 0)
        variants = [original_yaml.replace('address: 127.0.0.1:', 'address: 0.0.0.0:'),
                    original_yaml.replace('    - 127.0.0.1\n', '    - 0.0.0.0\n'),
                    original_yaml.replace('    - 127.0.0.1\n', '    - 127.0.0.2\n'),
                    original_yaml.replace('schema_version: 34', 'schema_version: 33'),
                    original_yaml.replace('  enabled: false', '  enabled: true'),
                    original_yaml.replace('insecure_enabled: true', 'insecure_enabled: false'),
                    original_yaml + 'querylog:\n  dir_path: /tmp/unmanaged\n']
        for invalid in variants:
            with self.subTest(config=invalid):
                yaml.write_text(invalid)
                self.assertNotEqual(call('agh_config').returncode, 0)
        yaml.write_text(original_yaml)
        m = json.loads(original_meta)
        for key, value in (('web_port', 443), ('dns_port', 53), ('dns_port', m['web_port']),
                           ('web_port', '18081'), ('version', 'bad'), ('arch', 'bad'),
                           ('path', 'bad'), ('domain', 'bad..domain')):
            with self.subTest(key=key, value=value):
                metadata.write_text(json.dumps({**m, key: value}))
                self.assertNotEqual(call('agh_config').returncode, 0)
        metadata.write_text('invalid JSON')
        self.assertNotEqual(call('agh_config').returncode, 0)
        metadata.write_text(original_meta)
        for invalid in (original_unit.replace('--no-check-update', ''),
                        original_unit.replace('-s run', '-s install'),
                        original_unit.replace(' -w ', ' --wrong-flag ')):
            with self.subTest(unit=invalid):
                unit.write_text(invalid)
                self.assertNotEqual(call('agh_unit').returncode, 0)
        unit.write_text(original_unit)
        for env in ({'LISTEN_WEB': '0.0.0.0'}, {'LISTEN_DNS': '0.0.0.0'}, {'LISTEN_DNS': '127.0.0.2'},
                    {'LISTEN_PID': '7777'}, {'DNS_PROTOCOL': 'tcp'}):
            self.assertNotEqual(call('agh_config && agh_listeners', **env).returncode, 0)
        for failure in ('dns-body', 'dns-failed'):
            self.assertNotEqual(call('agh_config && agh_doh_probe "http://127.0.0.1:$AGH_WEB_PORT/dns-query"', FAIL=failure).returncode, 0)

    def test_authenticated_admin_probe_rolls_back_and_cleans_private_secrets(self):
        for failure in ('', 'login', 'login-status', 'cookie', 'cookie-unusable',
                        'auth-status', 'auth-http', 'auth-json', 'auth-response'):
            with self.subTest(failure=failure):
                self.calls.write_text('')
                r = self.run_shell(('cleanup_adguard','adguard_stage','install_adguard'),
                                   'install_adguard; echo Installation-Complete', FAIL=failure, PYTHONOPTIMIZE='1')
                log = self.calls.read_text()
                self.assertNotIn('A'*32, log + r.stdout + r.stderr)
                self.assertIn('--resolve example.com:443:127.0.0.1', log)
                payload = re.search(r'--data-binary @([^ ]+)/login.json', log)[1]
                self.assertFalse(Path(payload).exists(), 'private login payload/cookies leaked')
                if failure:
                    self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertNotIn('Installation-Complete', r.stdout)
                    self.assertFalse((self.root/'opt/AdGuardHome').exists())
                    self.assertIn('Core 3x-ui stack remains operational.', r.stdout)
                else:
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertIn('/control/status', log)
                    self.assertIn(' -b ', log)
                    r = self.run_shell(('cleanup_adguard',), 'cleanup_adguard')
                    self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('AGH_PASSWORD', HELPER)
        self.assertNotIn('adguard_admin_probe', HELPER)

    def test_authenticated_admin_uses_curl_session_without_metadata_gate(self):
        probe = function('adguard_admin_probe')
        self.assertNotIn('Missing usable Secure AGH session cookie', probe)
        self.assertNotIn('Netscape', probe)
        self.assertNotIn('read_text().splitlines()', probe)
        # Representations rejected by the old parser can still yield authenticated status.
        # Secure/Path policy is independently enforced by the real nginx test below.
        for optimize in ('', '1'):
            for representation in ('cookie-representation', 'cookie-insecure'):
                with self.subTest(optimize=optimize, representation=representation):
                    self.calls.write_text('')
                    r = self.run_shell(('cleanup_adguard', 'adguard_stage', 'install_adguard'),
                                       'install_adguard; echo authenticated-success',
                                       FAIL=representation, PYTHONOPTIMIZE=optimize)
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertIn('authenticated-success', r.stdout)
                    log = self.calls.read_text()
                    self.assertIn('/control/status', log)
                    self.assertIn(' -b ', log)
                    self.assertNotIn('A'*32, log + r.stdout + r.stderr)
                    private = re.search(r'--data-binary @([^ ]+)/login.json', log)[1]
                    self.assertFalse(Path(private).exists())
                    self.assertEqual(self.run_shell(('cleanup_adguard',), 'cleanup_adguard').returncode, 0)

    def final_result(self, requested, failure='', unverified=False):
        # Exercise the actual main, optional install/rollback and summary on private state.
        operations = ('preflight_base_os','prepare_base_os','prepare_system_dns','finish_initial_reboot','select_security','select_vision','select_client','preflight_integrated_features','select_amneziawg','preflight_amneziawg','preflight_panel_release','confirm_destructive_reinstall', 'validate_domains', 'clean_previous_install',
                      'install_packages', 'setup_firewall', 'get_server_ip', 'setup_acme_http',
                      'get_ssl_certs', 'install_panel', 'configure_nginx', 'configure_xui_db',
                      'install_clash_sub', 'install_fake_site', 'install_diagnostics', 'tune_system',
                      'install_backup_tool', 'setup_certificate_renewal')
        stubs = '\n'.join(n + '() { :; }' for n in operations)
        for name in ('var/www/diagnostics/index.html', 'var/www/diagnostics/speedtest.js',
                     'var/www/diagnostics/speedtest_worker.js', 'usr/local/lib/3x-ui-pro/mtr-backend.py',
                     'usr/local/bin/x-ui-backup', 'etc/letsencrypt/live/example.com/fullchain.pem',
                     'etc/letsencrypt/live/example.com/privkey.pem', 'etc/letsencrypt/live/cover.example/fullchain.pem',
                     'etc/letsencrypt/live/cover.example/privkey.pem', 'root/cert/example.com/fullchain.pem',
                     'root/cert/example.com/privkey.pem'):
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
            path.chmod(0o755)
        body = stubs + r'''
select_adguard() { :; }
x-ui() { :; }
ufw() { echo 'Status: active'; }
CORE_CHECKS=0
check_installation() {
    CORE_CHECKS=$((CORE_CHECKS+1))
    echo "core-health $CORE_CHECKS" >> "$CALLS"
    [[ "$CORE_CHECKS" == 1 || "$UNVERIFIED" != 1 ]]
}
panel_path=panel
config_username=panel-user
config_password=generated-panel-secret
reality_domain=cover.example
main
'''
        return self.run_shell(('cleanup_adguard', 'adguard_stage', 'install_adguard', 'show_results', 'main'),
                              body, INSTALL_AGH='y' if requested else 'n', FAIL=failure,
                              UNVERIFIED='1' if unverified else '0', PYTHONOPTIMIZE='1')

    def assert_core_credentials(self, result):
        self.assertIn('3x-ui Auto Nginx — Installation Result', result.stdout)
        self.assertIn('https://example.com/panel/', result.stdout)
        self.assertIn('Username: panel-user', result.stdout)
        self.assertEqual(result.stdout.count('Password: generated-panel-secret'), 1)
        self.assertIn('Save these credentials', result.stdout)
        self.assertIn('core-health 1', self.calls.read_text())

    def test_final_result_agh_success_keeps_both_credentials(self):
        r = self.final_result(True)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assert_core_credentials(r)
        self.assertIn('[✓] AdGuard Home           Running (v0.107.79)', r.stdout)
        self.assertIn('[✓] DNS-over-HTTPS         Ready', r.stdout)
        self.assertIn('AdGuard Home: https://example.com/adg-'+'A'*12+'/', r.stdout)
        self.assertEqual(r.stdout.count('Password: '+'A'*32), 1)
        self.assertNotIn('A'*32, self.calls.read_text())

    def test_final_result_opt_out_keeps_only_core_credentials(self):
        r = self.final_result(False)
        self.assertEqual(r.returncode, 0, r.stdout+r.stderr)
        self.assert_core_credentials(r)
        self.assertNotIn('AdGuard Home:', r.stdout)
        self.assertNotIn('Login: admin', r.stdout)
        self.assertNotIn('A'*32, r.stdout)
        self.assertNotIn('control/login', self.calls.read_text())

    def test_final_result_verified_rollback_keeps_core_credentials_and_fails(self):
        r = self.final_result(True, 'cookie-unusable')
        self.assertEqual(r.returncode, 1, r.stdout+r.stderr)
        self.assert_core_credentials(r)
        self.assertIn('[✓] 3x-ui / Xray           Running', r.stdout)
        self.assertIn('[!] AdGuard Home           Failed — rolled back', r.stdout)
        self.assertIn('[!] DNS-over-HTTPS         Not installed', r.stdout)
        self.assertIn('The core 3x-ui stack remains operational.', r.stdout)
        self.assert_no_agh_credentials_or_success(r)
        self.assertIn('core-health 2', self.calls.read_text())
        self.assertFalse((self.root/'opt/AdGuardHome').exists())

    def test_final_result_unverified_rollback_keeps_credentials_without_false_health(self):
        r = self.final_result(True, 'auth-http', unverified=True)
        self.assertEqual(r.returncode, 1, r.stdout+r.stderr)
        self.assert_core_credentials(r)
        self.assertIn('Post-rollback core health could not be verified.', r.stdout)
        self.assertIn('[!] AdGuard Home           Failed — rollback not verified', r.stdout)
        for label in ('3x-ui / Xray', 'nginx', 'XHTTP', 'Diagnostics', 'Certificate renewal'):
            line = next(l for l in r.stdout.splitlines() if label in l and '[!]' in l)
            self.assertIn('Post-rollback health not verified', line)
            self.assertNotIn('[✓] '+label, r.stdout)
        self.assert_no_agh_credentials_or_success(r)
        self.assertIn('core-health 2', self.calls.read_text())

    def assert_no_agh_credentials_or_success(self, result):
        self.assertNotIn('AdGuard Home: https://', result.stdout)
        self.assertNotIn('Login: admin', result.stdout)
        self.assertNotIn('A'*32, result.stdout + result.stderr + self.calls.read_text())
        self.assertNotIn('[✓] AdGuard Home', result.stdout)
        self.assertNotIn('[✓] DNS-over-HTTPS', result.stdout)

    def test_production_python_has_no_assert_and_optional_directory_is_owned(self):
        import ast
        for name in ('x-ui-latest.sh', 'assets/adguard/managed.sh', 'assets/backup/x-ui-backup.sh'):
            source = (ROOT/name).read_text()
            for code in re.findall(r"<<'PY'\n(.*?)^PY$", source, re.M | re.S):
                self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(code))), name)
        self.assertIn('install -d -o root -g root -m 0755', function('configure_nginx'))
        self.assertNotIn('mkdir -p /etc/nginx/snippets/x-ui-auto-optional', INSTALLER)
        # Execute the actual directory-creation line under a restrictive umask.
        directory = self.root/'etc/nginx/snippets/x-ui-auto-optional'
        directory.chmod(0o700)
        line = next(l.strip() for l in function('configure_nginx').splitlines() if 'install -d' in l and 'x-ui-auto-optional' in l)
        r = self.run_shell((), 'umask 077; ' + relocate(line, self.root))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o755)

    def test_real_nginx_optional_include_and_exact_routes(self):
        nginx=os.environ.get('NGINX_BIN') or shutil.which('nginx')
        self.assertTrue(nginx, 'Real nginx is required')
        hits=[]
        random_id='client-'+os.urandom(6).hex()
        class Backend(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(('GET',self.path));self.send_response(200);self.end_headers();self.wfile.write(b'backend')
            def do_POST(self):
                hits.append(('POST',self.path));self.send_response(200)
                self.send_header('Set-Cookie', 'agh_session=fixture; Path=/; HttpOnly; SameSite=Lax')
                self.end_headers();self.wfile.write(b'backend')
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Backend)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        optional=self.root/'optional';optional.mkdir()
        self.root.chmod(0o755)
        config=self.root/'nginx.conf'
        paths='\n'.join(f'{kind}_temp_path {self.root}/{kind};' for kind in ('client_body','proxy','fastcgi','uwsgi','scgi'))
        config.write_text(f'pid {self.root}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{ access_log off;\n{paths}\nserver {{ listen 127.0.0.1:{port}; include {optional}/*.conf; location / {{ return 404; }} }} }}')
        cmd=[nginx,'-p',str(self.root)+'/', '-c',str(config)]
        for enabled in (False,True):
            if enabled:
                r=subprocess.run(['bash','-c',HELPER+'\nAGH_WEB_PORT=$PORT; AGH_PATH=adg-ABCDEFGHIJKL; agh_snippet'],
                                 capture_output=True,text=True,env={**os.environ,'PORT':str(server.server_port)})
                (optional/'adguard.conf').write_text(r.stdout)
            checked=subprocess.run(cmd+['-t'],capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)
            subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                positive=('/dns-query','/dns-query/my-client?dns=fixture&extra=1',
                          '/dns-query/'+random_id+'?dns=fixture', '/dns-query/extra',
                          '/dns-query/A', '/dns-query/'+'a'*63)
                cases=[(path,method,200 if enabled else 404) for path in positive for method in ('GET','POST')]
                invalid=('/dns-query/', '/dns-query/client/extra', '/dns-query/my-client/',
                         '/dns-query/-bad', '/dns-query/bad-', '/dns-query/bad_id',
                         '/dns-query/bad.id', '/dns-query/'+'a'*64,
                         '/dns-query/adg-ABCDEFGHIJKL/control/status', '/dns-query/panel/api',
                         '/3000/test','/9090/api')
                cases += [(path,'GET',404) for path in invalid]
                cases += [('/adg-ABCDEFGHIJKL/control/status','GET',200 if enabled else 404)]
                cases += [(path,method,403 if enabled else 404) for path in positive for method in ('DELETE','PUT')]
                for path,method,status in cases:
                    before=len(hits)
                    url=f'http://127.0.0.1:{port}{path}'
                    r=subprocess.run(['curl','--noproxy','*','-s','-o','/dev/null','-w','%{http_code}','-X',method,url],text=True,capture_output=True)
                    self.assertEqual(r.stdout,str(status),(path,method,r.stderr))
                    if status==200:
                        expected='/control/status' if path.startswith('/adg-') else path
                        self.assertEqual(hits[before:],[(method,expected)])
                    else:self.assertEqual(len(hits),before,(path,method))
                if enabled:
                    response = subprocess.run(['curl', '--noproxy', '*', '-fsS', '-D', '-', '-o', '/dev/null',
                                               '-X', 'POST', f'http://127.0.0.1:{port}/adg-ABCDEFGHIJKL/control/login'],
                                              text=True, capture_output=True)
                    self.assertEqual(response.returncode, 0, response.stderr)
                    cookie = next(line for line in response.stdout.splitlines() if line.lower().startswith('set-cookie:'))
                    parts = [part.strip() for part in cookie.split(':', 1)[1].split(';')]
                    self.assertIn('agh_session=fixture', parts)
                    self.assertIn('Path=/adg-ABCDEFGHIJKL/', parts)
                    self.assertIn('secure', [part.lower() for part in parts])
                    self.assertIn('httponly', [part.lower() for part in parts])
                    self.assertIn('samesite=lax', [part.lower() for part in parts])
                    # The Secure policy is local to the admin prefix, not DoH.
                    doh = subprocess.run(['curl', '--noproxy', '*', '-fsS', '-D', '-', '-o', '/dev/null',
                                          '-X', 'POST', f'http://127.0.0.1:{port}/dns-query'],
                                         text=True, capture_output=True)
                    self.assertEqual(doh.returncode, 0, doh.stderr)
                    doh_cookie = next(line for line in doh.stdout.splitlines() if line.lower().startswith('set-cookie:'))
                    self.assertNotIn('secure', [part.strip().lower() for part in doh_cookie.split(';')[1:]])
                    self.assertIn(('POST','/control/login'),hits)
                    self.assertIn(('GET','/dns-query'),hits);self.assertIn(('POST','/dns-query'),hits)
                    self.assertIn(('GET','/control/status'),hits)
                    self.assertFalse(any(p in invalid for _,p in hits))
                else:self.assertEqual(hits,[])
            finally:
                subprocess.run(cmd+['-s','quit'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
                # Wait for pid removal before starting the next isolated instance.
                import time
                for _ in range(50):
                    if not (self.root/'nginx.pid').exists():break
                    time.sleep(.02)


if __name__=='__main__':unittest.main(verbosity=2)
