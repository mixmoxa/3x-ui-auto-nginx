# 3x-ui Auto Nginx

Maintained deployment stack derived from [mozaroc/3x-ui-pro](https://github.com/mozaroc/3x-ui-pro), using the panel from [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui). Development is independent; do not synchronize upstream automatically.

## Repository structure

- `x-ui-latest.sh`: fresh installer/rebuild; stops and removes the previous installation and panel database.
- `assets/adguard/managed.sh`: active managed AdGuard Home component for the integrated installer and Backup/Restore.
- `assets/backup/x-ui-backup.sh`: Backup/Restore v3, same OS ID/version and architecture.
- `assets/clash/clash.yaml`: Clash/Mihomo subscription template.
- `assets/diagnostics/`: MTR backend, diagnostics page and vendored LibreSpeed files.
- `assets/fake-sites/`: cover pages.
- `tests/run_ci.py`: canonical runner for nonroot, root, integration and services suites; see CONTRIBUTING.md for privilege contexts and commands.
- `.github/workflows/stack-xhttp.yml`, `stack-backup.yml` and `stack-services.yml`: PR/push validation on `main`; manual dispatch available.
- `README.md`: default, maintainer-reviewed Russian documentation; `README_EN.md`: full English documentation. `README_RU.md` is a compatibility pointer for older Russian links. Arabic, Persian, Simplified Chinese, Spanish and Turkish have dedicated README translations.
- `CONTRIBUTING.md`: development, checks, protection and emergency recovery.

## Runtime sources and compatibility

Canonical asset base: `https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main`.
The installer uses `GITHUB_RAW` for project-owned assets; panel/CLI releases still come from MHSanaei/3x-ui. Keep upstream attribution and third-party release references.

Do not rename historical filesystem paths `/usr/local/lib/3x-ui-pro` or `/etc/sysctl.d/99-3x-ui-pro.conf` without a separate backup-compatible migration. Test filenames/classes and archived `personal-v*` releases are historical identifiers.

## Architecture

The installer creates REALITY/TCP, XHTTP stream-up over a Unix socket, Hysteria2/UDP, WebSocket and Trojan gRPC inbounds. nginx routes public TCP 443 by SNI to REALITY on 8443 or the panel TLS vhost on 7443. The REALITY target uses 9443. Hysteria2 uses UDP 443.

WS and Trojan gRPC routes must use known paths and fixed backend ports. Never restore variable `/<port>/...` proxying. Diagnostics use panel-session authentication and a hardened localhost backend. Active UFW policy is preserved; enabling inactive UFW requires successful SSH-port discovery.

## Validation and changes

Read actual code before making claims. Run canonical completeness and all applicable suites in the Ubuntu CI environment, preserving their root/non-root privilege contexts. Check all tracked shell scripts with Bash syntax and ShellCheck error-only. Never execute the destructive installer on the development machine. See CONTRIBUTING.md for exact commands.

Required GitHub check contexts are `Stack XHTTP and security`, `Stack Backup and restore`, `Real services (ubuntu-24.04)` and `Real services (ubuntu-26.04)`. Preserve these names; branch protection depends on them.

Use feature branches and PRs to `main`. Preserve `personal`, historical branches, tags and releases. Their removal is outside routine maintenance. The maintainer has adopted `GPL-3.0-only` for original xPROMSx developments and changes; see `LICENSE` and `THIRD_PARTY_NOTICES.md`. Preserve previous authors' rights and the documented unresolved status of inherited material; do not claim repository-wide GPL clearance.

## Companion project

[Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager) complements the stack with Telemt WEB proxy installation and management. Keep its prominent, relevant README block; do not imply automatic installation or port-conflict-free coexistence.
