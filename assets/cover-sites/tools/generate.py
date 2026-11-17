#!/usr/bin/env python3
"""Render six one-time static website covers. Python standard library only.

The caller persists only the template code and four catalogue indices. Fine colour
adjustments, illustrations and dates live exclusively in the generated files.
"""
import argparse
import colorsys
from datetime import date, timedelta
import html
import json
import math
from pathlib import Path
import random
import re
import secrets
import shutil
import struct
import sys
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'data/variants.json').read_text(encoding='utf-8'))
CODES = ('A1', 'A2', 'A3', 'B1', 'B2', 'B3')
TOKENS = re.compile(r'\{\{([A-Z][A-Z_0-9]*)\}\}')
SVGNS = '{http://www.w3.org/2000/svg}'
# Foreground/background pairs used by the reviewed CSS. Bright themes put dark
# text on accents; B3 uses a separately chosen foreground on the accent block.
CONTRAST_BACKGROUNDS = {
    'A1': (('#ffffff', 'accent'), ('#ffffff', 'accent2'), ('soft', 'accent2')),
    'A2': (('#0d1728', 'accent'), ('#07101a', 'accent')),
    'A3': (('#121417', 'accent'), ('#101414', 'accent')),
    'B1': (('#ffffff', 'accent'), ('#ffffff', 'accent2')),
    'B2': (('#ffffff', 'accent2'), ('#f6f8f7', 'accent2'), ('soft', 'accent2'), ('accent', 'on_accent')),
    'B3': (('#ffffff', 'accent2'), ('#f6f2e9', 'accent2'), ('soft', 'accent2'), ('accent', 'on_accent')),
}


def selection(which, requested, *, rng=None, now=None):
    """Choose/validate the unchanged four zero-based catalogue indices."""
    obj = DATA[which]
    options = (len(obj['brands']), len(obj['palettes']), 3, len(obj['copy']))
    if requested is None:
        entropy = rng if rng is not None else secrets.SystemRandom()
        return [entropy.randrange(n) for n in options]
    try:
        values = [int(n) for n in requested.split(':')]
    except ValueError:
        raise ValueError(f'{which}: expected 4 integer indices separated by colons') from None
    if len(values) != 4 or any(not 0 <= n < limit for n, limit in zip(values, options)):
        raise ValueError(f'{which}: index out of range; sizes are {options}')
    return values


def _rgb(colour):
    return tuple(int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _hex(rgb):
    return '#' + ''.join(f'{round(max(0.0, min(1.0, x)) * 255):02x}' for x in rgb)


def contrast(foreground, background):
    """WCAG relative-luminance contrast, including sRGB gamma."""
    def luminosity(colour):
        r, g, b = _rgb(colour)
        channels = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in (r, g, b)]
        return sum(a * b for a, b in zip(channels, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminosity(foreground), luminosity(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _on_accent(accent):
    # Only B3 places white text directly on all four accent backgrounds. Gold
    # cannot achieve 4.5:1 against white with the permitted +/-3% lightness.
    return '#ffffff' if contrast('#ffffff', accent) >= 4.5 else '#181d21'


def colour_pairs(which, palette):
    merged = dict(palette)
    merged['on_accent'] = _on_accent(palette['accent'])
    return {(fg, bg): contrast(merged.get(fg, fg), merged.get(bg, bg))
            for bg, fg in CONTRAST_BACKGROUNDS[which]}


def _adjusted_colours(which, original, rng):
    original_pairs = colour_pairs(which, original)
    for _ in range(1500):
        # Same HSL offset for accent, accent2 and soft preserves their relative
        # positions in hue, saturation and lightness (subject to sRGB rounding).
        dh = rng.uniform(-10.0 / 360.0, 10.0 / 360.0)
        ds = rng.uniform(-0.05, 0.05)
        dl = rng.uniform(-0.03, 0.03)
        changed = {'id': original['id']}
        roundtrip_ok = True
        for key in ('accent', 'accent2', 'soft'):
            hue, light, sat = colorsys.rgb_to_hls(*_rgb(original[key]))
            new = colorsys.hls_to_rgb((hue + dh) % 1, min(1, max(0, light + dl)),
                                     min(1, max(0, sat + ds)))
            changed[key] = _hex(new)
            hh, ll, ss = colorsys.rgb_to_hls(*_rgb(changed[key]))
            hue_change = ((hh - hue + 0.5) % 1.0) - 0.5
            if (abs(hue_change) > 10 / 360 + .003 or
                    abs(ll - light) > .033 or abs(ss - sat) > .053):
                roundtrip_ok = False
        if not roundtrip_ok:
            continue
        pairs = colour_pairs(which, changed)
        if all(ratio >= max(4.5, original_pairs[key] - 0.3) - 1e-9
               for key, ratio in pairs.items()):
            changed['on_accent'] = _on_accent(changed['accent'])
            return changed
    raise ValueError(f'{which}: no contrast-safe colour shift for {original["id"]}')


def _generation_dates(rng, today):
    if isinstance(today, str):
        today = date.fromisoformat(today)
    if not isinstance(today, date):
        raise ValueError('now must be a date or ISO YYYY-MM-DD string')
    dates = [today - timedelta(days=rng.randint(10, 60))]
    for _ in range(5):
        dates.append(dates[-1] - timedelta(days=rng.randint(20, 150)))
    # Five gaps <=150 days and the first <=60 days: always <30 months.
    tokens = {'YEAR': str(today.year), 'YEAR_FROM': str(dates[-1].year)}
    for n, value in enumerate(dates, 1):
        tokens[f'DATE_{n}'] = f'{value.day} {value.strftime("%B")} {value.year}'
        tokens[f'ISO_{n}'] = value.isoformat()
    return tokens


def render_text(text, replacements, path):
    def replace(match):
        name = match.group(1)
        if name not in replacements:
            raise ValueError(f'Unknown substitution {name} in {path}')
        return str(replacements[name])
    result = TOKENS.sub(replace, text)
    if TOKENS.search(result):
        raise ValueError(f'Unexpected template syntax in {path}')
    return result


def _jitter(svg, rng, *, hero=False):
    """Move/resize selected visible artwork, keeping the original SVG structure."""
    tree = ET.fromstring(svg)
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    if hero:
        # Keep SVG background, defs, text and top-level panel layout intact.
        shapes = [node for node in tree.iter()
                  if node.tag in (SVGNS + 'path', SVGNS + 'circle', SVGNS + 'ellipse')]
        if not shapes:
            shapes = [node for node in tree.iter() if node.tag == SVGNS + 'rect']
        chosen = shapes[-min(3, len(shapes)):]
        view = tree.get('viewBox')
        if view:
            _, _, w, h = (float(n) for n in view.split())
        else:
            w, h = float(tree.get('width', '720')), float(tree.get('height', '560'))
    else:
        # In the favicon only the foreground mark moves; background and any
        # central cut-out (B3 circle) remain at their original coordinates.
        chosen = [node for node in tree if node.tag == SVGNS + 'path']
        w = h = 64.0
    for node in chosen:
        dx, dy = rng.uniform(-0.025, 0.025) * w, rng.uniform(-0.025, 0.025) * h
        sx, sy = rng.uniform(0.975, 1.025), rng.uniform(0.975, 1.025)
        node.set('transform', f'translate({dx:.5f} {dy:.5f}) translate({w/2:g} {h/2:g}) '
                              f'scale({sx:.6f} {sy:.6f}) translate({-w/2:g} {-h/2:g})')
    return ET.tostring(tree, encoding='unicode', short_empty_elements=True)


def _path_segments(path):
    """Small SVG path subset used by the six source favicon marks.

    Supports M/m, L/l, H/h, V/v, A/a and Z/z. The single tiny arc in B2 is
    approximated by its chord at favicon resolutions; it stays recognizable.
    """
    parts = re.findall(r'[MmLlHhVvAaZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?', path)
    sequences = []
    point = (0.0, 0.0)
    command = None
    i = 0
    while i < len(parts):
        if parts[i].isalpha():
            command = parts[i]
            i += 1
            if command in ('z', 'Z'):
                if sequences:
                    sequences[-1][1] = True
                    point = sequences[-1][0][0]
                command = None
                continue
        if command is None:
            continue
        c = command.upper()
        needed = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'A': 7}[c]
        if i + needed > len(parts):
            raise ValueError(f'Invalid SVG path {path}')
        vals = [float(t) for t in parts[i:i + needed]]
        i += needed
        x, y = point
        if c in ('M', 'L'):
            px, py = vals
            if command.islower(): px, py = x + px, y + py
        elif c == 'H':
            px, py = (x + vals[0] if command.islower() else vals[0]), y
        elif c == 'V':
            px, py = x, (y + vals[0] if command.islower() else vals[0])
        else:
            px, py = vals[5:7]
            if command.islower(): px, py = x + px, y + py
        point = (px, py)
        if c == 'M':
            sequences.append([[point], False])
            command = 'l' if command == 'm' else 'L'
        elif sequences:
            sequences[-1][0].append(point)
        else:
            raise ValueError('SVG path must start with M/m')
    return sequences


def _rgba(colour):
    if not colour or colour == 'none':
        return None
    if re.fullmatch(r'#[0-9a-fA-F]{3}', colour):
        colour = '#' + ''.join(v * 2 for v in colour[1:])
    if re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
        return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
    raise ValueError(f'Unsupported favicon SVG colour {colour}')


def _point_in_polygon(x, y, coords):
    odd = False
    for n in range(len(coords)):
        x1, y1 = coords[n - 1]
        x2, y2 = coords[n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            odd = not odd
    return odd


def _distance_segment(x, y, a, b):
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    length2 = vx * vx + vy * vy
    t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / length2)) if length2 else 0
    return math.hypot(x - (ax + t * vx), y - (ay + t * vy))


def _svg_shapes(svg):
    doc = ET.fromstring(svg)
    shapes = []
    for node in doc:
        kind = node.tag.rsplit('}', 1)[-1]
        if kind not in ('rect', 'circle', 'path'):
            continue
        # An SVG path without fill= defaults to black; this matches browser SVG.
        fill = _rgba(node.get('fill', '#000000'))
        stroke = _rgba(node.get('stroke', 'none'))
        width = float(node.get('stroke-width', '1'))
        transform = node.get('transform', '')
        if transform:
            nums = [float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)', transform)]
            dx, dy, cx, cy, sx, sy, _, _ = nums
            assert cx == cy == 32.0
        else:
            dx = dy = 0.0
            sx = sy = 1.0
        def adjust(coord):
            x, y = coord
            return ((x - 32) * sx + 32 + dx, (y - 32) * sy + 32 + dy)
        if kind == 'path':
            parts = [([adjust(p) for p in points], closed)
                     for points, closed in _path_segments(node.get('d', ''))]
            shapes.append(('path', parts, fill, stroke, width))
        elif kind == 'rect':
            bounds = (float(node.get('x', '0')), float(node.get('y', '0')),
                      float(node.get('width', '0')), float(node.get('height', '0')),
                      float(node.get('rx', '0')))
            shapes.append(('rect', bounds, fill, stroke, width))
        else:
            values = tuple(float(node.get(k, '0')) for k in ('cx', 'cy', 'r'))
            shapes.append(('circle', values, fill, stroke, width))
    return shapes


def _drawn(shape, x, y):
    kind, geometry, fill, stroke, width = shape
    if kind == 'rect':
        bx, by, w, h, rad = geometry
        ux, uy = x - bx, y - by
        inside = 0 <= ux <= w and 0 <= uy <= h
        if inside and rad:
            cx = min(max(ux, rad), w - rad)
            cy = min(max(uy, rad), h - rad)
            inside = (ux - cx) ** 2 + (uy - cy) ** 2 <= rad ** 2
        return fill if inside else None
    if kind == 'circle':
        cx, cy, rad = geometry
        dist = math.hypot(cx - x, cy - y)
        if stroke and abs(dist - rad) <= width / 2:
            return stroke
        return fill if dist <= rad else None
    if stroke:
        for coords, closed in geometry:
            edges = list(zip(coords, coords[1:]))
            if closed:edges.append((coords[-1], coords[0]))
            if any(_distance_segment(x, y, a, b) <= width / 2 for a, b in edges):
                return stroke
    if fill:
        # Nonzero SVG fill generally coincides with even-odd for the simple
        # one-contour favicon shapes; all source paths have <=1 filled contour.
        if any(_point_in_polygon(x, y, coords) for coords, _ in geometry if len(coords) >= 3):
            return fill
    return None


def _png_chunk(name, data):
    return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))


def _icon_png(shapes, pixels):
    rows = []
    # 2x2 sub-pixel sampling gives antialiased edges without external imaging.
    for row in range(pixels):
        current = bytearray(b'\x00')
        for col in range(pixels):
            cover = 0
            red = green = blue = 0
            for uy in (0.25, 0.75):
                for ux in (0.25, 0.75):
                    x, y = (col + ux) * 64 / pixels, (row + uy) * 64 / pixels
                    chosen = None
                    for shape in shapes:
                        pixel = _drawn(shape, x, y)
                        if pixel is not None:chosen = pixel
                    if chosen is not None:
                        cover += 1
                        red += chosen[0]
                        green += chosen[1]
                        blue += chosen[2]
            if cover:
                current.extend((round(red / cover), round(green / cover),
                                round(blue / cover), round(255 * cover / 4)))
            else:
                current.extend((0, 0, 0, 0))
        rows.append(bytes(current))
    payload = zlib.compress(b''.join(rows), 9)
    return (b'\x89PNG\r\n\x1a\n'
            + _png_chunk(b'IHDR', struct.pack('>IIBBBBB', pixels, pixels, 8, 6, 0, 0, 0))
            + _png_chunk(b'IDAT', payload) + _png_chunk(b'IEND', b''))


def favicon_ico(svg):
    """Create 16/32/48px valid PNG-in-ICO frames from the same SVG geometry."""
    shapes = _svg_shapes(svg)
    images = [_icon_png(shapes, size) for size in (16, 32, 48)]
    offset = 6 + len(images) * 16
    entries = []
    for size, png in zip((16, 32, 48), images):
        entries.append(struct.pack('<BBBBHHII', size, size, 0, 0, 1, 32, len(png), offset))
        offset += len(png)
    return struct.pack('<HHH', 0, 1, 3) + b''.join(entries + images)


def _robots(rng):
    variants = (
        'User-agent: *\nDisallow:\n',
        'User-agent: *\nAllow: /\n',
        '# Public pages may be indexed.\nUser-agent: *\nDisallow:\n',
        'User-agent: *\n# This site uses only local static resources.\nAllow: /\n',
    )
    return variants[rng.randrange(4)]


def generate(which, destination, options, *, rng=None, now=None):
    """Create a new directory and return the unchanged public manifest fields."""
    brand_idx, palette_idx, art_idx, copy_idx = options
    item = DATA[which]
    brand = item['brands'][brand_idx]
    base_palette = item['palettes'][palette_idx]
    copy = item['copy'][copy_idx]
    entropy = rng if rng is not None else secrets.SystemRandom()
    palette = _adjusted_colours(which, base_palette, entropy)
    today = date.today() if now is None else now
    values = {'VARIANT_NONCE': f'{entropy.getrandbits(96):024x}',
              'BRAND': html.escape(brand, quote=True),
              'ACCENT': palette['accent'], 'ACCENT2': palette['accent2'],
              'SOFT': palette['soft'], 'ON_ACCENT': palette['on_accent']}
    values.update({key.upper(): html.escape(value, quote=True) for key, value in copy.items()})
    values.update(_generation_dates(entropy, today))
    origin = ROOT / 'templates' / which
    destination.mkdir(parents=True, exist_ok=False)
    for src in origin.rglob('*'):
        if not src.is_file() or 'art' in src.relative_to(origin).parts or 'ico' in src.relative_to(origin).parts:
            continue
        relative = src.relative_to(origin)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in ('.html', '.css', '.svg', '.txt', '.js'):
            contents = render_text(src.read_text(encoding='utf-8'), values, str(relative))
            if relative == Path('favicon.svg'):
                contents = _jitter(contents, entropy)
            target.write_text(contents, encoding='utf-8')
        else:
            shutil.copyfile(src, target)
    hero = origin / 'static' / 'art' / f'hero-{art_idx+1}.svg'
    art = render_text(hero.read_text(encoding='utf-8'), values, str(hero))
    (destination / 'static' / 'hero.svg').write_text(_jitter(art, entropy, hero=True), encoding='utf-8')
    (destination / 'favicon.ico').write_bytes(favicon_ico((destination / 'favicon.svg').read_text(encoding='utf-8')))
    (destination / 'robots.txt').write_text(_robots(entropy), encoding='utf-8')
    return {'brand': brand, 'palette': base_palette['id'], 'artwork': art_idx + 1,
            'copy_kit': copy_idx + 1,
            'scope': 'Static website files only; no authentication or external API'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build', help='Output parent directory (must not exist)')
    parser.add_argument('--sites', nargs='+', choices=CODES,
                        help='Optional site subset; defaults to all six (e.g. --sites A1 B2 B3)')
    parser.add_argument('--seed', help='Reproducible testing seed; omit for secrets-based randomness')
    parser.add_argument('--now', type=date.fromisoformat, help='Generation date, ISO YYYY-MM-DD')
    for code in CODES:
        parser.add_argument('--' + code.lower(), help='Brand:palette:artwork:copy zero-based indices')
    args = parser.parse_args(argv)
    try:
        if args.out.exists():raise ValueError(f'Output already exists: {args.out}; choose a new directory')
        wanted = args.sites or CODES
        if len(set(wanted)) != len(wanted):raise ValueError('Duplicate site in --sites')
        entropy = random.Random(args.seed) if args.seed is not None else secrets.SystemRandom()
        choices = {code: selection(code, getattr(args, code.lower()), rng=entropy, now=args.now) for code in wanted}
        args.out.mkdir(parents=True)
        manifest = {}
        for which, selection_values in choices.items():
            manifest[which] = generate(which, args.out / which, selection_values, rng=entropy, now=args.now)
        (args.out / 'selection.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        for name, attrs in manifest.items():
            print(f'{name}: {attrs["brand"]}, {attrs["palette"]}, illustration {attrs["artwork"]}, copy {attrs["copy_kit"]}')
    except (OSError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
