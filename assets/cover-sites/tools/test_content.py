#!/usr/bin/env python3
"""Verify dated article/list parity and six copy-kit indices on each template."""
from datetime import date
from pathlib import Path
import random
import re
import tempfile
from generate import CODES, DATA, generate, selection
from check import check_site

NEW={
    'A1': ('guides', ('scoping','decision-notes','review-rhythm')),
    'A2': ('field-notes', ('latency','error-budgets','dependencies')),
    'A3': ('guides', ('content-types','http-caching','redirects')),
    'B1': ('journal', ('service-boundaries','rollback-decisions','operational-handoffs')),
    'B2': ('start', ('conditional-requests','content-negotiation','redirects')),
    'B3': ('notes', ('type-hierarchy','prototype-honesty','accessibility-review')),
}
TIMES=re.compile(r'<time datetime="(\d{4}-\d{2}-\d{2})">([^<]+)</time>')

def main():
    tested=0
    with tempfile.TemporaryDirectory(prefix='cover-content-') as tmp:
        for code in CODES:
            page_paths=None
            assert len(DATA[code]['copy'])==6
            for copy_index in (0,5):
                base=Path(tmp)/f'{code}-{copy_index}'
                indexes=selection(code,f'0:0:0:{copy_index}')
                generate(code,base,indexes,rng=random.Random(f'content-{code}-{copy_index}'),now=date(2026,11,17))
                problems,pages,size=check_site(base)
                assert not problems,(code,problems)
                assert 9<=pages<=14 and size<400*1024
                current_paths=tuple(sorted(p.relative_to(base).as_posix() for p in base.rglob('*.html')))
                if page_paths is None:page_paths=current_paths
                assert page_paths==current_paths,(code,'page addresses depend on text selection')
                listing,slugs=NEW[code]
                text=(base/listing/'index.html').read_text()
                stamps=[]
                for slug in slugs:
                    article=(base/(listing if code!='B2' else 'guides')/slug/'index.html')
                    assert article.exists(),(code,article)
                    matches=TIMES.findall(article.read_text())
                    assert len(matches)==1,(code,slug,matches)
                    stamp,visible=matches[0]
                    assert f'<time datetime="{stamp}">{visible}</time>' in text,(code,slug)
                    stamps.append(date.fromisoformat(stamp))
                assert stamps==sorted(stamps,reverse=True) and len(set(stamps))==3,(code,stamps)
                tested+=1
            print(f'{code}: 3 dated articles linked with matching list dates, old/new copy kits PASS')
    print(f'PASS: {tested} builds, 36 article-date/list comparisons and stable HTML paths')
if __name__=='__main__':main()
