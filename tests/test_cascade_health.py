"""Entry health, conservative rule classification and malformed foreign fixtures."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_cascade as exits
from test_cascade_entry import FakePanel, ORIGINAL, TAG, rules


class Clock:
    def __init__(self):
        self.now = 0
        self.pauses = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.pauses.append(seconds)
        self.now += seconds


class HealthPanel(FakePanel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.statuses = [dict(state='running', errorMsg='')]
        self.status_reads = 0
        self.route_failures = 0
        self.deadline = None

    def request(self, path, data=None, **options):
        if path == 'panel/api/server/status':
            self.calls.append((path, copy.deepcopy(data), options))
            self.status_reads += 1
            value = self.statuses[min(self.status_reads - 1, len(self.statuses) - 1)]
            if isinstance(value, Exception):
                raise value
            return dict(success=True, obj=dict(xray=copy.deepcopy(value)))
        if path.endswith('/routeTest') and self.route_failures:
            self.route_failures -= 1
            raise TimeoutError('fixture-password')
        return super().request(path, data, **options)


class CascadeHealth(unittest.TestCase):
    def setUp(self):
        self.module = exits.helper()
        self.clock = Clock()
        timer = SimpleNamespace(monotonic=self.clock.monotonic, sleep=self.clock.sleep)
        self.addCleanup(patch.stopall)
        patch.object(self.module, 'time', timer, create=True).start()

    def execute(self, mode, panel):
        return self.module.execute_entry(mode, panel, exits.link())

    def test_stopped_and_status_request_failure_never_save(self):
        for state in ('stop', 'error', 'unknown'):
            panel = HealthPanel()
            panel.statuses = [dict(state=state, errorMsg='fixture-private-error')]
            self.assertEqual(self.execute('entry-connect', panel), dict(state='failed', reason='xray_not_running'))
            self.assertEqual(panel.saves, 0)
        panel = HealthPanel()
        panel.statuses = [TimeoutError('fixture-password')]
        self.assertEqual(self.execute('entry-connect', panel), dict(state='failed', reason='panel_request_failed'))
        self.assertEqual(panel.saves, 0)

    def test_first_attempt_and_delayed_routes_restore_deadline(self):
        for failures in (0, 3):
            panel = HealthPanel()
            panel.route_failures = failures
            self.assertEqual(self.execute('entry-connect', panel), dict(state='connected', custom_rules=[]))
            self.assertEqual(panel.saves, 1)
            self.assertIsNone(panel.deadline)
        self.assertEqual(self.clock.pauses, [1, 1, 1])

    def test_stale_status_errors_and_wrong_routes_are_retried(self):
        panel = HealthPanel()
        panel.statuses = [dict(state='running', errorMsg=''), dict(state='stop', errorMsg=''),
                          TimeoutError('fixture-password'), dict(state='running', errorMsg='old'),
                          dict(state='running', errorMsg='')]
        self.assertEqual(self.execute('entry-connect', panel)['state'], 'connected')
        self.assertEqual(self.clock.pauses, [1, 1, 1])
        panel = HealthPanel(fault='route-wrong')
        request = panel.request
        def recover(path, data=None, **options):
            if self.clock.now >= 5:
                panel.fault = ''
            return request(path, data, **options)
        panel.request = recover
        self.assertEqual(self.execute('entry-connect', panel)['state'], 'connected')

    def test_route_deadline_rolls_back_then_confirms_health(self):
        panel = HealthPanel(fault='route')
        self.assertEqual(self.execute('entry-connect', panel), dict(state='failed', reason='route_test_failed'))
        self.assertEqual(panel.template, ORIGINAL)
        self.assertEqual(self.clock.now, 15)
        self.assertEqual(panel.saves, 2)
        self.assertIsNone(panel.deadline)

    def test_unhealthy_deadline_and_delayed_rollback_recovery(self):
        panel = HealthPanel()
        request = panel.request
        def unhealthy(path, data=None, **options):
            if path.endswith('/status'):
                if panel.saves == 1:
                    panel.statuses = [dict(state='running', errorMsg='private')]
                elif panel.saves == 2:
                    panel.statuses = [dict(state='running' if self.clock.now >= 18 else 'stop', errorMsg='')]
            return request(path, data, **options)
        panel.request = unhealthy
        self.assertEqual(self.execute('entry-connect', panel), dict(state='failed', reason='xray_unhealthy'))
        self.assertEqual(self.clock.now, 18)
        self.assertEqual(panel.template, ORIGINAL)

    def test_unhealthy_rollback_admits_possible_changes(self):
        panel = HealthPanel(fault='route')
        request = panel.request
        def stopped(path, data=None, **options):
            if panel.saves == 2:
                panel.statuses = [dict(state='stop', errorMsg='private')]
            return request(path, data, **options)
        panel.request = stopped
        self.assertEqual(self.execute('entry-connect', panel), dict(state='failed_rollback',
                         reason='route_test_failed', config_may_contain_changes=True, xray_running=False))
        self.assertEqual(self.clock.now, 30)

    def test_disable_runs_while_stopped_and_reports_health(self):
        for healthy in (True, False):
            panel = HealthPanel(active=True)
            panel.statuses = [dict(state='running' if healthy else 'stop', errorMsg='')]
            self.assertEqual(self.execute('entry-disable', panel), dict(state='removed', xray_running=healthy))
            self.assertEqual(panel.template, ORIGINAL)
            self.assertEqual(panel.calls[0][0], 'panel/api/xray/')
            save_index = next(i for i, (p, _, _) in enumerate(panel.calls) if p.endswith('/update'))
            status_index = next(i for i, (p, _, _) in enumerate(panel.calls) if p.endswith('/status'))
            self.assertLess(save_index, status_index)

    def test_status_and_warp_details_never_disclose_error_message(self):
        panel = HealthPanel()
        panel.statuses = [dict(state='error', errorMsg='fixture-password')]
        panel.template['outbounds'].append(dict(tag='warp-masque'))
        panel.template['routing']['rules'].append(dict(comment='WARP - RU2', enabled=False))
        expected = dict(state='absent', warp=True, warp_outbound=True, warp_rules=['WARP - RU2'],
                        xray='error', custom_rules=[])
        self.assertEqual(self.execute('entry-status', panel), expected)
        self.assertEqual(self.execute('entry-connect', panel), dict(state='warp_active',
                         warp_outbound=True, warp_rules=['WARP - RU2']))
        panel.statuses = [TimeoutError('fixture-password')]
        self.assertEqual(self.execute('entry-status', panel)['xray'], 'unknown')

    def test_standard_disabled_and_custom_rules_above_first_owned_rule(self):
        panel = HealthPanel()
        standard = dict(protocol=['bittorrent'], outboundTag='blocked', comment='renamed', ruleTag='panel', enabled=True)
        custom = dict(domain=['full:admin.test'], outboundTag='direct')
        panel.template['routing']['rules'] += [standard, dict(custom, enabled=False), custom]
        self.assertEqual(self.execute('entry-status', panel)['custom_rules'], [5])
        self.assertEqual(self.execute('entry-connect', panel), dict(state='connected', custom_rules=[5]))
        panel.template['routing']['rules'].append(custom)
        self.assertEqual(self.execute('entry-status', panel)['custom_rules'], [5])
        panel.template['routing']['rules'].insert(1, dict(ip=['geoip:private'], outboundTag='direct'))
        self.assertEqual(self.execute('entry-status', panel)['custom_rules'], [2, 6])

    def test_foreign_reference_details_and_malformed_values(self):
        for bad in (None, 7, {}, 'invalid', [None, 7, 'bad', {}], [dict(selector=[None, 7, {}])]):
            panel = HealthPanel(active=True)
            panel.template['routing']['balancers'] = bad
            panel.template['routing']['rules'].insert(1, None)
            self.assertEqual(self.execute('entry-disable', panel), dict(state='removed', xray_running=True))
            self.assertIsNone(panel.template['routing']['rules'][1])
        panel = HealthPanel(active=True)
        panel.template['routing']['rules'].append(dict(outboundTag=TAG, domain=['full:private']))
        panel.template['routing']['balancers'] = [None, dict(selector=[None, 'cascade'])]
        self.assertEqual(self.execute('entry-disable', panel), dict(state='foreign_reference',
                         foreign_rules=[6], foreign_balancers=[2]))
        self.assertEqual(panel.saves, 0)

    def test_malformed_balancers_do_not_prevent_rollback(self):
        panel = HealthPanel(fault='route')
        panel.template['routing']['balancers'] = None
        expected = copy.deepcopy(panel.template)
        self.assertEqual(self.execute('entry-connect', panel), dict(state='failed', reason='route_test_failed'))
        self.assertEqual(panel.template, expected)

    def test_ambiguous_api_rule_and_extra_conditions_are_custom(self):
        panel = HealthPanel()
        panel.template['routing']['rules'] += [
            dict(inboundTag=['api', 'admin'], outboundTag='api'),
            dict(ip=['geoip:private'], outboundTag='blocked', domain=['full:admin.test']),
            dict(ip=['geoip:private'], outboundTag='blocked', futureField=True),
        ]
        self.assertEqual(self.execute('entry-status', panel)['custom_rules'], [3, 4, 5])

    def test_absent_rules_with_remaining_outbound_reports_all_custom(self):
        panel = HealthPanel()
        panel.template['outbounds'].append(dict(tag=TAG))
        panel.template['routing']['rules'].append(dict(domain=['full:admin.test'], outboundTag='direct'))
        self.assertEqual(self.execute('entry-status', panel)['custom_rules'], [3])

    def test_rollback_preserves_unreadable_rule_and_waits_on_status_errors(self):
        panel = HealthPanel(fault='route')
        def concurrent(p):
            if p.saves == 1:
                p.template['routing']['rules'].insert(1, None)
        panel.on_save = concurrent
        request = panel.request
        def unavailable(path, data=None, **options):
            if panel.saves == 2 and path.endswith('/status'):
                raise TimeoutError('fixture-password')
            return request(path, data, **options)
        panel.request = unavailable
        result = self.execute('entry-connect', panel)
        self.assertEqual(result, dict(state='failed_rollback', reason='readback_mismatch',
                         config_may_contain_changes=True, xray_running=False))
        self.assertIsNone(panel.template['routing']['rules'][1])
        self.assertEqual(self.clock.now, 15)
