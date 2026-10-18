#!/bin/bash
# All installer operations happen inside the disposable VM, never on this host.
set -Eeuo pipefail
umask 077
repository=$(git rev-parse --show-toplevel)
ref=$(git rev-parse HEAD)
[[ "$ref" =~ ^[0-9a-f]{40}$ ]]
git diff --quiet HEAD -- x-ui-latest.sh assets
work=$(mktemp -d)
container="xui-fresh-$$"
root_container=""
cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    if [[ -n "$root_container" ]]; then docker rm -f "$root_container" >/dev/null 2>&1 || true; fi
    # Only this invocation's private mktemp directory, never any user directory.
    if [[ -d "$work" ]]; then
        if [[ $EUID == 0 ]]; then rm -rf -- "$work"; else sudo rm -rf -- "$work"; fi
    fi
}
trap cleanup EXIT
date +%s > "$work/started"
secret=()
if [[ -f /etc/ssl/certs/ca-certificates.crt ]]; then
    secret=(--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt)
fi
timeout 8m docker build "${secret[@]}" -t xui-fresh-root -f "$repository/tests/fresh/Dockerfile" "$repository"
timeout 8m docker build "${secret[@]}" -t xui-fresh-tools -f "$repository/tests/systemd/tools.Dockerfile" "$repository"
date +%s > "$work/images.ready"
root_container=$(docker create xui-fresh-root)
docker export "$root_container" -o "$work/rootfs.tar"
git show bf5ce345949c530b97bcf324b7d334332cd33dc9:assets/security/managed.py > "$work/old-security.py"
# Preserve the cloud proxy if present; only hostname/IP mappings, no credentials in argv.
mapfile -t proxy_hosts < <(python3 - <<'PY'
import os, socket
from urllib.parse import urlsplit
hosts={urlsplit(v).hostname for k,v in os.environ.items()
       if k.lower() in ('http_proxy','https_proxy','all_proxy')}
for host in sorted(h for h in hosts if h):
    print(host+':'+socket.gethostbyname(host))
PY
)
network=()
for mapping in "${proxy_hosts[@]}"; do network+=(--add-host "$mapping"); done
docker run --name "$container" --rm --memory=6g --cpus=2 "${network[@]}" \
    -e HTTP_PROXY -e HTTPS_PROXY -e ALL_PROXY -e http_proxy -e https_proxy -e all_proxy \
    -e "XUI_AUTO_REF=$ref" \
    -e CURL_CA_BUNDLE=/run/proxy-ca.pem \
    --mount "type=bind,src=$work,dst=/pilot" \
    --mount "type=bind,src=$repository,dst=/repo,readonly" \
    --mount type=bind,src=/etc/ssl/certs/ca-certificates.crt,dst=/run/proxy-ca.pem,readonly \
    xui-fresh-tools bash -ec \
    'bash /repo/tests/fresh/prepare.sh; date +%s > /pilot/disk.ready; python3 /repo/tests/fresh/acceptance.py'
