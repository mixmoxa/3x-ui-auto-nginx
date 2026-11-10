"""Bounded domain switch for the project's local SQLite/nginx-stream layout.

The manager owns fd 9 and supplies trusted checks/Backup from its selected tree.
The durable journal contains data only; recovery never executes saved code.
"""
import argparse
import base64
import copy
import fcntl
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import socket
import sqlite3
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit, urlunsplit
from configobj import ConfigObj
from cryptography import x509
from cryptography.hazmat.primitives import serialization

DB = '/etc/x-ui/x-ui.db'
MANIFEST = '/etc/x-ui/auto-nginx-managed.json'
STATE = '/var/lib/3x-ui-auto-nginx/change-domains'
STREAM = '/etc/nginx/stream-enabled/stream.conf'
HTTP = '/etc/nginx/sites-available/80.conf'
HOOK = '/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'
HYSTERIA = '/etc/nginx/sites-available/hysteria-cover.conf'
HYSTERIA_ENABLED = '/etc/nginx/sites-enabled/hysteria-cover.conf'
HYSTERIA_MASQUERADE = dict(type='proxy', url='unix:/run/3x-ui-hysteria-cover.sock', rewriteHost=False)
CLASH = '/var/www/subpage/clash.yaml.tpl'
DIAGNOSTICS = '/var/www/diagnostics/index.html'
AGH = '/opt/AdGuardHome/managed.json'
CORE = ('reality', 'ws', 'grpc', 'xhttp', 'hysteria2')
SNI_INCLUDE = '/etc/nginx/stream-sni.d/*.conf'
UPSTREAM_INCLUDE = '/etc/nginx/stream-upstreams.d/*.conf'
TELEMT_FILES = ('/etc/nginx/conf.d/telemt-web-manager.conf', '/etc/nginx/conf.d/telemt-web-manager-acme.conf',
                '/etc/nginx/stream-sni.d/telemt-web-manager.conf', '/etc/nginx/stream-upstreams.d/telemt-web-manager.conf')
TELEMT_MANIFEST = '/var/lib/telemt-web-manager/manifest.json'
TELEMT_VHOST_DIGESTS = (
    'a35de3320bdd721063a3d13ff7d6ed2ccabd469c57ee10387882c126c42afef5',  # direct
    '8eb4edbb28cbc42d1a3cceb473ad3b36f4dbb26ab11920947f9920adc3c6cb00',  # keepalive
    '9eaf317bae5488e259c1d621d77e6a42d1b2c8c4149de97a519ccadca1981f04',  # site v0.3
)


class Refusal(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def hostname(value):
    require(isinstance(value, str) and value == value.lower() and len(value) <= 253 and '.' in value and
            all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.')),
            'Invalid hostname: use ASCII DNS labels without URL, whitespace or terminal dot.')
    return value


def digest(value):
    return hashlib.sha256(value).hexdigest()


def single(values, reason):
    require(len(values) == 1, reason)
    return values[0]


def edit(text, pattern, replacement, count=1):
    result, found = re.subn(pattern, lambda match: replacement(match), text, flags=re.M)
    require(found == count, 'Unrecognized or ambiguous managed nginx/template directive.')
    return result


def endpoint(value, old, new):
    url = urlsplit(value)
    require(url.scheme == 'https' and url.hostname == old and not url.username and not url.password and
            url.port in (None, 443) and url.path.startswith('/') and not url.fragment and not url.query,
            'Subscription URL is not an unambiguous managed HTTPS endpoint.')
    return urlunsplit((url.scheme, new + (':443' if url.port else ''), url.path, url.query, ''))


def validate_schema(db):
    required = {'settings': {'id', 'key', 'value'}, 'users': {'id', 'username', 'password'},
                'inbounds': {'id', 'protocol', 'listen', 'port', 'settings', 'stream_settings', 'enable', 'node_id'},
                'hosts': {'id', 'group_id', 'inbound_id', 'address', 'port', 'security', 'sni', 'host_header'},
                'clients': {'id', 'sub_id'}, 'client_inbounds': {'client_id', 'inbound_id'}}
    tables = dict(db.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view')"))
    for table, columns in required.items():
        metadata = {r[1]: r[2].upper() for r in db.execute('PRAGMA table_info('+table+')')}
        require(tables.get(table) == 'table' and columns <= metadata.keys(),
                'Unknown SQLite schema; no data changed.')
        for column in columns:
            types = ('INTEGER',) if column in ('id','inbound_id','client_id','port','node_id') else ('NUMERIC','INTEGER') if column=='enable' else ('TEXT',)
            require(metadata[column] in types, 'Unsupported SQLite column type; no data changed.')
    require(not db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name IN ('settings','inbounds','hosts')").fetchone(),
            'Custom triggers on managed SQLite tables are unsupported.')


def hysteria_cover(domain):
    hostname(domain)
    return """# Managed by 3x-ui Auto Nginx: Hysteria2 cover
server {
    listen unix:/run/3x-ui-hysteria-cover.sock;
    server_name %s;
    server_tokens off;
    absolute_redirect off;
    autoindex off;
    root /var/www/html/cover-reality;
    index index.html;
    if ($host !~* ^%s$) { return 404; }
    location / { error_page 404 /404.html; try_files $uri $uri/ =404; }
}
""" % (domain, domain.replace('.',r'\.'))


def database_context(db, panel, reality, manifest=None):
    """Read roles by structure; names/tags alone never establish identity."""
    validate_schema(db)
    require(tuple(db.execute('PRAGMA quick_check').fetchone()) == ('ok',), 'SQLite integrity check failed.')
    pairs = db.execute('SELECT key,value FROM settings').fetchall()
    settings = dict(pairs)
    require(len(settings) == len(pairs), 'Duplicate panel setting keys are ambiguous.')
    for key, file in (('webCertFile', 'fullchain.pem'), ('webKeyFile', 'privkey.pem'),
                      ('subCertFile', 'fullchain.pem'), ('subKeyFile', 'privkey.pem')):
        require(settings.get(key) == '/root/cert/'+panel+'/'+file, 'Panel/subscription TLS paths disagree with the managed domain.')
    require(settings.get('webListen') == settings.get('subListen') == '127.0.0.1', 'Only local HTTPS panel/subscription backends are supported.')
    for key in ('webPort', 'subPort'):
        require(str(settings.get(key, '')).isdigit() and 1024 <= int(settings[key]) <= 65535, 'Invalid managed backend port.')
    require(settings['webPort'] != settings['subPort'], 'Panel and subscription ports conflict.')
    for key in ('webBasePath', 'subPath', 'subJsonPath'):
        require(re.fullmatch(r'/[A-Za-z0-9_-]+/', settings.get(key, '')) is not None, 'Unknown panel/subscription path layout.')
    rows = [dict(row) for row in db.execute('SELECT * FROM inbounds')]
    streams = {}
    for row in rows:
        try:
            streams[row['id']] = json.loads(row['stream_settings'] or '{}')
        except ValueError:
            raise Refusal('Invalid inbound stream JSON; no data changed.') from None
    roles = {}
    def role(name, predicate):
        row = single([r for r in rows if predicate(r, streams[r['id']])], 'Missing or ambiguous inbound role: '+name)
        require(row['node_id'] in (None, 0), 'Remote node inbounds are unsupported.')
        roles[name] = row['id']
        return row, streams[row['id']]
    _, stream = role('reality', lambda r, s: (r['protocol'], r['listen'], r['port']) == ('vless', '127.0.0.1', 8443) and s.get('security') == 'reality')
    require(stream.get('realitySettings', {}).get('serverNames') == [reality] and
            stream['realitySettings'].get('target') == '127.0.0.1:9443', 'REALITY SNI/target differs from the managed topology.')
    role('ws', lambda r, s: r['protocol'] == 'vless' and r['listen'] == '127.0.0.1' and s.get('network') == 'ws' and s.get('security') == 'none')
    role('grpc', lambda r, s: r['protocol'] == 'trojan' and r['listen'] == '127.0.0.1' and s.get('network') == 'grpc' and s.get('security') == 'none')
    role('xhttp', lambda r, s: (r['protocol'], r['listen'], r['port']) == ('vless', '/dev/shm/uds2023.sock,0666', 0) and
         s.get('network') == 'xhttp' and s.get('security') == 'none' and s.get('xhttpSettings', {}).get('mode') == 'stream-up')
    _, hy = role('hysteria2', lambda r, s: r['protocol'] == 'hysteria' and r['listen'] in ('', '0.0.0.0') and r['port'] == 443 and s.get('network') == 'hysteria')
    require(hy.get('hysteriaSettings', {}).get('version') == 2, 'Unknown managed Hysteria2 version.')
    masquerade = hy.get('hysteriaSettings', {}).get('masquerade')
    cover = masquerade is not None
    require(not cover or masquerade == HYSTERIA_MASQUERADE, 'Unknown managed Hysteria2 masquerade.')
    hy_domain = reality if cover else panel
    require(hy.get('tlsSettings', {}).get('serverName') == hy_domain and
            (not cover or hy['tlsSettings'].get('rejectUnknownSni') is True), 'Hysteria2 TLS domain/policy differs from its managed layout.')
    require(hy['tlsSettings'].get('certificates') and len(hy['tlsSettings']['certificates']) == 1, 'Ambiguous Hysteria2 TLS certificates.')
    cert = hy['tlsSettings']['certificates'][0]
    base = '/etc/letsencrypt/live/'+reality if cover else '/root/cert/'+panel
    require(cert.get('certificateFile') == base+'/fullchain.pem' and cert.get('keyFile') == base+'/privkey.pem',
            'Hysteria2 certificate paths differ from its managed layout.')
    vision = None
    candidates = [r for r in rows if r['protocol'] == 'vless' and streams[r['id']].get('security') == 'tls' and r['listen'] == '127.0.0.1']
    if candidates:
        row = single(candidates, 'Ambiguous Vision inbound.')
        vision = hostname(streams[row['id']]['tlsSettings']['serverName'])
        require(vision not in (panel, reality), 'Vision domain conflicts with core domains.')
        roles['vision'] = row['id']
    awg = [r for r in rows if r['protocol'] == 'amneziawg']
    if awg:
        row = single(awg, 'Ambiguous AmneziaWG inbound.')
        require((row['listen'], row['port'], row.get('share_addr_strategy'), row.get('share_addr')) == ('0.0.0.0', 8443, 'custom', panel),
                'Unknown AmneziaWG listener/share address layout.')
        awg_settings = json.loads(row['settings'])
        require(not awg_settings.get('kernelMode', False) and not awg_settings.get('server', {}).get('kernelMode', False),
                'Kernel AmneziaWG is outside Change Domains support.')
        roles['amneziawg'] = row['id']
    cdn = (manifest or {}).get('xhttp_cdn')
    cdn_hosts = []
    if cdn is not None:
        require(type(cdn.get('port')) is int and 1024 <= cdn['port'] <= 65535 and
                re.fullmatch(r'/[A-Za-z0-9]{10,64}/cookie', cdn.get('path', '')),
                'Unknown XHTTP CDN endpoint layout.')
        iid = manifest.get('inbound_roles', {}).get('xhttp_cdn')
        row = single([r for r in rows if r['id'] == iid], 'Missing XHTTP CDN inbound.')
        stream = streams[iid]
        require((row['protocol'], row['listen'], row['port']) == ('vless', '127.0.0.1', cdn['port']) and row['node_id'] in (None, 0) and
                stream.get('network') == 'xhttp' and stream.get('security') == 'none' and
                stream.get('xhttpSettings', {}).get('mode') == 'packet-up' and
                stream['xhttpSettings'].get('path') == cdn['path'], 'XHTTP CDN topology differs from manifest.')
        roles['xhttp_cdn'] = iid
        cdn_hosts = [dict(h) for h in db.execute('SELECT * FROM hosts WHERE inbound_id=?', (iid,))]
    hosts = {}
    for name, iid in roles.items():
        if name in ('amneziawg', 'xhttp_cdn'):
            continue
        address = vision if name == 'vision' else hy_domain if name == 'hysteria2' else panel
        security = 'same' if name in ('reality', 'hysteria2', 'vision') else 'tls'
        hosts[name] = single([dict(h) for h in db.execute('SELECT * FROM hosts WHERE inbound_id=? AND address=? AND port=443 AND security=?',
                                                      (iid, address, security))], 'Missing or ambiguous managed Host: '+name)
    managed_ids = {h['id'] for h in (*hosts.values(), *cdn_hosts)}
    require(all(h['id'] in managed_ids for h in db.execute('SELECT id FROM hosts WHERE address IN (?,?)', (panel, reality if cover else panel))),
            'Additional Hosts depend on Panel; ownership is ambiguous.')
    features = dict(vision=bool(vision), amneziawg=bool(awg))
    if cdn is not None: features['xhttp_cdn'] = True
    return dict(domains=dict(panel=panel, reality=reality, vision=vision), inbound_roles=roles,
                features=features, settings=settings, hosts=hosts, cdn_hosts=cdn_hosts, hysteria_cover=cover,
                rows={r['id']: r for r in rows}, streams=streams)


def database_edits(db, context, panel, reality):
    """Build a finite list of compare-and-set UPDATEs; never create/delete rows."""
    old = context['domains']; edits = []
    def add(table, identity, column, value, paths=None):
        key = 'key' if table == 'settings' else 'id'
        original = single(db.execute('SELECT '+column+' FROM '+table+' WHERE '+key+'=?', (identity,)).fetchall(),
                          'Managed SQLite row is missing or duplicated.')[0]
        if paths:
            args = []
            for path, item in paths:
                args.extend((path, json.dumps(item)))
            value = db.execute('SELECT json_set(?, '+','.join('?,json(?)' for _ in paths)+')', (original, *args)).fetchone()[0]
        if value != original:
            edits.append(dict(table=table, identity=identity, column=column, before=original, after=value, paths=paths))
    if panel != old['panel']:
        for key in ('webCertFile', 'subCertFile', 'webKeyFile', 'subKeyFile'):
            add('settings', key, 'value', '/root/cert/'+panel+'/'+('privkey.pem' if 'Key' in key else 'fullchain.pem'))
        for key in ('subURI', 'subJsonURI'):
            require(key in context['settings'], 'Missing subscription URL setting.')
            add('settings', key, 'value', endpoint(context['settings'][key], old['panel'], panel))
        for key in ('webDomain', 'subDomain'):
            value = context['settings'].get(key, '')
            require(value in ('', old['panel']), 'Custom panel/subscription domain override prevents a safe switch.')
            if value:
                add('settings', key, 'value', panel)
        for name in CORE:
            if name == 'hysteria2' and context['hysteria_cover']: continue
            host = context['hosts'][name]
            for key in ('sni', 'host_header', 'pinned_peer_cert_sha256', 'verify_peer_cert_by_name', 'ech_config_list'):
                require(not host.get(key), 'Managed Host has a custom TLS/SNI/header override; preserved.')
            require(host.get('snis') in (None, '', '[]') and not host.get('override_sni_from_address') and not host.get('keep_sni_blank'),
                    'Managed Host has a custom SNI policy; preserved.')
            add('hosts', host['id'], 'address', panel)
        for name, path in (('ws', '$.wsSettings.host'), ('grpc', '$.grpcSettings.authority')):
            stream = context['streams'][context['inbound_roles'][name]]
            section, field = path[2:].split('.')
            require(stream.get(section, {}).get(field) == old['panel'], 'Custom WS/gRPC domain override prevents a safe switch.')
            add('inbounds', context['inbound_roles'][name], 'stream_settings', None, [(path, panel)])
        cdn = (context.get('manifest') or {}).get('xhttp_cdn')
        if cdn and cdn['host'] in context['cdn_hosts']:
            # Only the exact initial Host is managed. Any user edit preserves it
            # in full; all additional Hosts are left untouched as well.
            add('hosts', cdn['host']['id'], 'address', panel)
            add('hosts', cdn['host']['id'], 'sni', panel)
        if not context['hysteria_cover']:
            add('inbounds', context['inbound_roles']['hysteria2'], 'stream_settings', None,
                [('$.tlsSettings.serverName', panel), ('$.tlsSettings.certificates[0].certificateFile', '/root/cert/'+panel+'/fullchain.pem'),
                 ('$.tlsSettings.certificates[0].keyFile', '/root/cert/'+panel+'/privkey.pem')])
        if context['features']['amneziawg']:
            add('inbounds', context['inbound_roles']['amneziawg'], 'share_addr', panel)
    if reality != old['reality']:
        host = context['hosts']['reality']
        require(not host.get('sni') and host.get('snis') in (None, '', '[]') and not host.get('override_sni_from_address') and not host.get('keep_sni_blank'),
                'REALITY Host has a custom SNI override; preserved.')
        add('inbounds', context['inbound_roles']['reality'], 'stream_settings', None, [('$.realitySettings.serverNames', [reality])])
        if context['hysteria_cover']:
            host = context['hosts']['hysteria2']
            require(not any(host.get(key) for key in ('sni','host_header','pinned_peer_cert_sha256','verify_peer_cert_by_name','ech_config_list')) and
                    host.get('snis') in (None,'','[]') and not host.get('override_sni_from_address') and not host.get('keep_sni_blank'),
                    'Managed Hysteria Host has a custom TLS override; preserved.')
            add('hosts', host['id'], 'address', reality)
            add('inbounds', context['inbound_roles']['hysteria2'], 'stream_settings', None,
                [('$.tlsSettings.serverName', reality), ('$.tlsSettings.certificates[0].certificateFile', '/etc/letsencrypt/live/'+reality+'/fullchain.pem'),
                 ('$.tlsSettings.certificates[0].keyFile', '/etc/letsencrypt/live/'+reality+'/privkey.pem')])
    return edits


class Operation:
    def __init__(self, checks, backup, root=Path('/')):
        self.root = Path(root)
        self.checks, self.backup = str(checks), str(backup)
        self.stage = 'preflight'

    def path(self, name):
        require(isinstance(name, str) and name.startswith('/') and '..' not in Path(name).parts,
                'Invalid managed path; no data changed.')
        return self.root / name.lstrip('/')

    def run(self, *args, timeout=60, inherit_lock=False):
        argv = list(map(str, args))
        if not inherit_lock:
            return subprocess.run(argv, capture_output=True, check=True, timeout=timeout).stdout
        # Let the existing Backup traps resume its services on interruption.
        # Private regular descriptors also survive a killed parent without
        # sending SIGPIPE to the still-running, lock-owning Backup process.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
            with subprocess.Popen(argv, stdout=output, stderr=error, pass_fds=(9,), start_new_session=True) as process:
                try:
                    process.wait(timeout=timeout)
                except BaseException:
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                    try: process.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        process.wait()
                    raise
                output.seek(0); error.seek(0)
                result = output.read()
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, argv, output=result, stderr=error.read())
                return result

    def check(self, action, *args):
        try:
            return self.run('bash', self.checks, action, *args, timeout=120).decode()
        except subprocess.CalledProcessError as error:
            raise Refusal('Managed '+action+' check failed (exit '+str(error.returncode)+').') from None

    def parents(self, name):
        for parent in reversed(self.path(name).parents):
            if parent == self.root.parent or self.root not in (parent, *parent.parents):
                continue
            if parent == self.root:
                continue
            if not parent.exists() and not parent.is_symlink():
                continue
            info = parent.lstat()
            logical = '/'+str(parent.relative_to(self.root))
            owners = (0, 33) if logical.startswith('/var/www') else (0,)
            require(stat.S_ISDIR(info.st_mode) and info.st_uid in owners and not info.st_mode & 0o022,
                    'Unsafe managed parent directory; no data changed.')

    def read(self, name, symlink=None):
        self.parents(name)
        path = self.path(name)
        info = path.lstat()
        if symlink is not None:
            require(stat.S_ISLNK(info.st_mode) and os.readlink(path) == symlink, 'Unexpected managed symlink target.')
            return self.path(symlink).read_text()
        owners = (0, 33) if name in (CLASH, DIAGNOSTICS) else (0,)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid in owners and
                not info.st_mode & 0o022 and info.st_size < (4_000_000 if name == STATE+'/journal.json' else 2_000_000),
                'Unsafe or oversized managed file.')
        return path.read_text()

    def connection(self, readonly=False):
        path = self.path(DB)
        self.parents(DB)
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and not info.st_mode & 0o022,
                'Only an owned local SQLite database is supported.')
        for suffix in ('-wal', '-shm'):
            sidecar = Path(str(path)+suffix)
            if sidecar.exists() or sidecar.is_symlink():
                info = sidecar.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and not info.st_mode & 0o022,
                        'Unsafe SQLite WAL/SHM file; no data changed.')
        db = sqlite3.connect('file:'+quote(str(path))+'?mode='+('ro' if readonly else 'rw'), uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def discover(self, expected=None, ignore_manifest=False):
        hook = self.read(HOOK)
        panel = single(re.findall(r'^PANEL_DOMAIN=([a-z0-9.-]+)$', hook, re.M), 'Unknown project certificate hook.')
        reality = single(re.findall(r'^REALITY_DOMAIN=([a-z0-9.-]+)$', hook, re.M), 'Unknown project certificate hook.')
        hostname(panel); hostname(reality)
        require(panel != reality, 'Panel and REALITY domains conflict.')
        self.check('hook', panel, reality)
        marker = self.path(MANIFEST)
        state = json.loads(self.read(MANIFEST)) if marker.exists() or marker.is_symlink() else None
        with self.connection(True) as db:
            context = database_context(db, panel, reality, state)
        context['features']['adguard'] = self.path(AGH).exists()
        agh_paths = ('/opt/AdGuardHome/AdGuardHome.yaml', '/etc/nginx/snippets/x-ui-auto-optional/adguard.conf',
                     '/usr/local/lib/3x-ui-pro/managed-adguard.sh')
        require(all(self.path(path).exists() == context['features']['adguard'] for path in agh_paths),
                'Incomplete or foreign AdGuard Home layout; no data changed.')
        if context['features']['adguard']:
            require(json.loads(self.read(AGH)).get('domain') == panel, 'AdGuard Home domain disagrees with Panel.')
        if state is not None and not ignore_manifest:
            require(marker.stat().st_uid == 0 and stat.S_IMODE(marker.stat().st_mode) == 0o600,
                    'Manifest must be a private root-owned 0600 file.')
            require(state.get('format') == 1 and state.get('layout') == 'nginx-stream-v1' and
                    (re.fullmatch(r'source@[0-9a-f]{40}', state.get('installed_by', '')) or state.get('installed_by') == 'legacy-v2.1.7-layout') and
                    re.fullmatch(r'[0-9a-f]{40}', state.get('source_ref', '')) and
                    state.get('domains') == context['domains'] and state.get('inbound_roles') == context['inbound_roles'] and
                    state.get('features') == context['features'], 'Manifest conflicts with the running configuration; no data changed.')
        context['manifest'] = state
        if expected:
            require(all(context[key] == expected[key] for key in ('domains', 'inbound_roles', 'features')),
                    'Managed roles changed independently; recovery material retained.')
        self.validate_files(context)
        if expected and 'telemt' in expected:
            require(context['telemt'] == expected['telemt'], 'Telemt nginx integration changed independently; preserved.')
        return context

    def stream_integration(self, context, stream):
        """Recognize only the two agreed Telemt layouts, without editing them.

        Vhost digests pin the three complete render_vhost outputs at TWPM
        3bf3fbea7fa77d662983f102e778a7b16e4a15ee, replacing only domain/site digest.
        The historical direct-vhost/ACME contract stays unchanged.
        The remaining complete stream still has to match our bounded template.
        """
        normalize = lambda value: re.sub(r'\s+', '', re.sub(r'(?m)#.*$', '', value))
        entries = []
        for directory in ('/etc/nginx/stream-sni.d', '/etc/nginx/stream-upstreams.d'):
            path = self.path(directory)
            self.parents(directory+'/telemt-web-manager.conf')
            if os.path.lexists(path):
                require(stat.S_ISDIR(path.lstat().st_mode) and path.stat().st_uid == path.stat().st_gid == 0 and
                        stat.S_IMODE(path.stat().st_mode) == 0o755, 'Unsafe nginx stream include directory.')
                entries += [str(p.relative_to(self.root)) for p in path.iterdir()]
        require(set(entries) <= {name.lstrip('/') for name in TELEMT_FILES[2:]}, 'Unknown additional nginx stream include files.')
        included = bool(entries)
        row = re.findall(r'^    ([a-z0-9.-]+) twm_frontend; # telemt-web-manager\n', stream, re.M)
        backend = '\n# telemt-web-manager\nupstream twm_frontend { server 127.0.0.1:7444; }\n'
        if included:
            require(set(entries) == {name.lstrip('/') for name in TELEMT_FILES[2:]} and not row,
                    'Incomplete or conflicting Telemt include integration.')
            sni = self.read(TELEMT_FILES[2])
            hosts = re.findall(r'^\s*([a-z0-9.-]+)\s+twm_frontend\s*;', re.sub(r'(?m)#.*$', '', sni))
            host = single(hosts, 'Unknown Telemt SNI include.')
            require(normalize(sni) == host+'twm_frontend;' and
                    normalize(self.read(TELEMT_FILES[3])) == 'upstreamtwm_frontend{server127.0.0.1:7444;}',
                    'Changed Telemt stream include objects.')
            require(all(stream.count('include '+name+';') == 1 for name in (SNI_INCLUDE, UPSTREAM_INCLUDE)),
                    'Telemt stream include directives are incomplete or ambiguous.')
        elif row:
            host = single(row, 'Duplicate Telemt SNI rows.')
            literal = f'    {host} twm_frontend; # telemt-web-manager\n'
            require(stream.count('map $ssl_preread_server_name $sni_name {') == 1, 'Unknown Telemt SNI map.')
            opening = stream.index('map $ssl_preread_server_name $sni_name {')
            closing = stream.index('}', opening)
            require(opening < stream.index(literal) < closing and stream.count(backend) == 1 and
                    stream.index(backend) == closing+1, 'Changed legacy Telemt stream fragments.')
            stream = stream.replace(literal, '', 1).replace(backend, '', 1)
        else:
            require(not any(os.path.lexists(self.path(name)) for name in TELEMT_FILES), 'Incomplete Telemt nginx integration.')
            context['telemt'] = None
            return stream
        hostname(host)
        require(host not in context['domains'].values(), 'Telemt SNI conflicts with a managed 3X-UI domain.')
        vhost = self.read(TELEMT_FILES[0])
        require('{domain}' not in vhost and '{site_digest}' not in vhost, 'Unexpanded Telemt HTTPS vhost markers.')
        canonical = re.sub(r'(?m)^(# TWPM original site v0\.3 sha256: )[0-9a-f]{64}$',
                           r'\1{site_digest}', vhost.replace(host, '{domain}'))
        canonical = re.sub(r'(?m)^    listen 127\.0\.0\.1:(?:1808[1-9]|18090);$',
                           '    listen 127.0.0.1:18081;', canonical)
        vhost_digest = digest(canonical.encode())
        require(vhost_digest in TELEMT_VHOST_DIGESTS, 'Changed or inconsistent Telemt HTTPS vhost.')
        paths = [TELEMT_FILES[0]] + (list(TELEMT_FILES[2:]) if included else [])
        if vhost_digest != TELEMT_VHOST_DIGESTS[0]:
            # New layouts bind the variable site identity to the live manifest.
            # Guard it read-only; never add it to scoped recovery writes.
            require(os.path.lexists(self.path(TELEMT_MANIFEST)), 'Missing Telemt manifest for the new vhost.')
            state = json.loads(self.read(TELEMT_MANIFEST))
            marker = self.path(TELEMT_MANIFEST)
            require(stat.S_IMODE(marker.stat().st_mode) == 0o600 and stat.S_IMODE(marker.parent.stat().st_mode) == 0o700,
                    'Unsafe Telemt manifest permissions.')
            require(isinstance(state, dict) and type(state.get('schema')) is int and state['schema'] == 1 and
                    state.get('domain') == host and state.get('nginx_sha256') == digest(vhost.encode()),
                    'Telemt manifest and HTTPS vhost disagree.')
            paths.append(TELEMT_MANIFEST)
        if os.path.lexists(self.path(TELEMT_FILES[1])):
            require(digest(self.read(TELEMT_FILES[1]).replace(host, '{domain}').encode()) ==
                    '787a182c26bb2d5b335b5a62573a56df524f2f24f35c303b17ab7eab9f4d7035', 'Changed Telemt ACME vhost.')
            paths.append(TELEMT_FILES[1])
        main = re.sub(r'(?m)#.*$', '', self.read('/etc/nginx/nginx.conf'))
        require(main.count('include /etc/nginx/conf.d/*.conf;') == 1, 'Telemt vhosts are not included through the known HTTP contract.')
        context['telemt'] = dict(domain=host, files={name:self.guard_value(name) for name in paths},
                                 layout='include' if included else 'inline')
        return stream

    def validate_files(self, context):
        cdn = (context.get('manifest') or {}).get('xhttp_cdn')
        if cdn:
            route = self.read('/etc/nginx/snippets/x-ui-auto-optional/xhttp-cdn.conf')
            require(route == cdn['snippet'] and
                    re.findall(r'proxy_pass http://127\.0\.0\.1:([0-9]+);', route) == [str(cdn['port'])] and
                    re.findall(r'location (?:=|\^~) (\S+) \{', route) == [cdn['path'], cdn['path']+'/'],
                    'XHTTP CDN nginx route differs from its managed snapshot.')
        domains = context['domains']; panel, reality, vision = (domains[k] for k in ('panel', 'reality', 'vision'))
        stream = self.stream_integration(context, self.read(STREAM))
        expected = ('map_hash_bucket_size 272;map $ssl_preread_server_name $sni_name {hostnames;' +
                    (vision+' vision;' if vision else '') + reality+' xray;'+panel+' www;SNI_INCLUDEdefault xray;}' +
                    'upstream xray { server 127.0.0.1:8443; }upstream www { server 127.0.0.1:7443; }' +
                    'UPSTREAM_INCLUDEserver {proxy_protocol on;set_real_ip_from unix:;listen 443;IPV6proxy_pass $sni_name;ssl_preread on;}')
        normalize = lambda text: re.sub(r'\s+', '', re.sub(r'(?m)#.*$', '', text))
        if vision:
            row = context['rows'][context['inbound_roles']['vision']]
            expected += 'upstream vision { server 127.0.0.1:'+str(row['port'])+'; }'
        layouts = (('', ''), ('include '+SNI_INCLUDE+';', 'include '+UPSTREAM_INCLUDE+';'))
        if (context['telemt'] or {}).get('layout') == 'include':
            layouts = layouts[1:]  # Files alone never prove an active include route.
        if context['hysteria_cover']:
            require(context['streams'][context['inbound_roles']['reality']]['realitySettings'].get('xver') == 1, 'Backup upstream requires REALITY PROXY v1.')
            expected = expected.replace('upstream xray { server 127.0.0.1:8443; }', 'upstream xray { server 127.0.0.1:8443 max_fails=0; server 127.0.0.1:9443 backup; }')
            require(self.read(HYSTERIA) == hysteria_cover(reality), 'Unknown Hysteria2 static backend.')
            self.read(HYSTERIA_ENABLED, HYSTERIA)
        else:
            require(self.object(HYSTERIA)['kind'] == self.object(HYSTERIA_ENABLED)['kind'] == 'absent', 'Unexpected Hysteria2 static backend.')
        variants = [expected.replace('SNI_INCLUDE', sni).replace('UPSTREAM_INCLUDE', upstream).replace('IPV6', ipv6)
                    for sni, upstream in layouts
                    for ipv6 in ('', 'listen [::]:443;')]
        require(normalize(stream) in list(map(normalize, variants)),
                'Unknown nginx stream layout; Vision and other routes were preserved.')
        require(list(self.path('/etc/nginx/stream-enabled').iterdir()) == [self.path(STREAM)], 'Unknown additional nginx stream files.')
        shared = self.read('/etc/nginx/snippets/includes.conf')
        settings = context['settings']
        subpath, jsonpath = settings['subPath'].strip('/'), settings['subJsonPath'].strip('/')
        expected_locations = ('/'+subpath+'/', '= /'+subpath, '~ ^/'+subpath+'/(?<clash_sub_id>[^/]+)$',
                              '/'+jsonpath, '/'+jsonpath+'/')
        assets = ''.join('location '+name+' { proxy_pass https://127.0.0.1:'+settings['subPort']+'; }'
                         for name in ('/assets','/assets/'))
        legacy_assets = normalize(assets) in normalize(shared)
        require(shared.count('proxy_pass https://127.0.0.1:'+settings['subPort']+';') == (7 if legacy_assets else 5) and
                all('location '+name+' {' in shared or 'location '+name+'  {' in shared for name in expected_locations),
                'Subscription paths/TLS backend do not match nginx.')
        if not legacy_assets:
            require('location /assets' not in shared and
                    normalize(assets) in normalize(self.read('/etc/nginx/sites-available/'+panel)) and
                    'location /assets' not in self.read('/etc/nginx/sites-available/'+reality),
                    'Unknown native subscription asset ownership.')
        xhttp = context['streams'][context['inbound_roles']['xhttp']].get('xhttpSettings', {}).get('path', '')
        require(re.fullmatch(r'/[A-Za-z0-9_-]+', xhttp) is not None and 'location ^~ '+xhttp+'/ {' in shared and
                shared.count('grpc_pass unix:/dev/shm/uds2023.sock;') == 1, 'XHTTP path/socket does not match nginx.')
        for name in ('ws', 'grpc'):
            row = context['rows'][context['inbound_roles'][name]]; stream = context['streams'][row['id']]
            if name == 'ws':
                route = stream.get('wsSettings', {}).get('path')
                require(isinstance(route, str) and re.fullmatch('/'+str(row['port'])+r'/[A-Za-z0-9_-]+', route) is not None and
                        'location = '+route+' {' in shared and 'proxy_pass http://127.0.0.1:'+str(row['port'])+';' in shared,
                        'WS path/port does not match the managed nginx location.')
            else:
                route = stream.get('grpcSettings', {}).get('serviceName', '').split('|')[0]
                require(re.fullmatch('/'+str(row['port'])+r'/[A-Za-z0-9_-]+', route) is not None and
                        'location = '+route+' {' in shared and 'grpc_pass grpc://127.0.0.1:'+str(row['port'])+';' in shared,
                        'gRPC method/port does not match the managed nginx location.')
        for name in (panel, reality):
            text = self.read('/etc/nginx/sites-available/'+name)
            self.read('/etc/nginx/sites-enabled/'+name, '/etc/nginx/sites-available/'+name)
            self.vhost(text, name, name)
            require(('listen 127.0.0.1:7443 ssl' if name == panel else 'listen 127.0.0.1:9443 ssl') in text,
                    'Unknown Panel/REALITY TLS listener.')
            if name == panel:
                for path in (settings['webBasePath'], settings['webBasePath'].rstrip('/')):
                    block = single(re.findall(r'\blocation '+re.escape(path)+r'\s*\{([^{}]*)\}', text), 'Ambiguous managed Panel location.')
                    require('proxy_pass https://127.0.0.1:'+settings['webPort']+';' in block and 'proxy_set_header Host $host;' in block,
                            'Panel path/TLS backend does not match nginx.')
            else:
                xver = context['streams'][context['inbound_roles']['reality']]['realitySettings'].get('xver', 0)
                require(type(xver) is int and xver in (0, 1), 'Unknown REALITY fallback PROXY contract.')
                require(('proxy_protocol' in single(re.findall(r'^\s*listen 127\.0\.0\.1:9443 ([^;]+);', text, re.M),
                                                    'Unknown REALITY fallback listener.')) == bool(xver),
                        'REALITY inbound/fallback PROXY contracts disagree.')
                if xver:
                    require(re.findall(r'^\s*real_ip_header\s+([^;]+);', text, re.M) == ['proxy_protocol'] and
                            re.findall(r'^\s*set_real_ip_from\s+([^;]+);', text, re.M) == ['127.0.0.1'],
                            'Unknown REALITY fallback PROXY trust boundary.')
            self.check('lineage', name)
        for file in ('fullchain.pem', 'privkey.pem'):
            self.read('/root/cert/'+panel+'/'+file, '/etc/letsencrypt/live/'+panel+'/'+file)
        main = self.read('/etc/nginx/nginx.conf')
        require(main.count('stream { include /etc/nginx/stream-enabled/*.conf; }') == 1 and
                'include /etc/nginx/sites-enabled/*;' in main, 'Unknown main nginx include layout.')
        self.read('/etc/nginx/sites-enabled/80.conf', '/etc/nginx/sites-available/80.conf')
        names = self.http_names(self.read(HTTP))
        # HTTP-01 preparation temporarily includes both original and proposed names.
        # file_plan retains the existing ownership check before preparing that change.
        require({panel,reality} <= set(names), 'Missing active names in the project HTTP-01 vhost.')
        if vision:
            for file in ('/etc/nginx/sites-available/vision.conf', '/etc/nginx/sites-available/vision-acme.conf',
                         '/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision'):
                require(vision in self.read(file), 'Vision artifacts disagree with its inbound/domain.')
            for name in ('vision.conf', 'vision-acme.conf'):
                self.read('/etc/nginx/sites-enabled/'+name, '/etc/nginx/sites-available/'+name)

    @staticmethod
    def http_names(text):
        names = single(re.findall(r'^    server_name ([a-z0-9. -]+);$', text, re.M), 'Unknown HTTP-01 server names.').split()
        guards = re.findall(r'^    if \(\$host[^\n]*$', text, re.M)
        tokens = re.findall(r'^\s*server_tokens\s+([^;]+);', text, re.M)
        if guards or tokens:
            expected = '    if ($host !~* ^('+'|'.join(name.replace('.',r'\.') for name in names)+')$) { return 404; }'
            require(guards == [expected] and tokens == ['off'], 'Unknown HTTP-01 Host guard.')
        return names

    @staticmethod
    def vhost(text, old, new):
        # Exactly one of the two installer-emitted Host/SNI contracts, never a generic regex editor.
        normalize = lambda line: re.sub(r'\s+', '', line)
        escaped = old.replace('.', r'\.')
        guards = [normalize(line) for line in text.splitlines()
                  if re.match(r'\s*if \(\$(host|ssl_server_name|scheme|safe)\b', line)]
        legacy = [f'if ($host !~* ^(.+\\.)?{old}$) {{ return 444; }}',
                  'if ($scheme ~* https) { set $safe 1; }',
                  f'if ($ssl_server_name !~* ^(.+\\.)?{old}$) {{ set $safe "${{safe}}0"; }}',
                  'if ($safe = 10) { return 444; }']
        modern = [f'if ($host !~* ^{escaped}$) {{ return 404; }}',
                  f'if ($ssl_server_name !~* ^{escaped}$) {{ return 421; }}']
        old_layout = guards == list(map(normalize, legacy))
        require((old_layout and text.count(old) == 5) or
                (guards == list(map(normalize, modern)) and text.count(old) == 3 and text.count(escaped) == 2),
                'Custom domain-bearing nginx directives prevent an unambiguous switch.')
        substitutions = [
            (r'^(\s*server_name )'+re.escape(old)+r'(;)$', lambda m: m[1]+new+m[2]),
            (r'^(\s*ssl_certificate\s+)/etc/letsencrypt/live/'+re.escape(old)+r'/fullchain.pem;$', lambda m: m[1]+'/etc/letsencrypt/live/'+new+'/fullchain.pem;'),
            (r'^(\s*ssl_certificate_key\s+)/etc/letsencrypt/live/'+re.escape(old)+r'/privkey.pem;$', lambda m: m[1]+'/etc/letsencrypt/live/'+new+'/privkey.pem;')]
        for variable in ('host','ssl_server_name'):
            prefix = r'\^\(\.\+\\\.\)\?' if old_layout else r'\^'
            previous, replacement = (old,new) if old_layout else (escaped,new.replace('.',r'\.'))
            substitutions.append((r'^(\s*if \(\$'+variable+r' !~\* '+prefix+')'+re.escape(previous)+r'(\$\).*)$',
                                  lambda m, value=replacement: m[1]+value+m[2]))
        for pattern, replacement in substitutions:
            text = edit(text, pattern, replacement)
        return text

    def object(self, name):
        self.parents(name)
        path = self.path(name)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return dict(kind='absent')
        require(info.st_uid in ((0, 33) if name in (CLASH, DIAGNOSTICS) else (0,)), 'Foreign resource owner; no data changed.')
        value = dict(uid=info.st_uid, gid=info.st_gid, mode=stat.S_IMODE(info.st_mode), mtime=info.st_mtime_ns)
        if stat.S_ISLNK(info.st_mode):
            value.update(kind='link', data=os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            require(not info.st_mode & 0o022, 'Writable managed certificate directory.')
            value.update(kind='directory')
        else:
            self.read(name)
            value.update(kind='file', data=base64.b64encode(path.read_bytes()).decode())
        return value

    @staticmethod
    def same(left, right):
        return {k: v for k, v in left.items() if k != 'mtime'} == {k: v for k, v in right.items() if k != 'mtime'}

    def put(self, name, value):
        self.parents(name)
        path = self.path(name)
        if value['kind'] == 'absent':
            if path.is_dir() and not path.is_symlink():
                path.rmdir()  # Never recursively delete independently added files.
            else:
                path.unlink(missing_ok=True)
        elif value['kind'] == 'directory':
            path.mkdir(mode=value['mode'], exist_ok=True)
            os.chown(path, value['uid'], value['gid']); os.chmod(path, value['mode'])
        else:
            fd, temporary = tempfile.mkstemp(prefix='.domains-', dir=path.parent)
            try:
                if value['kind'] == 'link':
                    os.close(fd); os.unlink(temporary); os.symlink(value['data'], temporary)
                    os.chown(temporary, value['uid'], value['gid'], follow_symlinks=False)
                else:
                    with os.fdopen(fd, 'wb') as out:
                        os.fchmod(out.fileno(), value['mode']); os.fchown(out.fileno(), value['uid'], value['gid'])
                        out.write(base64.b64decode(value['data'], validate=True)); out.flush(); os.fsync(out.fileno())
                os.replace(temporary, path)
                os.utime(path, ns=(value['mtime'], value['mtime']), follow_symlinks=False)
            finally:
                if os.path.lexists(temporary):
                    os.unlink(temporary)
        self.sync(path.parent)

    @staticmethod
    def sync(directory):
        fd = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def journal(self, record):
        directory = self.path(STATE)
        for parent in (directory.parent, directory):
            if not parent.exists():
                parent.mkdir(mode=0o700)
                self.sync(parent.parent)
            require(not parent.is_symlink() and parent.stat().st_uid == 0 and stat.S_IMODE(parent.stat().st_mode) == 0o700,
                    'Unsafe Change Domains recovery directory.')
        target = STATE+'/journal.json'
        data = json.dumps(record, ensure_ascii=True, separators=(',', ':')).encode()+b'\n'
        require(len(data) < 4_000_000, 'Domain snapshot exceeds its bounded size.')
        self.put(target, dict(kind='file', uid=0, gid=0, mode=0o600, mtime=time.time_ns(), data=base64.b64encode(data).decode()))

    def finish(self):
        self.path(STATE+'/journal.json').unlink()
        self.sync(self.path(STATE))

    def panel_version(self):
        self.parents('/usr/local/x-ui'); self.parents('/usr/bin/x-ui')
        archive_owner = False
        for file in ('/usr/local/x-ui', '/usr/local/x-ui/x-ui', '/usr/bin/x-ui'):
            info = self.path(file).lstat()
            require((stat.S_ISDIR(info.st_mode) if file == '/usr/local/x-ui' else stat.S_ISREG(info.st_mode)) and not info.st_mode & 0o022,
                    'Unknown panel binary/CLI ownership or layout.')
            if info.st_uid == 0:continue
            # The verified official archives preserve runner UID/GID 1001.
            # Admit that exact metadata only while the identity is unassigned;
            # a real local account/process would make the binary foreign-owned.
            require(file != '/usr/bin/x-ui' and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)) == (1001,1001,0o755),
                    'Unknown panel binary/CLI ownership or layout.')
            archive_owner = True
        if archive_owner:
            try: pwd.getpwuid(1001)
            except KeyError: pass
            else: raise Refusal('Official archive UID 1001 belongs to a local account; owner verification refused.')
            for path in self.path('/proc').glob('[0-9]*/status'):
                try: status = path.read_text()
                except FileNotFoundError: continue
                owners = re.search(r'^Uid:\s+([^\n]+)',status,re.M)
                require(owners is not None and '1001' not in owners[1].split(),
                        'Official archive UID 1001 is active or cannot be verified; owner verification refused.')
        version = self.run(self.path('/usr/local/x-ui/x-ui'), '-v').decode().strip()
        require(version in ('3.10.2', '3.11.0'), 'Change Domains supports the verified 3.10.2/3.11.0 SQLite layouts only.')
        return version

    def version_and_layout(self):
        os_release = dict(re.findall(r'^(ID|VERSION_ID)="?([A-Za-z0-9.]+)"?$', self.path('/etc/os-release').read_text(), re.M))
        require((os_release.get('ID'), os_release.get('VERSION_ID')) in (('ubuntu', '24.04'), ('ubuntu', '26.04'), ('debian', '13')),
                'Unsupported OS for Change Domains.')
        version = self.panel_version()
        unit = self.read('/etc/systemd/system/x-ui.service')
        require(re.findall(r'^ExecStart=(.*)$', unit, re.M) == ['/usr/local/x-ui/x-ui'] and
                re.findall(r'^WorkingDirectory=(.*)$', unit, re.M) == ['/usr/local/x-ui/'], 'Unknown x-ui service layout.')
        require(all(value == '-/etc/default/x-ui' for value in re.findall(r'^EnvironmentFile=(.*)$', unit, re.M)) and
                not re.search(r'^Environment=.*\bXUI_', unit, re.M), 'Unsupported x-ui service environment override.')
        require(self.run('systemctl', 'show', 'x-ui', '-p', 'FragmentPath', '--value').decode().strip() == '/etc/systemd/system/x-ui.service' and
                not self.run('systemctl', 'show', 'x-ui', '-p', 'DropInPaths', '--value').strip(),
                'Unsupported x-ui unit override/relocated service.')
        pid = self.run('systemctl', 'show', 'x-ui', '-p', 'MainPID', '--value').decode().strip()
        require(pid.isdigit() and int(pid) > 0 and self.path('/proc/'+pid+'/exe').resolve() == self.path('/usr/local/x-ui/x-ui').resolve(),
                'The active panel executable is not the managed local binary.')
        environment = self.path('/proc/'+pid+'/environ').read_bytes()
        require(len(environment) < 1_000_000, 'Unexpected panel process environment size.')
        allowed_environment = {'XUI_DB_FOLDER': '/etc/x-ui', 'XUI_BIN_FOLDER': '/usr/local/x-ui/bin',
                               'XUI_LOG_FOLDER': '/var/log/x-ui', 'XUI_DB_TYPE': 'sqlite'}
        for value in environment.split(b'\0'):
            if value.startswith(b'XUI_'):
                key, _, content = value.decode().partition('=')
                require(key in allowed_environment and content == allowed_environment[key], 'Running panel uses nonstandard storage/environment.')
        if self.path('/etc/default/x-ui').exists():
            env = self.read('/etc/default/x-ui')
            for key, value in re.findall(r'^(XUI_[A-Z_]+)=["\']?([^"\'\n]*)["\']?$', env, re.M):
                expected = {'XUI_DB_FOLDER': '/etc/x-ui', 'XUI_BIN_FOLDER': '/usr/local/x-ui/bin',
                            'XUI_LOG_FOLDER': '/var/log/x-ui', 'XUI_DB_TYPE': 'sqlite'}
                require(key in expected and value == expected[key], 'Nonstandard panel storage environment; no data changed.')
        return version

    def healthy(self, context, ignore_manifest=False):
        panel, reality = (context['domains'][k] for k in ('panel', 'reality'))
        current = self.discover(context, ignore_manifest)
        self.check('health', panel, reality)
        if context['features']['adguard']:
            self.check('adguard')
        if context['features']['amneziawg']:
            self.check('amneziawg')
        self.https_checks(current)

    def service_states(self, context):
        units = ['x-ui', 'nginx', 'mtr-backend', 'certbot.timer']
        if context['features']['adguard']:
            units.append('AdGuardHome')
        result = {}
        for unit in units:
            values = dict(line.split('=', 1) for line in self.run('systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'UnitFileState').decode().splitlines() if '=' in line)
            require(values.get('ActiveState') == 'active' and values.get('UnitFileState') in ('enabled', 'disabled', 'static', 'indirect', 'enabled-runtime'),
                    'Required service is inactive, masked or in an unknown state.')
            result[unit] = values
        return result

    def request(self, name, path, cafile, method='GET', headers=None, body=None):
        # Connect through the actual SNI stream while verifying this exact domain.
        context = ssl.create_default_context(cafile=str(self.path(cafile)))
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        context.set_alpn_protocols(['http/1.1'])
        connection = http.client.HTTPConnection('127.0.0.1', 443, timeout=10)
        connection.sock = context.wrap_socket(socket.create_connection(('127.0.0.1', 443), timeout=10), server_hostname=name)
        try:
            connection.request(method, path, body=body, headers={'Host': name, **(headers or {})})
            response = connection.getresponse()
            data = response.read(4_000_001)
            require(len(data) <= 4_000_000, 'Unexpected oversized managed HTTPS response.')
            return response.status, data
        finally:
            connection.close()

    def https_checks(self, context):
        panel, reality = (context['domains'][k] for k in ('panel', 'reality'))
        cert = '/etc/letsencrypt/live/'+panel+'/fullchain.pem'
        with self.connection(True) as db:
            settings = dict(db.execute('SELECT key,value FROM settings'))
            def active_clients(protocols):
                query = ("SELECT DISTINCT c.sub_id FROM clients c JOIN client_inbounds ci ON ci.client_id=c.id "
                         "JOIN inbounds i ON i.id=ci.inbound_id WHERE c.enable=1 AND i.enable=1 AND c.sub_id<>'' "
                         "AND i.protocol IN ("+','.join('?' for _ in protocols)+") ORDER BY c.id LIMIT 1")
                return db.execute(query, protocols).fetchall()
            clients = active_clients(('vless','trojan','hysteria','amneziawg'))
            json_clients = active_clients(('vless','trojan','hysteria'))
        pid = self.run('systemctl', 'show', 'x-ui', '-p', 'MainPID', '--value').decode().strip()
        listeners = self.run('ss', '-H', '-lntp').decode().splitlines()
        for key in ('webPort', 'subPort'):
            owners = {owner for line in listeners if len(line.split()) > 3 and line.split()[3] == '127.0.0.1:'+settings[key]
                      for owner in re.findall(r'pid=(\d+)', line)}
            require(owners == {pid}, 'Panel/subscription HTTPS listeners are not owned by the active panel.')
        require(self.request(panel, settings['webBasePath'], cert)[0] in (200, 302), 'Panel HTTPS is unavailable.')
        if context['hysteria_cover'] or context['rows'][context['inbound_roles']['reality']]['enable']:
            require(self.request(reality, '/', '/etc/letsencrypt/live/'+reality+'/fullchain.pem')[0] == 200,
                    'REALITY TLS camouflage endpoint is unavailable.')
        vision = context['domains']['vision']
        if vision:
            require(self.request(vision, '/', '/etc/letsencrypt/live/'+vision+'/fullchain.pem')[0] == 200, 'Existing Vision TLS fallback is unavailable.')
        for key in ('subURI', 'subJsonURI'):
            url = urlsplit(settings[key])
            require(url.hostname == panel, 'Subscription URL domain is inconsistent.')
            selected = json_clients if key == 'subJsonURI' else clients
            path = url.path+(quote(selected[0][0], safe='') if selected else 'xui-domains-health-invalid-id')
            code, body = self.request(panel, path, cert, headers={'User-Agent': 'x-ui-domain-health', 'Accept': 'application/json'})
            enabled = settings.get('subEnable' if key == 'subURI' else 'subJsonEnable', 'true') == 'true'
            if not selected or not enabled:
                require(code in (400, 404), 'Subscription backend did not reject an unknown client.')
            elif key == 'subJsonURI':
                configs = json.loads(body) if code == 200 else None
                if isinstance(configs, dict): configs = [configs]
                require(isinstance(configs, list) and configs and
                        all(isinstance(item, dict) and isinstance(item.get('outbounds'), list) and item['outbounds'] for item in configs),
                        'JSON subscription validation failed.')
            else:
                require(code == 200, 'RAW subscription validation failed.')
                base64.b64decode(b''.join(body.split()), validate=True)
        if clients and settings.get('subEnable', 'true') == 'true':
            code, body = self.request(panel, settings['subPath']+quote(clients[0][0], safe=''), cert,
                                      headers={'User-Agent': 'mihomo'})
            require(code == 200 and b'proxy-providers:' in body and ('https://'+panel+'/').encode() in body,
                    'Managed Clash/Mihomo subscription validation failed.')

    def target_preflight(self, context, panel, reality):
        old = context['domains']
        hostname(panel); hostname(reality)
        require(panel != reality and old['vision'] not in (panel, reality), 'New domains conflict with each other or Vision.')
        require(panel != old['reality'] and reality != old['panel'], 'Panel/REALITY role exchange is unsupported; choose distinct new domains.')
        require((panel, reality) != (old['panel'], old['reality']), 'Domains are unchanged; no operation is necessary.')
        require(not context.get('telemt') or context['telemt']['domain'] not in (panel, reality),
                'New domain conflicts with the Telemt SNI route; no data changed.')
        history = (context['manifest'] or {}).get('retained_domains', {})
        require(isinstance(history, dict), 'Invalid retained domain ownership metadata.')
        effective = self.run('nginx', '-T').decode()
        for file, text in re.findall(r'^# configuration file ([^\n]+):\n(.*?)(?=^# configuration file |\Z)', effective, re.M | re.S):
            for names in re.findall(r'\bserver_name\s+([^;]+);', re.sub(r'(?m)#.*$', '', text)):
                for name in names.split():
                    name = name.strip('"\'')
                    for target, previous in ((panel, old['panel']), (reality, old['reality'])):
                        if target == previous or (file in ('/etc/nginx/sites-enabled/80.conf','/etc/nginx/sites-available/80.conf') and target in history):
                            continue
                        require(not name.startswith('~') and '$' not in name and name != target and not
                                (name.startswith('*.') and target.endswith(name[1:])) and not
                                (name.startswith('.') and (target == name[1:] or target.endswith(name))),
                                'New domain conflicts with an existing nginx server name; no data changed.')
        for value, previous in ((panel, old['panel']), (reality, old['reality'])):
            if value == previous:
                continue
            self.account(previous)
            for directory in ('/etc/nginx/sites-available/', '/etc/nginx/sites-enabled/'):
                require(not os.path.lexists(self.path(directory+value)), 'New domain already owns an nginx resource; no data changed.')
            lineage = self.path('/etc/letsencrypt/renewal/'+value+'.conf')
            existing = any(os.path.lexists(self.path(p+value)) for p in ('/etc/letsencrypt/live/', '/etc/letsencrypt/archive/')) or lineage.exists()
            for folder in ('live', 'archive', 'renewal'):
                require(not list(self.path('/etc/letsencrypt/'+folder).glob(value+'-*')), 'Ambiguous certificate lineage.')
            if existing:
                require(value in history and lineage.is_file() and digest(lineage.read_bytes()) == history[value],
                        'Existing certificate lineage has no matching managed ownership record; preserved.')
                self.check('lineage', value)
            certdir = self.path('/root/cert/'+value)
            require(not os.path.lexists(certdir) or value in history, 'Existing certificate link directory is not owned by this operation.')
        # Reuse the current working public DNS identity (including NAT), without
        # changing addresses or routing. ACME independently validates HTTP-01.
        try:
            known = {str(ipaddress.ip_address(r[4][0])) for name in (old['panel'], old['reality'])
                     for r in socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)}
            for name, previous in ((panel, old['panel']), (reality, old['reality'])):
                if name != previous:
                    addresses = {str(ipaddress.ip_address(r[4][0])) for r in socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)}
                    require(bool(addresses) and addresses <= known, 'New domain DNS does not match the current VPS identity; fix A/AAAA records first.')
        except socket.gaierror:
            raise Refusal('Current/new domain DNS lookup failed; check A/AAAA records before retrying.') from None

    def file_plan(self, context, panel, reality, source):
        old = context['domains']; files = []
        def add(path, value):
            before = self.object(path)
            after = copy.deepcopy(before)
            if value is None:
                after = dict(kind='absent')
            elif isinstance(value, str):
                require(before['kind'] == 'file', 'Expected an existing managed text file.')
                after['data'] = base64.b64encode(value.encode()).decode()
            else:
                after = value
            if not self.same(before, after):
                files.append(dict(path=path, before=before, after=after))
        stream = self.read(STREAM)
        for previous, value, backend in ((old['panel'], panel, 'www'), (old['reality'], reality, 'xray')):
            if value != previous:
                stream = edit(stream, r'^(\s*)'+re.escape(previous)+r'(\s+'+backend+r';)$', lambda m: m[1]+value+m[2])
                original = '/etc/nginx/sites-available/'+previous
                transformed = self.vhost(self.read(original), previous, value)
                new = '/etc/nginx/sites-available/'+value
                metadata = self.object(original); metadata['data'] = base64.b64encode(transformed.encode()).decode()
                add(new, metadata); add(original, None)
                add('/etc/nginx/sites-enabled/'+value, dict(kind='link', uid=0, gid=0, mode=0o777, mtime=time.time_ns(), data=new))
                add('/etc/nginx/sites-enabled/'+previous, None)
        add(STREAM, stream)
        if context['hysteria_cover']:
            add(HYSTERIA, hysteria_cover(reality))
        http = self.read(HTTP)
        names = self.http_names(http)
        allowed = {old['panel'], old['reality'], *((context['manifest'] or {}).get('retained_domains', {}))}
        require(set(names) <= allowed and {old['panel'], old['reality']} <= set(names), 'Unknown names in the project HTTP-01 vhost.')
        updated_names = list(dict.fromkeys([*names, panel, reality]))
        if re.search(r'^    if \(\$host', http, re.M):
            before = '    if ($host !~* ^('+'|'.join(name.replace('.',r'\.') for name in names)+')$) { return 404; }'
            after = '    if ($host !~* ^('+'|'.join(name.replace('.',r'\.') for name in updated_names)+')$) { return 404; }'
            http = edit(http, '^'+re.escape(before)+'$', lambda m: after)
        add(HTTP, edit(http, r'^    server_name [a-z0-9. -]+;$', lambda m: '    server_name '+' '.join(updated_names)+';'))
        add(HOOK, self.check('render-hook', panel, reality))
        if panel != old['panel']:
            directory = '/root/cert/'+panel
            if self.object(directory)['kind'] == 'absent':
                add(directory, dict(kind='directory', uid=0, gid=0, mode=0o755, mtime=time.time_ns()))
            for name in ('fullchain.pem', 'privkey.pem'):
                add(directory+'/'+name, dict(kind='link', uid=0, gid=0, mode=0o777, mtime=time.time_ns(), data='/etc/letsencrypt/live/'+panel+'/'+name))
            template = self.read(CLASH)
            url = 'https://'+old['panel']+context['settings']['subPath']+'${SUB_ID}?provider=1'
            add(CLASH, edit(template, r'^(    url: )'+re.escape(url)+r'$', lambda m: m[1]+'https://'+panel+context['settings']['subPath']+'${SUB_ID}?provider=1'))
            html = self.read(DIAGNOSTICS)
            add(DIAGNOSTICS, edit(html, re.escape('<span class="mono">'+old['panel']+'</span>'), lambda m: '<span class="mono">'+panel+'</span>'))
            if context['features']['adguard']:
                agh = json.loads(self.read(AGH)); agh['domain'] = panel
                add(AGH, json.dumps(agh, ensure_ascii=True)+'\n')
        marker = copy.deepcopy(context['manifest']) if context['manifest'] else dict(format=1, layout='nginx-stream-v1',
                   installed_by='legacy-v2.1.7-layout', source_ref=source, inbound_roles=context['inbound_roles'], features=context['features'])
        marker['domains'] = dict(panel=panel, reality=reality, vision=old['vision'])
        cdn = marker.get('xhttp_cdn')
        if cdn and panel != old['panel'] and cdn['host'] in context['cdn_hosts']:
            cdn['host'].update(address=panel, sni=panel)
        marker['domain_change_source'] = source
        history = marker.setdefault('retained_domains', {})
        for name in (old['panel'], old['reality']):
            history[name] = digest(self.path('/etc/letsencrypt/renewal/'+name+'.conf').read_bytes())
        if context['manifest']:
            add(MANIFEST, json.dumps(marker, ensure_ascii=True)+'\n')
        else:
            add(MANIFEST, dict(kind='file', uid=0, gid=0, mode=0o600, mtime=time.time_ns(), data=base64.b64encode((json.dumps(marker)+'\n').encode()).decode()))
        return files, marker

    def certificate(self, name):
        self.check('lineage', name)
        directory = '/etc/letsencrypt/live/'+name
        for folder in (directory, '/etc/letsencrypt/archive/'+name):
            info = self.path(folder).lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022, 'Unknown certificate directory ownership/layout.')
        for file in ('fullchain.pem', 'privkey.pem'):
            path = self.path(directory+'/'+file)
            require(path.resolve(strict=True).is_relative_to(self.path('/etc/letsencrypt/archive/'+name)),
                    'Certificate symlink leaves its exact managed archive directory.')
            info = path.stat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1 and not info.st_mode & 0o022,
                    'Unsafe managed certificate/key file.')
        leaf = x509.load_pem_x509_certificate(self.path(directory+'/fullchain.pem').read_bytes())
        key = serialization.load_pem_private_key(self.path(directory+'/privkey.pem').read_bytes(), password=None)
        public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        before = getattr(leaf, 'not_valid_before_utc', None)
        after = getattr(leaf, 'not_valid_after_utc', None)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        before = before or leaf.not_valid_before.replace(tzinfo=datetime.timezone.utc)
        after = after or leaf.not_valid_after.replace(tzinfo=datetime.timezone.utc)
        require(set(names) == {name} and public(key.public_key()) == public(leaf.public_key()) and before <= now < after,
                'Certificate identity, key or validity mismatch.')

    def account(self, previous):
        config = ConfigObj(str(self.path('/etc/letsencrypt/renewal/'+previous+'.conf')), file_error=True)['renewalparams']
        account, server = config.get('account', ''), config.get('server', '')
        url = urlsplit(server)
        require(re.fullmatch(r'[a-f0-9]{32}', account) is not None and url.scheme == 'https' and url.hostname and
                not url.username and not url.password and not url.query and not url.fragment and
                re.fullmatch(r'[A-Za-z0-9.:[\]-]+', url.netloc) and re.fullmatch(r'/[A-Za-z0-9_./-]*', url.path) and
                all(part not in ('.','..') for part in url.path.split('/')),
                'Unknown managed Certbot account/server; existing accounts were preserved.')
        for file in ('meta.json', 'private_key.json', 'regr.json'):
            require(isinstance(json.loads(self.read('/etc/letsencrypt/accounts/'+url.netloc+url.path+'/'+account+'/'+file)), dict),
                    'Missing or invalid managed Certbot account metadata.')
        return account, server

    def issue(self, name, previous):
        account, server = self.account(previous)
        self.run('certbot', 'certonly', '--webroot', '--webroot-path', '/var/www/acme', '--cert-name', name, '-d', name,
                 '--account', account, '--server', server, '--non-interactive', '--no-directory-hooks',
                 '--pre-hook', '', '--post-hook', '', '--deploy-hook', '', timeout=300)
        self.certificate(name)

    def candidate_nginx(self, record):
        # Test the complete real include tree. Only candidate configs and log/pid
        # destinations are private; certificates and distro modules are real deps.
        with tempfile.TemporaryDirectory(prefix='xui-domain-nginx-', dir=self.path(STATE) if self.path(STATE).is_dir() else None) as temporary:
            stage = Path(temporary); tree = stage/'nginx'
            shutil.copytree(self.path('/etc/nginx'), tree, symlinks=True)
            for item in record['files']:
                if not item['path'].startswith('/etc/nginx/'):
                    continue
                path = tree/item['path'].removeprefix('/etc/nginx/')
                value = item['after']
                if path.is_symlink() or path.is_file():
                    path.unlink()
                if value['kind'] == 'file':
                    path.write_bytes(base64.b64decode(value['data']))
                elif value['kind'] == 'link':
                    path.symlink_to(value['data'])
            for path in list(tree.rglob('*')):
                if not path.is_symlink():
                    continue
                target = os.readlink(path)
                if target.startswith('/etc/nginx/'):
                    path.unlink(); path.symlink_to(tree/target.removeprefix('/etc/nginx/'))
                elif target.startswith('/usr/share/nginx/modules-available/'):
                    contents = self.path(target).read_bytes(); path.unlink(); path.write_bytes(contents)
                else:
                    require(target.startswith('/usr/lib/nginx/modules/'), 'Unsupported external nginx include symlink.')
            for path in tree.rglob('*'):
                if not path.is_file() or path.is_symlink():
                    continue
                text = path.read_text()
                text = re.sub(r'(\binclude\s+)(["\']?)/etc/nginx/', lambda m: m[1]+m[2]+str(tree)+'/', text)
                def include(match):
                    target = match[2].strip('"\'')
                    if '$' in target or '..' in Path(target).parts or (target.startswith('/') and not target.startswith(str(tree)+'/')):
                        # Only nginx determines whether this file is effective.
                        return match[1]+'xui_domains_unsupported_include;'
                    return match[0]
                text = re.sub(r'(\binclude\s+)([^;]+);', include, text)
                text = re.sub(r'(\b(?:access_log|error_log)\s+)([^;\s]+)',
                              lambda m: m[0] if m[2] in ('off', 'stderr') else m[1]+str(stage/'nginx.log'), text)
                text = re.sub(r'(\bpid\s+)[^;]+;', lambda m: m[1]+str(stage/'nginx.pid')+';', text)
                text = text.replace('load_module modules/', 'load_module /usr/lib/nginx/modules/')
                path.write_text(text)
            self.run('nginx', '-t', '-p', str(stage)+'/', '-c', tree/'nginx.conf')

    @staticmethod
    def summary(context):
        result = {key: copy.deepcopy(context[key]) for key in ('domains', 'inbound_roles', 'features')}
        result['telemt'] = copy.deepcopy(context.get('telemt'))
        return result

    @staticmethod
    def same_value(column, left, right):
        if column == 'stream_settings':
            try:
                return json.loads(left) == json.loads(right)
            except (ValueError, TypeError):
                return False
        return left == right

    def database_current(self, db, item):
        allowed = {'settings': {'value'}, 'inbounds': {'stream_settings', 'share_addr'}, 'hosts': {'address', 'sni'}}
        require(item.get('table') in allowed and item.get('column') in allowed[item['table']], 'Invalid SQLite recovery record.')
        key = 'key' if item['table'] == 'settings' else 'id'
        if key == 'key':
            require(item['identity'] in ('webCertFile', 'webKeyFile', 'subCertFile', 'subKeyFile', 'subURI', 'subJsonURI', 'webDomain', 'subDomain'),
                    'Invalid setting in recovery record.')
        else:
            require(type(item['identity']) is int and item['identity'] > 0, 'Invalid row identity in recovery record.')
        values = db.execute('SELECT '+item['column']+' FROM '+item['table']+' WHERE '+key+'=?', (item['identity'],)).fetchall()
        return single(values, 'Recovery row is missing or duplicated.')[0]

    def database_update(self, record, forward):
        with self.connection() as db:
            validate_schema(db)
            require(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0, 'SQLite WAL is busy; no database replacement was attempted.')
            db.execute('BEGIN IMMEDIATE')
            try:
                for item in record['database']:
                    current = self.database_current(db, item)
                    target, previous = (item['after'], item['before']) if forward else (item['before'], item['after'])
                    if self.same_value(item['column'], current, target):
                        continue
                    require(self.same_value(item['column'], current, previous), 'SQLite values changed independently; recovery refused to overwrite them.')
                    key = 'key' if item['table'] == 'settings' else 'id'
                    values = [target]
                    expression = '?'
                    if forward and item.get('paths'):
                        expression = 'json_set('+item['column']+','+','.join('?,json(?)' for _ in item['paths'])+')'
                        values = [value for path, value in item['paths'] for value in (path, json.dumps(value))]
                    result = db.execute('UPDATE '+item['table']+' SET '+item['column']+'='+expression+' WHERE '+key+'=? AND '+item['column']+' IS ?',
                                        (*values, item['identity'], current))
                    require(result.rowcount == 1, 'SQLite compare-and-set failed; transaction rolled back.')
                    require(self.same_value(item['column'], self.database_current(db, item), target), 'SQLite UPDATE did not persist the exact intended value.')
                require(tuple(db.execute('PRAGMA quick_check').fetchone()) == ('ok',), 'SQLite integrity check failed after UPDATE.')
                db.commit()
            except BaseException:
                db.rollback()
                raise
            require(db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] == 0, 'SQLite WAL checkpoint failed after UPDATE.')
        fd = os.open(self.path(DB), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.sync(self.path(DB).parent)

    def guards(self, context):
        paths = ['/etc/systemd/system/x-ui.service', '/etc/default/x-ui']
        paths += list((context.get('telemt') or {}).get('files', {}))
        if context['features']['vision']:
            paths += ['/etc/nginx/sites-available/vision.conf', '/etc/nginx/sites-available/vision-acme.conf',
                      '/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision']
        return {path: self.guard_value(path) for path in paths}

    def guard_value(self, path):
        value = self.object(path); value.pop('mtime', None)
        return digest(json.dumps(value, sort_keys=True).encode())

    def check_guards(self, record):
        allowed = {'/etc/systemd/system/x-ui.service', '/etc/default/x-ui', '/etc/nginx/sites-available/vision.conf',
                   '/etc/nginx/sites-available/vision-acme.conf', '/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision'}
        allowed.update(TELEMT_FILES)
        allowed.add(TELEMT_MANIFEST)
        require(record['guards'].keys() <= allowed and all(self.guard_value(path) == expected for path, expected in record['guards'].items()),
                'Service/Vision resources changed independently; operation refused to overwrite them.')

    def conflict_check(self, record):
        domains = record['old']['domains']; new = record['new']['domains']
        allowed = {STREAM, HTTP, HOOK, CLASH, DIAGNOSTICS, AGH, MANIFEST, HYSTERIA}
        for domain in {domains['panel'], domains['reality'], new['panel'], new['reality']}:
            hostname(domain)
            allowed |= {'/etc/nginx/sites-available/'+domain, '/etc/nginx/sites-enabled/'+domain}
        allowed |= {'/root/cert/'+new['panel'], '/root/cert/'+new['panel']+'/fullchain.pem', '/root/cert/'+new['panel']+'/privkey.pem'}
        require(len(record['files']) <= 24 and len({r['path'] for r in record['files']}) == len(record['files']), 'Invalid bounded recovery file list.')
        for item in record['files']:
            require(item['path'] in allowed and item['before']['kind'] in ('absent', 'file', 'link', 'directory') and
                    item['after']['kind'] in ('absent', 'file', 'link', 'directory'), 'Invalid path/type in recovery journal.')
            current = self.object(item['path'])
            choices = [item['before']]
            if record['phase'] != 'prepared' or item['path'] == HTTP:
                choices.append(item['after'])
            require(any(self.same(current, choice) for choice in choices), 'Managed file changed independently; recovery material retained.')
        with self.connection(True) as db:
            validate_schema(db)
            require(len(record['database']) <= 20, 'Invalid bounded SQLite recovery list.')
            for item in record['database']:
                current = self.database_current(db, item)
                choices = [item['before']] if record['phase'] == 'prepared' else [item['before'], item['after']]
                require(any(self.same_value(item['column'], current, value) for value in choices), 'SQLite changed independently; recovery material retained.')
        self.check_guards(record)

    def recover(self):
        self.parents(STATE+'/journal.json')
        directory = self.path(STATE)
        if not directory.exists() and not directory.is_symlink():
            return False
        require(not directory.is_symlink() and directory.stat().st_uid == 0 and stat.S_IMODE(directory.stat().st_mode) == 0o700,
                'Unsafe persistent recovery directory.')
        path = self.path(STATE+'/journal.json')
        if not path.exists() and not path.is_symlink():
            return False
        require(path.lstat().st_uid == 0 and stat.S_IMODE(path.lstat().st_mode) == 0o600 and not path.is_symlink(),
                'Unsafe persistent recovery journal.')
        record = json.loads(self.read(STATE+'/journal.json'))
        require(record.get('format') == 1 and record.get('phase') in ('prepared', 'switching', 'committed'), 'Unknown recovery journal format/phase.')
        self.stage = 'recovering '+record['phase']+' operation'
        require(self.panel_version() == record.get('version'), 'Panel version changed after preparation; recovery material retained.')
        require(not self.run('systemctl', 'show', 'x-ui', '-p', 'DropInPaths', '--value').strip(), 'Service overrides changed after preparation; recovery material retained.')
        self.check_guards(record)
        if record['phase'] == 'committed':
            # A committed installation is never rolled back for cleanup failure.
            self.check_guards(record)
            self.healthy(record['new'])
            require(self.service_states(record['new']) == record['services'], 'Service states changed independently after commit.')
            self.finish()
            print('COMMITTED: new domains verified; recovery cleanup completed.')
            return True
        self.conflict_check(record)
        if record['phase'] == 'switching':
            with self.connection(True) as db:
                changed = any(not self.same_value(item['column'], self.database_current(db, item), item['before']) for item in record['database'])
            files_changed = any(item['path'] != HTTP and not self.same(self.object(item['path']), item['before']) for item in record['files'])
            if changed or files_changed:
                self.run('systemctl', 'stop', 'x-ui')
            if changed:
                self.database_update(record, False)
        for item in reversed(record['files']):
            if not self.same(self.object(item['path']), item['before']):
                self.put(item['path'], item['before'])
        self.run('nginx', '-t')
        self.run('systemctl', 'reload', 'nginx')
        self.run('systemctl', 'start', 'x-ui')
        self.run('systemctl', 'start', 'certbot.timer')
        self.healthy(record['old'])
        require(self.service_states(record['old']) == record['services'], 'Original service states could not be verified.')
        self.check_guards(record)
        self.finish()
        print('ROLLBACK_VERIFIED: original domains and services restored. Backup: '+record['backup'])
        return True

    def change(self, panel, reality, expected_panel, expected_reality, source):
        require(re.fullmatch(r'[0-9a-f]{40}', source) is not None, 'Missing exact trusted project source.')
        require(not os.path.lexists(self.path(STATE+'/journal.json')), 'Recover the pending domain operation before starting another.')
        self.stage = 'validating installed layout'
        version = self.version_and_layout()
        self.stage = 'recognizing managed configuration'
        context = self.discover()
        require((context['domains']['panel'], context['domains']['reality']) == (expected_panel, expected_reality),
                'Domains changed after confirmation; no data changed.')
        self.stage = 'checking target domains'
        self.target_preflight(context, panel, reality)
        self.stage = 'planning scoped changes'
        with self.connection(True) as db:
            database_edits(db, context, panel, reality)  # Reject overrides before Backup or ACME.
        self.file_plan(context, panel, reality, source)
        self.stage = 'checking original stack'
        self.healthy(context)
        self.stage = 'checking original nginx'
        self.candidate_nginx({'files': []})
        self.stage = 'checking original certificates'
        for domain in (context['domains']['panel'], context['domains']['reality']):
            self.certificate(domain)
        services = self.service_states(context)
        self.stage = 'creating full Backup v3'
        try:
            result = json.loads(self.run('bash', self.backup, 'backup', '--json', timeout=1800, inherit_lock=True))
        except BaseException:
            try:
                self.healthy(context)
                require(self.service_states(context) == services, 'Original service states changed during Backup.')
            except BaseException:
                raise Refusal('ROLLBACK_UNVERIFIED: full Backup failed and original service health could not be verified; retain /var/backups/x-ui recovery materials.') from None
            raise
        require(result.get('status') == 'success' and isinstance(result.get('archive'), str), 'Full Backup v3 did not return verified success.')
        archive = Path(result['archive'])
        require(archive.parent == self.path('/var/backups/x-ui') and archive.name.endswith('.tar.gz') and not archive.is_symlink(),
                'Backup returned an unexpected archive path.')
        self.run('bash', self.backup, 'inspect', archive, inherit_lock=True)
        print('Full Backup v3 verified: '+str(archive))
        self.stage = 'checking stack after Backup'
        context = self.discover(self.summary(context))
        self.healthy(context)
        require(self.service_states(context) == services, 'Backup did not preserve the original service states.')
        with self.connection(True) as db:
            edits = database_edits(db, context, panel, reality)
        files, marker = self.file_plan(context, panel, reality, source)
        new = self.summary(context); new['domains'] = marker['domains']
        record = dict(format=1, phase='prepared', version=version, old=self.summary(context), new=new, files=files,
                      database=edits, backup=str(archive), guards=self.guards(context), services=services)
        self.journal(record)
        committed = False
        try:
            self.stage = 'preparing certificates'
            self.run('systemctl', 'stop', 'certbot.timer')
            status = self.run('systemctl', 'show', 'certbot.service', '-p', 'ActiveState', '--value').decode().strip()
            require(status in ('inactive', 'failed'), 'A Certbot transaction is already running; retry when it finishes.')
            for item in files:
                if item['path'] == HTTP:
                    require(self.same(self.object(HTTP), item['before']), 'HTTP-01 configuration changed independently.')
                    self.put(HTTP, item['after'])
            self.run('nginx', '-t'); self.run('systemctl', 'reload', 'nginx')
            for name, previous in ((panel, context['domains']['panel']), (reality, context['domains']['reality'])):
                if name != previous:
                    self.issue(name, previous)
            self.stage = 'validating complete candidate nginx'
            self.candidate_nginx(record)
            self.conflict_check(record)
            self.stage = 'switching'
            record['phase'] = 'switching'; self.journal(record)
            self.run('systemctl', 'stop', 'x-ui')
            self.database_update(record, True)
            for item in files:
                if item['path'] != MANIFEST:
                    require(any(self.same(self.object(item['path']), state) for state in (item['before'], item['after'])),
                            'Managed file changed during switching; recovery material retained.')
                    self.put(item['path'], item['after'])
            self.run('nginx', '-t'); self.run('systemctl', 'reload', 'nginx')
            self.run('systemctl', 'start', 'x-ui')
            self.run('systemctl', 'start', 'certbot.timer')
            self.stage = 'verifying new stack'
            self.healthy(new, ignore_manifest=True)
            self.check_guards(record)
            item = single([i for i in files if i['path'] == MANIFEST], 'Missing final managed manifest.')
            require(self.same(self.object(MANIFEST), item['before']), 'Manifest changed independently during switching.')
            self.put(MANIFEST, item['after'])
            self.healthy(new)
            require(self.service_states(new) == services, 'New stack service states could not be verified.')
            record['phase'] = 'committed'; self.journal(record); committed = True
        except BaseException:
            if not committed:
                failure_stage = self.stage
                try:
                    self.recover()
                except BaseException:
                    print('ROLLBACK_UNVERIFIED: retain '+str(self.path(STATE))+' and Backup '+str(archive)+'.', file=sys.stderr)
                    raise Refusal('Switch/recovery could not be verified; new modifying actions are blocked.') from None
                self.stage = failure_stage
            raise
        try:
            self.finish()
        except OSError:
            print('COMMITTED: new stack is healthy; private journal retained for verified cleanup.', file=sys.stderr)
        print('SUCCESS: Panel='+panel+' REALITY='+reality+'. Update affected client configurations/subscription URLs.')


def lock_required():
    require(os.geteuid() == 0, 'Run Change Domains through the root manager.')
    path = Path('/run/3x-ui-auto-nginx/operation.lock')
    parent = path.parent.lstat()
    require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0 and stat.S_IMODE(parent.st_mode) == 0o700,
            'Unsafe shared operation lock directory.')
    info = path.lstat(); inherited = os.fstat(9)
    require(not path.is_symlink() and stat.S_ISREG(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600 and
            (info.st_dev, info.st_ino) == (inherited.st_dev, inherited.st_ino), 'Missing shared operation lock descriptor.')
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checks', required=True)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('action', choices=('inspect', 'recover', 'change'))
    parser.add_argument('domains', nargs='*')
    args = parser.parse_args()
    operation = Operation(args.checks, args.backup)
    try:
        lock_required()
        for file in (args.checks, args.backup):
            info = Path(file).lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                    'Unsafe trusted manager helper path.')
        def interrupted(signum, frame):
            raise Refusal('Operation interrupted; verified recovery is required.')
        signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
        if args.action == 'inspect':
            operation.stage = 'validating installed layout'
            operation.version_and_layout()
            operation.stage = 'recognizing managed configuration'
            context = operation.discover()
            print(json.dumps(operation.summary(context)))
        elif args.action == 'recover':
            operation.recover()
        else:
            require(len(args.domains) == 4, 'Expected new and confirmed current domain pairs.')
            operation.change(*args.domains, args.source)
        return 0
    except BaseException as error:
        reason = str(error) if isinstance(error, Refusal) else (
            'command failed (exit '+str(error.returncode)+')' if isinstance(error, subprocess.CalledProcessError) else
            'Managed HTTPS certificate/handshake/response validation failed.' if isinstance(error, (ssl.SSLError, http.client.HTTPException)) else
            'Required local component is missing/inaccessible (errno '+str(error.errno)+').' if isinstance(error, OSError) else
            'Malformed managed metadata or unsupported layout.' if isinstance(error, (KeyError, TypeError, ValueError)) else type(error).__name__)
        print('Change Domains failed during '+operation.stage+': '+reason, file=sys.stderr)
        if operation.path(STATE+'/journal.json').exists():
            try:
                phase = json.loads(operation.read(STATE+'/journal.json')).get('phase')
            except (OSError, ValueError):
                phase = None
            status = 'COMMITTED_STATE_UNVERIFIED' if phase == 'committed' else 'ROLLBACK_UNVERIFIED'
            print(status+': private recovery journal retained at '+STATE+'. Start the manager through SSH before another operation.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
