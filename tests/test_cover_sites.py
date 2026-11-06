"""Supplied cover resources and scoped one-time publication; no live services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'assets/cover-sites'

def helper():
    spec=importlib.util.spec_from_file_location('covers',SOURCE/'managed.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class CoverResources(unittest.TestCase):
    def test_all_supplied_variants_and_local_resources(self):
        result=subprocess.run(['python3',str(SOURCE/'tools/test_variants.py')],capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.count('144 combinations'),6)
        tracked=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'ls-files','assets/cover-sites'],cwd=ROOT,text=True)
        self.assertNotIn('__pycache__',tracked);self.assertNotIn('.pyc',tracked)
        self.assertEqual(set(p.name for p in (SOURCE/'templates').iterdir()),{'A1','A2','A3','B1','B2','B3'})

    def test_vision_accepts_only_legacy_and_new_static_roots(self):
        from test_integrated_features import helper as feature
        vision=feature('vision')
        with tempfile.TemporaryDirectory() as directory:
            site=Path(directory)/'vision.conf';acme=Path(directory)/'vision-acme.conf'
            acme.write_text(vision.acme_config('vision.example',False))
            for root in ('/var/www/html','/var/www/html/cover-vision'):
                site.write_text(vision.fallback_config('vision.example',12345,root))
                self.assertEqual(vision.nginx_artifact_domain(site,acme),'vision.example')
                if root == '/var/www/html':
                    self.assertNotIn('absolute_redirect',site.read_text())
                else:
                    # Backups made before relative redirects keep their exact known layout.
                    site.write_text(site.read_text().replace('    absolute_redirect off;\n',''))
                    self.assertEqual(vision.nginx_artifact_domain(site,acme),'vision.example')
            site.write_text(vision.fallback_config('vision.example',12345,'/var/www/html/cover-vision').replace(
                'absolute_redirect off;','absolute_redirect on;'))
            with self.assertRaises(ValueError):vision.nginx_artifact_domain(site,acme)
            site.write_text(vision.fallback_config('vision.example',12345,'/srv/foreign'))
            with self.assertRaises(ValueError):vision.nginx_artifact_domain(site,acme)

    def test_archive_delivery_is_pinned_and_rejects_links_and_wrong_tree(self):
        from test_personal_xhttp import function
        import io, tarfile
        sha='a'*40
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'source.tar.gz';log=root/'urls';marker=root/'executed'
            def bundle(kind):
                with tarfile.open(archive,'w:gz') as out:
                    prefix='3x-ui-auto-nginx-'+('b'*40 if kind=='wrong-tree' else sha)+'/assets/cover-sites/'
                    for relative in ('managed.py','tools/generate.py','tools/check.py','data/variants.json'):
                        name=prefix+relative
                        if kind=='escape' and relative=='managed.py':name=prefix+'../../outside'
                        item=tarfile.TarInfo(name)
                        data=("from pathlib import Path; Path("+repr(str(marker))+").touch()\n").encode() if relative=='managed.py' else b'{}'
                        if kind=='symlink' and relative=='managed.py':
                            item.type=tarfile.SYMTYPE;item.linkname='/etc/passwd';out.addfile(item)
                        else:item.size=len(data);out.addfile(item,io.BytesIO(data))
            script=function('preflight_cover_sites')+'''
pin_project_source() { PROJECT_SOURCE_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; PROJECT_REF=$PROJECT_SOURCE_SHA; }
curl() { printf '%s\n' "$*" > "$URL_LOG"; cp "$FIXTURE_ARCHIVE" "${@: -1}"; }
preflight_cover_sites
'''
            for kind in ('valid','symlink','escape','wrong-tree'):
                stage=root/kind;stage.mkdir();bundle(kind);marker.unlink(missing_ok=True)
                result=subprocess.run(['bash','-c',script],capture_output=True,text=True,env={**os.environ,
                    'PANEL_STAGE':str(stage),'PROJECT_REF':'main','FIXTURE_ARCHIVE':str(archive),'URL_LOG':str(log)})
                self.assertEqual(result.returncode==0,kind=='valid',result.stderr)
                self.assertEqual(marker.exists(),kind=='valid')
                self.assertIn('/tar.gz/'+sha,log.read_text())
            self.assertFalse((root/'outside').exists())

    def test_source_pin_and_preflight_order(self):
        text=(ROOT/'x-ui-latest.sh').read_text();main=text[text.index('main() {'):]
        self.assertLess(main.index('preflight_cover_sites'),main.index('clean_previous_install'))
        self.assertLess(main.index('install_fake_site'),main.index('configure_nginx'))
        self.assertIn('/tar.gz/$PROJECT_SOURCE_SHA',text)
        self.assertIn('|| pin_project_source || return 1',text)
        self.assertNotIn('assets/fake-sites/',text)

class CoverPublication(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.web=self.root/'web';self.state=self.root/'private/cover-sites.json'
        self.m=helper()

    def prepare(self,name,roles):
        path=self.root/name;self.m.prepare(path,self.state,roles);return path

    def test_role_selection_deferred_vision_idempotence_and_verified_cleanup(self):
        stage=self.prepare('base',['panel','reality']);self.m.publish(stage,self.web,self.state,['panel','reality'])
        base=self.m.read_state(self.state);before={r:self.m.tree(self.web/('cover-'+r)) for r in base}
        self.assertTrue(base['panel']['template'].startswith('A'));self.assertTrue(base['reality']['template'].startswith('B'))
        self.assertEqual(self.state.stat().st_mode&0o777,0o600);self.assertEqual(self.state.stat().st_uid,0)
        self.assertFalse((self.web/'cover-vision').exists())
        with patch.object(self.m,'module',side_effect=AssertionError('unexpected regeneration')):
            # Existing public sites are not part of Restore/Change Domains rendering.
            self.assertEqual({r:self.m.tree(self.web/('cover-'+r)) for r in base},before)
        later=self.prepare('later',['panel','reality','vision'])
        self.assertFalse((later/'cover-panel').exists());self.assertFalse((later/'cover-reality').exists())
        self.m.publish(later,self.web,self.state,['vision'])
        state=self.m.read_state(self.state);self.assertNotEqual(state['vision']['template'],state['reality']['template'])
        self.assertEqual({r:self.m.tree(self.web/('cover-'+r)) for r in base},before)
        self.m.publish(later,self.web,self.state,['vision'])
        extra=self.web/'cover-vision/independent';extra.write_text('preserve')
        with self.assertRaises(ValueError):self.m.rollback_vision(later,self.web,self.state)
        self.assertEqual(extra.read_text(),'preserve');extra.unlink()
        self.m.rollback_vision(later,self.web,self.state)
        self.assertEqual(self.m.read_state(self.state),base);self.assertFalse((self.web/'cover-vision').exists())
        for role in base:
            files=self.m.tree(self.web/('cover-'+role))
            self.assertFalse(any(name.endswith(('.py','.json')) for name in files))
            self.assertEqual(files,before[role])

    def test_public_root_is_searchable_with_private_caller_umask(self):
        stage=self.prepare('private-umask',['panel','reality'])
        previous=os.umask(0o077)
        try:self.m.publish(stage,self.web,self.state,['panel','reality'])
        finally:os.umask(previous)
        self.assertEqual(self.web.stat().st_mode&0o777,0o755)
        self.assertEqual(self.state.stat().st_mode&0o777,0o600)
        for role in ('panel','reality'):
            site=self.web/('cover-'+role)
            self.assertEqual(site.stat().st_mode&0o777,0o755)
            self.assertEqual((site/'index.html').stat().st_mode&0o777,0o644)

    def test_foreign_paths_symlinks_and_failed_publication_preserve_data(self):
        stage=self.prepare('base',['panel','reality'])
        self.web.mkdir();outside=self.root/'foreign';outside.mkdir();(outside/'important').write_text('keep')
        (self.web/'cover-panel').symlink_to(outside,target_is_directory=True)
        with self.assertRaises(ValueError):self.m.publish(stage,self.web,self.state,['panel','reality'])
        (self.web/'cover-panel').unlink();(self.web/'cover-panel').mkdir();(self.web/'cover-panel/foreign').write_text('keep')
        with self.assertRaises(ValueError):self.m.check_paths(self.web,self.state)
        self.assertEqual((self.web/'cover-panel/foreign').read_text(),'keep')
        shutil.rmtree(self.web/'cover-panel')
        with patch.object(self.m,'write_state',side_effect=OSError('injected state failure')):
            with self.assertRaises(OSError):self.m.publish(stage,self.web,self.state,['panel','reality'])
        self.assertFalse((self.web/'cover-panel').exists());self.assertFalse((self.web/'cover-reality').exists())
        self.assertEqual((outside/'important').read_text(),'keep')
        generator=self.m.module('generate');checker=self.m.module('check')
        with patch.object(generator,'generate',side_effect=OSError('injected generator failure')), patch.object(self.m,'module',side_effect=[generator,checker]):
            with self.assertRaises(OSError):self.prepare('failed',['panel','reality'])
        self.assertFalse(self.state.exists())

    def test_new_sites_backup_restore_preserves_bytes_and_selection(self):
        from test_personal_backup import PersonalBackup, relocated
        for vision,legacy_redirect in ((False,False),(True,False),(True,True)):
            with self.subTest(vision=vision,legacy_redirect=legacy_redirect):
                fixture=PersonalBackup('runTest');fixture.setUp()
                try:
                    if vision:fixture.seed_vision()
                    stage=self.root/('stage-'+str(vision)+'-'+str(legacy_redirect));web=fixture.path('/var/www/html');state=fixture.path('/etc/x-ui/cover-sites.json')
                    roles=['panel','reality']+(['vision'] if vision else [])
                    self.m.prepare(stage,state,roles);self.m.publish(stage,web,state,roles)
                    if vision:
                        from test_integrated_features import helper as feature
                        site=feature('vision').fallback_config('vision.example.com',12001,root='/var/www/html/cover-vision')
                        if legacy_redirect:site=site.replace('    absolute_redirect off;\n','')
                        fixture.write('/etc/nginx/sites-available/vision.conf',relocated(site,fixture.root))
                    before={r:self.m.tree(web/('cover-'+r)) for r in roles};selection=state.read_bytes()
                    archive=fixture.backup();original=archive.read_bytes()
                    for r in roles:shutil.rmtree(web/('cover-'+r))
                    state.unlink()
                    result=fixture.run_tool('restore',str(archive))
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertTrue(state.read_bytes()==selection,'Selection changed on Restore')
                    self.assertEqual({r:self.m.tree(web/('cover-'+r)) for r in roles},before)
                    self.assertTrue(archive.read_bytes()==original,'Source archive changed')
                finally:fixture.doCleanups()
