"""Release packaging uses immutable Git content, not the working-tree installer."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_personal_xhttp import ROOT, SOURCE


class ReleaseAsset(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='release-asset-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'repo'; self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Proms')
        self.git('config', 'user.email', '102687702+xPROMSx@users.noreply.github.com')
        (self.repo/'x-ui-latest.sh').write_text(SOURCE)
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD').strip()
        self.git('tag', 'v2.1.5')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True, stderr=subprocess.PIPE)

    def prepare(self, directory, tag='v2.1.5', sha=None):
        return subprocess.run(['python3',str(ROOT/'tools/prepare_release.py'),tag,sha or self.sha,str(directory)],
            cwd=self.repo, capture_output=True, text=True, timeout=15)

    def test_reproducible_pinned_asset_override_and_interactive_stdin(self):
        first, second = self.root/'first', self.root/'second'
        self.assertEqual(self.prepare(first).returncode,0)
        # A later development commit and dirty source cannot alter a historical asset.
        (self.repo/'x-ui-latest.sh').write_text(SOURCE+'\n# later development\n')
        self.git('commit','-qam','later')
        (self.repo/'x-ui-latest.sh').write_text('dirty source\n')
        self.assertEqual(self.prepare(second).returncode,0)
        asset=(first/'x-ui-latest.sh').read_bytes()
        self.assertEqual(asset,(second/'x-ui-latest.sh').read_bytes())
        self.assertEqual((self.repo/'x-ui-latest.sh').read_text(),'dirty source\n')
        self.assertEqual((first/'x-ui-latest.sh.sha256').read_text(),hashlib.sha256(asset).hexdigest()+'  x-ui-latest.sh\n')
        init=re.search(r'^PROJECT_REF=.*?^configure_project_source \|\| exit 1$',asset.decode(),re.M|re.S)[0]
        for override, expected in (('',self.sha),('v2.1.4','v2.1.4'),('a'*40,'a'*40)):
            result=subprocess.run(['bash','-eu','-c',init+'\nread -r reply; printf "%s|%s" "$GITHUB_RAW" "$reply"'],
                input='interactive answer\n',env={**os.environ,'XUI_AUTO_REF':override},capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout,f'https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/{expected}|interactive answer')

    def test_invalid_tags_shas_contracts_and_existing_outputs_fail(self):
        existing=self.root/'existing';existing.mkdir();(existing/'keep').write_text('untouched')
        for tag,sha in (('v2.1.5-rc1',self.sha),('missing',self.sha),('v2.1.6',self.sha),
                        ('v2.1.5','main'),('v2.1.5','0'*40)):
            output=self.root/'output'
            result=self.prepare(output,tag,sha)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Release preparation failed:',result.stderr)
            self.assertFalse(output.exists())
        self.assertNotEqual(self.prepare(existing).returncode,0)
        self.assertEqual((existing/'keep').read_text(),'untouched')
        (self.repo/'x-ui-latest.sh').write_text(SOURCE.replace('${XUI_AUTO_REF:-main}','${XUI_AUTO_REF:-v2.1.4}'))
        self.git('commit','-qam','invalid source contract');self.git('tag','v2.1.6')
        self.assertNotEqual(self.prepare(self.root/'bad','v2.1.6',self.git('rev-parse','HEAD').strip()).returncode,0)
        self.assertFalse((self.root/'bad').exists())


if __name__ == '__main__': unittest.main()
