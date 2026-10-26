"""Release packaging uses immutable Git content, not the working-tree installer."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

from test_personal_xhttp import ROOT, SOURCE


# Only the GitHub boundary is simulated. Git refs, builder, Bash, downloads'
# bytes, checksum verification and source-ref checks execute real local tools.
GH_FIXTURE = r'''#!/usr/bin/env python3
import json, os, pathlib, re, shutil, subprocess, sys
state_path=pathlib.Path(os.environ['RELEASE_STATE'])
state=json.loads(state_path.read_text()); args=sys.argv[1:]
state['calls'].append(args)
def save(): state_path.write_text(json.dumps(state))
def fail(message='simulated GitHub failure'):
    save(); print(message,file=sys.stderr); sys.exit(1)
def flag(name): return args[args.index(name)+1]
if args[0]=='api':
    path=next(a for a in args if a.startswith('repos/'))
    if path.endswith('/branches/main'):
        print(str(state['protected']).lower()+'\t'+state['main_sha'])
    elif '/git/matching-refs/tags/' in path:
        if state['fault']=='lookup': fail()
        print(1 if state['tag'] else 0)
    elif '/releases?per_page=100' in path:
        assert '--paginate' in args
        assert flag('--jq')=='.[] | select(.tag_name == "'+os.environ['RELEASE_VERSION']+'") | .id'
        if state['fault']=='release_lookup' or (state['release'] and state['fault']=='draft_list_api'): fail()
        # Matching draft is on a later page, after a similarly named release.
        pages=[[{'id':7,'tag_name':'v2.1.50'}],[]]
        if state['release'] and state['fault']!='draft_missing':
            pages[1].append(state['release'])
            if state['fault']=='draft_duplicate': pages[1].append({**state['release'],'id':43})
        for page in pages:
            for release in page:
                if release['tag_name']==os.environ['RELEASE_VERSION']:
                    print('invalid' if state['fault']=='draft_list_id' else release['id'])
    elif path.endswith('/git/refs') and flag('--method')=='POST':
        values=dict(a.split('=',1) for a in args if a.startswith(('ref=','sha=')))
        if state['tag']: fail()
        subprocess.run(['git','--git-dir',state['remote'],'update-ref',values['ref'],values['sha'],'0'*40],check=True)
        state['tag']=values['sha']; state['mutations'].append('tag')
    elif '/git/ref/tags/' in path:
        print(state['tag'])
    elif '/releases/tags/' in path:
        fail('HTTP 404: draft lookup by tag is unavailable')
    elif re.search(r'/releases/[0-9]+$',path):
        assert path.endswith('/releases/'+str(state['release']['id']))
        if state['fault']=='draft_get_api': fail()
        release=json.loads(json.dumps(state['release']))
        if state['fault']=='draft_wrong_id': release['id']+=1
        if state['fault']=='draft_wrong_tag': release['tag_name']='v2.1.50'
        if state['fault']=='draft_wrong_source': release['target_commitish']='a'*40
        if state['fault']=='draft_missing_metadata': del release['draft']
        if state['fault']=='draft_not_draft': release['draft']=False
        if state['fault']=='draft_prerelease': release['prerelease']=True
        if state['fault']=='draft_assets': release['assets'].pop()
        print('invalid JSON' if state['fault']=='draft_json' else json.dumps(release))
    else: raise AssertionError('Unexpected API operation')
elif args[:2]==['release','create']:
    assert '--draft' in args and '--verify-tag' in args
    assert flag('--notes')=='' and '--generate-notes' not in args
    assert flag('--target')==state['main_sha'] and state['tag']==state['main_sha']
    if state['release'] or state['fault']=='create': fail()
    state['release']={'id':42,'draft':True,'prerelease':False,'tag_name':args[2],
        'target_commitish':flag('--target'),'html_url':'https://github.com/xPROMSx/3x-ui-auto-nginx/releases/tag/'+args[2],
        'assets':[]}
    state['mutations'].append('draft')
    for name in ('x-ui-latest.sh','x-ui-latest.sh.sha256'):
        if state['fault']=='upload' and name.endswith('.sha256'): fail()
        source=next(pathlib.Path(a) for a in args if a.endswith('/'+name))
        shutil.copyfile(source,pathlib.Path(state['assets'])/name)
        state['release']['assets'].append({'name':name,'size':source.stat().st_size})
        state['mutations'].append('upload:'+name)
elif args[:2]==['release','download']:
    directory=pathlib.Path(flag('--dir')); directory.mkdir()
    for item in state['release']['assets']:
        shutil.copyfile(pathlib.Path(state['assets'])/item['name'],directory/item['name'])
    if state['fault']=='download':
        with (directory/'x-ui-latest.sh').open('ab') as file: file.write(b'tampered')
else: raise AssertionError('Unexpected GitHub operation')
save()
'''


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
        init=re.search(r'^PROJECT_REF=.*?^configure_project_source \|\| return 1 2>/dev/null \|\| exit 1$',asset.decode(),re.M|re.S)[0]
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

    def workflow_block(self, name):
        workflow=(ROOT/'.github/workflows/prepare-release.yml').read_text()
        block=re.search(r'      - name: '+re.escape(name)+r'\n        run: \|\n((?:(?:          .*)?\n)+)',workflow)
        self.assertIsNotNone(block,'Missing executable workflow step: '+name)
        return textwrap.dedent(block[1])

    def workflow_fixture(self, fault=''):
        self.git('tag','-d','v2.1.5'); self.git('branch','-M','main')
        (self.repo/'tools').mkdir()
        shutil.copyfile(ROOT/'tools/prepare_release.py',self.repo/'tools/prepare_release.py')
        if fault=='build':
            (self.repo/'x-ui-latest.sh').write_text(SOURCE.replace('${XUI_AUTO_REF:-main}','${XUI_AUTO_REF:-v2.1.4}'))
        self.git('add','.'); self.git('commit','-qm','workflow fixture')
        self.sha=self.git('rev-parse','HEAD').strip()
        remote=self.root/'remote.git'
        subprocess.run(['git','init','--bare','-q',remote],check=True)
        self.git('remote','add','origin',str(remote)); self.git('push','-q','origin','main')
        self.api_assets=self.root/'api-assets'; self.api_assets.mkdir()
        self.api_state=self.root/'api-state.json'
        self.api_state.write_text(json.dumps({'main_sha':self.sha,'protected':True,'tag':None,'release':None,
            'remote':str(remote),'assets':str(self.api_assets),'fault':fault,'calls':[],'mutations':[]}))
        commands=self.root/'commands'; commands.mkdir()
        (commands/'gh').write_text(GH_FIXTURE); (commands/'gh').chmod(0o755)
        self.workflow_env={**os.environ,'PATH':str(commands)+':'+os.environ['PATH'],
            'GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main','GITHUB_SHA':self.sha,
            'GITHUB_REPOSITORY':'xPROMSx/3x-ui-auto-nginx','RELEASE_VERSION':'v2.1.5',
            'RUNNER_TEMP':str(self.root),'GITHUB_STEP_SUMMARY':str(self.root/'summary'),
            'RELEASE_STATE':str(self.api_state)}

    def run_workflow(self, **overrides):
        script=self.workflow_block('Require main and a stable version')+'\n'+self.workflow_block('Prepare verified draft release')
        return subprocess.run(['bash','-euo','pipefail','-c',script],cwd=self.repo,
            env={**self.workflow_env,**overrides},capture_output=True,text=True,timeout=25)

    def test_release_workflow_is_manual_and_has_only_release_permissions(self):
        workflow=(ROOT/'.github/workflows/prepare-release.yml').read_text()
        triggers=workflow.split('\non:\n',1)[1].split('\npermissions:',1)[0]
        self.assertEqual(re.findall(r'^  ([a-z_]+):',triggers,re.M),['workflow_dispatch'])
        self.assertIn('contents: read',workflow); self.assertEqual(workflow.count('contents: write'),1)
        self.assertIn('ref: ${{ github.sha }}',workflow)
        self.assertIn('fetch-depth: 0',workflow); self.assertIn('persist-credentials: false',workflow)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertIn('GH_TOKEN: ${{ github.token }}',workflow)
        self.assertNotRegex(workflow,r'continue-on-error|--generate-notes|release edit|--clobber|secrets\.|apt-get|tests/fresh|--suite')
        self.assertLess(workflow.index('name: Require main'),workflow.index('uses: actions/checkout'))

    def test_release_workflow_builds_verified_draft_and_refuses_repeat(self):
        self.workflow_fixture()
        result=self.run_workflow(); self.assertEqual(result.returncode,0,result.stderr)
        state=json.loads(self.api_state.read_text())
        self.assertEqual(state['tag'],self.sha)
        self.assertTrue(state['release']['draft']); self.assertFalse(state['release']['prerelease'])
        self.assertEqual(sorted(a['name'] for a in state['release']['assets']),['x-ui-latest.sh','x-ui-latest.sh.sha256'])
        self.assertIn(state['release']['html_url'],(self.root/'summary').read_text())
        self.assertIn(self.sha,(self.root/'summary').read_text())
        self.assertIn(f'PROJECT_REF="${{XUI_AUTO_REF:-{self.sha}}}"'.encode(),(self.api_assets/'x-ui-latest.sh').read_bytes())
        api_paths=[next(a for a in call if a.startswith('repos/')) for call in state['calls'] if call[0]=='api']
        self.assertEqual(sum(path.endswith('/releases?per_page=100') for path in api_paths),2)
        self.assertTrue(api_paths[-1].endswith('/releases/42'))
        self.assertFalse(any('/releases/tags/' in path for path in api_paths))
        by_tag=subprocess.run(['gh','api','repos/xPROMSx/3x-ui-auto-nginx/releases/tags/v2.1.5'],
            env=self.workflow_env,capture_output=True,text=True,timeout=5)
        self.assertNotEqual(by_tag.returncode,0); self.assertIn('HTTP 404',by_tag.stderr)
        before={p.name:p.read_bytes() for p in self.api_assets.iterdir()}
        repeated=self.run_workflow(); self.assertNotEqual(repeated.returncode,0)
        self.assertIn('already exists',repeated.stdout+repeated.stderr)
        self.assertEqual(json.loads(self.api_state.read_text())['mutations'],state['mutations'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.api_assets.iterdir()})

    def test_release_workflow_preflight_errors_do_not_create_resources(self):
        self.workflow_fixture()
        original=json.loads(self.api_state.read_text())
        for scenario in ('branch','event','fork','version','injection','sha','checkout','unprotected','tag','release','lookup','release_lookup'):
            with self.subTest(scenario=scenario):
                state=json.loads(json.dumps(original)); env={}
                if scenario=='branch': env['GITHUB_REF']='refs/heads/feature'
                if scenario=='event': env['GITHUB_EVENT_NAME']='push'
                if scenario=='fork': env['GITHUB_REPOSITORY']='fixture/fork'
                if scenario=='version': env['RELEASE_VERSION']='v2.1.5-rc1'
                if scenario=='injection': env['RELEASE_VERSION']='v2.1.5\n$(touch injected)'
                if scenario=='sha': state['main_sha']='a'*40
                if scenario=='checkout': state['main_sha']='a'*40; env['GITHUB_SHA']='a'*40
                if scenario=='unprotected': state['protected']=False
                if scenario=='tag': state['tag']=self.sha
                if scenario=='release': state['release']={'id':42,'draft':True,'tag_name':'v2.1.5'}
                if scenario in ('lookup','release_lookup'): state['fault']=scenario
                self.api_state.write_text(json.dumps(state))
                result=self.run_workflow(**env); self.assertNotEqual(result.returncode,0,scenario)
                after=json.loads(self.api_state.read_text())
                self.assertEqual(after['mutations'],[])
                self.assertEqual((after['tag'],after['release']),(state['tag'],state['release']))
                self.assertFalse((self.repo/'injected').exists())

    def test_release_workflow_partial_failures_are_never_published_or_overwritten(self):
        for fault in ('build','create','upload','download'):
            with self.subTest(fault=fault):
                f=ReleaseAsset('runTest'); f.setUp(); self.addCleanup(f.doCleanups); f.workflow_fixture(fault)
                result=f.run_workflow(); self.assertNotEqual(result.returncode,0)
                state=json.loads(f.api_state.read_text())
                self.assertEqual(state['tag'],f.sha)
                self.assertEqual(state['release'] is not None,fault in ('upload','download'))
                if state['release']: self.assertTrue(state['release']['draft'])
                self.assertFalse((f.root/'summary').exists(),'Partial draft must not be reported as prepared')
                before={p.name:p.read_bytes() for p in f.api_assets.iterdir()}
                self.assertNotEqual(f.run_workflow().returncode,0)
                self.assertEqual(json.loads(f.api_state.read_text())['mutations'],state['mutations'])
                self.assertEqual(before,{p.name:p.read_bytes() for p in f.api_assets.iterdir()})

    def test_release_workflow_draft_lookup_failures_never_report_success(self):
        faults=('draft_missing','draft_duplicate','draft_list_id','draft_list_api','draft_get_api',
                'draft_wrong_id','draft_wrong_tag','draft_wrong_source','draft_missing_metadata',
                'draft_not_draft','draft_prerelease','draft_assets','draft_json')
        for fault in faults:
            with self.subTest(fault=fault):
                f=ReleaseAsset('runTest'); f.setUp(); self.addCleanup(f.doCleanups); f.workflow_fixture(fault)
                result=f.run_workflow(); self.assertNotEqual(result.returncode,0)
                state=json.loads(f.api_state.read_text())
                self.assertTrue(state['release']['draft'])
                self.assertEqual(state['mutations'],['tag','draft','upload:x-ui-latest.sh','upload:x-ui-latest.sh.sha256'])
                # Fail at final lookup/metadata verification, after both downloads.
                download=next(i for i,c in enumerate(state['calls']) if c[:2]==['release','download'])
                final=state['calls'][download+1:]
                self.assertTrue(any('/releases?per_page=100' in ' '.join(c) for c in final))
                if fault not in ('draft_missing','draft_duplicate','draft_list_id','draft_list_api'):
                    self.assertTrue(any(c[0]=='api' and c[1].endswith('/releases/42') for c in final))
                self.assertFalse((f.root/'summary').exists())
                before={p.name:p.read_bytes() for p in f.api_assets.iterdir()}
                self.assertNotEqual(f.run_workflow().returncode,0)
                self.assertEqual(json.loads(f.api_state.read_text())['mutations'],state['mutations'])
                self.assertEqual(before,{p.name:p.read_bytes() for p in f.api_assets.iterdir()})


if __name__ == '__main__': unittest.main()
