"""Conservative Git-derived docs exception and stdlib-only documentation smoke test."""
import argparse
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

READMES = {'README.md', 'README_EN.md', 'README_RU.md', 'README_AR.md',
           'README_FA.md', 'README_ES.md', 'README_TR.md', 'README_ZH_CN.md'}
INSTRUCTIONS = {'AGENTS.md', 'CLAUDE.md', 'CONTRIBUTING.md'}


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE, timeout=30)


def changed_paths(data):
    fields = data.split(b'\0')
    if fields[-1] != b'' or (len(fields)-1) % 2:
        raise ValueError('Ambiguous diff records')
    result = []
    for status, raw in zip(fields[:-1:2], fields[1:-1:2]):
        path = raw.decode('utf-8')
        if status not in (b'A', b'M', b'D') or not path or path in {p for _, p in result}:
            raise ValueError('Unsupported diff status')
        if str(PurePosixPath(path)) != path or '..' in PurePosixPath(path).parts or path.startswith('/'):
            raise ValueError('Noncanonical path')
        if '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
            raise ValueError('Noncanonical path')
        result.append((status.decode(), path))
    if not result:
        raise ValueError('Empty diff')
    return result


def allowed(path):
    p = PurePosixPath(path)
    return (path in READMES or path in INSTRUCTIONS or (p.parts[0] == 'docs' and p.suffix == '.md')
            or (p.parts[:2] == ('assets', 'support') and p.suffix == '.png'))


def blob(ref, path):
    return git('show', ref+':'+path)


def classify(event, payload, sha):
    if event not in ('pull_request', 'push'):
        return None, None, [], 'Manual or unknown event'
    try:
        base, head = ((payload['pull_request']['base']['sha'], payload['pull_request']['head']['sha'])
                      if event == 'pull_request' else (payload['before'], sha))
        for ref in (base, head):
            if not re.fullmatch('[0-9a-f]{40}', ref) or ref == '0'*40:
                raise ValueError('Invalid revision')
            git('cat-file', '-e', ref+'^{commit}')
        if git('rev-parse', '--is-shallow-repository').strip() != b'false':
            raise ValueError('Incomplete history')
        if git('rev-parse', 'HEAD').decode().strip() != head:
            raise ValueError('Checkout does not match event head')
        if event == 'pull_request':
            base = git('merge-base', base, head).decode().strip()
        else:
            git('merge-base', '--is-ancestor', base, head)
        changes = changed_paths(git('diff', '--name-status', '-z', '-M', '-C', '--find-copies-harder', base, head, '--'))
        for status, path in changes:
            if not allowed(path):
                raise ValueError('Change outside documentation allowlist')
            for ref in ([base] if status == 'D' else [head] if status == 'A' else [base, head]):
                entry = git('ls-tree', ref, '--', path).split(b'\t')[0].split()
                if len(entry) != 3 or entry[:2] != [b'100644', b'blob']:
                    raise ValueError('Unknown or nonregular file type')
        return base, head, changes, 'Allowlisted regular documentation files'
    except (KeyError, TypeError, ValueError, UnicodeError, subprocess.SubprocessError, OSError):
        return None, None, [], 'Uncertain or non-documentation scope; full CI required'


def validate_png(data):
    if len(data) > 16*1024*1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG signature/size')


def references(text):
    # Ignore examples in code; inspect file destinations, not Markdown rendering.
    text = re.sub(r'(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text)
    text = re.sub(r'`[^`\n]*`', '', text)
    targets = re.findall(r'!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)', text)
    targets += re.findall(r'(?m)^\s*\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)', text)
    targets += re.findall(r'(?i)\b(?:src|href)\s*=\s*[\"\']([^\"\']+)[\"\']', text)
    return set(html.unescape(t.strip('<>')) for t in targets)


def local_path(root, document, target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path: return None
    path = unquote(parsed.path)
    candidate = root/path.lstrip('/') if path.startswith('/') else root/Path(document).parent/path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root): raise ValueError('Local reference leaves working tree')
    return resolved


def smoke(base, head, changes):
    root = Path(git('rev-parse', '--show-toplevel').decode().strip()).resolve()
    changed = {(root/path).resolve() for _, path in changes}
    for status, path in changes:
        print('Verified path: '+json.dumps(path, ensure_ascii=True)+' ('+status+')')
        if status == 'D': continue
        data = blob(head, path)
        if path.endswith('.png'):
            validate_png(data)
        else:
            text = data.decode('utf-8')
            previous = references(blob(base, path).decode('utf-8', errors='replace')) if status == 'M' else set()
            for target in references(text):
                destination = local_path(root, path, target)
                if destination is None: continue
                if destination.exists(): continue
                # Do not block unrelated edits on pre-existing broken references.
                if target in previous and destination not in changed: continue
                raise ValueError('Missing local reference in '+path)
    git('diff', '--check', base, head, '--')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', action='store_true')
    args = parser.parse_args()
    if args.summary:
        docs = os.environ.get('CI_DOCS_ONLY') == 'true'
        status = os.environ.get('CI_JOB_STATUS', 'unknown')
        status = status if status in ('success', 'failure', 'cancelled') else 'unknown'
        message = ('DOCS-ONLY: Full Fresh E2E not executed; documentation scope verified.'
                   if docs and os.environ.get('CI_FRESH') == 'true' else
                   'DOCS-ONLY: UTF-8, PNG signature/size, local references and diff whitespace checked.'
                   if docs else 'FULL CI mode; job result: '+status+'.')
        if os.environ.get('CI_DOCS_ONLY') not in ('true','false'):
            message = 'Scope/smoke incomplete: documentation exception NOT verified; job result: '+status+'.'
        print(message)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out: out.write('\n'+message+'\n')
        return 0
    try:
        payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    except (OSError, KeyError, ValueError): payload = {}
    base, head, changes, reason = classify(os.environ.get('GITHUB_EVENT_NAME'), payload, os.environ.get('GITHUB_SHA'))
    docs = head is not None
    print('CI MODE: '+('docs-only' if docs else 'full'))
    print(reason)
    if docs:
        try: smoke(base, head, changes)
        except (ValueError, OSError, subprocess.SubprocessError):
            print('DOCS SMOKE: FAIL — invalid text, image, local reference or diff whitespace', file=sys.stderr)
            return 1
        print('DOCS SMOKE: PASS')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out: out.write('docs_only='+str(docs).lower()+'\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('## CI scope\n\nMode: **'+('docs-only' if docs else 'full')+'**\n\n'+reason+'\n')
            for status, path in changes: out.write('\n- '+status+' <code>'+html.escape(path)+'</code>')
            if docs: out.write('\n\nDocumentation smoke: PASS. Heavy tests are not executed.\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
