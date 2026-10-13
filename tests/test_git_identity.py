"""Git metadata checks use only synthetic commits in private repositories."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import ci_git_identity as checker


class GitIdentity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        self.git('init', '-q')
        # Historical identities are deliberately outside the introduced range.
        self.base = self.commit(('Legacy Fixture', 'legacy@example.invalid'))

    def git(self, *args, env=None, input=None):
        return subprocess.check_output(['git', *args], cwd=self.repo, env=env,
                                       input=input, stderr=subprocess.PIPE).decode().strip()

    def commit(self, author=('Proms', checker.MAINTAINER_EMAIL), committer=None):
        committer = committer or author
        env = dict(os.environ, GIT_AUTHOR_NAME=author[0], GIT_AUTHOR_EMAIL=author[1],
                   GIT_COMMITTER_NAME=committer[0], GIT_COMMITTER_EMAIL=committer[1])
        self.git('-c', 'commit.gpgsign=false', 'commit', '-q', '--allow-empty',
                 '-m', 'synthetic fixture', env=env)
        return self.git('rev-parse', 'HEAD')

    def run_check(self, base=None, head=None, event='pull_request'):
        return subprocess.run(['python3', str(Path(checker.__file__).resolve())],
                              cwd=self.repo, env=dict(os.environ, GITHUB_EVENT_NAME=event,
                              PR_BASE_SHA=self.base if base is None else base,
                              PR_HEAD_SHA=self.git('rev-parse', 'HEAD') if head is None else head),
                              capture_output=True, text=True, timeout=20)

    def test_maintainer_aliases_and_historical_commits(self):
        self.commit()
        self.commit(('xPROMSx', checker.MAINTAINER_EMAIL))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2 introduced commits', result.stdout)

    def test_noreply_web_merge_and_bot_identities(self):
        user = ('fixture-user', '12345+fixture-user@users.noreply.github.com')
        self.commit(user)
        self.commit(('fixture-old', 'fixture-old@users.noreply.github.com'))
        self.commit(('github-actions[bot]', '41898282+github-actions[bot]@users.noreply.github.com'))
        other = self.git('rev-parse', 'HEAD')
        tree = self.git('rev-parse', 'HEAD^{tree}')
        env = dict(os.environ, GIT_AUTHOR_NAME=user[0], GIT_AUTHOR_EMAIL=user[1],
                   GIT_COMMITTER_NAME='GitHub', GIT_COMMITTER_EMAIL='noreply@github.com')
        merge = self.git('-c', 'commit.gpgsign=false', 'commit-tree', tree,
                         '-p', other, '-p', self.base, input=b'synthetic web merge\n', env=env)
        result = self.run_check(head=merge)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_author_and_committer_fail_without_disclosure(self):
        for role in ('author', 'committer'):
            with self.subTest(role=role):
                self.git('reset', '--hard', self.base)
                private = ('Private Fixture', 'private@example.invalid')
                public = ('Proms', checker.MAINTAINER_EMAIL)
                sha = self.commit(private if role == 'author' else public,
                                  private if role == 'committer' else public)
                result = self.run_check()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(sha, result.stderr)
                self.assertIn(role, result.stderr)
                self.assertNotIn(private[0], result.stdout + result.stderr)
                self.assertNotIn(private[1], result.stdout + result.stderr)

    def test_wrong_alias_email_and_non_noreply_bot_are_rejected(self):
        for identity in [('Proms', '12345+fixture-user@users.noreply.github.com'),
                         ('fixture-user', checker.MAINTAINER_EMAIL),
                         ('github-actions[bot]', 'bot@example.invalid'),
                         ('GitHub', 'web@example.invalid')]:
            with self.subTest(identity=identity):
                self.git('reset', '--hard', self.base)
                self.commit(identity)
                self.assertNotEqual(self.run_check().returncode, 0)

    def test_invalid_missing_zero_and_unavailable_sha(self):
        self.commit()
        for value in ['', '0' * 40, 'f' * 40, '--all', 'HEAD', '1' * 39, '1' * 40 + '\n']:
            with self.subTest(value=value):
                result = self.run_check(base=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('Traceback', result.stderr)
        self.assertNotEqual(self.run_check(head='').returncode, 0)

    def test_empty_reversed_and_unrelated_ranges(self):
        head = self.commit()
        self.assertNotEqual(self.run_check(base=head).returncode, 0)
        self.assertNotEqual(self.run_check(base=head, head=self.base).returncode, 0)
        tree = self.git('rev-parse', 'HEAD^{tree}')
        env = dict(os.environ, GIT_AUTHOR_NAME='Proms', GIT_AUTHOR_EMAIL=checker.MAINTAINER_EMAIL,
                   GIT_COMMITTER_NAME='Proms', GIT_COMMITTER_EMAIL=checker.MAINTAINER_EMAIL)
        unrelated = self.git('commit-tree', tree, input=b'unrelated\n', env=env)
        self.assertNotEqual(self.run_check(base=unrelated).returncode, 0)

    def test_diverged_target_checks_only_introduced_commits(self):
        head = self.commit()
        self.git('reset', '--hard', self.base)
        target = self.commit(('Legacy Fixture', 'legacy@example.invalid'))
        self.assertEqual(self.run_check(base=target, head=head).returncode, 0)

    def test_shallow_history_is_rejected(self):
        self.commit()
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder) / 'shallow'
            subprocess.run(['git', 'clone', '-q', '--depth=1', self.repo.as_uri(), str(clone)],
                           check=True, capture_output=True)
            with self.assertRaises(checker.ValidationError):
                checker.validate(self.base, self.git('rev-parse', 'HEAD'), clone)

    def test_oversized_range_is_rejected(self):
        self.commit()
        self.commit()
        with self.assertRaises(checker.ValidationError):
            checker.validate(self.base, self.git('rev-parse', 'HEAD'), self.repo, max_commits=1)

    def test_malformed_metadata_cannot_bypass_check(self):
        head = self.commit()
        raw = self.git('cat-file', 'commit', head).encode()
        for role in (b'author', b'committer'):
            with self.subTest(role=role):
                line = next(x for x in raw.splitlines() if x.startswith(role + b' '))
                broken = raw.replace(line, line + b'\n' + line)
                sha = self.git('hash-object', '--literally', '-t', 'commit', '-w', '--stdin', input=broken)
                result = self.run_check(head=sha)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(role.decode(), result.stderr)
                self.assertNotIn(checker.MAINTAINER_EMAIL, result.stderr)
        broken = raw.replace(b'<'+checker.MAINTAINER_EMAIL.encode()+b'>', b'<bad\x00@example.invalid>')
        sha = self.git('hash-object', '--literally', '-t', 'commit', '-w', '--stdin', input=broken)
        self.assertNotEqual(self.run_check(head=sha).returncode, 0)

    def test_push_and_manual_do_not_scan_historical_identity(self):
        for event in ('push', 'workflow_dispatch'):
            result = self.run_check(event=event, base='', head='')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SKIP', result.stdout)
        self.assertNotEqual(self.run_check(event='unexpected').returncode, 0)
