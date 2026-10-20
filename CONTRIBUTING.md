# Contributing to 3x-ui Auto Nginx

## Development

`main` is the maintained production line. Create `feat/*`, `fix/*`, `docs/*` or `chore/*` branches and open pull requests against `main`. Upstream is a reference source; do not automatically synchronize it.

Create all new PRs as **Draft**. Codex may mark its own PR **Ready for review** when implementation is complete, the final commit is pushed, necessary local checks pass, and no further changes are planned. Do not wait for long-running GitHub CI first: Ready starts the existing final-stage check. Waiting for Full Fresh in the working session is unnecessary; report the exact HEAD and actual **PASS**, **FAIL**, **IN PROGRESS** or **NOT RUN** states at handoff. If another commit is needed after launch, return to Draft during edits and repeat Ready for the new final HEAD. This permission does not authorize merge, actual tags/releases, Prepare Release dispatch, publication, Settings/Rulesets changes or VPS operations.

Review product wording with the maintainer in Russian (`README.md`) first, then adapt all seven languages; Russian is the default GitHub landing page (`README.md`), and the full English adaptation is in `README_EN.md`. `README_RU.md` preserves older Russian links. Preserve exact commands, safety warnings and upstream attribution in every full translation. The maintainer has adopted `GPL-3.0-only` for original xPROMSx developments and changes. Follow the partial scope in `LICENSE` and `THIRD_PARTY_NOTICES.md`; do not claim permission to relicense inherited material.

## Required checks

Keep the four existing required checks, which run during Draft development:

- `Stack XHTTP and security` (`.github/workflows/stack-xhttp.yml`)
- `Stack Backup and restore` (`.github/workflows/stack-backup.yml`)
- `Real services (ubuntu-24.04)` (`.github/workflows/stack-services.yml`)
- `Real services (ubuntu-26.04)` (`.github/workflows/stack-services.yml`)

The final-stage required check is `Full fresh installer (ubuntu-26.04)`
(`.github/workflows/fresh-acceptance.yml`); see the owner setup and acceptance
procedure below. All five checks must pass for the current revision before merge.

The four ordinary checks retain their unique names and run for pushes to `main`,
pull requests targeting `main`, and manual `workflow_dispatch`. Full Fresh runs
only on `ready_for_review` for a PR targeting `main`. These PR validation workflows
have read-only repository permissions and no repository-secret dependency.

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

Required enforcement is configured by the repository owner, not by workflow code.
Preserve the four existing protected check names and add the final-stage check
using the procedure below; this change does not modify repository settings.

Live VPS acceptance is still required for public DNS, Let's Encrypt, provider kernel/firewall behavior, external-network acceptance and full recovery. Do not run `x-ui-latest.sh` to test syntax: it removes an existing installation. The controlled VM test below covers fresh installation and cold boot, not arbitrary provider/VPS acceptance. Use a disposable VPS for live checks.

## Full fresh installation acceptance

`fresh-acceptance.yml` runs `bash tests/fresh/run.sh` (Docker, Python 3, Git and
passwordless sudo required) only when a PR targeting `main` changes from Draft to
Ready for review. It checks out the exact event's PR head SHA with full history.
There is no push, synchronize, opened or manual-dispatch trigger. A new final
launch cancels an older running Full Fresh job for the same PR.

The unchanged harness boots a minimal disk-based VM
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
Raw installer logs, disks and private keys are never uploaded. The dedicated job
has a 45-minute limit for this measured sequential workload. Both ordinary native
services jobs have the standard 25-minute limit; their existing names, Debian 13
coverage and all systemd jobs remain unchanged.

### Owner setup and hosted acceptance

In repository Settings → Rules → Rulesets → `main-protection`, keep enforcement
active and preserve all four checks listed above. Under required status checks,
add the exact fifth context `Full fresh installer (ubuntu-26.04)` with source
**GitHub Actions** (app ID 15368). Keep **Require branches to be up to date before
merging** enabled (strict required status checks), preserve PR requirements and
the existing no-bypass policy. If GitHub does not yet offer the new context, run
the first Draft → Ready acceptance to register it, then add it before any merge.
Do not remove an existing check or merge during this configuration handoff.

Use the CI-change PR to verify GitHub behavior before merging it:

1. Leave the PR Draft while ordinary CI runs. Confirm there is no Full Fresh run.
2. After the final commit, choose Ready for review. Confirm one real Full Fresh
   run with event `pull_request`, action `ready_for_review`, the correct PR and
   checkout SHA; wait for its successful completion in GitHub Actions.
3. With the fifth check required, add a small meaningful follow-up commit.
   Confirm ordinary CI runs, Full Fresh does not start, and the old PASS does not
   satisfy the new revision: merge must be blocked awaiting the fifth check.
4. Convert to Draft, then Ready again. Confirm one new real Full Fresh run on the
   new head SHA and PASS before merge eligibility. Preserve the earlier run/SHA
   evidence. Return the audit PR to Draft if it must remain Draft for handoff.

These are required hosted acceptance steps, not a claim that YAML validation
proves event or protection behavior. Stop if GitHub behaves differently; do not
substitute a skipped job or synthetic success. New commits after a PASS require
another explicit Draft → Ready cycle. A base update required by strict protection
also needs fresh acceptance for the resulting revision. Do not merge until all five required checks are enforced and the final SHA has
a real Full Fresh PASS for code changes or a verified documentation-only smoke.
Never label the documentation exception as Full Fresh PASS.

## Documentation-only CI

Every ordinary job and the final-stage check run `tests/ci_scope.py` after exact
checkout with full history. A nonempty, reliable Git diff may use the lightweight
mode only for the eight listed root README files, `docs/**/*.md`, and PNG images
under `assets/support/`. SVG, agent/contributor instructions, tests, workflows,
unknown paths/types, renames/copies and mixed changes keep full CI. A PR uses the
merge-base of the event base/head; main pushes use before/head across the entire
change. Invalid or unavailable revisions fall back to full CI; manual dispatch
always runs full CI. Branch names, labels and commit messages do not classify it.

The stdlib-only smoke validates changed regular paths, UTF-8, PNG chunk CRCs and
pixel stream, local file/image references within the checkout, and diff whitespace.
It checks new/touched references and tolerates unrelated pre-existing broken links;
it does not contact external sites or enforce Markdown style. Corrupt documents
fail the job. No APT, binary downloads, test suites, Docker or QEMU run in docs mode.
All jobs still execute a real scope/smoke step and report what ran.

The five protected check names stay unchanged. After Draft → Ready, a verified
documentation-only final check states exactly:
`DOCS-ONLY: Full Fresh E2E not executed; documentation scope verified.`
Production/code changes still execute the complete unchanged acceptance sequence.
The owner must confirm hosted docs-only behavior with a separately authorized PR
after merge; synthetic Git-history tests do not prove GitHub merge enforcement.

Ordinary workflow concurrency cancels superseded runs only for the same PR and
workflow. Main pushes and dispatches have independent run-ID groups; Canary and
release workflows remain independent. Cancelled runs are not successful checks.

Fresh diagnostics publish only allowlisted Vision stage/exit/rollback fields and
DNS probe/RCODE/ID-match/Answer-count/expected-A/length/timing values. Unknown
Vision stages become `unknown`; raw logs, DNS names, packets, credentials and URLs
remain private. DNS parsing validates the expected Answer A record rather than
assuming it occupies the final four packet bytes. No retries or timeout increases
are added; failure remains failure.

## Verified upstream baseline and Canary

`verified_panel_release()` in `x-ui-latest.sh` is the single version/digest source for production and real integration. The default is 3x-ui v3.10.2 / bundled Xray 26.10.10. Archive pins cover every supported download architecture; full transport integration currently covers **amd64 only**, with additional QEMU ARMv5/v6/v7 CLI, X25519 and config-validation checks. A pinned checksum does not certify architecture-specific runtime behavior.

The installer bootstraps only release-preflight dependencies, then verifies the selected official archive, sidecar and pinned/API digest and validates its layout **before managed cleanup**. Installation consumes that same private archive. Explicit `-version <tag>` requires a published stable release >= v3.8.0 with verifiable assets, and warns when outside the baseline. A manual version choice is not an automatic promotion.

`upstream-canary.yml` runs daily or manually on free Ubuntu 24.04 runners; PRs changing Canary infrastructure also validate it as a non-required check. It runs the existing integration suite with the candidate's own official x-ui and bundled Xray, including native CLI/migration/SQLite persistence, actual RAW/JSON subscriptions, five transport positive/negative pairs and Mihomo. Its report records version, archive SHA-256, bundled Xray and failure diagnostics. It is **not a required PR check**, never writes the baseline, and has no repository-secret or VPS dependency.

A small Actions cache stores only the tested result, keyed by version, digest and test-implementation fingerprint. Unchanged daily candidates reuse the latest tested PASS/FAIL report; preparation/download failures are reported but not cached as tested; changed artifacts/code and every manual run retest. Each fresh result gets a unique cache key, so manual retesting supersedes previous results. Cache eviction causes a fresh run, not a skip. Reports/logs are retained as artifacts for 30 days.

For an explicit local candidate run (non-root, integration dependencies installed):

```bash
python3 tests/upstream_canary.py probe --directory /tmp/xui-canary --version v3.10.2
NGINX_BIN=/usr/sbin/nginx python3 tests/upstream_canary.py run --directory /tmp/xui-canary
python3 tests/upstream_canary.py report --directory /tmp/xui-canary
```

Promote upstream only in a separate reviewed PR: independently confirm all official archive pins, update the single baseline, run all five required checks, and record full installer/live acceptance. Canary **integration PASS is not full installer acceptance**: systemd lifecycle, public ACME/DNS, kernel UFW, reboot/recovery and non-amd64 behavior still require their own acceptance. Canary failures must be investigated, not hidden by changing assertions or silently substituting baseline binaries.

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

Only the owner publishes `vX.Y.Z` project releases, after independent audit, required checks and merge to `main`, with explicit authorization. Project versions are separate from upstream 3x-ui/Xray versions; `-version <tag>` selects the panel, not this project's assets. Release notes describe user-visible project changes and compatibility limits, not CI, README edits or internal repository tooling. A short release is preferable to presenting internal maintenance as a new installer capability.

The development `x-ui-latest.sh` keeps `PROJECT_REF="${XUI_AUTO_REF:-main}"`. Prepare the release asset from **committed content**, never by editing or copying the working-tree installer manually. `tools/prepare_release.py` checks an existing stable tag against an exact source commit, pins the asset's default to that 40-hex SHA, checks Bash/source initialization and writes a new output directory with `x-ui-latest.sh` and its SHA-256 sidecar. `XUI_AUTO_REF` remains an explicit override. All project-owned helpers follow the same selected tree; no fallback to main or mixed versions is permitted. An exact SHA is immutable even if a tag moves; dynamic Latest is only a download selector, never the source ref inside an asset.

Normal owner procedure after audit/merge — no local SHA selection, tag commands, Python invocation or manual asset upload is needed:

1. Open **Actions → Prepare Release → Run workflow**, select **main**, and enter the new stable project version, for example `v2.1.5`.
2. On success, open the **Draft Release** link in the job summary. The summary records the exact source SHA; the workflow has built and downloaded both attachments and verified their bytes, SHA-256, Bash syntax, tag and source-ref contract.
3. Write/review the user-facing release notes in GitHub and click **Publish release** as stable Latest. The workflow leaves notes empty and never publishes automatically.

`.github/workflows/prepare-release.yml` is manual-only, not a required PR check. It runs only for this repository's `main`, checks that the dispatched/checked-out SHA is still the current protected main commit, and rejects invalid versions and existing matching tags/releases before writing. GitHub lookup failures are failures, not evidence of absence. It uses the standard `GITHUB_TOKEN` with `contents: write` only for its preparation job; no PAT, extra secret, package installation or heavy acceptance is required. Owner approval, audit and full required acceptance precede dispatch; this lightweight job does not establish installer acceptance.

Preparation creates the tag, invokes the existing builder, attaches both files to a new Draft Release, downloads them for byte/checksum verification, and checks the final tag/release source metadata. It finds exactly one matching tag in the paginated release list and fetches the Draft by numeric Release ID; the tag lookup endpoint is not used for Draft verification. Concurrent preparations do not cancel a running preparation. Any error fails the job without publishing. A created tag or partial Draft may remain: a repeat deliberately refuses to overwrite it. Inspect/resolve those unpublished resources as the owner before trying again; never reuse or modify a published release/tag, including `personal-v*`. The local builder remains available for independent reproduction, not as a required manual release step.

The workflow becomes dispatchable from `main` after merge. Do not run it, create tags/releases, or publish during PR development without explicit owner permission. Review the successful summary before publishing; a failed job is not a prepared release.

Publish the prepared Draft Release only with the owner's authorization, as a stable Latest (not prerelease). The asset name is always **`x-ui-latest.sh`**. Verify all of the following before declaring the release available:

- GitHub's Latest API returns the intended stable tag and lists the installer asset with `download_count`.
- `https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh` downloads the exact built bytes/SHA-256 and source ref.
- `https://github.com/xPROMSx/3x-ui-auto-nginx/releases/download/v2.1.5/x-ui-latest.sh` serves that specific version; historical assets have not changed.
- The single Raw GitHub fallback from `main` is available. It is development source and is not promised to match the published release.

All seven READMEs recommend only the permanent GitHub Releases Latest command openly. Its published installer pins the exact release source SHA. The only fallback is `raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh`, hidden inside localized `<details>` with a short warning that main may differ from the latest release. Do not add CDN, version-pinned fallbacks or additional install methods. Future releases update Latest without README command edits. Do not add a download badge, telemetry or artificial downloads; a publication verification download checks integrity.

User-facing project releases may include a short companion-project footer linking to [Telegram Web Proxy Manager](https://github.com/xPROMSx/3x-ui-auto-nginx#telemt-web-manager); keep it secondary to the actual release changes.
