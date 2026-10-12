"""Separate loopback RAW TLS Vision inbound; nginx retains public TCP/443."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

from cryptography import x509
from cryptography.hazmat.primitives import serialization

MARKER = '# Managed by 3x-ui Auto Nginx: Vision\n'


class Failure(ValueError):
    def __init__(self, status, stage='Vision setup', reason='operation failed', rollback=''):
        super().__init__(f'Vision failed during {stage}: {reason}; rollback={status}' +
                         (f'; rollback failure: {rollback}' if rollback else ''))
        self.status = status
        self.stage, self.reason = stage, reason


def safe_reason(error):
    # Never include argv, stderr, API bodies or arbitrary exception messages.
    if isinstance(error, subprocess.CalledProcessError):
        tool = Path(error.cmd[0]).name if isinstance(error.cmd, (tuple, list)) else 'command'
        tool = tool if tool in ('curl', 'nginx', 'systemctl') else 'command'
        detail = {7:'connection refused/unavailable', 22:'HTTP error response', 28:'request timed out',
                  35:'TLS handshake failed', 52:'empty response', 56:'connection receive failed',
                  60:'certificate verification failed'}.get(error.returncode, '') if tool == 'curl' else ''
        return f'{tool} exited with {error.returncode}' + (f' ({detail})' if detail else '')
    if isinstance(error, subprocess.TimeoutExpired): return 'command timed out'
    if isinstance(error, OSError): return f'OS error (errno {error.errno})'
    known = ('Invalid Vision certificate identity, key or validity', 'Refusing existing/symlinked Vision artifacts',
             'Conflicting/unrecognized nginx stream', 'Vision tag already owned by another inbound',
             'Vision API topology mismatch', 'Ambiguous Vision ownership',
             'Vision artifact ownership changed; retained', 'Stream rollback mismatch',
             'Vision listener did not become ready within 10 seconds')
    if isinstance(error, ValueError) and str(error) in known: return str(error)
    if isinstance(error, ValueError) and str(error).startswith('AmneziaWG panel '):
        return '3X-UI API rejected request' if 'rejected request:' in str(error) else '3X-UI API request failed'
    return type(error).__name__


def domain_name(name):
    if len(name) > 253 or '.' not in name or not all(
        re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in name.split('.')):
        raise ValueError('Invalid Vision domain')
    return name


def certificate(domain, cert, key):
    leaf = x509.load_pem_x509_certificate(Path(cert).read_bytes())
    private = serialization.load_pem_private_key(Path(key).read_bytes(), password=None)
    public = lambda value: value.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    now = datetime.datetime.now(datetime.timezone.utc)
    before = getattr(leaf, 'not_valid_before_utc', None)
    after = getattr(leaf, 'not_valid_after_utc', None)
    # Ubuntu 24.04's cryptography <42 has no UTC properties or deprecation.
    if before is None: before = leaf.not_valid_before.replace(tzinfo=datetime.timezone.utc)
    if after is None: after = leaf.not_valid_after.replace(tzinfo=datetime.timezone.utc)
    if (set(names) != {domain} or public(private.public_key()) != public(leaf.public_key())
            or not before <= now < after):
        raise ValueError('Invalid Vision certificate identity, key or validity')


def inbound(domain, port, fallback, cert, key, flag="🌐"):
    domain_name(domain)
    if port == fallback or any(not 1024 <= p <= 65535 for p in (port, fallback)):
        raise ValueError('Invalid/distinct internal ports required')
    return {'enable': True, 'listen': '127.0.0.1', 'port': port, 'protocol': 'vless',
            'remark': flag + ' XTLS', 'tag': f'inbound-{port}',
            'settings': {'clients': [], 'decryption': 'none', 'encryption': 'none',
                         'fallbacks': [{'name': domain, 'alpn': 'http/1.1', 'dest': f'127.0.0.1:{fallback}', 'xver': 1}]},
            # Official panel v3.9.0 gates flow on "tcp". Xray maps tcp/raw to RAW.
            'streamSettings': {'network': 'tcp', 'security': 'tls',
                               'rawSettings': {'acceptProxyProtocol': True, 'header': {'type': 'none'}},
                               'tlsSettings': {'serverName': domain, 'minVersion': '1.2', 'alpn': ['http/1.1'],
                                               'certificates': [{'certificateFile': cert, 'keyFile': key,
                                                                 'oneTimeLoading': False, 'usage': 'encipherment'}]}},
            'sniffing': {'enabled': True, 'destOverride': ['http', 'tls'], 'routeOnly': False}}


def fallback_config(domain, port, root='/var/www/html'):
    domain_name(domain)
    return MARKER + f'''server {{
    listen 127.0.0.1:{port} proxy_protocol;
    server_name {domain};
    server_tokens off;
    root {root};
    index index.html;
    real_ip_header proxy_protocol;
    set_real_ip_from 127.0.0.1;
    if ($host != {domain}) {{ return 404; }}
    location / {{ try_files $uri $uri/ =404; }}
}}
'''


def acme_config(domain):
    domain_name(domain)
    return MARKER + f'''server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/acme; try_files $uri =404; }}
    location / {{ return 301 https://$host$request_uri; }}
}}
'''


def nginx_artifact_domain(site, acme):
    names = set()
    for path, render in ((Path(site), fallback_config), (Path(acme), acme_config)):
        if not path.exists():
            continue
        text = path.read_text()
        name = re.search(r'^    server_name ([a-z0-9.-]+);$', text, re.M)
        if not name:
            raise ValueError('Unrecognized Vision server name')
        domain_name(name[1])
        if render is fallback_config:
            port = re.search(r'^    listen 127\.0\.0\.1:(\d+) proxy_protocol;$', text, re.M)
            if not port or not 1024 <= int(port[1]) <= 65535:
                raise ValueError('Unrecognized Vision fallback port')
            expected = render(name[1], int(port[1]))
        else:
            expected = render(name[1])
        if text != expected:
            raise ValueError('Modified Vision nginx configuration; preserved')
        names.add(name[1])
    if len(names) > 1:
        raise ValueError('Conflicting managed Vision domains')
    return next(iter(names), '')


def stream_config(text, domain, port):
    domain_name(domain)
    # One exact insertion point in the existing installer topology, no generic rewriting.
    anchor = 'map $ssl_preread_server_name $sni_name {\n    hostnames;\n'
    if text.count(anchor) != 1 or re.search(r'\b' + re.escape(domain) + r'\b', text) or 'upstream vision' in text:
        raise ValueError('Conflicting/unrecognized nginx stream')
    return text.replace(anchor, anchor + f'    {domain} vision;\n') + f'\nupstream vision {{ server 127.0.0.1:{port}; }}\n'


def run(*argv):
    subprocess.run(argv, check=True, capture_output=True, timeout=40)


def wait_inbound(port):
    deadline = time.monotonic() + 10
    while True:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.25): return
        except OSError:
            if time.monotonic() >= deadline:
                raise ValueError('Vision listener did not become ready within 10 seconds') from None
            time.sleep(0.25)


def configure(panel, domain, port, fallback, stream, site, enabled, cert, key, flag="🌐"):
    stage = 'validating Vision certificate'
    try:
        certificate(domain, cert, key)
        stage = 'checking Vision artifacts and stream'
        stream, site, enabled = map(Path, (stream, site, enabled))
        if stream.is_symlink() or site.exists() or site.is_symlink() or enabled.exists() or enabled.is_symlink():
            raise ValueError('Refusing existing/symlinked Vision artifacts')
        original = stream.read_bytes()
        patched = stream_config(original.decode(), domain, port)
        expected = inbound(domain, port, fallback, cert, key, flag)
        stage = 'listing existing 3X-UI inbounds'
        if any(row.get('tag') == expected['tag'] for row in panel.request('panel/api/inbounds/list')['obj']):
            raise ValueError('Vision tag already owned by another inbound')
    except Exception as error:
        raise Failure('failed_rolled_back', stage, safe_reason(error)) from None
    try:
        stage = 'creating Vision inbound via 3X-UI API'
        row = panel.request('panel/api/inbounds/add', expected)['obj']
        iid = row['id']
        if any(row.get(k) != expected[k] for k in ('enable', 'listen', 'port', 'protocol', 'tag')):
            raise ValueError('Vision API topology mismatch')
        stage = 'creating Vision host via 3X-UI API'
        panel.request('panel/api/hosts/add', {'inboundIds': [iid], 'remark': 'vision', 'hosts': [domain],
                      'port': 443, 'security': 'same', 'sni': domain, 'alpn': ['http/1.1'], 'allowInsecure': False})
        stage = 'writing Vision nginx fallback and SNI route'
        site.write_text(fallback_config(domain, fallback)); site.chmod(0o644)
        enabled.symlink_to(site)
        stream.write_text(patched)
        stage = 'validating nginx configuration'
        run('nginx', '-t')
        stage = 'reloading nginx'
        run('systemctl', 'reload', 'nginx')
        stage = 'restarting Xray via 3X-UI API'
        panel.request('panel/api/server/restartXrayService', {})
        stage = 'checking 3X-UI service'
        run('systemctl', 'is-active', '--quiet', 'x-ui')
        stage = 'waiting for Vision inbound readiness'
        wait_inbound(port)
        # Actual trusted HTTPS fallback through public nginx SNI and Xray TLS.
        stage = 'checking trusted HTTPS fallback'
        run('curl', '-q', '-fsS', '--noproxy', '*', '--http1.1', '--resolve', f'{domain}:443:127.0.0.1',
            '--connect-timeout', '2', '--max-time', '3', '--retry', '3', '--retry-delay', '1',
            '--retry-max-time', '5', '--retry-all-errors', f'https://{domain}/')
        return iid
    except Exception as error:
        status = 'failed_unverified'
        rollback_stage = 'restoring nginx files'; rollback_error = ''
        try:
            stream.write_bytes(original)
            enabled.unlink(missing_ok=True); site.unlink(missing_ok=True)
            # Reconcile an uncertain POST response; never delete by an unverified response ID.
            rollback_stage = 'reconciling owned Vision inbound'
            candidates = [r for r in panel.request('panel/api/inbounds/list')['obj'] if r.get('tag') == expected['tag']]
            if len(candidates) > 1:
                raise ValueError('Ambiguous Vision ownership')
            if candidates:
                row = candidates[0]
                settings = row['settings'] if isinstance(row['settings'], dict) else json.loads(row['settings'])
                stream_settings = row['streamSettings'] if isinstance(row['streamSettings'], dict) else json.loads(row['streamSettings'])
                if (any(row.get(k) != expected[k] for k in ('listen', 'port', 'protocol', 'tag'))
                        or settings.get('clients') != [] or stream_settings.get('tlsSettings', {}).get('serverName') != domain):
                    raise ValueError('Vision artifact ownership changed; retained')
                panel.request('panel/api/inbounds/del/' + str(row['id']), {})
            rollback_stage = 'validating and reloading original nginx'
            run('nginx', '-t'); run('systemctl', 'reload', 'nginx')
            rollback_stage = 'restarting original Xray'
            panel.request('panel/api/server/restartXrayService', {})
            run('systemctl', 'is-active', '--quiet', 'x-ui')
            if stream.read_bytes() != original:
                raise ValueError('Stream rollback mismatch')
            status = 'failed_rolled_back'
        except Exception as failure:
            rollback_error = rollback_stage + ': ' + safe_reason(failure)
        raise Failure(status, stage, safe_reason(error), rollback_error) from None


def main():
    if sys.argv[1:2] == ['--render-acme'] and len(sys.argv)==3:
        print(acme_config(sys.argv[2]), end='')
        return
    if sys.argv[1:2] == ['--preflight-nginx'] and len(sys.argv)==4:
        print(nginx_artifact_domain(*sys.argv[2:]))
        return
    helper, domain, path, username, vision, port, fallback, flag = sys.argv[1:]
    spec = importlib.util.spec_from_file_location('awg_session', helper)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='xui-vision-') as directory:
        os.chmod(directory, 0o700)
        panel = module.Panel(f'https://{domain}/{path}/', username, sys.stdin.read(), directory,
                             ['--resolve', f'{domain}:443:127.0.0.1'])
        iid = configure(panel, vision, int(port), int(fallback), '/etc/nginx/stream-enabled/stream.conf',
                        '/etc/nginx/sites-available/vision.conf', '/etc/nginx/sites-enabled/vision.conf',
                        f'/etc/letsencrypt/live/{vision}/fullchain.pem', f'/etc/letsencrypt/live/{vision}/privkey.pem', flag)
        print(json.dumps({'status': 'configured', 'inboundId': iid}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': getattr(error, 'status', 'failed_unverified')}))
        print(str(error) if isinstance(error, Failure) else
              'Vision failed during local API initialization: '+safe_reason(error)+'; rollback=failed_unverified', file=sys.stderr)
        sys.exit(1)
