"""Cascade manager uses fixture helpers, stdin credentials and existing UI primitives."""
import json
import os
from pathlib import Path
import pty
import re
import select
import signal
import subprocess
import tempfile
import termios
import time
import unittest

from test_manager import ROOT


class CascadeManager(unittest.TestCase):
    def shell(self, body, payload='', language='en'):
        return subprocess.run(['bash', '-c', 'source "$1"; UI_LANG=$2; '+body,
                               'fixture', str(ROOT/'x-ui-latest.sh'), language],
                              input=payload, text=True, capture_output=True, timeout=10)

    def test_submenu_numbers_existing_main_options_and_back(self):
        for language in ('en', 'ru'):
            result = self.shell('recover_domain_operation() { :; }; manager_menu', '5\n0\n0\n', language)
            self.assertEqual(result.returncode, 0, result.stderr)
            for value in (('1. Installation', '2. Change Domains', '3. Backups', '4. Telegram Web Proxy Manager',
                           '5. Cascade', '1. Create key', '2. Connect exit server', '3. Status', '4. Disable')
                          if language == 'en' else ('1. Установка', '2. Смена доменов', '3. Резервные копии',
                           '4. Telegram Web Proxy Manager', '5. Каскад', '1. Создать ключ',
                           '2. Подключить выходной сервер', '3. Состояние', '4. Отключить')):
                self.assertIn(value, result.stdout)

    def test_custom_warning_frames_numbers_and_amneziawg_translations(self):
        for language in ('en', 'ru'):
            result = self.shell('cascade_result=$(cat); cascade_custom_warning; cascade_awg_notice',
                                json.dumps(dict(custom_rules=[2, 7])), language)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('=' * 60, result.stdout)
            self.assertIn('2, 7', result.stdout)
            self.assertIn('AmneziaWG', result.stdout)
            self.assertIn('bittorrent', result.stdout)
            self.assertNotIn('—', result.stdout)
            brief=self.shell('cascade_result=$(cat); cascade_custom_warning brief',
                             json.dumps(dict(custom_rules=[2, 7])), language)
            self.assertEqual(brief.returncode,0,brief.stderr)
            self.assertIn('2, 7',brief.stdout)
            self.assertLess(len(brief.stdout), len(result.stdout))

    def test_result_texts_cover_states_reasons_and_private_errors(self):
        cases = {
            'exit-create': [dict(state=s) for s in ('name_taken', 'no_reality', 'ambiguous_reality')]
                + [dict(state='link_invalid', reason=r) for r in ('wrong_scheme', 'uuid_mismatch', 'missing_host',
                   'internal_port_8443', 'wrong_port', 'invalid_encryption', 'invalid_security', 'invalid_type',
                   'invalid_flow', 'invalid_sni', 'invalid_pbk', 'invalid_sid', 'invalid_fp', 'malformed_link', 'link_count')]
                + [dict(state='failed', reason=r) for r in ('client_absent', 'identity_changed', 'disabled',
                   'wrong_binding', 'wrong_flow', 'readback_failed', 'panel_request_failed', 'manifest_invalid')]
                + [dict(state='failed_cleanup', client_may_remain=True)],
            'entry-connect': [dict(state=s) for s in ('already_connected', 'test_failed')]
                + [dict(state='intercepted', rule_index=4), dict(state='warp_active', warp_outbound=True, warp_rules=['WARP - RU2'])]
                + [dict(state='failed', reason=r, rule_index=4) for r in ('save_failed', 'readback_failed',
                   'readback_mismatch', 'route_test_failed', 'xray_unhealthy', 'xray_not_running', 'missing_direct',
                   'invalid_rule', 'invalid_network', 'panel_request_failed', 'session_failed')]
                + [dict(state='link_invalid', reason=r) for r in ('wrong_scheme', 'invalid_uuid', 'missing_host',
                   'invalid_port', 'invalid_encryption', 'invalid_security', 'invalid_type', 'invalid_flow',
                   'invalid_sni', 'invalid_pbk', 'invalid_sid', 'invalid_fp', 'malformed_link')]
                + [dict(state='failed_rollback', reason=r, config_may_contain_changes=True, xray_running=False,
                        foreign_rules=[4], foreign_balancers=[2]) for r in ('foreign_reference', 'route_test_failed')],
            'exit-remove': [dict(state=s) for s in ('removed', 'absent', 'not_ours', 'failed_cleanup', 'panel_error')]
                + [dict(state='failed', reason=r) for r in ('delete_unverified', 'identity_changed', 'manifest_invalid', 'panel_request_failed')],
            'entry-disable': [dict(state='removed', xray_running=value) for value in (True, False)]
                + [dict(state='absent'), dict(state='foreign_reference', foreign_rules=[4], foreign_balancers=[2])]
                + [dict(state='failed', reason=r) for r in ('readback_failed', 'remove_unverified', 'save_failed_actual_unknown',
                   'save_failed_actual_active', 'save_failed_actual_absent', 'save_failed_actual_missing_outbound',
                   'save_failed_actual_missing_rules', 'save_failed_actual_wrong_order')]
                + [dict(state='panel_error')],
            'exit-status': [dict(state=s) for s in ('ready', 'absent', 'no_reality', 'ambiguous_reality', 'panel_error')]
                + [dict(state='inconsistent', reason=r) for r in ('disabled', 'wrong_binding', 'wrong_flow')],
            'entry-status': [dict(state=s, xray='running', warp=False, custom_rules=[]) for s in ('active', 'absent', 'panel_error')]
                + [dict(state='inconsistent', reason=r, xray='error', warp=True, warp_outbound=True,
                        warp_rules=['WARP - RU3'], custom_rules=[3]) for r in ('missing_outbound', 'missing_rules', 'wrong_order')],
        }
        for language in ('en', 'ru'):
            for mode, values in cases.items():
                for value in values:
                    with self.subTest(language=language, mode=mode, value=value):
                        result = self.shell('cascade_result=$(cat); cascade_show_result '+mode, json.dumps(value), language)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertTrue(result.stdout.strip())
                        self.assertNotIn('—', result.stdout)
                        self.assertNotIn('Traceback', result.stderr)
                        self.assertNotIn('UNKNOWN', result.stdout)
                        if language == 'ru':
                            self.assertRegex(result.stdout, '[А-Яа-я]')
                        else:
                            self.assertNotRegex(result.stdout, '[А-Яа-я]')

    def action(self, action, replies, answers, language='en'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'replies').write_text(json.dumps(replies))
            (root/'helper.py').write_text('''import json, os, pathlib, sys
root=pathlib.Path(sys.argv[1]);mode=sys.argv[2]
payload=sys.stdin.read().split('\\0')
assert payload[:2] == ['fixture-user','fixture-password']
if mode=='entry-connect': assert payload[2]=='vless://fixture-private-link'
for secret in payload:
    assert secret not in ' '.join(sys.argv)
    assert secret not in '\\0'.join(os.environ.values())
with (root/'calls').open('a') as out: out.write(mode+'\\n')
replies=json.loads((root/'replies').read_text());reply=replies.pop(0)
(root/'replies').write_text(json.dumps(replies));print(json.dumps(reply))
sys.exit(0 if reply['state'] in ('created','ready','removed','absent','connected','active') else 1)
''')
            script = '''source "$1"
UI_LANG=$2
acquire_stack_lock() { printf 'locked\\n' >> "$FIXTURE_ROOT/lock"; }
recover_domain_operation() { :; }
prepare_cascade_tools() { CASCADE_STAGE=$(mktemp -d "$FIXTURE_ROOT/stage.XXXXXX"); }
cascade_panel_context() { cascade_domain=panel.example; cascade_path=panel; }
cascade_tool() { python3 "$FIXTURE_ROOT/helper.py" "$FIXTURE_ROOT" "$1"; }
cascade_action "$3"
'''
            result = subprocess.run(['bash', '-c', script, 'fixture', str(ROOT/'x-ui-latest.sh'), language, str(action)],
                input=answers, text=True, capture_output=True, timeout=10,
                env={**os.environ, 'FIXTURE_ROOT':str(root), 'cascade_username':'fixture-user',
                     'cascade_password':'fixture-password', 'cascade_link':'vless://fixture-private-link'})
            calls=(root/'calls').read_text().splitlines() if (root/'calls').exists() else []
            self.assertFalse(list(root.glob('stage.*')), result.stderr)
            self.assertEqual((root/'lock').read_text(), 'locked\n')
            for secret in ('fixture-user', 'fixture-password', 'vless://fixture-private-link'):
                self.assertNotIn(secret, result.stdout + result.stderr + ' '.join(result.args))
            return result, calls

    def test_preflight_before_link_custom_confirmation_default_no(self):
        status=dict(state='absent', xray='running', warp=False, custom_rules=[2])
        result, calls=self.action(2, [status], 'fixture-user\nfixture-password\n\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['entry-status'])
        self.assertIn('[y/N]', result.stdout)
        self.assertNotIn('Paste', result.stdout)
        status['custom_rules']=[]
        result, calls=self.action(2, [status, dict(state='connected', custom_rules=[])],
                                 'fixture-user\nfixture-password\nvless://fixture-private-link\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['entry-status', 'entry-connect'])
        self.assertEqual(result.stdout.count('Cascade does not work with AmneziaWG.'), 2)

    def test_session_failures_retry_at_most_three_and_one_login_for_status_pair(self):
        failure=dict(state='failed', reason='session_failed')
        result, calls=self.action(1, [failure]*3, 'fixture-user\nfixture-password\n'*3)
        self.assertEqual(calls, ['exit-create']*3)
        self.assertEqual(result.stdout.count('Panel login (hidden):'), 3)
        self.assertNotEqual(result.returncode, 0)
        result, calls=self.action(3, [dict(state='absent'), dict(state='absent', xray='running', warp=False, custom_rules=[])],
                                 'fixture-user\nfixture-password\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['exit-status', 'entry-status'])
        self.assertEqual(result.stdout.count('Panel login (hidden):'), 1)

    def test_disable_default_no_for_both_roles(self):
        result, calls=self.action(4, [dict(state='ready'), dict(state='active', xray='running', warp=False, custom_rules=[])],
                                 'fixture-user\nfixture-password\n\n\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['exit-status', 'entry-status'])
        self.assertEqual(result.stdout.count('[y/N]'), 2)

    def test_amneziawg_intro_connected_and_status_for_both_languages(self):
        for language, phrase in (('en', 'Cascade does not work with AmneziaWG.'),
                                 ('ru', 'Каскад не работает с AmneziaWG.')):
            result, calls=self.action(2, [dict(state='absent', xray='running', warp=False, custom_rules=[]),
                dict(state='connected', custom_rules=[])], 'fixture-user\nfixture-password\nvless://fixture-private-link\n', language)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count(phrase), 2)
            for state in ('active', 'inconsistent', 'absent'):
                result, calls=self.action(3, [dict(state='ready'), dict(state=state, reason='missing_rules',
                    xray='running', warp=False, custom_rules=[])], 'fixture-user\nfixture-password\n', language)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.count(phrase), 0 if state == 'absent' else 1)
                self.assertEqual(calls, ['exit-status', 'entry-status'])

    def test_custom_confirmation_yes_and_blocking_preflights(self):
        status=dict(state='absent', xray='running', warp=False, custom_rules=[3, 5])
        result, calls=self.action(2, [status, dict(state='connected', custom_rules=[3, 5])],
            'fixture-user\nfixture-password\ny\nvless://fixture-private-link\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['entry-status', 'entry-connect'])
        self.assertEqual(result.stdout.count('YOUR ROUTING RULES'), 2)
        self.assertEqual(result.stdout.count('3, 5'), 2)
        for changes in (dict(state='active'), dict(state='inconsistent'), dict(xray='stop'),
                        dict(xray='error'), dict(xray='unknown'),
                        dict(warp=True, warp_outbound=True, warp_rules=['WARP - RU'])):
            result, calls=self.action(2, [status | changes], 'fixture-user\nfixture-password\n')
            self.assertEqual(calls, ['entry-status'])
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Paste', result.stdout)

    def test_retry_then_continue_and_disable_both_roles_under_one_login(self):
        failure=dict(state='panel_error', reason='session_failed')
        result, calls=self.action(3, [failure, dict(state='ready'), dict(state='active',
            xray='running', warp=False, custom_rules=[])], 'fixture-user\nfixture-password\n'*2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['exit-status', 'exit-status', 'entry-status'])
        self.assertEqual(result.stdout.count('Panel login (hidden):'), 2)
        result, calls=self.action(4, [dict(state='ready'), dict(state='active', xray='running', warp=False,
            custom_rules=[]), dict(state='removed'), dict(state='removed', xray_running=False)],
            'fixture-user\nfixture-password\ny\ny\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ['exit-status', 'entry-status', 'exit-remove', 'entry-disable'])
        self.assertEqual(result.stdout.count('Panel login (hidden):'), 1)
        self.assertIn('Xray is stopped or has an error.', result.stdout)

    def test_absent_entry_with_warp_status_and_disable(self):
        entry = dict(state='absent', xray='running', warp=True, warp_outbound=True,
                     warp_rules=['WARP - RU'], custom_rules=[3])
        for language in ('en', 'ru'):
            for action, replies, answers in (
                (3, [dict(state='absent'), entry], 'fixture-user\nfixture-password\n'),
                (4, [dict(state='ready'), entry, dict(state='removed')], 'fixture-user\nfixture-password\ny\n'),
                (4, [dict(state='absent'), entry], 'fixture-user\nfixture-password\n'),
            ):
                with self.subTest(language=language, action=action, replies=replies):
                    result, calls = self.action(action, replies, answers, language)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    for text in ('[FAIL]', 'WARP was found', 'Найден WARP', 'YOUR ROUTING RULES',
                                 'ВАШИ ПРАВИЛА МАРШРУТИЗАЦИИ'):
                        self.assertNotIn(text, result.stdout)
                    if len(replies) == 3:
                        self.assertIn('disabled' if language == 'en' else 'отключена', result.stdout)

    def test_active_entry_keeps_warp_and_rule_warnings(self):
        for state in ('active', 'inconsistent'):
            entry = dict(state=state, reason='missing_rules', xray='running', warp=True,
                         warp_outbound=True, warp_rules=['WARP - RU'], custom_rules=[3])
            result, _ = self.action(3, [dict(state='absent'), entry], 'fixture-user\nfixture-password\n')
            self.assertEqual(result.returncode, 0)
            self.assertIn('WARP was found', result.stdout)
            self.assertIn('YOUR ROUTING RULES', result.stdout)

    def test_status_colors_obey_terminal_and_no_color(self):
        cases = [('exit-status', dict(state='ready'), 'Exit role: ready', '1;32'),
                 ('entry-status', dict(state='active', xray='running'), 'Entry role: configured', '1;32'),
                 ('entry-status', dict(state='inconsistent', reason='missing_rules', xray='running'), 'Cascade settings are incomplete', '1;31'),
                 ('exit-status', dict(state='panel_error'), 'Could not read the panel settings', '1;31'),
                 ('entry-status', dict(state='absent'), 'Cascade is not configured', None)]
        for language in ('en', 'ru'):
            for mode, value, phrase, color in cases:
                with self.subTest(language=language, mode=mode, state=value['state']):
                    body = 'cascade_result=$2; UI_LANG=$3; cascade_show_result "$4"'
                    args = ['bash', '-c', 'source "$1"; '+body, 'fixture', str(ROOT/'x-ui-latest.sh'),
                            json.dumps(value), language, mode]
                    env = {k: v for k, v in os.environ.items() if k != 'NO_COLOR'} | {'TERM': 'xterm'}
                    master, slave = pty.openpty()
                    try:
                        proc = subprocess.run(args, stdout=slave, stderr=subprocess.PIPE, env=env, timeout=10)
                        os.close(slave); slave = -1
                        output = b''
                        while True:
                            try:
                                chunk = os.read(master, 65536)
                            except OSError:
                                break
                            if not chunk: break
                            output += chunk
                    finally:
                        os.close(master)
                        if slave != -1: os.close(slave)
                    self.assertEqual(proc.returncode, 0)
                    if language == 'en':
                        self.assertIn(phrase.encode(), output)
                    if color:
                        self.assertIn(('\x1b['+color+'m').encode(), output)
                    else:
                        self.assertNotIn(b'\x1b[', output)
                    piped = subprocess.run(args, capture_output=True, env=env, timeout=10)
                    self.assertEqual(piped.returncode, 0)
                    self.assertNotIn(b'\x1b[', piped.stdout)
                    master, slave = pty.openpty()
                    try:
                        no_color = subprocess.run(args, stdout=slave, stderr=subprocess.PIPE,
                                                  env=env | {'NO_COLOR': '1'}, timeout=10)
                        os.close(slave); slave = -1
                        output = b''
                        while True:
                            try:
                                chunk = os.read(master, 65536)
                            except OSError:
                                break
                            if not chunk: break
                            output += chunk
                    finally:
                        os.close(master)
                        if slave != -1: os.close(slave)
                    self.assertEqual(no_color.returncode, 0)
                    self.assertNotIn(b'\x1b[', output)

    def test_created_link_is_the_only_deliberate_private_output(self):
        for language in ('ru', 'en'):
            link='vless://fixture-generated-key'
            result=self.shell('cascade_result=$(cat); cascade_show_result exit-create',
                              json.dumps(dict(state='created', link=link)), language)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count(link), 1)
            self.assertIn('='*60+'\n'+link+'\n'+'='*60, result.stdout)
            self.assertEqual(result.stderr, '')

    def test_panel_context_reads_certificate_domain_and_path_without_credentials(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temporary:
            db=Path(temporary)/'panel.db'
            with sqlite3.connect(db) as connection:
                connection.execute('CREATE TABLE settings (key TEXT,value TEXT)')
                connection.executemany('INSERT INTO settings VALUES (?,?)', [('webCertFile','/root/cert/panel.example/fullchain.pem'),
                    ('webBasePath','/private-panel/'), ('password','fixture-password')])
            result=self.shell('XUIDB='+str(db)+'; cascade_panel_context; printf "%s|%s" "$cascade_domain" "$cascade_path"')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, 'panel.example|private-panel')
            self.assertEqual(result.stderr, '')

    def test_loader_same_ref_syntax_failure_and_no_per_file_fallback(self):
        source=(ROOT/'x-ui-latest.sh').read_text()
        loader=re.search(r'^prepare_cascade_tools\(\) \{.*?^\}', source, re.M|re.S)[0]
        for fault in ('', 'download', 'syntax'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                script=loader.replace('/run/xui-cascade.', str(root)+'/stage.')+'''
pin_project_source() { return 99; }
curl() {
    local previous='' output='' url='' arg
    for arg in "$@"; do
        [[ "$previous" != -o ]] || output=$arg
        [[ "$arg" != https://* ]] || url=$arg
        previous=$arg
    done
    printf '%s\\n' "$url" >> "$FIXTURE_ROOT/urls"
    [[ $FAULT != download ]] || return 22
    if [[ $FAULT == syntax ]]; then printf 'not valid python !!!\\n' > "$output"
    else printf '# fixture helper\\n' > "$output"; fi
}
PROJECT_REF=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
PROJECT_SOURCE_SHA=$PROJECT_REF
GITHUB_RAW=https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/$PROJECT_REF
prepare_cascade_tools
'''
                result=subprocess.run(['bash','-c',script],capture_output=True,text=True,
                    env={**os.environ,'FIXTURE_ROOT':str(root),'FAULT':fault},timeout=5)
                self.assertEqual(result.returncode == 0, not fault, result.stderr)
                urls=(root/'urls').read_text().splitlines()
                self.assertTrue(all('/'+'a'*40+'/assets/' in url for url in urls))
                if not fault:
                    self.assertEqual([url.rsplit('/',2)[1] for url in urls], ['cascade','amneziawg'])
                    stage=next(root.glob('stage.*'))
                    self.assertEqual(stage.stat().st_mode & 0o777, 0o700)
                    self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in stage.iterdir()))

    def test_real_tty_credentials_hidden_even_with_inherited_xtrace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            script=root/'tty.sh'
            script.write_text('source '+str(ROOT/'x-ui-latest.sh')+'''
acquire_stack_lock() { :; }
recover_domain_operation() { :; }
prepare_cascade_tools() { CASCADE_STAGE=$(mktemp -d "$FIXTURE_ROOT/stage.XXXXXX"); }
cascade_panel_context() { cascade_domain=panel.example; cascade_path=panel; }
cascade_tool() { printf '{"state":"absent","xray":"running","warp":false,"custom_rules":[]}'; }
cascade_action 3
''')
            master,slave=pty.openpty()
            process=subprocess.Popen(['bash','-x',str(script)],stdin=slave,stdout=slave,stderr=slave,
                env={**os.environ,'FIXTURE_ROOT':str(root),'NO_COLOR':'1','TERM':'dumb'},start_new_session=True)
            os.close(slave)
            output=bytearray();sent=0;deadline=time.monotonic()+10
            try:
                while time.monotonic()<deadline:
                    if select.select([master],[],[],.02)[0]:
                        try:
                            chunk=os.read(master,65536)
                        except OSError:
                            break
                        output.extend(chunk)
                    prompt=(b'Panel login (hidden):' if sent == 0 else b'Panel password (hidden,')
                    if sent<2 and prompt in output and not termios.tcgetattr(master)[3] & termios.ECHO:
                        os.write(master, (b'fixture-user\n' if sent==0 else b'fixture-password\n'));sent+=1
                    if process.poll() is not None:
                        break
                process.wait(timeout=2)
                self.assertEqual(sent,2,output.decode(errors='replace'))
                self.assertEqual(process.returncode,0,output.decode(errors='replace'))
                self.assertNotIn(b'fixture-user',output)
                self.assertNotIn(b'fixture-password',output)
                self.assertFalse(list(root.glob('stage.*')))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                os.close(master)


class CascadeManagerLock(unittest.TestCase):
    def test_real_lock_released_after_success_error_and_interrupt(self):
        self.assertEqual(os.geteuid(), 0, 'This class belongs to the root suite')
        source=(ROOT/'x-ui-latest.sh').read_text()
        lock_function=re.search(r'^acquire_stack_lock\(\) \{.*?^\}', source, re.M|re.S)[0]
        for outcome in ('success','error','prepare','cancel','interrupt'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                script=root/'action.sh'
                script.write_text('source '+str(ROOT/'x-ui-latest.sh')+'\n'+
                    lock_function.replace('/run/3x-ui-auto-nginx',str(root/'lock'))+'''
recover_domain_operation() { :; }
prepare_cascade_tools() { CASCADE_STAGE=$(mktemp -d "$FIXTURE_ROOT/stage.XXXXXX"); [[ $OUTCOME != prepare ]]; }
cascade_panel_context() { cascade_domain=panel.example; cascade_path=panel; }
cascade_tool() {
    if [[ $OUTCOME == interrupt ]]; then : > "$FIXTURE_ROOT/running"; sleep 30
    elif [[ $OUTCOME == error ]]; then printf '{"state":"failed","reason":"panel_request_failed"}'; return 1
    else printf '{"state":"absent"}'; fi
}
cascade_action 1
''')
                process=subprocess.Popen(['bash',str(script)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,text=True,start_new_session=True,
                    env={**os.environ,'FIXTURE_ROOT':str(root),'OUTCOME':outcome})
                try:
                    if outcome == 'interrupt':
                        process.stdin.write('fixture-user\nfixture-password\n');process.stdin.flush()
                        deadline=time.monotonic()+5
                        while not (root/'running').exists() and time.monotonic()<deadline:
                            time.sleep(.02)
                        self.assertTrue((root/'running').exists())
                        held=subprocess.run(['flock','-n',str(root/'lock/operation.lock'),'true'],capture_output=True)
                        self.assertNotEqual(held.returncode,0)
                        os.killpg(process.pid, signal.SIGINT)
                        output,errors=process.communicate(timeout=5)
                    else:
                        output,errors=process.communicate('' if outcome=='cancel' else 'fixture-user\nfixture-password\n',timeout=5)
                    self.assertEqual(process.returncode, {'success':0,'error':1,'prepare':1,'cancel':0,'interrupt':130}[outcome], output+errors)
                    unlocked=subprocess.run(['flock','-n',str(root/'lock/operation.lock'),'true'],capture_output=True)
                    self.assertEqual(unlocked.returncode,0)
                    self.assertFalse(list(root.glob('stage.*')))
                    self.assertNotIn('fixture-password',output+errors)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid,signal.SIGKILL);process.communicate()
