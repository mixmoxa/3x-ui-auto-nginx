"""Fresh-install-only, disabled packet-up profile; CDN services remain user-owned."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


PARAMETERS = {
    'mode': 'packet-up', 'xPaddingBytes': '100-1000', 'xPaddingObfsMode': True,
    'xPaddingKey': '_dc', 'xPaddingHeader': 'X-Cache',
    'xPaddingPlacement': 'queryInHeader', 'xPaddingMethod': 'tokenish',
    'uplinkDataPlacement': 'cookie', 'uplinkDataKey': 'edge_data',
    'scMaxEachPostBytes': '2048', 'uplinkHTTPMethod': 'GET',
    'scMaxBufferedPosts': 30, 'scStreamUpServerSecs': '20-80',
    'serverMaxHeaderBytes': 0, 'noSSEHeader': False, 'noGRPCHeader': False,
    'enableXmux': False,
    'sessionIDPlacement': '', 'sessionIDKey': '', 'sessionIDTable': '',
    'sessionIDLength': '', 'seqPlacement': '', 'seqKey': '',
    'scMinPostsIntervalMs': '', 'uplinkChunkSize': 0,
}


def inbound(port, path, flag):
    if not 1024 <= port <= 65535 or not re.fullmatch(r'/[A-Za-z0-9]{10,64}/cookie', path):
        raise ValueError('Invalid XHTTP CDN endpoint')
    return dict(enable=False, listen='127.0.0.1', port=port, protocol='vless',
                remark=flag+' xhttp CDN', tag=f'inbound-{port}',
                settings=dict(clients=[], decryption='none', encryption='none', fallbacks=[]),
                streamSettings=dict(network='xhttp', security='none',
                                    xhttpSettings=dict(path=path, host='', headers={}, **PARAMETERS)),
                sniffing=dict(enabled=True, destOverride=['http', 'tls'], routeOnly=False))


def nginx(port, path):
    inbound(port, path, '')  # Validate all interpolated values.
    # Xray normalizes its base path with a terminal slash before session URLs.
    # Preserve that slash and the entire URI, query and Cookie upstream.
    return f'''# Managed by 3x-ui Auto Nginx: XHTTP CDN
location = {path} {{
    return 307 {path}/$is_args$args;
}}
location ^~ {path}/ {{
    proxy_pass http://127.0.0.1:{port};
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Connection "";
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    add_header Cache-Control "no-store, no-transform" always;
}}
'''


def run(*args):
    subprocess.run(args, check=True, capture_output=True, timeout=30)


def configure(panel, domain, port, path, flag, snippet):
    snippet = Path(snippet)
    if snippet.exists() or snippet.is_symlink():
        raise ValueError('Existing XHTTP CDN snippet; preserved')
    expected = inbound(port, path, flag)
    previous = panel.request('panel/api/inbounds/list')['obj']
    if any(r['tag'] == expected['tag'] or r['port'] == port for r in previous):
        raise ValueError('Conflicting XHTTP CDN endpoint')
    iid = None
    try:
        row = panel.request('panel/api/inbounds/add', expected)['obj']; iid = row['id']
        if any(row.get(k) != expected[k] for k in ('enable', 'listen', 'port', 'protocol', 'tag', 'streamSettings')):
            raise ValueError('Unexpected XHTTP CDN API configuration')
        hosts = panel.request('panel/api/hosts/add', dict(inboundIds=[iid], remark='xhttp CDN',
                      hosts=[domain], port=443, security='tls', fingerprint='firefox',
                      alpn=[], sni=domain, hostHeader=''))['obj']
        expected_host = dict(inboundId=iid, address=domain, port=443, security='tls',
                             fingerprint='firefox', alpn=[], sni=domain, hostHeader='')
        if (len(hosts) != 1 or any(hosts[0].get(k) != value for k, value in expected_host.items()) or
                not re.fullmatch(r'[a-z0-9]{16}', hosts[0].get('groupId', ''))):
            raise ValueError('Unexpected XHTTP CDN Host configuration')
        with snippet.open('x') as output:
            os.chmod(snippet, 0o600)
            output.write(nginx(port, path))
        run('nginx', '-t'); run('systemctl', 'reload', 'nginx')
        # Disabled inbound does not require an Xray restart or become a client target.
        return 'configured'
    except Exception:
        try:
            rows = panel.request('panel/api/inbounds/list')['obj']
            owned = [r for r in rows if r['tag'] == expected['tag'] and r['id'] not in {p['id'] for p in previous}]
            if len(owned) > 1: raise ValueError('Ambiguous XHTTP CDN creation')
            for row in owned:
                if any(row.get(k) != expected[k] for k in ('enable', 'listen', 'port', 'protocol', 'tag', 'settings', 'streamSettings')):
                    raise ValueError('XHTTP CDN ownership changed')
                panel.request('panel/api/inbounds/del/'+str(row['id']), {})
            if snippet.exists():
                if snippet.is_symlink() or snippet.read_text() != nginx(port, path):
                    raise ValueError('XHTTP CDN snippet ownership changed')
                snippet.unlink()
            run('nginx', '-t'); run('systemctl', 'reload', 'nginx')
            run('systemctl', 'is-active', '--quiet', 'x-ui')
            if any(r['tag'] == expected['tag'] for r in panel.request('panel/api/inbounds/list')['obj']):
                raise ValueError('XHTTP CDN rollback did not remove inbound')
            return 'failed_rolled_back'
        except Exception:
            return 'failed_unverified'


def main():
    helper, domain, panel_path, port, path, flag = sys.argv[1:]
    spec = importlib.util.spec_from_file_location('panel_api', helper)
    api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
    username, password = sys.stdin.read().split('\0', 1)
    with tempfile.TemporaryDirectory(prefix='xui-cdn-') as directory:
        os.chmod(directory, 0o700)
        panel = api.Panel(f'https://{domain}/{panel_path}/', username, password, directory,
                          ['--resolve', f'{domain}:443:127.0.0.1'])
        status = configure(panel, domain, int(port), path, flag,
                           '/etc/nginx/snippets/x-ui-auto-optional/xhttp-cdn.conf')
        print(status)
        return 0 if status == 'configured' else 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        print('failed_unverified')
        sys.exit(1)
