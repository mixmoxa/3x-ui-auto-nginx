"""Real Git histories exercise the docs exception and private Fresh diagnostics."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]


def png(rgb=b'\xff\xff\xff'):
    def chunk(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            +chunk(b'IDAT', zlib.compress(b'\0'+rgb))+chunk(b'IEND', b''))


class CIScope(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Proms')
        self.git('config', 'user.email', '102687702+xPROMSx@users.noreply.github.com')
        self.write('README.md', '# Example\n')
        self.write('docs/SUPPORT.md', '# Support\n')
        self.write('assets/support/qr.png', png())
        self.write('x-ui-latest.sh', '#!/bin/bash\ntrue\n')
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, stderr=subprocess.PIPE).decode().strip()

    def write(self, name, data):
        path = self.repo/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'synthetic fixture', '--allow-empty')
        return self.git('rev-parse', 'HEAD')

    def check(self, event='pull_request', base=None, head=None):
        head = head or self.git('rev-parse', 'HEAD')
        event_data = {'pull_request': {'base': {'sha': base or self.base}, 'head': {'sha': head}},
                      'before': base or self.base, 'after': head}
        path = Path(self.temp.name).parent/(Path(self.temp.name).name+'-event.json')
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(json.dumps(event_data))
        return subprocess.run(['python3', str(ROOT/'tests/ci_scope.py')], cwd=self.repo,
            env={**os.environ, 'GITHUB_EVENT_NAME': event, 'GITHUB_EVENT_PATH': str(path),
                 'GITHUB_SHA': head, 'GITHUB_OUTPUT': os.devnull, 'GITHUB_STEP_SUMMARY': os.devnull},
            capture_output=True, text=True, timeout=20)

    def assert_mode(self, result, mode):
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('CI MODE: '+mode, result.stdout)

    def test_documentation_histories_and_push(self):
        cases = [('README.md', '# Revised\n'), ('docs/SUPPORT.md', '# Donate\n'),
                 ('assets/support/qr.png', png(b'\0\0\0')), ('README_EN.md', '# English\n')]
        for name, data in cases:
            with self.subTest(name=name):
                self.git('reset', '--hard', self.base)
                self.write(name, data if name.endswith('.md') else data+b'')
                self.commit()
                self.assert_mode(self.check(), 'docs-only')
                self.assert_mode(self.check('push'), 'docs-only')
        self.write('docs/guide.md', '![QR](../assets/support/qr.png)\n[RU](../README.md)\n')
        self.write('README_AR.md', '# العربية\n')
        self.write('README_EN.md', '# English updated\n')
        self.commit()
        self.assert_mode(self.check(), 'docs-only')
        summary = subprocess.check_output(['python3', str(ROOT/'tests/ci_scope.py'), '--summary'],
            env={**os.environ, 'CI_DOCS_ONLY':'true', 'CI_FRESH':'true', 'CI_JOB_STATUS':'success',
                 'GITHUB_STEP_SUMMARY':os.devnull}, text=True)
        self.assertEqual(summary.strip(), 'DOCS-ONLY: Full Fresh E2E not executed; documentation scope verified.')
        self.assertNotIn('Full Fresh PASS', summary)

    def test_mixed_and_unknown_files_require_full(self):
        for path in ('x-ui-latest.sh', 'assets/helper.py', 'tests/test_fixture.py',
                     '.github/workflows/example.yml', 'AGENTS.md', 'CLAUDE.md', 'CONTRIBUTING.md',
                     'SECURITY.md', 'LICENSE', 'unknown.md', 'docs/run.sh', 'docs/data.yaml',
                     'assets/support/logo.svg', 'assets/support/file.bin', 'tests/ci_scope.py'):
            with self.subTest(path=path):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                self.write('README.md', '# Changed\n'); self.write(path, 'changed\n'); self.commit()
                self.assert_mode(self.check(), 'full')

    def test_rename_symlink_and_executable_are_not_docs(self):
        self.git('mv', 'x-ui-latest.sh', 'docs/install.md'); self.commit()
        self.assert_mode(self.check(), 'full')
        self.git('reset', '--hard', self.base)
        self.git('mv', 'README.md', 'installer.sh'); self.commit()
        self.assert_mode(self.check(), 'full')
        self.git('reset', '--hard', self.base)
        (self.repo/'README.md').unlink(); (self.repo/'README.md').symlink_to('/etc/passwd'); self.commit()
        self.assert_mode(self.check(), 'full')
        self.git('reset', '--hard', self.base)
        (self.repo/'README.md').chmod(0o755); self.commit()
        self.assert_mode(self.check(), 'full')

    def test_unreliable_diff_and_dispatch_are_full(self):
        self.assert_mode(self.check(), 'full')
        self.write('README.md', '# Change\n'); self.commit()
        for event, base in (('workflow_dispatch', self.base), ('pull_request', 'bad'),
                            ('pull_request', 'f'*40), ('push', '0'*40)):
            with self.subTest(event=event, base=base):
                self.assert_mode(self.check(event, base=base), 'full')
        spec = importlib.util.spec_from_file_location('scope', ROOT/'tests/ci_scope.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with self.assertRaises(ValueError): module.changed_paths(b'X\0README.md\0')
        with self.assertRaises(ValueError): module.changed_paths(b'R100\0old.md\0README.md\0')

    def test_whole_history_copy_ambiguity_and_real_main_merge(self):
        self.write('x-ui-latest.sh', '#!/bin/bash\nfalse\n'); self.commit()
        self.write('README.md', '# Last commit is documentation\n'); self.commit()
        self.assert_mode(self.check(), 'full')
        self.git('reset', '--hard', self.base)
        self.write('docs/copied.md', (self.repo/'README.md').read_bytes()); self.commit()
        self.assert_mode(self.check(), 'full')
        self.git('reset', '--hard', self.base)
        self.git('checkout', '-qb', 'docs-fixture')
        self.write('README.md', '# Documentation branch\n'); self.commit()
        self.git('checkout', '-qb', 'main-fixture', self.base)
        self.git('-c', 'commit.gpgsign=false', 'merge', '--no-ff', '-qm', 'synthetic merge', 'docs-fixture')
        self.assert_mode(self.check('push'), 'docs-only')

    def test_smoke_rejects_broken_resources_utf8_and_whitespace(self):
        for name, content in (('assets/support/qr.png', png()[:-5]),
                              ('docs/SUPPORT.md', b'\xff'),
                              ('docs/SUPPORT.md', '[missing](missing.md)\n'),
                              ('docs/SUPPORT.md', '![bad](../../outside.png)\n'),
                              ('docs/SUPPORT.md', '# trailing space \n')):
            with self.subTest(name=name):
                self.git('reset', '--hard', self.base)
                self.write(name, content); self.commit()
                self.assertNotEqual(self.check().returncode, 0)
        self.git('reset', '--hard', self.base)
        data = bytearray(png()); data[45] ^= 1
        self.write('assets/support/qr.png', bytes(data)); self.commit()
        self.assertNotEqual(self.check().returncode, 0)

    def test_existing_broken_reference_and_deleted_docs(self):
        self.write('docs/old.md', '[legacy](missing.md)\n'); self.base = self.commit()
        self.write('docs/old.md', '# Added text\n[legacy](missing.md)\n'); self.commit()
        self.assert_mode(self.check(), 'docs-only')
        self.git('rm', 'docs/old.md'); self.commit()
        self.assert_mode(self.check(), 'docs-only')
        self.write('README.md', '![QR](assets/support/qr.png)\n'); self.base = self.commit()
        self.git('rm', 'assets/support/qr.png'); self.write('README.md', '# Removed QR\n'); self.commit()
        self.assert_mode(self.check(), 'docs-only')

    def test_local_reference_cannot_escape_via_symlink(self):
        (self.repo/'docs/escape').symlink_to('/etc')
        self.write('docs/SUPPORT.md', '[escape](escape/passwd)\n'); self.commit()
        self.assert_mode(self.check(), 'full')  # unknown tracked symlink path
        self.base = self.git('rev-parse', 'HEAD')
        self.write('docs/SUPPORT.md', '[escape](escape/passwd)\n# Changed\n'); self.commit()
        self.assertNotEqual(self.check().returncode, 0)

    def diagnostics(self):
        spec = importlib.util.spec_from_file_location('fresh_diagnostics', ROOT/'tests/fresh/diagnostics.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def test_vision_failure_is_allowlisted_not_raw_log(self):
        diagnostics = self.diagnostics()
        secret = 'PRIVATE-CREDENTIAL-https://secret.invalid/token'
        result = diagnostics.vision_failure('Vision failed during configuring Vision inbound/nginx/HTTPS (exit 1): rollback=failed_rolled_back\n'+secret)
        self.assertEqual(result, {'stage':'configuring_inbound', 'exit_code':1, 'rollback':'failed_rolled_back'})
        unknown = diagnostics.vision_failure('Vision failed during '+secret+' (exit 2): rollback='+secret)
        self.assertEqual(unknown, {'stage':'unknown', 'exit_code':2, 'rollback':'unknown'})
        self.assertNotIn(secret, json.dumps([result, unknown]))
        self.assertIsNone(diagnostics.vision_failure('Vision Ready\n'+secret))

    def test_domain_failure_diagnostics_are_limited_to_public_source_constants(self):
        d=self.diagnostics();source=(ROOT/'assets/domains/managed.py').read_text()
        message='Unknown x-ui service layout.';secret='PRIVATE-SESSION-https://secret.invalid/token'
        self.assertEqual(d.domain_failure('Type YES: Change Domains failed during preflight: '+message+'\r\n'+secret,source),
                         {'stage':'preflight','reason':message})
        result=d.domain_failure('Change Domains failed during PRIVATE-STAGE: '+secret,source)
        self.assertEqual(result,{'stage':'unknown','reason':'unknown'})
        self.assertNotIn(secret,json.dumps(result))
        self.assertIsNone(d.domain_failure(secret,source))
        for reason in ('Managed health check failed (exit 1).','command failed (exit 1)',
                       'Required local component is missing/inaccessible (errno 1).'):
            self.assertEqual(d.domain_failure('Change Domains failed during preflight: '+reason,source)['reason'],reason)
        import ast,re,time
        tree=ast.parse((ROOT/'tests/fresh/acceptance.py').read_text())
        functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ('invoke','failure_location')]
        frame=b'  File "\x1b[35m/root/pilot/checks.py\x1b[0m", line \x1b[35m527\x1b[0m, in change_domains\n'+secret.encode()
        def ssh(command,*args,**kwargs):return subprocess.CompletedProcess([],1,frame if command.startswith('python3 -c') else b'',b'')
        with tempfile.TemporaryDirectory() as directory:
            env=dict(ROOT=Path(directory),REPO=ROOT,phase='change-domains',report={},ssh=ssh,re=re,time=time,json=json,domain_failure=d.domain_failure)
            exec(compile(ast.Module(body=functions,type_ignores=[]),'acceptance.py','exec'),env)
            with self.assertRaises(AssertionError):env['invoke']('checks.change_domains()','domains',tty=True)
            self.assertEqual(env['report'].get('failure_location'),'checks.py:527')
            self.assertNotIn(secret,json.dumps(env['report']))

    def test_dns_wire_contract_and_safe_probe_failures(self):
        d = self.diagnostics()
        ident=b'\x12\x34'
        question=b'\x07private\x07invalid\0'+struct.pack('!HH',1,1)
        answer=b'\xc0\x0c'+struct.pack('!HHIH',1,1,60,4)+bytes([203,0,113,7])
        extra=b'\xc0\x0c'+struct.pack('!HHIH',16,1,60,3)+b'\x02ok'
        packet=ident+struct.pack('!5H',0x8180,1,1,0,1)+question+answer+extra
        self.assertTrue(d.dns_metrics(packet,ident)['expected_a'])  # A need not be the packet suffix
        for probe in ('native_udp','doh_get','doh_post'):
            for data, field in ((b'bad','parse_valid'), (b'xx'+packet[2:],'transaction_id_match'),
                                (packet[:3]+b'\x83'+packet[4:],'rcode'),
                                (packet.replace(bytes([203,0,113,7]),bytes([203,0,113,8])),'expected_a')):
                with self.subTest(probe=probe,field=field):
                    with self.assertRaises(AssertionError):d.validate_dns(data,ident,probe,0.25)
                    payload=json.loads(str(self._read_dns_failure(d,data,ident,probe)))
                    self.assertEqual(payload['probe'],probe)
                    self.assertNotIn('private',json.dumps(payload))
            self.assertTrue(d.validate_dns(packet,ident,probe,0.25)['expected_a'])
        with self.assertRaises(ValueError):d.validate_dns(packet,ident,'secret URL',1)

    def test_dns_probe_records_success_and_failure_without_secret(self):
        diagnostics = self.diagnostics()
        secret = 'PRIVATE-DNS-NAME-https://secret.invalid/token'
        for probe in ('native_udp','doh_get','doh_post'):
            records = []
            def failure(): raise OSError(secret)
            with self.assertRaises(AssertionError) as caught:
                diagnostics.probe_dns(probe, b'aa', failure, records.append)
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]['transport_error'])
            self.assertEqual(records[0]['probe'], probe)
            self.assertNotIn(secret, str(caught.exception)+json.dumps(records))
            records.clear()
            with self.assertRaises(AssertionError):
                diagnostics.probe_dns(probe, b'aa', lambda:b'bad packet', records.append)
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0]['parse_valid'])

    def _read_dns_failure(self, diagnostics, data, ident, probe):
        try:diagnostics.validate_dns(data,ident,probe,0.25)
        except AssertionError as error:return error
        self.fail('DNS negative unexpectedly passed')


if __name__ == '__main__':
    unittest.main()
