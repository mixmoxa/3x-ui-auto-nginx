# Contributing to 3x-ui Auto Nginx

## Development

`main` is the maintained production line. Create `feat/*`, `fix/*`, `docs/*` or `chore/*` branches and open pull requests against `main`. Upstream is a reference source; do not automatically synchronize it.

Review product wording with the maintainer in Russian (`README.md`) first, then adapt all seven languages; Russian is the default GitHub landing page (`README.md`), and the full English adaptation is in `README_EN.md`. `README_RU.md` preserves older Russian links. Preserve exact commands, safety warnings and upstream attribution in every full translation. The maintainer has adopted `GPL-3.0-only` for original xPROMSx developments and changes. Follow the partial scope in `LICENSE` and `THIRD_PARTY_NOTICES.md`; do not claim permission to relicense inherited material.

## Required checks

All four checks must pass on the current PR revision:

- `Stack XHTTP and security` (`.github/workflows/stack-xhttp.yml`)
- `Stack Backup and restore` (`.github/workflows/stack-backup.yml`)
- `Real services (ubuntu-24.04)` (`.github/workflows/stack-services.yml`)
- `Real services (ubuntu-26.04)` (`.github/workflows/stack-services.yml`)

The jobs have unique names so GitHub can require them separately. The workflows run for pushes to `main`, pull requests targeting `main`, and manual `workflow_dispatch`. They have read-only repository permissions and no repository-secret dependency.

Reproduce the full suites on a disposable Ubuntu 24.04 test environment:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends nginx libnginx-mod-stream certbot sqlite3 openssl curl python3 python3-configobj python3-cryptography tar gzip shellcheck iproute2 apache2-utils
mapfile -d '' -t scripts < <(git ls-files -z -- '*.sh')
for script in "${scripts[@]}"; do bash -n "$script"; done
shellcheck --severity=error "${scripts[@]}"
python3 tests/run_ci.py --check-completeness
NGINX_BIN=/usr/sbin/nginx python3 tests/run_ci.py --suite nonroot
export NGINX_BIN=/usr/sbin/nginx
sudo --preserve-env=NGINX_BIN python3 tests/run_ci.py --suite root
NGINX_BIN=/usr/sbin/nginx python3 tests/run_ci.py --suite integration
NGINX_BIN=/usr/sbin/nginx python3 tests/run_ci.py --suite services
git diff --check
```

The canonical runner collects only TestCase classes defined in each `tests/test_*.py` module, so imported classes run once. Assign every new TestCase to exactly one suite in `tests/run_ci.py`; completeness fails for unassigned classes or stale/duplicate entries. New test methods in an existing class are included automatically. Do not use `unittest discover` as the CI entry point: existing imports would execute tests twice.

The `nonroot`, `integration` and `services` suites require EUID != 0; the `root` suite requires EUID 0 for ownership/permission coverage. The `systemd` suite requires EUID 0 **inside its disposable VM**, with systemd as PID 1. Do not run non-root suites under sudo. Legacy entry commands remain available for compatibility but are not the canonical CI interface.

CI checks every tracked shell script with `bash -n` and ShellCheck **error-only**. Existing warning/info/style findings are not suppressed or claimed clean. All tracked workflow YAML is checked with actionlint 1.7.12, downloaded from its official release with a pinned SHA-256 verified before extraction; the workflow records the exact download and checksum.

Every confirmed bug must follow: **reproducing RED regression test → fix → same test PASS → full suite PASS**.

Fast regression (`nonroot`/`root`) uses fixtures, fault injection and negative paths. Real integration uses nginx, pinned/checksummed Xray from the verified 3x-ui baseline, the real private-state x-ui subscription backend and Mihomo. The integration suite downloads verified official binaries automatically; there are no silent missing-binary skips or repository secrets. For offline runs, `INTEGRATION_ARTIFACTS` may point to downloaded `x-ui.tar.gz`, `x-ui.sha256` and `mihomo.gz`, plus each `x-ui-linux-armv5/armv6/armv7.tar.gz` archive and its `.sha256` sidecar for the verified-baseline ARM checks; the same hash verification remains mandatory. All listeners and state stay local/temporary, and child processes have bounded cleanup. Most GitHub jobs have 25-minute deadlines; the full fresh-install Ubuntu 26.04 job has a 45-minute deadline.

Real services (`services`) runs on native `ubuntu-24.04` and `ubuntu-26.04` hosted runners. It verifies pinned official AdGuard Home v0.107.79, loopback DNS, nginx TLS DoH/admin, and Certbot HTTP-01 issuance/renewal against pinned Pebble v2.10.1 with validation enabled and local DNS. No public DNS, Let's Encrypt or secrets are used. Both native jobs also run the pinned official panel’s embedded AmneziaWG TCP/UDP, client export, restart and cryptographic-negative test; no kernel module or external VPN server is installed. `SERVICES_ARTIFACTS` can supply `agh.tar.gz` and `pebble.tar.gz` offline; both pinned hashes are still checked before execution.

The private Backup v3 fixture restores real files and runs the verified AGH binary, DNS/DoH/admin and certificate checks. It uses sudo only for private archived ownership checks; all managed paths are relocated into temporary directories. Systemd, Xray, firewall and other core service management remain controlled fixtures, so this is **PARTIAL Restore integration**, not a full real-system recovery claim. The deploy-hook test uses actual nginx validation/reload and renewed TLS certificates; x-ui restart and systemd state are controlled fixtures.

The v2 integration case starts official 3x-ui v3.9.0 with its real client API, CSRF session, native RAW/JSON subscriptions and embedded Xray 26.9.30. It verifies REALITY/XHTTP/Hysteria2/Vision/AWG attachments and per-inbound credentials, then connects through Vision with Xray and Mihomo. HTTPS fallback, PROXY source IP, wrong UUID/SNI/ALPN/trust, closed administrative paths, restart and certificate replacement are real network checks. Certbot/Pebble separately issues and renews three webroot lineages; CI does not claim this is a complete public ACME/systemd/Xray deployment.
The same Vision/API case and native AWG transfer case run in both Ubuntu service jobs and a normal Debian 13 container. Canonical suite privilege checks remain unchanged; these selected cross-distro cases use private nonroot state.

`stack-services.yml` also runs the canonical `systemd` suite against Ubuntu 24.04, Ubuntu 26.04 and Debian 13 userspace inside QEMU TCG. Docker exports each root filesystem; an ordinary container boots it with the tools image's Ubuntu kernel. No privileged Docker, host cgroups, KVM, outside network or paid infrastructure is used. Native Fail2ban/sshd, APT configuration/timers and resolved are exercised. Generated test CA and local authenticated TLS DNS endpoints provide actual TLS traffic, with packet capture excluding plaintext fallback. This tests native distro userspace with a common CI kernel, not each distro's production kernel or cloud network.

See [v2 audit scope](docs/V2_AUDIT.md) for option states, ownership, portable Restore and remaining live acceptance boundaries.

The repository owner must add the exact checks `Real services (ubuntu-24.04)` and `Real services (ubuntu-26.04)` to branch protection/rulesets for required enforcement. Existing protected check names stay unchanged; this PR does not modify repository settings.

Live VPS acceptance is still required for public DNS, Let's Encrypt, provider kernel/firewall behavior, external-network acceptance and full recovery. Do not run `x-ui-latest.sh` to test syntax: it removes an existing installation. The controlled VM test below covers fresh installation and cold boot, not arbitrary provider/VPS acceptance. Use a disposable VPS for live checks.

## Full fresh installation acceptance

The existing Ubuntu 26.04 required job also runs `bash tests/fresh/run.sh` (Docker,
Python 3, Git and passwordless sudo required). It boots a minimal disk-based VM
under QEMU TCG with 2 vCPU/4 GiB RAM, runs the unmodified installer `main()` with
maximum options and one exact checkout SHA, then cold-boots the same disk.
Actual installed services, subscriptions, restricted MTR HTTP and Xray/AWG data
transfer are checked; TLS clients explicitly trust the temporary CA and reject
wrong trust, SNI and credentials. Independent clean disk copies cover mandatory
APT dependency failure and partial installation after verified DNS rollback.
The existing canonical regression preserves STOP on unverified rollback.

Only external DNS/DoT/filter/HTTP-01 services are controlled fixtures (real Pebble
validation); official package/release downloads remain real. This does not test
public Let's Encrypt, a provider's kernel/network or full disaster recovery.
Raw installer logs, disks and private keys are never uploaded. The Ubuntu 26.04
job has a 45-minute limit for this measured sequential workload; other job limits
and required check names are unchanged.

## Verified upstream baseline and Canary

`verified_panel_release()` in `x-ui-latest.sh` is the single version/digest source for production and real integration. The default is 3x-ui v3.10.0 / bundled Xray 26.10.10. Archive pins cover every supported download architecture; full transport integration currently covers **amd64 only**, with additional QEMU ARMv5/v6/v7 CLI, X25519 and config-validation checks. A pinned checksum does not certify architecture-specific runtime behavior.

The installer bootstraps only release-preflight dependencies, then verifies the selected official archive, sidecar and pinned/API digest and validates its layout **before managed cleanup**. Installation consumes that same private archive. Explicit `-version <tag>` requires a published stable release >= v3.8.0 with verifiable assets, and warns when outside the baseline. A manual version choice is not an automatic promotion.

`upstream-canary.yml` runs daily or manually on free Ubuntu 24.04 runners; PRs changing Canary infrastructure also validate it as a non-required check. It runs the existing integration suite with the candidate's own official x-ui and bundled Xray, including native CLI/migration/SQLite persistence, actual RAW/JSON subscriptions, five transport positive/negative pairs and Mihomo. Its report records version, archive SHA-256, bundled Xray and failure diagnostics. It is **not a required PR check**, never writes the baseline, and has no repository-secret or VPS dependency.

A small Actions cache stores only the tested result, keyed by version, digest and test-implementation fingerprint. Unchanged daily candidates reuse the latest tested PASS/FAIL report; preparation/download failures are reported but not cached as tested; changed artifacts/code and every manual run retest. Each fresh result gets a unique cache key, so manual retesting supersedes previous results. Cache eviction causes a fresh run, not a skip. Reports/logs are retained as artifacts for 30 days.

For an explicit local candidate run (non-root, integration dependencies installed):

```bash
python3 tests/upstream_canary.py probe --directory /tmp/xui-canary --version v3.10.0
NGINX_BIN=/usr/sbin/nginx python3 tests/upstream_canary.py run --directory /tmp/xui-canary
python3 tests/upstream_canary.py report --directory /tmp/xui-canary
```

Promote upstream only in a separate reviewed PR: independently confirm all official archive pins, update the single baseline, run all four required jobs, and record full installer/live acceptance. Canary **integration PASS is not full installer acceptance**: systemd lifecycle, public ACME/DNS, kernel UFW, reboot/recovery and non-amd64 behavior still require their own acceptance. Canary failures must be investigated, not hidden by changing assertions or silently substituting baseline binaries.

## Public Git metadata

Before committing, set repository-local `git config user.name Proms` and
`git config user.email 102687702+xPROMSx@users.noreply.github.com` (never global).
Verify both author and committer in `git log --format=fuller <base>..HEAD`.
The maintainer's public `xPROMSx` alias with the same email is also approved.

The existing XHTTP job checks only commits introduced by a PR: head reachable
commits excluding everything reachable from the actual event base. Historical
identities are preserved. Other supported identities are exact public GitHub
login/noreply pairs (optional positive numeric ID prefix), conventional `[bot]`
login/noreply pairs, and `GitHub <noreply@github.com>` web-generated metadata.
Arbitrary display-name aliases are not inferred. Invalid metadata fails with
only the commit SHA and role, never the rejected identity.

Local PR-range validation (full history required):

```bash
GITHUB_EVENT_NAME=pull_request PR_BASE_SHA=<full-base-sha> PR_HEAD_SHA=<full-head-sha> \
python3 tests/ci_git_identity.py
```

Missing, malformed, zero, unavailable, unrelated/empty ranges and shallow history
fail. The check bounds ranges to 1,000 commits and each inspected commit object to
1 MiB. Diverged target history is supported through the reachable-set difference.
Push and manual events explicitly skip this PR-only policy; they do not scan all
historical commits. This checks metadata format, not cryptographic authorship or
GitHub account ownership. Never rewrite published history without authorization.

## Main protection

The main branch protection requires PRs, the required checks and an up-to-date PR branch, with zero required external approvals. Force pushes and deletion are disallowed. Protection applies to administrators; no standing bypass actor is configured.

Emergency recovery is an explicit maintainer action: preserve the current commit, document the incident and exact intended change, and prefer a repair PR. If CI or protection configuration itself blocks recovery, the repository owner may temporarily amend the protection settings, perform the smallest repair, immediately restore the protections, rerun all required checks and record the outcome. This is not permission for routine direct pushes or a permanently exempt automation account.

## Migration compatibility

The initial main checkpoint is `e02bd9e87768afb11b7cad18fc64d77ee637c3b3`, promoted by fast-forward from `personal` after PR #5.

`personal` and historical feature branches/tags/releases are preserved. Do not remove them as part of migration or routine maintenance. Old runtime paths and test identifiers are retained for Backup/Restore compatibility.

## Releases

Publish `vX.Y.Z` project releases from validated `main` with scope, test results and compatibility notes. Preserve historical `personal-v*` releases. Project versioning is separate from the upstream 3x-ui/Xray release versions. Pin the panel with `-version <tag>` when validating a deployment.

User-facing project releases may include a short companion-project footer linking to [Telegram Web Proxy Manager](https://github.com/xPROMSx/3x-ui-auto-nginx#telemt-web-manager); keep it secondary to the actual release changes.
