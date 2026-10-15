#!/bin/bash
# 3x-ui Auto Nginx - based on x-ui-pro-refactor by mozaroc (github.com/mozaroc/3x-ui-pro)
[[ $EUID -ne 0 ]] && { echo "Run as root: sudo bash $0"; exit 1; }

# ─── Output helpers ──────────────────────────────────────────────────────────
msg_ok()  { printf '\e[1;32m%s\e[0m\n' "$1"; }
msg_err() { echo -e "\e[1;41m $1 \e[0m"; }
msg_inf() { echo -e "\e[1;34m$1\e[0m"; }
msg_warn() { printf '\e[1;33m%s\e[0m\n' "$1"; }

echo
msg_inf '3X-UI AUTO NGINX'
echo

# ─── Pre-flight checks ───────────────────────────────────────────────────────
check_os() {
    local os_id os_version
    os_id=$(grep -oP '(?<=^ID=).+' /etc/os-release 2>/dev/null | tr -d '"')
    os_version=$(grep -oP '(?<=^VERSION_ID=").+(?=")' /etc/os-release 2>/dev/null)

    case "${os_id}" in
        ubuntu)
            [[ "$os_version" == "24.04" || "$os_version" == "26.04" ]] && return 0
            ;;
        debian)
            [[ "$os_version" == "13" ]] && return 0
            ;;
    esac

    msg_err "Unsupported OS: ${os_id} ${os_version}"
    echo -e "\nThis script supports:\n  Ubuntu 24.04 / 26.04\n  Debian 13"
    echo -e "\nPlease reinstall your server with one of the supported OS versions and try again."
    exit 1
}

check_cpu() {
    local cpuinfo="${1:-/proc/cpuinfo}" arch feature_field cpu_model cpu_flags
    CPU_SUPPORT_LEVEL="info"
    CPU_SUPPORT_TEXT="Compatible (acceleration not assessed)"
    arch=$(uname -m 2>/dev/null) || return 0
    case "$arch" in
        x86_64|i386|i486|i586|i686) feature_field="flags" ;;
        aarch64|arm64) feature_field="Features" ;;
        *) return 0 ;;
    esac
    cpu_model=$(grep -m1 -E '^[[:space:]]*model name[[:space:]]*:' "$cpuinfo" 2>/dev/null) || cpu_model=""
    cpu_flags=$(grep -m1 -E "^[[:space:]]*${feature_field}[[:space:]]*:" "$cpuinfo" 2>/dev/null) || return 0
    cpu_flags="${cpu_flags#*:}"
    [[ -n "${cpu_flags//[[:space:]]/}" ]] || return 0

    if [[ " $cpu_flags " =~ [[:space:]]aes[[:space:]] ]]; then
        CPU_SUPPORT_LEVEL="ok"
        CPU_SUPPORT_TEXT="Compatible (hardware AES available)"
    else
        CPU_SUPPORT_LEVEL="warn"
        CPU_SUPPORT_TEXT="Compatible — hardware AES unavailable"
        msg_warn "Hardware AES unavailable. Xray can run, but cryptographic performance may be lower."
        if [[ "${cpu_model,,}" == *qemu* ]]; then
            msg_warn "Generic QEMU/KVM CPU detected: host-passthrough / AES exposure is recommended when available."
        fi
        msg_warn "Continuing installation."
    fi
}

check_os
check_cpu

# ─── Constants ───────────────────────────────────────────────────────────────
XUIDB="/etc/x-ui/x-ui.db"
PROJECT_REF="${XUI_AUTO_REF:-main}"
configure_project_source() {
    if [[ "$PROJECT_REF" != main && ! "$PROJECT_REF" =~ ^[a-fA-F0-9]{40}$ &&
          ! "$PROJECT_REF" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        msg_err 'Invalid XUI_AUTO_REF: use main, an exact 40-hex commit SHA, or a stable vMAJOR.MINOR.PATCH tag.'
        return 1
    fi
    GITHUB_RAW="https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/${PROJECT_REF}"
}
configure_project_source || exit 1
FAKE_SITE_COUNT=10
LEGACY_CERTBOT_CRON='@monthly certbot renew --non-interactive --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx" > /dev/null 2>&1'

# ─── Default argument values ─────────────────────────────────────────────────
domain=""
reality_domain=""
UNINSTALL="x"
INSTALL="y"
AUTODOMAIN="n"
CFALLOW="n"
PANEL_VERSION=""
INSTALL_AGH=n
INSTALL_SECURITY=n
DNS_PREPARED=n
DNS_FINALIZED=n
DNS_ROLLBACK_ATTEMPTED=n
DNS_ROLLBACK_RESULT=not_requested
INSTALL_VISION=n
CREATE_CLIENT=n
vision_domain=''

# ─── Stop & clean previous install (called from main, after domain validation) ─
clean_previous_install() {
    systemctl stop x-ui 2>/dev/null || true
    if [[ "${VISION_PREVIOUS_HOOK:-}" == owned ]]; then
        rm -f /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision
    fi
    rm -rf /etc/systemd/system/x-ui.service || return 1
    rm -rf /usr/local/x-ui || return 1
    rm -rf /etc/x-ui || return 1
    rm -rf /etc/nginx/sites-enabled/* || return 1
    rm -rf /etc/nginx/sites-available/* || return 1
    rm -rf /etc/nginx/stream-enabled/* || return 1
}

# ─── Port / path generators ──────────────────────────────────────────────────
get_port() {
    echo $(( ((RANDOM<<15)|RANDOM) % 49152 + 10000 ))
}

gen_random_string() {
    local length="$1"
    head -c 4096 /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c "$length"
    echo
}

# Matches the panel's host group_id format (16 lowercase alphanumerics)
gen_group_id() {
    head -c 4096 /dev/urandom | tr -dc 'a-z0-9' | head -c 16
    echo
}

check_free() {
    nc -z 127.0.0.1 "$1" &>/dev/null
    return $?
}

make_port() {
    while true; do
        local PORT
        PORT=$(get_port)
        if ! check_free "$PORT"; then
            echo "$PORT"
            break
        fi
    done
}

# ─── Generate ports & paths (done once at startup) ───────────────────────────
sub_port=$(make_port)
panel_port=$(make_port)
ws_port=$(make_port)
trojan_port=$(make_port)

sub_path=$(gen_random_string 10)
json_path=$(gen_random_string 10)
panel_path=$(gen_random_string 10)
ws_path=$(gen_random_string 10)
trojan_path=$(gen_random_string 10)
xhttp_path=$(gen_random_string 10)
config_username=$(gen_random_string 10)
config_password=$(gen_random_string 10)
diag_path="/net-$(gen_random_string 12)/"
diag_token=$(gen_random_string 16)
mtr_backend_port=$(make_port)

# ─── Argument parsing ────────────────────────────────────────────────────────
while [ "$#" -gt 0 ]; do
    case "$1" in
        -install)          INSTALL="$2";           shift 2 ;;
        -subdomain)        domain="$2";            shift 2 ;;
        -reality_domain)   reality_domain="$2";    shift 2 ;;
        -ONLY_CF_IP_ALLOW) CFALLOW="$2";           shift 2 ;;
        -version)
            PANEL_VERSION="${2:-}"
            [[ -n "$PANEL_VERSION" ]] || { msg_err "-version requires a stable release tag."; exit 1; }
            shift 2 ;;
        -uninstall)        UNINSTALL="$2";         shift 2 ;;
        *)                 shift 1 ;;
    esac
done

# Only stable release versions at or above the supported security baseline.
_validate_panel_version() {
    local version="${1#v}"
    if [[ ! "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] ||
       [[ "$(printf '%s\n' 3.8.0 "$version" | sort -V | head -n1)" != "3.8.0" ]]; then
        msg_err "Unsupported 3X-UI version: $1. Use a stable release >= v3.8.0."
        return 1
    fi
}

# Reject unsafe/invalid -version values before uninstall or rebuild actions.
if [[ -n "$PANEL_VERSION" ]]; then
    _validate_panel_version "$PANEL_VERSION" || exit 1
fi

# ─── Detect package manager ───────────────────────────────────────────────────
Pak=$(type apt &>/dev/null && echo "apt" || echo "yum")

# ─────────────────────────────────────────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────────────────────────────────────────
detect_existing_installation() {
    EXISTING_INSTALL_CATEGORIES=()
    if [[ -e /etc/x-ui || -e /usr/local/x-ui || -e /usr/bin/x-ui ||
          -e /etc/systemd/system/x-ui.service || -e /lib/systemd/system/x-ui.service ]] ||
       systemctl is-active --quiet x-ui 2>/dev/null || systemctl is-enabled --quiet x-ui 2>/dev/null; then
        EXISTING_INSTALL_CATEGORIES+=("3X-UI installation")
    fi
    if [[ -e /usr/local/lib/3x-ui-pro || -e /usr/local/bin/x-ui-backup ||
          -e /etc/systemd/system/mtr-backend.service ]] ||
       systemctl is-active --quiet mtr-backend 2>/dev/null || systemctl is-enabled --quiet mtr-backend 2>/dev/null; then
        EXISTING_INSTALL_CATEGORIES+=("Project runtime / diagnostics")
    fi
    if [[ -d /etc/nginx ]] || compgen -G '/etc/nginx/sites-enabled/*' >/dev/null ||
       compgen -G '/etc/nginx/sites-available/*' >/dev/null || compgen -G '/etc/nginx/stream-enabled/*' >/dev/null ||
       compgen -G '/etc/nginx/snippets/*' >/dev/null ||
       [[ "$(dpkg-query -W -f='${Status}' nginx-common 2>/dev/null)" == 'install ok installed' ]]; then
        EXISTING_INSTALL_CATEGORIES+=("nginx configuration / package")
    fi
    if [[ -d /root/cert ]] || compgen -G '/etc/letsencrypt/live/*' >/dev/null; then
        EXISTING_INSTALL_CATEGORIES+=("TLS certificates")
    fi
    if command -v crontab >/dev/null && LC_ALL=C crontab -l 2>/dev/null | grep -Fxq -- "$LEGACY_CERTBOT_CRON"; then
        EXISTING_INSTALL_CATEGORIES+=("Legacy project certificate renewal")
    fi
    if [[ -e /opt/AdGuardHome || -e /etc/systemd/system/AdGuardHome.service ||
          -e /etc/nginx/snippets/adguard.conf || -e /etc/nginx/snippets/x-ui-auto-optional/adguard.conf ]] ||
       systemctl is-active --quiet AdGuardHome 2>/dev/null || systemctl is-enabled --quiet AdGuardHome 2>/dev/null ||
       grep -RqE 'location.*(/adg-|/dns-query)' /etc/nginx/sites-available /etc/nginx/snippets 2>/dev/null; then
        EXISTING_INSTALL_CATEGORIES+=("AdGuard Home")
    fi
    return 0
}

confirm_destructive_reinstall() {
    local answer category
    detect_existing_installation
    (( ${#EXISTING_INSTALL_CATEGORIES[@]} )) || return 0
    msg_warn '============================================================'
    msg_warn '  Existing installation detected'
    msg_warn '============================================================'
    for category in "${EXISTING_INSTALL_CATEGORIES[@]}"; do msg_warn " [!] $category"; done
    printf '\nContinuing will run a full OS dist-upgrade (services may restart),\nremove the current 3X-UI deployment and replace nginx configuration.\nThe OS upgrade cannot be rolled back. Copy a backup off-host first.\n\n'
    printf 'Type YES to remove the existing deployment and continue: '
    if ! IFS= read -r answer || [[ "$answer" != YES ]]; then
        msg_err 'Cancelled. Existing deployment was not changed.'
        return 1
    fi
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
        crontab - < "$directory/new" && crontab -l > "$directory/verified" &&
            cmp -s "$directory/new" "$directory/verified" || { rm -rf "$directory"; return 1; }
    fi
    rm -rf "$directory"
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

uninstall_xui() {
    cleanup_adguard || { msg_err "Cannot clean AdGuard Home; core deployment was not removed."; return 1; }
    remove_legacy_certbot_cron || { msg_err "Cannot remove the exact legacy certificate renewal job."; return 1; }
    rm -f /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx || return 1
    printf 'y\n' | x-ui uninstall 2>/dev/null || true
    rm -rf /etc/x-ui/ /usr/local/x-ui/
    rm -f  /usr/bin/x-ui
    $Pak -y remove nginx nginx-common nginx-core nginx-full
    $Pak -y purge  nginx nginx-common nginx-core nginx-full
    $Pak -y autoclean
    rm -rf /var/www/html/ /var/www/diagnostics/ /var/www/subpage/ /etc/nginx/ /usr/share/nginx/
    systemctl stop mtr-backend 2>/dev/null || true
    systemctl disable mtr-backend 2>/dev/null || true
    rm -f /etc/systemd/system/mtr-backend.service
    rm -rf /usr/local/lib/3x-ui-pro/
    systemctl daemon-reload 2>/dev/null || true
}

if [[ ${UNINSTALL} == *"y"* ]]; then
    confirm_destructive_reinstall || exit 1
    uninstall_xui || exit 1
    msg_ok "3X-UI Auto Nginx completely uninstalled."
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# GET SERVER IP
# ─────────────────────────────────────────────────────────────────────────────
IP4_REGEX="^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$"
IP6_REGEX="([a-f0-9:]+:+)+[a-f0-9]+"

get_server_ip() {
    IP4=$(ip route get 8.8.8.8 2>&1 | grep -Po -- 'src \K\S*')
    IP6=$(ip route get 2620:fe::fe 2>&1 | grep -Po -- 'src \K\S*')
    [[ $IP4 =~ $IP4_REGEX ]] || IP4=$(curl -4 -fsS --connect-timeout 5 --max-time 10 https://ipv4.icanhazip.com | tr -d '[:space:]')
    [[ $IP6 =~ $IP6_REGEX ]] || IP6=$(curl -6 -fsS --connect-timeout 5 --max-time 10 https://ipv6.icanhazip.com 2>/dev/null | tr -d '[:space:]')
    [[ $IP4 =~ $IP4_REGEX ]] || IP4=""
    [[ $IP6 =~ $IP6_REGEX ]] || IP6=""
}

# Early IP fetch for auto-domain
IP4=$(ip route get 8.8.8.8 2>&1 | grep -Po -- 'src \K\S*')
[[ $IP4 =~ $IP4_REGEX ]] || IP4=$(curl -4 -fsS --connect-timeout 5 --max-time 10 https://ipv4.icanhazip.com | tr -d '[:space:]')
[[ $IP4 =~ $IP4_REGEX ]] || IP4=""


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
validate_domains() {
    while true; do
        [[ -n "$domain" ]] && break
        printf 'Enter the domain for your 3X-UI panel: '
        read -r domain || { msg_err "Panel domain is required."; return 1; }
    done
    domain=$(echo "$domain" | tr -d '[:space:]')
    SubDomain=$(echo "$domain"   | sed 's/^[^ ]* \|\..*//g')
    MainDomain=$(echo "$domain"  | sed 's/.*\.\([^.]*\..*\)$/\1/')
    [[ "${SubDomain}.${MainDomain}" != "${domain}" ]] && MainDomain=${domain}

    while true; do
        [[ -n "$reality_domain" ]] && break
        printf 'Enter the domain for VLESS REALITY: '
        read -r reality_domain || { msg_err "REALITY domain is required."; return 1; }
    done
    reality_domain=$(echo "$reality_domain" | tr -d '[:space:]')
    RealitySubDomain=$(echo "$reality_domain" | sed 's/^[^ ]* \|\..*//g')
    RealityMainDomain=$(echo "$reality_domain" | sed 's/.*\.\([^.]*\..*\)$/\1/')
    [[ "${RealitySubDomain}.${RealityMainDomain}" != "${reality_domain}" ]] && RealityMainDomain=${reality_domain}

    if [[ "$domain" == "$reality_domain" ]]; then
        msg_err "Panel domain and REALITY domain must be different! Got: ${domain}"
        exit 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL PACKAGES
# ─────────────────────────────────────────────────────────────────────────────
apt_system() {
    local output attempt rc deadline=$((SECONDS + 300))
    local -a statuses
    output=$(mktemp) || return 1
    for attempt in {1..30}; do
        if DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l UCF_FORCE_CONFFOLD=1 \
            apt-get -o DPkg::Lock::Timeout=300 -o Dpkg::Options::=--force-confdef \
            -o Dpkg::Options::=--force-confold -o Acquire::Retries=3 \
            -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 \
            --no-remove "$@" 2>&1 | tee "$output"; then
            statuses=("${PIPESTATUS[@]}")
        else
            statuses=("${PIPESTATUS[@]}")
        fi
        rc=${statuses[0]}
        (( statuses[1] == 0 )) || { rm -f "$output"; return 1; }
        if (( rc == 0 )); then rm -f "$output"; return 0; fi
        # apt update's lists lock does not use DPkg::Lock::Timeout.
        if ! grep -Eq 'Could not get lock|Unable to acquire.*lock' "$output"; then break; fi
        (( SECONDS < deadline )) || break
        sleep 10
    done
    rm -f "$output"; return "$rc"
}

setup_swap() {
    [[ "${INSTALL_SECURITY:-n}" == y ]] || return 0
    SWAP_RESULT=skipped
    SWAP_REASON='required tools unavailable'
    local tool active fs available fstab_tmp='' identity
    for tool in swapon swapoff findmnt df awk fallocate chmod mkswap stat cp mv mktemp grep rm; do
        command -v "$tool" >/dev/null || return 0
    done
    SWAP_REASON='cannot inspect active swap'
    active=$(swapon --show=NAME --noheadings --raw) || return 0
    if [[ -n "$active" ]]; then SWAP_RESULT=existing; return 0; fi
    SWAP_REASON='/swapfile already exists'
    [[ ! -e /swapfile && ! -L /swapfile ]] || return 0
    SWAP_REASON='unsupported filesystem'
    fs=$(findmnt -n -o FSTYPE --target /) || return 0
    [[ "$fs" == ext4 || "$fs" == xfs ]] || return 0
    SWAP_REASON='less than 4 GiB free'
    available=$(df -Pk / | awk 'END {print $4}') || return 0
    [[ "$available" =~ ^[0-9]+$ ]] && (( available >= 4194304 )) || return 0
    SWAP_REASON='fstab unavailable or already references /swapfile'
    [[ -f /etc/fstab && ! -L /etc/fstab ]] || return 0
    awk '$1 == "/swapfile" {found=1} END {exit found}' /etc/fstab || return 0
    SWAP_REASON='cannot create private swap file'
    (set -o noclobber; umask 077; : > /swapfile) 2>/dev/null || return 0
    identity=$(stat -c '%d:%i' /swapfile) || { rm -f /swapfile; return 0; }
    # Only this invocation's file is owned; never remove pre-existing swap.
    while :; do
        SWAP_REASON='allocation failed'
        fallocate -l 1G /swapfile && chmod 600 /swapfile || break
        SWAP_REASON='mkswap failed'
        mkswap /swapfile || break
        SWAP_REASON='activation failed'
        swapon /swapfile || break
        active=$(swapon --show=NAME --noheadings --raw) || break
        grep -Fxq /swapfile <<< "$active" || break
        SWAP_REASON='fstab update failed'
        # Stage the append privately: a failed write must not leave a partial entry.
        fstab_tmp=$(mktemp /etc/.3x-ui-fstab.XXXXXX) || break
        cp -p /etc/fstab "$fstab_tmp" || break
        printf '\n/swapfile none swap sw 0 0\n' >> "$fstab_tmp" || break
        mv -f "$fstab_tmp" /etc/fstab || break
        SWAP_RESULT=created
        return 0
    done
    [[ -z "$fstab_tmp" ]] || rm -f "$fstab_tmp"
    if active=$(swapon --show=NAME --noheadings --raw); then
        if grep -Fxq /swapfile <<< "$active"; then
            swapoff /swapfile || { SWAP_REASON+='; swap cleanup failed'; return 0; }
        fi
        if [[ ! -L /swapfile && "$(stat -c '%d:%i' /swapfile)" == "$identity" ]]; then
            rm -f /swapfile || SWAP_REASON+='; file cleanup failed'
        fi
    else
        SWAP_REASON+='; activation unknown, file retained'
    fi
    return 0
}

preflight_base_os() {
    local audit binary
    for binary in apt-get apt-config dpkg systemctl timedatectl getent /usr/sbin/sshd; do
        command -v "$binary" >/dev/null || { msg_err "Base OS tool unavailable: $binary"; return 1; }
    done
    audit=$(dpkg --audit) || return 1
    [[ -z "$audit" ]] || { msg_err 'Incomplete dpkg state; repair it before installation.'; return 1; }
    BASE_SSH_POLICY=$(/usr/sbin/sshd -T) || return 1
    systemctl is-active --quiet ssh.service || systemctl is-active --quiet ssh.socket || {
        msg_err 'No active SSH service/socket; refusing OS preparation.'; return 1;
    }
    BASE_SSH_LISTEN=''
    if systemctl is-active --quiet ssh.socket; then
        BASE_SSH_LISTEN=$(systemctl show ssh.socket -p Listen --value) || return 1
    fi
    getent ahosts debian.org >/dev/null || { msg_err 'Initial libc DNS resolution failed.'; return 1; }
}

verify_base_os() {
    local binary
    [[ "$(/usr/sbin/sshd -T)" == "$BASE_SSH_POLICY" ]] || { msg_err 'Effective SSH policy changed during OS preparation.'; return 1; }
    systemctl is-active --quiet ssh.service || systemctl is-active --quiet ssh.socket || return 1
    if [[ -n "$BASE_SSH_LISTEN" ]]; then
        [[ "$(systemctl show ssh.socket -p Listen --value)" == "$BASE_SSH_LISTEN" ]] && systemctl is-active --quiet ssh.socket || return 1
    fi
    for binary in curl wget jq python3 openssl ip ss ufw; do
        command -v "$binary" >/dev/null || return 1
    done
    getent ahosts debian.org >/dev/null
}

prepare_base_os() {
    msg_warn 'Preparing OS: full dist-upgrade; package changes cannot be rolled back.'
    apt_system -o APT::Update::Error-Mode=any update || { msg_err "APT list refresh failed (exit $?). Package changes are not rolled back."; return 1; }
    # Simulation and execution both reject any package removal.
    apt_system -s -y dist-upgrade || { msg_err "Full upgrade simulation failed (exit $?). No deployment cleanup was performed."; return 1; }
    apt_system -y dist-upgrade || { msg_err "Full OS upgrade failed (exit $?). Package changes are not rolled back."; return 1; }
    apt_system -y --no-install-recommends install curl wget jq python3 openssl \
        ca-certificates procps iproute2 ufw tar gzip || { msg_err "System dependency installation failed (exit $?). Package changes are not rolled back."; return 1; }
    verify_base_os || return 1
    BASE_OS_RESULT=configured
}

prepare_system_dns() {
    [[ "${INSTALL_SECURITY:-n}" == y ]] || return 0
    local output status
    DNS_PREPARED=y
    if ! output=$(python3 "$PANEL_STAGE/managed-security.py" --prepare-dns "$PANEL_STAGE/dns-checkpoint"); then
        status=$(printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])') || status=failed_unverified
        [[ "$status" != failed_rolled_back ]] || DNS_PREPARED=n
        printf '%s' "$output" | python3 -c 'import json,sys; [print("[!] DNS preparation: "+w,file=sys.stderr) for w in json.load(sys.stdin)["warnings"]]'
        return 1
    fi
    if ! output=$(python3 "$PANEL_STAGE/managed-security.py" --preflight); then
        printf '%s' "$output" | python3 -c 'import json,sys; [print("[!] Security readiness: "+w,file=sys.stderr) for w in json.load(sys.stdin)["warnings"]]'
        return 1
    fi
    verify_base_os
}

rollback_system_dns() {
    local output
    DNS_ROLLBACK_ATTEMPTED=y
    DNS_ROLLBACK_RESULT=failed_unverified
    output=$(python3 "$PANEL_STAGE/managed-security.py" --rollback-dns "$PANEL_STAGE/dns-checkpoint")
    DNS_ROLLBACK_RESULT=$(printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])') || return 1
    printf '%s' "$output" | python3 -c 'import json,sys; [print("[!] "+w,file=sys.stderr) for w in json.load(sys.stdin)["warnings"]]'
    if [[ "$DNS_ROLLBACK_RESULT" == failed_rolled_back ]]; then DNS_PREPARED=n; return 0; fi
    return 1
}

finish_initial_reboot() {
    [[ -e /var/run/reboot-required ]] || return 0
    if (( $1 != 0 )); then
        msg_warn 'Reboot required, but installation failed. Inspect the failure before rebooting manually: sudo reboot'
    else
        msg_warn 'Initial upgrade requires a manual reboot: sudo reboot. Post-reboot acceptance is pending.'
    fi
}

install_packages() {
    if [[ ${INSTALL} == *"y"* ]]; then
        local version
        version=$(grep -oP '(?<=VERSION_ID=")[0-9]+' /etc/os-release)
        [[ "$version" == "20" || "$version" == "22" ]] && echo "System: Ubuntu $version"

        apt_system -o APT::Update::Error-Mode=any update || { msg_err "APT list refresh failed (exit $?). Package changes are not rolled back."; return 1; }
        apt_system -y install curl wget jq bash sudo nginx-full certbot sqlite3 ufw netcat-openbsd mtr python3 python3-configobj python3-cryptography libcap2-bin openssl procps iproute2 tar gzip tzdata ca-certificates || return 1
        systemctl daemon-reload && systemctl enable --now nginx || return 1
    fi

    apt_system -y --no-install-recommends install ca-certificates || return 1
    local binary
    for binary in openssl sysctl ip ss tar gzip curl wget jq bash sudo nginx certbot sqlite3 ufw nc mtr python3 setcap; do
        command -v "$binary" >/dev/null || { msg_err "Required binary is missing: $binary"; return 1; }
    done
    python3 -c 'import configobj, cryptography' || { msg_err 'Required Python modules are unavailable: configobj, cryptography.'; return 1; }
}

# ─────────────────────────────────────────────────────────────────────────────
# SSL CERTIFICATES
# ─────────────────────────────────────────────────────────────────────────────
prepare_acme_webroot() {
    install -d -o root -g root -m 0755 /var/www/acme /var/www/acme/.well-known /var/www/acme/.well-known/acme-challenge
}

setup_acme_http() {
    prepare_acme_webroot || return 1
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled || return 1
    cat > /etc/nginx/sites-available/80.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${domain} ${reality_domain};
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
        try_files \$uri =404;
    }
    location / { return 301 https://\$host\$request_uri; }
}
EOF
    [[ $? == 0 ]] || return 1
    rm -f /etc/nginx/sites-enabled/default || return 1
    ln -sf /etc/nginx/sites-available/80.conf /etc/nginx/sites-enabled/80.conf || return 1
    nginx -t && systemctl enable --now nginx && systemctl reload nginx && systemctl is-active --quiet nginx
}

get_ssl_certs() {
    if [[ ${AUTODOMAIN} == *"y"* ]]; then
        local resolve_ok=true
        for d in "$domain" "$reality_domain"; do
            local a
            a=$(getent ahostsv4 "$d" 2>/dev/null | awk 'NR==1{print $1}')
            if [[ "$a" != "$IP4" ]]; then
                msg_err "Auto-domain $d does not resolve to $IP4. Fix DNS and retry."
                resolve_ok=false
            fi
        done
        [[ $resolve_ok == false ]] && return 1
    fi
    # Rebuild only our hook after runtime configuration; preserve all lineages.
    rm -f /etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx || return 1
    local d
    for d in "$domain" "$reality_domain"; do
        if [[ -e "/etc/letsencrypt/live/$d" || -e "/etc/letsencrypt/renewal/$d.conf" ]]; then
            [[ -d "/etc/letsencrypt/live/$d" && -f "/etc/letsencrypt/renewal/$d.conf" ]] || {
                msg_err "Incomplete certificate lineage: $d. Resolve it before rebuilding."; return 1;
            }
            check_certificate_identity "$d" || return 1
            if ! check_webroot_lineage "$d" 2>/dev/null; then
                certbot reconfigure --cert-name "$d" --webroot --webroot-path /var/www/acme \
                    --pre-hook '' --post-hook '' --non-interactive || return 1
            fi
        elif compgen -G "/etc/letsencrypt/live/$d-*" >/dev/null || compgen -G "/etc/letsencrypt/renewal/$d-*.conf" >/dev/null; then
            msg_err "Ambiguous certificate lineage for $d. Resolve it before rebuilding."; return 1
        else
            certbot certonly --webroot --webroot-path /var/www/acme --cert-name "$d" -d "$d" \
                --non-interactive --agree-tos --register-unsafely-without-email || return 1
        fi
        check_webroot_lineage "$d" || return 1
    done
    mkdir -p "/root/cert/${domain}" || return 1
    chmod 755 /root/cert "/root/cert/${domain}" || return 1
    ln -sf "/etc/letsencrypt/live/${domain}/fullchain.pem" "/root/cert/${domain}/fullchain.pem" || return 1
    ln -sf "/etc/letsencrypt/live/${domain}/privkey.pem" "/root/cert/${domain}/privkey.pem"
}
# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURE NGINX
# ─────────────────────────────────────────────────────────────────────────────
configure_nginx() {
    install -d -o root -g root -m 0755 /etc/nginx/snippets/x-ui-auto-optional || return 1
    mkdir -p /etc/nginx/stream-enabled /etc/nginx/snippets || return 1

    # nginx >= 1.25.1 deprecates "listen ... http2" in favor of "http2 on;";
    # older versions (Ubuntu 24.04) don't know the new directive
    local ngx_ver http2_listen="" http2_on=""
    ngx_ver=$(nginx -v 2>&1 | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' || echo 0)
    if [[ "$(printf '%s\n' 1.25.1 "$ngx_ver" | sort -V | head -1)" == "1.25.1" ]]; then
        http2_on="http2 on;"
    else
        http2_listen=" http2"
    fi

    # SNI-based stream: reality → 8443, domain → 7443
    cat > /etc/nginx/stream-enabled/stream.conf <<EOF
map \$ssl_preread_server_name \$sni_name {
    hostnames;
    ${reality_domain}    xray;
    ${domain}            www;
    default              xray;
}

upstream xray { server 127.0.0.1:8443; }
upstream www  { server 127.0.0.1:7443; }

server {
    proxy_protocol on;
    set_real_ip_from unix:;
    listen     443;
    listen     [::]:443;
    proxy_pass \$sni_name;
    ssl_preread on;
}
EOF
    [[ $? -eq 0 ]] || return 1

    grep -xqFR "stream { include /etc/nginx/stream-enabled/*.conf; }" /etc/nginx/* \
        || echo "stream { include /etc/nginx/stream-enabled/*.conf; }" >> /etc/nginx/nginx.conf
    grep -xqFR "load_module modules/ngx_stream_module.so;" /etc/nginx/* \
        || sed -i '1s/^/load_module \/usr\/lib\/nginx\/modules\/ngx_stream_module.so; /' /etc/nginx/nginx.conf
    grep -xqFR "worker_rlimit_nofile 16384;" /etc/nginx/* \
        || echo "worker_rlimit_nofile 16384;" >> /etc/nginx/nginx.conf
    sed -i "/worker_connections/c\worker_connections 4096;" /etc/nginx/nginx.conf

    # Shared proxy locations for xray inbounds (included by both vhosts)
    cat > /etc/nginx/snippets/includes.conf <<EOF
    #Subscription — prefix location covers all sub-paths (assets, JS, etc.)
    # Local error_page overrides inherited cover-page redirects; backend 5xx retain their status.
    location /${sub_path}/ {
        access_log off;
        error_log /dev/null crit;
        error_page 404 =404 @subscription_error;
        if (\$hack = 1) { return 404; }
        proxy_redirect off;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_pass https://127.0.0.1:${sub_port};
    }
    location = /${sub_path} {
        access_log off;
        error_log /dev/null crit;
        error_page 404 =404 @subscription_error;
        if (\$hack = 1) { return 404; }
        proxy_redirect off;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_pass https://127.0.0.1:${sub_port};
    }
    # Regex takes priority over prefix: catches subscription IDs (one-level deep)
    # and routes Clash/Mihomo clients to dynamic clash.yaml generator
    location ~ ^/${sub_path}/(?<clash_sub_id>[^/]+)$ {
        access_log off;
        error_log /dev/null crit;
        error_page 404 =404 @subscription_error;
        if (\$hack = 1) { return 404; }
        if (\$serve_clash_yaml = 1) { rewrite ^ /__clash_api?sub_id=\$clash_sub_id last; }
        proxy_redirect off;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_pass https://127.0.0.1:${sub_port};
    }
    location /assets  { proxy_pass https://127.0.0.1:${sub_port}; }
    location /assets/ { proxy_pass https://127.0.0.1:${sub_port}; }

    #Subscription (json)
    location /${json_path} {
        access_log off;
        error_log /dev/null crit;
        error_page 404 =404 @subscription_error;
        if (\$hack = 1) { return 404; }
        proxy_redirect off;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_pass https://127.0.0.1:${sub_port};
    }
    location /${json_path}/ {
        access_log off;
        error_log /dev/null crit;
        error_page 404 =404 @subscription_error;
        if (\$hack = 1) { return 404; }
        proxy_redirect off;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_pass https://127.0.0.1:${sub_port};
    }

    location @subscription_error {
        access_log off;
        error_log /dev/null crit;
        return 404;
    }

    #XHTTP
    location ^~ /${xhttp_path}/ {
        client_max_body_size  0;
        client_body_timeout   1h;
        grpc_read_timeout     1h;
        grpc_send_timeout     1h;
        grpc_set_header Connection        "";
        grpc_set_header Host              \$host;
        grpc_set_header X-Real-IP         \$remote_addr;
        grpc_set_header X-Forwarded-For   \$remote_addr;
        grpc_pass unix:/dev/shm/uds2023.sock;
    }

    # Installer-managed WS: exact path, fixed backend port
    location = /${ws_port}/${ws_path} {
        if (\$hack = 1) { return 404; }
        client_max_body_size 0;
        client_body_timeout 1d;
        proxy_read_timeout 1d;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_socket_keepalive on;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_pass http://127.0.0.1:${ws_port};
    }

    # Xray custom gRPC serviceName is the full method path (no /Tun suffix)
    location = /${trojan_port}/${trojan_path} {
        if (\$hack = 1) { return 404; }
        client_max_body_size 0;
        client_body_timeout 1d;
        grpc_read_timeout 1d;
        grpc_socket_keepalive on;
        grpc_set_header Host \$host;
        grpc_pass grpc://127.0.0.1:${trojan_port};
    }

    location / { try_files \$uri \$uri/ =404; }
EOF
    [[ $? -eq 0 ]] || return 1

    # HTTP-level maps. The clash maps are consumed by the shared includes.conf
    # snippet, which is included by BOTH vhosts, so they live in their own
    # always-loaded file — never inside a single vhost, or the other vhost's
    # include would reference an undefined var ("unknown ... variable").
    cat > /etc/nginx/sites-available/00-maps.conf <<EOF
# Detect Clash/Mihomo clients by User-Agent
map \$http_user_agent \$is_clash_ua {
    ~*(clash|clashx|clashn|mihomo|stash|surfboard)  1;
    default                                          0;
}
# Serve clash.yaml only when: Clash UA AND no ?provider=1 query param
# (proxy-provider refresh requests add ?provider=1 and must get the real sub)
map "\$is_clash_ua:\$arg_provider" \$serve_clash_yaml {
    "1:"    1;
    default 0;
}
EOF
    [[ $? -eq 0 ]] || return 1

    # Main domain vhost (TLS termination at 7443, proxy_protocol)
    cat > "/etc/nginx/sites-available/${domain}" <<EOF
# Rate limiting zones (http context)
limit_req_zone  \$binary_remote_addr zone=diag_api:10m  rate=6r/m;
limit_req_zone  \$binary_remote_addr zone=diag_page:10m rate=30r/m;
limit_conn_zone \$binary_remote_addr zone=per_ip:10m;

# Diagnostics access: cookie issued by the SSO bridge after panel login
map \$cookie_diag_key \$diag_auth {
    "${diag_token}" 1;
    default          0;
}

server {
    server_tokens off;
    server_name ${domain};
    listen 127.0.0.1:7443 ssl${http2_listen} proxy_protocol;
    ${http2_on}
    index index.html index.htm index.php;
    root /var/www/html/;
    real_ip_header proxy_protocol;
    set_real_ip_from 127.0.0.1;
    # This vhost listens on 7443 behind the SNI stream (public port 443). Without
    # this, nginx bakes :7443 into redirect Location headers (return/error_page),
    # so browsers get sent to an unreachable port. Keep redirects relative.
    absolute_redirect off;
    # Larger h2 preread window improves single-stream upload throughput
    http2_max_concurrent_streams 256;
    http2_body_preread_size 128k;
    client_body_buffer_size 512k;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!eNULL:!MD5:!DES:!RC4:!ADH:!SSLv3:!EXP:!PSK:!DSS;
    ssl_certificate     /etc/letsencrypt/live/${domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${domain}/privkey.pem;
    if (\$host !~* ^(.+\.)?${domain}\$)            { return 444; }
    if (\$scheme ~* https)                          { set \$safe 1; }
    if (\$ssl_server_name !~* ^(.+\.)?${domain}\$) { set \$safe "\${safe}0"; }
    if (\$safe = 10)                                { return 444; }
    if (\$request_uri ~ "(\"|'|\`|~|,|:|;|%|\\$|&&|\?\?|0x00|0X00|\||\\|\{|\}|\[|\]|<|>|\.\.\.|\.\.\/|\/\/\/)") { set \$hack 1; }
    error_page 400 401 402 403 500 501 502 503 504 =404 /404;
    proxy_intercept_errors on;

    location /${panel_path}/ {
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_pass https://127.0.0.1:${panel_port};
    }
    location /${panel_path} {
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_pass https://127.0.0.1:${panel_port};
    }

    # ── Diagnostics SSO bridge ───────────────────────────────────────────────
    # Lives under the panel path so the browser attaches the 3x-ui session
    # cookie (its Path is scoped to the panel base path). Valid panel session
    # → issue the diag cookie and redirect; otherwise → panel login page.
    # NOTE: auth_request runs in the access phase; a plain "return" here would
    # skip it (rewrite phase), hence the try_files → named-location hop.
    location = /${panel_path}/diag {
        auth_request /__diag_auth;
        # Named location (not "=302 /uri") so the deny path emits a real Location
        # header; an internal-redirect error_page returns a 302 with no Location.
        error_page 401 403 = @diag_login;
        try_files /__nonexistent @diag_sso_ok;
    }
    location @diag_login {
        return 302 /${panel_path}/;
    }
    location @diag_sso_ok {
        add_header Set-Cookie "diag_key=${diag_token}; Path=${diag_path}; Secure; HttpOnly; SameSite=Lax; Max-Age=604800";
        return 302 ${diag_path};
    }
    location = /__diag_auth {
        internal;
        proxy_pass https://127.0.0.1:${panel_port}/${panel_path}/panel/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        # 3x-ui answers AJAX requests with 401 instead of a login redirect
        proxy_set_header X-Requested-With XMLHttpRequest;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        # auth_request emits a raw 500 to the browser if the subrequest returns
        # anything other than 2xx / 401 / 403 (a login 302, or a 502 when the
        # panel's HTTPS cert is missing). Coerce every such status to a 401 deny
        # so the main location redirects to the panel login instead of 500ing.
        # 401/403 must be listed too, else the server-level "error_page 401 =404"
        # hijacks a genuine deny into a 404 (which auth_request then 500s on).
        proxy_intercept_errors on;
        error_page 300 301 302 303 304 305 307 308 400 401 402 403 404 405 500 501 502 503 504 =401 @diag_denied;
    }
    location @diag_denied { return 401; }

    # ── Network diagnostics page ─────────────────────────────────────────────
    # No diag cookie yet → bounce through the SSO bridge, which checks the panel
    # session and mints the cookie, so a bookmarked diag link "just works" once
    # you're logged into the panel. (Only the HTML page redirects; the API/asset
    # sub-locations below stay 404 without the cookie.)
    location ^~ ${diag_path} {
        if (\$diag_auth = 0) { return 302 /${panel_path}/diag; }
        limit_req  zone=diag_page burst=10 nodelay;
        limit_conn per_ip 5;
        alias /var/www/diagnostics/;
        index index.html;
        try_files \$uri \$uri/ /index.html;
        add_header Set-Cookie "diag_key=${diag_token}; Path=${diag_path}; Secure; HttpOnly; SameSite=Lax; Max-Age=604800" always;
        add_header Cache-Control "no-store" always;
        add_header X-Robots-Tag "noindex, nofollow" always;
    }

    # ── Diagnostics MTR API ──────────────────────────────────────────────────
    location ^~ ${diag_path}api/mtr {
        if (\$diag_auth = 0) { return 404; }
        limit_req  zone=diag_api burst=2 nodelay;
        limit_conn per_ip 2;
        proxy_pass         http://127.0.0.1:${mtr_backend_port}/api/mtr;
        proxy_http_version 1.1;
        proxy_set_header   X-Real-IP       \$remote_addr;
        proxy_set_header   X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
        # Let the backend's JSON error bodies through; the server-level
        # "proxy_intercept_errors on" would otherwise rewrite a 500 into an HTML
        # 404 and break the frontend's response.json() parse.
        proxy_intercept_errors off;
    }

    # ── LibreSpeed upload sink ───────────────────────────────────────────────
    # No limit_req: librespeed fires many short POSTs (parallel streams).
    # proxy_request_buffering off = client sees true network backpressure.
    location ^~ ${diag_path}api/st/up {
        if (\$diag_auth = 0) { return 404; }
        access_log              off;
        limit_conn              per_ip 8;
        proxy_pass              http://127.0.0.1:${mtr_backend_port}/api/st/up;
        proxy_http_version      1.1;
        proxy_set_header        X-Real-IP       \$remote_addr;
        proxy_request_buffering off;
        client_max_body_size    64m;
        proxy_read_timeout      60s;
        proxy_send_timeout      60s;
        add_header              Cache-Control "no-store" always;
    }

    # ── LibreSpeed ping endpoint (answered by nginx, no backend hop) ─────────
    location = ${diag_path}api/st/ping {
        if (\$diag_auth = 0) { return 404; }
        access_log off;
        limit_conn per_ip 8;
        add_header Cache-Control "no-store" always;
        default_type text/plain;
        return 200 "";
    }

    # ── LibreSpeed client IP ─────────────────────────────────────────────────
    location = ${diag_path}api/st/getip {
        if (\$diag_auth = 0) { return 404; }
        proxy_pass          http://127.0.0.1:${mtr_backend_port}/api/st/getip;
        proxy_http_version  1.1;
        proxy_set_header    X-Real-IP \$remote_addr;
        add_header          Cache-Control "no-store" always;
    }

    # ── Download test files ──────────────────────────────────────────────────
    location ^~ ${diag_path}testfiles/ {
        if (\$diag_auth = 0) { return 404; }
        alias      /var/www/diagnostics/testfiles/;
        access_log off;
        add_header Cache-Control "no-store, no-cache, must-revalidate" always;
        add_header Content-Disposition "attachment" always;
    }

    # ── Clash YAML generator — internal, proxied here by rewrite from sub_path ────
    location = /__clash_api {
        internal;
        access_log off;
        error_log /dev/null crit;
        error_page 404 =404 @subscription_error;
        proxy_pass          http://127.0.0.1:${mtr_backend_port}/api/clash\$is_args\$args;
        proxy_http_version  1.1;
        proxy_set_header    X-Real-IP \$remote_addr;
    }

    include /etc/nginx/snippets/x-ui-auto-optional/*.conf;
    include /etc/nginx/snippets/includes.conf;
}
EOF
    [[ $? -eq 0 ]] || return 1

    # Reality domain vhost (plain TLS at 9443, no proxy_protocol)
    cat > "/etc/nginx/sites-available/${reality_domain}" <<EOF
server {
    server_tokens off;
    server_name ${reality_domain};
    listen 127.0.0.1:9443 ssl${http2_listen};
    ${http2_on}
    index index.html index.htm index.php;
    root /var/www/html/;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!eNULL:!MD5:!DES:!RC4:!ADH:!SSLv3:!EXP:!PSK:!DSS;
    ssl_certificate     /etc/letsencrypt/live/${reality_domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${reality_domain}/privkey.pem;
    if (\$host !~* ^(.+\.)?${reality_domain}\$)            { return 444; }
    if (\$scheme ~* https)                                  { set \$safe 1; }
    if (\$ssl_server_name !~* ^(.+\.)?${reality_domain}\$) { set \$safe "\${safe}0"; }
    if (\$safe = 10)                                        { return 444; }
    if (\$request_uri ~ "(\"|'|\`|~|,|:|;|%|\\$|&&|\?\?|0x00|0X00|\||\\|\{|\}|\[|\]|<|>|\.\.\.|\.\.\/|\/\/\/)") { set \$hack 1; }
    error_page 400 401 402 403 500 501 502 503 504 =404 /404;
    proxy_intercept_errors on;

    include /etc/nginx/snippets/includes.conf;
}
EOF
    [[ $? -eq 0 ]] || return 1

    # Activate configs
    if [[ -f "/etc/nginx/sites-available/${domain}" ]]; then
        rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-available/default || return 1
        ln -sf "/etc/nginx/sites-available/00-maps.conf"       /etc/nginx/sites-enabled/ || return 1
        ln -sf "/etc/nginx/sites-available/${domain}"          /etc/nginx/sites-enabled/ || return 1
        ln -sf "/etc/nginx/sites-available/${reality_domain}"  /etc/nginx/sites-enabled/ || return 1
        ln -sf "/etc/nginx/sites-available/80.conf"            /etc/nginx/sites-enabled/ || return 1
    else
        msg_err "${domain} nginx config not found!" && exit 1
    fi

    nginx -t || { msg_err "nginx configuration test failed; see nginx error above."; return 1; }

    systemctl reload nginx || return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL PANEL (3x-ui)
# ─────────────────────────────────────────────────────────────────────────────
_arch() {
    case "$(uname -m)" in
        x86_64|x64|amd64)          echo 'amd64'  ;;
        i*86|x86)                  echo '386'    ;;
        armv8*|armv8|arm64|aarch64) echo 'arm64' ;;
        armv7*|armv7|arm)          echo 'armv7'  ;;
        armv6*|armv6)              echo 'armv6'  ;;
        armv5*|armv5)              echo 'armv5'  ;;
        s390x)                     echo 's390x'  ;;
        *) echo "Unsupported CPU architecture!" && exit 1 ;;
    esac
}

_panel_initial_config() {
    /usr/local/x-ui/x-ui setting -username "$config_username" -password "$config_password" \
        -port "$panel_port" -webBasePath "$panel_path" || return 1
    /usr/local/x-ui/x-ui migrate || return 1
    # No service is started until the managed backend bind is persisted.
    sqlite3 "$XUIDB" "BEGIN; DELETE FROM settings WHERE key='webListen';
        INSERT INTO settings(key,value) VALUES('webListen','127.0.0.1'); COMMIT;" || return 1
    # The upstream CLI can report individual setting errors with exit code 0.
    local initialized
    initialized=$(sqlite3 "$XUIDB" "SELECT
        (SELECT username FROM users ORDER BY id LIMIT 1),
        COALESCE((SELECT value FROM settings WHERE key='webListen'), ''),
        (SELECT value FROM settings WHERE key='webPort'),
        (SELECT value FROM settings WHERE key='webBasePath');") || return 1
    [[ "$initialized" == "$config_username|127.0.0.1|$panel_port|/$panel_path/" ]] || {
        msg_err "3X-UI initial settings were not saved correctly."
        return 1
    }
}

# Single release baseline for the installer and real integration/Canary tooling.
# Pinned archive integrity is not functional acceptance on every architecture.
verified_panel_release() {
    cat <<'VERIFIED_RELEASE_JSON'
{
  "version": "v3.10.0",
  "xray": "26.10.10",
  "archives": {
    "386": "514f7376806ed30b3b8166f36256b47e6101994ccb2e3eebd07f408ce542903b",
    "amd64": "b647a3e7d6695600bdd18cbfd34959991be09d4b1ad1e05efa790c0cf69ca40d",
    "arm64": "a0bb393989b96833c84460dff21c968a6263f4e09b7ceff93e0f92975aeadc16",
    "armv5": "e6787c78c68260320016739a87f35513acf344ee11b23d48a476ef834c15ede6",
    "armv6": "2dd4d186f5cb22d4afeceaf7bfdf255a825afdfbb4f3e284128dfac2011c612d",
    "armv7": "f6d331215584c788f77943d7a5a9301d22a64d41f0bf8fac74956a550839a2ab",
    "s390x": "769f11d45eb567a1f2f669b12bfeed445e07a038686b9f965ff2121306467203"
  },
  "integration_architectures": [
    "amd64"
  ]
}
VERIFIED_RELEASE_JSON
}

bootstrap_panel_dependencies() {
    local binary missing=0
    for binary in curl python3 tar gzip sha256sum ip ss; do
        command -v "$binary" >/dev/null 2>&1 || missing=1
    done
    [[ -s /etc/ssl/certs/ca-certificates.crt ]] || missing=1
    if (( missing )); then
        apt_system -o APT::Update::Error-Mode=any update || { msg_err "APT list refresh failed (exit $?). Package changes are not rolled back."; return 1; }
        apt_system -y --no-install-recommends install \
            curl ca-certificates python3 tar gzip iproute2 || return 1
    fi
    for binary in curl python3 tar gzip sha256sum ip ss; do
        command -v "$binary" >/dev/null 2>&1 || { msg_err "Release preflight requires $binary."; return 1; }
    done
    [[ -s /etc/ssl/certs/ca-certificates.crt ]]
}

release_panel_preflight() {
    if [[ "${DNS_PREPARED:-n}" == y && "${DNS_FINALIZED:-n}" != y && "${DNS_ROLLBACK_ATTEMPTED:-n}" != y ]]; then
        rollback_system_dns || msg_err 'Original DNS rollback could not be verified.'
    fi
    if [[ "${DNS_ROLLBACK_RESULT:-}" == failed_unverified ]]; then
        msg_warn "Private stage retained for DNS rollback inspection: $PANEL_STAGE"
        return 1
    fi
    [[ -z "${PANEL_STAGE:-}" ]] || rm -rf -- "$PANEL_STAGE"
}

_validate_panel_archive() {
    python3 - "$1" "$2" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1], 'r:gz') as archive:
    members = archive.getmembers()
    seen = set()
    for member in members:
        path = PurePosixPath(member.name)
        if (path.is_absolute() or '..' in path.parts or not path.parts or
                path.parts[0] != 'x-ui' or member.name in seen or
                not (member.isfile() or member.isdir())):
            raise ValueError('Unsafe 3X-UI archive member: '+member.name)
        seen.add(member.name)
    for name in ('x-ui/x-ui', 'x-ui/x-ui.sh', 'x-ui/x-ui.service.debian',
                 'x-ui/bin/xray-linux-'+sys.argv[2]):
        entry = archive.getmember(name)
        if not entry.isfile() or entry.size == 0:
            raise ValueError('Missing regular release component: '+name)
PY
}

# Verify official sidecar and the independently pinned baseline/API digest.
_download_panel_archive() {
    local url="$1" archive="$2" checksum="${2}.sha256" pinned="${3:-}" expected actual
    if ! curl -fLsS --retry 3 --connect-timeout 15 --max-time 300 "$url" -o "$archive" ||
       ! curl -fLsS --retry 3 --connect-timeout 15 --max-time 60 "${url}.sha256" -o "$checksum"; then
        rm -f "$archive" "$checksum"
        msg_err "Failed to download the 3X-UI release or checksum."
        return 1
    fi
    expected=$(python3 - "$checksum" "${url##*/}" <<'PY'
import re, sys
from pathlib import Path
match = re.fullmatch(r'([0-9a-f]{64})\s+\*?'+re.escape(sys.argv[2])+r'\s*',
                     Path(sys.argv[1]).read_text())
if not match:
    raise ValueError('Invalid official release checksum format')
print(match[1])
PY
    ) || { rm -f "$archive" "$checksum"; return 1; }
    actual=$(sha256sum "$archive") || {
        rm -f "$archive" "$checksum"
        return 1
    }
    actual="${actual%% *}"
    rm -f "$checksum"
    if [[ "$expected" != "$actual" || ( -n "$pinned" && "$pinned" != "$actual" ) ]]; then
        rm -f "$archive"
        msg_err "3X-UI release checksum verification failed."
        return 1
    fi
}

preflight_panel_release() {
    bootstrap_panel_dependencies || { msg_err "Release preflight dependency setup failed."; return 1; }
    PANEL_STAGE=$(mktemp -d /tmp/x-ui-release.XXXXXX) || return 1
    trap release_panel_preflight EXIT
    chmod 700 "$PANEL_STAGE" || return 1
    verified_panel_release > "$PANEL_STAGE/baseline.json" || return 1
    PANEL_ARCH=$(_arch) || return 1
    local baseline pinned asset
    baseline=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$PANEL_STAGE/baseline.json") || return 1
    PANEL_TAG="${PANEL_VERSION:-$baseline}"
    PANEL_TAG="v${PANEL_TAG#v}"
    _validate_panel_version "$PANEL_TAG" || return 1
    asset="x-ui-linux-${PANEL_ARCH}.tar.gz"
    if [[ "$PANEL_TAG" == "$baseline" ]]; then
        pinned=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["archives"][sys.argv[2]])' \
            "$PANEL_STAGE/baseline.json" "$PANEL_ARCH") || return 1
    else
        msg_warn "Explicit 3X-UI $PANEL_TAG selection: not the verified baseline; compatibility and full installer acceptance are not assured."
        curl -fLsS --retry 3 --connect-timeout 15 --max-time 60 \
            "https://api.github.com/repos/MHSanaei/3x-ui/releases/tags/${PANEL_TAG}" \
            -o "$PANEL_STAGE/release.json" || { msg_err "Stable 3X-UI release $PANEL_TAG is unavailable."; return 1; }
        pinned=$(python3 - "$PANEL_STAGE/release.json" "$PANEL_TAG" "$asset" <<'PY'
import json, re, sys
release = json.load(open(sys.argv[1]))
if (release.get('tag_name') != sys.argv[2] or release.get('draft') is not False or
        release.get('prerelease') is not False):
    raise ValueError('Not an official stable release')
assets = release['assets']
for name in (sys.argv[3], sys.argv[3]+'.sha256'):
    matches = [asset for asset in assets if asset.get('name') == name]
    if len(matches) != 1:
        raise ValueError('Missing/ambiguous release asset: '+name)
digest = next(asset for asset in assets if asset['name'] == sys.argv[3]).get('digest')
if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
    raise ValueError('Release asset lacks an official SHA-256 digest')
print(digest[7:])
PY
        ) || { msg_err "Unsupported or unverifiable 3X-UI release $PANEL_TAG."; return 1; }
    fi
    PANEL_ARCHIVE="$PANEL_STAGE/$asset"
    _download_panel_archive \
        "https://github.com/MHSanaei/3x-ui/releases/download/${PANEL_TAG}/$asset" \
        "$PANEL_ARCHIVE" "$pinned" || return 1
    _validate_panel_archive "$PANEL_ARCHIVE" "$PANEL_ARCH" || { msg_err "Invalid 3X-UI release archive."; return 1; }
    chmod 400 "$PANEL_ARCHIVE" || return 1
    msg_ok "3X-UI $PANEL_TAG archive verified before deployment cleanup."
}

install_panel() {
    local tag_version="${PANEL_TAG:?Release preflight is required}" archive="${PANEL_ARCHIVE:?Release preflight is required}"
    [[ -f "$archive" ]] || { msg_err "Verified release archive is unavailable."; return 1; }
    cd /usr/local/ || return 1
    echo "Installing 3X-UI ${tag_version} ..."

    [[ -d /usr/local/x-ui/ ]] && systemctl stop x-ui 2>/dev/null; rm -rf /usr/local/x-ui/
    if ! tar zxvf "$archive" -C /usr/local; then
        rm -f "$archive"
        return 1
    fi
    rm -f "$archive"

    cd x-ui || return 1
    chmod +x x-ui x-ui.sh

    local xray_name="xray-linux-$(_arch)"
    case "$(_arch)" in
        armv5|armv6|armv7)
            mv "bin/$xray_name" bin/xray-linux-arm32 || return 1
            xray_name=xray-linux-arm32 ;;
    esac
    chmod +x "bin/$xray_name" || return 1
    [[ -f "bin/$xray_name" && -x "bin/$xray_name" ]] || return 1

    install -m 0755 x-ui.sh /usr/bin/x-ui || return 1

    _panel_initial_config || return 1

    cp -f x-ui.service.debian /etc/systemd/system/x-ui.service || return 1
    if [[ "$tag_version" == v3.10.0 ]]; then
        # Supported OSes have systemd >=239. Keep upstream's seccomp policy in
        # the already-owned unit so uninstall and Backup v3 need no new paths.
        sed -i '/^\[Service\]$/a SystemCallFilter=@system-service\nSystemCallErrorNumber=EPERM' /etc/systemd/system/x-ui.service || return 1
    fi
    systemctl daemon-reload || return 1

    msg_ok "3X-UI ${tag_version} installed."
}

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURE X-UI DATABASE
# ─────────────────────────────────────────────────────────────────────────────
country_flag() {
    local response flag
    response=$(curl -fsS --connect-timeout 5 --max-time 10 https://ipwho.is/ 2>/dev/null) || response=''
    flag=$(printf '%s' "$response" | python3 -c '
import json, re, sys
flag = "🌐"
try:
    data = json.load(sys.stdin)
    code = data.get("country_code") if data.get("success") is True else None
    if isinstance(code, str) and re.fullmatch(r"[A-Z]{2}", code):
        flag = "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)
except Exception:
    pass
sys.stdout.buffer.write(flag.encode("utf-8"))
' 2>/dev/null) || flag='🌐'
    printf '%s' "${flag:-🌐}"
}

configure_xui_db() {
    if [[ ! -f $XUIDB ]]; then
        msg_err "x-ui.db not found — panel may not be installed." && exit 1
    fi

    x-ui stop 2>/dev/null || true

    local output private_key public_key trojan_pass xray_bin
    # install_panel renames armv5/6/7 binaries to xray-linux-arm32
    xray_bin="/usr/local/x-ui/bin/xray-linux-$(_arch)"
    [[ -f "$xray_bin" ]] || xray_bin="/usr/local/x-ui/bin/xray-linux-arm32"
    [[ -x "$xray_bin" ]] || { msg_err "Xray executable unavailable."; return 1; }
    output=$("$xray_bin" x25519) || return 1
    private_key=$(echo "$output" | grep "^PrivateKey:" | awk '{print $2}')
    public_key=$(echo "$output"  | grep "^Password"   | awk '{print $3}')
    trojan_pass=$(gen_random_string 10)
    # Per-host group_id: without it the panel cannot edit or delete the host.
    # The column only exists since 3x-ui v3.5.0 (pinnable via -version), so
    # probe the migrated schema and skip it on older releases.
    local gid_col="" gid_reality="" gid_ws="" gid_xhttp="" gid_trojan="" gid_hysteria=""
    if sqlite3 "$XUIDB" "PRAGMA table_info(hosts);" | grep -qw "group_id"; then
        gid_col='"group_id",'
        gid_reality="'$(gen_group_id)',"
        gid_ws="'$(gen_group_id)',"
        gid_xhttp="'$(gen_group_id)',"
        gid_trojan="'$(gen_group_id)',"
        gid_hysteria="'$(gen_group_id)',"
    fi
    emoji_flag=$(country_flag)

    local sub_uri="https://${domain}/${sub_path}/"
    local json_uri="https://${domain}/${json_path}/"

    # Prepare short IDs for REALITY
    local shor
    shor=($(openssl rand -hex 8) $(openssl rand -hex 8) $(openssl rand -hex 8) $(openssl rand -hex 8) \
           $(openssl rand -hex 8) $(openssl rand -hex 8) $(openssl rand -hex 8) $(openssl rand -hex 8))

    sqlite3 $XUIDB <<EOF
DELETE FROM "settings" WHERE "key" IN ("webCertFile","webKeyFile","webListen","subListen","subJsonEnable","subJsonPath","subJsonURI");

INSERT INTO "settings" ("key","value") VALUES ("subPort",             '${sub_port}');
UPDATE "settings" SET "value" = '/${sub_path}/' WHERE "key" = 'subPath';
INSERT INTO "settings" ("key","value") VALUES ("subURI",              '${sub_uri}');
INSERT INTO "settings" ("key","value") VALUES ("subJsonEnable",       'true');
INSERT INTO "settings" ("key","value") VALUES ("subJsonPath",         '/${json_path}/');
INSERT INTO "settings" ("key","value") VALUES ("subJsonURI",          '${json_uri}');
INSERT INTO "settings" ("key","value") VALUES ("subClashEnable",      'false');
INSERT INTO "settings" ("key","value") VALUES ("subEnableRouting",    'false');
INSERT INTO "settings" ("key","value") VALUES ("subEnable",           'true');
INSERT INTO "settings" ("key","value") VALUES ("webListen",           '127.0.0.1');
INSERT INTO "settings" ("key","value") VALUES ("subListen",           '127.0.0.1');
INSERT INTO "settings" ("key","value") VALUES ("webDomain",           '');
INSERT INTO "settings" ("key","value") VALUES ("webCertFile",         '');
INSERT INTO "settings" ("key","value") VALUES ("webKeyFile",          '');
INSERT INTO "settings" ("key","value") VALUES ("sessionMaxAge",       '60');
INSERT INTO "settings" ("key","value") VALUES ("pageSize",            '50');
INSERT INTO "settings" ("key","value") VALUES ("expireDiff",          '0');
INSERT INTO "settings" ("key","value") VALUES ("trafficDiff",         '0');
INSERT INTO "settings" ("key","value") VALUES ("remarkModel",         '-ieo');
INSERT INTO "settings" ("key","value") VALUES ("tgBotEnable",         'false');
INSERT INTO "settings" ("key","value") VALUES ("tgBotToken",          '');
INSERT INTO "settings" ("key","value") VALUES ("tgBotProxy",          '');
INSERT INTO "settings" ("key","value") VALUES ("tgBotAPIServer",      '');
INSERT INTO "settings" ("key","value") VALUES ("tgBotChatId",         '');
INSERT INTO "settings" ("key","value") VALUES ("tgRunTime",           '@daily');
INSERT INTO "settings" ("key","value") VALUES ("tgBotBackup",         'false');
INSERT INTO "settings" ("key","value") VALUES ("tgBotLoginNotify",    'true');
INSERT INTO "settings" ("key","value") VALUES ("tgCpu",               '80');
INSERT INTO "settings" ("key","value") VALUES ("tgLang",              'en-US');
INSERT INTO "settings" ("key","value") VALUES ("timeLocation",        'Europe/Moscow');
INSERT INTO "settings" ("key","value") VALUES ("secretEnable",        'false');
INSERT INTO "settings" ("key","value") VALUES ("subDomain",           '');
INSERT INTO "settings" ("key","value") VALUES ("subCertFile",         '');
INSERT INTO "settings" ("key","value") VALUES ("subKeyFile",          '');
INSERT INTO "settings" ("key","value") VALUES ("subUpdates",          '12');
INSERT INTO "settings" ("key","value") VALUES ("subEncrypt",          'true');
INSERT INTO "settings" ("key","value") VALUES ("subShowInfo",         'true');
INSERT INTO "settings" ("key","value") VALUES ("subJsonFragment",     '');
INSERT INTO "settings" ("key","value") VALUES ("subJsonNoises",       '');
INSERT INTO "settings" ("key","value") VALUES ("subJsonMux",          '');
INSERT INTO "settings" ("key","value") VALUES ("subJsonRules",        '');
INSERT INTO "settings" ("key","value") VALUES ("datepicker",          'gregorian');

INSERT INTO "inbounds"
    ("user_id","up","down","total","remark","enable","expiry_time","listen","port","protocol","settings","stream_settings","tag","sniffing")
VALUES (
    '1','0','0','0','${emoji_flag} reality','1','0','127.0.0.1','8443','vless',
    '{
  "clients": [],
  "decryption": "none",
  "encryption": "none",
  "fallbacks": []
}',
    '{
  "network": "tcp",
  "security": "reality",
  "realitySettings": {
    "show": false,
    "xver": 0,
    "target": "127.0.0.1:9443",
    "serverNames": ["${reality_domain}"],
    "privateKey": "${private_key}",
    "minClient": "",
    "maxClient": "",
    "maxTimediff": 0,
    "shortIds": [
      "${shor[0]}","${shor[1]}","${shor[2]}","${shor[3]}",
      "${shor[4]}","${shor[5]}","${shor[6]}","${shor[7]}"
    ],
    "settings": {
      "publicKey": "${public_key}",
      "fingerprint": "firefox",
      "serverName": "",
      "spiderX": "/"
    }
  },
  "tcpSettings": {
    "acceptProxyProtocol": true,
    "header": {"type":"none"}
  }
}',
    'inbound-8443',
    '{"enabled":true,"destOverride":["http","tls","quic","fakedns"],"metadataOnly":false,"routeOnly":false}'
);

INSERT INTO "inbounds"
    ("user_id","up","down","total","remark","enable","expiry_time","listen","port","protocol","settings","stream_settings","tag","sniffing")
VALUES (
    '1','0','0','0','${emoji_flag} ws','0','0','127.0.0.1','${ws_port}','vless',
    '{
  "clients": [],
  "decryption": "none",
  "encryption": "none",
  "fallbacks": []
}',
    '{
  "network": "ws",
  "security": "none",
  "wsSettings": {
    "acceptProxyProtocol": false,
    "path": "/${ws_port}/${ws_path}",
    "host": "${domain}",
    "headers": {}
  }
}',
    'inbound-${ws_port}',
    '{"enabled":true,"destOverride":["http","tls","quic","fakedns"],"metadataOnly":false,"routeOnly":false}'
);

INSERT INTO "inbounds"
    ("user_id","up","down","total","remark","enable","expiry_time","listen","port","protocol","settings","stream_settings","tag","sniffing")
VALUES (
    '1','0','0','0','${emoji_flag} xhttp','1','0','/dev/shm/uds2023.sock,0666','0','vless',
    '{
  "clients": [],
  "decryption": "none",
  "encryption": "none",
  "fallbacks": []
}',
    '{
  "network": "xhttp",
  "security": "none",
  "xhttpSettings": {
    "path": "/${xhttp_path}",
    "mode": "stream-up"
  },
  "sockopt": {
    "trustedXForwardedFor": ["X-Forwarded-For"]
  }
}',
    'inbound-/dev/shm/uds2023.sock,0666:0|',
    '{"enabled":true,"destOverride":["http","tls","quic","fakedns"],"metadataOnly":false,"routeOnly":false}'
);

INSERT INTO "inbounds"
    ("user_id","up","down","total","remark","enable","expiry_time","listen","port","protocol","settings","stream_settings","tag","sniffing")
VALUES (
    '1','0','0','0','${emoji_flag} trojan-grpc','0','0','127.0.0.1','${trojan_port}','trojan',
    '{
  "clients": [],
  "fallbacks": []
}',
    '{
  "network": "grpc",
  "security": "none",
  "grpcSettings": {
    "serviceName": "/${trojan_port}/${trojan_path}|${trojan_path}-multi",
    "authority": "${domain}",
    "multiMode": false
  }
}',
    'inbound-${trojan_port}',
    '{"enabled":true,"destOverride":["http","tls","quic","fakedns"],"metadataOnly":false,"routeOnly":false}'
);

INSERT INTO "inbounds"
    ("user_id","up","down","total","remark","enable","expiry_time","listen","port","protocol","settings","stream_settings","tag","sniffing")
VALUES (
    '1','0','0','0','${emoji_flag} hysteria2','1','0','','443','hysteria',
    '{"version":2,"clients":[]}',
    '{
  "network": "hysteria",
  "security": "tls",
  "hysteriaSettings": {
    "version": 2,
    "udpIdleTimeout": 60
  },
  "tlsSettings": {
    "serverName": "${domain}",
    "alpn": ["h3"],
    "certificates": [{
      "certificateFile": "/root/cert/${domain}/fullchain.pem",
      "keyFile": "/root/cert/${domain}/privkey.pem",
      "ocspStapling": 0,
      "oneTimeLoading": false,
      "usage": "encipherment",
      "buildChain": false
    }]
  }
}',
    'inbound-443-udp',
    '{"enabled":true,"destOverride":["http","tls","quic","fakedns"],"metadataOnly":false,"routeOnly":false}'
);

-- Hosts supersede the legacy externalProxy arrays: one host per inbound,
-- rendered as the share-link endpoint at subscription time.
-- REALITY and Hysteria keep their own TLS params (security=same);
-- WS/XHTTP/Trojan front through nginx at :443 with TLS.
INSERT INTO "hosts" ("inbound_id",${gid_col}"sort_order","remark","address","port","security","fingerprint","alpn")
VALUES
    ((SELECT id FROM inbounds WHERE tag='inbound-8443'),           ${gid_reality} 0, 'reality', '${domain}', 443, 'same', '',        '[]'),
    ((SELECT id FROM inbounds WHERE tag='inbound-${ws_port}'),     ${gid_ws}      0, 'ws',      '${domain}', 443, 'tls',  'firefox', '["http/1.1"]'),
    ((SELECT id FROM inbounds WHERE tag='inbound-/dev/shm/uds2023.sock,0666:0|'), ${gid_xhttp} 0, 'xhttp', '${domain}', 443, 'tls', 'firefox', '["h2","http/1.1"]'),
    ((SELECT id FROM inbounds WHERE tag='inbound-${trojan_port}'), ${gid_trojan}  0, 'trojan',  '${domain}', 443, 'tls',  'firefox', '["h2","http/1.1"]'),
    ((SELECT id FROM inbounds WHERE tag='inbound-443-udp'),        ${gid_hysteria} 0, 'hysteria2', '${domain}', 443, 'same', '', '[]');
EOF
    [[ $? -eq 0 ]] || return 1

    /usr/local/x-ui/x-ui setting \
        -username  "${config_username}" \
        -password  "${config_password}" \
        -port      "${panel_port}"      \
        -webBasePath "${panel_path}" || return 1

    # v3.9.0 updateCert sets BOTH web and subscription TLS settings before first start.
    /usr/local/x-ui/x-ui cert \
        -webCert    "/root/cert/${domain}/fullchain.pem" \
        -webCertKey "/root/cert/${domain}/privkey.pem" || return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL FAKE SITE
# ─────────────────────────────────────────────────────────────────────────────
install_clash_sub() {
    local clash_dir="/var/www/subpage"
    mkdir -p "${clash_dir}" || return 1
    if curl -fsSL "${GITHUB_RAW}/assets/clash/clash.yaml" -o "${clash_dir}/clash.yaml.tpl"; then
        # Substitute domain and sub_path; leave ${EMAIL} for mtr-backend to fill per-request
        sed -i "s|\${DOMAIN}|${domain}|g"     "${clash_dir}/clash.yaml.tpl" || return 1
        sed -i "s|\${SUB_PATH}|${sub_path}|g" "${clash_dir}/clash.yaml.tpl" || return 1
        chown -R www-data:www-data "${clash_dir}" 2>/dev/null || return 1
        chmod 644 "${clash_dir}/clash.yaml.tpl" || return 1
        msg_ok "Clash subscription template installed."
    else
        msg_err "Failed to download clash.yaml from GitHub."
        return 1
    fi
}

install_fake_site() {
    local idx=$(( (RANDOM % FAKE_SITE_COUNT) + 1 ))
    local site_id
    site_id=$(printf "site-%02d" "$idx")
    local url="${GITHUB_RAW}/assets/fake-sites/${site_id}/index.html"

    mkdir -p /var/www/html || return 1
    if curl -fsSL "$url" -o /var/www/html/index.html; then
        chown -R www-data:www-data /var/www/html 2>/dev/null || return 1
        chmod 644 /var/www/html/index.html || return 1
        msg_ok "Fake cover site '${site_id}' installed."
    else
        msg_err "Failed to download fake site ${site_id} from GitHub."
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL NETWORK DIAGNOSTICS PAGE
# ─────────────────────────────────────────────────────────────────────────────
install_diagnostics() {
    local diag_webroot="/var/www/diagnostics"
    local backend_script="/usr/local/lib/3x-ui-pro/mtr-backend.py"

    # Diagnostics HTML page
    mkdir -p "${diag_webroot}" || return 1
    curl -fsSL "${GITHUB_RAW}/assets/diagnostics/index.html" -o "${diag_webroot}/index.html" || return 1
    sed -i \
        -e "s|__DIAG_PATH__|${diag_path}|g" \
        -e "s|__SERVER_DOMAIN__|${domain}|g" \
        -e "s|__SERVER_IP__|${IP4}|g" \
        "${diag_webroot}/index.html" || return 1

    # LibreSpeed engine (speed test frontend, LGPL — github.com/librespeed/speedtest)
    curl -fsSL "${GITHUB_RAW}/assets/diagnostics/librespeed/speedtest.js" \
        -o "${diag_webroot}/speedtest.js" || return 1
    curl -fsSL "${GITHUB_RAW}/assets/diagnostics/librespeed/speedtest_worker.js" \
        -o "${diag_webroot}/speedtest_worker.js" || return 1

    # Test download files
    local testfiles="${diag_webroot}/testfiles"
    mkdir -p "${testfiles}" || return 1
    [[ -f "${testfiles}/test-15k.bin"  ]] || dd if=/dev/zero bs=1024    count=15   of="${testfiles}/test-15k.bin"  status=none || return 1
    [[ -f "${testfiles}/test-17k.bin"  ]] || dd if=/dev/zero bs=1024    count=17   of="${testfiles}/test-17k.bin"  status=none || return 1
    [[ -f "${testfiles}/test-100m.bin" ]] || dd if=/dev/zero bs=1048576 count=100  of="${testfiles}/test-100m.bin" status=none || return 1
    [[ -f "${testfiles}/test-1g.bin"   ]] || dd if=/dev/zero bs=1048576 count=1024 of="${testfiles}/test-1g.bin"   status=none || return 1
    rm -f "${testfiles}/test-512m.bin" || return 1   # only used by the old single-stream speed test
    chown -R www-data:www-data "${diag_webroot}" 2>/dev/null || return 1

    # MTR backend Python script
    mkdir -p "$(dirname "${backend_script}")" || return 1
    curl -fsSL "${GITHUB_RAW}/assets/diagnostics/mtr-backend.py" -o "${backend_script}" || return 1
    chmod 755 "${backend_script}" || return 1

    # Grant mtr raw socket capability (runs as restricted user, no root needed)
    # mtr-packet is the helper that actually opens the raw socket
    command -v setcap &>/dev/null && setcap cap_net_raw+ep "$(command -v mtr)"        2>/dev/null || true
    command -v setcap &>/dev/null && setcap cap_net_raw+ep "$(command -v mtr-packet)" 2>/dev/null || true

    # Dedicated system user for mtr-backend
    id mtr-backend &>/dev/null || \
        useradd --system --no-create-home --shell /usr/sbin/nologin mtr-backend || return 1

    # Systemd service for mtr-backend
    cat > /etc/systemd/system/mtr-backend.service <<EOF
[Unit]
Description=3x-ui Auto Nginx MTR diagnostics backend
After=network.target

[Service]
Type=simple
User=mtr-backend
Group=mtr-backend
ExecStart=/usr/bin/python3 ${backend_script} --port ${mtr_backend_port}
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_NETLINK
RestrictNamespaces=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
RemoveIPC=yes
# mtr-packet opens raw ICMP sockets. NoNewPrivileges=yes strips the file
# capability off the mtr binary, so grant CAP_NET_RAW the systemd-native way
# (ambient caps survive NoNewPrivileges). Empty here = mtr fails with
# "Failure to open IPv4 sockets: Permission denied".
AmbientCapabilities=CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_RAW
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mtr-backend

[Install]
WantedBy=multi-user.target
EOF
    [[ $? -eq 0 ]] || return 1

    systemctl daemon-reload || return 1
    systemctl enable mtr-backend || return 1
    systemctl restart mtr-backend || return 1

    msg_ok "Network diagnostics installed at https://${domain}/${panel_path}/diag (panel login required)"
}

# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM TUNING (BBR + kernel params)
# ─────────────────────────────────────────────────────────────────────────────
tune_system() {
    local managed_file=/etc/sysctl.d/99-3x-ui-pro.conf
    local params=(
        "net.core.default_qdisc=fq"
        "net.ipv4.tcp_congestion_control=bbr"
        "fs.file-max=2097152"
        "net.ipv4.tcp_timestamps=1"
        "net.ipv4.tcp_sack=1"
        "net.ipv4.tcp_window_scaling=1"
        "net.core.rmem_max=16777216"
        "net.core.wmem_max=16777216"
        "net.ipv4.tcp_rmem=4096 87380 16777216"
        "net.ipv4.tcp_wmem=4096 65536 16777216"
    )
    mkdir -p /etc/sysctl.d &&
        printf '%s\n' "${params[@]}" > "$managed_file" &&
        chown root:root "$managed_file" &&
        chmod 0644 "$managed_file" &&
        sysctl -p "$managed_file"
}

install_backup_tool() {
    local temporary
    mkdir -p /usr/local/bin || return 1
    temporary=$(mktemp /usr/local/bin/.x-ui-backup.XXXXXX) || return 1
    if ! curl -fsSL "${GITHUB_RAW}/assets/backup/x-ui-backup.sh" -o "$temporary" ||
       ! bash -n "$temporary" || [[ ! -s "$temporary" ]]; then
        rm -f "$temporary"
        msg_err "Failed to download a valid backup tool."
        return 1
    fi
    if ! chown root:root "$temporary" || ! chmod 0755 "$temporary" ||
       ! mv -fT "$temporary" /usr/local/bin/x-ui-backup; then
        rm -f "$temporary"
        msg_err "Failed to install the backup tool."
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# CERTIFICATE RENEWAL
# ─────────────────────────────────────────────────────────────────────────────

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

check_certificate_identity() {
    python3 - "$1" <<'PYIDENTITY'
import sys
from pathlib import Path
from cryptography import x509
try:
    domain = sys.argv[1]
    live = Path('/etc/letsencrypt/live') / domain
    cert = x509.load_pem_x509_certificate((live / 'fullchain.pem').read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    if set(names) != {domain} or not (live / 'privkey.pem').is_file():
        raise ValueError('expected a separate exact-domain certificate and key')
except (OSError, ValueError, x509.ExtensionNotFound) as exc:
    print('[FAIL] Existing certificate identity mismatch: ' + str(exc), file=sys.stderr)
    sys.exit(1)
PYIDENTITY
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

setup_certificate_renewal() {
    local hook=/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx
    remove_legacy_certbot_cron || return 1
    install -d -o root -g root -m 0755 /etc/letsencrypt/renewal-hooks/deploy || return 1
    render_certificate_hook "$domain" "$reality_domain" > "$hook" || return 1
    chown root:root "$hook" && chmod 0755 "$hook" && bash -n "$hook" || return 1
    systemctl enable --now certbot.timer || return 1
    check_certificate_renewal "$domain" "$reality_domain"
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

check_installation() {
    local service
    [[ "$(sqlite3 "$XUIDB" "SELECT value FROM settings WHERE key='webListen';")" == 127.0.0.1 ]] || {
        msg_err "Panel backend must bind only to 127.0.0.1."; return 1
    }
    for service in x-ui nginx mtr-backend; do
        systemctl is-active --quiet "$service" || { msg_err "$service is not active."; return 1; }
    done
    check_certificate_renewal "$domain" "$reality_domain" || return 1
    nginx -t || return 1
    check_xray_runtime
}

# ─────────────────────────────────────────────────────────────────────────────
# FIREWALL
# ─────────────────────────────────────────────────────────────────────────────
setup_firewall() {
    local status port socket_state socket_listen='' ssh_config='' detected
    local -a ssh_ports=()
    status=$(LC_ALL=C ufw status) || return 1
    case "$status" in
        "Status: active"*|"Status: inactive"*) ;;
        *) msg_err "Cannot determine UFW status." >&2; return 1 ;;
    esac
    for port in 80/tcp 443/tcp 443/udp; do
        ufw allow "$port" || return 1
    done
    [[ "$status" == "Status: active"* ]] && return 0

    socket_state=$(systemctl is-active ssh.socket 2>/dev/null) || :
    case "$socket_state" in
        active) socket_listen=$(systemctl show ssh.socket -p Listen --value 2>/dev/null) || socket_listen='' ;;
        inactive|failed) ssh_config=$(sshd -T 2>/dev/null) || ssh_config='' ;;
        *) echo 'WARNING: Cannot determine ssh.socket state; UFW was not enabled automatically.' >&2; return 0 ;;
    esac
    detected=$(python3 - "${SSH_CONNECTION:-}" "$socket_state" "$socket_listen" "$ssh_config" <<'PYSSH'
import ipaddress, re, sys
connection, state, listen, effective = sys.argv[1:]
def port(value):
    if not re.fullmatch(r'[0-9]{1,5}', value) or not 1 <= int(value) <= 65535:
        raise ValueError('Invalid SSH port')
    return int(value)
ports = set()
try:
    fields = connection.split()
    if len(fields) == 4:
        ipaddress.ip_address(fields[0]); ipaddress.ip_address(fields[2]); port(fields[1])
        ports.add(port(fields[3]))
except ValueError:
    pass
try:
    if state == 'active':
        endpoints = re.findall(r'(\S+)\s+\(Stream\)', listen)
        if not endpoints or re.sub(r'\S+\s+\(Stream\)', '', listen).strip():
            raise ValueError('Unrecognized ssh.socket Listen')
        for endpoint in endpoints:
            match = re.fullmatch(r'\[([^\]]+)\]:([0-9]+)|([^:\s]+):([0-9]+)|([0-9]+)', endpoint)
            if not match: raise ValueError('Unrecognized SSH endpoint')
            if match[1]:
                if ipaddress.ip_address(match[1]).version != 6: raise ValueError('Invalid IPv6 endpoint')
            elif match[3] and match[3] != '*':
                if ipaddress.ip_address(match[3]).version != 4: raise ValueError('Invalid IPv4 endpoint')
            ports.add(port(match[2] or match[4] or match[5]))
    else:
        for value in re.findall(r'^port (\S+)$', effective, re.M):
            try: ports.add(port(value))
            except ValueError: pass
    if not ports: raise ValueError('No confirmed SSH port')
except ValueError:
    sys.exit(1)
print('\n'.join(map(str, sorted(ports))))
PYSSH
    ) || {
        echo 'WARNING: SSH port could not be detected reliably (including active ssh.socket). Application rules were added, but UFW was not enabled automatically.' >&2
        return 0
    }
    mapfile -t ssh_ports <<< "$detected"
    for port in "${ssh_ports[@]}"; do
        ufw allow "$port/tcp" || return 1
    done
    ufw --force enable || return 1
}

# ─────────────────────────────────────────────────────────────────────────────
# SHOW RESULTS
# ─────────────────────────────────────────────────────────────────────────────
select_amneziawg() {
    INSTALL_AWG=n
    local answer
    while true; do
        printf 'Set up an additional AmneziaWG connection? [y/N]: '
        IFS= read -r answer || return 0
        case "$answer" in
            ''|n|N) return 0 ;;
            y|Y) INSTALL_AWG=y; return 0 ;;
            *) printf 'Please enter y or n.\n' ;;
        esac
    done
}

awg_port_available() {
    python3 - <<'PYPORT'
import errno, socket, sys
for family, address in ((socket.AF_INET,'0.0.0.0'), (socket.AF_INET6,'::')):
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as listener:
            if family == socket.AF_INET6: listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((address,8443))
    except OSError as error:
        if family == socket.AF_INET6 and error.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL): continue
        sys.exit(1 if error.errno == errno.EADDRINUSE else 2)
PYPORT
}

check_awg_reinstall_owner() {
    systemctl is-active --quiet x-ui || return 1
    python3 - "${XUIDB:-/etc/x-ui/x-ui.db}" <<'PYOWNER'
import os, pathlib, re, sqlite3, subprocess, sys
try:
    unit = pathlib.Path('/etc/systemd/system/x-ui.service')
    if not unit.is_file() or unit.is_symlink(): sys.exit(1)
    with sqlite3.connect(pathlib.Path(sys.argv[1]).as_uri()+'?mode=ro', uri=True) as db:
        rows = db.execute("SELECT protocol,listen,port,tag,enable FROM inbounds WHERE protocol='amneziawg' OR tag='inbound-8443-udp'").fetchall()
    if rows != [('amneziawg','0.0.0.0',8443,'inbound-8443-udp',1)]: sys.exit(1)
    main = int(subprocess.check_output(['systemctl','show','x-ui','-p','MainPID','--value'], text=True).strip())
    if main <= 1 or os.readlink(f'/proc/{main}/exe') != '/usr/local/x-ui/x-ui': sys.exit(1)
    listing = subprocess.check_output(['ss','-H','-lntup'], text=True)
    owners = set()
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) < 6 or fields[:2] != ['udp','UNCONN'] or fields[4].rsplit(':',1)[-1] != '8443': continue
        pids = set(map(int, re.findall(r'pid=(\d+)',line)))
        if fields[4] not in ('*:8443','0.0.0.0:8443','[::]:8443',':::8443') or len(pids) != 1: sys.exit(1)
        owners.update(pids)
    if len(owners) != 1: sys.exit(1)
    pid = owners.pop()
    # Official 3X-UI v3.9.0 embeds AWG in the panel process. A managed
    # Xray child is also accepted; neither case admits a foreign owner.
    if pid == main: sys.exit(0)
    executable = pathlib.Path(os.readlink(f'/proc/{pid}/exe'))
    parent = int(pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[1])
    if (parent != main or executable.parent != pathlib.Path('/usr/local/x-ui/bin')
            or not re.fullmatch(r'xray-linux-[A-Za-z0-9_-]+',executable.name) or not executable.is_file()): sys.exit(1)
except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError):
    sys.exit(1)
PYOWNER
}

prepare_awg_reinstall() {
    [[ "${AWG_REINSTALL:-n}" == y ]] || return 0
    check_awg_reinstall_owner || { msg_err 'AWG ownership changed before cleanup; existing deployment preserved.'; return 1; }
    systemctl stop x-ui || { msg_err 'Cannot stop owned 3X-UI before AWG reinstall; configuration preserved.'; return 1; }
    if ! awg_port_available; then
        systemctl start x-ui || msg_warn 'Previous 3X-UI restart failed; inspect services. Configuration retained.'
        msg_err 'UDP/8443 did not become available after stopping owned 3X-UI/Xray; reinstall stopped before cleanup.'
        return 1
    fi
}

preflight_amneziawg() {
    AWG_REINSTALL=n
    [[ "${INSTALL_AWG:-n}" == y ]] || return 0
    [[ "${PANEL_TAG:-}" == v3.9.0 || "${PANEL_TAG:-}" == v3.10.0 ]] || { msg_err "AmneziaWG 3.1 integration requires verified 3X-UI v3.9.0 or v3.10.0."; return 1; }
    local port_result=0
    awg_port_available || port_result=$?
    if (( port_result != 0 )); then
        (( port_result == 1 )) && check_awg_reinstall_owner || {
            msg_err 'UDP/8443 is unavailable and a unique owned AWG listener could not be confirmed; existing deployment preserved.'
            return 1
        }
        AWG_REINSTALL=y
    fi
    AWG_HELPER="${PANEL_STAGE:?Release preflight is required}/managed-amneziawg.py"
    curl -fsSL --connect-timeout 15 --max-time 60 "${GITHUB_RAW}/assets/amneziawg/managed.py" -o "$AWG_HELPER" || return 1
}

install_amneziawg() {
    [[ "${INSTALL_AWG:-n}" == y ]] || return 0
    local inbound_id
    inbound_id=$(printf '%s' "$config_password" | python3 "${AWG_HELPER:?AmneziaWG preflight is required}" "$domain" "$panel_path" "$config_username") || return 1
    [[ "$inbound_id" =~ ^[1-9][0-9]*$ ]] || return 1
    AWG_RESULT=configured
}

select_adguard() {
    INSTALL_AGH=n
    local answer
    while true; do
        printf 'Install and configure AdGuard Home? [y/N]: '
        if ! IFS= read -r answer; then return 0; fi
        case "$answer" in
            ''|n|N) return 0 ;;
            y|Y)
                case "$(uname -m)" in
                    x86_64|aarch64|arm64) INSTALL_AGH=y; return 0 ;;
                    *) msg_err 'AdGuard Home supports only amd64/arm64; existing deployment was not changed.'; return 1 ;;
                esac ;;
            *) printf 'Please enter y or n.\n' ;;
        esac
    done
}

adguard_admin_probe() {
    # Install-only: Backup/Restore health never needs the plaintext password.
    (
        local directory result
        directory=$(mktemp -d) || exit 1
        trap 'rm -rf -- "$directory"' EXIT
        chmod 0700 "$directory" || exit 1
        umask 077
        printf '%s' "$AGH_PASSWORD" | python3 -c 'import json,sys; json.dump({"name":"admin","password":sys.stdin.read()}, sys.stdout)' > "$directory/login.json" || exit 1
        chmod 0600 "$directory/login.json" || exit 1
        result=$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 15 \
            --resolve "${domain}:443:127.0.0.1" -H 'Content-Type: application/json' \
            --data-binary "@$directory/login.json" -c "$directory/cookies" \
            -o "$directory/login-response" -w '%{http_code}' \
            "https://${domain}/${AGH_PATH}/control/login") || exit 1
        [[ "$result" == 200 ]] || exit 1
        result=$(curl --noproxy '*' -fsS --connect-timeout 5 --max-time 15 \
            --resolve "${domain}:443:127.0.0.1" -b "$directory/cookies" \
            -o "$directory/status.json" -w '%{http_code}' \
            "https://${domain}/${AGH_PATH}/control/status") || exit 1
        [[ "$result" == 200 ]] || exit 1
        python3 - "$directory/status.json" "$AGH_WEB_PORT" "$AGH_DNS_PORT" <<'PY'
import json, pathlib, sys
status = json.loads(pathlib.Path(sys.argv[1]).read_text())
if not isinstance(status, dict) or status.get('version') != 'v0.107.79' or status.get('running') is not True:
    raise ValueError('Invalid authenticated AGH status')
for key, expected in (('http_port', sys.argv[2]), ('dns_port', sys.argv[3])):
    if type(status.get(key)) is not int or status[key] != int(expected):
        raise ValueError('Authenticated AGH status does not match managed ports')
PY
    )
}

adguard_stage() {
    # The shared helper is conditional and uses the same validated project ref.
    curl -fsSL "${GITHUB_RAW}/assets/adguard/managed.sh" -o "$AGH_TEMP/helper" &&
        bash -n "$AGH_TEMP/helper" || return 1
    install -o root -g root -m 0600 "$AGH_TEMP/helper" /usr/local/lib/3x-ui-pro/managed-adguard.sh || return 1
    . /usr/local/lib/3x-ui-pro/managed-adguard.sh
    agh_release "$(uname -m)" || return 1
    apt-get install -y --no-install-recommends apache2-utils || return 1
    curl -fsSL --connect-timeout 15 --max-time 180 \
        "https://github.com/AdguardTeam/AdGuardHome/releases/download/${AGH_VERSION}/AdGuardHome_linux_${AGH_ARCH}.tar.gz" \
        -o "$AGH_TEMP/archive" || return 1
    [[ "$(sha256sum "$AGH_TEMP/archive" | awk '{print $1}')" == "$AGH_SHA" ]] || return 1
    mkdir "$AGH_TEMP/extracted" || return 1
    python3 - "$AGH_TEMP/archive" "$AGH_TEMP/extracted" <<'PY'
import pathlib, sys, tarfile
with tarfile.open(sys.argv[1], 'r:gz') as tar:
    names = set()
    for item in tar:
        name = item.name.removeprefix('./').rstrip('/')
        if not (name == 'AdGuardHome' or name in {'AdGuardHome/' + n for n in (
            'AdGuardHome', 'CHANGELOG.md', 'AdGuardHome.sig', 'LICENSE.txt', 'README.md')}):
            raise ValueError('Invalid AGH unexpected release archive member')
        if not (name not in names):
            raise ValueError('Invalid AGH duplicate release archive entry')
        names.add(name)
        if not (item.isdir() if name == 'AdGuardHome' else item.isfile()):
            raise ValueError('Invalid AGH release archive member type')
    if not ('AdGuardHome/AdGuardHome' in names):
        raise ValueError('Invalid AGH required release binary')
    tar.extractall(sys.argv[2], filter='data')
PY
    [[ $? == 0 ]] || return 1
    [[ -f "$AGH_TEMP/extracted/AdGuardHome/AdGuardHome" && ! -L "$AGH_TEMP/extracted/AdGuardHome/AdGuardHome" ]] || return 1
    chmod 0755 "$AGH_TEMP/extracted/AdGuardHome/AdGuardHome" || return 1
    [[ "$("$AGH_TEMP/extracted/AdGuardHome/AdGuardHome" --version)" == "AdGuard Home, version $AGH_VERSION" ]] || return 1
    mv "$AGH_TEMP/extracted/AdGuardHome" /opt/AdGuardHome || return 1
    chown -R root:root /opt/AdGuardHome && chmod 0700 /opt/AdGuardHome || return 1
    AGH_PASSWORD=$(gen_random_string 32) || return 1
    AGH_PATH="adg-$(gen_random_string 12)" || return 1
    [[ "$AGH_PASSWORD" =~ ^[A-Za-z0-9]{32}$ && "$AGH_PATH" =~ ^adg-[A-Za-z0-9]{12}$ ]] || return 1
    local hash ports
    hash=$(printf '%s\n' "$AGH_PASSWORD" | htpasswd -niB -C 12 admin) || return 1
    hash=${hash#admin:}
    [[ "$hash" =~ ^\$2[aby]\$12\$[./A-Za-z0-9]{53}$ ]] || return 1
    # Binding both TCP and UDP sockets avoids the core generator's TCP-only probe.
    ports=$(python3 - <<'PY'
import secrets, socket
sockets = []
try:
    for _ in range(100):
        port = 10000 + secrets.randbelow(55536)
        try:
            tcp, udp = socket.socket(), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tcp.bind(('127.0.0.1', port)); udp.bind(('127.0.0.1', port))
        except OSError:
            tcp.close(); udp.close(); continue
        sockets.extend([tcp, udp]); print(port)
        if len(sockets) == 4: break
    if not (len(sockets) == 4):
        raise ValueError('Invalid AGH allocation of two TCP/UDP ports')
finally:
    for s in sockets: s.close()
PY
    ) || return 1
    local -a selected
    mapfile -t selected <<< "$ports"
    AGH_WEB_PORT=${selected[0]} AGH_DNS_PORT=${selected[1]} AGH_DOMAIN=$domain
    cat > /opt/AdGuardHome/AdGuardHome.yaml <<EOFAGH
http:
  address: 127.0.0.1:${AGH_WEB_PORT}
  doh:
    insecure_enabled: true
    routes:
      - GET /dns-query
      - POST /dns-query
      - GET /dns-query/{ClientID}
      - POST /dns-query/{ClientID}
users:
  - name: admin
    password: '${hash}'
auth_attempts: 5
block_auth_min: 15
dns:
  bind_hosts:
    - 127.0.0.1
  port: ${AGH_DNS_PORT}
  upstream_dns:
    - https://dns.cloudflare.com/dns-query
    - https://dns.google/dns-query
    - https://dns.quad9.net/dns-query
  bootstrap_dns:
    - 1.1.1.1
    - 8.8.8.8
    - 9.9.9.9
  trusted_proxies:
    - 127.0.0.1/32
filtering:
  protection_enabled: true
  filtering_enabled: true
filters:
  - enabled: true
    url: https://adguardteam.github.io/HostlistsRegistry/assets/filter_1.txt
    name: AdGuard DNS filter
    id: 1
tls:
  enabled: false
schema_version: 34
EOFAGH
    [[ $? == 0 ]] || return 1
    chmod 0600 /opt/AdGuardHome/AdGuardHome.yaml || return 1
    python3 - /opt/AdGuardHome/managed.json "$domain" "$AGH_PATH" "$AGH_WEB_PORT" "$AGH_DNS_PORT" "$AGH_ARCH" <<'PY'
import json, sys
file, domain, path, web, dns, arch = sys.argv[1:]
with open(file, 'w') as out:
    json.dump(dict(version='v0.107.79', domain=domain, path=path, web_port=int(web), dns_port=int(dns), arch=arch), out)
PY
    [[ $? == 0 ]] || return 1
    chmod 0600 /opt/AdGuardHome/managed.json || return 1
    agh_install_service || return 1
    agh_snippet > "$AGH_TEMP/candidate" || return 1
    install -o root -g root -m 0600 "$AGH_TEMP/candidate" /etc/nginx/snippets/x-ui-auto-optional/adguard.conf || return 1
    nginx -t || return 1
    AGH_NGINX_RELOAD_ATTEMPTED=1
    systemctl reload nginx && agh_health && adguard_admin_probe && check_installation
}

install_adguard() {
    local AGH_TEMP had_snippet=0 result=0 AGH_NGINX_RELOAD_ATTEMPTED=0
    AGH_RESULT=failed_unverified
    AGH_TEMP=$(mktemp -d) || return 1
    chmod 0700 "$AGH_TEMP" || { rm -rf "$AGH_TEMP"; return 1; }
    if [[ -e /etc/nginx/snippets/x-ui-auto-optional/adguard.conf ]]; then
        cp -a /etc/nginx/snippets/x-ui-auto-optional/adguard.conf "$AGH_TEMP/previous" || { rm -rf "$AGH_TEMP"; return 1; }
        had_snippet=1
    fi
    if ! adguard_stage; then
        msg_err 'AdGuard Home stage failed.'
        cleanup_adguard || result=1
        if (( had_snippet )); then
            cp -a "$AGH_TEMP/previous" /etc/nginx/snippets/x-ui-auto-optional/adguard.conf || result=1
        fi
        nginx -t || result=1
        if (( AGH_NGINX_RELOAD_ATTEMPTED )); then systemctl reload nginx || result=1; fi
        check_installation || result=1
        AGH_PASSWORD=''
        if (( result == 0 )); then
            AGH_RESULT=failed_rolled_back
            msg_warn 'Core 3X-UI stack remains operational.'
        else
            msg_err 'Rollback could not be verified. Inspect nginx and core services.'
        fi
        rm -rf "$AGH_TEMP"
        return 1
    fi
    rm -rf "$AGH_TEMP" || return 1
    AGH_RESULT=installed
}

show_results() {
    local version version_label="" firewall
    version=$(/usr/local/x-ui/x-ui -v 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1) || version=""
    [[ -n "$version" ]] && version_label=" (3X-UI ${version})"

    echo
    msg_inf '============================================================'
    msg_inf " [i] Base OS                ${BASE_OS_RESULT:-not_prepared} (full upgrade is not rollbackable)"
    msg_inf " [i] Local timezone         $(timedatectl show -p Timezone --value)"
    if [[ "${INSTALL_SECURITY:-n}" == y ]]; then
        msg_inf ' [i] APT schedule           update 02:30 / upgrade 02:50; reboot 04:38, including logged-in users'
    fi
    [[ ! -e /var/run/reboot-required ]] || msg_warn ' [!] Reboot required; post-reboot acceptance pending'
    msg_inf '  3X-UI Auto Nginx — Installation Result'
    msg_inf '============================================================'
    # The core passed its initial gate; optional rollback may leave its current health unverified.
    if [[ "${AGH_RESULT:-not_requested}" == failed_unverified || "${VISION_RESULT:-not_requested}" == failed_unverified || "${CORE_RESULT:-configured}" == failed_unverified ]]; then
        msg_warn ' [!] 3X-UI / Xray           Post-rollback health not verified'
    else
        msg_ok " [✓] 3X-UI / Xray           Running${version_label}"
    fi
    case "${CPU_SUPPORT_LEVEL:-info}" in
        ok)   msg_ok " [✓] CPU support             ${CPU_SUPPORT_TEXT}" ;;
        warn) msg_warn " [!] CPU support             ${CPU_SUPPORT_TEXT}" ;;
        *)    msg_inf " [i] CPU support             ${CPU_SUPPORT_TEXT:-Compatible (acceleration not assessed)}" ;;
    esac
    if [[ "${AGH_RESULT:-not_requested}" == failed_unverified || "${VISION_RESULT:-not_requested}" == failed_unverified || "${CORE_RESULT:-configured}" == failed_unverified ]]; then
        msg_warn ' [!] nginx                  Post-rollback health not verified'
    else
        msg_ok ' [✓] nginx                  Running'
    fi
    if [[ -s "/etc/letsencrypt/live/${domain}/fullchain.pem" && -s "/etc/letsencrypt/live/${domain}/privkey.pem" &&
          -s "/etc/letsencrypt/live/${reality_domain}/fullchain.pem" && -s "/etc/letsencrypt/live/${reality_domain}/privkey.pem" &&
          -s "/root/cert/${domain}/fullchain.pem" && -s "/root/cert/${domain}/privkey.pem" ]]; then
        msg_ok ' [✓] TLS certificates       Ready'
    else
        msg_warn ' [!] TLS certificates       Check certificate files'
    fi
    if [[ "${AGH_RESULT:-not_requested}" == failed_unverified || "${VISION_RESULT:-not_requested}" == failed_unverified || "${CORE_RESULT:-configured}" == failed_unverified ]]; then
        msg_warn ' [!] XHTTP                  Post-rollback health not verified'
    else
        msg_ok ' [✓] XHTTP                  Ready'
    fi
    if [[ "${AGH_RESULT:-not_requested}" == failed_unverified || "${VISION_RESULT:-not_requested}" == failed_unverified || "${CORE_RESULT:-configured}" == failed_unverified ]]; then
        msg_warn ' [!] Diagnostics            Post-rollback health not verified'
    elif [[ -s /var/www/diagnostics/index.html && -s /var/www/diagnostics/speedtest.js &&
          -s /var/www/diagnostics/speedtest_worker.js && -s /usr/local/lib/3x-ui-pro/mtr-backend.py ]]; then
        msg_ok ' [✓] Diagnostics            Ready'
    else
        msg_warn ' [!] Diagnostics            Check diagnostics files'
    fi
    if [[ -x /usr/local/bin/x-ui-backup ]]; then
        msg_ok ' [✓] Backup / Restore       Installed'
    else
        msg_warn ' [!] Backup / Restore       Backup utility unavailable'
    fi
    case "${AWG_RESULT:-not_requested}" in
        configured) msg_ok " [✓] AmneziaWG              Configured (UDP/8443)" ;;
        failed) msg_warn " [!] AmneziaWG              Not configured" ;;
    esac
    case "${SECURITY_RESULT:-not_requested}" in
        configured) msg_ok ' [✓] VPS Security + DoT     Configured (strict system TLS DNS)' ;;
        failed_rolled_back) msg_warn ' [!] VPS Security + DoT     Failed — rolled back / unchanged' ;;
        failed_unverified) msg_warn ' [!] VPS Security + DoT     Failed — rollback not verified' ;;
    esac
    case "${SWAP_RESULT:-not_requested}" in
        created) msg_ok ' [✓] SWAP 1 GiB             Created and enabled' ;;
        existing) msg_inf ' [i] SWAP                   Already configured' ;;
        skipped) msg_warn " [!] SWAP                   Skipped ($SWAP_REASON)" ;;
    esac
    case "${VISION_RESULT:-not_requested}" in
        configured) msg_ok " [✓] VLESS TLS Vision       Ready ($vision_domain:443)" ;;
        failed_rolled_back) msg_warn ' [!] VLESS TLS Vision       Failed — rolled back' ;;
        failed_unverified) msg_warn ' [!] VLESS TLS Vision       Failed — rollback not verified' ;;
    esac
    case "${CLIENT_RESULT:-not_requested}" in
        configured)
            msg_ok ' [✓] Client                  Created'
            msg_ok ' [✓] Subscription            Ready'
            ;;
        failed_unverified) msg_warn ' [!] Client / Subscription   Failed verification — inspect panel before retrying' ;;
    esac
    case "${AGH_RESULT:-not_requested}" in
        installed)
            msg_ok ' [✓] AdGuard Home           Running (v0.107.79)'
            msg_ok ' [✓] DNS-over-HTTPS         Ready' ;;
        failed_rolled_back)
            msg_warn ' [!] AdGuard Home           Failed — rolled back'
            msg_warn ' [!] DNS-over-HTTPS         Not installed' ;;
        failed_unverified)
            msg_warn ' [!] AdGuard Home           Failed — rollback not verified'
            msg_warn ' [!] DNS-over-HTTPS         State not verified' ;;
    esac
    if [[ "${AGH_RESULT:-not_requested}" == failed_unverified || "${VISION_RESULT:-not_requested}" == failed_unverified || "${CORE_RESULT:-configured}" == failed_unverified ]]; then
        msg_warn ' [!] Certificate renewal    Post-rollback health not verified'
    else
        msg_ok ' [✓] Certificate renewal    Webroot + systemd timer'
    fi
    firewall=$(LC_ALL=C ufw status 2>/dev/null) || firewall=""
    case "$firewall" in
        "Status: active"*)   msg_ok ' [✓] Firewall / UFW         Active' ;;
        "Status: inactive"*) msg_warn ' [!] Firewall / UFW         Inactive — review firewall settings' ;;
        *)                   msg_warn ' [!] Firewall / UFW         Unknown — review firewall settings' ;;
    esac

    printf '\n Enabled by default: REALITY · XHTTP · Hysteria2\n Optional profiles: WS · Trojan gRPC\n'
    msg_inf "\n Panel:"
    msg_inf " https://${domain}/${panel_path}/"
    msg_inf "\n Diagnostics (panel login required):"
    msg_inf " https://${domain}/${panel_path}/diag"
    printf '\n Username: %s\n Password: %s\n' "$config_username" "$config_password"
    if [[ "${CLIENT_RESULT:-not_requested}" == configured ]]; then
        local subscription_url
        subscription_url=$(printf '%s' "$CLIENT_OUTPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["url"])')
        msg_inf "\n Subscription:"
        msg_inf " $subscription_url"
        printf '%s' "$CLIENT_OUTPUT" | python3 -c 'import json,sys; print(" " + " / ".join(json.load(sys.stdin)["protocols"]))'
        CLIENT_OUTPUT=''
    fi
    if [[ "${AWG_RESULT:-not_requested}" == configured ]]; then
        msg_inf "\n AmneziaWG:"
        msg_inf ' AWG vpn:// export requires an Amnezia-compatible application.'
    fi
    msg_inf "\n Backup:"
    printf ' x-ui-backup backup\n\n'
    if [[ "${AGH_RESULT:-not_requested}" == installed ]]; then
        msg_inf " AdGuard Home:"
        msg_inf " https://${domain}/${AGH_PATH}/"
        printf ' Login: admin\n Password: %s\n DoH: https://%s/dns-query\n\n' "$AGH_PASSWORD" "$domain"
        AGH_PASSWORD=''
    elif [[ "${AGH_RESULT:-not_requested}" == failed_rolled_back ]]; then
        msg_warn ' AdGuard Home was not installed. The core 3X-UI stack remains operational.'
    elif [[ "${AGH_RESULT:-not_requested}" == failed_unverified || "${VISION_RESULT:-not_requested}" == failed_unverified || "${CORE_RESULT:-configured}" == failed_unverified ]]; then
        msg_warn ' Post-rollback core health could not be verified. Inspect nginx and core services.'
    fi
    msg_inf '============================================================'
    msg_inf ' Save these credentials before closing the terminal.'
    msg_inf '============================================================'
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
select_security() {
    local answer
    INSTALL_SECURITY=n
    printf 'Enhance VPS security? [Y/n]: '
    while IFS= read -r answer; do
        case "$answer" in
            ''|y|Y) INSTALL_SECURITY=y; return 0 ;;
            n|N) return 0 ;;
            *) printf 'Please enter y or n.\n' ;;
        esac
    done
    return 0
}

select_vision() {
    local answer
    INSTALL_VISION=n
    while true; do
        printf 'Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]: '
        IFS= read -r answer || return 0
        case "$answer" in
            ''|n|N) return 0 ;;
            y|Y) break ;;
            *) printf 'Please enter y or n.\n' ;;
        esac
    done
    printf 'Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains): '
    IFS= read -r vision_domain || return 1
    vision_domain=${vision_domain,,}
    [[ -n "$vision_domain" ]] || return 1
    INSTALL_VISION=y
}

select_client() {
    local answer
    CREATE_CLIENT=n
    while true; do
        printf 'Create a client in 3X-UI and display a subscription link after installation? [Y/n]: '
        IFS= read -r answer || return 0
        case "$answer" in
            ''|y|Y) CREATE_CLIENT=y; return 0 ;;
            n|N) return 0 ;;
            *) printf 'Please enter y or n.\n' ;;
        esac
    done
}

preflight_vision_artifacts() {
    VISION_PREVIOUS_HOOK=''
    VISION_OWNED_LINEAGE=''
    local name file hook old_domain='' nginx_domain=''
    for name in vision vision-acme; do
        file="/etc/nginx/sites-available/$name.conf"
        if [[ -e "$file" || -L "$file" ]]; then
            [[ -f "$file" && ! -L "$file" && "$(head -n1 "$file")" == '# Managed by 3x-ui Auto Nginx: Vision' &&
               "$(stat -c '%u:%g:%a' "$file")" == '0:0:644' ]] || { msg_err "Unowned Vision artifact: $file"; return 1; }
        fi
        file="/etc/nginx/sites-enabled/$name.conf"
        if [[ -e "$file" || -L "$file" ]]; then
            [[ -L "$file" && "$(readlink "$file")" == "/etc/nginx/sites-available/$name.conf" ]] || {
                msg_err "Unowned Vision link: $file"; return 1;
            }
        fi
    done
    if [[ -f /etc/nginx/sites-available/vision.conf || -f /etc/nginx/sites-available/vision-acme.conf ]]; then
        nginx_domain=$(python3 "$PANEL_STAGE/managed-vision.py" --preflight-nginx \
            /etc/nginx/sites-available/vision.conf /etc/nginx/sites-available/vision-acme.conf) || {
            msg_err 'Modified/unrecognized Vision nginx configuration; deployment preserved.'; return 1;
        }
    fi
    hook=/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision
    if [[ -e "$hook" || -L "$hook" ]]; then
        [[ -f "$hook" && ! -L "$hook" && "$(stat -c '%u:%g:%a' "$hook")" == '0:0:755' ]] || return 1
        old_domain=$(sed -n 's/^VISION_DOMAIN=//p' "$hook")
        [[ "$old_domain" =~ ^[a-z0-9][a-z0-9.-]*[a-z0-9]$ && "$old_domain" == *.* ]] || return 1
        cmp -s "$hook" <(render_vision_hook "$old_domain") ||
            cmp -s "$hook" <(render_vision_hook "$old_domain" previous) ||
            cmp -s "$hook" <(render_vision_hook "$old_domain" legacy) || { msg_err 'Unowned Vision deploy-hook; deployment preserved.'; return 1; }
        [[ -z "$nginx_domain" || "$old_domain" == "$nginx_domain" ]] || { msg_err 'Vision hook/nginx domains differ.'; return 1; }
        VISION_PREVIOUS_HOOK=owned
    fi
    if [[ "${INSTALL_VISION:-n}" == y ]] &&
       [[ -e "/etc/letsencrypt/live/$vision_domain" || -L "/etc/letsencrypt/live/$vision_domain" ||
          -e "/etc/letsencrypt/archive/$vision_domain" || -L "/etc/letsencrypt/archive/$vision_domain" ||
          -e "/etc/letsencrypt/renewal/$vision_domain.conf" || -L "/etc/letsencrypt/renewal/$vision_domain.conf" ]]; then
        [[ "$VISION_PREVIOUS_HOOK" == owned && "$old_domain" == "$vision_domain" && "$nginx_domain" == "$vision_domain" &&
           -f /etc/nginx/sites-available/vision.conf && -f /etc/nginx/sites-available/vision-acme.conf ]] || {
            msg_err 'Existing Vision lineage has no complete verified project ownership; deployment preserved.'; return 1;
        }
        check_webroot_lineage "$vision_domain" || return 1
        VISION_OWNED_LINEAGE=$vision_domain
    fi
}

preflight_integrated_features() {
    if [[ "${INSTALL_VISION:-n}" == y || "${CREATE_CLIENT:-n}" == y ]]; then
        [[ "$PANEL_TAG" == v3.9.0 || "$PANEL_TAG" == v3.10.0 ]] || {
            msg_err 'Vision and initial client require verified 3X-UI v3.9.0 or v3.10.0; select N with other versions.'; return 1;
        }
        # Reuse the existing authenticated local HTTPS/CSRF implementation.
        AWG_HELPER="$PANEL_STAGE/managed-amneziawg.py"
        curl -fsSL --connect-timeout 15 --max-time 60 "$GITHUB_RAW/assets/amneziawg/managed.py" -o "$AWG_HELPER" || return 1
    fi
    local feature
    for feature in security vision client; do
        case "$feature" in
            security) [[ "${INSTALL_SECURITY:-n}" == y ]] || continue ;;
            vision) [[ "${INSTALL_VISION:-n}" == y || -e /etc/nginx/sites-available/vision.conf || -e /etc/nginx/sites-available/vision-acme.conf ]] || continue ;;
            client) [[ "${CREATE_CLIENT:-n}" == y ]] || continue ;;
        esac
        curl -fsSL --connect-timeout 15 --max-time 60 "$GITHUB_RAW/assets/$feature/managed.py" -o "$PANEL_STAGE/managed-$feature.py" || return 1
        python3 - "$PANEL_STAGE/managed-$feature.py" <<'PYCHECK' || return 1
import ast, sys
ast.parse(open(sys.argv[1]).read())
PYCHECK
    done
    preflight_vision_artifacts || return 1
    if [[ "${INSTALL_SECURITY:-n}" == y ]]; then
        local security_preflight
        if ! security_preflight=$(python3 "$PANEL_STAGE/managed-security.py" --preflight); then
            printf '%s' "$security_preflight" | python3 -c 'import json,sys; [print("[!] Security preflight: "+w, file=sys.stderr) for w in json.load(sys.stdin)["warnings"]]'
            return 1
        fi
    fi
    [[ "${INSTALL_VISION:-n}" == y ]] || return 0
    get_server_ip
    python3 - "$vision_domain" "$domain" "$reality_domain" "$IP4" "$IP6" <<'PYDOMAIN' || return 1
import ipaddress, re, socket, sys
name, panel, reality, ipv4, ipv6 = sys.argv[1:]
if (len(name)>253 or '.' not in name or name.lower() in (panel.lower(), reality.lower())
    or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in name.split('.'))):
    sys.exit('Invalid/conflicting Vision domain; deployment preserved')
expected = {str(ipaddress.ip_address(ip)) for ip in (ipv4, ipv6) if ip}
actual = {str(ipaddress.ip_address(row[4][0])) for row in socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)}
if not actual or not expected or not actual <= expected:
    sys.exit('Every Vision A/AAAA record must point to this VPS; deployment preserved')
PYDOMAIN
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

install_vision() {
    VISION_RESULT=failed_unverified
    local new_lineage=0 result=0 vision_output='' hook=/etc/letsencrypt/renewal-hooks/deploy/3x-ui-auto-nginx-vision vision_port fallback_port vision_stage='rendering ACME configuration' vision_exit=1
    vision_port=$(make_port)
    fallback_port=$(make_port)
    while [[ "$fallback_port" == "$vision_port" ]]; do fallback_port=$(make_port); done
    [[ -e "/etc/letsencrypt/live/$vision_domain" || -e "/etc/letsencrypt/renewal/$vision_domain.conf" ]] || new_lineage=1
    if (( ! new_lineage )) && [[ "${VISION_OWNED_LINEAGE:-}" != "$vision_domain" ]]; then
        VISION_RESULT=failed_rolled_back
        msg_warn 'Existing Vision lineage was not approved by project ownership preflight; preserved.'
        return 1
    fi
    if python3 "$PANEL_STAGE/managed-vision.py" --render-acme "$vision_domain" > /etc/nginx/sites-available/vision-acme.conf &&
       { vision_stage='activating ACME configuration'; chmod 0644 /etc/nginx/sites-available/vision-acme.conf &&
         ln -s /etc/nginx/sites-available/vision-acme.conf /etc/nginx/sites-enabled/vision-acme.conf; } &&
       { vision_stage='validating ACME nginx configuration'; nginx -t; } &&
       { vision_stage='reloading ACME nginx'; systemctl reload nginx; } &&
       { vision_stage='issuing/checking Vision certificate'; if (( new_lineage )); then
             certbot certonly --webroot --webroot-path /var/www/acme --cert-name "$vision_domain" \
                 -d "$vision_domain" --non-interactive --agree-tos --register-unsafely-without-email;
         else check_webroot_lineage "$vision_domain";
         fi; } &&
       { vision_stage='installing Vision renewal hook'; render_vision_hook "$vision_domain" > "$hook" && chown root:root "$hook" && chmod 0755 "$hook" && bash -n "$hook"; } &&
       { vision_stage='configuring Vision inbound/nginx/HTTPS'; vision_output=$(printf '%s' "$config_password" | python3 "$PANEL_STAGE/managed-vision.py" "$AWG_HELPER" \
           "$domain" "$panel_path" "$config_username" "$vision_domain" "$vision_port" "$fallback_port" "${emoji_flag:-🌐}"); }; then
        VISION_RESULT=configured
        return 0
    else
        vision_exit=$?
    fi
    if [[ -n "$vision_output" ]]; then
        VISION_RESULT=$(printf '%s' "$vision_output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])') || VISION_RESULT=failed_unverified
    elif [[ "$vision_stage" == 'configuring Vision inbound/nginx/HTTPS' ]]; then
        # No result after entering the API helper cannot establish rollback.
        VISION_RESULT=failed_unverified
    else
        # Failure before API changes; only newly owned webroot/hook artifacts exist.
        VISION_RESULT=failed_rolled_back
    fi
    if [[ "$VISION_RESULT" == failed_rolled_back ]]; then
        rm -f "$hook" || result=1
        rm -f /etc/nginx/sites-enabled/vision-acme.conf /etc/nginx/sites-available/vision-acme.conf || result=1
        if (( new_lineage )) && [[ -e "/etc/letsencrypt/live/$vision_domain" || -e "/etc/letsencrypt/renewal/$vision_domain.conf" ]]; then
            certbot delete --cert-name "$vision_domain" --non-interactive || result=1
        fi
    else
        msg_warn 'Vision rollback is unverified; retained certificate and managed renewal artifacts for inspection.'
    fi
    nginx -t && systemctl reload nginx && check_installation || result=1
    if (( result != 0 )); then VISION_RESULT=failed_unverified; fi
    msg_warn "Vision failed during $vision_stage (exit $vision_exit): rollback=$VISION_RESULT"
    return 1
}

install_security() {
    local output
    SECURITY_RESULT=failed_unverified
    output=$(python3 "$PANEL_STAGE/managed-security.py")
    SECURITY_RESULT=$(printf '%s' "$output" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])') || return 1
    printf '%s' "$output" | python3 -c 'import json,sys; [print("[!] "+w) for w in json.load(sys.stdin)["warnings"]]'
    if [[ "$SECURITY_RESULT" == configured ]]; then DNS_FINALIZED=y; return 0; fi
    local failed_security=$SECURITY_RESULT
    if [[ "${DNS_PREPARED:-n}" == y ]]; then
        if rollback_system_dns; then
            [[ "$failed_security" == failed_unverified ]] || SECURITY_RESULT=failed_rolled_back
        else
            SECURITY_RESULT=failed_unverified
        fi
    fi
    return 1
}

install_initial_client() {
    CLIENT_RESULT=failed_unverified
    CLIENT_OUTPUT=$(printf '%s' "$config_password" | python3 "$PANEL_STAGE/managed-client.py" \
        "$AWG_HELPER" "$domain" "$panel_path" "$config_username") || return 1
    CLIENT_RESULT=configured
}

main() {
    confirm_destructive_reinstall || exit 1
    validate_domains || exit 1
    select_security || exit 1
    select_vision || exit 1
    select_amneziawg || exit 1
    select_adguard || exit 1
    select_client || exit 1
    printf '\nPreparing system...\n'
    msg_warn 'Initial full OS upgrade is mandatory; services may restart. A required initial reboot is manual (sudo reboot).'
    preflight_base_os || { msg_err 'Base OS preflight failed; existing deployment was not removed.'; exit 1; }
    preflight_panel_release || { msg_err "Release preflight failed; existing deployment was not removed."; exit 1; }
    preflight_amneziawg || { msg_err "AmneziaWG preflight failed; existing deployment was not removed."; exit 1; }
    preflight_integrated_features || { msg_err 'Optional feature preflight failed; existing deployment was not removed.'; exit 1; }
    setup_swap || { SWAP_RESULT=skipped; SWAP_REASON='setup failed'; }
    prepare_base_os || { msg_err 'OS preparation failed; deployment was not removed, package changes may remain.'; exit 1; }
    prepare_system_dns || { msg_err 'DNS preparation failed; existing deployment was not removed.'; exit 1; }
    local awg_xui_stopped=n
    if [[ "${AWG_REINSTALL:-n}" == y ]]; then
        prepare_awg_reinstall || { msg_err 'AWG reinstall preparation failed; deployment was not removed.'; exit 1; }
        awg_xui_stopped=y
    fi
    cleanup_adguard || {
        msg_err "Cannot clean AdGuard Home; core deployment was not removed."
        if [[ "$awg_xui_stopped" == y ]]; then
            if systemctl start x-ui && systemctl is-active --quiet x-ui; then
                msg_warn 'Reinstall aborted; previous x-ui is active and its configuration retained. AdGuard Home may require inspection.'
            else
                msg_warn 'Reinstall aborted; previous x-ui could not be confirmed active. Configuration retained; recover manually with sudo systemctl start x-ui. AdGuard Home may require inspection.'
            fi
        fi
        exit 1
    }
    clean_previous_install || { msg_err "Previous deployment cleanup failed (exit $?). See the cause above; installation stopped."; exit 1; }
    install_packages || { msg_err "Dependency setup failed."; exit 1; }
    setup_firewall || { msg_err "Firewall setup failed."; exit 1; }
    get_server_ip || { msg_err "VPS IP detection failed (exit $?). See the cause above; installation stopped."; exit 1; }
    setup_acme_http || { msg_err "ACME HTTP setup failed."; exit 1; }
    get_ssl_certs || { msg_err "Webroot certificate setup failed."; exit 1; }

    install_panel || { msg_err "3X-UI installation failed (exit $?). See the cause above; installation stopped."; exit 1; }

    configure_nginx || { msg_err "nginx configuration failed (exit $?). See the cause above; installation stopped."; exit 1; }
    configure_xui_db || { msg_err "3X-UI database configuration failed (exit $?). See the cause above; installation stopped."; exit 1; }
    install_clash_sub || { msg_err "Clash template download/setup failed (exit $?). See the cause above; installation stopped."; exit 1; }
    install_fake_site || { msg_err "Cover site download/setup failed (exit $?). See the cause above; installation stopped."; exit 1; }
    install_diagnostics || { msg_err "Diagnostics download/setup failed (exit $?). See the cause above; installation stopped."; exit 1; }
    tune_system || { msg_err "System tuning failed (exit $?). See the cause above; installation stopped."; exit 1; }
    install_backup_tool || { msg_err "Backup tool setup failed (exit $?). See the cause above; installation stopped."; exit 1; }
    setup_certificate_renewal || { msg_err "Certificate renewal setup failed."; exit 1; }

    if ! systemctl is-enabled --quiet x-ui; then
        systemctl daemon-reload && systemctl enable x-ui.service || { msg_err "3X-UI service enablement failed (exit $?). Installation stopped."; exit 1; }
    fi
    x-ui restart || { msg_err "3X-UI restart failed (exit $?). Installation stopped."; exit 1; }
    check_installation || { msg_err "Installation failed mandatory health checks."; exit 1; }

    local install_result=0
    VISION_RESULT=not_requested
    SECURITY_RESULT=not_requested
    CLIENT_RESULT=not_requested
    if [[ "${INSTALL_VISION:-n}" == y ]]; then
        install_vision || install_result=1
    fi
    AWG_RESULT=not_requested
    if [[ "${INSTALL_AWG:-n}" == y ]]; then
        AWG_RESULT=failed
        install_amneziawg || install_result=1
    fi
    AGH_RESULT=not_requested
    if [[ "$INSTALL_AGH" == y ]]; then
        install_adguard || install_result=1
    fi
    # DNS was prepared and verified before cleanup; repeat runtime checks here.
    if [[ "${INSTALL_SECURITY:-n}" == y ]]; then
        install_security || install_result=1
    fi
    if [[ "${CREATE_CLIENT:-n}" == y ]]; then
        # A retained unverified Vision inbound may lack its public SNI route.
        if [[ "$VISION_RESULT" != failed_unverified ]] && check_installation; then
            install_initial_client || install_result=1
        else
            install_result=1
            CLIENT_RESULT=failed_unverified
        fi
    fi
    CORE_RESULT=configured
    if [[ "${INSTALL_SECURITY:-n}${INSTALL_VISION:-n}${INSTALL_AWG:-n}${INSTALL_AGH:-n}${CREATE_CLIENT:-n}" != nnnnn ]]; then
        if ! check_installation; then CORE_RESULT=failed_unverified; install_result=1; fi
    fi
    show_results
    finish_initial_reboot "$install_result" || install_result=1
    return "$install_result"
}

main
