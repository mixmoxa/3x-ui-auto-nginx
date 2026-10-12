"""Small filesystem fixtures shared by renewal and Backup v3 tests."""
import os
from pathlib import Path
import re
import shlex
import subprocess
from configobj import ConfigObj

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / 'x-ui-latest.sh').read_text()
LEGACY = ('@monthly certbot renew --non-interactive --pre-hook "systemctl stop nginx" '
          '--post-hook "systemctl start nginx" > /dev/null 2>&1')


def function(name, source=INSTALLER):
    found = re.findall(r'^' + re.escape(name) + r'\(\)\s*\{.*?^\}', source, re.M | re.S)
    assert len(found) == 1, name
    return found[0]


def relocate(source, root):
    return re.sub(r"(?<![A-Za-z0-9_./])/(?:proc|opt|etc|root|var|lib|usr/local|usr/bin/x-ui|usr/share/nginx|dev/shm)(?=[/\s\"';,)}]|$)",
                  lambda m: str(root) + m[0], source)


def certificates(root, panel='example.com', reality='reality.example.com', mapped=True, extra=()):
    for domain in (panel, reality, *extra):
        live = root / 'etc/letsencrypt/live' / domain
        live.mkdir(parents=True, exist_ok=True)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
                        '-nodes', '-days', '1', '-subj', '/CN=' + domain, '-addext', 'subjectAltName=DNS:' + domain,
                        '-keyout', str(live / 'privkey.pem'), '-out', str(live / 'fullchain.pem')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        config = root / 'etc/letsencrypt/renewal' / (domain + '.conf')
        config.parent.mkdir(parents=True, exist_ok=True)
        cfg = ConfigObj()
        cfg.filename = str(config)
        cfg['version'] = '4.0.0' if mapped else '2.9.0'
        cfg['fullchain'] = str(live / 'fullchain.pem')
        cfg['privkey'] = str(live / 'privkey.pem')
        cfg['renewalparams'] = {'authenticator': 'webroot', 'webroot_path': [str(root / 'var/www/acme')]}
        if mapped:
            cfg['renewalparams']['webroot_map'] = {domain: str(root / 'var/www/acme')}
        cfg.write()
    hook = root / 'etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx'
    hook.parent.mkdir(parents=True, exist_ok=True)
    source = '\n'.join(relocate(function(name), root) for name in ('check_xray_runtime', 'render_certificate_hook'))
    body = subprocess.check_output(['bash', '-c', source + '\nrender_certificate_hook "$1" "$2"',
                                    'fixture', panel, reality], text=True)
    hook.write_text(body)
    executable = root/'usr/local/x-ui/bin/xray-linux-amd64'
    executable.parent.mkdir(parents=True, exist_ok=True)
    if not executable.exists(): executable.write_text('fixture executable')
    proc = root/'proc/43210/exe'; proc.parent.mkdir(parents=True, exist_ok=True)
    if not proc.exists(): proc.symlink_to(executable)
    ss = root/'health-bin/ss'; ss.parent.mkdir(exist_ok=True)
    ss.write_text(f'''#!/bin/sh
case "$*" in
 *-lxnp*) echo 'u_str LISTEN 0 128 {root}/dev/shm/uds2023.sock 0 users:(("xray",pid=43210,fd=1))' ;;
 *) echo 'tcp LISTEN 0 128 127.0.0.1:8443 0.0.0.0:* users:(("xray",pid=43210,fd=2))'; echo 'udp UNCONN 0 128 *:443 *:* users:(("xray",pid=43210,fd=3))' ;;
esac
''')
    ss.chmod(0o755)
    hook.chmod(0o755)
    if os.geteuid() == 0:
        os.chown(hook, 0, 0)
    (root / 'var/www/acme/.well-known/acme-challenge').mkdir(parents=True, exist_ok=True)
    return hook
