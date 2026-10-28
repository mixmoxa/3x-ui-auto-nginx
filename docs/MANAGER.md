<a id="installer-menu-and-backup-management"></a>

# Installer menu, domain changes and Backup management

Download the installer to a file using the README command, then run it from an
interactive terminal. Remote sessions need a TTY (`ssh -t`). The menu is English:
**1 Installation**, **2 Change Domains**, **3 Backups**, **0 Exit**. With no
unfinished domain operation, opening it, Back and Exit need no root access and
perform no downloads, IP lookups or system preparation. An unfinished domain
journal instead requires root and verified recovery before another menu action.

Installation is the existing destructive fresh install/rebuild, with the same
`YES` confirmation for an existing deployment. Existing explicit installation and
uninstall arguments run directly. Without arguments and without an interactive
stdin/stdout TTY, the script refuses to install. Do not pipe the script into Bash;
download it to a file so prompts keep their terminal input.

Backups offers Create, List and Restore. Create reports the exact archive made by
that operation. Listing shows UTC file dates and byte sizes, without opening each
archive. A listed filename is not evidence of integrity or trusted provenance.
Restore accepts a list number or absolute path, shows archive metadata and asks
for `YES` before replacing managed data. Restore keeps the existing Backup v3
OS/version/architecture and recovery contracts.

Restore offers two independent options, both **No** by default:

- **Automatic security updates + SSH Fail2ban**: one combined choice, using the
  existing Security helper without system DoT or initial installation. The policy
  permits automatic reboot at **04:38 server time, including with active users**;
  the menu warns before asking for consent.
- **UFW with SSH protection**: after Restore has added project rules, preserve an
  already active UFW without changing it, or enable inactive UFW only on a simple
  supported Ubuntu 24.04/26.04 configuration. It validates sshd, standard
  `ssh.service`/`ssh.socket`, actual listeners and owners, packaged UFW defaults,
  simple project/SSH allows and absence of other kernel firewall rules. It allows
  the confirmed SSH TCP ports before enabling UFW and verifies effective rules.
  Nonstandard SSH ports and socket activation are supported. Custom before/after
  files, policies, DENY/route/application rules, another firewall manager or
  ambiguous listeners cause refusal; rules are never deleted or reordered.
  The distro `nftables` inspection tool is installed if missing.

When either option is selected, the manager pins its exact source revision and
prepares the matching helper **before** Restore, in a private root-owned 0700
temporary directory under `/run`, outside restored trees. It runs Python in
isolated mode and never executes a helper from the archive or reloads mutable
`main` afterwards. If preparation fails, explicitly choose ordinary Restore
without Security or cancel.

Security starts only after the foreground Restore process has completely exited,
including EXIT cleanup, with status 0. The existing operation lock remains held
through all requested actions. Results show Restore, APT, Fail2ban, UFW and
Overall separately. Security failure returns nonzero with `Overall: PARTIAL`
while retaining successfully restored data; it does not trigger Restore rollback.
Installed package changes are not rolled back. A possibly enabled but unverified
firewall is reported `FAILED_UNVERIFIED`; check `ufw status verbose` and establish
a new external SSH connection before relying on access. Interruption can leave
Security state unverified and does not promise rollback.

The standalone `x-ui-backup restore` keeps its existing contract and does not run
these optional actions. Backup v3 layout/metadata remain unchanged. Restore
accepts the native AmneziaWG empty `stream_settings` without rewriting that value;
an expected active panel must own its saved localhost web listener. Saved stopped
panel state is preserved.

The standalone CLI remains available:

```bash
sudo x-ui-backup backup
sudo x-ui-backup backup --json
sudo x-ui-backup inspect /path/to/archive.tar.gz
sudo x-ui-backup restore /path/to/archive.tar.gz
sudo x-ui-backup list
```

`inspect` validates the existing archive contract without extraction, APT or
service changes. It prints JSON containing only format, OS/version/architecture,
creation date, panel/Xray versions, AGH presence and any saved service states.
Control characters are escaped. Missing Python 3/gzip produces an error without
installing packages. Validation does not authenticate who created the archive.

`backup --json` keeps progress on stderr and writes one successful result to
stdout: `{"status":"success","archive":"/exact/archive/path"}`. A result-output
failure returns nonzero and retains the already verified archive. Default Backup
output remains human readable. Backups contain secrets; keep an off-host copy.

The menu reuses a trusted root-owned compatible installed utility offline. For an
older utility it prepares and validates a replacement before atomic installation;
failed download/replacement preserves the previous utility. The selected project
source is pinned before downloading code, with no fallback to a different tree.
Mutable main/tag downloads must match the running script (allowing only the
published asset's source-default substitution), otherwise preparation stops.

## Change Domains

Run the current manager from a file through an SSH TTY as root, select **2**, and
choose Panel, REALITY or both. The submenu shows current domains. Review the old
and new names and type the exact uppercase **YES**. Existing installation flags
continue to select Installation directly; Change Domains does not reinstall or
update 3x-ui.

Point all new A/AAAA records to this VPS and keep TCP/80 reachable for Let's
Encrypt HTTP-01. Domains must remain distinct from each other and Vision.
Neither new domain may take the other role's current name. Unknown DNS identity,
foreign/ambiguous lineages, certificate or SNI overrides, custom SQLite storage,
unknown service/layout or contradictory manifest cause refusal before switching.
Known local SQLite layouts are 3x-ui **v3.10.2/v3.11.0** on the supported OSes.

A consistent `/etc/x-ui/auto-nginx-managed.json` is checked against the real
inbounds, Hosts, nginx, certificates and optional components. A missing manifest
is supported for an unambiguously recognized v2.1.7 project layout: standard
paths, separate loopback Panel/REALITY TLS, exact project hook and stream map,
matching five transport roles/Hosts and optional routes. Names/tags alone are
not ownership evidence. No reinstall is needed to obtain a manifest; a successful
legacy switch records `installed_by=legacy-v2.1.7-layout`. Other layouts/versions
are deliberately refused rather than guessed.

The official archives retain UID/GID `1001:1001` on the panel directory/binary.
That exact 0755 metadata is recognized only while UID 1001 has no account and no
active process on the host. Ownership is preserved. An assigned/active identity
or another non-root owner is refused before Backup or changes.

Before the first stack change, the selected tree's existing Backup v3 creates a
full verified archive in `/var/backups/x-ui`. An old installed Backup utility is
not replaced: a private current copy performs this archive under the inherited
lock. New certificates are obtained with the existing webroot/account while old
HTTP-01 routes stay available. The complete candidate nginx include tree is
tested before the short x-ui stop and compare-and-set SQLite updates.

Panel changes update its public endpoints, TLS paths, managed Hosts (including
the REALITY connection address), WS/gRPC/Hysteria2 metadata, AWG share address,
Clash template, Diagnostics and optional AGH metadata. REALITY-only changes update
its SNI/TLS vhost and `serverNames`; Panel/Hosts/subscription/AGH endpoints stay
unchanged. Both changes share one Backup and recovery snapshot. IDs, client
secrets/bindings, traffic, REALITY keys/shortIds/target, user settings and Vision
are preserved. Existing paths are retained. Clients and old subscription URLs
may need updating; an old domain is not guaranteed to work after its DNS is
removed. Old certificates/lineages are never deleted by this operation.

The root-only 0700 directory
`/var/lib/3x-ui-auto-nginx/change-domains` holds a private 0600 data journal with
atomic, fsynced `prepared`, `switching`, `committed` phases and snapshots of only
affected resources. Preparation/switch failures restore and verify the original
configuration. `ROLLBACK_UNVERIFIED` means recovery could not be proved: retain
this directory and the reported full Backup; do not delete the journal or run
Installation to bypass it. Start the manager again through SSH. It checks and
recovers an unfinished operation before new changes; conflicting independent
edits stop recovery. Backup `inspect`/`list` remain available, while modifying
Backup/Restore commands stop until manager recovery completes. No boot service
or daemon is installed. A healthy `committed` state is retained on optional
cleanup failure and is never rolled back for that reason. Prepared new lineages
may remain after a failed operation; inspect dependencies before owner cleanup.

Private fixture fault/SIGKILL tests do not certify every power-loss/provider
scenario. Existing Full Fresh additionally exercises P/R/Both on one installed
systemd guest with real Backup, Pebble, nginx, 3x-ui/Xray and consumers. Public
DNS/Let's Encrypt and a live VPS acceptance remain separate owner actions.

## Operation locking

Installation, rebuild, uninstall, Change Domains and the updated standalone Backup/Restore and
`update-hooks` share a nonblocking `flock`. Contention returns **75** before stack
changes. `/run/3x-ui-auto-nginx` is root-owned 0700; its regular 0600
`operation.lock` is never deleted to release a lock and lies outside Restore trees.

Protocol 1 uses inherited descriptor **9**. A child validates its inode against
the private lock file and takes `flock` on the same open-file description. An
independent session opens a different description and cannot acquire a held lock.
There is no skip-lock flag or environment override. Foreground children retain
ownership through operation cleanup/rollback; the kernel releases it when the
last owning descriptor closes. Do not pass descriptor 9 to unrelated daemons.
Systemd-started services are launched by the service manager, not as shell children.

Helper preparation checks both capabilities and actual contention through
`lock-check`. Identifiable already-running historical Backup/Restore/update-hooks
script processes cause refusal; they are never killed. Advisory locking cannot
retroactively coordinate old or third-party processes that do not use the
protocol, including unidentifiable copies or processes started after the scan.
Let existing maintenance finish and use the updated utility in other sessions.

On success the menu allows another action. On an operation failure it reports the
original exit code and exits, allowing inspection of the reported recovery state
before further changes. Exit/EOF without an operation, or after success, returns 0.
Direct operation calls preserve their error status. Ctrl-C uses normal shell
signal handling; it does not start another menu action.

The lightweight real Restore acceptance reuses the existing networked QEMU/SSH
stand; it creates one minimal source installation and real Backup v3, restores to
a clean target of the same Ubuntu version, configures Security, opens a new SSH
connection from outside the VM (including socket port 2222), and checks a cold
boot. Run each version once from a committed, remotely available exact HEAD:

```bash
XUI_RESTORE_ACCEPTANCE=1 XUI_TEST_DISTRO=ubuntu:24.04 bash tests/fresh/run.sh
XUI_RESTORE_ACCEPTANCE=1 XUI_TEST_DISTRO=ubuntu:26.04 bash tests/fresh/run.sh
```

This opt-in mode does not change the ordinary CI jobs or the default full fresh
installer acceptance. It selects no Vision, AWG, AGH or client/Mihomo integration.
Private archives, database digests, keys and logs stay in the disposable stand and
are removed by its existing cleanup; only fixed check results are public.

## Installed description

After a healthy fresh installation, `/etc/x-ui/auto-nginx-managed.json` describes
the actual domain roles, inbound IDs and successfully configured optional
components. It contains no credentials and is atomically written root:root 0600.
`installed_by=source@<SHA>` records source provenance without claiming an
unpublished project release. `source_ref` is the exact revision used for assets.
Marker failure makes installation nonzero while retaining installed core data.

This description is included in Backup v3 under `/etc/x-ui`; older v3 archives
without it remain valid. It is descriptive metadata, not proof of ownership and
not permission to modify a restored installation without checking actual state.
