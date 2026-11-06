#!/usr/bin/env python3
"""Render six independent static websites. Standard library only; no network access.

A site variant is the Cartesian product of a reviewed name, palette, artwork and
copy kit. All combinations are compatible and contain no factual business claims.
"""
import argparse
import html
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
DATA=json.loads((ROOT/'data/variants.json').read_text(encoding='utf-8'))
TOKENS=re.compile(r'\{\{([A-Z][A-Z_0-9]*)\}\}')

def selection(which, requested):
    obj=DATA[which]
    options=(len(obj['brands']),len(obj['palettes']),3,len(obj['copy']))
    if requested is None:
        return [secrets.randbelow(n) for n in options]
    try:
        values=[int(n) for n in requested.split(':')]
    except ValueError:
        raise ValueError(f'{which}: expected 4 integer indices separated by colons') from None
    if len(values)!=4 or any(not 0<=n<limit for n,limit in zip(values,options)):
        raise ValueError(f'{which}: index out of range; sizes are {options}')
    return values

def render_text(text, replacements, path):
    def replace(match):
        name=match.group(1)
        if name not in replacements:
            raise ValueError(f'Unknown substitution {name} in {path}')
        return replacements[name]
    result=TOKENS.sub(replace,text)
    if '{{' in result and path.endswith(('.html','.svg')):
        raise ValueError(f'Unexpected template syntax in {path}')
    return result

def generate(which, destination, options):
    brand_idx,palette_idx,art_idx,copy_idx=options
    item=DATA[which]
    brand=item['brands'][brand_idx]
    palette=item['palettes'][palette_idx]
    copy=item['copy'][copy_idx]
    values={'BRAND':html.escape(brand,quote=True),
            'ACCENT':palette['accent'], 'ACCENT2':palette['accent2'], 'SOFT':palette['soft']}
    values.update({key.upper():html.escape(value,quote=True) for key,value in copy.items()})
    origin=ROOT/'templates'/which
    destination.mkdir(parents=True,exist_ok=False)
    for src in origin.rglob('*'):
        if not src.is_file() or 'art' in src.relative_to(origin).parts or 'ico' in src.relative_to(origin).parts:
            continue
        relative=src.relative_to(origin)
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if src.suffix in ('.html','.css','.svg','.txt','.js'):
            target.write_text(render_text(src.read_text(encoding='utf-8'),values,str(relative)),encoding='utf-8')
        else:
            shutil.copyfile(src,target)
    shutil.copyfile(origin/'static'/'art'/f'hero-{art_idx+1}.svg',destination/'static'/'hero.svg')
    shutil.copyfile(origin/'static'/'ico'/f"{palette['id']}.ico",destination/'favicon.ico')
    return {'brand':brand,'palette':palette['id'],'artwork':art_idx+1,'copy_kit':copy_idx+1,
            'scope':'Static website files only; no authentication or external API'}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'build',help='Output parent directory (must not exist)')
    parser.add_argument('--sites',nargs='+',choices=('A1','A2','A3','B1','B2','B3'),
                        help='Optional site subset; defaults to all six (e.g. --sites A1 B2 B3)')
    for code in ('A1','A2','A3','B1','B2','B3'):
        parser.add_argument('--'+code.lower(),help='Brand:palette:artwork:copy zero-based indices, e.g. 0:0:0:0')
    args=parser.parse_args(argv)
    try:
        if args.out.exists(): raise ValueError(f'Output already exists: {args.out}; choose a new directory')
        wanted=args.sites or ('A1','A2','A3','B1','B2','B3')
        if len(set(wanted))!=len(wanted):raise ValueError('Duplicate site in --sites')
        choices={code:selection(code,getattr(args,code.lower())) for code in wanted}
        args.out.mkdir(parents=True)
        manifest={}
        for which,selection_values in choices.items():
            manifest[which]=generate(which,args.out/which,selection_values)
        # A manifest is intentionally not placed inside either public document root.
        (args.out/'selection.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        for name,attributes in manifest.items():
            print(f'{name}: {attributes["brand"]}, {attributes["palette"]}, illustration {attributes["artwork"]}, copy {attributes["copy_kit"]}')
    except (OSError,ValueError) as e:
        print(f'ERROR: {e}',file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
