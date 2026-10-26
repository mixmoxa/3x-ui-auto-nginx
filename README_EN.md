<div align="center">

[🇷🇺 Русский](README.md) · 🇬🇧 **English** · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Automated deployment of 3X-UI / XRAY-CORE on your own VPS

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

Two domains, a clean VPS, and a few minutes to install.

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT.en.md)

[📦 Releases](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ Support](#support-development) · [🐛 Report an issue](https://github.com/xPROMSx/3x-ui-auto-nginx/issues) · [💬 Feedback](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX** installs [3x-ui](https://github.com/MHSanaei/3x-ui) and Xray with nginx, HTTPS, connection profiles, subscriptions, diagnostics, and Backup / Restore. AmneziaWG 3.1 and AdGuard Home with DoH are optional.

Bring two domains and a clean VPS. A cover website is selected and deployed automatically.

## ✨ Why this project

| | |
| --- | --- |
| **Preconfigured connections**<br>REALITY, XHTTP, Hysteria2, Amnezia WG, VLESS XTLS Vision, WebSocket TLS, and Trojan gRPC. | **Private internal services**<br>The panel and subscription service don't expose their internal ports to the internet. |
| **Restricted nginx routing**<br>Requests cannot be forwarded to arbitrary local ports. | **Backup / Restore v3**<br>Roll back your VPS or restore to a new server, including one from another hosting provider. |
| **Automatic certificates**<br>Let's Encrypt issuance and renewal need no manual configuration. | **AdGuard Home + DoH**<br>Opt in during setup; no third domain needed. |

<a id="installation"></a>

## 🚀 Quick start

Configure the DNS records for **two domains** to point to your VPS IP address: one for the panel, one for REALITY. Connect via SSH as **root** and allow TCP **80/443**, UDP **443**. [Supported systems](#technical-details).

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

The current stable release v2.1.7 starts installation directly. After v2.2.0 is published, the command above will open the menu: **1 — Installation**, **3 — Backups**, **0 — Exit**. Allocate a TTY with `ssh -t` for the menu; without a TTY, use explicit installation flags. [Menu and Backup CLI](docs/MANAGER.md).

<details>
<summary><strong>Fallback download — if GitHub Releases is unavailable</strong></summary>

Install directly from the current `main` branch. Its contents may differ from the latest published release.

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

</details>

<a id="installation-vs-update"></a>

> [!CAUTION]
> **Installation ≠ update**
>
> **3X-UI AUTO NGINX** is intended for initial installation on a clean VPS or a complete reinstall.
>
> Rerunning the script on an already configured server **does not update the existing installation** — it reinstalls the stack, removing the previous 3X-UI database and nginx configuration.

<details>
<summary><strong>How do I update?</strong></summary>

- **3X-UI and Xray:** use 3X-UI's built-in update tools.
- **3X-UI AUTO NGINX:** in-place updates of the installed stack are not supported. Changes in new releases only take effect after a fresh installation or complete reinstall.
- **Backup / Restore:** is for saving and restoring data, not for updating the project.

**Do not rerun the installer just to update!** To keep your VPS secure, regularly update nginx, the Linux kernel, and other system components using your operating system's package manager.

</details>


Once started, the installer walks you through the following steps. The prompts below are shown exactly as they appear in the terminal:

---

### 1. 🌐 3X-UI panel domain

> `Enter the domain for your 3X-UI panel:`

Enter the domain used for the administration panel, subscriptions, and additional web services.

---

### 2. 🛰️ VLESS REALITY domain

> `Enter the domain for VLESS REALITY:`

Enter a second domain for REALITY. Both domains must point to your VPS IP address.

<details>
<summary>ℹ️ Additional startup parameters</summary>

You can supply both domains on the command line instead of entering them interactively:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

Replace `panel.example.com` and `reality.example.com` with your own domains. Optional features are still selected interactively.

</details>

---

### 3. 🔐 Enhanced VPS security

> `Enhance VPS security? [Y/n]:`

*Recommended for less experienced users · Enabled by default (`Y`)*

The installer automatically configures additional server protection: Fail2ban against SSH password brute-force attacks, encrypted system DNS (DoT), automatic security updates for the system and packages, and a 1 GiB swap file to improve resilience when memory runs low.

**Read the settings below before enabling this option**, particularly the automatic reboot schedule.

<details>
<summary>🔐 Detailed security settings</summary>

Choosing `Y` enables:

- **1 GiB swap.** If no swap is active, the filesystem is supported and at least 4 GiB is free, the installer creates and enables a swap file. Existing swap settings remain unchanged. If these conditions are not met, this step is skipped without stopping installation.
- **SSH protection — Fail2ban.** Limits repeated unsuccessful logins using the actual SSH ports. Existing SSH authentication settings are not changed.
- **Encrypted DNS (DoT).** Global Cloudflare and Google resolvers use strict DNS-over-TLS through `systemd-resolved`. Interface/VPN DNS routes and search domains are preserved; their queries may remain unencrypted. If DoT preparation fails and the original DNS is successfully restored, core, Fail2ban and automatic update installation continues independently of DoT; the final result reports the failure and exits nonzero.
- **Automatic security updates.** Package lists are updated at 02:30, with security updates installed at 02:50.
- **Automatic reboot — 04:38.** If updates require a reboot, it occurs at the scheduled time, **even when users are connected**. This may interrupt active connections.

Times are in the VPS's local time zone.

Existing settings are checked for compatibility before changes. If security configuration fails, a controlled rollback is provided.

**Important:** This does not disable SSH password login or replace proper server administration. Configure SSH key access first, then disable password authentication yourself.

</details>

---

### 4. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*Additional connection · Disabled by default (`N`)*

An alternative VLESS connection over TLS that may help when REALITY is unstable or blocked on your network. It is created as a separate profile in 3X-UI.

> [!IMPORTANT]
> **XTLS Vision requires a third domain**, distinct from the panel and REALITY domains. Its DNS record must point to your VPS IP. HTTPS certificates and nginx routing are configured automatically.
>
> After you choose `Y`, the installer asks for this domain: `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

### 5. 🔑 Amnezia WG

> `Set up an additional AmneziaWG connection? [y/N]:`

*Additional connection · Disabled by default (`N`)*

A separate AmneziaWG connection is created in the 3X-UI panel. No additional domain is required.

<details>
<summary>ℹ️ About Amnezia WG</summary>

The installer configures AmneziaWG 3.1 on **UDP/8443** and automatically allows the required UFW rule.

After installation, create a client in the 3X-UI panel to obtain a configuration or a `vpn://` link for a compatible Amnezia app.

The installer creates the server connection but does not automatically generate AmneziaWG clients.

The configuration and necessary firewall rule are included in **Backup / Restore v3**.

</details>

---

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS

> `Install and configure AdGuard Home? [y/N]:`

*Optional DNS server · Disabled by default (`N`)*

A personal DNS server for blocking ads and trackers, managing clients, and making encrypted DNS requests.

<details>
<summary>ℹ️ About AdGuard Home and access control</summary>

No additional domain is needed.

After installation, the following are available:

- **AdGuard Home admin panel:** `https://panel.example.com/adg-.../` — a unique random path.
- **DNS-over-HTTPS:** `https://panel.example.com/dns-query`.

Public TCP/UDP port **53** is not opened. The AdGuard Home configuration and data are included in **Backup / Restore v3**.

**⚠️ Security recommendation**

For a personal VPS, create a separate [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) for each device.

In AdGuard Home, go to **Settings → DNS settings → Access settings → Allowed clients** and enter **only those ClientIDs**, not IP addresses or subnets.

Use DoH URLs such as:

`https://panel.example.com/dns-query/<ClientID>`

Once configured, requests without an allowed ClientID, including requests to `/dns-query`, are rejected.

Choose long, random identifiers. See the [official AdGuard Home security guidance](https://adguard-dns.io/kb/adguard-home/running-securely/).

</details>

---

### 7. 👤 Automatic client and subscription

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*Recommended · Enabled by default (`Y`)*

The installer creates a 3X-UI client and generates a personal HTTPS subscription URL for the configured, supported connections.

The link appears in the final installation report. If you decline, you can create clients manually through the panel.

---

> [!CAUTION]
> **Clean install or full reinstall only.** `x-ui-latest.sh` removes the previous 3x-ui database and nginx configuration — **it is not an update command for an existing VPS**. Keep a Backup off-server before reinstalling. Reinstalling or uninstalling a detected deployment requires typing exactly `YES` in uppercase.

The installation report displays the **panel URL, username and password, diagnostics address, and subscription link** (if you chose to create a client). For AdGuard Home, it also includes the admin address, password, and DoH endpoint.

If an OS update requires a reboot, the installer will notify you. **The initial reboot is manual**: run `sudo reboot`.

## 🚀 Connection profiles

| Connection | Status |
| --- | :---: |
| VLESS + REALITY | ✅ Ready to use |
| VLESS + XHTTP | ✅ Ready to use |
| Hysteria2 | ✅ Ready to use |
| VLESS + WebSocket (TLS) | ✅ Ready to use |
| Trojan + gRPC | ✅ Ready to use |
| VLESS + XTLS Vision | ✅ Optional |
| Amnezia WG | ✅ Optional |

Five standard profiles are configured: REALITY, XHTTP, and Hysteria2 are enabled immediately, while WebSocket and Trojan gRPC can be enabled in 3X-UI as needed.

XTLS Vision and Amnezia WG are added only when selected during setup. **You need to create clients** to use the connections, automatically during installation or manually in the panel. Amnezia WG clients are created separately.

Compatibility depends on your client app and its version.

### Subscriptions

Standard subscriptions, JSON, and **Mihomo / Clash** are served via nginx and HTTPS. `provider=1` returns the original subscription for proxy providers rather than a complete Clash configuration.


## 💾 Backup / Restore

Backup / Restore **v3** lets you roll back your VPS or recover a compatible server after an OS reinstall. The utility is installed with the server; run as root:

```bash
# Create a new backup
x-ui-backup backup

# List available backups
x-ui-backup list

# Restore a selected backup
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

Archives are saved in `/var/backups/x-ui/`.

> **Backups contain sensitive data:** the client database, passwords, and certificate private keys. Keep a copy **off the VPS** and restore only trusted archives.

If Restore is unavailable, extract the files for manual recovery without installing packages or running services. Only Bash, Python 3, and access to the archive and destination are needed; root is not required:

```bash
x-ui-backup extract /path/to/archive.tar.gz ./recovered-backup
```

The destination must be new; original paths are preserved under `files/` and links are skipped. The data contains secrets: review it before copying anything over a running server.

[Recovery on a new VPS](#restore-on-new-vps).

## 🔐 Security

Service interfaces are not exposed directly to the internet. The panel, subscriptions, and additional services are accessible through nginx and HTTPS, while internal ports remain local.

There is no generic proxy to arbitrary localhost ports. Critical errors stop installation or restore rather than starting an incomplete configuration.


**Not sure how to secure your VPS?** Enable enhanced security during installation to configure protection against SSH brute-force attempts, encrypted DNS, and automatic security updates. Read the detailed settings and the scheduled nighttime reboot policy in **Quick start** first.

**Important:** Secure access to the server itself. Use SSH keys, verify key-based login works, and only then disable password authentication. The installer does not disable it automatically.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[A companion project](https://github.com/xPROMSx/telegram-web-proxy-manager) for your own Telegram WEB Proxy: HTTPS, a cover site, and updates with rollback.

The projects are independent; **this installer does not install Telegram Web Proxy Manager**.

<a id="technical-details"></a>

## ⚙️ Technical details and compatibility

- **Systems:** Ubuntu 24.04, Ubuntu 26.04, and Debian 13.
- **UFW:** allows 80/tcp, 443/tcp, and 443/udp (8443/udp optionally, when AmneziaWG is selected). Inactive UFW is enabled only after the SSH port is detected and allowed; otherwise it remains inactive with a warning. **⚠️ Restore never enables UFW.**
- **Certificates:** Let's Encrypt webroot and `certbot.timer` renew certificates automatically without stopping nginx.
- **3x-ui version:** by default, the installer uses the latest version thoroughly tested for compatibility with 3X-UI AUTO NGINX, which may not be the latest upstream release. After installation, you can update 3x-ui using its built-in update mechanism, but the new version may not yet be verified against this configuration. You can also explicitly select another stable release with `-version <tag>` (minimum supported version: v3.8.0); the installer will warn that compatibility has not been verified.

<a id="restore-on-new-vps"></a>

### Recovery on a new VPS

Match the backup's OS, OS version, and architecture. If the VPS IP address changes, update the DNS records for your domains. Do not run `x-ui-latest.sh` — install only the utility, then restore a trusted archive:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

SSH, OS configuration, and the base firewall remain the administrator's responsibility. For v2 archives, use the utility from the matching older release.

## 🤝 Credits / Origins

Based on [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro), this project is maintained independently. Since the fork, nginx/SNI routing and XHTTP configuration have been substantially reworked, TLS certificate issuance and automatic renewal redesigned, and Backup / Restore v3 introduced with recovery and rollback capabilities. Hysteria2 on UDP/443 was added, and identified security issues were fixed.

The panel comes from [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui). Third-party authors retain their rights and existing licenses.

Original xPROMSx developments and changes are offered under [GNU GPL-3.0-only](LICENSE). Copyright (C) 2026 xPROMSx contributors. The license covers only our rights in those materials; it does not relicense inherited code or establish GPL status for the entire repository. The scope of our license and notices for third-party components are explained in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

<a id="windows-flag-emojis"></a>

## 🖥️ Country flags on Windows 11

If you see two-letter country codes (`FI`, `DE`, `US`) instead of flags when opening the **3x-ui** panel in **Chrome, Edge, or Brave** on Windows 11, try our small companion project [**Flag Emojis Windows Installer**](https://github.com/xPROMSx/flag-emojis-windows-installer). It restores flag emoji display, preserves the original Windows font, and lets you roll back the change.

<a id="support-development"></a>

## ❤️ Support Development

If you find this project useful, you can voluntarily support its continued development. The project and all its features remain free and open source, regardless of donations.

- **🌍 International:** [Support via Tribute (bank card)](https://web.tribute.tg/d/S0p)
- **🇷🇺 Russia:** [Support via SBP / Mir (bank app)](https://pay.cloudtips.ru/p/9f240c8b)
- [All donation methods](docs/SUPPORT.en.md) — including USDT, USDC, and Bitcoin.

<div align="center">

**Two domains. A few minutes. Your own 3x-ui / Xray server.**

⭐ If this installer helped you, consider giving it a [Star on GitHub](https://github.com/xPROMSx/3x-ui-auto-nginx). It helps others discover the project.

[Install](#installation) · [Releases](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Issues](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
