#!/usr/bin/env python3
"""Verify generated static websites without external dependencies or network access."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from datetime import date
import struct
import zlib
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs=[];self.ids=[];self.title=[];self.in_title=False;self.links=[];self.scripts=[];self.lang=False;self.description=False
        self.description_text='';self.theme_variants=[];self.h1_count=0
        self.hidden=0;self.words=[];self.time_active=[];self.times=[]
    def handle_starttag(self, tag, attrs):
        data=dict(attrs)
        if tag in ('head','style','script'):self.hidden+=1
        if tag=='h1':self.h1_count+=1
        if tag=='html':self.lang=bool(data.get('lang'))
        if tag=='title':self.in_title=True
        if tag=='meta' and data.get('name')=='description':
            self.description=bool(data.get('content'))
            self.description_text=data.get('content','')
        if tag=='meta' and data.get('name')=='theme-color':
            self.theme_variants.append(data.get('data-variant',''))
        if tag=='time':self.time_active.append([data.get('datetime',''),[]])
        if data.get('id'):self.ids.append(data['id'])
        for attr in ('href','src'):
            if data.get(attr):self.refs.append((tag,attr,data[attr]))
        if tag=='a' and data.get('href'):self.links.append(data['href'])
        if tag=='script' and data.get('src'):self.scripts.append(data['src'])
        if tag=='form' and data.get('action') and data['action'] not in ('','#'): raise ValueError('Unexpected network form action')
        if any(k.startswith('on') for k in data):raise ValueError('Inline event handler found')
    def handle_endtag(self, tag):
        if tag=='title':self.in_title=False
        if tag=='time' and self.time_active:
            dt, visible=self.time_active.pop()
            self.times.append((dt,''.join(visible).strip()))
        if tag in ('head','style','script'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if self.in_title:self.title.append(data)
        if self.time_active:self.time_active[-1][1].append(data)
        if not self.hidden:self.words.extend(re.findall(r"\b[\w]+(?:[-']\w+)*\b",data))

MONTHS = ('January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December')
UNRESOLVED = re.compile(r'\{\{[A-Z][A-Z_0-9]*\}\}')


def _ico_problems(blob):
    """Validate all three PNG frames, chunk CRCs and uncompressed scanlines."""
    problems = []
    if len(blob) < 54:
        return ['ICO too short']
    reserved, kind, count = struct.unpack_from('<HHH', blob)
    if (reserved, kind, count) != (0, 1, 3):
        return ['ICO must contain three image frames']
    regions = []
    for i, expected in enumerate((16, 32, 48)):
        w, h, palette, reserved, planes, bpp, nbytes, offset = struct.unpack_from('<BBBBHHII', blob, 6 + 16 * i)
        if (w, h, palette, reserved, planes, bpp) != (expected, expected, 0, 0, 1, 32):
            problems.append(f'ICO frame {expected}: invalid directory entry')
            continue
        if offset < 54 or offset + nbytes > len(blob):
            problems.append(f'ICO frame {expected}: invalid offset or size')
            continue
        regions.append((offset, offset + nbytes))
        png = blob[offset:offset + nbytes]
        if not png.startswith(b'\x89PNG\r\n\x1a\n'):
            problems.append(f'ICO frame {expected}: missing PNG signature')
            continue
        cursor = 8
        chunks = []
        pixels = b''
        while cursor + 12 <= len(png):
            length = struct.unpack_from('>I', png, cursor)[0]
            if length > len(png) - cursor - 12:
                break
            name = png[cursor + 4:cursor + 8]
            value = png[cursor + 8:cursor + 8 + length]
            crc = struct.unpack_from('>I', png, cursor + 8 + length)[0]
            if zlib.crc32(name + value) != crc:
                problems.append(f'ICO frame {expected}: PNG CRC mismatch')
                break
            chunks.append(name)
            if name == b'IHDR':
                if len(value) != 13 or struct.unpack_from('>IIBBBBB', value) != (expected, expected, 8, 6, 0, 0, 0):
                    problems.append(f'ICO frame {expected}: unsupported PNG format')
            if name == b'IDAT':
                pixels += value
            cursor += 12 + length
            if name == b'IEND':
                break
        if not chunks or chunks[0] != b'IHDR' or chunks[-1] != b'IEND' or cursor != len(png):
            problems.append(f'ICO frame {expected}: incomplete PNG frame')
            continue
        try:
            decoded = zlib.decompress(pixels)
            line = expected * 4 + 1
            if len(decoded) != expected * line or any(decoded[row * line] != 0 for row in range(expected)):
                problems.append(f'ICO frame {expected}: malformed RGBA pixels')
        except zlib.error:
            problems.append(f'ICO frame {expected}: invalid deflate stream')
    if any(a[1] > b[0] for a, b in zip(regions, regions[1:])):
        problems.append('ICO frame offsets overlap')
    if regions and regions[-1][1] != len(blob):
        problems.append('ICO trailing data')
    return problems


def _html_dates(content):
    """Reject impossible ISO / English dates in generated HTML."""
    invalid = []
    for match in re.finditer(r'(?<![\d-])\d{4}-\d{2}-\d{2}(?![\d-])', content):
        try:
            date.fromisoformat(match.group())
        except ValueError:
            invalid.append(match.group())
    english = r'\b(\d{1,2}) (' + '|'.join(MONTHS) + r') (\d{4})\b'
    for match in re.finditer(english, content):
        day, month, year = match.groups()
        try:
            date(int(year), MONTHS.index(month) + 1, int(day))
        except ValueError:
            invalid.append(match.group())
    return invalid

def check_site(root):
    problems=[];count=0
    html_pages=sorted(root.rglob('*.html'))
    if len(html_pages)>14:problems.append(f'Site has {len(html_pages)} HTML pages, limit 14')
    if not html_pages: problems.append('No HTML pages')
    titles={}; descriptions={}; variants=set(); parsed={}
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
        relative=str(page.relative_to(root))
        parsed[relative]=item
        title=''.join(item.title).strip()
        for field,value,seen in (('title',title,titles),('meta description',item.description_text,descriptions)):
            if value and value in seen:
                problems.append(f'{relative}: duplicate {field} also in {seen[value]}')
            else:seen[value]=relative
        if len(item.theme_variants)!=1 or not re.fullmatch(r'[0-9a-fA-F]{24}', item.theme_variants[0] if item.theme_variants else ''):
            problems.append(f'{relative}: missing or invalid 24-char data-variant')
        else:variants.add(item.theme_variants[0])
        if page.name!='404.html' and len(item.words)<250:
            problems.append(f'{relative}: only {len(item.words)} visible words, minimum 250')
        if item.h1_count!=1:
            problems.append(f'{relative}: expected one h1, got {item.h1_count}')
        for stamp,visible in item.times:
            try:
                value=date.fromisoformat(stamp)
                if visible!=f'{value.day} {MONTHS[value.month-1]} {value.year}':
                    raise ValueError('visible date differs from datetime')
            except ValueError as exc:
                problems.append(f'{relative}: time datetime={stamp!r} display={visible!r}: {exc}')
        if len(item.ids)!=len(set(item.ids)):
            problems.append(f'{page.relative_to(root)}: duplicate DOM ids')
        if UNRESOLVED.search(content) or '{{' in content or '}}BRAND' in content:
            problems.append(f'{page.relative_to(root)}: unrendered template')
        for invalid in _html_dates(content):
            problems.append(f'{page.relative_to(root)}: invalid date: {invalid}')
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
    if len(variants)>1:
        problems.append('HTML pages have different data-variant values within one build')
    # A published HTML document must be accessible by following local links
    # from the homepage. The 404 document is served on errors, not linked.
    reachable={'index.html'};waiting=['index.html']
    while waiting:
        page_name=waiting.pop()
        item=parsed.get(page_name)
        if item is None:continue
        for ref in item.links:
            parts=urlsplit(ref)
            if parts.scheme or parts.netloc:continue
            part=unquote(parts.path)
            dest=(root/part.lstrip('/')) if part.startswith('/') else (root/page_name).parent/part
            if not part:dest=root/page_name
            if dest.is_dir():dest=dest/'index.html'
            try:relative=dest.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:continue
            if relative in parsed and relative not in reachable:
                reachable.add(relative);waiting.append(relative)
    for unreachable in sorted(set(parsed)-reachable-{'404.html'}):
        problems.append(f'{unreachable}: not reachable from index.html by local links')
    for stylesheet in root.rglob('*.css'):
        content=stylesheet.read_text(encoding='utf-8')
        if re.search(r'@import\b|url\s*\(\s*["\']?\s*(?:https?:|//)',content,re.I):
            problems.append(f'{stylesheet.relative_to(root)}: external stylesheet dependency')
        if UNRESOLVED.search(content):
            problems.append(f'{stylesheet.relative_to(root)}: unrendered palette')
    for script in root.rglob('*.js'):
        content=script.read_text(encoding='utf-8')
        if UNRESOLVED.search(content):
            problems.append(f'{script.relative_to(root)}: unrendered template token')
        if re.search(r'\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\b',content):
            problems.append(f'{script.relative_to(root)}: unexpected network capability')
    for suffix in ('*.svg', '*.txt'):
        for path in root.rglob(suffix):
            if UNRESOLVED.search(path.read_text(encoding='utf-8')):
                problems.append(f'{path.relative_to(root)}: unrendered template token')
    for svg in root.rglob('*.svg'):
        try:ET.parse(svg)
        except ET.ParseError as e:problems.append(f'{svg.relative_to(root)}: malformed SVG: {e}')
    if not (root/'404.html').exists():problems.append('Missing custom 404.html')
    if not (root/'favicon.ico').exists():
        problems.append('Missing favicon.ico')
    else:
        problems.extend(_ico_problems((root/'favicon.ico').read_bytes()))
    robots = root / 'robots.txt'
    if robots.exists():
        content = robots.read_text(encoding='utf-8')
        if 'Sitemap:' in content or not any(x in content for x in ('Disallow:', 'Allow: /')):
            problems.append('robots.txt: unexpected rule')
    else:
        problems.append('Missing robots.txt')
    total=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    if total > 400 * 1024:problems.append(f'Site exceeds 400 KiB: {total} bytes')
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
