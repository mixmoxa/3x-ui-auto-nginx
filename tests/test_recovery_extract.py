"""Recovery-only extraction against an actual Backup v3 fixture, as nonroot."""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

from test_personal_backup import PersonalBackup

SCRIPT = Path(__file__).resolve().parents[1] / 'assets/backup/x-ui-backup.sh'


class RecoveryExtract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = PersonalBackup('runTest')
        try:
            fixture.setUp()
            archive = fixture.backup()
            cls.entries = []
            # Undo only the existing fixture's filesystem relocation in member names.
            # Payloads remain byte-for-byte from the real backup command.
            prefix = 'files' + str(fixture.root)
            with tarfile.open(archive) as source:
                for member in source:
                    data = source.extractfile(member).read() if member.isfile() else None
                    member = copy.copy(member)
                    if member.name.startswith(prefix):
                        member.name = 'files' + member.name[len(prefix):]
                    elif member.name != 'meta.json':
                        continue  # Ancestors of the private fixture root, not project data.
                    if member.linkname.startswith(str(fixture.root)):
                        member.linkname = member.linkname[len(str(fixture.root)):]
                    elif member.linkname.startswith(prefix):
                        member.linkname = 'files' + member.linkname[len(prefix):]
                    member.uid = member.gid = 0
                    member.uname = member.gname = 'root'
                    cls.entries.append((member, data))
        finally:
            fixture.doCleanups()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='recovery-extract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'backup.tar.gz'
        self.output = self.root / 'recovered'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.bin / 'python3').symlink_to(sys.executable)
        self.calls = self.root / 'forbidden-calls'
        for name in ('systemctl', 'apt-get', 'apt', 'nginx', 'ufw', 'certbot', 'curl',
                     'gzip', 'tar', 'sqlite3', 'uname', 'ip'):
            path = self.bin / name
            path.write_text('#!' + sys.executable + '\nfrom pathlib import Path\n'
                            + f'Path({str(self.calls)!r}).write_text({name!r})\nraise SystemExit(97)\n')
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.bash = shutil.which('bash')
        self.pack()

    def pack(self, changes=None, omit=(), extra=()):
        changes = changes or {}
        with tarfile.open(self.archive, 'w:gz') as target:
            for original, payload in [*self.entries, *extra]:
                if original.name in omit:
                    continue
                member = copy.copy(original)
                payload = changes.get(member.name, payload)
                if payload is not None:
                    member.size = len(payload)
                target.addfile(member, io.BytesIO(payload) if payload is not None else None)

    def run_extract(self, output=None, **env):
        before = hashlib.sha256(self.archive.read_bytes()).digest()
        result = subprocess.run([self.bash, str(SCRIPT), 'extract', str(self.archive),
                                 str(self.output if output is None else output)],
                                env={**self.env, **env}, capture_output=True, text=True, timeout=30)
        self.assertTrue(before == hashlib.sha256(self.archive.read_bytes()).digest(), 'Source archive changed')
        self.assertFalse(self.calls.exists(), 'Recovery extraction invoked a host/dependency command')
        for secret in ('fixture-secret-not-for-output', '-----BEGIN PRIVATE KEY-----'):
            self.assertNotIn(secret, result.stdout + result.stderr)
        return result

    def test_full_v3_bytes_private_modes_and_no_execution(self):
        marker = self.root / 'must-not-execute'
        executable = ('#!/bin/sh\ntouch ' + str(marker) + '\n').encode()
        self.pack(changes={'files/usr/local/x-ui/x-ui': executable})
        strict = subprocess.run([self.bash, '-c', 'source \"$1\"; validate_archive \"$2\"',
                                 'fixture', str(SCRIPT), str(self.archive)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(strict.returncode, 0, strict.stderr)
        result = self.run_extract()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        regular = [(m, executable if m.name == 'files/usr/local/x-ui/x-ui' else b)
                   for m, b in self.entries if m.isfile()]
        self.assertIn(f'Files: {len(regular)}', result.stdout)
        self.assertIn(f'Skipped links: {sum(m.issym() or m.islnk() for m, _ in self.entries)}', result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 4)
        self.assertIn(str(self.output), result.stdout)
        self.assertIn('private keys', result.stdout)
        for member, data in regular:
            path = self.output / member.name
            self.assertTrue(path.read_bytes() == data, 'Extracted file bytes differ')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for path in [self.output, *self.output.rglob('*')]:
            self.assertFalse(path.is_symlink())
            if path.is_dir(): self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertTrue((self.output / 'files/etc/x-ui/x-ui.db').is_file())
        self.assertTrue((self.output / 'files/etc/letsencrypt/live/example.com/fullchain.pem').is_file())
        self.assertTrue((self.output / 'files/etc/letsencrypt/live/example.com/privkey.pem').is_file())

    def test_incomplete_or_incompatible_state_is_still_data(self):
        meta = json.loads(next(data for m, data in self.entries if m.name == 'meta.json'))
        scenarios = [({'meta.json': json.dumps({**meta, 'os_version': '99'}).encode()}, ()),
                     ({'files/etc/x-ui/x-ui.db': b'not a SQLite database'}, ()),
                     ({}, ('files/usr/bin/x-ui',)), ({}, ('meta.json',)),
                     ({'meta.json': b'broken JSON with private-data'}, ())]
        for index, (changes, omit) in enumerate(scenarios):
            with self.subTest(scenario=index):
                self.pack(changes=changes, omit=omit)
                result = self.run_extract(self.root / f'data-{index}')
                self.assertEqual(result.returncode, 0, result.stderr)
                data = (self.root / f'data-{index}/files/etc/x-ui/x-ui.db').read_bytes()
                expected = changes.get('files/etc/x-ui/x-ui.db', next(b for m,b in self.entries if m.name=='files/etc/x-ui/x-ui.db'))
                self.assertTrue(data == expected, 'DB must be extracted as opaque bytes')
        member = tarfile.TarInfo('files/opt/AdGuardHome/data/saved-data'); member.mode = 0o755
        self.pack(changes={'meta.json': b'incomplete'}, extra=[(member, b'opaque AGH data')])
        self.assertEqual(self.run_extract().returncode, 0)
        self.assertTrue((self.output / member.name).read_bytes() == b'opaque AGH data')

    def test_unsafe_structure_is_rejected_before_output(self):
        cases = []
        for name in ('../escape', '/etc/shadow', 'files/etc/nginx/../../escape',
                     'files/etc/nginx//bad', 'files/etc/nginx/./bad', 'files/etc/shadow',
                     'files/etc/nginx/line\nbreak', 'meta.json'):
            cases.append((tarfile.TarInfo(name), b'unsafe'))
        for kind in (tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE):
            m = tarfile.TarInfo('files/etc/nginx/special'); m.type = kind
            cases.append((m, None))
        for kind, link in ((tarfile.SYMTYPE, '/etc/shadow'), (tarfile.SYMTYPE, '../../../../escape'),
                           (tarfile.LNKTYPE, '../escape'), (tarfile.LNKTYPE, '/etc/shadow')):
            m = tarfile.TarInfo('files/etc/nginx/bad-link'); m.type = kind; m.linkname = link
            cases.append((m, None))
        for index, entry in enumerate(cases):
            with self.subTest(case=index):
                self.pack(extra=[entry])
                result = self.run_extract(PYTHONOPTIMIZE='1')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
        parent = tarfile.TarInfo('files/etc/nginx/parent')
        child = tarfile.TarInfo('files/etc/nginx/parent/child')
        self.pack(extra=[(child, b'data'), (parent, b'not a directory')])
        self.assertNotEqual(self.run_extract().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_safe_links_are_counted_but_never_materialized(self):
        link = tarfile.TarInfo('files/etc/nginx/hardcopy'); link.type = tarfile.LNKTYPE
        link.linkname = 'files/etc/nginx/nginx.conf'
        self.pack(extra=[(link, None)])
        result = self.run_extract()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.output / link.name).exists())
        self.assertIn(f'Skipped links: {1+sum(m.issym() or m.islnk() for m,_ in self.entries)}', result.stdout)

    def test_existing_output_and_symlink_ancestors_preserve_foreign_data(self):
        foreign = self.root / 'foreign'; foreign.mkdir(); (foreign / 'sentinel').write_bytes(b'keep')
        self.output.mkdir(); (self.output / 'sentinel').write_bytes(b'keep')
        self.assertNotEqual(self.run_extract().returncode, 0)
        self.assertTrue((self.output / 'sentinel').read_bytes() == b'keep')
        alias = self.root / 'alias'; alias.symlink_to(foreign, target_is_directory=True)
        for path in (alias, alias / 'new'):
            self.assertNotEqual(self.run_extract(path).returncode, 0)
            self.assertTrue(alias.is_symlink())
            self.assertEqual(sorted(p.name for p in foreign.iterdir()), ['sentinel'])
        existing = self.root / 'existing-file'; existing.write_bytes(b'keep')
        self.assertNotEqual(self.run_extract(existing).returncode, 0)
        self.assertTrue(existing.read_bytes() == b'keep')

    def test_physical_corruption_is_not_partial_recovery(self):
        original = self.archive.read_bytes()
        short = io.BytesIO()
        with tarfile.open(fileobj=short, mode='w') as tar:
            m = tarfile.TarInfo('files/etc/x-ui/x-ui.db'); m.size = 4096
            tar.addfile(m, io.BytesIO(b'x'*4096))
        cases = [b'not gzip', original[:-8], original[:-8]+bytes([original[-8]^1])+original[-7:],
                 gzip.compress(short.getvalue()[:514])]
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                self.archive.write_bytes(data)
                self.assertNotEqual(self.run_extract().returncode, 0)
                self.assertFalse(self.output.exists())

    def python_fault(self, body):
        interpreter = self.bin / 'python3'; interpreter.unlink()
        interpreter.write_text('#!' + sys.executable + '\nimport os, shutil, signal, sys\n'
                               + 'from pathlib import Path\noriginal = shutil.copyfileobj\n'
                               + body + '\nsys.argv = sys.argv[1:]\nexec(compile(sys.stdin.read(), "production-extract", "exec"))\n')
        interpreter.chmod(0o755)

    def test_partial_write_and_interrupt_clean_private_output(self):
        marker = self.root / 'write-reached'
        for action in ('raise OSError("controlled write failure")', 'signal.raise_signal(signal.SIGTERM)'):
            with self.subTest(action=action):
                self.python_fault(f'def fail(src, dst, *args):\n    Path({str(marker)!r}).touch()\n    dst.write(src.read(1))\n    '+action+'\nshutil.copyfileobj = fail')
                self.assertNotEqual(self.run_extract().returncode, 0)
                self.assertTrue(marker.exists(), 'Reached a partial write before failure')
                marker.unlink()
                self.assertFalse(self.output.exists(), 'Partial secrets must be cleaned')
                (self.bin / 'python3').unlink(); (self.bin / 'python3').symlink_to(sys.executable)

    def test_output_root_swapped_between_mkdir_and_open_is_not_used_or_cleaned(self):
        for kind in ('public', 'foreign-owner'):
            with self.subTest(kind=kind):
                self.output = self.root / ('recovered-' + kind)
                foreign = self.root / ('foreign-' + kind); foreign.mkdir(mode=0o700)
                foreign.chmod(0o777 if kind == 'public' else 0o700)
                (foreign / 'sentinel').write_bytes(b'keep')
                before = foreign.stat()
                moved = self.root / ('created-' + kind)
                marker = self.root / ('mkdir-swap-' + kind)
                self.python_fault(
                    'mkdir_original = os.mkdir\nfstat_original = os.fstat\n'
                    'def swap(path, mode=0o777, *, dir_fd=None):\n'
                    '    result = mkdir_original(path, mode, dir_fd=dir_fd)\n'
                    f'    if path == {self.output.name!r} and not Path({str(marker)!r}).exists():\n'
                    f'        Path({str(self.output)!r}).rename({str(moved)!r})\n'
                    f'        Path({str(foreign)!r}).rename({str(self.output)!r})\n'
                    f'        Path({str(marker)!r}).touch()\n'
                    '    return result\n'
                    'def reported_owner(fd):\n    info = fstat_original(fd)\n'
                    f'    if {kind!r} == "foreign-owner" and info.st_ino == {before.st_ino}:\n'
                    '        fields = list(info); fields[4] = os.geteuid() + 1\n'
                    '        return os.stat_result(fields)\n    return info\n'
                    'os.mkdir = swap\nos.fstat = reported_owner')
                result = self.run_extract()
                self.assertTrue(marker.exists(), 'Swap occurred exactly after the root mkdir')
                self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['sentinel'],
                                 'Never write secrets into, or clean, the substituted directory')
                self.assertTrue((self.output / 'sentinel').read_bytes() == b'keep')
                after = self.output.stat()
                self.assertEqual((after.st_dev, after.st_ino, after.st_uid, after.st_gid, after.st_mode),
                                 (before.st_dev, before.st_ino, before.st_uid, before.st_gid, before.st_mode))
                self.assertEqual(list(moved.iterdir()), [])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Output directory must be owned by the current user with mode 0700', result.stderr)
                (self.bin / 'python3').unlink(); (self.bin / 'python3').symlink_to(sys.executable)

    def test_untrusted_writable_output_ancestors_are_rejected(self):
        parent = self.root / 'writable'; parent.mkdir()
        for permissions in (0o777, 0o770):
            with self.subTest(permissions=permissions):
                parent.chmod(permissions)
                nested = parent / 'private'; nested.mkdir(mode=0o700, exist_ok=True)
                result = self.run_extract(nested / 'recovered')
                self.assertFalse((nested / 'recovered').exists(), 'Reject before output creation')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Untrusted output ancestor', result.stderr)

    def test_trusted_sticky_parent_allows_private_output(self):
        parent = self.root / 'sticky'; parent.mkdir(); parent.chmod(0o1777)
        self.output = parent / 'recovered'
        result = self.run_extract()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.stat().st_uid, os.geteuid())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)

    def test_swapped_output_child_cannot_redirect_writes_or_cleanup(self):
        foreign = self.root / 'foreign'; foreign.mkdir(); (foreign / 'sentinel').write_bytes(b'keep')
        marker = self.root / 'swap-reached'
        self.python_fault(f'def swap(src, dst, *args):\n    out = Path({str(self.output)!r})\n'
                          f'    if (out/"files").is_dir() and not Path({str(marker)!r}).exists():\n'
                          f'        (out/"files").rename(out/"original")\n        (out/"files").symlink_to({str(foreign)!r}, target_is_directory=True)\n'
                          f'        Path({str(marker)!r}).touch()\n    return original(src, dst, *args)\nshutil.copyfileobj = swap')
        self.assertNotEqual(self.run_extract().returncode, 0)
        self.assertTrue(marker.exists(), 'Reached the post-open symlink swap')
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['files'])
        self.assertTrue((self.output/'files').is_symlink(), 'Preserve the independently inserted link')
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in foreign.iterdir()), ['sentinel'])
        self.assertTrue((foreign / 'sentinel').read_bytes() == b'keep')

    def test_replaced_output_root_is_not_followed_or_removed(self):
        foreign = self.root / 'foreign'; foreign.mkdir(); (foreign / 'sentinel').write_bytes(b'keep')
        moved = self.root / 'moved-output'; marker = self.root / 'root-swap-reached'
        self.python_fault(f'def swap(src, dst, *args):\n    out = Path({str(self.output)!r})\n'
                          f'    if not Path({str(marker)!r}).exists():\n'
                          f'        out.rename({str(moved)!r})\n        out.symlink_to({str(foreign)!r}, target_is_directory=True)\n'
                          f'        Path({str(marker)!r}).touch()\n    return original(src, dst, *args)\nshutil.copyfileobj = swap')
        self.assertNotEqual(self.run_extract().returncode, 0)
        self.assertTrue(marker.exists())
        self.assertTrue(self.output.is_symlink(), 'Do not remove an independently replaced output')
        self.assertEqual(list(moved.iterdir()), [], 'Clean partial secrets through the pinned original root')
        self.assertEqual(stat.S_IMODE(moved.stat().st_mode), 0o700)
        self.assertEqual(sorted(p.name for p in foreign.iterdir()), ['sentinel'])
        self.assertTrue((foreign / 'sentinel').read_bytes() == b'keep')

    def test_replaced_output_ancestor_cannot_redirect_success_or_cleanup(self):
        parent = self.root / 'parent'; parent.mkdir(); (parent/'prior-data').write_bytes(b'keep')
        self.output = parent / 'recovered'
        foreign = self.root / 'foreign'; foreign.mkdir(); (foreign/'recovered').mkdir()
        (foreign/'recovered/sentinel').write_bytes(b'keep')
        moved = self.root / 'moved-parent'; marker = self.root / 'ancestor-swap-reached'
        self.python_fault(f'def swap(src, dst, *args):\n'
                          f'    if not Path({str(marker)!r}).exists():\n'
                          f'        Path({str(parent)!r}).rename({str(moved)!r})\n'
                          f'        Path({str(parent)!r}).symlink_to({str(foreign)!r}, target_is_directory=True)\n'
                          f'        Path({str(marker)!r}).touch()\n    return original(src, dst, *args)\nshutil.copyfileobj = swap')
        self.assertNotEqual(self.run_extract().returncode, 0)
        self.assertTrue(marker.exists())
        self.assertTrue(parent.is_symlink())
        self.assertFalse((moved/'recovered').exists(), 'Clean only the original private extraction')
        self.assertTrue((moved/'prior-data').read_bytes() == b'keep')
        self.assertEqual(sorted(p.name for p in (foreign/'recovered').iterdir()), ['sentinel'])
        self.assertTrue((foreign/'recovered/sentinel').read_bytes() == b'keep')

    def test_failure_cleanup_preserves_independently_added_file(self):
        for location in ('root', 'nested'):
            with self.subTest(location=location):
                self.output = self.root / ('recovery-' + location)
                marker = self.root / ('independent-write-' + location)
                self.python_fault(f'def fail(src, dst, *args):\n    out = Path({str(self.output)!r})\n'
                                  f'    if {location!r} == "nested" and not (out/"files").exists():\n'
                                  '        return original(src, dst, *args)\n'
                                  f'    parent = out if {location!r} == "root" else Path(os.readlink("/proc/self/fd/"+str(dst.fileno()))).parent\n'
                                  f'    (parent/"independent-user-data").write_bytes(b"keep")\n    Path({str(marker)!r}).touch()\n'
                                  '    dst.write(src.read(1))\n    raise OSError("controlled write failure")\nshutil.copyfileobj = fail')
                self.assertNotEqual(self.run_extract().returncode, 0)
                self.assertTrue(marker.exists())
                independent = list(self.output.rglob('independent-user-data'))
                self.assertEqual(len(independent), 1, 'Never delete independent user data')
                self.assertTrue(independent[0].read_bytes() == b'keep')
                self.assertEqual([p for p in self.output.rglob('*') if p.is_file()], independent,
                                 'Remove all owned partial files, including after a nonempty child')
                self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)

    def test_nonroot_extract_does_not_relax_other_commands(self):
        self.assertNotEqual(os.geteuid(), 0, 'Canonical extraction coverage must run nonroot')
        self.assertEqual(self.run_extract().returncode, 0)
        for command in ('backup', 'restore', 'update-hooks', 'list'):
            result = subprocess.run([self.bash, str(SCRIPT), command], env=self.env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('as root', result.stderr)
        self.assertFalse(self.calls.exists())
