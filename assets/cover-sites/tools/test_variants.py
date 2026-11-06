#!/usr/bin/env python3
"""Exhaustively render and statically verify all 144 reviewed variants per site.
Creates isolated, temporary site roots, not permanent artefacts or runtime state.
"""
from itertools import product
from pathlib import Path
import json
import sys
import tempfile
from generate import generate,DATA
from check import check_site

SITES=('A1','A2','A3','B1','B2','B3')

def main():
    for site in SITES:
        item=DATA[site]
        counts=[len(item['brands']),len(item['palettes']),3,len(item['copy'])]
        total=0
        with tempfile.TemporaryDirectory(prefix='cover-variants-'+site+'-') as tmp:
            for indexes in product(*(range(n) for n in counts)):
                path=Path(tmp)/str(total)
                generate(site,path,indexes)
                problems,pages,size=check_site(path)
                if problems:
                    print(f'{site} variant {indexes}: FAIL '+str(problems),file=sys.stderr)
                    return 1
                total+=1
        print(f'{site}: {total} combinations, validated pages and resources: PASS')
    return 0
if __name__=='__main__':sys.exit(main())
