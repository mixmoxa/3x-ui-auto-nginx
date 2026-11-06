#!/usr/bin/env python3
"""Verify generated static websites without external dependencies or network access."""
import argparse
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs=[];self.ids=[];self.title=[];self.in_title=False;self.links=[];self.scripts=[];self.lang=False;self.description=False
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if tag=='html':self.lang=bool(data.get('lang'))
        if tag=='title':self.in_title=True
        if tag=='meta' and data.get('name')=='description':self.description=bool(data.get('content'))
        if data.get('id'):self.ids.append(data['id'])
        for attr in ('href','src'):
            if data.get(attr):self.refs.append((tag,attr,data[attr]))
        if tag=='a' and data.get('href'):self.links.append(data['href'])
        if tag=='script' and data.get('src'):self.scripts.append(data['src'])
        if tag=='form' and data.get('action') and data['action'] not in ('','#'): raise ValueError('Unexpected network form action')
        if any(k.startswith('on') for k in data):raise ValueError('Inline event handler found')
    def handle_endtag(self, tag):
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title.append(data)

def check_site(root):
    problems=[];count=0
    html_pages=sorted(root.rglob('*.html'))
    if not html_pages: problems.append('No HTML pages')
    for page in html_pages:
        count+=1
        try:
            content=page.read_text(encoding='utf-8')
            item=Page();item.feed(content);item.close()
        except Exception as e:
            problems.append(f'{page.relative_to(root)}: cannot parse: {e}')
            continue
        if not item.lang or not item.description or not ''.join(item.title).strip():
            problems.append(f'{page.relative_to(root)}: missing language, title or meta description')
        if len(item.ids)!=len(set(item.ids)):
            problems.append(f'{page.relative_to(root)}: duplicate DOM ids')
        if '{{' in content or '}}BRAND' in content:
            problems.append(f'{page.relative_to(root)}: unrendered template')
        if not item.links:
            problems.append(f'{page.relative_to(root)}: no navigation links')
        for tag,attr,ref in item.refs:
            if ref.startswith(('#','/')) or ref.startswith('./') or ref.startswith('../'):
                parts=urlsplit(ref)
                if parts.netloc or parts.scheme:
                    problems.append(f'{page.relative_to(root)}: absolute/external URL: {ref}')
                    continue
                path=unquote(parts.path)
                dest=(root/path.lstrip('/')) if path.startswith('/') else (page.parent/path)
                if not path:dest=page
                if dest.is_dir():dest=dest/'index.html'
                if not dest.is_file():
                    problems.append(f'{page.relative_to(root)}: missing local resource: {ref}')
                    continue
                if parts.fragment and dest.suffix=='.html':
                    other=Page();other.feed(dest.read_text(encoding='utf-8'))
                    if unquote(parts.fragment) not in other.ids:
                        problems.append(f'{page.relative_to(root)}: missing anchor: {ref}')
            else:
                problems.append(f'{page.relative_to(root)}: nonlocal URL: {ref}')
    for stylesheet in root.rglob('*.css'):
        content=stylesheet.read_text(encoding='utf-8')
        if re.search(r'@import\b|url\s*\(\s*["\']?\s*(?:https?:|//)',content,re.I):
            problems.append(f'{stylesheet.relative_to(root)}: external stylesheet dependency')
        if '{{' in content:
            problems.append(f'{stylesheet.relative_to(root)}: unrendered palette')
    for script in root.rglob('*.js'):
        content=script.read_text(encoding='utf-8')
        if re.search(r'\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\b',content):
            problems.append(f'{script.relative_to(root)}: unexpected network capability')
    for svg in root.rglob('*.svg'):
        try:ET.parse(svg)
        except ET.ParseError as e:problems.append(f'{svg.relative_to(root)}: malformed SVG: {e}')
    if not (root/'404.html').exists():problems.append('Missing custom 404.html')
    if not (root/'favicon.ico').exists() or (root/'favicon.ico').read_bytes()[:4]!=b'\x00\x00\x01\x00':
        problems.append('Invalid favicon.ico')
    total=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    return problems,count,total

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'build')
    args=parser.parse_args();all_problems=[]
    for which in ('A1','A2','A3','B1','B2','B3'):
        root=args.root/which
        if not root.is_dir():all_problems.append(f'{which}: missing directory');continue
        problems,pages,total=check_site(root)
        print(f'{which}: {pages} HTML pages, {total/1024:.1f} KiB total; {"PASS" if not problems else "FAIL"}')
        all_problems.extend(f'{which}: {message}' for message in problems)
    if all_problems:
        print('\n'.join(all_problems),file=sys.stderr)
        return 1
    return 0
if __name__=='__main__':sys.exit(main())
