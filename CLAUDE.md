# Claude Code project and development guidance

This guide is authoritative for Claude Code; [AGENTS.md](AGENTS.md) provides equally authoritative guidance for Codex.

## Purpose, sources and licensing

This project automates deployment of the official 3x-ui panel, bundled Xray and supporting nginx/VPS infrastructure. Supported systems are Ubuntu 24.04, Ubuntu 26.04 and Debian 13; verify `check_os()` before changing that claim.

Development is independent of the reference-only fork origin [mozaroc/3x-ui-pro](https://github.com/mozaroc/3x-ui-pro). Do not auto-sync upstream. Preserve attribution to mozaroc and [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui), and previous authors' rights. Original xPROMSx developments/modifications are GPL-3.0-only within [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); do not claim repository-wide relicensing or clearance for inherited material. Preserve LibreSpeed's existing LGPL notices.

The current verified baseline is 3x-ui v3.10.2 / bundled Xray 26.10.10. **Read `verified_panel_release()` in `x-ui-latest.sh` for the authoritative versions and archive pins** rather than copying this snapshot into code or tests. Production/default integration must use that single source. Archive integrity across supported architectures is not proof of functional compatibility everywhere: full transport integration is amd64; ARMv5/v6/v7 have additional QEMU CLI/key/config checks. Other architecture acceptance remains separate.

Project-owned assets use `GITHUB_RAW`, derived from validated `PROJECT_REF="${XUI_AUTO_REF:-main}"`: `main`, an exact 40-hex commit SHA, or a stable `vMAJOR.MINOR.PATCH` tag. The default raw base is `https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main`; all assets must follow the same selected tree. Do not introduce individual fallbacks to main. Official upstream archives use their own validated release contract; `-version` is explicit stable selection, not promotion. Never run downloaded executables before integrity/layout checks.

## Production components and lifecycle

- `x-ui-latest.sh`: destructive fresh install / full rebuild, not an in-place updater. **Never execute it on the development machine.** Existing deployment reinstall and uninstall require exact uppercase `YES`. Preserve foreign state and ownership checks.
- `assets/adguard/managed.sh`: managed AdGuard Home config, nginx snippet and health/cleanup contract; pinned v0.107.79, schema 34.
- `assets/amneziawg/managed.py`: official panel API/session and optional embedded AmneziaWG 3.1, UDP/8443; preserve administrator firewall rules on failure.
- `assets/vision/managed.py`: optional VLESS TLS/XTLS Vision with a third, distinct domain, native panel API, TLS fallback, owned nginx/hook state and rollback.
- `assets/client/managed.py`: optional native initial-client creation, attachment checks and official RAW/JSON/export validation; no custom production subscription generator.
- `assets/security/managed.py`: optional Fail2ban, unattended-upgrades/timers, strict system DoT and scoped rollback. Host-specific Security state is not portable Backup v3 data.
- `assets/backup/x-ui-backup.sh`: private Backup/Restore v3, staged migrations/preflights, target snapshot, replacement and verified rollback.
- `assets/clash/clash.yaml`, `assets/diagnostics/`, `assets/fake-sites/`: public consumer template, authenticated diagnostics and static camouflage sites.

Read actual lifecycle code before changing it. Release/option/domain preflights and download verification precede managed destructive cleanup. Base OS preparation includes a mandatory initial full upgrade; it may restart services and leave installed packages behind. Strict DNS preparation has a private rollback checkpoint. Optional 1 GiB swap is best-effort and skips unsuitable conditions. Do not infer that preflight is completely free of package/system preparation.

Core mandatory health gates precede optional feature configuration. Preserve existing option results and rollback verification: requested failure must yield nonzero even when the restored core is healthy. After initial core readiness, the final result must still show generated panel credentials on optional failure, without claiming an unverified feature is ready or printing failed AGH credentials. A required initial reboot is manual; no automatic successful full-stack reboot acceptance is implied.

## Network and trust boundaries

- Public TCP/443 belongs to nginx stream SNI routing: REALITY to loopback 8443, panel TLS to loopback 7443, optional Vision to its distinct loopback listener. REALITY camouflage target is TLS 127.0.0.1:9443 with a static site, not a second panel proxy. Hysteria2 remains UDP/443.
- XHTTP uses production stream-up and its Unix socket; WS and Trojan gRPC are optional profiles with exact known paths/fixed backend ports. Preserve public Host/SNI/ALPN, credentials, PROXY semantics and the split gRPC method contract. Never add request-selected `/<port>/...` localhost proxies or arbitrary localhost-port forwarding.
- The panel listens on loopback HTTPS behind nginx; subscriptions use their configured loopback TLS backend. Keep RAW, JSON and Clash/Mihomo public exports free of internal listener ports, loopback addresses and UDS paths. Preserve the panel-domain HTTPS API-token/multi-node path and native node mTLS behavior.
- nginx's stream proxy supplies PROXY information to intended trusted backends. HTTP real-IP handling trusts loopback only; Vision terminates native TLS and forwards fallback HTTP with PROXY to a restricted static nginx listener. Do not accept untrusted client-supplied forwarding headers as verified identity.
- AGH HTTP/native DNS stay loopback-only, native TLS off, with nginx TLS termination on the existing panel domain. Keep exact DoH plus validated single-segment ClientID routing, GET/POST limits, random `/adg-.../` admin path, cookie path/Secure policy and functional authenticated install probe. Never open public TCP/UDP :53 or bypass admin authentication.
- VPS Security's strict `systemd-resolved` DoT is separate from AGH's upstreams. Preserve no plaintext fallback, scoped project drop-ins, effective policy checks and verified failure recovery; do not rewrite unrelated host network/SSH policy. UFW preserves existing rules/policy; enabling inactive UFW requires detected/allowed SSH access. Restore never activates UFW.

## Certificates, Backup and stable paths

Certbot uses `/var/www/acme` webroot and distro `certbot.timer`; nginx remains online during renewal. Managed deploy hooks restart x-ui for the applicable panel/Vision certificate only. Preserve official lineage validation/reconfigure rules, timer/active transaction coordination, foreign certificates/hooks/accounts and exact legacy-project-cron cleanup. Do not introduce standalone renewal or stop nginx to issue certificates.

Keep `/etc/x-ui`, `/usr/local/x-ui`, `/usr/bin/x-ui`, `/etc/nginx`, `/etc/letsencrypt`, `/root/cert`, `/opt/AdGuardHome` and existing project systemd/website paths consistent with Backup ownership. Historical identifiers `/usr/local/lib/3x-ui-pro`, `/etc/sysctl.d/99-3x-ui-pro.conf`, test names and `personal-v*` releases remain compatibility identifiers. Do not rename or broaden managed paths without an explicitly designed Backup/Restore migration.

Backup v3 requires matching OS ID/version and architecture, trusted archives under administrator control, and presence-aware managed state. Restore validation detects incompatibility/corruption; it does not authenticate archive provenance. Never source an archived helper to establish its trust. Preserve staged DB/TLS/AGH validation, authenticated pinned AGH binary before execution, private effective-nginx validation without live-host resource fallback, target snapshot readiness before replacement and post-restore core health. Migrations change only staging, preserve source archive bytes and custom state, and fail rather than guess ambiguous managed identity. Rollback must restore prior service states; retain private recovery material if health cannot be verified. Full real-host recovery is not established by private fixtures.

## Credentials and disclosure

Panel credentials, client UUIDs/passwords/keys, API sessions/tokens, subscription IDs/URLs, TLS keys and backup contents are private. Do not put them in commits, PR bodies, logs, screenshots or CI artifacts. Keep plaintext out of process argv, use private temporary files/stdin, and clean session material on success/failure. Preserve native CSRF/session/API validation and initial-client reconciliation instead of blindly repeating creation. Diagnostics require panel-session authentication and restricted local backends; report only safe validation stage/exit information, not private API bodies or command payloads.

Public documented examples and funding addresses/QR codes are intentional; do not rotate or rewrite them. Report suspected actual exposure privately under [SECURITY.md](SECURITY.md), without quoting values publicly. Credential rotation, production remediation and history rewriting require separate authorization; scanning the current tree is not a complete history/security audit.

## CI, tests and review

[CONTRIBUTING.md](CONTRIBUTING.md) defines exact dependency/local commands. Use a disposable Ubuntu environment; test processes/listeners/files must be private, bounded and cleaned up. Confirmed bugs require **reproducing RED regression → minimal fix → same test PASS → full suite PASS**. Do not mask failures with retries, weaker assertions or silent missing-binary skips.

`tests/run_ci.py` collects only defining TestCase classes, assigned once in its explicit registry. Every new class must be registered; new methods are automatic. Run `--check-completeness`; never use `unittest discover` as the suite entry point. Privilege contexts:

| Suite | Context / coverage |
| --- | --- |
| `nonroot` | EUID != 0; fast static/fixture/fault regressions |
| `root` | EUID 0; private Backup/ownership/recovery fixtures |
| `integration` | EUID != 0; real pinned x-ui/Xray/nginx/Mihomo, transport and consumer contracts |
| `services` | EUID != 0; real AGH/DNS/DoH and Certbot/Pebble, private partial Restore |
| `systemd` | EUID 0 **inside disposable QEMU guest**, PID 1 systemd; native host-service checks |

Required protected job names must remain exactly:

- `Stack XHTTP and security`: all tracked shell Bash syntax, ShellCheck error-only, actionlint 1.7.12, PR Git identity, completeness, nonroot and integration.
- `Stack Backup and restore`: completeness and root fixtures.
- `Real services (ubuntu-24.04)` and `Real services (ubuntu-26.04)`: native service suites and selected Vision/client API/AWG tests.
- `Full fresh installer (ubuntu-26.04)`: final-stage fresh install/cold boot after Draft → Ready.

Create every new PR as **Draft**. Codex must not mark it Ready without the owner's instruction. Ordinary CI runs in Draft; production/code changes need Full Fresh after Ready. Only a verified docs-only diff may use the lightweight documentation smoke instead; never report Full Fresh PASS when it did not run. A new commit after a final PASS requires a new Draft → Ready cycle. Merge and releases belong to the owner.

`tests/ci_scope.py` is the shared conservative exception: the listed root READMEs, Markdown under `docs/` and PNG under `assets/support/` only. Unknown scope, mixed changes, agent/development guidance, tests, workflows and other code keep full CI; manual dispatch is always full. Keep the same five protected contexts and strict protection. Docs-mode success certifies scope, UTF-8/PNG/local-reference/whitespace checks, not installation. Do not add job skips or path filters that leave required checks pending.

`stack-services.yml` also runs Debian 13 native API/Vision/AWG and three systemd userspace guests with a common CI kernel. Preserve their execution model and privilege split. Check all tracked `*.sh`, all workflow YAML and `git diff --check` / `git show --check`. Run applicable suites and require green jobs on the **exact final HEAD**; earlier results do not certify later changes.

Upstream Canary is daily/manual, non-required, reuses real integration with the candidate's own official archive/bundled Xray and does not update production pins. Cached tested results follow candidate digest/test fingerprint; preparation failures are not cached as compatibility failures. Promotion requires a separate reviewed PR. Integration PASS is not full installer acceptance: public DNS/Let's Encrypt, actual provider/kernel UFW, full reboot and whole-system disaster recovery still need explicitly authorized live acceptance. Required PR CI uses read-only permissions/free hosted runners without repository secrets; the separate release-only Telegram notification workflow uses its bot secret and must not expose it to PR code.

## Git identity and operational boundaries

Use feature branches and focused PRs to protected `main`; no unrelated changes or automatic upstream sync. Before commits set **repository-local**, not global, `user.name=Proms` and `user.email=102687702+xPROMSx@users.noreply.github.com`. Verify effective author/committer for every new commit and again after PR creation. The public `xPROMSx` alias with that same email is also approved; preserve historical upstream identities without rewriting existing commit objects.

The PR metadata checker validates only new PR commits against the event's actual base/head SHAs. It accepts the maintainer pair, public GitHub login/noreply pairs, narrowly formed bot identities and GitHub web committers. Rejected metadata must not be echoed. Push/manual events explicitly skip this PR-only check; shallow/invalid/unavailable/empty/oversized PR ranges fail. See [CONTRIBUTING.md](CONTRIBUTING.md) for local use and limits.

Do not merge, tag, publish releases, operate a VPS, change GitHub protection/settings, force-push or rewrite published history without explicit task authorization. Preserve `personal`, historical branches, tags and releases. Use repair PRs; emergency protection changes described in CONTRIBUTING are maintainer-only actions, not standing agent permission.

## Documentation and authoritative references

`README.md` is the maintainer-reviewed Russian source and default GitHub page; `README_EN.md` is the complete English adaptation. Arabic, Persian, Simplified Chinese, Spanish and Turkish are full translations; `README_RU.md` is the old-link pointer. Keep all seven full languages semantically aligned, exact commands/warnings/requirements and legacy anchors intact. User benefits/installation precede concise technical details. Do not promote unverified guarantees, change funding data or alter visual presentation during maintenance.

Retain [Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager) as a companion, not an automatically installed or guaranteed conflict-free component. Project release versions are separate from upstream versions. [docs/V2_AUDIT.md](docs/V2_AUDIT.md) records historical feature/acceptance boundaries, not the current pin source or proof of full live deployment. AGENTS.md and CLAUDE.md are equally authoritative, self-contained agent guides with matching security/operational constraints; consult both plus CONTRIBUTING, SECURITY and license notices, and verify actual source when documentation may be historical.
