"""AGH snapshot/restore coverage reuses the existing private Backup fixtures."""
import copy
import io
import json
import os
from pathlib import Path
import tarfile
import unittest
from certificate_fixtures import relocate
from test_adguard import BINARY, HELPER, OFFICIAL_AMD64_SHA, FIXTURE_BINARY_SHA


# Exact pre-ClientID project snippet; preflight never executes archive helpers.
LEGACY_SNIPPET = r'''agh_snippet() {
    cat <<EOFNG
# Integrated AdGuard Home (project-owned).
location = /dns-query {
    limit_except GET POST { deny all; }
    proxy_pass http://127.0.0.1:${AGH_WEB_PORT};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_buffering off;
    proxy_intercept_errors off;
    access_log off;
}
location = /${AGH_PATH} { return 302 /${AGH_PATH}/; }
location ^~ /${AGH_PATH}/ {
    proxy_pass http://127.0.0.1:${AGH_WEB_PORT}/;
    proxy_redirect / /${AGH_PATH}/;
    proxy_cookie_path / /${AGH_PATH}/;
    proxy_cookie_flags agh_session secure;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_intercept_errors off;
    add_header X-Robots-Tag "noindex, nofollow" always;
}
EOFNG
}'''

class AdGuardBackup(unittest.TestCase):
    def setUp(self):
        # Instantiate the fixture, without inheriting/rerunning its 22 tests.
        from test_personal_backup import PersonalBackup
        self.fixture=PersonalBackup('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.fixture.env.update(ROOT=str(self.root), CALLS=str(self.root/'binary-calls'))
        # Private trusted fixture digest; actual sha256sum remains unstubbed.
        self.fixture.script.write_text(self.fixture.script.read_text().replace(OFFICIAL_AMD64_SHA, FIXTURE_BINARY_SHA))

    def install_fixture(self, active=True, legacy=False):
        f=self.fixture
        f.write('/opt/AdGuardHome/AdGuardHome',BINARY,0o755)
        f.write('/opt/AdGuardHome/AdGuardHome.yaml', '''http:
  address: 127.0.0.1:18081
  doh:
    insecure_enabled: true
    routes:
      - GET /dns-query
      - POST /dns-query
users:
  - name: admin
    password: '$2y$12$00000000000000000000000000000000000000000000000000000'
dns:
  bind_hosts:
    - 127.0.0.1
  port: 18082
tls:
  enabled: false
schema_version: 34
''',0o600)
        f.write('/opt/AdGuardHome/managed.json',json.dumps(dict(version='v0.107.79',arch='amd64',domain='example.com',path='adg-ABCDEFGHIJKL',web_port=18081,dns_port=18082)),0o600)
        f.write('/opt/AdGuardHome/data/querylog.json','persistent query state')
        start=HELPER.index('agh_snippet() {')
        end=HELPER.index('\nEOFNG\n}',start)+len('\nEOFNG\n}')
        helper=HELPER[:start]+LEGACY_SNIPPET+HELPER[end:] if legacy else HELPER
        if not legacy:
            yaml=f.path('/opt/AdGuardHome/AdGuardHome.yaml')
            yaml.write_text(yaml.read_text().replace('      - POST /dns-query\n',
                '      - POST /dns-query\n      - GET /dns-query/{ClientID}\n      - POST /dns-query/{ClientID}\n'))
        f.write('/usr/local/lib/3x-ui-pro/managed-adguard.sh',relocate(helper,self.root).replace(OFFICIAL_AMD64_SHA, FIXTURE_BINARY_SHA),0o600)
        # Generate the exact snippet from the same managed helper.
        import subprocess
        r=subprocess.run(['bash','-c','source "$1"; AGH_WEB_PORT=18081; AGH_PATH=adg-ABCDEFGHIJKL; agh_snippet','fixture',str(f.path('/usr/local/lib/3x-ui-pro/managed-adguard.sh'))],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        f.write('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf',r.stdout,0o600)
        f.write('/etc/systemd/system/AdGuardHome.service',f'ExecStart={self.root}/opt/AdGuardHome/AdGuardHome -c {self.root}/opt/AdGuardHome/AdGuardHome.yaml -w {self.root}/opt/AdGuardHome -s run --no-check-update\n')
        services=json.loads((self.root/'services.json').read_text());services['AdGuardHome']='active' if active else 'inactive';(self.root/'services.json').write_text(json.dumps(services))
        enabled=json.loads((self.root/'enabled.json').read_text());enabled['AdGuardHome']=True;(self.root/'enabled.json').write_text(json.dumps(enabled))

    def test_legacy_and_clientid_archives_restore_without_upgrading_state(self):
        import hashlib
        f=self.fixture
        for legacy in (False,True):
            with self.subTest(legacy=legacy):
                self.install_fixture(legacy=legacy)
                snippet=f.path('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf')
                saved={path:path.read_bytes() for path in (snippet,
                    f.path('/opt/AdGuardHome/AdGuardHome.yaml'),
                    f.path('/usr/local/lib/3x-ui-pro/managed-adguard.sh'))}
                if not legacy:self.assertIn(b'location ~',saved[snippet])
                archive=f.backup();digest=hashlib.sha256(archive.read_bytes()).digest()
                for _ in range(2):
                    result=f.run_tool('restore',archive)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual({path:path.read_bytes() for path in saved},saved)
                    self.assertEqual(hashlib.sha256(archive.read_bytes()).digest(),digest)
                archive.unlink()

    def test_absent_metadata_and_restore_remove_target_adguard(self):
        f=self.fixture;archive=f.backup()
        with tarfile.open(archive) as tar:
            self.assertIs(json.load(tar.extractfile('meta.json'))['adguard_home'],False)
            self.assertFalse(any('/opt/AdGuardHome' in m.name for m in tar))
        self.install_fixture()
        r=f.run_tool('restore',archive)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertFalse(f.path('/opt/AdGuardHome').exists())
        self.assertFalse(f.path('/etc/systemd/system/AdGuardHome.service').exists())
        self.assertFalse(f.path('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf').exists())
        self.assertNotIn('binary -c', (self.root/'binary-calls').read_text() if (self.root/'binary-calls').exists() else '')

    def test_stopped_adguard_restore_never_starts_it_and_preserves_data(self):
        f=self.fixture;self.install_fixture(active=False)
        enabled=json.loads((self.root/'enabled.json').read_text());enabled['AdGuardHome']=False
        (self.root/'enabled.json').write_text(json.dumps(enabled))
        archive=f.backup();original=archive.read_bytes()
        for _ in range(2):
            states=json.loads((self.root/'services.json').read_text());states['AdGuardHome']='active'
            (self.root/'services.json').write_text(json.dumps(states))
            (self.root/'commands').write_text('');(self.root/'binary-calls').write_text('')
            result=f.run_tool('restore',archive)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads((self.root/'services.json').read_text())['AdGuardHome'],'inactive')
            self.assertFalse(json.loads((self.root/'enabled.json').read_text())['AdGuardHome'])
            self.assertNotIn(['systemctl','start','AdGuardHome'],f.commands())
            self.assertNotIn(['systemctl','enable','--now','AdGuardHome'],f.commands())
            self.assertNotIn('-s install',(self.root/'binary-calls').read_text(),
                             'Official AGH -s install starts its service as a side effect')
            self.assertEqual(f.path('/opt/AdGuardHome/data/querylog.json').read_text(),'persistent query state')
            self.assertTrue(f.path('/etc/systemd/system/AdGuardHome.service').is_file())
            self.assertEqual(archive.read_bytes(),original)

    def test_present_snapshot_order_state_and_workdir(self):
        f=self.fixture
        for active in (True,False):
            self.install_fixture(active);(self.root/'commands').write_text('')
            archive=f.backup();calls=f.commands()
            collect=next(i for i,c in enumerate(calls) if c[:2]==['cp','-a'] and str(f.path('/opt/AdGuardHome')) in c)
            if active:
                self.assertLess(calls.index(['systemctl','stop','AdGuardHome']),collect)
                self.assertGreater(calls.index(['systemctl','start','AdGuardHome']),collect)
            else:self.assertNotIn(['systemctl','start','AdGuardHome'],calls)
            self.assertEqual(json.loads((self.root/'services.json').read_text())['AdGuardHome'],'active' if active else 'inactive')
            with tarfile.open(archive) as tar:
                meta=json.load(tar.extractfile('meta.json'))
                self.assertIs(meta['adguard_home'],True);self.assertEqual(meta['adguard_version'],'v0.107.79')
                self.assertEqual(meta['adguard_arch'],'amd64')
                self.assertIn('files/' + str(f.path('/opt/AdGuardHome/data/querylog.json')).lstrip('/'),tar.getnames())
                self.assertNotIn('files/' + str(f.path('/etc/systemd/system/AdGuardHome.service')).lstrip('/'),tar.getnames())
            archive.unlink()

    def test_backup_failure_recovers_adguard_and_certbot_timer(self):
        f=self.fixture;self.install_fixture()
        r=f.run_tool('backup',FAIL_AGH_COPY='1')
        self.assertNotEqual(r.returncode,0)
        self.assertNotIn('Backup completed successfully.',r.stdout)
        state=json.loads((self.root/'services.json').read_text())
        self.assertEqual(state['AdGuardHome'],'active');self.assertEqual(state['certbot.timer'],'active')
        self.assertFalse(list(f.path('/var/backups/x-ui').glob('*.tar.gz')))

    def test_partial_state_and_conditional_archive_validation(self):
        f=self.fixture
        f.write('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf','partial')
        r=f.run_tool('backup');self.assertNotEqual(r.returncode,0);self.assertNotIn('Backup completed successfully.',r.stdout)
        f.path('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf').unlink()
        archive=f.backup()
        file=tarfile.TarInfo('files/' + str(f.path('/opt/AdGuardHome/unexpected')).lstrip('/'));file.size=3
        bad=f.changed_archive(archive,extra=file)
        r=f.run_tool('restore',bad);self.assertNotEqual(r.returncode,0);self.assertIn('prohibited',r.stderr)
        bad=f.changed_archive(archive,metadata={'adguard_home':True,'adguard_version':'v0.107.79','adguard_arch':'amd64'})
        r=f.run_tool('restore',bad);self.assertNotEqual(r.returncode,0);self.assertIn('missing required',r.stderr)
        bad=f.changed_archive(archive,metadata={'adguard_home':'false'})
        r=f.run_tool('restore',bad);self.assertNotEqual(r.returncode,0);self.assertIn('boolean',r.stderr)

    def staged_archive(self, archive, replacements):
        target = self.root / 'staged-test.tar.gz'
        with tarfile.open(archive) as src, tarfile.open(target, 'w:gz') as dst:
            for original in src:
                item = copy.copy(original)
                data = src.extractfile(original).read() if original.isfile() else None
                if item.name in replacements:
                    data, mode = replacements[item.name]
                    if isinstance(data, str):
                        data = data.encode()
                    if mode is not None:
                        item.mode = mode
                if data is not None:
                    item.size = len(data)
                dst.addfile(item, io.BytesIO(data) if data is not None else None)
        return target

    def assert_staged_rejection_preserves_target(self, archive, replacements=None, **env):
        f = self.fixture
        # Poison only the archived shell helper: preflight must never source it.
        helper = f.path('/usr/local/lib/3x-ui-pro/managed-adguard.sh').read_text()
        replacements = dict(replacements or {})
        replacements[f.member('/usr/local/lib/3x-ui-pro/managed-adguard.sh')] = (
            'echo untrusted-helper >> "$ROOT/mutation-trace"\n' + helper, None)
        bad = self.staged_archive(archive, replacements)
        protected = ('/opt/AdGuardHome', '/etc/x-ui', '/etc/nginx', '/etc/letsencrypt')
        def snapshot():
            return {str(p): p.read_bytes() for directory in protected
                    for p in f.path(directory).rglob('*') if p.is_file()}
        before = snapshot()
        services = (self.root / 'services.json').read_bytes()
        enabled = (self.root / 'enabled.json').read_bytes()
        (self.root / 'commands').write_text('')
        r = f.run_tool('restore', bad, **env)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('Restore completed successfully.', r.stdout)
        self.assertFalse((self.root / 'mutation-trace').exists())
        self.assertEqual(snapshot(), before)
        self.assertEqual((self.root / 'services.json').read_bytes(), services)
        self.assertEqual((self.root / 'enabled.json').read_bytes(), enabled)
        self.assertTrue(f.path('/etc/systemd/system/AdGuardHome.service').exists())
        calls = f.commands()
        for service in ('AdGuardHome', 'nginx', 'x-ui', 'mtr-backend', 'certbot.timer'):
            self.assertNotIn(['systemctl', 'stop', service], calls)
        return r

    def trace_mutation_boundaries(self):
        # Execution trace, rather than only asserting source ordering.
        script = self.fixture.script.read_text()
        for name in ('pause_certbot_timer', 'cleanup_adguard', 'replace_managed_state'):
            script = script.replace(name + '() {', name + '() {\n    echo ' + name + ' >> "$ROOT/mutation-trace"')
        self.fixture.script.write_text(script)

    def test_staged_corrupt_config_is_rejected_before_target_mutation(self):
        f = self.fixture
        self.install_fixture()
        archive = f.backup()
        self.trace_mutation_boundaries()
        yaml = f.path('/opt/AdGuardHome/AdGuardHome.yaml').read_text()
        for config in (yaml.replace('schema_version: 34', 'schema_version: 33'),
                       yaml.replace('address: 127.0.0.1:', 'address: 0.0.0.0:'),
                       yaml + 'querylog:\n  dir_path: /tmp/external-querylog\n',
                       yaml + 'statistics:\n  dir_path: /tmp/external-statistics\n'):
            with self.subTest(config=config):
                self.assert_staged_rejection_preserves_target(archive, {
                    f.member('/opt/AdGuardHome/AdGuardHome.yaml'): (config, None)})
        self.assert_staged_rejection_preserves_target(archive, FAIL='config')

    def test_staged_wrong_binary_is_rejected_before_target_mutation(self):
        f = self.fixture
        self.install_fixture()
        archive = f.backup()
        self.trace_mutation_boundaries()
        self.assert_staged_rejection_preserves_target(archive, FAIL='version')
        for binary, mode in (('not an executable format', 0o755), (BINARY, 0o600)):
            with self.subTest(binary=binary, mode=mode):
                self.assert_staged_rejection_preserves_target(archive, {
                    f.member('/opt/AdGuardHome/AdGuardHome'): (binary, mode)})

    def test_staged_metadata_and_snippet_rejected_before_target_mutation(self):
        f = self.fixture
        self.install_fixture()
        archive = f.backup()
        self.trace_mutation_boundaries()
        metadata = json.loads(f.path('/opt/AdGuardHome/managed.json').read_text())
        for key, value in (('version', 'v0.107.78'), ('arch', 'arm64'), ('arch', 'invalid'),
                           ('domain', 'bad..example.com'), ('path', 'adg-bad'),
                           ('web_port', 443), ('dns_port', metadata['web_port'])):
            with self.subTest(key=key, value=value):
                self.assert_staged_rejection_preserves_target(archive, {
                    f.member('/opt/AdGuardHome/managed.json'): (json.dumps({**metadata, key: value}), None)})
        self.assert_staged_rejection_preserves_target(archive, {
            f.member('/opt/AdGuardHome/managed.json'): ('invalid JSON', None)})
        self.assert_staged_rejection_preserves_target(archive, {
            f.member('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf'): ('arbitrary nginx snippet', None)})
        snippet=f.path('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf').read_text()
        self.assert_staged_rejection_preserves_target(archive, {
            f.member('/etc/nginx/snippets/x-ui-auto-optional/adguard.conf'): (snippet.replace('^/dns-query/', '^/'), None)})

    def test_restore_uses_the_same_trusted_static_contract(self):
        from test_personal_backup import SOURCE
        def function(source, name):
            start = source.index(name + '() {')
            end = source.index('\nEOFNG\n}', start) + len('\nEOFNG\n}') if name == 'agh_snippet' else source.index('\n}\n', start) + 2
            return source[start:end]
        for name in ('agh_binary_hash', 'agh_verify_binary', 'agh_binary', 'agh_config', 'agh_snippet'):
            self.assertEqual(function(SOURCE, name), function(HELPER, name))
        start = SOURCE.index('preflight_staged_adguard()')
        preflight = SOURCE[start:SOURCE.index('\n)\n', start) + 2]
        self.assertNotIn('source ', preflight)
        self.assertNotIn('managed-adguard.sh', preflight)

    def test_optimized_staged_public_bind_and_low_ports_preserve_target(self):
        f = self.fixture
        self.install_fixture()
        archive = f.backup()
        self.trace_mutation_boundaries()
        yaml = f.path('/opt/AdGuardHome/AdGuardHome.yaml').read_text()
        metadata = json.loads(f.path('/opt/AdGuardHome/managed.json').read_text())
        variants = [
            {f.member('/opt/AdGuardHome/AdGuardHome.yaml'): (yaml.replace('address: 127.0.0.1:', 'address: 0.0.0.0:'), None)},
            {f.member('/opt/AdGuardHome/AdGuardHome.yaml'): (yaml.replace('    - 127.0.0.1\n', '    - 0.0.0.0\n'), None)},
        ]
        for key, value in (('web_port', 443), ('dns_port', 53)):
            variants.append({f.member('/opt/AdGuardHome/managed.json'): (json.dumps({**metadata, key: value}), None)})
        for invalid in variants:
            with self.subTest(invalid=invalid):
                r = self.assert_staged_rejection_preserves_target(archive, invalid, PYTHONOPTIMIZE='1')
                self.assertIn('configuration/binary contract is invalid', r.stderr)

    def test_staged_malicious_binary_is_not_executed_before_hash_check(self):
        f = self.fixture
        self.install_fixture()
        archive = f.backup()
        self.trace_mutation_boundaries()
        malicious = '#!/bin/bash\ntouch "$ROOT/binary-mutation"\necho "AdGuard Home, version v0.107.79"\n'
        for optimize in ('', '1'):
            with self.subTest(optimize=optimize):
                r = self.assert_staged_rejection_preserves_target(archive, {
                    f.member('/opt/AdGuardHome/AdGuardHome'): (malicious, 0o755)}, PYTHONOPTIMIZE=optimize)
                self.assertIn('executable SHA256 mismatch', r.stderr)
                self.assertFalse((self.root/'binary-mutation').exists())
        # No metadata/helper digest override is accepted by production restore code.
        from test_personal_backup import SOURCE
        start = SOURCE.index('preflight_staged_adguard()')
        preflight = SOURCE[start:SOURCE.index('\n)\n', start) + 2]
        self.assertLess(preflight.index('agh_verify_binary "$ARCH"'), preflight.index('agh_config'))

    def test_verified_fixture_restore_optimized_and_optional_directory_mode(self):
        f = self.fixture
        self.install_fixture()
        archive = f.backup()
        directory = f.path('/etc/nginx/snippets/x-ui-auto-optional')
        directory.chmod(0o700)
        self.trace_mutation_boundaries()
        r = f.run_tool('restore', archive, PYTHONOPTIMIZE='1')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('Restore completed successfully.', r.stdout)
        self.assertEqual((self.root/'mutation-trace').read_text().splitlines(),
                         ['pause_certbot_timer', 'cleanup_adguard', 'replace_managed_state'])
        self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
        self.assertEqual(directory.stat().st_uid, os.geteuid())
        if os.geteuid() == 0:
            self.assertEqual(directory.stat().st_gid, 0)
        else:
            self.assertIn(['install', '-d', '-o', 'root', '-g', 'root', '-m', '0755', str(directory)], f.commands())
        self.assertIn('--check-config', (self.root/'binary-calls').read_text())
        self.assertFalse(any(c[0] == 'curl' for c in f.commands()))

    def test_present_restore_recreates_service_and_requires_health(self):
        f=self.fixture;self.install_fixture();archive=f.backup()
        f.write('/opt/AdGuardHome/data/querylog.json','changed')
        (self.root/'commands').write_text('')
        r=f.run_tool('restore',archive)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('existing credentials preserved',r.stdout)
        self.assertEqual(f.path('/opt/AdGuardHome/data/querylog.json').read_text(),'persistent query state')
        self.assertTrue(f.path('/etc/systemd/system/AdGuardHome.service').exists())
        calls=f.commands()
        self.assertIn(['systemctl','enable','--now','AdGuardHome'],calls)
        self.assertFalse(any(c[0]=='curl' for c in calls))
        for fail in ({'FAIL':'version'},{'FAIL':'config'},{'FAIL':'service'},{'FAIL_HEALTH_SERVICE':'AdGuardHome'}):
            r=f.run_tool('restore',archive,**fail)
            self.assertNotEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertNotIn('Restore completed successfully.',r.stdout)


if __name__=='__main__':unittest.main(verbosity=2)
