#!/usr/bin/env bash
# Managed 3x-ui Auto Nginx backup: same-host rollback or clean-host recovery, same OS/arch.
# Usage: x-ui-backup {backup|restore <archive>|list|update-hooks}
set -Eeuo pipefail
umask 077

BACKUP_STORE=/var/backups/x-ui
DB=/etc/x-ui/x-ui.db
XRAY_DIR=/usr/local/x-ui/bin
SYSCTL_FILE=/etc/sysctl.d/99-3x-ui-pro.conf
XHTTP_SOCKET=/dev/shm/uds2023.sock
LEGACY_CERTBOT_CRON='@monthly certbot renew --non-interactive --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx" > /dev/null 2>&1'
PACKAGES=(nginx-full certbot sqlite3 curl wget jq ufw
          netcat-openbsd mtr python3 python3-configobj python3-cryptography libcap2-bin ca-certificates openssl procps iproute2 tar gzip tzdata)
RUNTIME_PATHS=(/etc/x-ui /usr/local/x-ui /usr/bin/x-ui)
TREE_PATHS=(/opt/AdGuardHome /etc/nginx /etc/letsencrypt /root/cert /usr/local/lib/3x-ui-pro
            /var/www/html /var/www/subpage)
EXTRA_PATHS=(/etc/systemd/system/x-ui.service /etc/systemd/system/mtr-backend.service
             /var/www/diagnostics/index.html /var/www/diagnostics/speedtest.js
             /var/www/diagnostics/speedtest_worker.js "$SYSCTL_FILE")
REQUIRED_PATHS=("$DB" /usr/local/x-ui/x-ui /usr/bin/x-ui /etc/nginx/nginx.conf
                /etc/letsencrypt /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx /usr/local/lib/3x-ui-pro/mtr-backend.py
                /var/www/html /var/www/subpage "${EXTRA_PATHS[@]:0:5}")
STAGING= OUTPUT= STAGE=preflight
BACKUP_FINISHED=0 RESUME_XUI=0 APT_UPDATED=0
RESUME_CERTBOT_TIMER=0
RESUME_AGH=0 ADGUARD_HOME=false AGH_ARCH=
RESTORE_RECOVERY=0 RESTORE_MUTATED=0 ROLLBACK_DIR=
declare -A OLD_ACTIVE=() OLD_ENABLED=()
declare -A RESTORED_ACTIVE=() RESTORED_ENABLED=()
BACKUP_SERVICE_STATES=

stage() { STAGE=$*; printf '\n==> %s\n' "$*"; }
ok()    { printf '[OK] %s\n' "$*"; }
warn()  { printf '[WARN] %s\n' "$*" >&2; }
die()   { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
require_root() { [[ $EUID -eq 0 ]] || die 'Run x-ui-backup as root.'; }

cleanup() {
    local result=$?
    trap - EXIT ERR
    if (( RESTORE_RECOVERY )); then
        # Retain the original restore failure even when recovery succeeds.
        result=1
        set +e
        if recover_restore_target; then
            warn 'Previous managed state/service states restored and checked; restore failed.'
            [[ -z "$ROLLBACK_DIR" ]] || rm -rf -- "$ROLLBACK_DIR"
        else
            warn "Automatic rollback could not be verified. Private recovery material: ${ROLLBACK_DIR:-not created}. Inspect nginx -t and systemctl status x-ui/nginx/AdGuardHome before retrying."
        fi
        RESUME_CERTBOT_TIMER=0
    fi
    if (( RESUME_XUI )); then
        if systemctl start x-ui && systemctl is-active --quiet x-ui; then
            ok 'x-ui returned to its original active state after failure'
        else
            printf '[FAIL] Cannot recover x-ui; run systemctl start x-ui.\n' >&2
            result=1
        fi
    fi
    if (( RESUME_AGH )); then
        systemctl start AdGuardHome && systemctl is-active --quiet AdGuardHome || { warn 'Cannot recover AdGuardHome; run systemctl start AdGuardHome.'; result=1; }
    fi
    resume_certbot_timer || { warn 'Cannot restore certbot.timer; run systemctl start certbot.timer.'; result=1; }
    if [[ -n "$OUTPUT" ]] && (( ! BACKUP_FINISHED )); then
        rm -f -- "$OUTPUT" || { warn 'Cannot remove incomplete archive'; result=1; }
    fi
    if [[ -n "$STAGING" ]]; then
        rm -rf -- "$STAGING" || { warn 'Cannot remove private staging directory'; result=1; }
    fi
    exit "$result"
}

cleanup_adguard() {
    # Only the upstream-generated project unit is owned here; never run an old binary.
    if systemctl cat AdGuardHome >/dev/null 2>&1 || systemctl is-active --quiet AdGuardHome 2>/dev/null; then
        local fragment
        fragment=$(systemctl show -p FragmentPath --value AdGuardHome) || return 1
        [[ "$fragment" == /etc/systemd/system/AdGuardHome.service ]] || return 1
        systemctl stop AdGuardHome && systemctl disable AdGuardHome || return 1
        systemctl is-active --quiet AdGuardHome && return 1
        rm -f /etc/systemd/system/AdGuardHome.service || return 1
        systemctl daemon-reload || return 1
    fi
    rm -rf /opt/AdGuardHome || return 1
    rm -f /etc/nginx/snippets/adguard.conf /etc/nginx/snippets/x-ui-auto-optional/adguard.conf || return 1
    rm -f /usr/local/lib/3x-ui-pro/managed-adguard.sh
}

load_adguard_backup_state() {
    ADGUARD_HOME=false
    if [[ -e /opt/AdGuardHome || -e /etc/systemd/system/AdGuardHome.service ||
          -e /etc/nginx/snippets/adguard.conf || -e /etc/nginx/snippets/x-ui-auto-optional/adguard.conf ||
          -e /usr/local/lib/3x-ui-pro/managed-adguard.sh ]] ||
       systemctl is-active --quiet AdGuardHome 2>/dev/null || systemctl is-enabled --quiet AdGuardHome 2>/dev/null ||
       grep -RqE 'location.*(/adg-|/dns-query)' /etc/nginx/sites-available /etc/nginx/snippets 2>/dev/null; then
        [[ -f /usr/local/lib/3x-ui-pro/managed-adguard.sh && ! -L /usr/local/lib/3x-ui-pro/managed-adguard.sh &&
           -f /etc/nginx/snippets/x-ui-auto-optional/adguard.conf && ! -e /etc/nginx/snippets/adguard.conf ]] || die 'Partial AdGuard Home state.'
        . /usr/local/lib/3x-ui-pro/managed-adguard.sh
        agh_config && agh_unit || die 'AdGuard Home configuration/service contract is invalid.'
        [[ "$(cat "$AGH_SNIPPET")" == "$(agh_snippet)" ]] || die 'AdGuard Home nginx state is inconsistent.'
        [[ "$AGH_ARCH" == "$ARCH" ]] || die 'AdGuard Home architecture does not match the host.'
        ADGUARD_HOME=true
    fi
}

check_python_dependencies() {
    python3 -c 'import configobj, cryptography' || die 'Required Python modules are unavailable: configobj, cryptography.'
}

pause_certbot_timer() {
    local timer_state service_state
    timer_state=$(systemctl is-active certbot.timer) || :
    case "$timer_state" in
        active) RESUME_CERTBOT_TIMER=1 ;;
        inactive|failed) ;;
        *) die 'Cannot determine certbot.timer state; retry after checking systemd.' ;;
    esac
    if (( RESUME_CERTBOT_TIMER )); then
        systemctl stop certbot.timer || die 'Cannot pause certbot.timer.'
    fi
    service_state=$(systemctl is-active certbot.service) || :
    case "$service_state" in
        inactive|failed) ;;
        *) die 'Certbot renewal is running or its state is unknown. No certificate state was copied or replaced; retry after it finishes.' ;;
    esac
}

resume_certbot_timer() {
    (( RESUME_CERTBOT_TIMER )) || return 0
    systemctl start certbot.timer && systemctl is-active --quiet certbot.timer || return 1
    RESUME_CERTBOT_TIMER=0
}

prepare_store() {
    [[ ! -L "$BACKUP_STORE" ]] || die 'Backup store must not be a symlink.'
    mkdir -p "$BACKUP_STORE"
    chown root:root "$BACKUP_STORE"
    chmod 0700 "$BACKUP_STORE"
    STAGING=$(mktemp -d "$BACKUP_STORE/.${1}-XXXXXX")
}

host_identity() {
    # os-release is trusted local OS state, never taken from the archive.
    . /etc/os-release
    OS_ID=$ID OS_VERSION=$VERSION_ID
    ARCH=$(dpkg --print-architecture)
    case "$OS_ID:$OS_VERSION" in
        ubuntu:24.04|ubuntu:26.04|debian:13) ;;
        *) die 'Supported OS: Ubuntu 24.04/26.04 or Debian 13.' ;;
    esac
}

install_missing_packages() {
    local package status missing=()
    for package in "$@"; do
        status=$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null) || status=
        [[ "$status" == 'install ok installed' ]] || missing+=("$package")
    done
    if (( ${#missing[@]} )); then
        stage "Installing missing dependencies: ${missing[*]}"
        if (( ! APT_UPDATED )); then
            apt-get update -qq || die 'Cannot update package lists; managed files have not been replaced.'
            APT_UPDATED=1
        fi
        DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing[@]}" ||
            die 'Dependency installation failed; managed files have not been replaced.'
    fi
}

quick_check() {
    local result
    [[ -f "$1" && ! -L "$1" ]] || die 'SQLite database is missing or is a symlink.'
    result=$(sqlite3 "$1" 'PRAGMA quick_check;' 2>/dev/null) || die 'SQLite quick_check failed.'
    [[ "$result" == ok ]] || die 'SQLite quick_check found database corruption.'
    ok 'SQLite database is consistent'
}

# Validate before extraction. Only managed paths and their parent directories are
# accepted; links cannot redirect extraction or target arbitrary OS/security files.
validate_archive() {
    gzip -t -- "$1" || die 'Archive gzip integrity check failed.'
    python3 - "$1" "$DB" "$XRAY_DIR" "${REQUIRED_PATHS[@]}" -- \
        "${RUNTIME_PATHS[@]:0:2}" "${TREE_PATHS[@]}" -- \
        /usr/bin/x-ui "${EXTRA_PATHS[@]}" <<'PY'
import ipaddress, json, posixpath, sys, tarfile
from pathlib import PurePosixPath
archive, db, xray_dir, *paths = sys.argv[1:]
split = paths.index('--')
required, paths = paths[:split], paths[split + 1:]
split = paths.index('--')
trees = [p.lstrip('/') for p in paths[:split]]
files = [p.lstrip('/') for p in paths[split + 1:]]
allowed = trees + files
required = ['files/' + p.lstrip('/') for p in required]
def fail(message):
    raise ValueError(message)
def clean(name):
    if name.startswith('./'):
        name = name[2:]
    name = name.rstrip('/')
    if not name or name.startswith('/') or any(ord(c) < 32 for c in name):
        fail('Unsafe archive member name')
    if any(p in ('', '.', '..') for p in name.split('/')):
        fail('Unsafe archive member path')
    return name
def managed(path):
    return path in files or any(path == p or path.startswith(p + '/') for p in trees)
def permitted(name, directory):
    if name == 'meta.json':
        return not directory
    if name == 'files':
        return directory
    if not name.startswith('files/'):
        return False
    path = name[6:]
    return managed(path) or (directory and any(p.startswith(path + '/') for p in allowed))
try:
    with tarfile.open(archive, 'r:gz') as tar:
        metadata = tar.getmember('meta.json')
        if not metadata.isfile() or metadata.size > 16384:
            fail('Invalid metadata file')
        meta = json.load(tar.extractfile(metadata))
        if isinstance(meta, dict) and type(meta.get('format_version')) is int and meta['format_version'] == 2:
            fail('Legacy backup format 2 is not supported by this release. Restore it with the matching older x-ui-backup version.')
        if not isinstance(meta, dict):
            fail('Metadata must be an object')
        if type(meta.get('adguard_home')) is not bool:
            fail('Missing boolean adguard_home metadata')
        if 'service_states' in meta:
            states = meta['service_states']
            services = {'x-ui', 'nginx', 'mtr-backend', 'certbot.timer'}
            if meta['adguard_home']: services.add('AdGuardHome')
            if not isinstance(states, dict) or set(states) != services:
                fail('Invalid service-state metadata: expected managed services only')
            for state in states.values():
                if (not isinstance(state, dict) or set(state) != {'active', 'enabled'} or
                    state['active'] not in ('active', 'inactive', 'failed') or type(state['enabled']) is not bool):
                    fail('Invalid service-state metadata: expected active/inactive/failed and boolean enabled')
        agh_tree = '/opt/AdGuardHome'.lstrip('/')
        agh_helper = '/usr/local/lib/3x-ui-pro/managed-adguard.sh'.lstrip('/')
        agh_snippet = '/etc/nginx/snippets/x-ui-auto-optional/adguard.conf'.lstrip('/')
        if meta['adguard_home']:
            if meta.get('adguard_version') != 'v0.107.79' or meta.get('adguard_arch') not in ('amd64', 'arm64') or meta['adguard_arch'] != meta.get('arch'):
                fail('Invalid AdGuard Home release metadata')
            required += ['files/' + p for p in (agh_tree, agh_tree + '/AdGuardHome', agh_tree + '/AdGuardHome.yaml', agh_tree + '/managed.json', agh_helper, agh_snippet)]
        members = {}
        for member in tar:
            name = clean(member.name)
            if not meta['adguard_home'] and (name == 'files/' + agh_tree or name.startswith('files/' + agh_tree + '/') or name in ('files/' + agh_helper, 'files/' + agh_snippet)):
                fail('AdGuard Home state prohibited when metadata is false')
            if name.startswith('files/' + agh_tree + '/') and not (member.isfile() or member.isdir()):
                fail('AdGuard Home tree cannot contain archive links')
            if name in ('files/' + agh_helper, 'files/' + agh_snippet) and not member.isfile():
                fail('AdGuard Home helper/snippet must be regular files')
            if name == 'files/etc/systemd/system/AdGuardHome.service':
                fail('AdGuard Home service must be recreated, not archived')
            if name in members or not permitted(name, member.isdir()):
                fail('Unexpected or duplicate archive member')
            if name.startswith('files/') and name[6:] in files and not member.isfile():
                fail('Managed files must be regular files')
            if name.startswith('files/') and name[6:] in trees and not member.isdir():
                fail('Managed trees must be directories')
            if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                fail('Special files are not allowed in backups')
            members[name] = member
        for name, member in members.items():
            for parent in PurePosixPath(name).parents:
                other = members.get(str(parent))
                if other and not other.isdir():
                    fail('Archive member traverses a non-directory')
            if member.issym():
                if not name.startswith('files/') or name[6:] in allowed:
                    fail('Managed roots must not be symbolic links')
                if any(ord(c) < 32 for c in member.linkname):
                    fail('Unsafe symbolic link')
                target = posixpath.normpath(posixpath.join('/' + posixpath.dirname(name[6:]), member.linkname))
                if not (managed(target.lstrip('/')) or target.startswith('/usr/share/nginx/modules-available/')
                        or target.startswith('/usr/lib/nginx/modules/')):
                    fail('Symbolic link points outside managed state')
            if member.islnk():
                target = members.get(clean(member.linkname))
                if not target or not target.isfile():
                    fail('Invalid hard link')
        for name in ['meta.json', *required]:
            if name not in members:
                fail('Archive is missing required managed state')
            if name in required and not (members[name].isdir() if name[6:] in trees else members[name].isfile()):
                fail('Required managed state has the wrong file type')
        for name in ('meta.json', 'files/' + db.lstrip('/')):
            if not members[name].isfile():
                fail('Metadata and DB must be regular files')
        xray_prefix = 'files/' + xray_dir.lstrip('/') + '/xray-linux-'
        if not any(name.startswith(xray_prefix) and member.isfile() and member.mode & 0o111
                   for name, member in members.items()):
            fail('Archive is missing the Xray executable')
        if members['meta.json'].size > 16384:
            fail('Unexpected metadata size')
        meta = json.load(tar.extractfile(members['meta.json']))
        if not isinstance(meta, dict):
            fail('Metadata must be an object')
        keys = ('created', 'hostname', 'os_id', 'os_version', 'arch', 'x_ui_version', 'xray_version', 'source_ipv4')
        if type(meta.get('format_version')) is not int or meta['format_version'] != 3:
            fail('Unsupported backup format; expected format_version=3')
        if any(not isinstance(meta.get(k), str) for k in keys):
            fail('Incomplete backup metadata')
        if meta['source_ipv4']:
            ipaddress.IPv4Address(meta['source_ipv4'])
except (ValueError, OSError, tarfile.TarError, KeyError, UnicodeError) as exc:
    print('[FAIL] Invalid or unsafe backup archive: ' + str(exc), file=sys.stderr)
    sys.exit(1)
PY
}

current_ipv4() {
    local candidate octet valid=1
    candidate=$(ip -4 route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src") {print $(i+1); exit}}') || candidate=
    if [[ ! "$candidate" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
        candidate=$(curl -4fsS --connect-timeout 5 --max-time 10 https://ipv4.icanhazip.com 2>/dev/null) || candidate=
    fi
    [[ "$candidate" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
    for octet in ${candidate//./ }; do
        (( 10#$octet <= 255 )) || valid=0
    done
    (( valid )) || return 1
    printf '%s\n' "$candidate"
}

collect_path() {
    local path=$1
    if [[ -e "$path" || -L "$path" ]]; then
        mkdir -p "$STAGING/files$(dirname "$path")"
        cp -a -- "$path" "$STAGING/files$path"
    fi
}

save_backup_services() {
    local service state enabled status records=()
    for service in x-ui nginx mtr-backend certbot.timer AdGuardHome; do
        [[ "$service" != AdGuardHome || "$ADGUARD_HOME" == true ]] || continue
        state=$(systemctl is-active "$service") || :
        case "$state" in active|inactive|failed) ;; *) die "Unknown initial $service state." ;; esac
        if systemctl is-enabled --quiet "$service"; then enabled=true;
        else
            status=$?
            (( status == 1 )) || die "Cannot determine whether $service is enabled."
            enabled=false
        fi
        records+=("$service" "$state" "$enabled")
    done
    BACKUP_SERVICE_STATES=$(python3 - "${records[@]}" <<'PY'
import json, sys
args = sys.argv[1:]
print(json.dumps({args[i]: dict(active=args[i+1], enabled=args[i+2]=='true') for i in range(0,len(args),3)}))
PY
    ) || die 'Cannot save initial service states.'
}

write_metadata() {
    local source_ip xui_version xray_version xray
    source_ip=$(current_ipv4) || { source_ip=; warn 'Cannot detect source IPv4; diagnostics IP migration will be skipped.'; }
    xui_version=$(/usr/local/x-ui/x-ui -v 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1) || xui_version=unknown
    xray_version=unknown
    for xray in "$XRAY_DIR"/xray-linux-*; do
        [[ -x "$xray" ]] || continue
        xray_version=$("$xray" version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1) || xray_version=unknown
        break
    done
    python3 - "$STAGING/meta.json" "$OS_ID" "$OS_VERSION" "$ARCH" "$xui_version" "$xray_version" "$source_ip" "$ADGUARD_HOME" "$AGH_ARCH" "$BACKUP_SERVICE_STATES" <<'PY'
import datetime, json, socket, sys
path, os_id, os_version, arch, x_ui, xray, ipv4, agh, agh_arch, services = sys.argv[1:]
with open(path, 'w') as out:
    json.dump(dict(format_version=3, created=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   hostname=socket.gethostname(), os_id=os_id, os_version=os_version, arch=arch,
                   x_ui_version=x_ui, xray_version=xray, source_ipv4=ipv4, adguard_home=(agh == "true"),
                   service_states=json.loads(services),
                   **(dict(adguard_version="v0.107.79", adguard_arch=agh_arch) if agh == "true" else {})), out, indent=2)
    out.write('\n')
PY
}

cmd_backup() {
    stage 'Backup preflight'
    host_identity
    for path in "${REQUIRED_PATHS[@]}"; do
        [[ -e "$path" ]] || die "Required managed path is missing: $path"
    done
    command -v python3 >/dev/null && command -v sqlite3 >/dev/null || die 'Backup requires python3 and sqlite3.'
    load_adguard_backup_state
    save_backup_services
    pause_certbot_timer
    prepare_store backup
    local estimate available path initial_state existing=()
    for path in "${RUNTIME_PATHS[@]}" "${TREE_PATHS[@]}" "${EXTRA_PATHS[@]}"; do
        [[ ! -e "$path" && ! -L "$path" ]] || existing+=("$path")
    done
    estimate=$(du -skc -- "${existing[@]}" | tail -n1 | awk '{print $1}')
    available=$(df -Pk "$BACKUP_STORE" | awk 'NR==2 {print $4}')
    (( available >= estimate * 2 + 102400 )) || die 'Insufficient space for private staging and archive.'
    initial_state=$(systemctl is-active x-ui) || :
    case "$initial_state" in
        active)
            RESUME_XUI=1
            systemctl stop x-ui || die 'Cannot stop x-ui for a consistent snapshot.'
            ;;
        inactive|failed) ;;
        *) die 'x-ui is in a transitional or unknown state; retry when it is active or inactive.' ;;
    esac
    ok "Initial x-ui state: $initial_state"
    stage 'Collecting consistent runtime snapshot'
    quick_check "$DB"
    for path in "${RUNTIME_PATHS[@]}"; do collect_path "$path"; done
    if (( RESUME_XUI )); then
        systemctl start x-ui && systemctl is-active --quiet x-ui || die 'Cannot return x-ui to its original active state.'
        RESUME_XUI=0
        ok 'x-ui returned to its original active state'
    else
        ok 'x-ui remains inactive'
    fi
    if [[ "$ADGUARD_HOME" == true ]]; then
        initial_state=$(systemctl is-active AdGuardHome) || :
        case "$initial_state" in
            active) RESUME_AGH=1; systemctl stop AdGuardHome || die 'Cannot stop AdGuard Home for snapshot.' ;;
            inactive|failed) ;;
            *) die 'AdGuard Home service state is transitional or unknown.' ;;
        esac
        systemctl is-active --quiet AdGuardHome && die 'AdGuard Home is still running; snapshot refused.'
    fi
    stage 'Collecting managed configuration and web content'
    for path in "${TREE_PATHS[@]}" "${EXTRA_PATHS[@]}"; do collect_path "$path"; done
    if (( RESUME_AGH )); then
        systemctl start AdGuardHome && systemctl is-active --quiet AdGuardHome || die 'Cannot recover AdGuard Home after snapshot.'
        RESUME_AGH=0
    fi
    write_metadata
    stage 'Compressing and verifying archive'
    local name="x-ui-backup-$(date -u +%Y%m%d-%H%M%S)-${STAGING##*-}.tar.gz"
    OUTPUT="$BACKUP_STORE/.$name.partial"
    tar -czf "$OUTPUT" -C "$STAGING" meta.json files
    chown root:root "$OUTPUT"
    chmod 0600 "$OUTPUT"
    validate_archive "$OUTPUT"
    resume_certbot_timer || die 'Cannot restore certbot.timer after snapshot.'
    mv -- "$OUTPUT" "$BACKUP_STORE/$name"
    OUTPUT="$BACKUP_STORE/$name"
    BACKUP_FINISHED=1
    ok 'Archive integrity and required members verified'
    printf '\nBackup completed successfully.\n  File: %s\n  Size: %s\n' "$OUTPUT" "$(du -h "$OUTPUT" | cut -f1)"
    warn 'Backup contains secrets and is stored on this VPS. Copy it securely off-host for disaster recovery.'
}

check_compatibility() {
    python3 - "$STAGING/meta.json" "$OS_ID" "$OS_VERSION" "$ARCH" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    meta = json.load(f)
if [meta['os_id'], meta['os_version'], meta['arch']] != sys.argv[2:]:
    print('[FAIL] Restore requires the same OS ID, VERSION_ID and architecture.', file=sys.stderr)
    sys.exit(1)
PY
    ok "Backup format 3; OS $OS_ID $OS_VERSION; architecture $ARCH"
}

replace_managed_state() {
    local path source
    for path in "${RUNTIME_PATHS[@]}" "${TREE_PATHS[@]}" /var/www/diagnostics; do
        source="$STAGING/files$path"
        if [[ "$path" == /etc/letsencrypt ]]; then
            restore_project_certificates "$source"
            continue
        fi
        rm -rf -- "$path"
        mkdir -p "$(dirname "$path")"
        if [[ -e "$source" ]]; then cp -a -- "$source" "$path"; fi
    done
    for path in "${EXTRA_PATHS[@]:0:2}"; do
        mkdir -p "$(dirname "$path")"
        rm -f -- "$path"
        cp -a -- "$STAGING/files$path" "$path"
    done
    if [[ -f "$STAGING/files$SYSCTL_FILE" ]]; then
        mkdir -p "$(dirname "$SYSCTL_FILE")"
        install -o root -g root -m 0644 "$STAGING/files$SYSCTL_FILE" "$SYSCTL_FILE"
        snapshot_restore_sysctl || die 'Cannot save current managed sysctl values.'
        sysctl -p "$SYSCTL_FILE" || die 'Cannot apply managed sysctl file.'
    fi
}

preflight_target_certbot_ownership() {
    local hook domains name vision
    local -a owned=() incoming
    hook=/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx
    if [[ -e "$hook" || -L "$hook" ]]; then
        [[ -f "$hook" && ! -L "$hook" && "$(stat -c '%u:%g:%a' "$hook")" == '0:0:755' ]] || die 'Unowned target project deploy-hook.'
        domains=$(restored_certificate_domains "$hook") || die 'Unowned target project deploy-hook.'
        mapfile -t owned <<< "$domains"
    fi
    hook=/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision
    if [[ -e "$hook" || -L "$hook" ]]; then
        [[ "$(stat -c '%u:%g:%a' "$hook")" == '0:0:755' ]] || die 'Unowned target Vision hook.'
        vision=$(restored_vision_domain "$hook") || die 'Unowned target Vision hook.'
        owned+=("$vision")
    fi
    domains=$(restored_certificate_domains "$STAGING/files/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx") || return 1
    mapfile -t incoming <<< "$domains"
    vision=$(restored_vision_domain "$STAGING/files/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision") || return 1
    [[ -z "$vision" ]] || incoming+=("$vision")
    for name in "${incoming[@]}"; do
        if [[ -e "/etc/letsencrypt/live/$name" || -L "/etc/letsencrypt/live/$name" ||
              -e "/etc/letsencrypt/archive/$name" || -e "/etc/letsencrypt/renewal/$name.conf" ]]; then
            [[ " ${owned[*]} " == *" $name "* ]] || die "Target Certbot lineage has no project ownership: $name"
        fi
    done
}

project_certbot_accounts() {
    # Certbot AccountFileStorage uses <server netloc+path>/<account id> and
    # exactly these three JSON files. Import only accounts referenced by renewal.
    python3 - "$1" /etc/letsencrypt "${@:2}" <<'PYACCOUNTS'
import json, pathlib, re, sys
from urllib.parse import urlsplit
from configobj import ConfigObj
source, target = map(pathlib.Path, sys.argv[1:3])
selected = set()
for name in sys.argv[3:]:
    params = ConfigObj(str(source/'renewal'/(name+'.conf')), file_error=True)['renewalparams']
    account = params.get('account')
    if not account:
        continue  # Historical archives may omit an explicit account reference.
    server = urlsplit(params.get('server', 'https://acme-v02.api.letsencrypt.org/directory'))
    if (not re.fullmatch(r'[a-f0-9]{32}', account) or server.scheme != 'https' or not server.hostname
            or server.username or server.password or server.query or server.fragment
            or not re.fullmatch(r'[A-Za-z0-9.:[\]-]+', server.netloc)
            or not re.fullmatch(r'/[A-Za-z0-9_./-]*', server.path)
            or any(p in ('.','..') for p in server.path.split('/'))):
        raise ValueError('Invalid managed Certbot account reference')
    base = pathlib.Path('accounts') / (server.netloc+server.path) / account
    for filename in ('meta.json','private_key.json','regr.json'):
        relative = base / filename
        for tree in (source,target):
            current = tree
            for part in relative.parts:
                current /= part
                if current.is_symlink():
                    raise ValueError('Symlinked Certbot account path refused')
        saved, existing = source/relative, target/relative
        if not saved.is_file() or not isinstance(json.loads(saved.read_text()), dict):
            raise ValueError('Missing/invalid managed Certbot account JSON')
        if existing.exists() and (not existing.is_file() or existing.read_bytes()!=saved.read_bytes()):
            raise ValueError('Conflicting target Certbot account metadata preserved')
        selected.add(str(relative))
for relative in sorted(selected):
    print(relative)
PYACCOUNTS
}

restore_project_certificates() {
    local source=$1 domains vision name kind file accounts
    local -a names
    [[ ! -L /etc/letsencrypt ]] || die 'Refusing symlinked target Certbot tree.'
    domains=$(restored_certificate_domains "$source/renewal-hooks/deploy/3x-ui-auto-nginx") || die 'Invalid project domains.'
    mapfile -t names <<< "$domains"
    vision=$(restored_vision_domain "$source/renewal-hooks/deploy/3x-ui-auto-nginx-vision") || die 'Invalid Vision declaration.'
    [[ -z "$vision" ]] || names+=("$vision")
    accounts=$(project_certbot_accounts "$source" "${names[@]}") || die 'Invalid/conflicting managed Certbot account metadata.'
    # Replace only declared project lineages. Foreign target lineages/options/hooks win.
    mkdir -p /etc/letsencrypt
    for name in "${names[@]}"; do
        for kind in live archive renewal; do
            [[ ! -L "/etc/letsencrypt/$kind" ]] || die 'Refusing symlinked target Certbot directory.'
            if [[ "$kind" == renewal ]]; then
                rm -f -- "/etc/letsencrypt/$kind/$name.conf"
            else
                rm -rf -- "/etc/letsencrypt/$kind/$name"
            fi
        done
    done
    [[ ! -L /etc/letsencrypt/renewal-hooks && ! -L /etc/letsencrypt/renewal-hooks/deploy ]] || die 'Refusing symlinked target deploy directory.'
    rm -f /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx
    rm -f /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision
    for name in "${names[@]}"; do
        mkdir -p "/etc/letsencrypt/live/$name" "/etc/letsencrypt/archive/$name" /etc/letsencrypt/renewal
        cp -a -- "$source/renewal/$name.conf" "/etc/letsencrypt/renewal/$name.conf" || die 'Cannot restore project renewal configuration.'
        for file in cert.pem chain.pem fullchain.pem privkey.pem; do
            if [[ -e "$source/live/$name/$file" || -L "$source/live/$name/$file" ]]; then
                cp -a -- "$source/live/$name/$file" "/etc/letsencrypt/live/$name/$file" || die 'Cannot restore project certificate link.'
            fi
        done
        for file in "$source/archive/$name/"*.pem; do
            [[ -e "$file" ]] || continue
            [[ ! -L "$file" && -f "$file" && "${file##*/}" =~ ^(cert|chain|fullchain|privkey)[0-9]+\.pem$ ]] || continue
            cp -a -- "$file" "/etc/letsencrypt/archive/$name/" || die 'Cannot restore project certificate version.'
        done
    done
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    for name in 3x-ui-auto-nginx 3x-ui-auto-nginx-vision; do
        [[ -f "$source/renewal-hooks/deploy/$name" ]] || continue
        if [[ "$name" == 3x-ui-auto-nginx-vision ]]; then
            install -m 0755 <(render_vision_hook "$vision") "/etc/letsencrypt/renewal-hooks/deploy/$name" || die 'Cannot restore verified Vision hook.'
        else
            install -m 0755 <(render_certificate_hook "${names[0]}" "${names[1]}") "/etc/letsencrypt/renewal-hooks/deploy/$name" || die 'Cannot restore verified project hook.'
        fi
    done
    while IFS= read -r file; do
        [[ -n "$file" ]] || continue
        [[ -e "/etc/letsencrypt/$file" ]] && continue
        mkdir -p -- "/etc/letsencrypt/${file%/*}" || die 'Cannot prepare account metadata directory.'
        chmod 0700 -- "/etc/letsencrypt/${file%/*}"
        cp -a -- "$source/$file" "/etc/letsencrypt/$file" && chmod 0600 -- "/etc/letsencrypt/$file" || die 'Cannot restore managed account metadata.'
    done <<< "$accounts"
}

repair_panel_certificates() {
    local certificate domain
    certificate=$(sqlite3 "$DB" "SELECT value FROM settings WHERE key='webCertFile';")
    if [[ "$certificate" =~ ^/root/cert/([^/]+)/ ]]; then
        domain=${BASH_REMATCH[1]}
        [[ "$domain" != . && "$domain" != .. ]] || die 'Invalid panel certificate domain.'
        if [[ -d "/etc/letsencrypt/live/$domain" ]]; then
            mkdir -p "/root/cert/$domain"
            chmod 0755 /root/cert "/root/cert/$domain"
            for name in fullchain.pem privkey.pem; do
                if [[ ! -e "/root/cert/$domain/$name" ]]; then
                    ln -sfn "/etc/letsencrypt/live/$domain/$name" "/root/cert/$domain/$name"
                fi
            done
        fi
    fi
}

prepare_mtr_backend() {
    local binary
    if ! id mtr-backend >/dev/null 2>&1; then
        useradd --system --no-create-home --shell /usr/sbin/nologin mtr-backend
    fi
    chmod 0755 /usr/local/lib/3x-ui-pro /usr/local/lib/3x-ui-pro/mtr-backend.py
    for binary in mtr mtr-packet; do
        if command -v "$binary" >/dev/null; then
            if ! setcap cap_net_raw+ep "$(command -v "$binary")" 2>/dev/null; then
                warn "Could not set CAP_NET_RAW file capability on $binary; mtr-backend uses systemd AmbientCapabilities."
            fi
        fi
    done
}

regenerate_diagnostics() {
    local directory=/var/www/diagnostics/testfiles current source
    mkdir -p "$directory"
    dd if=/dev/zero of="$directory/test-15k.bin" bs=1024 count=15 status=none
    dd if=/dev/zero of="$directory/test-17k.bin" bs=1024 count=17 status=none
    dd if=/dev/zero of="$directory/test-100m.bin" bs=1048576 count=100 status=none
    dd if=/dev/zero of="$directory/test-1g.bin" bs=1048576 count=1024 status=none
    rm -f "$directory/test-512m.bin"
    source=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_ipv4"])' "$STAGING/meta.json")
    if current=$(current_ipv4); then
        if [[ -n "$source" && "$source" != "$current" ]]; then
            python3 - /var/www/diagnostics/index.html "$source" "$current" <<'PY'
import re, sys
path, old, new = sys.argv[1:]
with open(path) as f:
    html = f.read()
pattern = r'(<(?:span|code)\b[^>]*\bid=[\'"]server-ip(?:-step)?[\'"][^>]*>)([^<]*)(</(?:span|code)>)'
updated = re.sub(pattern, lambda m: m[1] + (new if m[2] == old else m[2]) + m[3], html)
if updated == html:
    print('[WARN] Diagnostics IP display was not recognized; saved display left unchanged.', file=sys.stderr)
else:
    with open(path, 'w') as f:
        f.write(updated)
PY
            warn 'Source VPS IP differs from current VPS IP. Point DNS to the new VPS separately.'
        elif [[ -z "$source" ]]; then
            warn 'Backup has no source IPv4; saved diagnostics display left unchanged.'
        fi
    else
        warn 'Cannot detect current IPv4; saved diagnostics display left unchanged.'
    fi
    chmod 0755 /var/www/diagnostics "$directory"
    chown -R www-data:www-data /var/www/diagnostics /var/www/html /var/www/subpage
}

prepare_acme_webroot() {
    install -d -o root -g root -m 0755 /var/www/acme /var/www/acme/.well-known /var/www/acme/.well-known/acme-challenge
}


remove_legacy_certbot_cron() {
    command -v crontab >/dev/null || return 0
    local directory
    directory=$(mktemp -d) || return 1
    if ! LC_ALL=C crontab -l > "$directory/current" 2> "$directory/error"; then
        if grep -qi 'no crontab for' "$directory/error"; then rm -rf "$directory"; return 0; fi
        rm -rf "$directory"; return 1
    fi
    if grep -Fxq -- "$LEGACY_CERTBOT_CRON" "$directory/current"; then
        awk -v legacy="$LEGACY_CERTBOT_CRON" '$0 != legacy' "$directory/current" > "$directory/new" || { rm -rf "$directory"; return 1; }
        if [[ -n "$ROLLBACK_DIR" ]]; then
            cp -- "$directory/current" "$ROLLBACK_DIR/cron.before" &&
                cp -- "$directory/new" "$ROLLBACK_DIR/cron.after" &&
                touch "$ROLLBACK_DIR/cron.changed" || { rm -rf "$directory"; return 1; }
        fi
        crontab - < "$directory/new" && crontab -l > "$directory/verified" &&
            cmp -s "$directory/new" "$directory/verified" || { rm -rf "$directory"; return 1; }
    fi
    rm -rf "$directory"
}

check_no_legacy_certbot_cron() {
    command -v crontab >/dev/null || return 0
    local directory
    directory=$(mktemp -d) || return 1
    if ! LC_ALL=C crontab -l > "$directory/current" 2> "$directory/error"; then
        if grep -qi 'no crontab for' "$directory/error"; then rm -rf "$directory"; return 0; fi
        rm -rf "$directory"; return 1
    fi
    if grep -Fxq -- "$LEGACY_CERTBOT_CRON" "$directory/current"; then rm -rf "$directory"; return 1; fi
    rm -rf "$directory"
}

check_webroot_lineage() {
    python3 - "$1" <<'PY'
import sys
from pathlib import Path
from configobj import ConfigObj, ConfigObjError
from cryptography import x509
try:
    domain = sys.argv[1]
    live = Path('/etc/letsencrypt/live') / domain
    conf = Path('/etc/letsencrypt/renewal') / (domain + '.conf')
    cfg = ConfigObj(str(conf), encoding='utf-8', file_error=True)
    params = cfg['renewalparams']
    if params.get('authenticator') != 'webroot':
        raise ValueError('authenticator must be webroot')
    for name in ('fullchain', 'privkey'):
        path = live / (name + '.pem')
        if cfg.get(name) != str(path) or not path.is_file() or not path.stat().st_size:
            raise ValueError('missing or unexpected certificate/key path')
    cert = x509.load_pem_x509_certificate((live / 'fullchain.pem').read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    if set(names) != {domain}:
        raise ValueError('expected a separate exact-domain lineage')
    mapping = params.get('webroot_map', {})
    roots = params.get('webroot_path', [])
    if isinstance(roots, str):
        roots = [roots]
    effective = mapping.get(domain) if domain in mapping else (roots[-1] if roots else None)
    if effective != '/var/www/acme':
        raise ValueError('unexpected persisted webroot')
    if any(params.get(key) for key in ('pre_hook', 'post_hook', 'renew_hook', 'deploy_hook')):
        raise ValueError('unexpected per-lineage hooks; use the project deploy directory hook')
except (OSError, ValueError, KeyError, ConfigObjError, x509.ExtensionNotFound) as exc:
    print('[FAIL] Invalid webroot renewal lineage: ' + str(exc), file=sys.stderr)
    sys.exit(1)
PY
}

check_acme_http() {
    local domain=$1 reality_domain=$2 token body code failed=0
    token=$(openssl rand -hex 16) || return 1
    printf '%s' "$token" > "/var/www/acme/.well-known/acme-challenge/$token" || { rm -f "/var/www/acme/.well-known/acme-challenge/$token"; return 1; }
    chmod 0644 "/var/www/acme/.well-known/acme-challenge/$token" || { rm -f "/var/www/acme/.well-known/acme-challenge/$token"; return 1; }
    local d
    for d in "$domain" "$reality_domain"; do
        body=$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 10 -H "Host: $d" \
            "http://127.0.0.1/.well-known/acme-challenge/$token") || failed=1
        [[ "$body" == "$token" ]] || failed=1
        code=$(curl --noproxy '*' -sS --connect-timeout 5 --max-time 10 -o /dev/null -w '%{http_code} %{redirect_url}' \
            -H "Host: $d" http://127.0.0.1/) || failed=1
        [[ "$code" == "301 https://$d/" ]] || failed=1
    done
    rm -f "/var/www/acme/.well-known/acme-challenge/$token" || return 1
    (( ! failed ))
}

check_certificate_renewal() {
    local domain=$1 reality_domain=$2 hook=/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx
    check_webroot_lineage "$domain" && check_webroot_lineage "$reality_domain" || return 1
    [[ -f "$hook" && ! -L "$hook" && -x "$hook" && "$(stat -c '%u:%g:%a' "$hook")" == '0:0:755' ]] || return 1
    bash -n "$hook" || return 1
    # Verify restored/generated hook domains without executing arbitrary hook code.
    python3 - "$hook" "$domain" "$reality_domain" <<'PY'
import shlex, sys
values = {}
for line in open(sys.argv[1]):
    for key in ('PANEL_DOMAIN', 'REALITY_DOMAIN'):
        if line.startswith(key + '='):
            parts = shlex.split(line.strip())
            if len(parts) == 1:
                values[key] = parts[0].split('=', 1)[1]
if [values.get('PANEL_DOMAIN'), values.get('REALITY_DOMAIN')] != sys.argv[2:]:
    sys.exit('Deploy hook domains do not match this installation')
PY
    [[ $? == 0 ]] || return 1
    systemctl is-enabled --quiet certbot.timer && systemctl is-active --quiet certbot.timer || return 1
    check_no_legacy_certbot_cron && nginx -t && check_acme_http "$domain" "$reality_domain"
}

snapshot_restore_firewall() {
    local path status
    status=$(LC_ALL=C ufw status) || return 1
    case "$status" in
        'Status: active'*) printf 'active\n' > "$ROLLBACK_DIR/ufw.state" ;;
        'Status: inactive'*) printf 'inactive\n' > "$ROLLBACK_DIR/ufw.state" ;;
        *) return 1 ;;
    esac || return 1
    mkdir "$ROLLBACK_DIR/ufw" || return 1
    for path in /etc/ufw/user.rules /etc/ufw/user6.rules; do
        if [[ -e "$path" || -L "$path" ]]; then cp -a -- "$path" "$ROLLBACK_DIR/ufw/" || return 1; fi
    done
    touch "$ROLLBACK_DIR/ufw.changed"
}

recover_restore_firewall() {
    [[ -f "$ROLLBACK_DIR/ufw.changed" ]] || return 0
    local path saved status expected failed=0
    for path in /etc/ufw/user.rules /etc/ufw/user6.rules; do
        saved="$ROLLBACK_DIR/ufw/${path##*/}"
        if [[ -e "$saved" || -L "$saved" ]]; then
            cp -aT -- "$saved" "$path" && cmp -s "$saved" "$path" &&
                [[ "$(stat -c '%u:%g:%a' "$saved")" == "$(stat -c '%u:%g:%a' "$path")" ]] || failed=1
        else
            rm -f -- "$path" || failed=1
        fi
    done
    (( ! failed )) || return 1
    expected=$(cat "$ROLLBACK_DIR/ufw.state") || return 1
    case "$expected" in active) ufw reload || return 1 ;; inactive) ;; *) return 1 ;; esac
    status=$(LC_ALL=C ufw status) || return 1
    [[ "$status" == "Status: $expected"* ]]
}

restore_firewall() {
    snapshot_restore_firewall || die 'Cannot save current UFW rules/state.'
    for rule in 80/tcp 443/tcp 443/udp; do ufw allow "$rule"; done
    local awg status
    awg=$(sqlite3 "$DB" "SELECT count(*) FROM inbounds WHERE protocol='amneziawg' AND tag='inbound-8443-udp' AND port=8443 AND enable=1 AND listen='0.0.0.0';") || die 'Cannot read restored AmneziaWG firewall state.'
    if [[ "$awg" == 1 ]]; then ufw allow 8443/udp || die 'Cannot restore AmneziaWG firewall rule.'; fi
    status=$(LC_ALL=C ufw status) || die 'Cannot read UFW status.'
    if ! grep -q '^Status: active$' <<< "$status"; then
        warn 'UFW is inactive; application rules added without enabling the firewall.'
    fi
}

restored_certificate_domains() {
    local hook=${1:-/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx} values mode
    [[ -f "$hook" && ! -L "$hook" ]] || return 1
    values=$(python3 - "$hook" <<'PYDOM'
import shlex, sys
values = {}
for line in open(sys.argv[1]):
    for key in ('PANEL_DOMAIN', 'REALITY_DOMAIN'):
        if line.startswith(key + '='):
            parts = shlex.split(line.strip())
            if len(parts) == 1:
                values[key] = parts[0].split('=', 1)[1]
names = [values.get('PANEL_DOMAIN'), values.get('REALITY_DOMAIN')]
if any(not name or '/' in name or any(c.isspace() for c in name) for name in names) or names[0] == names[1]:
    sys.exit('Missing or ambiguous project domains in deploy hook')
print('\n'.join(names))
PYDOM
    ) || return 1
    local -a names
    mapfile -t names <<< "$values"
    for mode in current previous legacy; do
        if cmp -s "$hook" <(render_certificate_hook "${names[0]}" "${names[1]}" "$mode"); then
            printf '%s\n' "$values"
            return 0
        fi
    done
    return 1
}

restored_vision_domain() {
    local hook=${1:-/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision} value
    [[ -e "$hook" || -L "$hook" ]] || return 0
    [[ -f "$hook" && ! -L "$hook" ]] || return 1
    value=$(python3 - "$hook" <<'PYVISION'
import re, shlex, sys
values=[]
for line in open(sys.argv[1]):
    if line.startswith('VISION_DOMAIN='):
        parts=shlex.split(line.strip())
        if len(parts)!=1: sys.exit('Invalid Vision hook domain')
        values.append(parts[0].split('=',1)[1])
if len(values)!=1 or len(values[0])>253 or '.' not in values[0] or not all(
    re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in values[0].split('.')):
    sys.exit('Missing/ambiguous Vision hook domain')
print(values[0])
PYVISION
    ) || return 1
    cmp -s "$hook" <(render_vision_hook "$value") ||
        cmp -s "$hook" <(render_vision_hook "$value" previous) ||
        cmp -s "$hook" <(render_vision_hook "$value" legacy) || return 1
    printf '%s\n' "$value"
}

check_vision_renewal() {
    local vision
    vision=$(restored_vision_domain) || return 1
    [[ -n "$vision" ]] || return 0
    check_webroot_lineage "$vision" || return 1
    [[ "$(stat -c '%u:%g:%a' /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision)" == '0:0:755' ]] || return 1
    curl -q -fsS --noproxy '*' --http1.1 --resolve "$vision:443:127.0.0.1" \
        --connect-timeout 5 --max-time 20 "https://$vision/" >/dev/null
}

render_vision_hook() {
    printf '#!/usr/bin/env bash\nset -Eeuo pipefail\nVISION_DOMAIN=%q\n' "$1"
    cat <<'VISIONHOOK'
[[ "${RENEWED_LINEAGE:-}" == "/etc/letsencrypt/live/$VISION_DOMAIN" ]] || exit 0
VISIONHOOK
    if [[ "${2:-current}" == current ]]; then
        # -checkend short-circuits -checkhost; hostname mismatch alone exits zero.
        cat <<'VISIONHOOK'
openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -noout -checkend 0
openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -noout -checkhost "$VISION_DOMAIN" |
    grep -Fx "Hostname $VISION_DOMAIN does match certificate"
VISIONHOOK
    else
        printf '%s\n' 'openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -noout -checkend 0 -checkhost "$VISION_DOMAIN"'
    fi
    cat <<'VISIONHOOK'
cert_key=$(openssl x509 -in "$RENEWED_LINEAGE/fullchain.pem" -pubkey -noout)
private_key=$(openssl pkey -in "$RENEWED_LINEAGE/privkey.pem" -pubout)
[[ "$cert_key" == "$private_key" ]] || exit 1
VISIONHOOK
    if [[ "${2:-current}" == current ]]; then
        cat <<'VISIONHOOK'
if systemctl is-active --quiet x-ui; then
    systemctl try-restart x-ui
    systemctl is-active --quiet x-ui
fi
VISIONHOOK
        return
    fi
    # Exact historical renderings are recognized, never deployed or executed.
    local readiness="--connect-timeout 2 --max-time 3 --retry 4 --retry-delay 1 --retry-max-time 10 --retry-all-errors"
    [[ "${2:-}" != legacy ]] || readiness="--connect-timeout 5 --max-time 20"
    cat <<'VISIONHOOK'
# Xray 26.9.30 polls files hourly; ensure the deployed certificate is used now.
systemctl restart x-ui
systemctl is-active --quiet x-ui
curl -q -fsS --noproxy '*' --http1.1 --resolve "$VISION_DOMAIN:443:127.0.0.1" \
VISIONHOOK
    printf '    %s "https://$VISION_DOMAIN/" >/dev/null\n' "$readiness"
}

# Same canonical runtime contract in installer/backup; embedded in the trusted deploy hook.
check_xray_runtime() {
    local attempt proc_root=${1:-/proc}
    for attempt in {1..10}; do
        if systemctl is-active --quiet x-ui && python3 - "$proc_root" <<'PY'
import os, pathlib, re, subprocess, sys
try:
    network = subprocess.check_output(['ss', '-H', '-lntup'], text=True)
    unix = subprocess.check_output(['ss', '-H', '-lxnp'], text=True)
    owners = []
    for protocol, state, address, listing in (
        ('tcp', 'LISTEN', '127.0.0.1:8443', network),
        ('udp', 'UNCONN', None, network),
        ('u_str', 'LISTEN', '/dev/shm/uds2023.sock', unix),
    ):
        candidates = set()
        for line in listing.splitlines():
            fields = line.split()
            if len(fields) < 6 or fields[0] != protocol or fields[1] != state:
                continue
            local = fields[4]
            if address is not None and local != address:
                continue
            if address is None and local not in ('*:443', '0.0.0.0:443', '[::]:443', ':::443'):
                continue
            candidates.update(int(pid) for pid in re.findall(r'pid=(\d+)', line))
        owners.append(candidates)
    common = set.intersection(*owners)
    managed = pathlib.Path('/usr/local/x-ui/bin').resolve()
    for pid in common:
        executable = pathlib.Path(os.readlink(sys.argv[1] + '/' + str(pid) + '/exe'))
        if executable.parent == managed and re.fullmatch(r'xray-linux-[A-Za-z0-9_-]+', executable.name) and executable.is_file():
            sys.exit(0)
except (OSError, subprocess.CalledProcessError, ValueError):
    pass
sys.exit(1)
PY
        then return 0; fi
        sleep 0.5
    done
    printf '[FAIL] Xray must own the REALITY TCP, live XHTTP Unix and Hysteria2 UDP listeners.\n' >&2
    return 1
}

render_certificate_hook() {
    local domain=$1 reality_domain=$2
    if [[ "${3:-current}" == current ]]; then
        printf '#!/usr/bin/env bash\nset -Eeuo pipefail\n'
        printf 'PANEL_DOMAIN=%q\nREALITY_DOMAIN=%q\n' "$domain" "$reality_domain"
        cat <<'HOOK'
case "${RENEWED_LINEAGE:-}" in
    "/etc/letsencrypt/live/$PANEL_DOMAIN") panel=1 ;;
    "/etc/letsencrypt/live/$REALITY_DOMAIN") panel=0 ;;
    *) exit 0 ;;
esac
if systemctl is-active --quiet nginx; then
    nginx -t
    systemctl reload nginx
    systemctl is-active --quiet nginx
fi
if (( panel )) && systemctl is-active --quiet x-ui; then
    systemctl try-restart x-ui
    systemctl is-active --quiet x-ui
fi
HOOK
        return
    fi
    # Exact historical renderings are recognized, never deployed or executed.
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
}

check_health() {
    local service state failed=0
    stage 'Final checks'
    quick_check "$DB"
    [[ "$(sqlite3 "$DB" "SELECT value FROM settings WHERE key='webListen';")" == 127.0.0.1 ]] ||
        die 'Restored panel backend must bind only to 127.0.0.1.'
    if nginx -t > "$STAGING/nginx-test.log" 2>&1; then
        ok 'nginx configuration'
    else
        warn 'nginx configuration check failed; inspect nginx -t.'
        failed=1
    fi
    for service in x-ui nginx mtr-backend certbot.timer AdGuardHome; do
        [[ "$service" != AdGuardHome || "$ADGUARD_HOME" == true ]] || continue
        state=$(systemctl is-active "$service") || :
        if [[ "${RESTORED_ACTIVE[$service]}" == active ]]; then
            if [[ "$state" == active ]]; then ok "$service is active";
            else printf '[FAIL] %s is not active\n' "$service" >&2; failed=1; fi
        else
            case "$state" in inactive|failed) ok "$service remains stopped ($state)" ;;
                *) printf '[FAIL] Unexpected %s state: %s\n' "$service" "$state" >&2; failed=1 ;; esac
        fi
    done
    if [[ "$ADGUARD_HOME" == true ]]; then
        ok 'AdGuard Home existing credentials preserved'
    fi
    (( ! failed )) || die 'Restore failed mandatory health checks; archive is unchanged. Fix the cause and rerun restore.'
}

# Trusted static AGH contract, synchronized with assets/adguard/managed.sh by tests.
# Embedded so restore never sources an archive-provided shell helper for preflight.
agh_binary_hash() {
    case "$1" in
        amd64|x86_64) printf '%s\n' 7e247573e63ce771a5925d16ca4ca9344e6e888673244289dc302f0fdfdfbf4e ;;
        arm64|aarch64) printf '%s\n' 64a9b6fc6269247f1973cddbf285aa6ce866d11bd29546b0f4135ba31d2283c8 ;;
        *) return 1 ;;
    esac
}

agh_verify_binary() {
    local expected actual
    [[ -f "$AGH_DIR/AdGuardHome" && ! -L "$AGH_DIR/AdGuardHome" && -x "$AGH_DIR/AdGuardHome" ]] || return 1
    expected=$(agh_binary_hash "$1") || return 1
    actual=$(sha256sum "$AGH_DIR/AdGuardHome") || return 1
    [[ "${actual%% *}" == "$expected" ]]
}

agh_binary() {
    agh_verify_binary "${AGH_ARCH:-$(uname -m)}" || return 1
    [[ "$("$AGH_DIR/AdGuardHome" --version)" == "AdGuard Home, version $AGH_VERSION" ]]
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
if not (m['version'] == 'v0.107.79' and m['arch'] in ('amd64', 'arm64')):
    raise ValueError('Invalid AGH version/architecture')
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
def section(name):
    match = re.search(r'^' + name + r':\s*\n((?:[ \t].*\n|\n)*)', s, re.M)
    if not (match):
        raise ValueError('Invalid AGH required YAML section')
    return match[1]
def scalar(text, key):
    matches = re.findall(r'^  ' + key + r':\s*(.*?)\s*$', text, re.M)
    if not (len(matches) == 1):
        raise ValueError('Invalid AGH unique YAML field')
    return matches[0].strip('"\'')
if not (re.search(r'^schema_version: 34\s*$', s, re.M)):
    raise ValueError('Invalid AGH schema 34')
http, dns, tls = section('http'), section('dns'), section('tls')
if not (scalar(http, 'address') == '127.0.0.1:' + str(m['web_port'])):
    raise ValueError('Invalid AGH loopback HTTP address')
if not (scalar(dns, 'port') == str(m['dns_port'])):
    raise ValueError('Invalid AGH DNS port')
hosts = re.search(r'^  bind_hosts:\s*\n((?:    - .*\n)+)', dns, re.M)
if not (hosts and [x.strip().strip('"\'') for x in re.findall(r'^    - (.*)$', hosts[1], re.M)] == ['127.0.0.1']):
    raise ValueError('Invalid AGH loopback DNS bind')
if not (scalar(tls, 'enabled') == 'false'):
    raise ValueError('Invalid AGH native TLS disabled')
if not (re.search(r'^    insecure_enabled: true\s*$', http, re.M)):
    raise ValueError('Invalid AGH DoH insecure bridge')
for part in ('querylog', 'statistics'):
    p = section(part) if re.search(r'^' + part + ':', s, re.M) else ''
    if p and re.search(r'^  dir_path:', p, re.M):
        directory = scalar(p, 'dir_path')
        if not (not directory or pathlib.Path(directory).resolve().is_relative_to(data_root.resolve())):
            raise ValueError('Invalid AGH managed data directory')
for k in ('web_port', 'dns_port', 'path', 'domain', 'arch'):
    print(m[k])
PY
    ) || return 1
    local -a fields
    mapfile -t fields <<< "$values"
    AGH_WEB_PORT=${fields[0]} AGH_DNS_PORT=${fields[1]} AGH_PATH=${fields[2]} AGH_DOMAIN=${fields[3]} AGH_ARCH=${fields[4]}
    agh_binary && "$AGH_DIR/AdGuardHome" -c "$AGH_DIR/AdGuardHome.yaml" -w "$AGH_DIR" --no-check-update --check-config
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

preflight_staged_adguard() (
    local AGH_VERSION=v0.107.79 AGH_DIR="$STAGING/files/opt/AdGuardHome"
    local AGH_DATA_ROOT=/opt/AdGuardHome
    local snippet="$STAGING/files/etc/nginx/snippets/x-ui-auto-optional/adguard.conf"
    # Authenticate using trusted host-architecture hashes before ANY staged execution.
    agh_verify_binary "$ARCH" ||
        die 'Staged AdGuard Home executable SHA256 mismatch; target state was not changed.'
    agh_config && [[ "$AGH_ARCH" == "$ARCH" ]] ||
        die 'Staged AdGuard Home configuration/binary contract is invalid; target state was not changed.'
    [[ -f "$snippet" && ! -L "$snippet" ]] &&
        { cmp -s "$snippet" <(agh_snippet) || cmp -s "$snippet" <(agh_snippet legacy); } ||
        die 'Staged AdGuard Home nginx snippet is invalid; target state was not changed.'
)

preflight_staged_core() {
    local domains panel reality vision hook="$STAGING/files/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx"
    domains=$(restored_certificate_domains "$hook") || die 'Unexpected staged project deploy hook; archive code was not executed.'
    panel=${domains%%$'\n'*} reality=${domains#*$'\n'}
    render_certificate_hook "$panel" "$reality" > "$STAGING/current-hook"
    vision=$(restored_vision_domain "$STAGING/files/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision") || die 'Invalid staged Vision hook.'
    python3 - "$STAGING/files" "$DB" /etc/nginx /etc/letsencrypt /root/cert /var/www \
        "$panel" "$reality" "$STAGING/nginx-validation" "$vision" <<'PY'
import json, os, pathlib, re, shutil, sqlite3, sys
from configobj import ConfigObj
from cryptography import x509
from cryptography.hazmat.primitives import serialization
root, dbpath, nginx, letsencrypt, certroot, webroot, panel, reality, validation, vision = sys.argv[1:]
root, validation = pathlib.Path(root), pathlib.Path(validation)
def staged(path, tls_reference=False):
    # Resolve every archived symlink component without consulting live certificates.
    if '..' in pathlib.PurePosixPath(str(path)).parts: raise ValueError('Staged path escaped private state')
    p = root / str(path).lstrip('/')
    for _ in range(32):
        if tls_reference and p.is_relative_to(root / letsencrypt.lstrip('/')):
            parts = p.relative_to(root / letsencrypt.lstrip('/')).parts
            if len(parts) != 3 or parts[1] not in (panel, reality, *([vision] if vision else [])):
                raise ValueError('Unowned staged Certbot TLS reference: ' + str(path))
            # Match exactly what restore_project_certificates copies, at every link hop.
            live = parts[0] == 'live' and parts[2] in ('cert.pem','chain.pem','fullchain.pem','privkey.pem')
            archive = (parts[0] == 'archive' and re.fullmatch(r'(cert|chain|fullchain|privkey)[0-9]+\.pem', parts[2])
                       and not p.is_symlink())
            if not (live or archive):
                raise ValueError('Non-restorable staged Certbot TLS reference: ' + str(path))
        relative = p.relative_to(root)
        current = root
        for i, component in enumerate(relative.parts):
            current /= component
            if current.is_symlink():
                target = os.readlink(current)
                destination = root / target.lstrip('/') if target.startswith('/') else current.parent / target
                p = pathlib.Path(os.path.normpath(destination.joinpath(*relative.parts[i+1:])))
                if not p.is_relative_to(root): raise ValueError('Staged link escaped private state')
                break
        else:
            if not p.is_file(): raise ValueError('Missing staged file: ' + str(path))
            return p
    raise ValueError('Staged link cycle')
for domain in (panel, reality, *([vision] if vision else [])):
    if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', domain):
        raise ValueError('Invalid saved domain')
    live = letsencrypt + '/live/' + domain
    cfg = ConfigObj(str(staged(letsencrypt + '/renewal/' + domain + '.conf')), file_error=True, encoding='utf-8')
    params = cfg['renewalparams']
    for key, filename in (('fullchain','fullchain.pem'), ('privkey','privkey.pem')):
        if cfg.get(key) != live + '/' + filename: raise ValueError('Unexpected lineage reference')
    cert = x509.load_pem_x509_certificate(staged(live + '/fullchain.pem').read_bytes())
    key = serialization.load_pem_private_key(staged(live + '/privkey.pem').read_bytes(), password=None)
    public = lambda k: k.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(cert.public_key()) != public(key.public_key()): raise ValueError('Certificate/private key mismatch')
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    if set(names) != {domain}: raise ValueError('Wrong certificate SAN')
    roots = params.get('webroot_path', [])
    if isinstance(roots, str): roots = [roots]
    mapping = params.get('webroot_map', {})
    effective = mapping.get(domain) if domain in mapping else (roots[-1] if roots else None)
    if params.get('authenticator') != 'webroot' or effective != webroot + '/acme':
        raise ValueError('Invalid staged webroot renewal')
    if any(params.get(k) for k in ('pre_hook','post_hook','renew_hook','deploy_hook')):
        raise ValueError('Unexpected per-lineage hook')
# Vision ownership comes from the canonical hook/lineage and managed nginx, not editable inbounds/Hosts.
site=root / (nginx+'/sites-available/vision.conf').lstrip('/')
acme=root / (nginx+'/sites-available/vision-acme.conf').lstrip('/')
if not vision:
    # A user-defined remark or filename in an older archive is not ownership.
    for path in (site,acme):
        if path.exists() or path.is_symlink():
            saved=staged('/'+str(path.relative_to(root)))
            if saved.read_text().startswith('# Managed by 3x-ui Auto Nginx: Vision\n'):
                raise ValueError('Managed Vision artifacts without trusted declaration')
else:
    site=staged(nginx+'/sites-available/vision.conf')
    if staged(nginx+'/sites-enabled/vision.conf')!=site:
        raise ValueError('Inactive or redirected Vision fallback')
    if vision in (panel,reality): raise ValueError('Conflicting Vision domain')
    match=re.search(r'^    listen 127\.0\.0\.1:(\d+) proxy_protocol;$',site.read_text(),re.M)
    if not match: raise ValueError('Invalid plaintext Vision fallback')
    fallback=int(match[1])
    if not 1024<=fallback<=65535: raise ValueError('Invalid Vision fallback port')
    expected_site=f"""# Managed by 3x-ui Auto Nginx: Vision
server {{
    listen 127.0.0.1:{fallback} proxy_protocol;
    server_name {vision};
    server_tokens off;
    root {webroot}/html;
    index index.html;
    real_ip_header proxy_protocol;
    set_real_ip_from 127.0.0.1;
    if ($host != {vision}) {{ return 404; }}
    location / {{ try_files $uri $uri/ =404; }}
}}
"""
    if not site.is_file() or site.read_text()!=expected_site: raise ValueError('Unsafe Vision fallback site')
    streamtext=staged(nginx+'/stream-enabled/stream.conf').read_text()
    upstreams=re.findall(r'^upstream vision \{ server 127\.0\.0\.1:(\d+); \}$',streamtext,re.M)
    if (streamtext.count(f'    {vision} vision;')!=1 or
        len(upstreams)!=1 or not 1024<=int(upstreams[0])<=65535 or int(upstreams[0])==fallback):
        raise ValueError('Vision SNI mapping mismatch')

# Verify the existing runtime certificate references too, never a live-host fallback.
with sqlite3.connect(staged(dbpath)) as db:
    # User TLS settings need not match the seed, but referenced files must survive Restore.
    # Never let a restored active inbound silently borrow a target-only certificate/key.
    for stream_json, in db.execute('SELECT stream_settings FROM inbounds WHERE enable=1'):
        stream = json.loads(stream_json)
        if stream.get('security') == 'tls':
            for pair in stream.get('tlsSettings',{}).get('certificates',[]):
                for name in ('certificateFile','keyFile'):
                    if not pair.get(name): continue
                    staged(pair[name], tls_reference=True)
    rows = db.execute('SELECT key,value FROM settings').fetchall()
    settings = dict(rows)
    for name in ('webListen','webPort','webBasePath','webCertFile','webKeyFile',
                 'subListen','subCertFile','subKeyFile','subPort','subPath','subJsonPath'):
        if sum(k == name for k,v in rows) != 1: raise ValueError('Missing/duplicate setting: ' + name)
    if settings['webListen'] not in ('','127.0.0.1'): raise ValueError('Unexpected panel listen setting')
    if settings['subListen'] != '127.0.0.1':
        raise ValueError('Unexpected subscription listener')
    # upstream x-ui cert sets both listeners to the same panel-domain TLS lineage.
    for setting, filename in (('webCertFile','fullchain.pem'),('webKeyFile','privkey.pem'),
                              ('subCertFile','fullchain.pem'),('subKeyFile','privkey.pem')):
        expected = certroot + '/' + panel + '/' + filename
        if settings[setting] != expected: raise ValueError('Unexpected managed TLS reference: ' + setting)
        # Old v3 may omit compatibility links: recreate only these two known links in staging.
        link = root / expected.lstrip('/')
        if not link.exists() and not link.is_symlink():
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(letsencrypt + '/live/' + panel + '/' + filename)
        if staged(expected).read_bytes() != staged(letsencrypt + '/live/' + panel + '/' + filename).read_bytes():
            raise ValueError('Managed TLS reference does not match panel lineage: ' + setting)
    port, panel_port = settings['subPort'], settings['webPort']
    if not re.fullmatch(r'[0-9]{1,5}',panel_port) or not 1 <= int(panel_port) <= 65535:
        raise ValueError('Invalid panel port')
    panel_base = settings['webBasePath']
    if not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)+',panel_base):
        raise ValueError('Unexpected managed panel base path')
    if not re.fullmatch(r'[0-9]{1,5}',port) or not 1 <= int(port) <= 65535 or port == panel_port:
        raise ValueError('Invalid subscription port')
    sub, jsonpath = settings['subPath'], settings['subJsonPath']
    if not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)+',sub) or not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)+',jsonpath):
        raise ValueError('Unexpected managed subscription paths')
    # Repair only the exact old project-generated JSON URI, in the private staged DB.
    modern_json_uri = 'https://' + panel + jsonpath
    legacy_json_uri = modern_json_uri.rstrip('/') + '?name='
    enabled = [v for k,v in rows if k == 'subJsonEnable']
    if len(enabled) > 1 or (enabled and enabled[0] not in ('','true','false','True','False','TRUE','FALSE','t','f','T','F','1','0')):
        raise ValueError('Invalid/duplicate managed JSON enable setting')
    if sum(k == 'subJsonURI' for k,v in rows) > 1: raise ValueError('Duplicate JSON URI setting')
    # Missing/empty enable uses upstream's false default. Never enable on the user's behalf.
    if enabled == ['true'] and settings.get('subJsonURI') == legacy_json_uri:
        db.execute('UPDATE settings SET value=? WHERE key=?', (modern_json_uri, 'subJsonURI'))
    # Only the three exact installer-managed Host/inbound topologies may be migrated.
    managed_ids = set()
    for profile in ('reality','ws','xhttp'):
        hosts = db.execute('SELECT inbound_id,sort_order,address,port,security FROM hosts WHERE remark=?',
                           (profile,)).fetchall()
        # Only exact historical Host relationships are candidates. Deleted/edited profiles
        # are user state, not evidence that a historical repair is required.
        hosts = [h for h in hosts if h[1:] == (0,panel,443,'same' if profile == 'reality' else 'tls')]
        if not hosts: continue
        for iid in {h[0] for h in hosts}:
            inbound = db.execute('SELECT protocol,listen,port,tag,stream_settings,settings FROM inbounds WHERE id=?',
                                 (iid,)).fetchall()
            if not inbound: continue
            if len(inbound) != 1: raise ValueError('Ambiguous managed VLESS inbound: ' + profile)
            protocol, listen, number, tag, stream_json, settings_json = inbound[0]
            stream, inbound_settings = json.loads(stream_json), json.loads(settings_json)
            valid = protocol == 'vless' and isinstance(stream, dict) and isinstance(inbound_settings, dict)
            if profile == 'reality':
                valid = valid and (listen,str(number),tag,stream.get('network'),stream.get('security')) == (
                    '127.0.0.1','8443','inbound-8443','tcp','reality')
                valid = valid and stream.get('realitySettings',{}).get('target') == '127.0.0.1:9443'
                valid = valid and stream.get('realitySettings',{}).get('serverNames') == [reality]
                valid = valid and stream.get('tcpSettings',{}).get('acceptProxyProtocol') is True
            elif profile == 'ws':
                valid = valid and listen == '127.0.0.1' and str(number).isdigit() and 1024 <= int(number) <= 65535
                valid = valid and tag == 'inbound-' + str(number) and stream.get('network') == 'ws' and stream.get('security') == 'none'
                ws = stream.get('wsSettings',{})
                valid = valid and ws.get('host') == panel and ws.get('acceptProxyProtocol') is False
                valid = valid and isinstance(ws.get('path'),str) and bool(re.fullmatch('/'+str(number)+r'/[A-Za-z0-9]+',ws['path']))
            else:
                socket = '/dev/shm/uds2023.sock,0666'
                valid = valid and (listen,str(number),tag,stream.get('network'),stream.get('security')) == (
                    socket,'0','inbound-'+socket+':0|','xhttp','none')
                xhttp = stream.get('xhttpSettings',{})
                valid = valid and xhttp.get('mode') == 'stream-up' and isinstance(xhttp.get('path'),str)
                valid = valid and bool(re.fullmatch(r'/[A-Za-z0-9]+',xhttp['path']))
            if not valid: continue
            encryption = inbound_settings.get('encryption','')
            if not isinstance(encryption,str): raise ValueError('Invalid managed VLESS encryption: ' + profile)
            if not encryption:
                if (len(hosts)!=1 or iid in managed_ids or
                        db.execute('SELECT count(*) FROM inbounds WHERE tag=?',(tag,)).fetchone()[0] != 1):
                    raise ValueError('Ambiguous managed VLESS identity; staged migration refused: ' + profile)
                inbound_settings['encryption'] = 'none'
                db.execute('UPDATE inbounds SET settings=? WHERE id=?',(json.dumps(inbound_settings),iid))
            managed_ids.add(iid)
    # Only an exact old project Trojan/Host/route relationship is repaired in staging.
    # Custom profiles and already-separated method names are left untouched.
    shared = staged(nginx + '/snippets/includes.conf').read_text()
    for iid, listen, number, tag, stream_json in db.execute(
            "SELECT id,listen,port,tag,stream_settings FROM inbounds WHERE protocol='trojan'").fetchall():
        stream = json.loads(stream_json)
        if not isinstance(stream,dict): continue
        grpc = stream.get('grpcSettings',{})
        if not isinstance(grpc,dict): continue
        service = grpc.get('serviceName','')
        if (listen != '127.0.0.1' or not str(number).isdigit() or not 1024 <= int(number) <= 65535 or
                tag != 'inbound-' + str(number) or stream.get('network') != 'grpc' or
                stream.get('security') != 'none' or grpc.get('authority') != panel or
                grpc.get('multiMode') is not False or not isinstance(service,str) or
                not re.fullmatch('/'+str(number)+r'/[A-Za-z0-9]+',service)):
            continue
        hosts = db.execute('SELECT sort_order,address,port,security FROM hosts '
                           "WHERE inbound_id=? AND remark='trojan'",(iid,)).fetchall()
        if (0,panel,443,'tls') not in hosts: continue
        blocks = re.findall(r'^\s*location\s+=\s+'+re.escape(service)+r'\s*\{.*?^\s*\}',shared,re.M|re.S)
        expected = '''location = %s {
        if ($hack = 1) { return 404; }
        client_max_body_size 0;
        client_body_timeout 1d;
        grpc_read_timeout 1d;
        grpc_socket_keepalive on;
        grpc_set_header Host $host;
        grpc_pass grpc://127.0.0.1:%s;
    }''' % (service, number)
        if not blocks or any(' '.join(b.split()) != ' '.join(expected.split()) for b in blocks):
            continue
        if len(blocks) != 1 or hosts.count((0,panel,443,'tls')) != 1:
            raise ValueError('Ambiguous managed gRPC Host/route; staged migration refused')
        if db.execute('SELECT count(*) FROM inbounds WHERE tag=?',(tag,)).fetchone()[0] != 1:
            raise ValueError('Ambiguous managed gRPC tag; staged migration refused')
        grpc['serviceName'] = service + '|' + service.rsplit('/',1)[1] + '-multi'
        db.execute('UPDATE inbounds SET stream_settings=? WHERE id=?',(json.dumps(stream),iid))
    jsonpath = jsonpath.rstrip('/')
    expected = {sub, '= ' + sub.rstrip('/'), '~ ^' + sub + '(?<clash_sub_id>[^/]+)$',
                '/assets','/assets/',jsonpath,jsonpath + '/'}
    include = staged(nginx + '/snippets/includes.conf')
    text, location, depth, seen = include.read_text(), None, 0, set()
    for line in text.splitlines(keepends=True):
        match = re.match(r'\s*location\s+(.+?)\s*\{',line)
        if match:
            if depth: raise ValueError('Nested/ambiguous managed location')
            location = match[1]
        proxy = re.search(r'proxy_pass (https?)://127\.0\.0\.1:' + re.escape(port) + r';',line)
        if proxy:
            if location not in expected or location in seen: raise ValueError('Unexpected subscription backend context')
            if proxy[1] != 'https': raise ValueError('Subscription TLS DB requires HTTPS nginx backend')
            seen.add(location)
        # Installer-managed locations contain no brace-bearing literals.
        depth += line.count('{') - line.count('}')
        if depth == 0: location = None
        if depth < 0: raise ValueError('Invalid managed location braces')
    if depth or seen != expected: raise ValueError('Incomplete managed subscription routes')
    db.execute("UPDATE settings SET value='127.0.0.1' WHERE key='webListen' AND value='' ")
# Remove only the two exact old managed panel proxies from the staged camouflage vhost.
# The main panel vhost and shared include are intentionally outside this migration.
camouflage = staged(nginx + '/sites-available/' + reality)
text = camouflage.read_text()
for path in (panel_base, panel_base.rstrip('/')):
    block = f'''    location {path} {{
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass http://127.0.0.1:{panel_port};
    }}
'''
    if text.count(block) > 1:
        raise ValueError('Duplicate legacy REALITY panel location')
    text = text.replace(block, '', 1)
for location in re.findall(r'\blocation\s+([^{};\n]+?)\s*\{',text):
    # A custom/mismatched panel route is not safe to guess or silently preserve.
    if re.search(re.escape(panel_base.rstrip('/')) + r'(?:[^A-Za-z0-9_-]|$)',location):
        raise ValueError('Unexpected REALITY panel location; staged migration refused')
camouflage.write_text(text)
# Private nginx representation, including absolute archived cert/module symlinks.
validation.mkdir(mode=0o700)
for base in (nginx, letsencrypt, certroot):
    destination = validation / base.lstrip('/')
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(root / base.lstrip('/'),destination,symlinks=True)
bases = (nginx, letsencrypt, certroot, webroot, '/var/log/nginx')
for p in list(validation.rglob('*')):
    if not p.is_symlink(): continue
    target = os.readlink(p)
    if target.startswith('/') and any(target == b or target.startswith(b + '/') for b in bases):
        p.unlink(); p.symlink_to(validation / target.lstrip('/'))
    elif target.startswith('/usr/share/nginx/modules-available/'):
        content = pathlib.Path(target).read_text(); p.unlink(); p.write_text(content)
    elif target.startswith('/usr/lib/nginx/modules/'):
        # Module files remain distro-owned; never load an ELF supplied in the archive.
        pass
blocked_resources = {}
for p in (validation / nginx.lstrip('/')).rglob('*'):
    if p.is_dir() or p.is_symlink(): continue
    text = p.read_text()
    for base in sorted(bases,key=len,reverse=True):
        text = re.sub(re.escape(base) + r'(?=/|[\s;"\']|$)',lambda m: str(validation / base.lstrip('/')),text)
    text = re.sub(r'(?m)^(\s*pid\s+)\S+;',lambda m: m[1] + str(validation/'nginx.pid') + ';',text)
    # Only nginx knows which files exact/wildcard includes actually load. In this
    # private copy, neutralize unsafe directives before nginx can open their paths.
    # An inactive distro snippet is harmless; loading it must fail nginx -t.
    text = re.sub(r'(?m)^\s*#.*$', '', text)
    resources = r'''\b(include|error_log|access_log|ssl_certificate(?:_key)?|ssl_client_certificate|ssl_trusted_certificate|ssl_dhparam)\s+("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^;\s]+)'''
    def private_resource(match):
        directive, resource = match[1], match[2].strip('\"\'')
        if directive == 'error_log' and resource == '/dev/null':
            return match[0][:match.start(2)-match.start()] + 'stderr'
        if resource in ('off', 'stderr'): return match[0]
        if ('$' in resource or '\\' in resource or '..' in pathlib.PurePosixPath(resource).parts or
                (resource.startswith('/') and not resource.startswith(str(validation) + '/'))):
            marker = 'xui_untrusted_resource_' + str(len(blocked_resources))
            archived = p.relative_to(validation / nginx.lstrip('/'))
            blocked_resources[marker] = f'Untrusted nginx resource in {archived}: {directive} {resource} (outside private staged state)'
            return marker
        return match[0]
    text = re.sub(resources, private_resource, text)
    for module in re.findall(r'\bload_module\s+([^;]+);',text):
        module = module.strip()
        if not re.fullmatch(r'(?:/usr/lib/nginx/modules/|modules/)ngx_[A-Za-z0-9_]+\.so',module):
            raise ValueError('Untrusted nginx module path')
        text = text.replace('load_module ' + module + ';', 'load_module /usr/lib/nginx/modules/' + pathlib.Path(module).name + ';')
    p.write_text(text)
(validation / 'blocked-resources.json').write_text(json.dumps(blocked_resources))
(validation / 'var/log/nginx').mkdir(parents=True,exist_ok=True)
print('Staged TLS, renewal, panel and subscription state validated/normalized')
PY
    [[ $? == 0 ]] || die 'Staged core validation failed; current managed state was not changed.'
    nginx -t -p "$STAGING/nginx-validation/" -c "$STAGING/nginx-validation/etc/nginx/nginx.conf" \
        > "$STAGING/nginx-preflight.log" 2>&1 || {
        cat "$STAGING/nginx-preflight.log" >&2
        python3 - "$STAGING/nginx-validation/blocked-resources.json" "$STAGING/nginx-preflight.log" <<'PY'
import json, pathlib, sys
blocked = json.loads(pathlib.Path(sys.argv[1]).read_text())
log = pathlib.Path(sys.argv[2]).read_text()
for marker, message in blocked.items():
    if '"' + marker + '"' in log:
        print(message, file=sys.stderr)
PY
        die 'Staged nginx -t failed; current managed state was not changed.'
    }
    install -o root -g root -m 0755 "$STAGING/current-hook" "$hook" || die 'Cannot normalize staged project hook.'
}

load_restored_services() {
    local records service active enabled
    records=$(python3 - "$STAGING/meta.json" <<'PY'
import json, sys
meta = json.load(open(sys.argv[1]))
services = ['x-ui', 'nginx', 'mtr-backend', 'certbot.timer']
if meta['adguard_home']: services.append('AdGuardHome')
for service in services:
    state = meta['service_states'][service] if 'service_states' in meta else dict(active='active', enabled=True)
    print(service, state['active'], int(state['enabled']))
PY
    ) || die 'Cannot read saved service states.'
    while read -r service active enabled; do
        RESTORED_ACTIVE[$service]=$active RESTORED_ENABLED[$service]=$enabled
    done <<< "$records"
}

restore_service_states() {
    local service status
    for service in x-ui mtr-backend AdGuardHome nginx certbot.timer; do
        [[ "$service" != AdGuardHome || "$ADGUARD_HOME" == true ]] || continue
        if [[ "${RESTORED_ENABLED[$service]}" == 1 ]]; then
            if [[ "$service" == certbot.timer && "${RESTORED_ACTIVE[$service]}" == active ]]; then
                systemctl enable --now "$service" && systemctl is-active --quiet "$service" || die "Cannot enable and start $service."
            else systemctl enable "$service" || die "Cannot enable $service."; fi
            systemctl is-enabled --quiet "$service" || die "$service was not enabled."
        else
            systemctl disable "$service" || die "Cannot disable $service."
            if systemctl is-enabled --quiet "$service"; then die "$service is still enabled.";
            else status=$?; (( status == 1 )) || die "Cannot verify disabled $service."; fi
        fi
        if [[ "${RESTORED_ACTIVE[$service]}" == active ]]; then
            [[ "$service" != certbot.timer || "${RESTORED_ENABLED[$service]}" != 1 ]] || continue
            systemctl start "$service" || die "Cannot start $service."
            systemctl is-active --quiet "$service" || die "$service is not active"
        else
            systemctl stop "$service" || die "Cannot leave $service stopped."
        fi
    done
    RESUME_CERTBOT_TIMER=0
}

prepare_stopped_adguard_service() {
    # v0.107.79 -s install also starts AGH. Render its systemd contract without that side effect.
    install -o root -g root -m 0644 /dev/stdin /etc/systemd/system/AdGuardHome.service <<EOF || return 1
[Unit]
Description=AdGuard Home: Network-level blocker
ConditionFileIsExecutable=${AGH_DIR}/AdGuardHome
After=syslog.target network-online.target
[Service]
StartLimitInterval=5
StartLimitBurst=10
ExecStart=${AGH_DIR}/AdGuardHome -c ${AGH_DIR}/AdGuardHome.yaml -w ${AGH_DIR} --no-check-update -s run
WorkingDirectory=${AGH_DIR}
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=10
EnvironmentFile=-/etc/sysconfig/AdGuardHome
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload && agh_unit
}

save_restore_services() {
    local service state
    for service in x-ui nginx mtr-backend AdGuardHome certbot.timer; do
        state=$(systemctl is-active "$service") || :
        case "$state" in active|inactive|failed) OLD_ACTIVE[$service]=$state ;; *) die "Unknown original $service state." ;; esac
        if systemctl is-enabled --quiet "$service"; then OLD_ENABLED[$service]=1; else OLD_ENABLED[$service]=0; fi
    done
    RESTORE_RECOVERY=1
}

# Capture only keys about to be applied; old file contents are not runtime state.
snapshot_restore_sysctl() {
    local line key value
    local -A seen=()
    : > "$ROLLBACK_DIR/sysctl.before" || return 1
    while IFS= read -r line || [[ -n "$line" ]]; do
        line=${line%%#*}; line=${line%%;*}
        if [[ "$line" =~ ^[[:space:]]*-?([a-zA-Z0-9_./-]+)[[:space:]]*= ]]; then
            key=${BASH_REMATCH[1]}
            [[ ! ${seen[$key]+present} ]] || continue
            value=$(sysctl -n "$key") || return 1
            [[ "$value" != *$'\n'* ]] || return 1
            printf '%s=%s\n' "$key" "$value" >> "$ROLLBACK_DIR/sysctl.before" || return 1
            seen[$key]=1
        elif [[ "$line" =~ [^[:space:]] ]]; then
            warn 'Cannot snapshot unsupported managed sysctl assignment.'; return 1
        fi
    done < "$SYSCTL_FILE" || return 1
    touch "$ROLLBACK_DIR/sysctl.changed"
}

recover_restore_sysctl() {
    [[ -f "$ROLLBACK_DIR/sysctl.changed" ]] || return 0
    local key value actual
    sysctl -p "$ROLLBACK_DIR/sysctl.before" || return 1
    while IFS='=' read -r key value; do
        actual=$(sysctl -n "$key") && [[ "$actual" == "$value" ]] || return 1
    done < "$ROLLBACK_DIR/sysctl.before"
}

recover_restore_cron() {
    [[ -f "$ROLLBACK_DIR/cron.changed" ]] || return 0
    crontab -l > "$ROLLBACK_DIR/cron.current" || return 1
    cmp -s "$ROLLBACK_DIR/cron.before" "$ROLLBACK_DIR/cron.current" && return 0
    cmp -s "$ROLLBACK_DIR/cron.after" "$ROLLBACK_DIR/cron.current" || {
        warn 'Root crontab changed independently; original crontab retained for manual recovery.'; return 1;
    }
    crontab - < "$ROLLBACK_DIR/cron.before" && crontab -l > "$ROLLBACK_DIR/cron.current" &&
        cmp -s "$ROLLBACK_DIR/cron.before" "$ROLLBACK_DIR/cron.current"
}

recover_restore_acme_parents() {
    local path saved uid gid mode
    # Only parent metadata/presence is owned here, never their unrelated contents.
    for path in /var/www/acme/.well-known /var/www/acme; do
        saved=$(cat "$ROLLBACK_DIR/acme-parent-${path##*/}") || return 1
        if [[ "$saved" == absent ]]; then
            if [[ -e "$path" || -L "$path" ]]; then
                [[ -d "$path" && ! -L "$path" ]] && rmdir -- "$path" || return 1
            fi
        else
            read -r uid gid mode <<< "$saved"
            [[ -d "$path" && ! -L "$path" ]] &&
                chown "$uid:$gid" -- "$path" && chmod "$mode" -- "$path" &&
                [[ "$(stat -c '%u %g %a' -- "$path")" == "$saved" ]] || return 1
        fi
    done
}

snapshot_restore_target() {
    local path
    ROLLBACK_DIR=$(mktemp -d "$BACKUP_STORE/.rollback-XXXXXX") || die 'Cannot create private rollback directory.'
    chmod 0700 "$ROLLBACK_DIR" || die 'Cannot protect private rollback directory.'
    for path in /var/www/acme /var/www/acme/.well-known; do
        if [[ -e "$path" || -L "$path" ]]; then
            [[ -d "$path" && ! -L "$path" ]] || die "Cannot snapshot ACME parent directory: $path"
            stat -c '%u %g %a' -- "$path" > "$ROLLBACK_DIR/acme-parent-${path##*/}" || die "Cannot snapshot ACME parent metadata: $path"
        else
            printf 'absent\n' > "$ROLLBACK_DIR/acme-parent-${path##*/}" || die "Cannot snapshot ACME parent absence: $path"
        fi
    done
    local -a owned=("${RUNTIME_PATHS[@]}" "${TREE_PATHS[@]}" "${EXTRA_PATHS[@]}" /var/www/diagnostics /etc/systemd/system/AdGuardHome.service /var/www/acme/.well-known/acme-challenge)
    for path in "${owned[@]}"; do
        if [[ -e "$path" || -L "$path" ]]; then
            mkdir -p "$ROLLBACK_DIR/files$(dirname "$path")" || die "Cannot prepare rollback copy: $path"
            cp -aT --reflink=auto -- "$path" "$ROLLBACK_DIR/files$path" || die "Cannot copy rollback state: $path"
        fi
    done
    # Clean-host recovery has no previous objects to copy.
    for path in "$DB" /usr/local/x-ui/x-ui /etc/nginx/nginx.conf; do
        [[ ! -e "$path" || -f "$ROLLBACK_DIR/files$path" ]] || die "Missing rollback file: $path"
    done
    if [[ -f "$DB" ]]; then quick_check "$ROLLBACK_DIR/files$DB"; fi
    # Successful copies and SQLite validation must precede the first deletion.
    printf 'complete\n' > "$ROLLBACK_DIR/ready" || die 'Cannot mark rollback snapshot ready.'
}

recover_restore_target() {
    local service path failed=0
    if (( RESTORE_MUTATED )); then
        [[ -f "$ROLLBACK_DIR/ready" ]] || return 1
        for service in nginx x-ui mtr-backend AdGuardHome; do
            if systemctl cat "$service" >/dev/null 2>&1; then systemctl stop "$service" || failed=1; fi
        done
        (( ! failed )) || return 1
        for path in "${RUNTIME_PATHS[@]}" "${TREE_PATHS[@]}" "${EXTRA_PATHS[@]}" /var/www/diagnostics /etc/systemd/system/AdGuardHome.service /var/www/acme/.well-known/acme-challenge; do
            rm -rf -- "$path" || failed=1
            if [[ -e "$ROLLBACK_DIR/files$path" || -L "$ROLLBACK_DIR/files$path" ]]; then
                mkdir -p "$(dirname "$path")" && cp -aT -- "$ROLLBACK_DIR/files$path" "$path" || failed=1
            fi
        done
        recover_restore_acme_parents || { warn 'Cannot verify original ACME parent directories; independent contents retained.'; failed=1; }
        recover_restore_firewall || { warn 'Cannot verify original UFW rules/state.'; failed=1; }
        recover_restore_cron || { warn 'Cannot verify original root crontab.'; failed=1; }
        recover_restore_sysctl || { warn 'Cannot verify original runtime sysctl values.'; failed=1; }
        systemctl daemon-reload || failed=1
        if [[ "${OLD_ACTIVE[nginx]}" == active ]]; then nginx -t || failed=1; fi
        rm -f -- "$XHTTP_SOCKET" || failed=1
    fi
    for service in x-ui mtr-backend AdGuardHome nginx certbot.timer; do
        if [[ "${OLD_ACTIVE[$service]}" == active ]]; then
            systemctl is-active --quiet "$service" || systemctl start "$service" || failed=1
            systemctl is-active --quiet "$service" || failed=1
        else
            if systemctl is-active --quiet "$service"; then systemctl stop "$service" || failed=1; fi
        fi
        if [[ "${OLD_ENABLED[$service]}" == 1 ]]; then
            systemctl enable "$service" || failed=1
        elif systemctl is-enabled --quiet "$service"; then
            systemctl disable "$service" || failed=1
        fi
    done
    (( ! failed ))
}

cmd_restore() {
    stage 'Restore preflight'
    local archive=${1:-} service path
    [[ -n "$archive" && -f "$archive" ]] || die 'Usage: x-ui-backup restore <existing archive.tar.gz>'
    archive=$(readlink -f -- "$archive")
    for path in "${RUNTIME_PATHS[@]}" "${TREE_PATHS[@]}" "${EXTRA_PATHS[@]}" /var/www/diagnostics; do
        [[ "$archive" != "$path" && "$archive" != "$path/"* ]] ||
            die 'Move the archive outside managed paths (for example /var/backups/x-ui) before restore.'
    done
    host_identity
    # Bootstrap archive tools before validation/extraction; managed state is untouched.
    install_missing_packages python3 gzip tar
    gzip -t -- "$archive" || die 'Archive gzip integrity check failed.'
    validate_archive "$archive"
    prepare_store restore
    tar -xzf "$archive" -C "$STAGING" --same-owner
    check_compatibility
    install_missing_packages "${PACKAGES[@]}"
    check_python_dependencies
    quick_check "$STAGING/files$DB"
    ADGUARD_HOME=$(python3 -c 'import json,sys; print(str(json.load(open(sys.argv[1]))["adguard_home"]).lower())' "$STAGING/meta.json")
    load_restored_services
    if [[ "$ADGUARD_HOME" == true ]]; then
        preflight_staged_adguard
    fi
    preflight_staged_core
    preflight_target_certbot_ownership
    local certificate_domains vision_account_domain
    certificate_domains=$(restored_certificate_domains "$STAGING/files/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx") || die 'Invalid certificate domains.'
    vision_account_domain=$(restored_vision_domain "$STAGING/files/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision") || die 'Invalid Vision domain.'
    local -a account_domains
    mapfile -t account_domains <<< "$certificate_domains"
    [[ -z "$vision_account_domain" ]] || account_domains+=("$vision_account_domain")
    project_certbot_accounts "$STAGING/files/etc/letsencrypt" "${account_domains[@]}" > /dev/null || die 'Invalid/conflicting managed Certbot account metadata.'
    save_restore_services
    pause_certbot_timer
    # Quiesce only after incoming staged state passes all static/native checks.
    for service in nginx x-ui mtr-backend AdGuardHome; do
        if systemctl cat "$service" >/dev/null 2>&1; then
            systemctl stop "$service" || die "Cannot stop $service before rollback snapshot."
        fi
    done
    snapshot_restore_target
    RESTORE_MUTATED=1
    cleanup_adguard || die 'Cannot clean target AdGuard Home; core state was not replaced.'
    stage 'Stopping services and restoring managed state'
    replace_managed_state
    install -d -o root -g root -m 0755 /etc/nginx/snippets/x-ui-auto-optional || die 'Cannot prepare optional nginx include directory.'
    if [[ "$ADGUARD_HOME" == true ]]; then
        chown -R root:root /opt/AdGuardHome
        chmod 0700 /opt/AdGuardHome
        chmod 0755 /opt/AdGuardHome/AdGuardHome
        chmod 0600 /opt/AdGuardHome/AdGuardHome.yaml /opt/AdGuardHome/managed.json
        . /usr/local/lib/3x-ui-pro/managed-adguard.sh
        agh_config && [[ "$AGH_ARCH" == "$ARCH" ]] || die 'Cannot validate restored AdGuard Home state.'
        if [[ "${RESTORED_ACTIVE[AdGuardHome]}" == active ]]; then
            agh_install_service || die 'Cannot recreate/start restored AdGuard Home service.'
        else
            prepare_stopped_adguard_service || die 'Cannot recreate stopped AdGuard Home service.'
        fi
    fi
    repair_panel_certificates
    prepare_mtr_backend
    regenerate_diagnostics
    rm -rf /var/www/acme/.well-known/acme-challenge
    prepare_acme_webroot
    remove_legacy_certbot_cron || die 'Cannot remove the exact legacy project renewal job.'
    restore_firewall
    stage 'Restoring saved service states'
    systemctl daemon-reload
    nginx -t > "$STAGING/nginx-test.log" 2>&1 || die 'nginx -t failed; nginx was not started. Fix the configuration and rerun restore.'
    rm -f -- "$XHTTP_SOCKET"
    restore_service_states
    check_health
    RESTORE_RECOVERY=0 RESTORE_MUTATED=0
    rm -rf -- "$ROLLBACK_DIR"
    ROLLBACK_DIR=''
    printf '\nRestore completed successfully.\n'
    warn 'Recovery uses the saved domains. On a new VPS, point their DNS to this VPS separately.'
}

# Explicit one-shot maintenance: reuse trusted renderers without running Restore.
cmd_update_hooks() (
    local deploy=/etc/letsencrypt/renewal-hooks/deploy domains vision directory='' name
    local -a hooks=(3x-ui-auto-nginx) changed=() names
    [[ -d "$deploy" && ! -L /etc/letsencrypt && ! -L /etc/letsencrypt/renewal-hooks && ! -L "$deploy" ]] ||
        die 'Unsafe/missing project deploy directory; no hooks changed.'
    domains=$(restored_certificate_domains "$deploy/3x-ui-auto-nginx") || die 'Unrecognized project hook; no hooks changed.'
    mapfile -t names <<< "$domains"
    vision=$(restored_vision_domain "$deploy/3x-ui-auto-nginx-vision") || die 'Unrecognized Vision hook; no hooks changed.'
    [[ -z "$vision" ]] || hooks+=(3x-ui-auto-nginx-vision)
    for name in "${hooks[@]}"; do
        [[ "$(stat -c '%u:%g:%a' "$deploy/$name")" == '0:0:755' ]] || die 'Unowned project hook; no hooks changed.'
    done
    directory=$(mktemp -d /etc/letsencrypt/.3x-ui-hooks-XXXXXX) || die 'Cannot prepare private hook update.'
    chmod 0700 "$directory" || die 'Cannot protect hook update directory.'
    # Each rename is atomic; a later failure restores every attempted replacement.
    trap 'result=$?; trap - EXIT ERR; if (( result )); then
        for name in "${changed[@]}"; do
            if cp -a -- "$directory/$name.old" "$directory/$name.restore" &&
               mv -fT -- "$directory/$name.restore" "$deploy/$name"; then :;
            else warn "Cannot restore project hook: $name"; fi
        done
        warn "Hook update failed; original files retained in $directory";
    fi; exit "$result"' EXIT
    trap 'exit 1' ERR
    trap 'exit 130' INT
    trap 'exit 143' TERM
    render_certificate_hook "${names[0]}" "${names[1]}" > "$directory/3x-ui-auto-nginx.new"
    if [[ -n "$vision" ]]; then render_vision_hook "$vision" > "$directory/3x-ui-auto-nginx-vision.new"; fi
    # Prepare and validate both files before the first replacement.
    for name in "${hooks[@]}"; do
        bash -n "$directory/$name.new"
        chown root:root "$directory/$name.new"
        chmod 0755 "$directory/$name.new"
        cp -a -- "$deploy/$name" "$directory/$name.old"
    done
    for name in "${hooks[@]}"; do
        cmp -s "$deploy/$name" "$directory/$name.new" && continue
        changed+=("$name")
        mv -fT -- "$directory/$name.new" "$deploy/$name"
    done
    if (( ${#changed[@]} )); then
        ok 'Hooks updated successfully; services and certbot.timer were not changed.'
        printf 'Original hooks: %s\n' "$directory"
    else
        rm -rf -- "$directory"
        ok 'Project hooks are already current.'
    fi
)

cmd_list() {
    local archive
    shopt -s nullglob
    local archives=("$BACKUP_STORE"/*.tar.gz)
    if (( ! ${#archives[@]} )); then printf 'No backups in %s\n' "$BACKUP_STORE"; return; fi
    for archive in "${archives[@]}"; do
        printf '%-52s %8s\n' "${archive##*/}" "$(du -h "$archive" | cut -f1)"
    done
}

main() {
    require_root
    export LC_ALL=C
    trap cleanup EXIT
    trap 'printf "[FAIL] Operation failed during: %s\n" "$STAGE" >&2; exit 1' ERR
    trap 'exit 130' INT
    trap 'exit 143' TERM
    case ${1:-} in
        backup) cmd_backup ;;
        restore) cmd_restore "${2:-}" ;;
        list) cmd_list ;;
        update-hooks) cmd_update_hooks ;;
        *) die 'Usage: x-ui-backup {backup|restore <archive>|list|update-hooks}' ;;
    esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
