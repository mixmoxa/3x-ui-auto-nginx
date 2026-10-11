<div align="center">

[🇷🇺 Русский](README_RU.md) · 🇬🇧 **English** · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Automated deployment of 3X-UI / XRAY-CORE on your own VPS

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

Two domains, a clean VPS, and a few minutes to install.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[Releases](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Telegram Web Proxy Manager](#telemt-web-manager) · [Issues](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>

**3X-UI AUTO NGINX** installs [3x-ui](https://github.com/MHSanaei/3x-ui) and Xray with nginx, HTTPS, connection profiles, subscriptions, diagnostics, and Backup / Restore. AmneziaWG 3.1 and AdGuard Home with DoH are optional.

Bring two domains and a clean VPS. A cover website is selected and deployed automatically.

## ✨ Why this project

| | |
| --- | --- |
| **Preconfigured connections**<br>REALITY, XHTTP, Hysteria2, WebSocket, and Trojan gRPC are already set up. | **Private internal services**<br>The panel and subscription service don't expose their internal ports to the internet. |
| **Restricted nginx routing**<br>Requests cannot be forwarded to arbitrary local ports. | **Backup / Restore v3**<br>Roll back your VPS or restore to a new server, including one from another hosting provider. |
| **Automatic certificates**<br>Let's Encrypt issuance and renewal need no manual configuration. | **AdGuard Home + DoH**<br>Opt in during setup; no third domain needed. |

<a id="installation"></a>

## 🚀 Quick start

Configure the DNS records for **two domains** to point to your VPS IP address: one for the panel, one for REALITY. Connect via SSH as **root** and allow TCP **80/443**, UDP **443**. [Supported systems](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Before rebuilding, the installer asks for both domains and offers VPS Security + DoT, RAW TLS Vision, AmneziaWG, AdGuard Home and initial client creation. A third domain is required only for Vision. You can also supply the core domains directly:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

> **⚠️ Clean install or full reinstall only.** `x-ui-latest.sh` removes the 3x-ui database and nginx configuration. **Do not use it to update a working VPS.** Save a Backup off-server first. A detected installation requires exact uppercase `YES` for reinstall or uninstall.

You receive a **panel URL, random credentials, and diagnostics URL** (3x-ui-authenticated MTR/LibreSpeed). With AdGuard Home: admin URL, password, and DoH endpoint. Optional client creation prints a verified subscription URL.

## 🚀 Connection profiles

| Connection | Status |
| --- | :---: |
| VLESS + REALITY | ✅ Ready to use |
| VLESS + XHTTP | ✅ Ready to use |
| Hysteria2 | ✅ Ready to use |
| VLESS + WebSocket | ✅ Ready to use |
| Trojan + gRPC | ✅ Ready to use |
| AmneziaWG 3.1 | ✅ Optional |
| VLESS + RAW TLS Vision | ✅ Optional |

Five standard profiles are preconfigured; enable the ones you need in 3x-ui without editing nginx. AmneziaWG is added only if selected during installation. Client creation can be automatic or manual in the panel; compatibility depends on your app and version.

### Subscriptions

Standard subscriptions, JSON, and **Mihomo / Clash** use nginx and HTTPS. `provider=1` returns the original subscription for proxy providers instead of a full Clash configuration.

## 🧩 Optional features

Choices are collected before the rebuild. Security and initial client creation default to Y; Vision, AWG and AGH default to N.

### Optional VPS Security + DNS-over-TLS

Before removing a previous deployment, the installer checks compatibility, runs mandatory `apt-get --no-remove -y dist-upgrade`, installs system dependencies and rechecks SSH/DNS. Reinstallation requires confirmation: OS upgrades may restart services and cannot be rolled back. A required reboot is scheduled only after successful installation, checks and the final report; the owner verifies post-reboot acceptance.

`Enhance VPS security? [Y/n]:` configures the SSH Fail2ban jail, APT update at 02:30, unattended upgrade at 02:50 and automatic reboot at 04:38, including when users are logged in. The displayed local VPS timezone is preserved; SSH policy and keys remain unchanged. Selecting Security applies the project DNS policy regardless of the previous provider or existing DNS directives. The installer snapshots the original resolver file/link, its own drop-in and service state, ensures systemd-resolved is installed, then applies and verifies strict DoT. The base resolved.conf and network/VPN files remain unchanged. Effective conflicting DNS routes or failed TLS/DNS checks cause verified rollback; old configuration alone does not block preflight. Package changes are not rolled back. Security=N leaves DNS unchanged. Host-specific security/DNS is not transported by Backup / Restore. Security also enables previously disabled periodic APT updates and verifies the effective flags; existing APT origins are preserved.

### Optional VLESS RAW TLS Vision

`Set up an additional VLESS Vision connection? (requires a separate domain) [y/N]:` requires one additional domain or subdomain pointing to this VPS. Vision shares TCP/443 through nginx SNI, uses a separate certificate and provides an HTTPS camouflage site. No extra public port is opened. Backup / Restore v3 supports the third certificate while retaining compatibility with archives without Vision.

### Automatic client and subscription

`Create a client in 3X-UI and display a subscription link after installation? [Y/n]:` creates one client through official 3x-ui v3.9.0 API, attaches it to supported active local inbounds and verifies the official subscription. It uses the panel domain; no subscription domain is required. N leaves client/subscription settings unchanged. The final result prints the subscription only after verification. An AWG `vpn://` export needs a compatible Amnezia application.


### AdGuard Home + DoH

Enter `y` when prompted `Install and configure AdGuard Home? [y/N]:`. No third domain is needed: the admin UI uses a random `/adg-.../` path on the panel domain, and DoH is available at `https://panel.example.com/dns-query`. Public TCP/UDP port **53** is not opened. Configuration and data are included in **Backup / Restore v3**.

<details>
<summary>⚠️ <strong>Security recommendation</strong></summary>

For a personal VPS, create a [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) for each device and add **only these IDs** under **Settings → DNS settings → Access settings → Allowed clients** (no IP addresses or CIDR ranges).

Use DoH URLs such as `/dns-query/<ClientID>`. DNS queries without an allowed ClientID, including requests to the standard `/dns-query`, will be refused. Choose long, randomly generated identifiers. [Official AdGuard Home security recommendations](https://adguard-dns.io/kb/adguard-home/running-securely/).

</details>

---

### AmneziaWG 3.1

You can configure **AmneziaWG 3.1 on UDP/8443** during installation (disabled by default). Enter `y` when prompted `Set up an additional AmneziaWG connection? [y/N]:`. It runs inside 3x-ui and uses the panel domain. After installation, add a client in the 3x-ui panel to get a configuration or `vpn://` link; initial client creation includes AWG when selected. UFW automatically allows UDP/8443; **Backup / Restore v3** preserves the configuration and restores the rule.

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

[Recovery on a new VPS](#restore-on-new-vps).

## 🔐 Security

Service interfaces are not exposed directly to the internet. The panel, subscriptions, and additional services are accessible through nginx and HTTPS, while internal ports remain local.

There is no generic proxy to arbitrary localhost ports. Critical errors stop installation or restore rather than starting an incomplete configuration.

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

<div align="center">

**Two domains. A few minutes. Your own 3x-ui / Xray server.**

⭐ If this installer helped you, consider giving it a [Star on GitHub](https://github.com/xPROMSx/3x-ui-auto-nginx). It helps others discover the project.

[Install](#installation) · [Releases](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Issues](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
