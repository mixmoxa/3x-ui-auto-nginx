# Architecture

Descriptive reference for how the project is built and deployed. Agent rules are in [AGENTS.md](../AGENTS.md); release process and local commands are in [CONTRIBUTING.md](../CONTRIBUTING.md); vulnerability reports in [SECURITY.md](../SECURITY.md).

## Purpose, sources and licensing

The project automates deployment of the official 3x-ui panel, its bundled Xray and the supporting nginx/VPS infrastructure. Supported systems are Ubuntu 24.04, Ubuntu 26.04 and Debian 13 (see `check_os()` in `x-ui-latest.sh`).

It is developed independently of the reference-only fork origin [mozaroc/3x-ui-pro](https://github.com/mozaroc/3x-ui-pro); there is no automatic upstream sync. Attribution to mozaroc and [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui), and previous authors' rights, are preserved. Original xPROMSx work is GPL-3.0-only under [LICENSE](../LICENSE) and [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md); there is no repository-wide relicensing claim for inherited material. LibreSpeed keeps its LGPL notices.

Panel and Xray versions and archive pins live only in `verified_panel_release()` in `x-ui-latest.sh`. Archive integrity across architectures is not proof of functional compatibility: full transport integration runs on amd64; ARMv5/v6/v7 have extra QEMU CLI/key/config checks; other architectures are accepted separately.

## Project ref and release assets

Project-owned assets are fetched from `GITHUB_RAW`, derived from `PROJECT_REF="${XUI_AUTO_REF:-main}"`. Allowed values: `main`, an exact 40-hex commit SHA, or a stable `vMAJOR.MINOR.PATCH` tag. The default raw base is `https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main`. All assets follow the same selected tree, with no per-file fallback to main. Official upstream archives use their own validated release contract; `-version` is an explicit stable selection. Downloaded executables are not run before integrity/layout checks.

Published `x-ui-latest.sh` release assets default to the exact 40-hex release commit. `tools/prepare_release.py` takes an existing stable tag and its SHA, reads Git content, validates Bash/source initialization and writes a reproducible asset plus a SHA-256 sidecar without touching the working source.

Release flow: after review and merge, the owner runs **Actions → Prepare Release → Run workflow** on `main` with a new stable version. The manual-only workflow verifies the protected main SHA, rejects existing tags/releases, creates a lightweight tag and a **Draft Release** with `x-ui-latest.sh` and its checksum, then downloads both to verify bytes, checksum and source. Only that job has `contents: write` (standard `GITHUB_TOKEN`). The workflow never publishes, overwrites or deletes; a failed or partial run is inspected by the owner. The owner writes release notes and publishes as stable Latest.

Primary install URL: `https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh`. Version-specific `releases/download/vX.Y.Z/...` stays that version. The only documented fallback is Raw GitHub from `main` (inside localized `<details>` in the READMEs). There is no CDN fallback, telemetry or download badge. Release notes describe user-visible changes and compatibility.

## Components

- `x-ui-latest.sh`: interactive manager. Installation is a destructive fresh install / full rebuild, not an in-place updater. Reinstall of an existing deployment requires typing `YES`.
- `assets/domains/managed.py`: Change Domains. Bounded edits of the local SQLite DB and nginx stream config, full Backup v3 before changes, role/Host ownership checks and durable private `prepared`/`switching`/`committed` recovery state in `/var/lib/3x-ui-auto-nginx/change-domains` (outside Restore trees). Known manifest-free v2.1.7 layouts can be adopted after read-only agreement checks. Old certificates/lineages are retained.
- `assets/adguard/managed.sh`: managed AdGuard Home (AGH) config, nginx snippet, health/cleanup. Initial pin v0.107.80, schema 34; fresh installs update via the native web updater; updated binaries are verified against vendor signatures at Backup/Restore; v0.107.79 archives stay compatible.
- `assets/amneziawg/managed.py`: optional embedded AmneziaWG 3.1 on UDP/8443 via the official panel API/session. Administrator firewall rules are left alone on failure.
- `assets/vision/managed.py`: optional VLESS TLS/XTLS Vision on a third, distinct domain via the native panel API, with TLS fallback, owned nginx/hook state and rollback.
- `assets/client/managed.py`: optional native initial-client creation, attachment checks and validation of the official RAW/JSON/export output. There is no custom production subscription generator.
- `assets/security/managed.py`: optional Fail2ban, unattended-upgrades/timers, strict system DoT and scoped rollback. Host-specific Security state is not part of portable Backup v3.
- `assets/backup/x-ui-backup.sh`: private Backup/Restore v3 (see below).
- `assets/clash/clash.yaml`, `assets/diagnostics/`, `assets/cover-sites/`: public consumer template, authenticated diagnostics, static camouflage sites.

A shared fd-9 lock and an unfinished-journal check cover every modifying manager action and standalone Backup/Restore.

## Install lifecycle

Release, option and domain preflights and download verification run before managed destructive cleanup. Base OS preparation includes a mandatory initial full upgrade (it may restart services and leaves installed packages in place). Strict DNS preparation has a private rollback checkpoint. Optional 1 GiB swap is best-effort and skips unsuitable hosts.

Core health gates run before optional feature configuration. Fresh transport health is strict. Maintenance reads the enable flags of the local REALITY/Hysteria2/XHTTP roles and keeps Disable as is. New-layout Change Domains binds Hysteria2 to REALITY; Panel-only leaves it unchanged. A requested optional feature that fails yields a nonzero result even when the restored core is healthy. After the core is ready, the final output still shows the generated panel credentials on optional failure, does not claim an unverified feature is ready and does not print failed AGH credentials. A required initial reboot is manual.

New installs generate independent static Panel/REALITY cover sites once from six supplied templates; Vision uses a different template. Assets come from one pinned project source archive. See [COVER_SITES.md](COVER_SITES.md). Legacy sites are not migrated; the pages are not a proven DPI/probing defense.

## Network and ports

- Public TCP/443 belongs to nginx stream SNI routing: REALITY → loopback 8443, panel TLS → loopback 7443, optional Vision → its own loopback listener.
- REALITY camouflage target is TLS `127.0.0.1:9443` with a static site. Fresh REALITY stream routing has a 9443 backup with `max_fails=0` and a trusted PROXY contract.
- Fresh Hysteria2 uses UDP/443 with the REALITY domain/certificate and a static-only nginx Unix backend `/run/3x-ui-hysteria-cover.sock` serving the cover-reality site. See [HYSTERIA_COVER.md](HYSTERIA_COVER.md) and [HYSTERIA_INDEPENDENCE.md](HYSTERIA_INDEPENDENCE.md).
- XHTTP uses stream-up and its Unix socket. WS and Trojan gRPC are optional profiles with exact known paths and fixed backend ports; the split gRPC method contract and public Host/SNI/ALPN are kept. There are no request-selected `/<port>/...` localhost proxies.
- The panel listens on loopback HTTPS behind nginx; subscriptions use their configured loopback TLS backend. RAW, JSON and Clash/Mihomo public endpoints contain no internal listener ports or loopback addresses. The native Hysteria2 JSON may keep its masquerade pointing at the fixed UDS cover path. The panel-domain HTTPS API-token/multi-node path and native node mTLS are used as is.
- nginx stream supplies PROXY information to trusted backends. HTTP real-IP handling trusts loopback only. Vision terminates native TLS and forwards fallback HTTP with PROXY to a restricted static nginx listener. Client-supplied forwarding headers are not treated as verified identity.
- AGH HTTP and native DNS are loopback-only with native TLS off; nginx terminates TLS on the existing panel domain. Routing: exact DoH, single-segment ClientID, GET/POST limits, random `/adg-.../` admin path, cookie path/Secure policy, authenticated install probe. Public TCP/UDP 53 is never opened. See [ADGUARD_UPDATES.md](ADGUARD_UPDATES.md).
- VPS Security's strict `systemd-resolved` DoT is separate from AGH's upstreams: no plaintext fallback, project-scoped drop-ins, effective policy checks and verified failure recovery. Unrelated host network/SSH policy is not rewritten. UFW keeps existing rules/policy; enabling an inactive UFW requires detected/allowed SSH access; Restore never activates UFW.

## Certificates

Certbot uses the `/var/www/acme` webroot and the distro `certbot.timer`; nginx stays online during renewal. Managed deploy hooks restart x-ui for the applicable panel/Vision certificate. Official lineage validation/reconfigure rules apply; foreign certificates, hooks and accounts are left alone; legacy project cron entries are removed by exact match. There is no standalone renewal and nginx is not stopped to issue certificates.

## Stable paths

`/etc/x-ui`, `/usr/local/x-ui`, `/usr/bin/x-ui`, `/etc/nginx`, `/etc/letsencrypt`, `/root/cert`, `/opt/AdGuardHome` and the project systemd/website paths are shared with Backup ownership. Historical identifiers `/usr/local/lib/3x-ui-pro`, `/etc/sysctl.d/99-3x-ui-pro.conf`, test names and `personal-v*` releases are kept as compatibility identifiers. Changing managed paths needs a designed Backup/Restore migration.

## Backup v3

Backup v3 requires a matching OS ID/version and architecture and presence-aware managed state. The archive is trusted input from the same administrator; Restore validation detects incompatibility and corruption, it does not authenticate provenance. Flow: staged migrations and preflights (DB, TLS, AGH), authenticated pinned AGH binary before execution, private effective-nginx validation, target snapshot before replacement, replacement, post-restore core health, and rollback that restores prior service states (private recovery material is kept if health cannot be verified). Migrations change only staging, keep source archive bytes and custom state, and fail on ambiguous managed identity. Archived helpers are not sourced to establish trust. Full real-host recovery is not established by private fixtures.

## Credentials

Panel credentials, client UUIDs/passwords/keys, API sessions/tokens, subscription IDs/URLs, TLS keys and backup contents are private: not in commits, PR text, logs, screenshots or CI artifacts, not in process argv (private temp files/stdin instead), and session material is cleaned up on success and failure. Panel CSRF/session/API validation and initial-client reconciliation are the native ones. Diagnostics need a panel session and restricted local backends and report only safe stage/exit information. Public documented examples and funding addresses/QR codes are intentional. Suspected exposure is reported privately per [SECURITY.md](../SECURITY.md).

## Telegram Web Proxy Manager companion

[Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager) is a companion, not an automatically installed or conflict-free component. Main-menu option 4 downloads its official bootstrap from current `main` on every launch (trusting GitHub HTTPS and that branch). Existing launchers must be root-owned regular 0755 files without symlinks; option 4 does not execute them directly or fall back to them. First installation requires the Ubuntu/working-stack preflight and default-No consent. The bootstrap owns SHA selection, validation, updates and recovery. No stack lock is held while it runs; pending Change Domains recovery still runs before menu actions.

## CI

`tests/run_ci.py` has an explicit registry of TestCase classes (check with `--check-completeness`). Suites: `nonroot`, `root` (private Backup/ownership/recovery fixtures), `integration` (real pinned x-ui/Xray/nginx/Mihomo), `services` (real AGH/DNS/DoH, Certbot/Pebble), `systemd` (root inside a disposable QEMU guest). Required job names: `Stack XHTTP and security`, `Stack Backup and restore`, `Real services (ubuntu-24.04)`, `Real services (ubuntu-26.04)`, `Full fresh installer (ubuntu-26.04)`. `tests/ci_scope.py` limits the lightweight docs-only mode to the listed root READMEs, Markdown under `docs/` and PNG under `assets/support/`; everything else runs full CI. Upstream Canary is daily/manual and non-required; integration PASS is not full installer acceptance (public DNS/Let's Encrypt, provider UFW, full reboot and whole-system recovery need live acceptance). Details: [CONTRIBUTING.md](../CONTRIBUTING.md); history of acceptance boundaries: [V2_AUDIT.md](V2_AUDIT.md).
