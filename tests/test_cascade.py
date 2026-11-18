"""Cascade exit role: native API fixtures only, including uncertain writes."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
FLOW = 'xtls-rprx-vision'
IDENTITY = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


def helper():
    spec = importlib.util.spec_from_file_location('cascade_test', ROOT/'assets/cascade/managed.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inbound(iid=7, **changes):
    return dict(id=iid, protocol='vless', listen='127.0.0.1', port=8443, enable=True,
                remark='Renamed by administrator', tag='also-renamed',
                settings=dict(clients=[]), sniffing={},
                streamSettings=dict(network='tcp', security='reality'), **changes)


def link(identity=IDENTITY, port=443, **changes):
    query = dict(encryption='none', security='reality', type='tcp', flow=FLOW,
                 sni='reality.example', pbk='fixture-public-key', sid='0123', fp='firefox')
    query.update(changes)
    return f'vless://{identity}@panel.example:{port}?'+urlencode({k:v for k,v in query.items() if v is not None})+'#cascade'


class FakePanel:
    def __init__(self, present=False, fault='', strings=False):
        self.rows = [inbound(), inbound(8)]
        self.rows[1].update(port=9444, streamSettings=dict(network='tcp', security='tls'))
        self.record = None
        self.links = [link()]
        self.calls = []
        self.fault = fault
        self.strings = strings
        if present:
            self.install(IDENTITY)

    def install(self, identity):
        self.record = dict(client=dict(id=51, uuid=identity, email='cascade', enable=True,
                                      flow=FLOW, totalGB=0, expiryTime=0), inboundIds=[7])
        self.rows[0]['settings']['clients'] = [dict(id=identity, email='cascade', enable=True, flow=FLOW)]

    def request(self, path, data=None, **options):
        self.calls.append((path, copy.deepcopy(data), options))
        if self.fault == 'panel':
            raise ValueError('fixture-user fixture-password '+link())
        if path.endswith('/inbounds/list'):
            rows = copy.deepcopy(self.rows)
            if self.strings:
                for row in rows:
                    for key in ('settings', 'streamSettings', 'sniffing'):
                        row[key] = json.dumps(row[key])
            return dict(success=True, obj=rows)
        if path.endswith('/clients/list'):
            if self.fault == 'readback' and self.record:
                raise ValueError('fixture-password '+link())
            return dict(success=True, obj=[] if self.record is None else [copy.deepcopy(self.record['client'])])
        if path.endswith('/clients/get/cascade'):
            if self.fault == 'get': raise ValueError('fixture-password')
            if self.record is None:
                raise ValueError('not found')
            return dict(success=True, obj=copy.deepcopy(self.record))
        if path.endswith('/clients/add'):
            if self.fault == 'rejected':
                raise ValueError('fixture-password')
            self.install(OTHER if self.fault == 'replaced' else data['client']['id'])
            self.record['inboundIds'] = list(data['inboundIds'])
            if self.fault == 'wrong_binding': self.record['inboundIds'] = [7, 8]
            if self.fault == 'wrong_flow': self.record['client']['flow'] = ''
            if self.fault == 'disabled': self.record['client']['enable'] = False
            if self.fault == 'partial':
                raise subprocess.TimeoutExpired(['curl'], 20, stderr=b'fixture-password')
            return dict(success=True)
        if path.endswith('/clients/links/cascade'):
            if self.fault == 'links': raise ValueError(link())
            if self.fault == 'replace-before-cleanup':
                self.install(OTHER)
                raise ValueError(link())
            return dict(success=True, obj=self.links)
        if path.endswith('/clients/del/cascade'):
            if self.fault in ('cleanup', 'delete'):
                raise ValueError('fixture-password '+link())
            if self.fault != 'delete-noop':
                self.record = None
                self.rows[0]['settings']['clients'] = []
            if self.fault == 'delete-partial': raise ValueError('fixture-password')
            return dict(success=True)
        raise AssertionError(path)


class Cascade(unittest.TestCase):
    def setUp(self):
        self.module = helper()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.manifest = Path(self.temporary.name)/'manifest.json'

    def run_command(self, mode, panel):
        with patch.object(self.module.uuid, 'uuid4', return_value=IDENTITY):
            return self.module.execute(mode, panel, self.manifest)

    def mutations(self, panel):
        return [p for p, _, _ in panel.calls if p.endswith(('/add', '/del/cascade'))]

    def test_structure_and_renamed_remark_both_json_shapes(self):
        for strings in (False, True):
            panel = FakePanel(strings=strings)
            result = self.run_command('exit-create', panel)
            self.assertEqual(result, dict(state='created', link=link()))
            post = next((body, opts) for p, body, opts in panel.calls if p.endswith('/clients/add'))
            self.assertEqual(post, (dict(client=dict(email='cascade', id=IDENTITY, flow=FLOW,
                                                   enable=True, totalGB=0, expiryTime=0), inboundIds=[7]),
                                    dict(method='POST')))
            self.assertEqual(self.run_command('exit-status', panel), dict(state='ready'))

    def test_cascade_exit_on_installer_layout_without_ws_grpc(self):
        from test_personal_xhttp import seed

        rows, _ = seed(INSTALL_WS_GRPC='n')
        self.assertEqual(set(rows), {'reality', 'xhttp', 'hysteria2'})
        # FakePanel uses ID 7 for the REALITY client readback.
        panel = FakePanel()
        panel.rows = [dict(id=row['id']+6, protocol=row['protocol'], port=int(row['port']), listen=row['listen'],
                           enable=row['enable']=='1', settings=json.loads(row['settings']),
                           streamSettings=json.loads(row['stream_settings'])) for row in rows.values()]
        self.manifest.write_text(json.dumps({'inbound_roles': {'reality': panel.rows[0]['id']}}))
        self.assertEqual(self.run_command('exit-create', panel)['state'], 'created')
        self.assertEqual(self.run_command('exit-status', panel), {'state': 'ready'})
        self.assertEqual(panel.record['inboundIds'], [rows['reality']['id']+6])

    def test_manifest_selects_one_of_multiple_structural_matches(self):
        self.manifest.write_text(json.dumps(dict(inbound_roles=dict(reality=9))))
        panel = FakePanel()
        panel.rows.append(inbound(9))
        self.assertEqual(self.run_command('exit-create', panel)['state'], 'created')
        self.assertEqual(next(b for p,b,_ in panel.calls if p.endswith('/clients/add'))['inboundIds'], [9])

    def test_no_and_ambiguous_reality_for_every_command_never_mutate(self):
        for mode in ('exit-create', 'exit-status', 'exit-remove'):
            for state in ('no_reality', 'ambiguous_reality'):
                with self.subTest(mode=mode, state=state):
                    panel = FakePanel(present=True)
                    if state == 'no_reality': panel.rows = panel.rows[1:]
                    else: panel.rows.append(inbound(9))
                    self.assertEqual(self.run_command(mode, panel), dict(state=state))
                    self.assertEqual(self.mutations(panel), [])

    def test_invalid_manifest_never_falls_back_for_every_command(self):
        values = ['broken json', '{}', '{"inbound_roles":{"reality":99}}',
                  '{"inbound_roles":{"reality":8}}']
        for mode in ('exit-create', 'exit-status', 'exit-remove'):
            for value in values:
                with self.subTest(mode=mode, value=value):
                    self.manifest.write_text(value)
                    panel = FakePanel(present=True)
                    expected = 'panel_error' if mode == 'exit-status' else 'failed'
                    self.assertEqual(self.run_command(mode, panel), dict(state=expected, reason='manifest_invalid'))
                    self.assertEqual(self.mutations(panel), [])
        self.manifest.unlink()
        self.manifest.mkdir()
        for mode in ('exit-create', 'exit-status', 'exit-remove'):
            self.assertEqual(self.run_command(mode, FakePanel())['reason'], 'manifest_invalid')

    def test_name_taken_including_disabled_or_foreign_client_never_changes_it(self):
        for changes in ({}, dict(enable=False), dict(flow='')):
            panel = FakePanel(present=True)
            panel.record['client'].update(changes)
            original = copy.deepcopy(panel.record)
            self.assertEqual(self.run_command('exit-create', panel), dict(state='name_taken'))
            self.assertEqual(panel.record, original)
            self.assertEqual(self.mutations(panel), [])

    def test_name_taken_does_not_depend_on_client_detail_request(self):
        panel = FakePanel(present=True, fault='get')
        self.assertEqual(self.run_command('exit-create', panel), dict(state='name_taken'))
        self.assertFalse(any('/clients/get/' in p for p,_,_ in panel.calls))

    def test_uncertain_add_is_read_back_and_never_retried(self):
        panel = FakePanel(fault='partial')
        self.assertEqual(self.run_command('exit-create', panel)['state'], 'created')
        paths = [p for p,_,_ in panel.calls]
        self.assertEqual(paths.count('panel/api/clients/add'), 1)
        self.assertGreater(paths.index('panel/api/clients/get/cascade'), paths.index('panel/api/clients/add'))
        panel = FakePanel(fault='rejected')
        self.assertEqual(self.run_command('exit-create', panel)['state'], 'failed')
        self.assertEqual(self.mutations(panel), ['panel/api/clients/add'])

    def test_actual_form_failure_rolls_back_owned_client(self):
        for fault in ('wrong_binding', 'wrong_flow', 'disabled'):
            with self.subTest(fault=fault):
                panel = FakePanel(fault=fault)
                self.assertEqual(self.run_command('exit-create', panel)['state'], 'failed')
                self.assertIsNone(panel.record)
                self.assertEqual(self.mutations(panel), ['panel/api/clients/add', 'panel/api/clients/del/cascade'])

    def test_link_validation_and_rollback(self):
        bad_links = [(link(port=8443), 'internal_port_8443'), (link(port=444), 'wrong_port'),
                     (link(identity=OTHER), 'uuid_mismatch'), (link().replace('vless:', 'trojan:'), 'wrong_scheme'),
                     (link().replace('panel.example', ''), 'missing_host')]
        for key, value in (('flow', None), ('security', 'tls'), ('type', 'ws'), ('encryption', 'aes'),
                           ('pbk', None), ('sid', None), ('sni', None), ('fp', None), ('fp', '')):
            bad_links.append((link(**{key:value}), 'invalid_'+key))
        for invalid, reason in bad_links:
            with self.subTest(reason=reason), patch.object(self.module.uuid, 'uuid4', return_value=IDENTITY):
                panel = FakePanel()
                panel.links = [invalid]
                self.assertEqual(self.run_command('exit-create', panel), dict(state='link_invalid', reason=reason))
                self.assertIsNone(panel.record)

    def test_multiple_links_require_exactly_one_reality_tcp_vision_link(self):
        for links, state in (([link(security='tls'), link()], 'created'),
                             ([link(type='ws'), link()], 'created'),
                             ([link(), link().replace('panel.example', 'other.example')], 'link_invalid'),
                             ([link(security='tls'), link(type='ws')], 'link_invalid'),
                             ([], 'link_invalid')):
            with self.subTest(state=state, count=len(links)):
                panel = FakePanel()
                panel.links = links
                result = self.run_command('exit-create', panel)
                self.assertEqual(result['state'], state)
                if state == 'created': self.assertEqual(result['link'], link())
                else: self.assertIsNone(panel.record)

    def test_cleanup_failure_and_unavailable_readback_admit_possible_remaining_client(self):
        for fault in ('cleanup', 'readback', 'delete-noop'):
            panel = FakePanel(fault=fault)
            panel.links = [link(pbk=None)]
            result = self.run_command('exit-create', panel)
            self.assertEqual(result['state'], 'failed_cleanup')
            self.assertIs(result['client_may_remain'], True)
            self.assertNotIn('link', result)
            self.assertIsNotNone(panel.record)

    def test_different_uuid_is_never_removed_including_replacement_before_cleanup(self):
        for fault in ('replaced', 'replace-before-cleanup'):
            panel = FakePanel(fault=fault)
            result = self.run_command('exit-create', panel)
            self.assertEqual(result['state'], 'failed')
            self.assertEqual(panel.record['client']['uuid'], OTHER)
            self.assertNotIn('panel/api/clients/del/cascade', self.mutations(panel))

    def test_link_api_error_cleans_up(self):
        panel = FakePanel(fault='links')
        self.assertEqual(self.run_command('exit-create', panel)['state'], 'failed')
        self.assertIsNone(panel.record)
        panel = FakePanel(fault='delete-partial')
        panel.links = [link(pbk=None)]
        self.assertEqual(self.run_command('exit-create', panel)['state'], 'link_invalid')
        self.assertIsNone(panel.record)

    def test_status_absent_ready_disabled_wrong_binding_wrong_flow_panel_error(self):
        self.assertEqual(self.run_command('exit-status', FakePanel()), dict(state='absent'))
        self.assertEqual(self.run_command('exit-status', FakePanel(present=True)), dict(state='ready'))
        for reason in ('disabled', 'wrong_binding', 'wrong_flow'):
            panel = FakePanel(present=True)
            if reason == 'disabled': panel.record['client']['enable'] = False
            if reason == 'wrong_binding': panel.record['inboundIds'] = [7, 8]
            if reason == 'wrong_flow': panel.record['client']['flow'] = ''
            self.assertEqual(self.run_command('exit-status', panel), dict(state='inconsistent', reason=reason))
            self.assertEqual(self.mutations(panel), [])
            self.assertFalse(any('/links/' in p for p,_,_ in panel.calls))
        self.assertEqual(self.run_command('exit-status', FakePanel(fault='panel'))['state'], 'panel_error')

    def test_remove_absent_removed_and_disabled_owned_client(self):
        self.assertEqual(self.run_command('exit-remove', FakePanel()), dict(state='absent'))
        for disabled in (False, True):
            panel = FakePanel(present=True)
            panel.record['client']['enable'] = not disabled
            self.assertEqual(self.run_command('exit-remove', panel), dict(state='removed'))
            self.assertIsNone(panel.record)
            delete = next((b,o) for p,b,o in panel.calls if p.endswith('/del/cascade'))
            self.assertEqual(delete, (None, dict(method='POST')))
            self.assertTrue(panel.calls[-1][0].endswith('/clients/list'))
            self.assertEqual(self.run_command('exit-remove', panel), dict(state='absent'))

    def test_remove_not_ours_never_deletes(self):
        for binding in ([8], [7,8], [], [7,7]):
            panel = FakePanel(present=True)
            panel.record['inboundIds'] = binding
            self.assertEqual(self.run_command('exit-remove', panel), dict(state='not_ours'))
            self.assertEqual(self.mutations(panel), [])
        panel = FakePanel(present=True)
        panel.record['client']['flow'] = ''
        self.assertEqual(self.run_command('exit-remove', panel), dict(state='not_ours'))
        self.assertEqual(self.mutations(panel), [])

    def test_remove_reads_back_even_after_api_error(self):
        for fault, state in (('delete-partial','removed'), ('delete','failed'), ('delete-noop','failed'), ('panel','failed')):
            panel = FakePanel(present=True, fault=fault)
            self.assertEqual(self.run_command('exit-remove', panel)['state'], state)

    def cli(self, mode, panel, login_error=False):
        sessions = []
        def factory(base, user, password, directory, options):
            self.assertEqual((base,user,password), ('https://panel.example/panel/', 'fixture-user', 'fixture-password'))
            for secret in ('fixture-user', 'fixture-password', link()):
                self.assertNotIn(secret, ' '.join(self.module.sys.argv))
            self.assertEqual(options, ['--resolve', 'panel.example:443:127.0.0.1'])
            self.assertEqual(Path(directory).stat().st_mode & 0o777, 0o700)
            sessions.append(Path(directory))
            if login_error: raise ValueError('fixture-user fixture-password '+link())
            return panel
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(self.module.importlib.util, 'spec_from_file_location', return_value=spec), \
             patch.object(self.module.importlib.util, 'module_from_spec', return_value=SimpleNamespace(Panel=factory)), \
             patch.object(self.module.sys, 'argv', ['managed.py',mode,'helper','panel.example','panel',self.temporary.name]), \
             patch.object(self.module.sys, 'stdin', io.StringIO('fixture-user\0fixture-password')), \
             patch.object(self.module, 'MANIFEST', self.manifest), \
             redirect_stdout(output), redirect_stderr(errors):
            code = self.module.main()
        self.assertTrue(sessions)
        self.assertTrue(all(not p.exists() for p in sessions))
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        value = json.loads(output.getvalue())
        self.assertIsInstance(value, dict)
        self.assertEqual(errors.getvalue(), '')
        for secret in ('fixture-user', 'fixture-password'):
            self.assertNotIn(secret, output.getvalue()+errors.getvalue())
        if value['state'] != 'created': self.assertNotIn(link(), output.getvalue())
        return code, value

    def test_cli_exit_codes_single_json_and_link_only_for_created(self):
        cases = [('exit-create', FakePanel(), 'created'),
                 ('exit-status', FakePanel(present=True), 'ready'),
                 ('exit-remove', FakePanel(present=True), 'removed'),
                 ('exit-status', FakePanel(), 'absent'), ('exit-remove', FakePanel(), 'absent'),
                 ('exit-create', FakePanel(present=True), 'name_taken'),
                 ('exit-create', FakePanel(fault='rejected'), 'failed'),
                 ('exit-status', FakePanel(fault='panel'), 'panel_error')]
        for mode in ('exit-create','exit-status','exit-remove'):
            panel = FakePanel(); panel.rows = []
            cases.append((mode, panel, 'no_reality'))
            panel = FakePanel(); panel.rows.append(inbound(9))
            cases.append((mode, panel, 'ambiguous_reality'))
        for fault, state in (('', 'link_invalid'), ('cleanup', 'failed_cleanup')):
            panel = FakePanel(fault=fault); panel.links = [link(pbk=None)]
            cases.append(('exit-create', panel, state))
        panel = FakePanel(present=True); panel.record['client']['flow'] = ''
        cases.append(('exit-remove', panel, 'not_ours'))
        panel = FakePanel(present=True); panel.record['client']['enable'] = False
        cases.append(('exit-status', panel, 'inconsistent'))
        for mode, panel, state in cases:
            with self.subTest(mode=mode, state=state), patch.object(self.module.uuid, 'uuid4', return_value=IDENTITY):
                code, value = self.cli(mode, panel)
                self.assertEqual(code, 0 if state in ('created','ready','removed','absent') else 1)
                self.assertEqual(value['state'], state)
                self.assertEqual('link' in value, state == 'created')

    def test_cli_session_and_api_errors_hide_secrets_and_cleanup(self):
        for mode in ('exit-create','exit-status','exit-remove'):
            for login_error in (False,True):
                code, value = self.cli(mode, FakePanel(fault='panel'), login_error=login_error)
                self.assertEqual(code, 1)
                self.assertEqual(value['state'], 'panel_error' if mode == 'exit-status' else 'failed')

    def test_cli_actual_success_does_not_write_role_state(self):
        with patch.object(self.module.uuid, 'uuid4', return_value=IDENTITY):
            code, value = self.cli('exit-create', FakePanel())
        self.assertEqual((code,value), (0,dict(state='created',link=link())))
        self.assertEqual(list(Path(self.temporary.name).iterdir()), [])
