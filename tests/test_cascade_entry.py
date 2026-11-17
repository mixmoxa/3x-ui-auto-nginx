"""Cascade entry transactions against an in-memory panel, never a real exit."""
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
from urllib.parse import parse_qs

import test_cascade as exit_fixtures


TAG = 'cascade-exit'
COMMENTS = ('CASCADE - RU', 'CASCADE - RU2', 'CASCADE - EXIT')
ORIGINAL = dict(outbounds=[dict(tag='direct', protocol='freedom', settings={}),
                          dict(tag='blocked', protocol='blackhole')],
                routing=dict(domainStrategy='AsIs', rules=[
                    dict(type='field', inboundTag=['api'], outboundTag='api'),
                    dict(type='field', ip=['geoip:private'], outboundTag='blocked')]),
                dns=dict(servers=['fixture']), custom=dict(keep=[1, 2]))
SECRETS = ('fixture-user', 'fixture-password', exit_fixtures.IDENTITY, 'fixture-public-key', '0123')


def outbound(spider=None):
    reality = dict(serverName='reality.example', fingerprint='firefox',
                   publicKey='fixture-public-key', shortId='0123')
    if spider is not None:
        reality['spiderX'] = spider
    return dict(tag=TAG, protocol='vless', settings=dict(address='panel.example', port=443,
                id=exit_fixtures.IDENTITY, flow=exit_fixtures.FLOW, encryption='none'),
                streamSettings=dict(network='tcp', security='reality', realitySettings=reality))


def rules():
    return [dict(type='field', outboundTag=tag, comment=comment, enabled=True, **criterion)
            for tag, comment, criterion in zip(('direct', 'direct', TAG), COMMENTS,
                (dict(domain=['geosite:category-ru']), dict(ip=['geoip:ru']), dict(network='tcp,udp')))]


class FakePanel:
    def __init__(self, active=False, fault='', strings=False):
        self.template = copy.deepcopy(ORIGINAL)
        if active:
            self.template['outbounds'].append(outbound())
            self.template['routing']['rules'].extend(rules())
        self.test_url = 'https://www.google.com/generate_204'
        self.fault, self.strings = fault, strings
        self.calls, self.saves, self.reads = [], 0, 0
        self.probe = dict(tag=TAG, success=True, mode='real', delay=1, httpStatus=204)
        self.on_save = None

    def request(self, path, data=None, **options):
        self.calls.append((path, copy.deepcopy(data), options))
        if path == 'panel/api/xray/':
            self.reads += 1
            if self.fault == 'panel' or (self.fault == 'readback' and self.reads == 2):
                raise ValueError(' '.join(SECRETS))
            if self.fault == 'rollback-read' and self.saves:
                raise TimeoutError(' '.join(SECRETS))
            value = copy.deepcopy(self.template)
            if self.strings:
                for item in value['outbounds']:
                    if isinstance(item.get('settings'), dict):
                        item['settings'] = json.dumps(item['settings'])
                value = json.dumps(value)
            result = dict(xraySetting=value, outboundTestUrl=self.test_url, inboundTags=['api'])
            return dict(success=True, obj=json.dumps(result) if self.strings else result)
        if path.endswith('/testOutbound'):
            if self.fault == 'probe-timeout':
                raise subprocess.TimeoutExpired(['curl'], 30, stderr=' '.join(SECRETS))
            if self.fault == 'probe-api':
                raise ValueError(' '.join(SECRETS))
            return dict(success=True, obj=copy.deepcopy(self.probe))
        if path.endswith('/update'):
            self.saves += 1
            if self.fault == 'save-rejected' or (self.fault == 'rollback-save' and self.saves > 1):
                raise ValueError(' '.join(SECRETS))
            if self.fault != 'save-noop':
                self.template = json.loads(data['xraySetting'])
                self.test_url = data['outboundTestUrl']
            if self.on_save:
                self.on_save(self)
            if self.fault == 'save-partial' and self.saves == 1:
                raise TimeoutError(' '.join(SECRETS))
            return dict(success=True)
        if path.endswith('/routeTest'):
            if self.fault in ('route', 'rollback-save', 'rollback-read'):
                raise ValueError(' '.join(SECRETS))
            tag = 'direct' if data['domain'] == 'yandex.ru' else TAG
            if self.fault == 'route-wrong':
                tag = 'blocked'
            if self.fault == 'route-format':
                return dict(success=True, obj={})
            return dict(success=True, obj=dict(matched=self.fault != 'route-unmatched', outboundTag=tag))
        raise AssertionError(path)


class CascadeEntry(unittest.TestCase):
    def setUp(self):
        self.module = exit_fixtures.helper()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_entry(self, mode, panel, link=None):
        return self.module.execute_entry(mode, panel, link if link is not None else exit_fixtures.link())

    def assert_no_save(self, panel):
        self.assertEqual(panel.saves, 0)
        self.assertEqual(self.module.normalized(panel.template), ORIGINAL)

    def test_invalid_links_all_required_fields_never_request_panel(self):
        invalid = [('', 'wrong_scheme'), ('https://fixture.test', 'wrong_scheme'),
                   (exit_fixtures.link(identity='bad'), 'invalid_uuid'),
                   (exit_fixtures.link(identity=''), 'invalid_uuid'),
                   (exit_fixtures.link().replace('panel.example', ''), 'missing_host')]
        for port in ('', 'bad', '0', '-1', '65536'):
            invalid.append((exit_fixtures.link(port=port), 'invalid_port'))
        for key, value in (('encryption', 'auto'), ('security', 'tls'), ('type', 'ws'),
                           ('flow', 'xtls-rprx-vision-udp443')):
            invalid.append((exit_fixtures.link(**{key: value}), 'invalid_' + key))
        for key in ('encryption', 'security', 'type', 'flow', 'sni', 'pbk', 'sid', 'fp'):
            for value in (None, '', ' '):
                invalid.append((exit_fixtures.link(**{key: value}), 'invalid_' + key))
            invalid.append((exit_fixtures.link().replace('#cascade', '&' + key + '=extra#cascade'), 'invalid_' + key))
        invalid.append(('vless://bad@[broken:443', 'malformed_link'))
        for link, reason in invalid:
            with self.subTest(reason=reason):
                panel = FakePanel()
                self.assertEqual(self.run_entry('entry-connect', panel, link), dict(state='link_invalid', reason=reason))
                self.assertEqual(panel.calls, [])

    def test_valid_ports_ipv6_optional_parameters_and_spider(self):
        for port in (1, 8443, 65535):
            panel = FakePanel()
            self.assertEqual(self.run_entry('entry-connect', panel, exit_fixtures.link(port=port))['state'], 'connected')
            self.assertEqual(panel.template['outbounds'][-1]['settings']['port'], port)
        panel = FakePanel()
        link = exit_fixtures.link(spx='/a?b=1&c=2', optional='ignored').replace('panel.example:', '[2001:db8::1]:')
        self.assertEqual(self.run_entry('entry-connect', panel, link)['state'], 'connected')
        expected = outbound('/a?b=1&c=2')
        expected['settings']['address'] = '2001:db8::1'
        self.assertEqual(panel.template['outbounds'][-1], expected)

    def test_exact_outbound_rules_at_end_and_unchanged_foreign_template(self):
        for strings in (False, True):
            panel = FakePanel(strings=strings)
            self.assertEqual(self.run_entry('entry-connect', panel), dict(state='connected'))
            expected = copy.deepcopy(ORIGINAL)
            expected['outbounds'].append(outbound())
            expected['routing']['rules'].extend(rules())
            self.assertEqual(self.module.normalized(panel.template), expected)
            probe = next((b, o) for p, b, o in panel.calls if p.endswith('/testOutbound'))
            self.assertEqual(probe, (dict(outbound=json.dumps(outbound()), mode='real'),
                                    dict(method='POST', form=True, timeout=30)))
            self.assertEqual(panel.saves, 1)
            routes = [(b, o) for p, b, o in panel.calls if p.endswith('/routeTest')]
            self.assertEqual(routes, [(dict(network='tcp', port=443, domain=d),
                                      dict(method='POST', form=True, timeout=10)) for d in ('yandex.ru', 'example.com')])
            for path, _, options in panel.calls:
                self.assertEqual(options['method'], 'POST')
                if path.endswith('/update'):
                    self.assertIs(options['form'], True)

    def test_already_connected_any_owned_element_never_changes_template(self):
        for item in [dict(tag=TAG)] + [dict(comment=c) for c in COMMENTS]:
            panel = FakePanel()
            if 'tag' in item:
                panel.template['outbounds'].append(item)
            else:
                panel.template['routing']['rules'].append(item)
            original = copy.deepcopy(panel.template)
            self.assertEqual(self.run_entry('entry-connect', panel), dict(state='already_connected'))
            self.assertEqual(panel.template, original)
            self.assertEqual(panel.saves, 0)

    def test_warp_tag_and_each_comment_block_connect(self):
        for item in [dict(tag='warp-masque')] + [dict(comment=c) for c in ('WARP - RU', 'WARP - RU2', 'WARP - RU3')]:
            panel = FakePanel()
            if 'tag' in item:
                panel.template['outbounds'].append(item)
            else:
                panel.template['routing']['rules'].append(item)
            original = copy.deepcopy(panel.template)
            self.assertEqual(self.run_entry('entry-connect', panel), dict(state='warp_active'))
            self.assertEqual(panel.template, original)
            self.assertEqual(panel.saves, 0)

    def test_catchall_network_shapes_and_empty_conditions_intercept(self):
        for network in (None, '', 'tcp', 'TCP,udp', ['udp', 'tcp'], []):
            panel = FakePanel()
            panel.template['routing']['rules'].append(dict(outboundTag='direct', network=network, domain=[]))
            self.assertEqual(self.run_entry('entry-connect', panel), dict(state='intercepted', rule_index=2))
            self.assertEqual(panel.saves, 0)

    def test_conditions_disabled_api_udp_and_unknown_field_are_not_universal(self):
        conditions = dict(domain=['full:fixture.test'], ip=['192.0.2.1'], port='443', sourcePort='1000',
            source=['192.0.2.2'], user=['fixture'], inboundTag=['inbound-1'], protocol=['http'], attrs={'x': 'y'},
            localIP=['127.0.0.1'], localPort='8080', vlessRoute='1', process=['fixture'],
            domains=['full:fixture.test'], sourceIP=['192.0.2.2'], localOS=['linux'])
        candidates = [dict(outboundTag='direct', **{k: v}) for k, v in conditions.items()]
        candidates += [dict(outboundTag='direct', network='udp'), dict(outboundTag='direct', enabled=False),
                       dict(outboundTag='api', inboundTag=['api']), dict(outboundTag='direct', futureField='unknown')]
        for rule in candidates:
            with self.subTest(rule=rule):
                panel = FakePanel()
                panel.template['routing']['rules'].append(rule)
                self.assertEqual(self.run_entry('entry-connect', panel)['state'], 'connected')

    def test_unreadable_network_refuses_with_index(self):
        for network in (True, 7, {}, ['tcp', 1]):
            panel = FakePanel()
            panel.template['routing']['rules'].append(dict(outboundTag='direct', network=network))
            self.assertEqual(self.run_entry('entry-connect', panel),
                             dict(state='failed', reason='invalid_network', rule_index=2))
            self.assertEqual(panel.saves, 0)

    def test_alias_precedence_and_unreadable_rule(self):
        panel = FakePanel()
        panel.template['routing']['rules'].append(dict(outboundTag='direct', domain=['full:fixture'], domains=[]))
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='intercepted', rule_index=2))
        panel = FakePanel()
        panel.template['routing']['rules'].append('unreadable fixture rule')
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='failed', reason='invalid_rule', rule_index=2))

    def test_api_exception_requires_an_array_of_inbound_tags(self):
        panel = FakePanel()
        # This is not the native api->api rule; do not exclude it in readback.
        panel.template['routing']['rules'].append(dict(outboundTag='api', inboundTag='api-admin'))
        def change(p):
            if p.saves == 1:
                p.template['routing']['rules'][2]['inboundTag'] = 'api-other'
        panel.on_save = change
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='failed', reason='readback_mismatch'))

    def test_missing_direct_never_tests_or_saves(self):
        panel = FakePanel()
        panel.template['outbounds'].pop(0)
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='failed', reason='missing_direct'))
        self.assertEqual(len(panel.calls), 1)

    def test_strict_probe_rejects_status_failures_missing_status_and_bad_contract(self):
        good = FakePanel().probe
        bad = [good | dict(httpStatus=v) for v in (0, 199, 300, 301, 404, 503, '204', True, None)]
        bad += [None, [], {}, {k:v for k,v in good.items() if k != 'httpStatus'},
                good | dict(success=False), good | dict(error=' '.join(SECRETS)), good | dict(mode='tcp'),
                good | dict(tag='direct'), good | dict(delay=0), good | dict(delay=True)]
        for result in bad:
            panel = FakePanel()
            panel.probe = result
            self.assertEqual(self.run_entry('entry-connect', panel), dict(state='test_failed', reason='outbound_test_failed'))
            self.assert_no_save(panel)
        for fault in ('probe-timeout', 'probe-api'):
            panel = FakePanel(fault=fault)
            self.assertEqual(self.run_entry('entry-connect', panel)['state'], 'test_failed')
            self.assert_no_save(panel)
        for status in (200, 204, 299):
            panel = FakePanel()
            panel.probe['httpStatus'] = status
            self.assertEqual(self.run_entry('entry-connect', panel)['state'], 'connected')

    def test_panel_normalization_extra_service_keys_and_settings_strings_are_accepted(self):
        panel = FakePanel()
        def normalize(p):
            p.template = dict(reversed(list(p.template.items())))
            p.template['metrics'] = {'listen': '127.0.0.1:11111'}
            p.template['panelFixtureService'] = True
            for item in p.template['outbounds']:
                if 'settings' in item:
                    item['settings'] = json.dumps(dict(reversed(list(item['settings'].items()))))
            p.template['outbounds'][-1]['panelNote'] = 'generated'
            p.template['routing']['rules'][-1]['ruleTag'] = 'generated'
            p.template['routing']['rules'][0]['enabled'] = True
        panel.on_save = normalize
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='connected'))
        self.assertEqual(panel.saves, 1)

    def test_string_settings_are_saved_as_native_xray_objects(self):
        panel = FakePanel(strings=True)
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='connected'))
        saved = next(json.loads(body['xraySetting']) for path, body, _ in panel.calls if path.endswith('/update'))
        self.assertEqual(saved['outbounds'][0]['settings'], {})
        self.assertEqual(saved['outbounds'][-1], outbound())
        self.assertEqual(self.run_entry('entry-disable', panel), dict(state='removed'))
        self.assertEqual(panel.template, ORIGINAL)

    def test_readback_detects_own_field_rule_order_and_foreign_list_changes(self):
        def own(p): p.template['outbounds'][-1]['settings']['port'] = 444
        def order(p): p.template['routing']['rules'][-3:] = list(reversed(p.template['routing']['rules'][-3:]))
        def extra(p): p.template['routing']['rules'].append(dict(outboundTag='direct', domain=['full:admin.test']))
        def foreign(p): p.template['outbounds'][0]['settings']['admin'] = True
        def foreign_order(p): p.template['outbounds'][:2] = list(reversed(p.template['outbounds'][:2]))
        for mutation in (own, order, extra, foreign, foreign_order):
            panel = FakePanel()
            panel.on_save = lambda p: mutation(p) if p.saves == 1 else None
            result = self.run_entry('entry-connect', panel)
            self.assertEqual(result, dict(state='failed', reason='readback_mismatch'))
            self.assertEqual(self.run_entry('entry-status', panel)['state'], 'absent')

    def test_save_readback_and_route_failures_roll_back(self):
        for fault, reason in (('save-rejected', 'save_failed'), ('save-partial', 'save_failed'),
                ('readback', 'readback_failed'), ('route', 'route_test_failed'), ('route-wrong', 'route_test_failed'),
                ('route-format', 'route_test_failed'), ('route-unmatched', 'route_test_failed')):
            with self.subTest(fault=fault):
                panel = FakePanel(fault=fault)
                self.assertEqual(self.run_entry('entry-connect', panel), dict(state='failed', reason=reason))
                self.assertEqual(self.module.normalized(panel.template), ORIGINAL)

    def test_rollback_retains_concurrent_admin_edits_and_fresh_test_url(self):
        panel = FakePanel(fault='route')
        def admin(p):
            if p.saves == 1:
                p.template['dns']['admin'] = 'kept'
                p.template['outbounds'].insert(0, dict(tag='admin', protocol='freedom'))
                p.template['routing']['rules'].insert(1, dict(outboundTag='blocked', domain=['full:admin.test']))
                p.test_url = 'https://admin.example/generate_204'
        panel.on_save = admin
        self.assertEqual(self.run_entry('entry-connect', panel)['state'], 'failed')
        self.assertEqual(panel.template['dns']['admin'], 'kept')
        self.assertEqual(panel.template['outbounds'][0]['tag'], 'admin')
        self.assertEqual(panel.template['routing']['rules'][1]['domain'], ['full:admin.test'])
        self.assertEqual(panel.test_url, 'https://admin.example/generate_204')
        self.assertEqual(self.run_entry('entry-status', panel)['state'], 'absent')

    def test_failed_rollback_when_save_read_or_verification_fails(self):
        for fault in ('rollback-save', 'rollback-read'):
            panel = FakePanel(fault=fault)
            result = self.run_entry('entry-connect', panel)
            self.assertEqual(result['state'], 'failed_rollback')
            self.assertIs(result['config_may_contain_changes'], True)

    def test_rollback_new_foreign_reference_removes_rules_but_keeps_outbound(self):
        for balancer in (False, True):
            panel = FakePanel(fault='route')
            def admin(p):
                if p.saves == 1:
                    if balancer:
                        p.template['routing']['balancers'] = [dict(tag='admin', selector=['cascade'])]
                    else:
                        p.template['routing']['rules'].insert(1, dict(outboundTag=TAG, domain=['full:admin.test']))
            panel.on_save = admin
            result = self.run_entry('entry-connect', panel)
            self.assertEqual(result, dict(state='failed_rollback', reason='foreign_reference', config_may_contain_changes=True))
            self.assertEqual(panel.saves, 2)
            self.assertTrue(any(o.get('tag') == TAG for o in panel.template['outbounds']))
            self.assertFalse(any(r.get('comment') in COMMENTS for r in panel.template['routing']['rules']))
            self.assertEqual(self.run_entry('entry-disable', panel), dict(state='foreign_reference'))
        panel = FakePanel(fault='route')
        panel.on_save = lambda p: p.template['outbounds'].append(outbound()) if p.saves == 2 else None
        self.assertEqual(self.run_entry('entry-connect', panel)['state'], 'failed_rollback')

    def test_rollback_new_foreign_reference_keeps_outbound_removes_only_owned_rules(self):
        for reference in ('rule', 'balancer'):
            panel = FakePanel(fault='route')
            def admin(p):
                if p.saves != 1: return
                if reference == 'rule':
                    p.template['routing']['rules'].append(dict(outboundTag=TAG, domain=['full:admin.test']))
                else:
                    p.template['routing']['balancers'] = [dict(tag='admin', selector=['cascade'])]
            panel.on_save = admin
            result = self.run_entry('entry-connect', panel)
            self.assertEqual(result, dict(state='failed_rollback', reason='foreign_reference', config_may_contain_changes=True))
            self.assertTrue(any(o.get('tag') == TAG for o in panel.template['outbounds']))
            self.assertFalse(any(r.get('comment') in COMMENTS for r in panel.template['routing']['rules']))
            if reference == 'rule':
                self.assertEqual(panel.template['routing']['rules'][-1]['outboundTag'], TAG)
            else:
                self.assertEqual(panel.template['routing']['balancers'][0]['selector'], ['cascade'])

    def test_status_absent_active_missing_outbound_rules_wrong_order_and_warp(self):
        panel = FakePanel()
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='absent', warp=False))
        panel = FakePanel(active=True)
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='active', warp=False))
        panel.template['outbounds'].append(dict(tag='warp-masque'))
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='active', warp=True))
        panel = FakePanel(active=True)
        panel.template['outbounds'].pop()
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='inconsistent', reason='missing_outbound', warp=False))
        panel = FakePanel(active=True)
        panel.template['routing']['rules'].pop()
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='inconsistent', reason='missing_rules', warp=False))
        panel = FakePanel(active=True)
        panel.template['routing']['rules'][-3:] = list(reversed(panel.template['routing']['rules'][-3:]))
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='inconsistent', reason='wrong_order', warp=False))
        panel = FakePanel()
        panel.template['routing']['rules'].append(dict(comment='WARP - RU2'))
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='absent', warp=True))
        self.assertEqual(self.run_entry('entry-status', FakePanel(fault='panel'))['state'], 'panel_error')

    def test_status_checks_relative_order_and_does_not_fetch_client_or_probe(self):
        panel = FakePanel(active=True, strings=True)
        panel.template['routing']['rules'].insert(-1, dict(outboundTag='direct', domain=['full:admin.test']))
        self.assertEqual(self.run_entry('entry-status', panel), dict(state='active', warp=False))
        self.assertEqual([p for p,_,_ in panel.calls], ['panel/api/xray/'])

    def test_disable_removed_absent_partial_state_and_repeat_only_one_save(self):
        for strings in (False, True):
            panel = FakePanel(active=True, strings=strings)
            self.assertEqual(self.run_entry('entry-disable', panel), dict(state='removed'))
            self.assertEqual(self.module.normalized(panel.template), ORIGINAL)
            self.assertEqual(panel.saves, 1)
            self.assertEqual(self.run_entry('entry-disable', panel), dict(state='absent'))
            self.assertEqual(panel.saves, 1)
        for keep_outbound in (False, True):
            panel = FakePanel(active=True)
            if keep_outbound: panel.template['routing']['rules'] = panel.template['routing']['rules'][:2]
            else: panel.template['outbounds'].pop()
            self.assertEqual(self.run_entry('entry-disable', panel), dict(state='removed'))
            self.assertEqual(self.module.normalized(panel.template), ORIGINAL)

    def test_disable_foreign_rules_balancer_exact_prefix_and_fallback_refuse(self):
        references = [dict(rule=dict(outboundTag=TAG, domain=['full:admin.test'])),
                      dict(balancer=dict(tag='admin', selector=[TAG])),
                      dict(balancer=dict(tag='admin', selector=['cascade'])),
                      dict(balancer=dict(tag='admin', selector=[''])),
                      dict(balancer=dict(tag='admin', selector=['direct'], fallbackTag=TAG))]
        for ref in references:
            panel = FakePanel(active=True)
            if 'rule' in ref:
                panel.template['routing']['rules'].append(ref['rule'])
            else:
                panel.template['routing']['balancers'] = [ref['balancer']]
            original = copy.deepcopy(panel.template)
            self.assertEqual(self.run_entry('entry-disable', panel), dict(state='foreign_reference'))
            self.assertEqual(panel.template, original)
            self.assertEqual(panel.saves, 0)

    def test_disable_preserves_unmarked_rules_similar_tags_and_unrelated_balancers(self):
        panel = FakePanel(active=True)
        panel.template['outbounds'].append(dict(tag='cascade-exit-admin', protocol='freedom'))
        foreign = dict(comment='CASCADE - administrator', outboundTag='direct', domain=['full:admin.test'])
        panel.template['routing']['rules'].insert(1, foreign)
        panel.template['routing']['balancers'] = [dict(tag='admin', selector=['cascade-exit-admin'])]
        self.assertEqual(self.run_entry('entry-disable', panel), dict(state='removed'))
        self.assertEqual(panel.template['outbounds'][-1]['tag'], 'cascade-exit-admin')
        self.assertEqual(panel.template['routing']['rules'][1], foreign)
        self.assertIn('balancers', panel.template['routing'])

    def test_balancer_string_selectors_use_comma_separated_prefixes(self):
        for selector, expected in (('direct', 'removed'), ('case', 'removed'),
                                   ('cascade', 'foreign_reference'), ('direct,cascade-exit', 'foreign_reference'),
                                   ('', 'foreign_reference')):
            with self.subTest(selector=selector):
                panel = FakePanel(active=True)
                panel.template['routing']['balancers'] = [dict(tag='admin', selector=selector)]
                self.assertEqual(self.run_entry('entry-disable', panel), dict(state=expected))
                self.assertEqual(panel.saves, 1 if expected == 'removed' else 0)

    def test_disable_save_error_reports_actual_state_even_if_applied(self):
        for fault, reason in (('save-rejected', 'save_failed_actual_active'),
                              ('save-partial', 'save_failed_actual_absent')):
            panel = FakePanel(active=True, fault=fault)
            self.assertEqual(self.run_entry('entry-disable', panel), dict(state='failed', reason=reason))
            self.assertEqual(panel.saves, 1)
        panel = FakePanel(active=True, fault='save-noop')
        self.assertEqual(self.run_entry('entry-disable', panel), dict(state='failed', reason='remove_unverified'))
        panel = FakePanel(active=True, fault='readback')
        self.assertEqual(self.run_entry('entry-disable', panel), dict(state='failed', reason='readback_failed'))
        self.assertEqual(self.run_entry('entry-disable', FakePanel(fault='panel'))['state'], 'panel_error')

    def test_disable_partial_save_and_unavailable_readback(self):
        panel = FakePanel(active=True, fault='save-partial')
        request = panel.request
        def unavailable(path, data=None, **options):
            if path == 'panel/api/xray/' and panel.saves:
                raise TimeoutError(' '.join(SECRETS))
            return request(path, data, **options)
        panel.request = unavailable
        self.assertEqual(self.run_entry('entry-disable', panel), dict(state='failed', reason='save_failed_actual_unknown'))
        self.assertEqual(panel.saves, 1)

    def test_rollback_save_error_with_committed_removal_is_read_back(self):
        panel = FakePanel(fault='route')
        request = panel.request
        def uncertain(path, data=None, **options):
            result = request(path, data, **options)
            if path.endswith('/update') and panel.saves == 2:
                raise TimeoutError(' '.join(SECRETS))
            return result
        panel.request = uncertain
        self.assertEqual(self.run_entry('entry-connect', panel), dict(state='failed', reason='route_test_failed'))
        self.assertEqual(panel.template, ORIGINAL)

    def test_rollback_noop_cannot_be_reported_as_confirmed(self):
        panel = FakePanel(fault='route')
        request = panel.request
        def noop(path, data=None, **options):
            if path.endswith('/update') and panel.saves == 1:
                panel.saves += 1
                return dict(success=True)
            return request(path, data, **options)
        panel.request = noop
        result = self.run_entry('entry-connect', panel)
        self.assertEqual(result, dict(state='failed_rollback', reason='route_test_failed', config_may_contain_changes=True))

    def test_cli_single_json_codes_secrets_and_session_cleanup(self):
        cases = [('entry-connect', FakePanel(), 'connected'),
                ('entry-status', FakePanel(active=True), 'active'), ('entry-status', FakePanel(), 'absent'),
                ('entry-disable', FakePanel(active=True), 'removed'), ('entry-disable', FakePanel(), 'absent'),
                ('entry-connect', FakePanel(active=True), 'already_connected'),
                ('entry-connect', FakePanel(fault='probe-timeout'), 'test_failed'),
                ('entry-connect', FakePanel(fault='route'), 'failed'),
                ('entry-connect', FakePanel(fault='rollback-save'), 'failed_rollback'),
                ('entry-status', FakePanel(fault='panel'), 'panel_error'),
                ('entry-disable', FakePanel(active=True, fault='save-partial'), 'failed'),
                ('entry-disable', FakePanel(fault='panel'), 'panel_error')]
        panel = FakePanel()
        panel.template['outbounds'].append(dict(tag='warp-masque'))
        cases.append(('entry-connect', panel, 'warp_active'))
        panel = FakePanel()
        panel.template['routing']['rules'].append(dict(outboundTag='direct'))
        cases.append(('entry-connect', panel, 'intercepted'))
        panel = FakePanel(active=True)
        panel.template['routing']['rules'].pop()
        cases.append(('entry-status', panel, 'inconsistent'))
        panel = FakePanel(active=True)
        panel.template['routing']['rules'].append(dict(outboundTag=TAG, domain=['full:admin.test']))
        cases.append(('entry-disable', panel, 'foreign_reference'))
        for mode, panel, expected in cases:
            code, result = self.cli(mode, panel)
            self.assertEqual(result['state'], expected)
            self.assertEqual(code, 0 if expected in ('connected','active','removed','absent') else 1)

    def cli(self, mode, panel, login_error=False, stdin=None):
        sessions = []
        def factory(base, user, password, directory, options):
            self.assertEqual((base, user, password), ('https://panel.example/panel/', *SECRETS[:2]))
            self.assertEqual(options, ['--resolve', 'panel.example:443:127.0.0.1'])
            self.assertEqual(Path(directory).stat().st_mode & 0o777, 0o700)
            sessions.append(Path(directory))
            if login_error: raise ValueError(' '.join(SECRETS))
            return panel
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
        payload = '\0'.join(SECRETS[:2]) + ('\0' + exit_fixtures.link() if mode == 'entry-connect' else '')
        output, errors = io.StringIO(), io.StringIO()
        argv = ['managed.py', mode, 'helper', 'panel.example', 'panel', self.temp.name]
        with patch.object(self.module.importlib.util, 'spec_from_file_location', return_value=spec), \
             patch.object(self.module.importlib.util, 'module_from_spec', return_value=SimpleNamespace(Panel=factory)), \
             patch.object(self.module.sys, 'argv', argv), patch.object(self.module.sys, 'stdin', io.StringIO(payload if stdin is None else stdin)), \
             redirect_stdout(output), redirect_stderr(errors):
            code = self.module.main()
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        value = json.loads(output.getvalue())
        self.assertEqual(errors.getvalue(), '')
        for secret in (*SECRETS, exit_fixtures.link()):
            self.assertNotIn(secret, output.getvalue() + errors.getvalue() + ' '.join(argv))
        self.assertTrue(all(not p.exists() for p in sessions))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        return code, value

    def test_cli_session_failures_and_invalid_link_hide_secrets(self):
        for mode in ('entry-connect', 'entry-status', 'entry-disable'):
            self.assertEqual(self.cli(mode, FakePanel(), login_error=True)[0], 1)
            self.assertEqual(self.cli(mode, FakePanel(), stdin='missing-separators')[0], 1)
        self.assertEqual(self.cli('entry-connect', FakePanel(), stdin='fixture-user\0fixture-password\0invalid')[1]['state'], 'link_invalid')

    def test_actual_subprocess_cli_stdin_only_and_single_json(self):
        root = Path(self.temp.name)
        helper = root/'fake-panel.py'
        helper.write_text('''import json
from pathlib import Path
class Panel:
    def __init__(self, base, username, password, directory, options):
        assert (username, password) == ('fixture-user', 'fixture-password')
        assert Path(directory).stat().st_mode & 0o777 == 0o700
    def request(self, path, data=None, **options):
        assert path == 'panel/api/xray/'
        return dict(success=True, obj=json.dumps(dict(xraySetting=dict(outbounds=[], routing=dict(rules=[])),
                                                     outboundTestUrl='https://fixture.test')))
''')
        session_root = root/'sessions'
        session_root.mkdir()
        result = subprocess.run(
            [self.module.sys.executable, str(exit_fixtures.ROOT/'assets/cascade/managed.py'), 'entry-status',
             str(helper), 'panel.example', 'panel', str(session_root)],
            input='fixture-user\0fixture-password', text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '{"state": "absent", "warp": false}\n')
        self.assertEqual(result.stderr, '')
        self.assertEqual(list(session_root.iterdir()), [])
        for secret in SECRETS:
            self.assertNotIn(secret, result.stdout + result.stderr + ' '.join(result.args))
        bad = subprocess.run([self.module.sys.executable, str(exit_fixtures.ROOT/'assets/cascade/managed.py')],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)['reason'], 'session_failed')
        self.assertEqual(len(bad.stdout.splitlines()), 1)
        self.assertEqual(bad.stderr, '')

    def test_shared_panel_curl_argv_has_no_outbound_credentials(self):
        spec = importlib.util.spec_from_file_location('cascade_entry_panel_test', exit_fixtures.ROOT/'assets/amneziawg/managed.py')
        api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        replies = [dict(success=True, obj='fixture-csrf'), dict(success=True), dict(success=True, obj='fixture-csrf')]
        with tempfile.TemporaryDirectory() as directory, patch.object(api.subprocess, 'run',
                side_effect=[subprocess.CompletedProcess([], 0, json.dumps(r).encode()) for r in replies]) as run:
            panel = api.Panel('https://panel.example/panel/', *SECRETS[:2], directory)
            for call in run.call_args_list:
                for secret in SECRETS:
                    self.assertNotIn(secret, ' '.join(call.args[0]))
            with patch.object(api.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{"success":true}')) as run:
                panel.request('panel/api/xray/testOutbound', dict(outbound=json.dumps(outbound()), mode='real'), method='POST', form=True)
                for secret in SECRETS:
                    self.assertNotIn(secret, ' '.join(run.call_args.args[0]))
                body = parse_qs(run.call_args.kwargs['input'].decode())
                self.assertEqual(json.loads(body['outbound'][0]), outbound())
