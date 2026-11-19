"""Retry failed jobs once, using only trusted workflow code and GitHub metadata."""
import html
import json
import os
from pathlib import Path
import subprocess
import sys

FAILED_CONCLUSIONS = ('failure', 'timed_out')


def skip_reason(run, repository):
    if run['conclusion'] not in FAILED_CONCLUSIONS:
        return 'conclusion is '+str(run['conclusion'])
    if run['run_attempt'] != 1:
        return 'only attempt 1 is eligible'
    event = run['event']
    if event == 'pull_request':
        if (run.get('head_repository') or {}).get('full_name') != repository:
            return 'PR head repository differs'
        if len(run.get('pull_requests') or []) != 1:
            return 'the event does not identify exactly one PR'
    elif event == 'push':
        if run['head_branch'] != 'main':
            return 'push was outside main'
    elif event != 'schedule' or run['name'] != 'Upstream 3x-ui Canary':
        return 'event is ineligible'
    return None


def pr_skip_reason(run, pull, repository):
    head = pull['head']
    if (head.get('repo') or {}).get('full_name') != repository:
        return 'current PR head repository differs'
    if pull['state'] != 'open':
        return 'PR is closed'
    if head['sha'] != run['head_sha']:
        return 'PR head SHA has changed'
    return None


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True, timeout=60)


def current_pull(repository, number):
    return json.loads(gh('api', f'repos/{repository}/pulls/{int(number)}'))


def process(run, repository, summary):
    run_id = str(int(run['id']))
    endpoint = f'repos/{repository}/actions/runs/{run_id}'
    decision = 'Skipped: GitHub API or rerun command failed'
    failed_jobs = 'unavailable'
    try:
        pages = json.loads(gh('api', '--paginate', '--slurp', endpoint+'/attempts/1/jobs?per_page=100'))
        names = [job['name'] for page in pages for job in page['jobs']
                 if job['conclusion'] in FAILED_CONCLUSIONS]
        failed_jobs = ', '.join(names) or 'none'
        reason = skip_reason(run, repository)
        if reason is None:
            latest = json.loads(gh('api', endpoint))
            if (latest['run_attempt'] != 1 or latest['status'] != 'completed'
                    or latest['conclusion'] not in FAILED_CONCLUSIONS):
                reason = 'run is no longer a completed failure or timeout on attempt 1'
        if reason is None and run['event'] == 'pull_request':
            try:
                pull = current_pull(repository, run['pull_requests'][0]['number'])
            except (OSError, subprocess.SubprocessError, ValueError):
                decision = 'Skipped: GitHub PR lookup failed'
                raise
            reason = pr_skip_reason(run, pull, repository)
        if reason is None:
            gh('run', 'rerun', run_id, '--repo', repository, '--failed')
            decision = 'Rerun requested for failed jobs'
        else:
            decision = 'Skipped: '+reason
    finally:
        for label, value in (
            ('Workflow', run['name']), ('Run', run['run_number']), ('SHA', run['head_sha']),
            ('Failed jobs on attempt 1', failed_jobs), ('Decision', decision),
        ):
            summary.write(f'<p><strong>{label}</strong> <code>{html.escape(str(value))}</code></p>\n')


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        process(event['workflow_run'], os.environ['GITHUB_REPOSITORY'], summary)


if __name__ == '__main__':
    sys.exit(main())
