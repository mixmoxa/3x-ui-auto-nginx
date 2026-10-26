# Installer menu and Backup management

Download the installer to a file using the README command, then run it from an
interactive terminal. Remote sessions need a TTY (`ssh -t`). The menu is English:
**1 Installation**, **3 Backups**, **0 Exit**. Opening it, Back and Exit need no
root access and perform no downloads, IP lookups or system preparation.

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
OS/version/architecture and recovery contracts; additional security configuration
and domain changes are not part of this menu.

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

## Operation locking

Installation, rebuild, uninstall and the updated standalone Backup/Restore and
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
