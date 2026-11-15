"""Fresh-install WARP transaction; Cloudflare registration is always a fixture."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
from types import SimpleNamespace

from test_personal_xhttp import ROOT, SOURCE, function
from release_contract import baseline


def helper(name):
    spec = importlib.util.spec_from_file_location('warp_test_' + name, ROOT/'assets'/name/'managed.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ORIGINAL = dict(outbounds=[dict(tag='direct', protocol='freedom'), dict(tag='blocked', protocol='blackhole')],
                routing=dict(domainStrategy='AsIs', rules=[
                    dict(type='field', inboundTag=['api'], outboundTag='api'),
                    dict(type='field', ip=['geoip:private'], outboundTag='blocked'),
                    dict(type='field', protocol=['bittorrent'], outboundTag='blocked')]),
                inbounds=[dict(tag='api')], dns=dict(servers=['fixture']), custom=dict(keep=[1, 2]))
REGISTRATION = dict(privateKey='fixture-private-key\n+&=', publicKey='fixture-public-key',
                    address=['172.16.0.2'], endpoint='fixture-endpoint')
RU3 = ['domain:ipify.org', 'domain:ifconfig.me', 'full:checkip.amazonaws.com', 'domain:ipapi.is',
       'domain:iplocate.io', 'domain:ip.sb', 'domain:2gis.com']
DOMAINS = ['yandex.ru', 'api.ipify.org', 'ifconfig.me', 'checkip.amazonaws.com', 'api.ipapi.is',
           'www.iplocate.io', 'api.ip.sb', 'relay-api.eu.2gis.com']


class FakePanel:
    def __init__(self, fault=''):
        self.template = copy.deepcopy(ORIGINAL)
        self.calls = []
        self.fault = fault
        self.registrations = 0

    def request(self, path, data=None, **kwargs):
        self.calls.append((path, copy.deepcopy(data), kwargs))
        if path == 'panel/api/xray/':
            value = self.template
            if self.fault == 'readback' and any(o['tag'] == 'warp-masque' for o in value['outbounds']):
                value = copy.deepcopy(value); value['custom'] = 'changed'
            return dict(success=True, obj=json.dumps(dict(xraySetting=value, outboundTestUrl='https://fixture.test/a?x=1&y=2')))
        if path.endswith('/regMasque'):
            self.registrations += 1
            if self.fault == 'registration': raise ValueError('fixture-private-key')
            if self.fault == 'registration-timeout': raise subprocess.TimeoutExpired('curl', 45)
            reg = copy.deepcopy(REGISTRATION)
            if self.fault == 'incomplete': reg['address'] = []
            if self.fault.startswith('incomplete-'): reg.pop(self.fault.removeprefix('incomplete-'))
            return dict(success=True, obj=json.dumps(reg))
        if path.endswith('/testOutbound'):
            result = dict(tag='warp-masque', success=True, delay=1, mode='real', httpStatus=503)
            if self.fault == 'probe': result.update(success=False, error='fixture-private-key')
            return dict(success=True, obj=result)
        if path.endswith('/update'):
            self.template = json.loads(data['xraySetting'])
            if self.fault == 'save': raise ValueError('fixture-private-key')
            return dict(success=True)
        if path.endswith('/routeTest'):
            control = data.get('domain') in ('example.com', 's3.amazonaws.com')
            result = dict(matched=not control, outboundTag='' if control else 'warp-masque')
            if self.fault == 'route': result['outboundTag'] = 'direct'
            if self.fault == 'control' and control: result.update(matched=True, outboundTag='warp-masque')
            if self.fault == 'route-format': result = dict(outbound='warp-masque')
            if self.fault == 'route-timeout': raise subprocess.TimeoutExpired('curl', 15)
            return dict(success=True, obj=result)
        if path.endswith('/restartXrayService'):
            if self.fault == 'restart': raise ValueError('fixture-private-key')
            return dict(success=True)
        raise AssertionError(path)


class Warp(unittest.TestCase):
    def test_prompt_defaults_eof_invalid_and_no_python_or_stage(self):
        release = SOURCE[SOURCE.index('verified_panel_release() {'):SOURCE.index('\nbootstrap_panel_dependencies()')]
        source = release + '\n' + '\n'.join(function(n) for n in ('ui_note', 'select_warp_ru'))
        source += '\npython3() { echo FORBIDDEN >&2; return 99; }; unset PANEL_STAGE; select_warp_ru; echo RESULT:$INSTALL_WARP_RU:$WARP_RESULT'
        for lang in ('ru', 'en'):
            for answer, expected in (('', 'n'), ('\n', 'y' if lang == 'ru' else 'n'), ('n\n', 'n'),
                                     ('y\n', 'y'), ('bad\nY\n', 'y'), ('bad\n', 'n')):
                result = subprocess.run(['bash', '-eu', '-c', source], input=answer, text=True, capture_output=True,
                                        env={**os.environ, 'UI_LANG': lang})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn('FORBIDDEN', result.stderr)
                self.assertIn('RESULT:'+expected+':not_requested', result.stdout)
                self.assertIn('[Y/n]' if lang == 'ru' else '[y/N]', result.stdout)
                if answer.startswith('bad'):
                    self.assertIn('Введите y или n.' if lang == 'ru' else 'Please enter y or n.', result.stdout)

    def test_explicit_other_version_skips_question_and_preserves_stdin(self):
        release = SOURCE[SOURCE.index('verified_panel_release() {'):SOURCE.index('\nbootstrap_panel_dependencies()')]
        text = release + '\n' + '\n'.join(function(n) for n in ('ui_note', 'select_warp_ru'))
        text += '\nselect_warp_ru; IFS= read -r untouched; echo RESULT:$INSTALL_WARP_RU:$untouched'
        for lang in ('ru', 'en'):
            result = subprocess.run(['bash', '-eu', '-c', text], input='keep\n', text=True, capture_output=True,
                                    env={**os.environ, 'PANEL_VERSION': 'v0.0.0', 'UI_LANG': lang})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('RESULT:n:keep', result.stdout)
            self.assertEqual(len(result.stdout.splitlines()), 2)
            self.assertNotIn('[y/N]', result.stdout); self.assertNotIn('[Y/n]', result.stdout)
        text = text[:text.index('\nselect_warp_ru;')]+'\nselect_warp_ru; echo RESULT:$INSTALL_WARP_RU'
        for version in (baseline()['version'], baseline()['version'].removeprefix('v')):
            result = subprocess.run(['bash', '-eu', '-c', text], input='y\n', text=True, capture_output=True,
                                    env={**os.environ, 'PANEL_VERSION': version})
            self.assertEqual(result.returncode, 0, result.stderr); self.assertIn('RESULT:y', result.stdout)

    def test_merge_exact_rules_order_and_native_masque_shape(self):
        warp = helper('warp'); original = copy.deepcopy(ORIGINAL)
        merged = warp.merge(original, REGISTRATION)
        self.assertEqual(original, ORIGINAL)
        self.assertEqual(merged['outbounds'][:-1], ORIGINAL['outbounds'])
        self.assertEqual(merged['outbounds'][0]['tag'], 'direct')
        self.assertEqual(merged['routing']['rules'][:-3], ORIGINAL['routing']['rules'])
        self.assertEqual(merged['routing']['rules'][-3:], [
            dict(type='field', domain=['geosite:category-ru'], outboundTag='warp-masque', comment='WARP - RU', enabled=True),
            dict(type='field', ip=['geoip:ru'], outboundTag='warp-masque', comment='WARP - RU2', enabled=True),
            dict(type='field', domain=RU3, outboundTag='warp-masque', comment='WARP - RU3', enabled=True)])
        self.assertEqual(list(warp.RU3_DOMAINS), RU3)
        self.assertTrue(all(x.startswith(('domain:', 'full:')) for x in warp.RU3_DOMAINS))
        outbound = merged['outbounds'][-1]
        self.assertEqual(outbound, dict(tag='warp-masque', protocol='masque', settings=dict(address='fixture-endpoint', port=443),
            streamSettings=dict(network='masque', security='tls', tlsSettings=dict(serverName='consumer-masque.cloudflareclient.com', alpn=['h3']),
                                masqueSettings=dict(warp={k: REGISTRATION[k] for k in ('privateKey', 'publicKey', 'address')}))))
        # WARP's nested block contains only keys and interface addresses, not endpoint.
        self.assertNotIn('endpoint', outbound['streamSettings']['masqueSettings']['warp'])
        restored = copy.deepcopy(merged)
        restored['outbounds'].pop(); del restored['routing']['rules'][-3:]
        self.assertEqual(restored, ORIGINAL)

    def test_apply_before_write_failures_never_save_and_registration_not_retried(self):
        warp = helper('warp')
        for fault in ('registration', 'registration-timeout', 'incomplete', 'incomplete-privateKey',
                      'incomplete-publicKey', 'incomplete-endpoint', 'incomplete-address', 'probe'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as d:
                panel = FakePanel(fault)
                self.assertEqual(warp.apply(panel, Path(d)), 'failed')
                self.assertEqual(panel.template, ORIGINAL); self.assertEqual(panel.registrations, 1)
                self.assertFalse((Path(d)/'save-attempted').exists())
                self.assertFalse(any(p.endswith('/update') for p, _, _ in panel.calls))

    def test_existing_tags_comments_and_bad_structure_fail_before_registration(self):
        warp = helper('warp')
        bad = [dict(outbounds=None, routing=dict(rules=[])), dict(outbounds=[], routing=dict(rules=None))]
        for comment in ('WARP - RU', 'WARP - RU2', 'WARP - RU3'):
            value = copy.deepcopy(ORIGINAL); value['routing']['rules'].append(dict(comment=comment)); bad.append(value)
        value = copy.deepcopy(ORIGINAL); value['outbounds'].append(dict(tag='warp-masque')); bad.append(value)
        for template in bad:
            with tempfile.TemporaryDirectory() as d:
                panel = FakePanel(); panel.template = copy.deepcopy(template)
                self.assertEqual(warp.apply(panel, Path(d)), 'failed')
                self.assertEqual(panel.template, template); self.assertEqual(panel.registrations, 0)

    def test_success_form_requests_routes_and_snapshot_contains_no_warp_key(self):
        warp = helper('warp')
        with tempfile.TemporaryDirectory() as d:
            panel = FakePanel(); stage = Path(d)
            self.assertEqual(warp.apply(panel, stage), 'applied_pending_health')
            self.assertEqual(panel.template, warp.merge(ORIGINAL, REGISTRATION))
            for file in stage.iterdir():
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                self.assertNotIn(REGISTRATION['privateKey'], file.read_text())
            calls = panel.calls
            for path, body, options in calls:
                self.assertEqual(options['method'], 'POST')
                if path.endswith(('/update', '/testOutbound', '/routeTest')): self.assertTrue(options['form'])
                elif path.endswith(('/regMasque', '/xray/')): self.assertIsNone(body)
            route = [body for p, body, _ in calls if p.endswith('/routeTest')]
            self.assertEqual([r['domain'] for r in route if 'domain' in r], DOMAINS+['example.com', 's3.amazonaws.com'])
            self.assertIn(dict(ip='77.88.55.88', network='tcp', port=443), route)
            self.assertTrue(all(r['network']=='tcp' and r['port']==443 for r in route))
            self.assertTrue(all(o['timeout']==10 for p, _, o in calls if p.endswith('/routeTest')))
            self.assertEqual(next(o['timeout'] for p, _, o in calls if p.endswith('/regMasque')), 40)
            self.assertEqual(next(o['timeout'] for p, _, o in calls if p.endswith('/testOutbound')), 30)
            self.assertEqual(warp.rollback(panel, stage), 'restored_pending_health')
            self.assertEqual(panel.template, ORIGINAL)
            self.assertEqual(sum(p.endswith('/restartXrayService') for p, _, _ in calls), 1)

    def test_save_readback_and_route_failures_require_shell_rollback(self):
        warp = helper('warp')
        for fault in ('save', 'readback', 'route', 'control', 'route-format', 'route-timeout'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as d:
                panel = FakePanel(fault); stage = Path(d)
                self.assertEqual(warp.apply(panel, stage), 'failed_needs_rollback')
                self.assertTrue((stage/'save-attempted').exists())
                self.assertFalse(any(p.endswith('/restartXrayService') for p, _, _ in panel.calls))
                panel.fault = ''
                self.assertEqual(warp.rollback(panel, stage), 'restored_pending_health')
                self.assertEqual(panel.template, ORIGINAL)

    def test_probe_parser_checks_inner_success_and_accepts_http_errors(self):
        warp = helper('warp')
        good = dict(success=True, tag='warp-masque', mode='real', delay=1, httpStatus=204)
        for status in (204, 404, 503):
            self.assertTrue(warp.probe_ok(good | dict(httpStatus=status)))
        for bad in (None, [], good | dict(success=False), good | dict(delay=0), good | dict(delay=True),
                    good | dict(error='private'), good | dict(mode='tcp'), good | dict(tag='direct'),
                    good | dict(httpStatus=0)):
            self.assertFalse(warp.probe_ok(bad))

    def test_rollback_requires_restart_and_exact_readback(self):
        warp = helper('warp')
        for fault in ('restart', 'readback'):
            with tempfile.TemporaryDirectory() as d:
                panel = FakePanel(); stage = Path(d)
                self.assertEqual(warp.apply(panel, stage), 'applied_pending_health')
                if fault == 'readback':
                    original_request = panel.request
                    def request(path, data=None, **options):
                        if path == 'panel/api/xray/':
                            return dict(success=True, obj=json.dumps(dict(xraySetting=dict(wrong=True), outboundTestUrl='wrong')))
                        return original_request(path, data, **options)
                    panel.request = request
                else: panel.fault = fault
                self.assertEqual(warp.rollback(panel, stage), 'failed_unverified')

    def test_panel_legacy_json_bodyless_post_urlencoded_and_deadline(self):
        api = helper('amneziawg')
        with tempfile.TemporaryDirectory() as d:
            replies = [dict(success=True, obj='fixture-csrf'), dict(success=True), dict(success=True, obj='fixture-csrf')]
            with patch.object(api.subprocess, 'run', side_effect=[subprocess.CompletedProcess([],0,json.dumps(r).encode()) for r in replies]) as run:
                panel = api.Panel('https://fixture.test/panel/', 'fixture-user', 'fixture-password', d)
                self.assertEqual(run.call_args_list[0].kwargs['timeout'], 25)
                self.assertIn('20', run.call_args_list[0].args[0])
                self.assertIn('Content-Type: application/json', run.call_args_list[1].args[0])
            with patch.object(api.subprocess, 'run', return_value=subprocess.CompletedProcess([],0,b'{"success":true}')) as run:
                panel.request('panel/api/xray/', method='POST')
                argv = run.call_args.args[0]
                self.assertIn('POST', argv); self.assertNotIn('--data-binary', argv)
                self.assertIsNone(run.call_args.kwargs['input'])
                for timeout in (20, 40, 30, 10):
                    panel.request('panel/api/xray/update', dict(xraySetting='{"privateKey":"a+b&=\\n"}'), method='POST', form=True, timeout=timeout)
                    argv = run.call_args.args[0]
                    self.assertEqual([a for a in argv if a.startswith('Content-Type:')], ['Content-Type: application/x-www-form-urlencoded'])
                    self.assertEqual(parse_qs(run.call_args.kwargs['input'].decode())['xraySetting'], ['{"privateKey":"a+b&=\\n"}'])
                    self.assertEqual(argv[argv.index('--max-time')+1], str(timeout))
                    self.assertEqual(run.call_args.kwargs['timeout'], timeout+5)
                    self.assertNotIn('privateKey', ' '.join(argv))
                panel.deadline = 102
                with patch.object(api.time, 'monotonic', return_value=100):
                    panel.request('reg', method='POST', timeout=40)
                self.assertEqual(run.call_args.kwargs['timeout'], 2)
                self.assertEqual(float(run.call_args.args[0][run.call_args.args[0].index('--max-time')+1]), 2)
                run.reset_mock()
                with patch.object(api.time, 'monotonic', return_value=102), self.assertRaises(TimeoutError):
                    panel.request('reg', method='POST', timeout=40)
                run.assert_not_called()

    def test_shell_transaction_all_health_and_rollback_combinations(self):
        cases = [('failed', '1', 'restored_pending_health', 'failed', 1, ['apply']),
                 ('applied_pending_health', '1', 'restored_pending_health', 'configured', 0, ['apply'])]
        for apply in ('applied_pending_health', 'failed_needs_rollback'):
            for restored in (True, False):
                for healthy in (True, False):
                    health = ('0' if apply == 'applied_pending_health' else '')+('1' if healthy else '0')
                    result = 'failed_rolled_back' if restored and healthy else 'failed_unverified'
                    cases.append((apply, health, 'restored_pending_health' if restored else 'failed_unverified',
                                  result, 1, ['apply', 'rollback']))
        # A dead helper's empty output is reconciled from its before-save marker.
        cases.append(('', '1', 'restored_pending_health', 'failed_rolled_back', 1, ['apply', 'rollback']))
        for apply, health, rollback, expected, code, calls in cases:
            with self.subTest(apply=apply, health=health, rollback=rollback), tempfile.TemporaryDirectory() as d:
                stage = Path(d)
                (stage/'managed-warp.py').write_text('''import os,sys
from pathlib import Path
assert sys.stdin.read() == 'fixture-user\\0fixture-password'
assert not any('fixture-password' in a for a in sys.argv)
mode=sys.argv[1]
with open(os.environ['CALLS'],'a') as f: f.write(mode+'\\n')
status=os.environ['APPLY'] if mode=='apply' else os.environ['ROLLBACK']
if mode=='apply' and status!='failed': (Path(sys.argv[-1])/'save-attempted').touch()
print(status)
sys.exit(0 if status in ('applied_pending_health','restored_pending_health') else 1)
''')
                script = '''health_index=0
check_xray_runtime() { return 0; }
check_installation() {
    local value=${HEALTH:$health_index:1}
    health_index=$((health_index+1))
    [[ "$value" == 1 ]]
}
'''+function('install_warp_ru')+'''
code=0; install_warp_ru || code=$?
printf 'RESULT:%s:%s\\n' "$WARP_RESULT" "$health_index"
exit "$code"
'''
                result = subprocess.run(['bash','-eu','-c',script], text=True, capture_output=True,
                    env={**os.environ, 'INSTALL_WARP_RU':'y','PANEL_STAGE':d,'AWG_HELPER':'unused',
                         'domain':'fixture.test','panel_path':'panel','config_username':'fixture-user',
                         'config_password':'fixture-password','CALLS':str(stage/'calls'),
                         'APPLY':apply,'ROLLBACK':rollback,'HEALTH':health})
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn('RESULT:'+expected+':', result.stdout)
                self.assertEqual((stage/'calls').read_text().splitlines(), calls)
                self.assertEqual(list(stage.glob('warp.*')), [])
                self.assertNotIn('fixture-password', result.stdout+result.stderr)

    def test_decline_and_stopped_xray_do_not_run_helper(self):
        for enabled, code, expected in (('n',0,'not_requested'), ('y',1,'failed')):
            script = '''check_xray_runtime() { return 1; }
python3() { echo MUTATION; return 99; }
WARP_RESULT=not_requested
'''+function('install_warp_ru')+'''
code=0; install_warp_ru || code=$?; echo RESULT:$WARP_RESULT; exit "$code"
'''
            result = subprocess.run(['bash','-eu','-c',script], capture_output=True,text=True,
                                    env={**os.environ,'INSTALL_WARP_RU':enabled})
            self.assertEqual(result.returncode,code,result.stderr)
            self.assertIn('RESULT:'+expected,result.stdout); self.assertNotIn('MUTATION',result.stdout)

    def test_preflight_selected_ref_shared_helper_reuse_failure_and_syntax(self):
        for requested, fault in (('n',''),('y',''),('y','reuse'),('y','download'),('y','warp-download'),('y','syntax')):
            with self.subTest(requested=requested,fault=fault), tempfile.TemporaryDirectory() as d:
                root = Path(d); stage=root/'stage'; stage.mkdir(mode=0o700)
                source=root/'warp.py'; source.write_text('this is invalid python !!!' if fault=='syntax' else '"""fixture helper"""\n')
                if fault=='reuse': (stage/'managed-amneziawg.py').write_text('existing shared helper')
                script = '''curl() {
    local url=${@: -3:1} target=${!#}
    echo "$url" >> "$CALLS"
    [[ "$FAULT" != download ]] || return 1
    [[ "$FAULT" != warp-download || "$url" != */warp/* ]] || return 1
    if [[ "$url" == */amneziawg/* ]]; then cp "$API" "$target"
    else cp "$WARP" "$target"; fi
}
preflight_vision_artifacts() { :; }
msg_err() { printf '%s\\n' "$*" >&2; }
'''+function('preflight_integrated_features')+'\npreflight_integrated_features'
                ref='a'*40; base='https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/'+ref
                result=subprocess.run(['bash','-eu','-c',script],capture_output=True,text=True,
                    env={**os.environ,'INSTALL_WARP_RU':requested,'INSTALL_SECURITY':'n','INSTALL_VISION':'n',
                         'CREATE_CLIENT':'n','PANEL_STAGE':str(stage),'GITHUB_RAW':base,'CALLS':str(root/'calls'),
                         'FAULT':fault,'API':str(ROOT/'assets/amneziawg/managed.py'),'WARP':str(source)})
                self.assertEqual(result.returncode,1 if requested=='y' and fault in ('download','warp-download','syntax') else 0,result.stderr)
                calls=(root/'calls').read_text().splitlines() if (root/'calls').exists() else []
                self.assertTrue(all(url.startswith(base+'/assets/') for url in calls))
                self.assertEqual(sum('/warp/' in url for url in calls), 0 if requested=='n' or fault=='download' else 1)
                if requested=='n': self.assertEqual(calls,[])
                if fault=='reuse':
                    self.assertEqual((stage/'managed-amneziawg.py').read_text(),'existing shared helper')
                    self.assertFalse(any('/amneziawg/' in url for url in calls))

    def test_summary_five_states_both_languages_and_recovery_instruction(self):
        for language in ('ru','en'):
            for state in ('not_requested','configured','failed','failed_rolled_back','failed_unverified'):
                script = '''msg_ok() { printf '%s\\n' "$*"; }
msg_warn() { printf '%s\\n' "$*"; }
msg_err() { printf '%s\\n' "$*"; }
msg_inf() { printf '%s\\n' "$*"; }
ufw() { printf 'Status: inactive\\n'; }
timedatectl() { printf UTC; }
'''+function('show_results')+'\nshow_results 1'
                result = subprocess.run(['bash','-eu','-c',script],capture_output=True,text=True,
                    env={**os.environ,'UI_LANG':language,'WARP_RESULT':state,'UI_INTERACTIVE':'0',
                         'domain':'fixture.test','reality_domain':'other.test','panel_path':'panel',
                         'config_username':'fixture-user','config_password':'fixture-password'})
                self.assertEqual(result.returncode,0,result.stderr)
                rows=[s for s in result.stdout.splitlines() if 'Cloudflare WARP' in s]
                self.assertEqual(len(rows),0 if state=='not_requested' else 1)
                if state=='configured': self.assertIn('[✓]', rows[0]); self.assertIn('3 ',rows[0])
                if state.startswith('failed'):
                    self.assertIn('[!]',rows[0]); self.assertIn('Outbounds',result.stdout)
                if state in ('failed','failed_rolled_back'):
                    hint=(' WARP не настроен: российские сайты по-прежнему видят IP вашего VPS. Если он нужен, добавьте WARP в панели 3X-UI (Xray, Outbounds, WARP) и направьте на него нужные сайты в разделе Routing.'
                          if language=='ru' else ' WARP is not configured: Russian websites still see your VPS IP. If you need it, add WARP in the 3X-UI panel (Xray, Outbounds, WARP) and send the sites you need to it in Routing.')
                    self.assertIn(hint,result.stdout)
                    self.assertNotIn('Продолжите настройку' if language=='ru' else 'Continue',result.stdout)
                if state=='failed_unverified':
                    self.assertIn('WARP - RU3',result.stdout)
                    self.assertIn('Сохранить' if language=='ru' else 'Save',result.stdout)
                    self.assertIn('Работа после отката не подтверждена' if language=='ru' else 'Post-rollback health not verified',result.stdout)

    def test_configured_summary_warns_when_core_health_is_unverified(self):
        for language in ('ru','en'):
            for core in ('configured','failed_unverified'):
                script = """msg_ok() { echo "OK:$*"; }; msg_warn() { echo "WARN:$*"; }
msg_err() { echo "ERROR:$*"; }; msg_inf() { echo "$*"; }
ufw() { echo 'Status: inactive'; }; timedatectl() { echo UTC; }
"""+function('show_results')+'\nshow_results 1'
                result=subprocess.run(['bash','-eu','-c',script],capture_output=True,text=True,
                    env={**os.environ,'UI_LANG':language,'WARP_RESULT':'configured','CORE_RESULT':core,
                         'UI_INTERACTIVE':'0','domain':'fixture.test','reality_domain':'other.test',
                         'panel_path':'panel','config_username':'fixture-user','config_password':'fixture-password'})
                self.assertEqual(result.returncode,0,result.stderr)
                rows=[line for line in result.stdout.splitlines() if 'Cloudflare WARP' in line]
                self.assertEqual(len(rows),1)
                if core=='failed_unverified':
                    text=('Настроен, но работа основного стека не подтверждена: проверьте Xray в панели.'
                          if language=='ru' else 'Configured, but core health is not verified: check Xray in the panel.')
                    self.assertEqual(rows[0],'WARN: [!] Cloudflare WARP        '+text)
                    self.assertNotIn('идут через WARP',result.stdout)
                    self.assertNotIn('use WARP (3 rules)',result.stdout)
                else:
                    text=('Настроен: российские сайты и выбранные домены идут через WARP (3 правила)'
                          if language=='ru' else 'Configured: Russian sites and selected domains use WARP (3 rules)')
                    self.assertEqual(rows[0],'OK: [✓] Cloudflare WARP        '+text)

    def test_summary_does_not_claim_core_works_after_failed_final_gate(self):
        for language in ('ru','en'):
            for state in ('failed','failed_rolled_back'):
                script = '''msg_ok() { echo "$*"; }; msg_warn() { echo "$*"; }
msg_err() { echo "$*"; }; msg_inf() { echo "$*"; }
ufw() { echo 'Status: inactive'; }; timedatectl() { echo UTC; }
'''+function('show_results')+'\nshow_results 1'
                result=subprocess.run(['bash','-eu','-c',script],capture_output=True,text=True,
                    env={**os.environ,'UI_LANG':language,'WARP_RESULT':state,'CORE_RESULT':'failed_unverified',
                         'UI_INTERACTIVE':'0','domain':'fixture.test','reality_domain':'other.test',
                         'panel_path':'panel','config_username':'fixture-user','config_password':'fixture-password'})
                self.assertEqual(result.returncode,0,result.stderr)
                row=next(s for s in result.stdout.splitlines() if 'Cloudflare WARP' in s)
                self.assertNotIn('Основной стек работает' if language=='ru' else 'The core stack works',row)
                self.assertIn('не подтверждена' if language=='ru' else 'not verified',row)

    def test_cli_budgets_private_session_cleanup_and_safe_errors(self):
        warp=helper('warp')
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d); panel=FakePanel(); sessions=[]; deadlines=[]
            def factory(base,user,password,directory,options,*,deadline):
                self.assertEqual((user,password),('fixture-user','fixture-password'))
                self.assertEqual(Path(directory).stat().st_mode & 0o777,0o700)
                self.assertIn('--resolve',options); sessions.append(directory); deadlines.append(deadline)
                return panel
            spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
            for mode,budget,expected in (('apply',180,'applied_pending_health'),('rollback',60,'restored_pending_health')):
                output,errors=io.StringIO(),io.StringIO()
                with patch.object(warp.importlib.util,'spec_from_file_location',return_value=spec), \
                     patch.object(warp.importlib.util,'module_from_spec',return_value=SimpleNamespace(Panel=factory)), \
                     patch.object(warp.sys,'argv',['managed.py',mode,'unused','fixture.test','panel',d]), \
                     patch.object(warp.sys,'stdin',io.StringIO('fixture-user\0fixture-password')), \
                     patch.object(warp.time,'monotonic',return_value=100), patch.object(warp.signal,'alarm') as alarm, \
                     redirect_stdout(output),redirect_stderr(errors):
                    self.assertEqual(warp.main(),0)
                    self.assertEqual([c.args[0] for c in alarm.call_args_list],[budget,0])
                self.assertEqual(deadlines[-1],100+budget)
                self.assertEqual(output.getvalue().strip(),expected)
                self.assertEqual(errors.getvalue(),'')
                self.assertFalse(Path(sessions[-1]).exists())
                self.assertNotIn('fixture-private-key', ''.join(p.read_text() for p in stage.iterdir()))
            # API exception content must never become a traceback or diagnostic.
            (stage/'save-attempted').unlink()
            panel=FakePanel('registration')
            with redirect_stdout(output:=io.StringIO()), redirect_stderr(errors:=io.StringIO()):
                self.assertEqual(warp.apply(panel,stage),'failed')
            self.assertNotIn('fixture-private-key',output.getvalue()+errors.getvalue())
            def failed_login(*args, **kwargs):
                sessions.append(args[3])
                raise ValueError('fixture-password fixture-csrf fixture-private-key')
            with patch.object(warp.importlib.util,'spec_from_file_location',return_value=spec), \
                 patch.object(warp.importlib.util,'module_from_spec',return_value=SimpleNamespace(Panel=failed_login)), \
                 patch.object(warp.sys,'argv',['managed.py','apply','unused','fixture.test','panel',d]), \
                 patch.object(warp.sys,'stdin',io.StringIO('fixture-user\0fixture-password')), \
                 patch.object(warp.signal,'alarm'), redirect_stdout(output:=io.StringIO()), redirect_stderr(errors:=io.StringIO()):
                self.assertEqual(warp.main(),1)
            self.assertEqual(output.getvalue(),'failed\n')
            self.assertFalse(Path(sessions[-1]).exists())
            for secret in ('fixture-password','fixture-csrf','fixture-private-key'):
                self.assertNotIn(secret,output.getvalue()+errors.getvalue())

    def test_only_warp_flag_runs_final_gate_and_failure_remains_partial(self):
        names=('confirm_destructive_reinstall','validate_domains','select_security','select_vision','select_amneziawg',
            'select_adguard','select_client','select_xhttp_cdn','preflight_base_os','preflight_panel_release',
            'make_port','preflight_cover_sites','preflight_amneziawg','preflight_integrated_features','preflight_xhttp_cdn',
            'setup_swap','prepare_base_os','prepare_system_dns','cleanup_adguard','clean_previous_install',
            'install_packages','setup_firewall','get_server_ip','setup_acme_http','get_ssl_certs','install_panel',
            'install_fake_site','configure_nginx','configure_xui_db','install_clash_sub','install_diagnostics','tune_system',
            'install_backup_tool','setup_certificate_renewal','finish_initial_reboot','write_managed_state')
        stubs='\n'.join(n+'() { :; }' for n in names)+'''
select_warp_ru() { INSTALL_WARP_RU=y; }
install_warp_ru() { echo WARP; WARP_RESULT=$FIXTURE_RESULT; [[ "$WARP_RESULT" == configured ]]; }
check_installation() { echo HEALTH; }
systemctl() { :; }
x-ui() { :; }
show_results() { echo RESULT:$1:$WARP_RESULT; }
msg_warn() { :; }
'''
        for state in ('configured','failed','failed_rolled_back','failed_unverified'):
            result=subprocess.run(['bash','-eu','-c',stubs+function('main')+'\nmain'],capture_output=True,text=True,
                env={**os.environ,**{k:'n' for k in ('INSTALL_SECURITY','INSTALL_VISION','INSTALL_AWG','INSTALL_AGH',
                     'CREATE_CLIENT','INSTALL_XHTTP_CDN')},'FIXTURE_RESULT':state})
            self.assertEqual(result.returncode,0 if state=='configured' else 1,result.stderr)
            self.assertEqual(result.stdout.count('HEALTH'),2)
            self.assertLess(result.stdout.index('WARP'),result.stdout.rindex('HEALTH'))
            self.assertIn('RESULT:'+('0' if state=='configured' else '1')+':'+state,result.stdout)
        main=function('main')
        self.assertLess(main.index('select_xhttp_cdn ||'),main.index('select_warp_ru ||'))
        self.assertLess(main.index('select_warp_ru ||'),main.index('select_adguard ||'))
        self.assertLess(main.index('install_xhttp_cdn ||'),main.index('install_warp_ru ||'))
        self.assertLess(main.index('install_warp_ru ||'),main.index('install_initial_client ||'))
        self.assertNotIn('rollback',main)
