#!/usr/bin/env bash
# Shared integrated AdGuard Home contract (installer and Backup v3).
AGH_VERSION=v0.107.80
AGH_DIR=/opt/AdGuardHome
AGH_SNIPPET=/etc/nginx/snippets/x-ui-auto-optional/adguard.conf

agh_release() {
    case "$1" in
        amd64|x86_64) AGH_ARCH=amd64; AGH_SHA=28593bc761d71469abdbc6f39ca42cbed763ec92b63082c729177b037ed51d18 ;;
        arm64|aarch64) AGH_ARCH=arm64; AGH_SHA=d5e17d0d724418ddef8b7723ed8ade7eef4e621ec5b0e43a341859cca71a3d8f ;;
        *) return 1 ;;
    esac
}

# Legacy v0.107.79 executable hashes; newer binaries use vendor GPG signatures.
agh_binary_hash() {
    case "$1" in
        amd64|x86_64) printf '%s\n' 7e247573e63ce771a5925d16ca4ca9344e6e888673244289dc302f0fdfdfbf4e ;;
        arm64|aarch64) printf '%s\n' 64a9b6fc6269247f1973cddbf285aa6ce866d11bd29546b0f4135ba31d2283c8 ;;
        *) return 1 ;;
    esac
}

agh_trusted_key() {
    local key="$AGH_DIR/AdGuardHome-public.gpg" fingerprint
    [[ -f "$key" && ! -L "$key" ]] || return 1
    fingerprint=$(gpg --batch --no-default-keyring --keyring "$key" --with-colons --fingerprint 2>/dev/null |
        awk -F: '$1 == "pub" { count++ } $1 == "fpr" && !seen++ { value=$10 } END { if (count == 1) print value }') || return 1
    [[ "$fingerprint" == "28645AC9776EC4C00BCE2AFC0FE641E7235E2EC6" ]]
}

agh_verify_binary() {
    local expected actual
    [[ -f "$AGH_DIR/AdGuardHome" && ! -L "$AGH_DIR/AdGuardHome" && -x "$AGH_DIR/AdGuardHome" ]] || return 1
    expected=$(agh_binary_hash "$1") || return 1
    actual=$(sha256sum "$AGH_DIR/AdGuardHome") || return 1
    [[ "${actual%% *}" != "$expected" ]] || return 0
    [[ -f "$AGH_DIR/AdGuardHome.sig" && ! -L "$AGH_DIR/AdGuardHome.sig" ]] || return 1
    agh_trusted_key &&
        gpgv --keyring "$AGH_DIR/AdGuardHome-public.gpg" \
            "$AGH_DIR/AdGuardHome.sig" "$AGH_DIR/AdGuardHome" >/dev/null 2>&1
}

agh_binary() {
    local version major minor patch baseline=79
    agh_verify_binary "${AGH_ARCH:-$(uname -m)}" || return 1
    version=$("$AGH_DIR/AdGuardHome" --version) || return 1
    [[ "$version" =~ ^AdGuard\ Home,\ version\ v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || return 1
    major=${BASH_REMATCH[1]} minor=${BASH_REMATCH[2]} patch=${BASH_REMATCH[3]}
    [[ "${AGH_INITIAL_VERSION:-}" != v0.107.80 ]] || baseline=80
    (( major > 0 || minor > 107 || (minor == 107 && patch >= baseline) )) || return 1
    AGH_RUNNING_VERSION="v${major}.${minor}.${patch}"
}

agh_config() {
    [[ -d "$AGH_DIR" && ! -L "$AGH_DIR" && -f "$AGH_DIR/AdGuardHome.yaml" && ! -L "$AGH_DIR/AdGuardHome.yaml" &&
       -f "$AGH_DIR/managed.json" && ! -L "$AGH_DIR/managed.json" ]] || return 1
    local values
    values=$(python3 - "$AGH_DIR" "${AGH_DATA_ROOT:-$AGH_DIR}" <<'PY'
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1])
data_root = pathlib.Path(sys.argv[2])
m = json.loads((root / 'managed.json').read_text())
if not (m['version'] in ('v0.107.79', 'v0.107.80') and m['arch'] in ('amd64', 'arm64')):
    raise ValueError('Invalid AGH version/architecture')
enabled = m.get('updates_enabled', False)
if type(enabled) is not bool:
    raise ValueError('Invalid AGH native-update contract')
if not (re.fullmatch(r'adg-[A-Za-z0-9]{12}', m['path'])):
    raise ValueError('Invalid AGH admin prefix')
domain = m['domain']
if not (isinstance(domain, str) and len(domain) <= 253 and '.' in domain):
    raise ValueError('Invalid AGH domain')
if not (all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in domain.split('.'))):
    raise ValueError('Invalid AGH domain labels')
if not (type(m['web_port']) is int and type(m['dns_port']) is int):
    raise ValueError('Invalid AGH integer ports')
if not (10000 <= m['web_port'] <= 65535 and 10000 <= m['dns_port'] <= 65535):
    raise ValueError('Invalid AGH high ports')
if not (m['web_port'] != m['dns_port']):
    raise ValueError('Invalid AGH distinct ports')
# Read only managed scalar/list fields in the canonical YAML written by AGH.
# Unrecognized representations fail closed; native --check-config handles YAML.
s = (root / 'AdGuardHome.yaml').read_text()
s = '\n'.join(line for line in s.splitlines() if not line.lstrip().startswith('#')) + '\n'
def section(name):
    matches = re.findall(r'^' + name + r':\s*\n((?:[ \t].*\n|\n)*)', s, re.M)
    if len(matches) != 1:
        raise ValueError('Invalid AGH required YAML section')
    return matches[0]
def indent(text):
    widths = [len(m[1]) for m in re.finditer(r'^( +)\S', text, re.M)]
    return ' ' * min(widths) if widths else ''
def value(text):
    # Bounded plain/quoted scalar forms, with optional YAML comments. Do not
    # interpret comments inside quotes as part of a different managed path.
    match = re.fullmatch(r"(?:'([^']*)'|\"([^\"\\]*)\"|([^#'\"]*?))(?:\s+#.*)?\s*", text.strip())
    if match is None:
        raise ValueError('Unsupported AGH managed scalar representation')
    return next(part for part in match.groups() if part is not None).strip()
def scalar(text, key):
    matches = re.findall(r'^' + indent(text) + key + r':\s*(.*?)\s*$', text, re.M)
    if len(matches) != 1:
        raise ValueError('Invalid AGH unique YAML field')
    return value(matches[0])
def nested(text, key):
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip() == indent(text) + key + ':']
    if len(starts) != 1:
        raise ValueError('Invalid AGH required nested section')
    result = []
    for line in lines[starts[0]+1:]:
        if line.strip() and len(line)-len(line.lstrip()) <= len(indent(text)):
            break
        result.append(line)
    return ''.join(result)
schemas = re.findall(r'^schema_version:\s*([0-9]+)\s*(?:#.*)?$', s, re.M)
if len(schemas) != 1 or int(schemas[0]) < 34:
    raise ValueError('Invalid AGH schema')
http, dns, tls = section('http'), section('dns'), section('tls')
if not (scalar(http, 'address') == '127.0.0.1:' + str(m['web_port'])):
    raise ValueError('Invalid AGH loopback HTTP address')
if not (scalar(dns, 'port') == str(m['dns_port'])):
    raise ValueError('Invalid AGH DNS port')
hosts = re.findall(r'^' + indent(dns) + r'bind_hosts:\s*\n((?: +- .*\n)+)', dns, re.M)
if not (len(hosts) == 1 and [value(x) for x in re.findall(r'^ +- (.*)$', hosts[0], re.M)] == ['127.0.0.1']):
    raise ValueError('Invalid AGH loopback DNS bind')
if not (scalar(tls, 'enabled') == 'false'):
    raise ValueError('Invalid AGH native TLS disabled')
if scalar(nested(http, 'doh'), 'insecure_enabled') != 'true':
    raise ValueError('Invalid AGH DoH insecure bridge')
for part in ('querylog', 'statistics'):
    p = section(part) if re.search(r'^' + part + ':', s, re.M) else ''
    if p and re.search(r'^' + indent(p) + 'dir_path:', p, re.M):
        directory = scalar(p, 'dir_path')
        if not (not directory or pathlib.Path(directory).resolve().is_relative_to(data_root.resolve())):
            raise ValueError('Invalid AGH managed data directory')
for k in ('web_port', 'dns_port', 'path', 'domain', 'arch', 'version'):
    print(m[k])
print('yes' if enabled else 'no')
PY
    ) || return 1
    local -a fields
    mapfile -t fields <<< "$values"
    AGH_WEB_PORT=${fields[0]} AGH_DNS_PORT=${fields[1]} AGH_PATH=${fields[2]} AGH_DOMAIN=${fields[3]} AGH_ARCH=${fields[4]}
    AGH_INITIAL_VERSION=${fields[5]} AGH_UPDATES_ENABLED=${fields[6]}
    agh_binary && "$AGH_DIR/AdGuardHome" -c "$AGH_DIR/AdGuardHome.yaml" -w "$AGH_DIR" --check-config
}

agh_unit() {
    local unit
    unit=$(systemctl cat AdGuardHome) || return 1
    grep -Eq '^ExecStart=' <<< "$unit" || return 1
    python3 - "$AGH_DIR" "$unit" "$AGH_UPDATES_ENABLED" <<'PY'
import shlex, sys
root, unit, updates = sys.argv[1:]
lines = [l for l in unit.splitlines() if l.startswith('ExecStart=')]
if not (len(lines) == 1):
    raise ValueError('Invalid AGH unique ExecStart')
args = shlex.split(lines[0].split('=', 1)[1])
if not (args[0] == root + '/AdGuardHome'):
    raise ValueError('Invalid AGH service executable')
# Accept the short/long and --name=value spellings of the same bounded
# service contract. Reject duplicate or unknown options rather than counting
# words, which makes harmless serialization changes look like foreign units.
aliases = {'-c': 'config', '--config': 'config', '-w': 'work', '--work-dir': 'work',
           '-s': 'service', '--service': 'service', '--no-check-update': 'disabled'}
options = {}
tokens = iter(args[1:])
for token in tokens:
    key, equals, value = token.partition('=')
    name = aliases.get(key)
    if name is None or name in options:
        raise ValueError('Invalid AGH service option')
    if name == 'disabled':
        value = value if equals else 'true'
        if value not in ('true', 'false'):
            raise ValueError('Invalid AGH native-update flag')
    elif not equals:
        value = next(tokens, None)
    options[name] = value
if options.get('config') != root + '/AdGuardHome.yaml':
    raise ValueError('Invalid AGH explicit config file')
if options.get('work') != root:
    raise ValueError('Invalid AGH explicit work directory')
legacy = updates == 'no'
if (options.get('disabled', 'false') == 'true') != legacy:
    raise ValueError('Invalid AGH native-update flag')
if options.get('service') != 'run':
    raise ValueError('Invalid AGH service run action')
# Upstream records the install caller's cwd as systemd WorkingDirectory.
# AGH's effective data directory is the explicit -w/--work-dir checked above;
# do not reject the official unit merely because those two directories differ.
PY
}

agh_install_trust_key() {
    local fingerprint="28645AC9776EC4C00BCE2AFC0FE641E7235E2EC6"
    curl --noproxy '*' -fsSL --connect-timeout 10 --max-time 45 \
        "https://keys.openpgp.org/vks/v1/by-fingerprint/$fingerprint" -o "$AGH_TEMP/adguard-key.asc" || return 1
    gpg --batch --no-default-keyring --keyring "$AGH_TEMP/adguard-key.gpg" \
        --import "$AGH_TEMP/adguard-key.asc" >/dev/null 2>&1 || return 1
    install -o root -g root -m 0600 "$AGH_TEMP/adguard-key.gpg" \
        "$AGH_DIR/AdGuardHome-public.gpg" || return 1
    agh_trusted_key
}

agh_install_service() {
    local attempt
    local -a update_flags=()
    agh_config || return 1
    [[ "$AGH_UPDATES_ENABLED" == yes ]] || update_flags+=(--no-check-update)
    "$AGH_DIR/AdGuardHome" -c "$AGH_DIR/AdGuardHome.yaml" -w "$AGH_DIR" "${update_flags[@]}" -s install &&
        systemctl daemon-reload && agh_unit && systemctl enable --now AdGuardHome &&
        systemctl is-active --quiet AdGuardHome || return 1
    # systemd start may return before the application has bound its sockets.
    for attempt in {1..20}; do
        agh_listeners 2>/dev/null && return 0
        sleep 0.25
    done
    return 1
}

agh_snippet() {
    local client_route=''
    if [[ "${1:-}" != legacy ]]; then
        # AdGuard Home v0.107.79 ValidateClientID: one hostname label, 1..63 bytes.
        client_route=$'\n'$(cat <<EOFCLIENT
location ~ "^/dns-query/[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\$" {
    limit_except GET POST { deny all; }
    proxy_pass http://127.0.0.1:${AGH_WEB_PORT};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_buffering off;
    proxy_intercept_errors off;
    access_log off;
}
EOFCLIENT
        ) || return 1
    fi
    cat <<EOFNG
# Integrated AdGuard Home (project-owned).
location = /dns-query {
    limit_except GET POST { deny all; }
    proxy_pass http://127.0.0.1:${AGH_WEB_PORT};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_buffering off;
    proxy_intercept_errors off;
    access_log off;
}
location = /${AGH_PATH} { return 302 /${AGH_PATH}/; }
location ^~ /${AGH_PATH}/ {
    proxy_pass http://127.0.0.1:${AGH_WEB_PORT}/;
    proxy_redirect / /${AGH_PATH}/;
    proxy_cookie_path / /${AGH_PATH}/;
    proxy_cookie_flags agh_session secure;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_intercept_errors off;
    add_header X-Robots-Tag "noindex, nofollow" always;
}${client_route}
EOFNG
}

agh_listeners() {
    local pid listeners
    pid=$(systemctl show -p MainPID --value AdGuardHome) || return 1
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    listeners=$(ss -H -lntup) || return 1
    python3 - "$pid" "$AGH_WEB_PORT" "$AGH_DNS_PORT" "$listeners" <<'PY'
import sys
pid, web, dns, listing = sys.argv[1:]
owned = [l.split() for l in listing.splitlines() if 'pid=' + pid + ',' in l]
if not owned:
    raise ValueError('Invalid AGH owned listeners')
# ss -lu includes outbound UDP sockets bound to ephemeral wildcard ports.
# Check TCP listeners and only UDP ports managed by AGH (plus public DNS/53).
service = [l for l in owned if l[0].startswith('tcp') or
           (l[0].startswith('udp') and l[4].rsplit(':', 1)[-1] in (web, dns, '53'))]
if not all(l[4].startswith('127.0.0.1:') for l in service):
    raise ValueError('Invalid AGH loopback listeners')
if {l[4] for l in service} != {'127.0.0.1:' + web, '127.0.0.1:' + dns}:
    raise ValueError('Invalid AGH listener endpoints')
if not any(l[0] == 'tcp' and l[4].endswith(':' + web) for l in service):
    raise ValueError('Invalid AGH TCP web socket')
if not any(l[0] == 'udp' and l[4].endswith(':' + dns) for l in service):
    raise ValueError('Invalid AGH UDP DNS socket')
PY
}

agh_doh_probe() {
    local url=$1 resolve=${2:-} directory result
    directory=$(mktemp -d) || return 1
    local -a options=()
    [[ -z "$resolve" ]] || options+=(--resolve "$resolve")
    result=$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 15 "${options[@]}" \
        -H 'Accept: application/dns-message' -D "$directory/headers" -o "$directory/body" -w '%{http_code}' \
        "${url}?dns=AAABAAABAAAAAAAAA3d3dwdleGFtcGxlA2NvbQAAAQAB") || { rm -rf "$directory"; return 1; }
    [[ "$result" == 200 ]] && grep -iqE '^Content-Type: application/dns-message\s*' "$directory/headers" &&
        python3 - "$directory/body" <<'PY'
import pathlib, struct, sys
packet = pathlib.Path(sys.argv[1]).read_bytes()
if not (len(packet) >= 12):
    raise ValueError('Invalid AGH DNS response length')
_, flags, questions, answers, _, _ = struct.unpack('!6H', packet[:12])
if not (flags & 0x8000 and not flags & 15 and questions == 1 and answers > 0):
    raise ValueError('Invalid AGH successful DNS response')
PY
    result=$?
    rm -rf "$directory"
    return "$result"
}

agh_dns_probe() {
    python3 - "$AGH_DNS_PORT" <<'PY'
import secrets, socket, struct, sys
ident = secrets.token_bytes(2)
query = ident + bytes.fromhex('0100000100000000000003777777076578616d706c6503636f6d0000010001')
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.settimeout(10)
    sock.connect(('127.0.0.1', int(sys.argv[1])))
    sock.send(query)
    response = sock.recv(65535)
if len(response) < 12 or response[:2] != ident:
    raise ValueError('Invalid AGH native DNS response')
_, flags, questions, answers, _, _ = struct.unpack('!6H', response[:12])
if not (flags & 0x8000 and not flags & 0x020f and questions == 1 and answers > 0):
    raise ValueError('Invalid AGH native DNS result')
PY
}

agh_health() {
    agh_config && agh_unit && systemctl is-active --quiet AdGuardHome && agh_listeners || return 1
    local expected body backend
    expected=$(agh_snippet) || return 1
    [[ -f "$AGH_SNIPPET" && ! -L "$AGH_SNIPPET" ]] || return 1
    body=$(cat "$AGH_SNIPPET") || return 1
    [[ "$body" == "$expected" || "$body" == "$(agh_snippet legacy)" ]] || return 1
    agh_doh_probe "http://127.0.0.1:${AGH_WEB_PORT}/dns-query" || return 1
    agh_doh_probe "https://${AGH_DOMAIN}/dns-query" "${AGH_DOMAIN}:443:127.0.0.1" || return 1
    backend=$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 15 "http://127.0.0.1:${AGH_WEB_PORT}/login.html") || return 1
    body=$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 15 \
        --resolve "${AGH_DOMAIN}:443:127.0.0.1" "https://${AGH_DOMAIN}/${AGH_PATH}/login.html") || return 1
    [[ "$body" == "$backend" && "$body" == *'<html'* && "$body" == *'src="login.'* ]]
}
