"""Exercise workflow-run decisions without GitHub write access."""
import io
import json
import subprocess
import unittest
from unittest.mock import patch

import ci_auto_rerun


class CIAutoRerun(unittest.TestCase):
    def setUp(self):
        self.repository = 'owner/project'
        self.run_data = {
            'id': 42, 'run_number': 17, 'name': 'Full fresh installer acceptance',
            'conclusion': 'failure', 'run_attempt': 1, 'status': 'completed',
            'event': 'pull_request', 'head_repository': {'full_name': self.repository},
            'head_branch': 'feature', 'head_sha': 'a'*40, 'pull_requests': [{'number': 9}],
        }
        self.current_pr = {'state': 'open', 'head': {
            'sha': self.run_data['head_sha'], 'repo': {'full_name': self.repository},
        }}
        self.latest = {**self.run_data}
        self.pull_endpoint = 'repos/owner/project/pulls/9'

    def evaluate(self):
        summary = io.StringIO()
        pages = [{'jobs': [{'name': 'passed job', 'conclusion': 'success'},
                           {'name': '<failed job>', 'conclusion': 'failure'}]},
                 {'jobs': [{'name': 'timed out job', 'conclusion': 'timed_out'}]}]
        self.endpoint = f'repos/{self.repository}/actions/runs/42'

        def gh(*args):
            if args[0] == 'run':
                return ''
            if args[-1] == self.pull_endpoint:
                return json.dumps(self.current_pr)
            return json.dumps(pages if '/attempts/1/jobs?' in args[-1] else self.latest)

        with patch.object(ci_auto_rerun, 'gh', side_effect=gh) as command:
            ci_auto_rerun.process(self.run_data, self.repository, summary)
        command.assert_any_call('api', '--paginate', '--slurp', self.endpoint+'/attempts/1/jobs?per_page=100')
        reruns = [call.args for call in command.call_args_list if call.args[0] == 'run']
        pulls = [call.args for call in command.call_args_list if '/pulls/' in call.args[-1]]
        return summary.getvalue(), reruns, pulls

    def test_failed_first_attempt_retries_only_failed_jobs_and_summarizes(self):
        summary, reruns, pulls = self.evaluate()
        self.assertEqual(pulls, [('api', self.pull_endpoint)])
        self.assertEqual(reruns, [('run', 'rerun', '42', '--repo', self.repository, '--failed')])
        for detail in ('Rerun requested', '&lt;failed job&gt;', 'timed out job', self.run_data['name'],
                       '17', self.run_data['head_sha']):
            self.assertIn(detail, summary)
        self.assertNotIn('passed job', summary)

    def test_timed_out_first_attempt_retries_failed_jobs(self):
        self.run_data['conclusion'] = self.latest['conclusion'] = 'timed_out'
        summary, reruns, pulls = self.evaluate()
        self.assertEqual(pulls, [('api', self.pull_endpoint)])
        self.assertEqual(reruns, [('run', 'rerun', '42', '--repo', self.repository, '--failed')])
        self.assertIn('Rerun requested', summary)

    def test_success_and_cancellation_skip(self):
        for conclusion in ('success', 'cancelled'):
            with self.subTest(conclusion=conclusion):
                self.run_data['conclusion'] = conclusion
                summary, reruns, pulls = self.evaluate()
                self.assertIn('conclusion is '+conclusion, summary)
                self.assertEqual(reruns, [])
                self.assertEqual(pulls, [])

    def test_second_attempt_skips(self):
        self.run_data['run_attempt'] = 2
        summary, reruns, _ = self.evaluate()
        self.assertIn('only attempt 1', summary)
        self.assertEqual(reruns, [])

    def test_fork_and_unidentified_pr_skip_without_api_lookup(self):
        for fields, reason in (
            ({'head_repository': {'full_name': 'fork/project'}}, 'repository differs'),
            ({'head_repository': None}, 'repository differs'),
            ({'pull_requests': []}, 'exactly one PR'),
        ):
            with self.subTest(fields=fields), patch.dict(self.run_data, fields):
                summary, reruns, pulls = self.evaluate()
                self.assertIn(reason, summary)
                self.assertEqual(reruns, [])
                self.assertEqual(pulls, [])

    def test_stale_pr_head_skips(self):
        self.current_pr['head']['sha'] = 'b'*40
        summary, reruns, _ = self.evaluate()
        self.assertIn('head SHA has changed', summary)
        self.assertEqual(reruns, [])

    def test_push_only_on_main(self):
        self.run_data['event'] = 'push'
        summary, reruns, pulls = self.evaluate()
        self.assertIn('push was outside main', summary)
        self.assertEqual(reruns, [])
        self.assertEqual(pulls, [])
        self.run_data['head_branch'] = 'main'
        self.assertEqual(len(self.evaluate()[1]), 1)

    def test_schedule_only_for_canary_and_dispatch_skips(self):
        self.run_data['event'] = 'schedule'
        self.assertEqual(self.evaluate()[1], [])
        self.run_data['name'] = 'Upstream 3x-ui Canary'
        self.assertEqual(len(self.evaluate()[1]), 1)
        self.run_data['event'] = 'workflow_dispatch'
        self.assertEqual(self.evaluate()[1], [])

    def test_run_already_retried_since_event_skips(self):
        self.latest['run_attempt'] = 2
        summary, reruns, pulls = self.evaluate()
        self.assertIn('no longer a completed failure', summary)
        self.assertEqual(reruns, [])
        self.assertEqual(pulls, [])

    def test_pr_lookup_error_skips_rerun_and_summarizes_reason(self):
        summary = io.StringIO()
        error = subprocess.CalledProcessError(1, ['gh', 'api', self.pull_endpoint])
        responses = ['[{"jobs":[]}]', json.dumps(self.latest), error]
        with patch.object(ci_auto_rerun, 'gh', side_effect=responses) as command:
            with self.assertRaises(subprocess.CalledProcessError):
                ci_auto_rerun.process(self.run_data, self.repository, summary)
        command.assert_called_with('api', self.pull_endpoint)
        self.assertEqual(command.call_count, 3)
        self.assertIn('Skipped: GitHub PR lookup failed', summary.getvalue())

    def test_rerun_error_keeps_failed_jobs_and_decision_in_summary(self):
        summary = io.StringIO()
        pages = '[{"jobs":[{"name":"first failed job","conclusion":"failure"}]}]'
        responses = [pages, json.dumps(self.latest), json.dumps(self.current_pr), OSError]
        with patch.object(ci_auto_rerun, 'gh', side_effect=responses):
            with self.assertRaises(OSError):
                ci_auto_rerun.process(self.run_data, self.repository, summary)
        self.assertIn('first failed job', summary.getvalue())
        self.assertIn('GitHub API or rerun command failed', summary.getvalue())
