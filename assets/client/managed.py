"""Initial client via official 3x-ui v3.9.0 session/CSRF and subscription backend.

Import Panel from the existing AWG helper. No SQL, custom exports or stored tokens.
"""
import base64
import configparser
import ipaddress
import json
import os
from pathlib import Path
import secrets
import string
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit
import uuid


def random_id():
    return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(16))


def object_value(value):
    return json.loads(value) if isinstance(value, str) else value


def active_inbounds(panel):
    rows = panel.request('panel/api/inbounds/list')['obj']
    supported = {'vless', 'trojan', 'hysteria', 'amneziawg'}
    result = [row for row in rows if row.get('enable') is True and row['protocol'] in supported
              and not row.get('nodeId')]
    if not result or len({r['id'] for r in result}) != len(result):
        raise ValueError('No applicable local inbounds or duplicate IDs')
    return result


def validate_credentials(rows, email):
    credentials = []
    for row in rows:
        matches = [c for c in object_value(row['settings'])['clients'] if c['email'] == email]
        if len(matches) != 1 or matches[0].get('enable') is not True:
            raise ValueError('Missing, disabled or duplicate inbound client')
        client = matches[0]
        stream = object_value(row.get('streamSettings') or {})
        vision = row['protocol'] == 'vless' and stream.get('network') in ('tcp', 'raw') and stream.get('security') in ('tls', 'reality')
        if client.get('flow', '') != ('xtls-rprx-vision' if vision else ''):
            raise ValueError('Wrong per-inbound flow: ' + row['protocol'] + '/' + stream.get('network', 'none'))
        if row['protocol'] == 'vless':
            uuid.UUID(client['id'])
            credentials.append(client['id'])
        elif row['protocol'] == 'hysteria' and not client.get('auth'):
            raise ValueError('Missing Hysteria credentials')
        elif row['protocol'] == 'trojan' and not client.get('password'):
            raise ValueError('Missing Trojan credentials')
        elif row['protocol'] == 'amneziawg':
            for key in ('privateKey', 'publicKey', *(['preSharedKey'] if client.get('preSharedKey') else [])):
                if len(base64.b64decode(client[key], validate=True)) != 32:
                    raise ValueError('Invalid AWG key')
            addresses = client.get('allowedIPs') or []
            if not addresses:
                raise ValueError('Missing AWG address')
            for address in addresses:
                ipaddress.ip_interface(address)
            others = object_value(row['settings'])['clients']
            if any(set(addresses) & set(c.get('allowedIPs') or []) for c in others if c['email'] != email):
                raise ValueError('AWG address collision')
    if len(set(credentials)) > 1:
        raise ValueError('VLESS credentials are not synchronized')


def decode_subscription(raw):
    if b'://' not in raw:
        raw = base64.b64decode(raw, validate=True)
    links = [line for line in raw.decode().splitlines() if '://' in line]
    if not links or len(links) != len(set(links)):
        raise ValueError('Empty/duplicate subscription')
    for link in links:
        parsed = urlsplit(link)
        if parsed.scheme not in ('vless', 'trojan', 'hy2', 'hysteria2', 'vpn'):
            raise ValueError('Unsupported subscription record')
        if parsed.scheme == 'vpn':
            encoded = link[6:]
            text = base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode()
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(text)
            if not config['Interface']['PrivateKey'] or not config['Peer']['Endpoint']:
                raise ValueError('Invalid official AWG export')
        else:
            if not parsed.hostname or not parsed.port or not parsed.username:
                raise ValueError('Invalid official link')
            query = parse_qs(parsed.query)
            if query.get('allowInsecure', ['0']) != ['0']:
                raise ValueError('Subscription disables TLS verification')
    return links


def fetch(panel, url):
    # No cookies required by the official subscription endpoint. Never follow redirects.
    result = subprocess.run(['curl', '-q', '-fsS', '--noproxy', '*', '--connect-timeout', '5',
                             '--max-time', '20', *panel.options, '--config', '-'],
                            input=('url = '+json.dumps(url)+'\n').encode(), capture_output=True, timeout=25)
    if result.returncode:
        raise ValueError('Subscription request failed (curl status ' + str(result.returncode) + ')')
    return result.stdout


def link_identity(link):
    parsed = urlsplit(link)
    if parsed.scheme == 'vpn':
        encoded = link[6:]
        conf = configparser.ConfigParser(interpolation=None)
        conf.read_string(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)).decode())
        return ('vpn', tuple((section, tuple(sorted(conf[section].items()))) for section in conf.sections()))
    # Official subscription remarks include usage; panel QR remarks use name only.
    params = parse_qs(parsed.query)
    if params.get('security') == ['reality']:
        params.pop('sid', None)  # Upstream selects randomly from this inbound's shortIds.
    return (parsed.scheme, parsed.hostname, parsed.port, parsed.username, parsed.password,
            tuple(sorted((key, tuple(values)) for key, values in params.items())))


def subscription(panel, sub_id, rows, email):
    settings = panel.request('panel/api/setting/defaultSettings', {})['obj']
    origin = urlsplit(panel.base)
    uri = settings.get('subURI', '')
    parsed = urlsplit(uri)
    if (not settings.get('subEnable') or parsed.scheme != 'https' or parsed.netloc != origin.netloc
            or not parsed.path.endswith('/') or parsed.query or parsed.fragment):
        raise ValueError('Unexpected subscription URI')
    url = uri + sub_id
    official = panel.request('panel/api/clients/links/' + email)['obj']
    links = decode_subscription(fetch(panel, url))
    if sorted(map(link_identity, links)) != sorted(map(link_identity, official)) or len(links) < len(rows):
        raise ValueError('Subscription differs from official client links: ' + str(len(links)) + '/' + str(len(official)) + '/' + str(len(rows)))
    # Each attached inbound must be represented in its official link set, with a matching secret.
    for row in rows:
        client = next(c for c in object_value(row['settings'])['clients'] if c['email'] == email)
        secret = client.get({'vless': 'id', 'trojan': 'password', 'hysteria': 'auth', 'amneziawg': 'privateKey'}[row['protocol']])
        if row['protocol'] != 'amneziawg' and not any(urlsplit(link).username == secret for link in links):
            raise ValueError('Inbound credentials absent from subscription')
        if row['protocol'] == 'amneziawg' and not any(link.startswith('vpn://') for link in links):
            raise ValueError('AWG export absent')
        stream = object_value(row.get('streamSettings') or {})
        if stream.get('security') == 'reality':
            related = [parse_qs(urlsplit(link).query) for link in links if urlsplit(link).username == secret
                       and parse_qs(urlsplit(link).query).get('security') == ['reality']]
            if not related or any(q.get('sid', [''])[0] not in stream['realitySettings']['shortIds'] for q in related):
                raise ValueError('Invalid REALITY shortId in subscription')
    json_uri = settings.get('subJsonURI', '')
    if settings.get('subJsonEnable'):
        parsed = urlsplit(json_uri)
        if (parsed.scheme != 'https' or parsed.netloc != origin.netloc or not parsed.path.endswith('/')
                or parsed.query or parsed.fragment):
            raise ValueError('Unexpected JSON subscription URI')
        configs = json.loads(fetch(panel, json_uri + sub_id))
        if not isinstance(configs, list) or not configs:
            raise ValueError('Empty JSON subscription')
    return url


def create(panel, identity=None, reserve=None):
    rows = active_inbounds(panel)
    expected = {row['id'] for row in rows}
    existing = panel.request('panel/api/clients/list')['obj']
    if identity is None:
        for _ in range(5):
            email, sub_id = 'client-' + random_id(), random_id()
            if not any(c['email'] == email or c.get('subId') == sub_id for c in existing):
                break
        else:
            raise ValueError('Cannot allocate unique client identity')
        identity = {'email': email, 'subId': sub_id}
        if reserve:
            reserve(identity)
        # Do not repeat this call after an uncertain response. Read actual state instead.
        try:
            panel.request('panel/api/clients/add', {'client': {**identity, 'enable': True,
                          'flow': 'xtls-rprx-vision', 'totalGB': 0, 'expiryTime': 0,
                          'limitIp': 0, 'limitHwid': 0}, 'inboundIds': sorted(expected)})
        except (ValueError, subprocess.SubprocessError):
            pass
    email, sub_id = identity['email'], identity['subId']
    record = panel.request('panel/api/clients/get/' + email)['obj']
    if record['client']['email'] != email or record['client']['subId'] != sub_id:
        raise ValueError('Client identity mismatch; no existing client was removed')
    if 'id' in identity and record['client']['id'] != identity['id']:
        raise ValueError('Owned initial client was replaced; existing record preserved')
    actual = set(record['inboundIds'])
    if not actual <= expected:
        raise ValueError('Unexpected attachments')
    if actual != expected:
        # One bounded attach, never another create. Only the uniquely owned client.
        try:
            panel.request('panel/api/clients/' + email + '/attach', {'inboundIds': sorted(expected - actual)})
        except (ValueError, subprocess.SubprocessError):
            pass
        record = panel.request('panel/api/clients/get/' + email)['obj']
    if set(record['inboundIds']) != expected or len(record['inboundIds']) != len(expected):
        raise ValueError('Incomplete client creation; retained for administrator inspection')
    rows = active_inbounds(panel)
    if {row['id'] for row in rows} != expected:
        raise ValueError('Active inbound set changed during creation')
    validate_credentials(rows, email)
    panel.request('panel/api/server/restartXrayService', {})
    all_clients = panel.request('panel/api/clients/list')['obj']
    if sum(c['email'] == email or c.get('subId') == sub_id for c in all_clients) != 1:
        raise ValueError('Client collision or duplicate')
    url = subscription(panel, sub_id, rows, email)
    return {'id': record['client']['id'], 'email': email, 'subId': sub_id, 'url': url, 'protocols': [r['remark'] for r in rows]}


def main():
    import importlib.util
    helper, domain, path, username = sys.argv[1:]
    spec = importlib.util.spec_from_file_location('awg_session', helper)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='xui-client-') as directory:
        os.chmod(directory, 0o700)
        panel = module.Panel(f'https://{domain}/{path}/', username, sys.stdin.read(), directory,
                             ['--resolve', f'{domain}:443:127.0.0.1'])
        marker = Path('/etc/x-ui/initial-client.json')
        identity = None
        if marker.exists() or marker.is_symlink():
            if marker.is_symlink() or marker.stat().st_uid != 0 or marker.stat().st_mode & 0o777 != 0o600:
                raise ValueError('Unowned initial client marker')
            saved = json.loads(marker.read_text())
            if saved.get('owner') != '3x-ui-auto-nginx':
                raise ValueError('Unowned initial client marker')
            identity = saved['identity']
            import re
            if not re.fullmatch(r'client-[a-z0-9]{16}', identity['email']) or not re.fullmatch(r'[a-z0-9]{16}', identity['subId']):
                raise ValueError('Invalid initial client marker')
        def reserve(identity):
            fd, temporary = tempfile.mkstemp(prefix='.initial-client-', dir=marker.parent)
            try:
                with os.fdopen(fd, 'w') as out:
                    json.dump({'owner': '3x-ui-auto-nginx', 'identity': identity}, out)
                os.replace(temporary, marker)
            finally:
                Path(temporary).unlink(missing_ok=True)
        result = create(panel, identity, reserve)
        reserve({key: result[key] for key in ('id', 'email', 'subId')})
        print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Initial client/subscription failed verification. Core remains installed; inspect clients in the panel before retrying.', file=sys.stderr)
        sys.exit(1)
