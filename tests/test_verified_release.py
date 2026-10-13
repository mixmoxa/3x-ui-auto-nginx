"""Release selection, pre-mutation preflight and Canary controller contracts."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    match = re.search(r'^'+re.escape(name)+r'\(\)\s*\{.*?^\}', source, re.M | re.S)
    if not match:
        raise ValueError('Missing function '+name)
    return match.group()


class VerifiedRelease(unittest.TestCase):
    def test_default_does_not_follow_hypothetical_new_upstream(self):
        source = (ROOT/'x-ui-latest.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'local').mkdir()
            archive = root/'fixture.tar.gz'
            with tarfile.open(archive, 'w:gz') as bundle:
                for name in ('x-ui','x-ui.sh','x-ui.service.debian','bin/xray-linux-amd64'):
                    entry = tarfile.TarInfo('x-ui/'+name)
                    entry.mode = 0o755
                    payload = b'#!/bin/sh\nexit 0\n'
                    entry.size = len(payload)
                    bundle.addfile(entry, io.BytesIO(payload))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            metadata = {'version':'v3.9.0','xray':'26.9.30','archives':{'amd64':digest},
                        'integration_architectures':['amd64']}
            mock = r'''
msg_err() { echo "$*" >&2; }
msg_warn() { :; }
msg_ok() { :; }
_arch() { echo amd64; }
bootstrap_panel_dependencies() { :; }
verified_panel_release() { printf '%s' "$MANIFEST"; }
apt-get() { :; }
curl() { echo '{"tag_name": "v9.9.9"}'; }
_download_panel_archive() { printf '%s\n' "$1" >> "$LOG"; cp "$FIXTURE" "$2"; }
systemctl() { :; }
install() { :; }
_panel_initial_config() { :; }
cp() { command cp "$@"; }
'''
            if 'preflight_panel_release()' in source:
                names = ('_validate_panel_version','_validate_panel_archive','release_panel_preflight','preflight_panel_release')
                script = mock+'\n'+'\n'.join(function(source,n) for n in names)+'\npreflight_panel_release'
            else:
                script = mock+'\n'+function(source,'_validate_panel_version')+'\n'+function(source,'install_panel').replace('/usr/local',str(root/'local')).replace('/etc/systemd/system/x-ui.service',str(root/'service'))+'\ninstall_panel'
            result = subprocess.run(['bash','-u','-c',script],capture_output=True,text=True,
                                    env={**os.environ,'MANIFEST':json.dumps(metadata),'PANEL_VERSION':'',
                                         'FIXTURE':str(archive),'LOG':str(root/'calls')})
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('/v3.9.0/x-ui-linux-amd64.tar.gz',(root/'calls').read_text())
            self.assertNotIn('v9.9.9',(root/'calls').read_text())

    def test_arm32_install_final_name_and_missing_binary_fail_closed(self):
        source=(ROOT/'x-ui-latest.sh').read_text()
        for arch in ('armv5','armv6','armv7'):
            for present in (True,False):
                with self.subTest(arch=arch,present=present), tempfile.TemporaryDirectory() as directory:
                    root=Path(directory); local=root/'local'; local.mkdir(); stage=root/'stage'; (stage/'x-ui/bin').mkdir(parents=True)
                    for name in ('x-ui','x-ui.sh'): (stage/'x-ui'/name).write_text('#!/bin/bash\nexit 0\n')
                    (stage/'x-ui/x-ui.service.debian').write_text('[Service]\nExecStart=/fixture\n[Install]\n')
                    if present: (stage/'x-ui/bin'/('xray-linux-'+arch)).write_text('#!/bin/bash\necho fixture\n')
                    archive=root/'archive.tar.gz'
                    with tarfile.open(archive,'w:gz') as bundle: bundle.add(stage/'x-ui',arcname='x-ui')
                    body=function(source,'install_panel').replace('/usr/local',str(local)).replace('/etc/systemd/system/x-ui.service',str(root/'unit'))
                    script='msg_err() { echo "$*" >&2; }; msg_ok() { echo "$*"; }; _arch() { echo '+arch+'; }; systemctl() { :; }; install() { :; }; _panel_initial_config() { :; };\n'+body+'\ninstall_panel'
                    result=subprocess.run(['bash','-u','-c',script],env={**os.environ,'PANEL_TAG':'v3.10.0','PANEL_ARCHIVE':str(archive)},capture_output=True,text=True)
                    target=local/'x-ui/bin/xray-linux-arm32'
                    if present:
                        self.assertEqual(result.returncode,0,result.stderr); self.assertTrue(os.access(target,os.X_OK))
                    else:
                        self.assertNotEqual(result.returncode,0); self.assertNotIn('installed.',result.stdout)

    def test_installed_310_unit_keeps_upstream_sandbox_and_seccomp(self):
        source=(ROOT/'x-ui-latest.sh').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); local=root/'local'; local.mkdir(); stage=root/'stage'; (stage/'x-ui/bin').mkdir(parents=True)
            for name in ('x-ui','x-ui.sh','bin/xray-linux-amd64'): (stage/'x-ui'/name).write_text('#!/bin/bash\nexit 0\n')
            original='[Service]\nProtectSystem=full\nProtectHome=read-only\nNoNewPrivileges=yes\nReadWritePaths=-/etc/x-ui -/usr/local/x-ui -/var/log/x-ui\n[Install]\n'
            (stage/'x-ui/x-ui.service.debian').write_text(original)
            archive=root/'archive.tar.gz'
            with tarfile.open(archive,'w:gz') as bundle: bundle.add(stage/'x-ui',arcname='x-ui')
            body=function(source,'install_panel').replace('/usr/local',str(local)).replace('/etc/systemd/system/x-ui.service',str(root/'unit'))
            script='msg_ok() { :; }; _arch() { echo amd64; }; systemctl() { :; }; install() { :; }; _panel_initial_config() { :; };\n'+body+'\ninstall_panel'
            result=subprocess.run(['bash','-u','-c',script],env={**os.environ,'PANEL_TAG':'v3.10.0','PANEL_ARCHIVE':str(archive)},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            unit=(root/'unit').read_text()
            for directive in ('ProtectSystem=full','ProtectHome=read-only','NoNewPrivileges=yes','SystemCallFilter=@system-service','SystemCallErrorNumber=EPERM'):
                self.assertIn(directive,unit)
            self.assertIn('ReadWritePaths=-/etc/x-ui -/usr/local/x-ui -/var/log/x-ui',unit)
        # Only explicitly tested versions pass optional component preflights.
        for tag,allowed in (('v3.9.0',True),('v3.10.0',True),('v3.11.0',False)):
            for name in ('preflight_amneziawg','preflight_integrated_features'):
                stubs='msg_err() { :; }; awg_port_available() { :; }; curl() { :; }; python3() { :; }; preflight_vision_artifacts() { :; };\n'
                result=subprocess.run(['bash','-eu','-c',stubs+function(source,name)+'\n'+name],env={**os.environ,'PANEL_TAG':tag,'INSTALL_AWG':'y','CREATE_CLIENT':'y','INSTALL_SECURITY':'n','INSTALL_VISION':'n','PANEL_STAGE':'/fixture','GITHUB_RAW':'https://example.invalid'},capture_output=True,text=True)
                self.assertEqual(result.returncode==0,allowed,(name,tag,result.stderr))


    def test_preflight_failure_preserves_existing_managed_state(self):
        source = (ROOT/'x-ui-latest.sh').read_text()
        names = re.findall(r'^\s*([a-z_]+)(?:\s|$)',function(source,'main'),re.M)
        # Execute the actual lifecycle, injecting the same archive-integrity failure
        # at the old installation stage or the new release preflight stage.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root/'managed-state'
            target.write_bytes(b'previous healthy installation')
            mock = '\n'.join(f'{n}() {{ :; }}' for n in set(names) if n not in ('main','local','if','else','return','fi','exit'))
            mock += r'''
msg_err() { echo "$*" >&2; }
preflight_panel_release() { echo verification-failed >> "$LOG"; return 1; }
install_panel() { echo verification-failed >> "$LOG"; return 1; }
cleanup_adguard() { echo cleanup >> "$LOG"; rm -f "$TARGET"; }
clean_previous_install() { echo cleanup >> "$LOG"; rm -f "$TARGET"; }
'''
            result = subprocess.run(['bash','-u','-c',mock+'\n'+function(source,'main')+'\nmain'],
                                    capture_output=True,text=True,env={**os.environ,'TARGET':str(target),
                                    'LOG':str(root/'calls'),'INSTALL_AGH':'n'})
            self.assertNotEqual(result.returncode,0)
            self.assertIn('verification-failed',(root/'calls').read_text())
            self.assertNotIn('cleanup',(root/'calls').read_text())
            self.assertEqual(target.read_bytes(),b'previous healthy installation')


    def preflight(self, version='', failure='', consume=False):
        source = (ROOT/'x-ui-latest.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'local/x-ui').mkdir(parents=True)
            old = root/'local/x-ui/old-state'
            old.write_bytes(b'healthy')
            archive = root/'fixture.tar.gz'
            with tarfile.open(archive,'w:gz') as bundle:
                for name in ('x-ui','x-ui.sh','x-ui.service.debian','bin/xray-linux-amd64'):
                    entry = tarfile.TarInfo('x-ui/'+name)
                    entry.mode = 0o755
                    data = b'#!/bin/sh\nexit 0\n'
                    entry.size = len(data)
                    bundle.addfile(entry,io.BytesIO(data))
                if failure == 'unsafe-member':
                    entry = tarfile.TarInfo('../outside'); entry.size=1
                    bundle.addfile(entry,io.BytesIO(b'x'))
            if failure == 'invalid-archive':
                archive.write_bytes(b'not a tar archive')
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            manifest = {'version':'v3.9.0','xray':'26.9.30','archives':{'amd64':digest},'integration_architectures':['amd64']}
            if failure == 'pinned-mismatch':
                manifest['archives']['amd64'] = '0'*64
            selected = 'v'+version.removeprefix('v') if version else 'v3.9.0'
            release = {'tag_name':selected,'prerelease':failure=='prerelease','draft':failure=='draft',
                       'assets':[{'name':'x-ui-linux-amd64.tar.gz','digest':'sha256:'+digest},
                                 {'name':'x-ui-linux-amd64.tar.gz.sha256'}]}
            if failure == 'missing-asset': release['assets'].pop()
            if failure == 'unknown-digest': release['assets'][0].pop('digest')
            sidecar = root/'fixture.sha256'
            sidecar.write_text(digest+'  x-ui-linux-amd64.tar.gz\n')
            mock = r'''
msg_err() { echo "$*" >&2; }
msg_ok() { echo "$*"; }
msg_warn() { echo "$*"; }
_arch() { echo amd64; }
bootstrap_panel_dependencies() { [[ "$FAILURE" != dependencies ]]; }
verified_panel_release() { printf '%s' "$MANIFEST"; }
curl() {
    local url='' output='' previous='' argument
    for argument in "$@"; do
        [[ "$argument" != https://* ]] || url=$argument
        [[ "$previous" != -o ]] || output=$argument
        previous=$argument
    done
    echo "$url" >> "$LOG"
    [[ "$FAILURE" != download ]] || return 22
    case "$url" in
        https://api.github.com/*) [[ "$FAILURE" != nonexistent ]] || return 22; printf '%s' "$METADATA" > "$output" ;;
        *.sha256) cp "$SIDECAR" "$output" ;;
        *) cp "$ARCHIVE" "$output" ;;
    esac
}
systemctl() { :; }
install() { :; }
_panel_initial_config() { :; }
'''
            names = ('_validate_panel_version','release_panel_preflight','_validate_panel_archive','_download_panel_archive','preflight_panel_release')
            script = mock+'\n'+'\n'.join(function(source,n) for n in names)+'\npreflight_panel_release || exit 1\n'
            if consume:
                script += function(source,'install_panel').replace('/usr/local',str(root/'local')).replace('/etc/systemd/system/x-ui.service',str(root/'service'))+'\ninstall_panel || exit 1\n'
            result = subprocess.run(['bash','-u','-c',script],capture_output=True,text=True,
                                    env={**os.environ,'PANEL_VERSION':version,'MANIFEST':json.dumps(manifest),
                                         'METADATA':json.dumps(release),'FAILURE':failure,'LOG':str(root/'calls'),
                                         'ARCHIVE':str(archive),'SIDECAR':str(sidecar)})
            calls = (root/'calls').read_text().splitlines() if (root/'calls').exists() else []
            if failure or version in ('v3.7.9','v3.10.0-rc.1','bad','v03.9.0'):
                self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertEqual(old.read_bytes(),b'healthy')
            else:
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                if consume: self.assertTrue((root/'local/x-ui/x-ui.sh').exists())
            return result, calls

    def test_verified_archive_is_downloaded_once_and_reused(self):
        result,calls = self.preflight(consume=True)
        self.assertEqual(len(calls),2)
        self.assertTrue(all('/v3.9.0/' in url for url in calls))
        self.assertNotIn('not the verified baseline',result.stdout)

    def test_explicit_stable_selection_warns_and_rejects_unverifiable_releases(self):
        result,calls = self.preflight('v3.10.0')
        self.assertIn('not the verified baseline',result.stdout)
        self.assertEqual(len(calls),3)
        self.assertTrue(all('v3.10.0' in url for url in calls))
        for failure in ('nonexistent','prerelease','draft','missing-asset','unknown-digest'):
            with self.subTest(failure=failure): self.preflight('v3.10.0',failure)
        for version in ('v3.7.9','v3.10.0-rc.1','bad','v03.9.0'):
            with self.subTest(version=version):
                _,calls = self.preflight(version)
                self.assertEqual(calls,[])

    def test_corrupt_or_unsafe_archive_and_dependency_failure_preserve_target(self):
        for failure in ('download','pinned-mismatch','invalid-archive','unsafe-member','dependencies'):
            with self.subTest(failure=failure): self.preflight(failure=failure)

    def test_canary_selection_and_changed_implementation_cache_identity(self):
        from unittest.mock import patch
        import upstream_canary
        from release_contract import candidate, baseline
        release = {'tag_name':'v3.10.0','draft':False,'prerelease':False,'assets':[
            {'name':'x-ui-linux-amd64.tar.gz','digest':'sha256:'+'1'*64},
            {'name':'x-ui-linux-amd64.tar.gz.sha256'}]}
        original_baseline = baseline()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            output=root/'outputs'
            with redirect_stdout(io.StringIO()), patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}), patch.object(upstream_canary,'fetch_json',return_value=release), patch.object(upstream_canary,'fingerprint',return_value='first'):
                selected=upstream_canary.probe(root)
            self.assertEqual(selected['version'],'v3.10.0')
            self.assertEqual(selected['sha256'],'1'*64)
            self.assertEqual(baseline(),original_baseline)
            first=output.read_text()
            with redirect_stdout(io.StringIO()), patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}), patch.object(upstream_canary,'fetch_json',return_value=release), patch.object(upstream_canary,'fingerprint',return_value='second'):
                upstream_canary.probe(root)
            self.assertNotEqual(first.splitlines()[0],output.read_text().splitlines()[1])
            for field,value in (('tag_name','v3.10.0-rc.1'),('prerelease',True),('draft',True)):
                with self.subTest(field=field), self.assertRaises(ValueError): candidate({**release,field:value})

    def test_canary_cache_invalidates_changed_integrated_api_helpers(self):
        from unittest.mock import patch
        import upstream_canary
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('tests','assets'):
                shutil.copytree(ROOT/folder,root/folder)
            shutil.copy2(ROOT/'x-ui-latest.sh',root/'x-ui-latest.sh')
            (root/'.github/workflows').mkdir(parents=True)
            shutil.copy2(ROOT/'.github/workflows/upstream-canary.yml',root/'.github/workflows/upstream-canary.yml')
            with patch.object(upstream_canary,'ROOT',root):
                for feature in ('vision','client'):
                    previous = upstream_canary.fingerprint()
                    path = root/f'assets/{feature}/managed.py'
                    path.write_text(path.read_text()+'\n# changed API contract\n')
                    self.assertNotEqual(previous,upstream_canary.fingerprint(),feature)

    def test_canary_uses_own_archive_and_reports_compatibility_failure(self):
        from unittest.mock import patch
        import upstream_canary
        from release_contract import verify
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            payload=b'candidate archive, not baseline'
            digest=hashlib.sha256(payload).hexdigest()
            selected={'version':'v3.10.0','sha256':digest,'arch':'amd64','implementation':'test'}
            (root/'candidate.json').write_text(json.dumps(selected))
            downloads=[]
            def download(url,target):
                downloads.append(url)
                target.write_bytes((digest+'  x-ui-linux-amd64.tar.gz\n').encode() if url.endswith('.sha256') else payload)
            class Process:
                stdout=io.StringIO('FAIL: native setting persistence incompatible\nFAILED (failures=1)\n')
                def __init__(self,*args,**kwargs):
                    Path(kwargs['env']['UPSTREAM_REPORT']).write_text(json.dumps({
                        '3x-ui':'3.10.0','bundled_xray':'Xray candidate fixture','preparation_complete':True}))
                def wait(self,timeout): return 1
                def poll(self): return 1
                def kill(self): pass
            with redirect_stdout(io.StringIO()), patch('test_real_integration.download',side_effect=download), patch.object(upstream_canary.subprocess,'Popen',side_effect=Process) as process:
                self.assertEqual(upstream_canary.run(root),1)
            env=process.call_args.kwargs['env']
            self.assertEqual(env['UPSTREAM_CANDIDATE'],str(root/'candidate.json'))
            self.assertNotIn('INTEGRATION_ARTIFACTS',env)
            self.assertEqual(downloads,[f'https://github.com/MHSanaei/3x-ui/releases/download/v3.10.0/x-ui-linux-amd64.tar.gz'+suffix for suffix in ('','.sha256')])
            result=json.loads((root/'result.json').read_text())
            self.assertEqual(result['status'],'FAIL')
            self.assertTrue(result['integration_started'])
            self.assertIn('setting persistence incompatible',result['reason'])
            (root/'x-ui.tar.gz').write_bytes(b'corruption')
            with self.assertRaises(ValueError): verify(root/'x-ui.tar.gz',root/'x-ui.sha256',digest)

    def test_baseline_all_archives_are_pinned_but_coverage_is_explicit(self):
        from release_contract import baseline
        value=baseline()
        source=(ROOT/'x-ui-latest.sh').read_text()
        body=source[source.index('verified_panel_release()'):source.index('bootstrap_panel_dependencies()')]
        emitted=subprocess.check_output(['bash','-u','-c',body+'\nverified_panel_release'],text=True)
        self.assertEqual(json.loads(emitted),value)
        from release_contract import selection
        from unittest.mock import patch
        with patch.dict(os.environ,{},clear=True):
            selected = selection()
        self.assertEqual(selected['version'],value['version'])
        self.assertEqual(selected['xray'],value['xray'])
        self.assertEqual(selected['sha256'],value['archives']['amd64'])
        self.assertEqual(set(value['archives']),{'amd64','arm64','386','armv5','armv6','armv7','s390x'})
        self.assertEqual(value['integration_architectures'],['amd64'])
        for digest in value['archives'].values(): self.assertRegex(digest,r'^[0-9a-f]{64}$')

    def test_bootstrap_missing_binaries_and_apt_failure_fail_closed(self):
        source=(ROOT/'x-ui-latest.sh').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ca=root/'ca.crt';ca.write_text('fixture CA')
            body=function(source,'apt_system')+'\n'+function(source,'bootstrap_panel_dependencies').replace('/etc/ssl/certs/ca-certificates.crt',str(ca))
            mock=r'''
command() { [[ "$1" != -v ]] || return 1; builtin command "$@"; }
apt-get() { echo "$*" >> "$CALLS"; [[ "$FAIL_APT" != 1 ]]; }
msg_err() { echo "$*" >&2; }
'''
            for failure in ('0','1'):
                log=root/'calls';log.write_text('')
                result=subprocess.run(['bash','-u','-c',mock+body+'\nbootstrap_panel_dependencies'],
                                      env={**os.environ,'CALLS':str(log),'FAIL_APT':failure},capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('update',log.read_text())
                if failure=='0':
                    self.assertIn('curl ca-certificates python3 tar gzip',log.read_text())
                    self.assertIn('Release preflight requires curl',result.stderr)
                else:
                    self.assertNotIn('install',log.read_text())

    def test_baseline_promotion_changes_installer_and_integration_contracts(self):
        from unittest.mock import patch
        import release_contract
        source = (ROOT/'x-ui-latest.sh').read_text()
        value = release_contract.baseline()
        promoted = {**value, 'version':'v3.10.0', 'xray':'27.1.1',
                    'archives':{arch:'a'*64 for arch in value['archives']}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def write_manifest(manifest):
                text = re.sub(r"(?<=cat <<'VERIFIED_RELEASE_JSON'\n).*?(?=\nVERIFIED_RELEASE_JSON)",
                              json.dumps(manifest, indent=2), source, flags=re.S)
                (root/'x-ui-latest.sh').write_text(text)
            write_manifest(promoted)
            with patch.object(release_contract,'ROOT',root), patch.dict(os.environ,{},clear=True), patch.dict(globals(),ROOT=root):
                # The existing production-contract test must also accept promotion.
                self.test_baseline_all_archives_are_pinned_but_coverage_is_explicit()
                selected = release_contract.selection()
                self.assertEqual(selected['version'],promoted['version'])
                self.assertEqual(selected['xray'],promoted['xray'])
                self.assertEqual(selected['sha256'],promoted['archives']['amd64'])
                for broken in ({**promoted,'xray':''}, {**promoted,'archives':{}},
                               {**promoted,'archives':{'amd64':'corrupt'}},
                               {**promoted,'integration_architectures':['unknown']}):
                    with self.subTest(manifest=broken):
                        write_manifest(broken)
                        with self.assertRaises(ValueError): release_contract.baseline()

    def test_real_integration_rejects_nonproduction_archive_layout(self):
        from unittest.mock import patch
        import gzip
        import test_real_integration as integration
        original_run = subprocess.run
        def run(argv,**kwargs):
            return original_run(argv,**kwargs) if argv[0] == 'bash' else subprocess.CompletedProcess([],0,stderr='nginx fixture')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mihomo = gzip.compress(b'fixture executable')
            (root/'mihomo.gz').write_bytes(mihomo)
            for missing in (None,'x-ui.sh','x-ui.service.debian','unsafe'):
                with self.subTest(missing=missing):
                    archive = root/'x-ui.tar.gz'
                    with tarfile.open(archive,'w:gz') as bundle:
                        for name in ('x-ui','x-ui.sh','x-ui.service.debian','bin/xray-linux-amd64'):
                            if name == missing: continue
                            entry = tarfile.TarInfo('x-ui/'+name)
                            data = b'fixture executable'; entry.size = len(data)
                            bundle.addfile(entry,io.BytesIO(data))
                        if missing == 'unsafe':
                            entry = tarfile.TarInfo('../outside'); entry.size = 1
                            bundle.addfile(entry,io.BytesIO(b'x'))
                    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
                    (root/'x-ui.sha256').write_text(digest+'  x-ui-linux-amd64.tar.gz\n')
                    selected = {'version':'v3.10.0','sha256':digest,'xray':'27.1.1','candidate':False}
                    def version(argv,**kwargs):
                        return 'Xray 27.1.1 fixture\n' if 'version' in argv else ('3.10.0' if '-v' in argv and str(argv[0]).endswith('/x-ui') else 'Mihomo fixture')
                    with patch.dict(os.environ,{'INTEGRATION_ARTIFACTS':str(root),'NGINX_BIN':'/fixture/nginx'},clear=True), patch.object(integration,'selection',return_value=selected), patch.object(integration,'MIHOMO_SHA256',hashlib.sha256(mihomo).hexdigest()), patch.object(integration.subprocess,'check_output',side_effect=version) as execute, patch.object(integration.subprocess,'run',side_effect=run), patch.object(integration.RealIntegration,'_prepare_arm32') as arm_prepare:
                        try:
                            if missing:
                                with self.assertRaises((ValueError,subprocess.CalledProcessError)):
                                    integration.RealIntegration.setUpClass()
                                execute.assert_not_called()
                            else:
                                integration.RealIntegration.setUpClass()
                                self.assertGreater(execute.call_count,0)
                                arm_prepare.assert_called_once()
                                report=root/'readiness.json'
                                with patch.dict(os.environ,{'UPSTREAM_REPORT':str(report)}), patch.object(integration.RealIntegration,'_prepare_arm32',side_effect=ValueError('ARM preparation unavailable')):
                                    with self.assertRaisesRegex(ValueError,'ARM preparation unavailable'):
                                        integration.RealIntegration.setUpClass()
                                self.assertFalse(report.exists(),'Preparation failure must not publish a cacheable compatibility result')
                        finally:
                            integration.RealIntegration.doClassCleanups()

    def test_canary_mihomo_setup_failure_is_not_a_tested_compatibility_result(self):
        from unittest.mock import patch
        import upstream_canary
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = b'authenticated candidate; setup must fail before extraction'
            digest = hashlib.sha256(payload).hexdigest()
            selected = {'version':'v3.10.0','sha256':digest,'arch':'amd64','implementation':'test'}
            (root/'candidate.json').write_text(json.dumps(selected))
            def download(url,target):
                target.write_bytes((digest+'  x-ui-linux-amd64.tar.gz\n').encode() if url.endswith('.sha256') else payload)
            worker = root/'setup_failure.py'
            worker.write_text('''import sys, unittest
from unittest.mock import patch
import test_real_integration as integration
with patch.object(integration, 'download', side_effect=RuntimeError('Mihomo preparation unavailable')):
    suite = unittest.TestSuite([integration.RealIntegration('test_reality')])
    result = unittest.TextTestRunner().run(suite)
sys.exit(not result.wasSuccessful())
''')
            original = subprocess.Popen
            def child(argv,**kwargs):
                kwargs['env']['PYTHONPATH'] = str(ROOT/'tests')
                return original([argv[0],str(worker)],**kwargs)
            output = root/'outputs'
            with redirect_stdout(io.StringIO()), patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}), patch('test_real_integration.download',side_effect=download), patch.object(upstream_canary.subprocess,'Popen',side_effect=child):
                self.assertEqual(upstream_canary.run(root),1)
            result = json.loads((root/'result.json').read_text())
            self.assertIn('Mihomo preparation unavailable',result['reason'])
            self.assertFalse(result['integration_started'])
            self.assertEqual(output.read_text(),'tested=false\n')
            self.assertFalse((root/'versions.json').exists())

    def test_canary_preparation_failure_is_reported_but_not_cached_as_tested(self):
        from unittest.mock import patch
        import upstream_canary
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            selected={'version':'v3.10.0','sha256':'1'*64,'arch':'amd64','implementation':'test'}
            (root/'candidate.json').write_text(json.dumps(selected))
            output=root/'outputs'
            with patch.dict(os.environ,{'GITHUB_OUTPUT':str(output)}), patch('test_real_integration.download',side_effect=RuntimeError('download unavailable')):
                self.assertEqual(upstream_canary.run(root),1)
            result=json.loads((root/'result.json').read_text())
            self.assertFalse(result['integration_started'])
            self.assertEqual(result['version'],'v3.10.0')
            self.assertIn('download unavailable',result['reason'])
            self.assertEqual(output.read_text(),'tested=false\n')
            workflow=(ROOT/'.github/workflows/upstream-canary.yml').read_text()
            self.assertIn("steps.integration.outputs.tested == 'true'",workflow)


if __name__ == '__main__':
    unittest.main()
