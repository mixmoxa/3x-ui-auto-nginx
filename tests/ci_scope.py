"""Conservative Git-derived docs exception and stdlib-only documentation smoke test."""
import argparse
import binascii
import html
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import zlib

READMES = {'README.md', 'README_EN.md', 'README_RU.md', 'README_AR.md',
           'README_FA.md', 'README_ES.md', 'README_TR.md', 'README_ZH_CN.md'}


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
    return (path in READMES or (p.parts[0] == 'docs' and p.suffix == '.md')
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
    offset, chunks, compressed = 8, [], bytearray()
    while offset < len(data):
        if offset+12 > len(data): raise ValueError('Truncated PNG')
        size = struct.unpack('!I', data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]; end = offset+12+size
        if end > len(data): raise ValueError('Truncated PNG chunk')
        payload = data[offset+8:end-4]
        if binascii.crc32(kind+payload) != struct.unpack('!I', data[end-4:end])[0]:
            raise ValueError('PNG CRC mismatch')
        chunks.append((kind, payload))
        if kind == b'IDAT': compressed.extend(payload)
        offset = end
    if not chunks or chunks[0][0] != b'IHDR' or len(chunks[0][1]) != 13:
        raise ValueError('Missing PNG header')
    if chunks[-1] != (b'IEND', b'') or sum(k == b'IHDR' for k, _ in chunks) != 1 or sum(k == b'IEND' for k, _ in chunks) != 1:
        raise ValueError('Invalid PNG boundaries')
    kinds = [kind for kind, _ in chunks]
    if b'IDAT' not in kinds or any(not re.fullmatch(b'[A-Za-z]{4}', k) or k[2:3].islower() or (k[:1].isupper() and k not in (b'IHDR',b'PLTE',b'IDAT',b'IEND')) for k in kinds):
        raise ValueError('Invalid PNG chunk type')
    first, last = kinds.index(b'IDAT'), len(kinds)-1-kinds[::-1].index(b'IDAT')
    if any(k != b'IDAT' for k in kinds[first:last+1]) or kinds.count(b'PLTE') > 1:
        raise ValueError('Invalid PNG chunk order')
    if b'PLTE' in kinds and kinds.index(b'PLTE') > first: raise ValueError('Invalid PNG palette order')
    w, h, depth, color, compression, filtering, interlace = struct.unpack('!IIBBBBB', chunks[0][1])
    channels = {0:1, 2:3, 3:1, 4:2, 6:4}
    depths = {0:(1,2,4,8,16), 2:(8,16), 3:(1,2,4,8), 4:(8,16), 6:(8,16)}
    if not w or not h or color not in channels or depth not in depths[color] or compression or filtering or interlace not in (0,1):
        raise ValueError('Invalid PNG header values')
    if color == 3 and not any(k == b'PLTE' and len(v) % 3 == 0 and 0 < len(v) <= 768 for k, v in chunks):
        raise ValueError('Missing PNG palette')
    # Bound decompression; verify every scanline including Adam7 passes.
    passes = ((0,0,1,1),) if interlace == 0 else ((0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2))
    rows = []
    for x, y, dx, dy in passes:
        pw, ph = max(0,(w-x+dx-1)//dx), max(0,(h-y+dy-1)//dy)
        if pw and ph:
            row = (pw*channels[color]*depth+7)//8+1
            if row*ph+sum(a*b for a,b in rows) > 64*1024*1024: raise ValueError('PNG pixels too large')
            rows.append((row, ph))
    expected = sum(a*b for a,b in rows)
    decoder = zlib.decompressobj()
    pixels = decoder.decompress(compressed, expected+1)
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or len(pixels) != expected:
        raise ValueError('Invalid PNG pixel stream')
    offset = 0
    for row, count in rows:
        for _ in range(count):
            if pixels[offset] > 4: raise ValueError('Invalid PNG filter')
            offset += row


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
                   'DOCS-ONLY: UTF-8, PNG integrity, local references and diff whitespace checked.'
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
        except (ValueError, OSError, subprocess.SubprocessError, zlib.error, struct.error):
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
