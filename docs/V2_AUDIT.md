# v2.0.0 — integrated features audit scope

Development branch: `feat/v2-integrated-features`.
Base `main`: `f91003391ba9748ec1fc7f18e98fa906767b8885`.

The PR and final execution report identify the exact HEAD, commits, changed files
and Actions runs. A green intermediate run does not certify a later HEAD.
Merge, release publication, repository settings and live VPS installation are
reserved for the owner. This document describes the implementation and test
boundaries; it is not an assertion that independent audit or live acceptance passed.

## 1. Installer sequence and results

All choices and release/domain preflights precede managed cleanup. Security also
runs its read-only compatibility preflight before cleanup and repeats it immediately
before applying changes. Base OS and DNS preparation now precede cleanup;
verified strict DNS must be usable before certificate issuance. Defaults:
Security + DoT Y, Vision N, AWG N, AGH N, initial client Y. EOF declines the new
options; an empty interactive answer applies the displayed default.

Core installation and mandatory health checks run first. Vision, AWG and AGH
follow; Security runs after certificate issuance, then the client API runs after
core readiness. A final core check precedes the Installation Result. Requested
option failure produces a nonzero exit even if the core remains healthy.

| Result | Meaning |
| --- | --- |
| `not_requested` | The new feature was declined; its configuration routine did not run. |
| `configured` | Configuration and the feature's effective readiness checks succeeded. |
| `failed_rolled_back` | Change failed and the checked previous state was restored, or preflight refused without modifying it. |
| `failed_unverified` | Success or rollback could not be verified; do not treat the option as ready. |

AGH retains its existing `installed` equivalent of configured. AWG retains its
existing `configured`/`failed` contract. Initial client failure retains an owned
incomplete record for administrator inspection after one bounded attach attempt;
it does not roll back the VPS or print a subscription URL.

## 2. VPS Security + strict system DoT

Production uses standard Fail2ban, unattended-upgrades, systemd timer drop-ins
and systemd-resolved. No SSH policy, timezone, cron, UFW, Ubuntu Pro, Livepatch or
personal provisioning is changed by this option. Existing core sysctl/firewall
behavior is retained.

Fail2ban reads `sshd -T` and active `ssh.socket` listeners. SSH jail values are
maxretry 5, findtime 1800, bantime 3600. Journald uses the native systemd backend;
the log backend requires an existing auth log. Effective SSH policy is compared
after configuration. Password/keyboard-interactive access triggers a warning;
Match contexts still require administrator review. No recidive jail is added.

APT adds the required distro security origin: Ubuntu's codename-security archive,
or Debian's Debian-Security/codename-security origin. Existing effective distro,
ESM and administrator origins remain permitted; they are neither cleared nor
replaced. Explicitly disabled periodic APT causes early refusal. An administrator
modified project APT drop-in also causes early refusal; both previous and current
canonical project drop-ins remain supported. The managed drop-in enables automatic
reboot, including logged-in users, at 04:38. Native timers run at 02:30 (lists)
and 02:50 (unattended upgrade), using the displayed local system timezone.
Updates outside APT, including 3x-ui/Xray/containers, are not scheduled.

Strict resolved policy uses four named Cloudflare/Google TLS endpoints, empty
fallbacks, global `~.`, DNSOverTLS=yes, DNSSEC=no, no LLMNR/mDNS, caching and the
stub listener. Effective D-Bus mode, TLS server names, interface routes, uncached
queries and libc resolution must pass. Named TLS endpoints use the system CA
store. Port 853 is outbound only.

Read-only DNS preflight accepts an active systemd-resolved with its standard
stub/uplink symlink, or a narrowly recognized minimal image: no installed/active
resolved, a root-owned non-writable regular resolv.conf containing only the four
public Cloudflare/Google nameservers, no generated/provider ownership notice,
search/options, competing DNS/network manager, local DNS listener or explicit
interface/cloud/VPN DNS policy. It is not proof of ownership of arbitrary provider
files. Unknown configurations fail safely before cleanup; network interfaces are
never rewritten. After taking a private snapshot, preparation installs the real
resolved package, applies strict DoT, checks effective routes/TLS and libc DNS,
then repeats the readiness preflight. Failure restores the original file/link
and service active/enable state and verifies libc resolution. The original
resolver snapshot remains in a root-private checkpoint inside the current
release stage until Security finishes. A late Security failure or fatal installer
exit before that point restores the original pre-preparation DNS, not the new DoT
baseline. Only the two DNS paths and resolver state are accepted by checkpoint
loading; modified/unowned current DNS is never overwritten. Unverified rollback
retains the private stage for root inspection; successful finalization removes it.
A newly installed package remains installed but inactive/disabled; retry of such a residual state
requires administrator review rather than assuming ownership. AGH's DoH
upstreams are not rewritten or used as the system resolver.

Initial preparation is mandatory even with Security=N: error-checked APT update,
no-remove upgrade simulation, `apt-get --no-remove -y dist-upgrade`, dependency
installation and SSH/tool/libc DNS readiness checks, all before cleanup. APT waits
for dpkg locks and retries the lists lock with a bounded deadline; noninteractive
dpkg/UCF preserve existing configuration, and needrestart reports pending restarts.
APT origins are not changed by the initial upgrade. Existing-deployment confirmation
explicitly covers possible service restarts and the non-rollbackable OS upgrade.
Package maintainer scripts can still restart services; package installation and
dist-upgrade are not transactional and are not claimed to be rolled back.

A reboot-required flag schedules reboot one minute after a successful final
report, never after a failed installation. Failure to schedule returns nonzero;
post-reboot acceptance remains pending. The Security=N path leaves DNS and the
unattended reboot policy unchanged, but initial full upgrade and its required
reboot still apply. Timezone, SSH policy/keys and existing firewall rules remain
unchanged by preparation; missing UFW is installed without activating it here.

Project-owned drop-ins:

- `/etc/fail2ban/jail.d/90-3x-ui-auto-nginx.local`
- `/etc/apt/apt.conf.d/99zz-3x-ui-auto-nginx`
- `/etc/systemd/system/apt-daily.timer.d/90-3x-ui-auto-nginx.conf`
- `/etc/systemd/system/apt-daily-upgrade.timer.d/90-3x-ui-auto-nginx.conf`
- `/etc/systemd/resolved.conf.d/90-3x-ui-auto-nginx.conf`

Existing managed files must have the project marker and safe root ownership.
Administrator SSH/DEFAULT Fail2ban overrides cause refusal; unmodified package
`.conf` defaults are identified using dpkg conffile checksums. A private snapshot
restores file contents/permissions, resolv.conf link and prior enabled/active
service state on failure. Packages installed during the attempt may remain;
rollback does not uninstall shared package dependencies.

None of these host-specific drop-ins or resolv.conf/service snapshots is
automatically transported by portable Backup v3. On a different VPS the option
must be evaluated against that host's own DNS/SSH/package environment.

## 3. Separate RAW TLS Vision

Public TCP/443 remains owned by nginx stream. Existing REALITY and panel SNI
routes remain; Vision adds a third SNI upstream to a distinct loopback listener.
UDP/443 Hysteria2 is untouched. No Vision or DoT UFW allow rule is added.

The official panel v3.9.0 gates Vision flow on `network=tcp`. Xray 26.9.30 maps
tcp/raw to RAW and accepts `rawSettings.acceptProxyProtocol=true`. The new native
VLESS inbound uses TLS, ALPN http/1.1, a separate domain certificate and native
Host metadata for public port 443, SNI and certificate verification.

Xray terminates TLS and sends decrypted fallback HTTP to explicit
127.0.0.1 on another internal port, with xver=1. Its separate nginx site accepts
PROXY only from loopback, checks Host and serves static `/var/www/html` content.
It contains no proxy to panel, subscriptions, DoH or administrative services.

The third certificate uses existing Certbot webroot and distro certbot.timer.
The separate canonical Vision deploy hook validates the renewed identity/key,
restarts x-ui only for that exact lineage and verifies HTTPS fallback. Xray's
native file polling is hourly, so the restart ensures immediate use. Unrelated
lineages do not trigger this hook's restart. Existing core hook is unchanged.

The API creates an empty inbound and native Host, then nginx is validated and
reloaded. Failure restores the original stream, reconciles uncertain API state
before deleting an exactly owned empty inbound, removes only new artifacts and
checks core readiness. An ambiguous/modified record is retained with an
unverified status. Reinstallation recognizes owned files and canonical hooks;
foreign artifacts cause refusal before cleanup. Existing Vision nginx files must
match the canonical generators exactly, including the dynamic domain and loopback
port, with root ownership and mode 0644. Reusing an existing Vision lineage requires
the canonical deploy-hook, matching nginx domain/configuration and valid webroot
renewal configuration; a matching certificate name alone is insufficient.

Initial configuration restarts Xray through the native API, preserving the
administrator session for rollback. If rollback is unverified, the new
certificate and renewal artifacts remain for inspection rather than breaking
an inbound that might still reference them. Subscription routes suppress nginx
access/error logging, including internal redirects. Missing subscriptions retain
404; upstream 500/503 and nginx-generated 502 remain errors of the same class, so subscription
identifiers do not enter shared logs. Initial client creation is deferred if
Vision rollback remains unverified: a retained inbound might lack its SNI route.

Portable Backup v3 includes Vision DB/Host, SNI, static fallback, ACME site,
canonical hook and third lineage when declared. Archives without the new
declaration retain the two-lineage contract. A declared Vision archive missing
its mandatory certificate fails before replacement. Existing certificate path,
SAN/key, webroot and nginx validations remain. Foreign target Certbot lineages,
options and hooks are preserved rather than replacing the entire tree.
Restore imports only declared project live/archive/renewal PEM state and verified
project hooks. Foreign archived lineages, hooks, cli.ini and unrelated accounts
are ignored. Only meta.json, private_key.json and regr.json for accounts explicitly
referenced by managed renewal configurations are imported. Account paths/JSON
are validated; conflicting target account data and symlinks cause early refusal.
Actual Certbot/Pebble renewal after this selective Restore is tested; directory
hooks are disabled for that isolated renewal, with hook execution covered separately.
Before stopping services, Restore rejects foreign/corrupt project-named hooks
and existing same-name certificate lineages without canonical project ownership.
It does not guess that an administrator's artifact belongs to this project.

The real Mihomo Vision transfer waits for the official file provider to load and
explicitly selects its VLESS profile through the local controller. A DIRECT
option is present in that test as a guard: direct traffic cannot satisfy it.

## 4. Native client and subscription

The helper reuses the existing local verified HTTPS Panel session, login and
CSRF token mechanism. Credentials enter via stdin; cookies and CSRF headers are
temporary private files. No long-lived API token, direct client SQL write,
settings.clients editing or custom production link exporter is introduced.

POST `/panel/api/clients/add` receives one random client identity and the actual
supported enabled local inbound IDs. The native panel generates UUID/password/
Hysteria credentials/AWG keys and tunnel address. The 16-character lowercase
alphanumeric subId and client name are checked against existing clients.
Traffic/expiry/IP/HWID limits are zero and the client is enabled.

After an uncertain POST the helper reads actual state rather than blindly
creating another client. It checks exact attachment IDs, performs at most one
attach of missing IDs, re-reads credentials/flow and compares official links to
the real raw subscription. REALITY/RAW TLS receive Vision flow; XHTTP receives
no flow. AWG keys and unique addresses are checked separately. Native JSON must
also be nonempty when enabled. REALITY shortIds are checked against the actual
allowed set because upstream selects one randomly for each export.

The root:600 `/etc/x-ui/initial-client.json` marker reserves identity before the
POST and records the successful native record ID. A retry validates that identity
instead of creating duplicates. This is a private client/subscription identifier,
not an API token; it travels with the private database backup. Existing foreign
clients are never deleted. Session temporary directories are removed on exit.

The verified native subURI on the panel HTTPS origin plus actual subId is printed
only in the terminal result. `vpn://` is the official separate AWG export and
requires an Amnezia-compatible application; VLESS subscription importers are not
promised to support it.

## 5. Upstream contracts

- [3x-ui v3.9.0 client controller](https://github.com/MHSanaei/3x-ui/blob/v3.9.0/internal/web/controller/client.go)
- [Native client CRUD](https://github.com/MHSanaei/3x-ui/blob/v3.9.0/internal/web/service/client_crud.go)
- [Session CSRF](https://github.com/MHSanaei/3x-ui/blob/v3.9.0/internal/web/session/csrf.go)
- [Xray 26.9.30 RAW/TCP configuration](https://github.com/XTLS/Xray-core/blob/v26.9.30/infra/conf/transport_internet.go)
- [Native TLS loading](https://github.com/XTLS/Xray-core/blob/v26.9.30/transport/internet/tls/config.go)
- [Reviewed DoT reference](https://github.com/xPROMSx/ubuntu-vps-tools/blob/main/vps-bootstrap-ubuntu24.sh)

Vision/client API features require v3.9.0 and refuse incompatible versions before
managed cleanup. Selecting N preserves existing explicit stable `-version`
behavior. The baseline release/Xray pins and checksum verification are unchanged.

## 6. Validation and limits

Existing required check names stay unchanged. `stack-xhttp.yml` runs syntax,
ShellCheck errors, actionlint, completeness, nonroot and real integration;
`stack-backup.yml` runs root fixtures; `stack-services.yml` runs native Ubuntu
service jobs, native Debian 13 Vision/API/AWG containers and three isolated
systemd guests. `upstream-canary.yml` consumes
the same integration test and fingerprints the new API helpers to avoid stale
cached results. No new test framework or paid infrastructure is introduced.

The required six option combinations are lifecycle/failure fixtures, not six
complete external VPS deployments. Network transport/API/Mihomo, Certbot/Pebble,
AGH and systemd/DoT checks execute real components in their respective suites.
The systemd guest also runs checksum-verified AGH against a trusted local HTTPS
DNS upstream while system queries use strict DoT. It checks that the two query
paths remain separate and refuses an actual per-interface route into local AGH.
Private Restore exercises real files/certificates and AGH, while core service
management remains fixtures. These boundaries must accompany reported PASS.

Live acceptance remains necessary for public A/AAAA, Let's Encrypt, the actual
provider/VPN DNS environment, cloud firewall, each distro kernel, a complete
same-host/new-host recovery and full VPS reboot acceptance. The systemd matrix
starts without resolved/resolvectl/UFW and with regular Google resolv.conf. It
uses real APT with a local repository containing distro resolved/UFW packages
and tiny upgrade/retention fixtures: upgrade changes the fixture version, retains
the unrelated package and sets reboot-required. It exercises real TLS DNS failure,
original plain DNS rollback, strict TLS preparation, socket/service SSH, and
systemd shutdown scheduling. A second real kernel/systemd cold boot checks the
persisted APT policy, administrator origins and enabled/active local-time timers.
Only the tested policy is transferred to this second disposable boot; this is not
an end-to-end reboot of a full installed stack. The CI host is never upgraded.
Functional integration covers amd64;
archive checksum pins do not certify every architecture. No claim of a live
installation, merge or release follows from CI success.

The owner performs the single clean Ubuntu 26.04 full-option VPS acceptance only
after complete CI and independent audit, then decides merge and v2.0.0 publication.

Before merge, use the exact audited commit for both installer and assets:

```bash
candidate_sha='<exact HEAD from the final report>'
curl -fSL "https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/$candidate_sha/x-ui-latest.sh" -o x-ui-latest.sh
XUI_AUTO_REF="$candidate_sha" bash x-ui-latest.sh
```

Choose all five options on the disposable VPS. Using main's assets with a
pre-merge candidate would mix implementations and is not acceptance of that HEAD.
