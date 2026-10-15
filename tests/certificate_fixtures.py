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


# Frozen pre-fix renderers: independent evidence of released hook bytes.
OLD_PANEL_RENDER = r'''render_certificate_hook() {
    local domain=$1 reality_domain=$2
    {
        printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
        printf 'PANEL_DOMAIN=%q\nREALITY_DOMAIN=%q\n' "$domain" "$reality_domain"
        if [[ "${3:-current}" != legacy ]]; then declare -f check_xray_runtime; fi
        cat <<'HOOK'
panel=0
project=0
read -r -a renewed_domains <<< "${RENEWED_DOMAINS:-}"
for renewed in "${renewed_domains[@]}"; do
    if [[ "$renewed" == "$PANEL_DOMAIN" ]]; then panel=1; project=1; fi
    if [[ "$renewed" == "$REALITY_DOMAIN" ]]; then project=1; fi
done
case "${RENEWED_LINEAGE:-}" in
    "/etc/letsencrypt/live/$PANEL_DOMAIN") panel=1; project=1 ;;
    "/etc/letsencrypt/live/$REALITY_DOMAIN") project=1 ;;
esac
(( project )) || exit 0
nginx -t
systemctl reload nginx
systemctl is-active --quiet nginx
if (( panel )); then
    systemctl restart x-ui
    systemctl is-active --quiet x-ui
fi
HOOK
        if [[ "${3:-current}" != legacy ]]; then
            printf 'if (( panel )); then check_xray_runtime; fi\n'
        fi
    }
}'''

OLD_VISION_RENDER = r'''render_vision_hook() {
    local readiness="--connect-timeout 2 --max-time 3 --retry 4 --retry-delay 1 --retry-max-time 10 --retry-all-errors"
    # Recognize only the exact previous canonical hook for existing installations/archives.
    [[ "${2:-}" != legacy ]] || readiness="--connect-timeout 5 --max-time 20"
    printf '#!/usr/bin/env bash\nset -Eeuo pipefail\nVISION_DOMAIN=%q\n' "$1"
    cat <<'VISIONHOOK'
[[ "${RENEWED_LINEAGE:-}" == "/etc/letsencrypt/live/$VISION_DOMAIN" ]] || exit 0
openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -noout -checkend 0 -checkhost "$VISION_DOMAIN"
cert_key=$(openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -pubkey -noout)
private_key=$(openssl pkey -in "$RENEWED_LINEAGE/privkey.pem" -pubout)
[[ "$cert_key" == "$private_key" ]] || exit 1
# Xray 26.9.30 polls files hourly; ensure the deployed certificate is used now.
systemctl restart x-ui
systemctl is-active --quiet x-ui
curl -q -fsS --noproxy '*' --http1.1 --resolve "$VISION_DOMAIN:443:127.0.0.1" \
VISIONHOOK
    printf '    %s "https://$VISION_DOMAIN/" >/dev/null\n' "$readiness"
}'''

def historical_hook(root, kind, legacy=False):
    renderer = OLD_PANEL_RENDER if kind == 'panel' else OLD_VISION_RENDER
    script = relocate(function('check_xray_runtime') + '\n' + renderer, root)
    command = 'render_certificate_hook example.com reality.example.com' if kind == 'panel' else 'render_vision_hook vision.example.com'
    return subprocess.check_output(['bash', '-c', script + '\n' + command + (' legacy' if legacy else '')], text=True)
