"""Validate public author/committer identities on commits introduced by a PR."""

import os
from pathlib import Path
import re
import subprocess
import sys

MAINTAINER_EMAIL = '102687702+xPROMSx@users.noreply.github.com'
MAX_COMMITS = 1000
LOGIN = r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?'
NOREPLY = re.compile(rf'(?:[1-9][0-9]*\+)?({LOGIN}(?:\[bot\])?)@users\.noreply\.github\.com')
SHA = re.compile(r'[0-9a-fA-F]{40}')
METADATA = re.compile(rb'([^<>\x00-\x1f\x7f]+) <([^<>\x00-\x20\x7f]+)> [0-9]+ [+-][0-9]{4}')


class ValidationError(ValueError):
    pass


def git(repo, *args):
    try:
        return subprocess.run(['git', '--no-replace-objects', *args], cwd=repo,
                              check=True, capture_output=True, timeout=20).stdout
    except (subprocess.SubprocessError, OSError):
        # Never echo Git stderr, argv or rejected metadata.
        raise ValidationError('Git identity check failed: unavailable commit or history') from None


def approved(name, email):
    if name in ('Proms', 'xPROMSx') or email == MAINTAINER_EMAIL:
        return name in ('Proms', 'xPROMSx') and email == MAINTAINER_EMAIL
    if name == 'GitHub' and email == 'noreply@github.com':
        return True
    match = NOREPLY.fullmatch(email)
    # A public login (or exact bot login) is used as the name; no arbitrary aliases.
    return bool(match and name == match[1] and '--' not in match[1])


def validate(base, head, repo=Path('.'), max_commits=MAX_COMMITS):
    for sha in (base, head):
        if not SHA.fullmatch(sha) or sha == '0' * 40:
            raise ValidationError('Git identity check failed: expected nonzero full commit SHA')
    if git(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValidationError('Git identity check failed: full history required')
    for sha in (base, head):
        if git(repo, 'cat-file', '-t', sha).strip() != b'commit':
            raise ValidationError('Git identity check failed: expected commit object')
    git(repo, 'merge-base', base, head)
    commits = git(repo, 'rev-list', '--max-count=' + str(max_commits + 1),
                  head, '--not', base).decode('ascii').splitlines()
    if not commits or len(commits) > max_commits:
        raise ValidationError('Git identity check failed: empty or oversized PR range')
    for sha in commits:
        if int(git(repo, 'cat-file', '-s', sha)) > 1024 * 1024:
            raise ValidationError(f'{sha}: commit object exceeds validation limit')
        headers = git(repo, 'cat-file', 'commit', sha).split(b'\n\n', 1)[0].split(b'\n')
        for role in ('author', 'committer'):
            lines = [line[len(role) + 1:] for line in headers if line.startswith(role.encode() + b' ')]
            valid = False
            if len(lines) == 1:
                match = METADATA.fullmatch(lines[0])
                if match:
                    try:
                        valid = approved(match[1].decode('utf-8'), match[2].decode('ascii'))
                    except UnicodeError:
                        pass
            if not valid:
                raise ValidationError(f'{sha}: invalid {role}')
    return len(commits)


def main():
    event = os.environ.get('GITHUB_EVENT_NAME', '')
    if event in ('push', 'workflow_dispatch'):
        print('GIT IDENTITY: SKIP — only PR-introduced commits are checked')
        return 0
    if event != 'pull_request':
        print('GIT IDENTITY: FAIL — unsupported event', file=sys.stderr)
        return 1
    try:
        count = validate(os.environ.get('PR_BASE_SHA', ''), os.environ.get('PR_HEAD_SHA', ''))
    except ValidationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f'GIT IDENTITY: PASS — {count} introduced commits')
    return 0


if __name__ == '__main__':
    sys.exit(main())
