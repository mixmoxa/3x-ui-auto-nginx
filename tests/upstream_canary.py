"""Read-only upstream probe and reuse of the canonical real integration suite."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import urllib.request

from release_contract import ROOT, candidate, stable_version, verify


def fetch_json(url):
    headers = {'Accept':'application/vnd.github+json', 'User-Agent':'3x-ui-auto-nginx-canary'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer '+os.environ['GH_TOKEN']
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
                return json.loads(response.read(8*1024*1024))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)


def fingerprint():
    paths = sorted((ROOT/'tests').glob('*.py')) + [
        ROOT/'x-ui-latest.sh', ROOT/'assets/clash/clash.yaml', ROOT/'assets/amneziawg/managed.py',
        ROOT/'assets/vision/managed.py', ROOT/'assets/client/managed.py',
        ROOT/'assets/diagnostics/mtr-backend.py', ROOT/'.github/workflows/upstream-canary.yml']
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes())
    return digest.hexdigest()


def probe(directory, version=None):
    for name in ('candidate.json','result.json','versions.json'):
        (directory/name).unlink(missing_ok=True)
    if version:
        stable_version(version)
    release = fetch_json('https://api.github.com/repos/MHSanaei/3x-ui/releases/'+
                         ('tags/'+version if version else 'latest'))
    selected = candidate(release, version)
    selected['implementation'] = fingerprint()
    (directory/'candidate.json').write_text(json.dumps(selected, indent=2)+'\n')
    key = 'upstream-amd64-'+selected['version']+'-'+selected['sha256']+'-'+selected['implementation']
    with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as output:
        output.write('key='+key+'\n')
    print('Upstream candidate:', selected['version'], '\nSHA-256:', selected['sha256'], flush=True)
    return selected


def run(directory):
    selected = json.loads((directory/'candidate.json').read_text())
    stable_version(selected['version'])
    for name in ('result.json','versions.json','integration.log'):
        (directory/name).unlink(missing_ok=True)
    result = {**selected, 'status':'FAIL', 'tested_at_utc':time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
              'tested_run':os.environ.get('GITHUB_RUN_ID','local'), 'integration_started':False,
              'coverage':'amd64 local integration; NOT full installer acceptance'}
    try:
        from test_real_integration import download
        base = 'https://github.com/MHSanaei/3x-ui/releases/download/'+selected['version']+'/x-ui-linux-amd64.tar.gz'
        archive, sidecar = directory/'x-ui.tar.gz', directory/'x-ui.sha256'
        download(base, archive)
        download(base+'.sha256', sidecar)
        verify(archive, sidecar, selected['sha256'])
        env = {k:v for k,v in os.environ.items() if k not in ('GH_TOKEN','GITHUB_TOKEN','INTEGRATION_ARTIFACTS')}
        env.update(UPSTREAM_CANDIDATE=str(directory/'candidate.json'), UPSTREAM_REPORT=str(directory/'versions.json'))
        with (directory/'integration.log').open('w') as log:
            process = subprocess.Popen([sys.executable, str(ROOT/'tests/run_ci.py'),'--suite','integration'],
                                       env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            deadline = threading.Timer(20*60, process.kill)
            deadline.daemon = True
            deadline.start()
            try:
                # Per-operation deadlines plus a hard enclosing suite deadline.
                for line in process.stdout:
                    print(line, end='', flush=True)
                    log.write(line)
                code = process.wait(timeout=10)
            finally:
                deadline.cancel()
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=10)
                process.stdout.close()
        if (directory/'versions.json').exists():
            versions = json.loads((directory/'versions.json').read_text())
            if versions.get('preparation_complete') is not True or versions.get('3x-ui') != selected['version'][1:]:
                raise ValueError('Invalid integration preparation report')
            result['integration_started'] = True
            result.update({key:versions[key] for key in ('3x-ui','bundled_xray')})
        if code:
            lines = (directory/'integration.log').read_text().splitlines()
            raise RuntimeError('Integration failed (exit '+str(code)+'): '+ '\n'.join(lines[-20:]))
        if not result['integration_started']:
            raise ValueError('Integration preparation did not complete')
        result['status'] = 'PASS'
        result['reason'] = 'CLI/SQLite, five transports, real RAW/JSON and Mihomo consumers passed'
    except Exception as error:
        result['reason'] = str(error)
    (directory/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as output:
        output.write('tested='+str(result['integration_started']).lower()+'\n')
    return 0 if result['status'] == 'PASS' else 1


def report(directory):
    path = directory/'result.json'
    selected = json.loads((directory/'candidate.json').read_text()) if (directory/'candidate.json').exists() else {}
    result = json.loads(path.read_text()) if path.exists() else {**selected, 'status':'FAIL','reason':'Candidate/dependency preparation failed; see job log'}
    # A cached report must belong to this exact artifact and test implementation.
    if (directory/'candidate.json').exists():
        for key in ('version','sha256','implementation'):
            if result.get(key) != selected[key]:
                result = {**selected, 'status':'FAIL', 'reason':'Cached result does not match candidate/test implementation'}
                break
    text = '\n'.join(f'{key}: {value}' for key,value in result.items())
    print(text, flush=True)
    with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a') as summary:
        summary.write('## Upstream Canary\n\n```text\n'+text.replace('```','')+'\n```\n')
        summary.write('\nCanary never changes the production baseline. Promotion requires a separate PR and installer acceptance.\n')
    return 0 if result['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('probe','run','report'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--version')
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    if args.command == 'probe':
        try:
            probe(args.directory, args.version)
            return 0
        except Exception as error:
            result = {'version':args.version or 'undetermined', 'sha256':'undetermined',
                      'status':'FAIL', 'reason':'Candidate probe: '+str(error)}
            (args.directory/'result.json').write_text(json.dumps(result, indent=2)+'\n')
            print(result['reason'], file=sys.stderr)
            return 1
    return run(args.directory) if args.command == 'run' else report(args.directory)


if __name__ == '__main__':
    sys.exit(main())
