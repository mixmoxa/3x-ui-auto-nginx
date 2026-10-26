"""Prepare a reproducible installer asset locally; never create tags or releases."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys


DEVELOPMENT_REF = b'PROJECT_REF="${XUI_AUTO_REF:-main}"'


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE)


def prepare(tag, commit, output):
    if not re.fullmatch(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', tag):
        raise ValueError('Expected a stable vMAJOR.MINOR.PATCH tag')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected an exact lowercase 40-hex commit SHA')
    if git('rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}').decode().strip() != commit:
        raise ValueError('Release tag does not match the selected commit')
    source = git('show', f'{commit}:x-ui-latest.sh')
    if source.splitlines().count(DEVELOPMENT_REF) != 1:
        raise ValueError('Unexpected installer source-ref contract')
    if source.count(b'https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/') != 1:
        raise ValueError('Expected one shared project-owned asset source')
    pinned = f'PROJECT_REF="${{XUI_AUTO_REF:-{commit}}}"'.encode()
    asset = source.replace(DEVELOPMENT_REF, pinned, 1)
    subprocess.run(['bash', '-n'], input=asset, check=True, capture_output=True)
    # Check the actual source initialization without running the installer.
    init = re.search(rb'^PROJECT_REF=.*?^configure_project_source \|\| return 1 2>/dev/null \|\| exit 1$', asset, re.M | re.S)
    if init is None:
        raise ValueError('Installer source initialization is missing')
    for override, expected in (('', commit), ('v1.2.3', 'v1.2.3')):
        result = subprocess.run(['bash', '-eu', '-c', init[0].decode()+'\nprintf "%s" "$GITHUB_RAW"'],
            env={**os.environ, 'XUI_AUTO_REF': override}, capture_output=True, check=True)
        if result.stdout != f'https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/{expected}'.encode():
            raise ValueError('Release asset source-ref validation failed')
    output = Path(output)
    output.mkdir(mode=0o700)  # A new directory: never overwrite the working source or old assets.
    try:
        target = output/'x-ui-latest.sh'
        target.write_bytes(asset)
        digest = hashlib.sha256(asset).hexdigest()
        (output/'x-ui-latest.sh.sha256').write_text(f'{digest}  x-ui-latest.sh\n')
    except Exception:
        for name in ('x-ui-latest.sh', 'x-ui-latest.sh.sha256'):
            (output/name).unlink(missing_ok=True)
        output.rmdir()
        raise
    print(f'Release: {tag}\nSource: {commit}\nSHA-256: {digest}\nAsset: {target}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tag')
    parser.add_argument('commit')
    parser.add_argument('output', help='new output directory outside the source file')
    args = parser.parse_args()
    try:
        prepare(args.tag, args.commit, args.output)
    except (ValueError, OSError, subprocess.SubprocessError):
        print('Release preparation failed: check tag/SHA, source contract, Bash syntax and output path.', file=sys.stderr)
        sys.exit(1)
