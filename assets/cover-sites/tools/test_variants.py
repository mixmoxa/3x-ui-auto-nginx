#!/usr/bin/env python3
"""Exhaustively render and statically verify all 432 reviewed variants per site.
Creates isolated, temporary site roots, not permanent artefacts or runtime state.
"""
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path
import random
import json
import os
import sys
import tempfile
from generate import generate,DATA
from check import check_site

SITES=('A1','A2','A3','B1','B2','B3')

def check_variant_site(site):
    item=DATA[site]
    counts=[len(item['brands']),len(item['palettes']),3,len(item['copy'])]
    total=0;max_size=0
    with tempfile.TemporaryDirectory(prefix='cover-variants-'+site+'-') as tmp:
        for indexes in product(*(range(n) for n in counts)):
            path=Path(tmp)/str(total)
            generate(site,path,indexes,rng=random.Random(f'catalogue-{site}-{indexes}'),now='2026-11-17')
            problems,pages,size=check_site(path)
            if problems:
                raise ValueError(f'{site} variant {indexes}: FAIL '+str(problems))
            total+=1
            max_size=max(max_size,size)
    assert total==432,(site,total)
    return f'{site}: {total} combinations, max {max_size} bytes, validated pages and resources: PASS'

def main():
    try:
        with ProcessPoolExecutor(max_workers=min(os.cpu_count() or 1,6)) as executor:
            for result in executor.map(check_variant_site,SITES):
                print(result,flush=True)
    except Exception as error:
        print(str(error),file=sys.stderr)
        return 1
    return 0
if __name__=='__main__':sys.exit(main())
