#!/usr/bin/env python3
"""One-time cover generation/publication. No network, service or database changes."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
ROLES = ('panel', 'reality', 'vision')

def module(name):
    spec = importlib.util.spec_from_file_location('cover_'+name, ROOT/'tools'/f'{name}.py')
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def parents(path):
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError('Unsafe cover directory: '+str(parent))


def read_state(path):
    parents(path.parent)
    if not os.path.lexists(path): return {}
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
        raise ValueError('Unsafe cover selection file')
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data)-set(ROLES): raise ValueError('Unknown cover selections')
    generator = module('generate')
    for role, item in data.items():
        allowed = ('A1','A2','A3') if role == 'panel' else ('B1','B2','B3')
        if not isinstance(item, dict) or set(item) != {'template','variants'} or item['template'] not in allowed:
            raise ValueError('Invalid cover selection')
        generator.selection(item['template'], ':'.join(map(str,item['variants'])))
    if data.get('reality',{}).get('template') == data.get('vision',{}).get('template') and 'vision' in data and 'reality' in data:
        raise ValueError('REALITY and Vision cover templates must differ')
    return data


def write_state(path, data):
    parents(path.parent); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.cover-sites-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            os.fchmod(out.fileno(), 0o600); os.fchown(out.fileno(), 0, 0)
            json.dump(data, out); out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def prepare(stage, state, roles):
    """Generate only missing roles; an existing selection is never re-rendered."""
    data = read_state(state)
    generator, checker = module('generate'), module('check')
    for code in ('A1','A2','A3','B1','B2','B3'):
        origin = ROOT/'templates'/code
        for name in ('index.html','404.html','static/site.css','favicon.svg'):
            if not (origin/name).is_file(): raise ValueError('Missing cover source: '+code+'/'+name)
    parents(stage.parent); stage.mkdir(mode=0o700)
    selections = dict(data)
    for role in roles:
        if role in data: continue
        candidates = ['A1','A2','A3'] if role == 'panel' else ['B1','B2','B3']
        other = 'reality' if role == 'vision' else 'vision'
        candidates = [c for c in candidates if c != selections.get(other,{}).get('template')]
        code = secrets.choice(candidates); indexes = generator.selection(code, None)
        selections[role] = dict(template=code, variants=indexes)
        site = stage/('cover-'+role)
        generator.generate(code, site, indexes)
        problems, _, _ = checker.check_site(site)
        if problems: raise ValueError('Invalid generated cover: '+str(problems))
        # Only generated public content leaves this private stage.
        for path in (site, *site.rglob('*')):
            if path.is_symlink() or not (path.is_dir() or path.is_file()): raise ValueError('Unsafe generated cover')
        for name in ('index.html','404.html','static/site.css','static/hero.svg','favicon.ico'):
            if not (site/name).is_file(): raise ValueError('Missing cover resource: '+name)
    write_state(stage/'selection.json', selections)


def tree(path):
    if path.is_symlink() or not path.is_dir(): raise ValueError('Unsafe cover root')
    result = {}
    for item in path.rglob('*'):
        if item.is_symlink() or not (item.is_dir() or item.is_file()): raise ValueError('Unsafe cover content')
        if item.is_file(): result[str(item.relative_to(path))] = item.read_bytes()
    return result


def check_paths(web, state):
    data = read_state(state); parents(web)
    for role in ROLES:
        path = web/('cover-'+role)
        if role in data: tree(path)
        elif os.path.lexists(path): raise ValueError('Foreign cover path; preserved: '+str(path))


def publish(stage, web, state, roles):
    before = read_state(state); selected = read_state(stage/'selection.json')
    parents(web)
    for role in roles:
        destination = web/('cover-'+role)
        if role in before:
            if before[role] != selected.get(role): raise ValueError('Cover selection changed independently')
            tree(destination)
        elif os.path.lexists(destination): raise ValueError('Foreign cover path; preserved: '+str(destination))
        else: tree(stage/('cover-'+role))
    # A private caller umask must not make the public document-root parent 0700.
    web.mkdir(mode=0o755, exist_ok=True); web.chmod(0o755)
    created = []
    try:
        for role in roles:
            if role in before: continue
            destination = web/('cover-'+role)
            created.append(destination)
            shutil.copytree(stage/('cover-'+role), destination)
            for path in (destination, *destination.rglob('*')):
                os.chown(path, 0, 0); path.chmod(0o755 if path.is_dir() else 0o644)
        after = dict(before); after.update({r:selected[r] for r in roles})
        write_state(state, after)
    except Exception:
        for path in created: shutil.rmtree(path)
        raise


def rollback_vision(stage, web, state):
    data = read_state(state); selected = read_state(stage/'selection.json')
    if 'vision' not in data: return
    path = web/'cover-vision'
    if data['vision'] != selected.get('vision') or tree(path) != tree(stage/'cover-vision'):
        raise ValueError('Vision cover changed independently; retained')
    shutil.rmtree(path); del data['vision']; write_state(state, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare','publish','rollback-vision','check'))
    parser.add_argument('stage', type=Path)
    parser.add_argument('--web', type=Path, default=Path('/var/www/html'))
    parser.add_argument('--state', type=Path, default=Path('/etc/x-ui/cover-sites.json'))
    parser.add_argument('--roles', nargs='+', choices=ROLES, default=['panel','reality'])
    args = parser.parse_args()
    if os.geteuid() != 0: raise ValueError('Cover publication requires root')
    if args.action == 'check': check_paths(args.web, args.state)
    elif args.action == 'prepare': prepare(args.stage, args.state, args.roles)
    elif args.action == 'publish': publish(args.stage, args.web, args.state, args.roles)
    else: rollback_vision(args.stage, args.web, args.state)

if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Cover sites: '+str(error), file=sys.stderr); sys.exit(1)
