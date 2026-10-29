<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · 🇨🇳 **简体中文** · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### 在自己的 VPS 上自动部署 3X-UI / XRAY-CORE

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

两个域名，一台全新的 VPS，只需几分钟即可完成安装。

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT_ZH_CN.md)

[📦 发布版本](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ 支持开发](#support-development) · [🐛 报告问题](https://github.com/xPROMSx/3x-ui-auto-nginx/issues) · [💬 交流反馈](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX** 自动安装 [3x-ui](https://github.com/MHSanaei/3x-ui) 和 Xray，并配置 nginx、HTTPS、连接配置、订阅、网络诊断以及 Backup / Restore。AmneziaWG 3.1 和支持 DoH 的 AdGuard Home 均为可选功能。 交互式管理菜单还支持更换域名和管理备份。

准备两个域名和一台全新的 VPS 即可。安装脚本会自动选择并部署一个伪装网站。

## ✨ 为什么选择这个项目？

| | |
| --- | --- |
| **预配置的连接方式**<br>REALITY、XHTTP、Hysteria2、Amnezia WG、VLESS XTLS Vision、WebSocket TLS 和 Trojan gRPC。 | **内部服务不直接暴露**<br>面板和订阅服务的内部端口不会直接暴露到互联网。 |
| **受限的 nginx 路由**<br>外部请求无法被代理到任意本地端口。 | **Backup / Restore v3**<br>回滚当前 VPS，或将备份恢复到新服务器，包括其他 VPS 服务商的服务器。 |
| **自动管理证书**<br>自动申请和续期 Let's Encrypt 证书，无需手动配置。 | **AdGuard Home + DoH**<br>按需启用，无需第三个域名。 |
| **英语和俄语管理菜单**<br>通过简洁的菜单完成安装和备份管理。 | **更换域名**<br>无需重装服务器，即可更换面板域名、REALITY 域名或两者。 |

<a id="installation"></a>

## 🚀 快速开始

配置**两个域名**的 DNS 记录，使它们指向你的 VPS IP 地址：一个用于面板，另一个用于 REALITY。通过 SSH 以 **root** 身份登录，并开放 TCP **80/443** 和 UDP **443**。查看[支持的系统](#technical-details)。

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

运行脚本后，选择 **1 — English** 或 **2 — Русский**，即可进入主菜单：

- **1 — Installation：**全新部署或完整重装服务器。
- **2 — Change Domains：**无需重装即可更换面板域名、REALITY 域名或两者。
- **3 — Backups：**创建、查看和恢复备份。
- **0 — Exit：**退出。

菜单需要在交互式 SSH 终端中使用。

<details>
<summary><strong>备用下载 — GitHub Releases 不可用时</strong></summary>

直接从当前 `main` 分支安装。其内容可能与最新发布的版本不同。

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

</details>

<a id="installation-vs-update"></a>

> [!CAUTION]
> **安装不等于更新！**
>
> **不带参数**再次运行脚本只会打开管理菜单，**不会**重装服务器。但 **Installation** 选项用于全新 VPS 部署或完整重装。
>
> 如果检测到已有安装，脚本会提示将删除项目管理的数据，并要求准确输入 **YES** 确认。重装时会替换 3X-UI 数据库和 nginx 配置。**请先在 VPS 之外保存备份。**
>
> **Change Domains** 和 **Backups** 是独立操作，不会重装面板。

<details>
<summary><strong>如何更新？</strong></summary>

- **3X-UI 和 Xray：**使用面板自带的更新功能。新版本与项目配置的兼容性可能尚未验证。
- **3X-UI AUTO NGINX：**不支持直接升级已安装的整套服务。要使用新版管理菜单的功能，可以下载最新脚本并选择相应操作；管理器会检查现有配置是否兼容。
- **Backup / Restore：**用于保存和恢复数据，不会升级已安装的服务。

**不要为了更新而选择 Installation！** 请使用操作系统的软件包管理工具更新 nginx、Linux 内核和其他系统软件包。

</details>

以下介绍在主菜单中选择 **Installation** 后提供的安装选项。

---

### 1. 🌐 3X-UI 面板域名

> `Enter the domain for your 3X-UI panel:`

填写用于访问管理面板、订阅及其他 Web 服务的域名。

---

### 2. 🛰️ VLESS REALITY 域名

> `Enter the domain for VLESS REALITY:`

填写 REALITY 使用的第二个域名。两个域名的 DNS 记录都必须指向 VPS 的 IP 地址。

<details>
<summary>ℹ️ 其他启动参数</summary>

你也可以在命令行中直接传入两个域名，无须在提示出现时手动输入：

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

将 `panel.example.com` 和 `reality.example.com` 替换为自己的域名。其他可选功能仍需在安装过程中选择。

</details>

---

### 3. 🔐 VPS 增强安全设置

> `Enhance VPS security? [Y/n]:`

*建议经验较少的用户启用 · 默认启用（`Y`）*

安装程序会配置 Fail2ban 保护 SSH、加密系统 DNS（DoT）和自动安全更新。如果条件允许，无论是否选择增强安全选项，都会创建 1 GiB 的 swap 文件。

**启用前请先阅读以下设置说明**，尤其要了解自动重启计划。

<details>
<summary>🔐 安全设置详情</summary>

选择 `Y` 会启用额外的安全设置。swap 的配置与此选择无关：

- **1 GiB swap。** 如果没有启用的 swap、文件系统受支持且至少有 4 GiB 可用空间，安装程序会创建并启用 swap 文件。现有 swap 设置不会被修改。如果不满足条件，将跳过此步骤而不中断安装。
- **SSH 防护 — Fail2ban。** 根据实际 SSH 监听端口限制反复失败的登录尝试，不修改现有的 SSH 身份验证设置。
- **加密 DNS（DoT）。** 全局 Cloudflare 和 Google DNS 服务器通过 `systemd-resolved` 使用严格的 DNS-over-TLS。接口/VPN 的 DNS 路由和搜索域保持不变；其查询可能仍未加密。如果 DoT 准备失败但原有 DNS 已成功恢复，核心组件、Fail2ban 和自动更新将独立于 DoT 继续安装；最终结果会报告失败并返回非零退出码。
- **自动安全更新。** 02:30 更新软件包列表，02:50 安装安全更新。
- **自动重启 — 04:38。** 如果更新要求重启，系统将在指定时间重启，**即使用户仍有活动会话**，连接也可能因此中断。

所有时间均以 VPS 的本地时区为准。

更改设置前会检查与现有配置的兼容性；安全设置失败时会执行受控回滚。

**注意：** 此选项不会关闭 SSH 密码登录，也不能替代日常服务器管理。建议先配置 SSH 密钥登录，确认可正常使用后再自行关闭密码认证。

</details>

---

### 4. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*附加连接 · 默认关闭（`N`）*

这是一种通过 TLS 建立的备用 VLESS 连接。如果 REALITY 在你的网络中不稳定或被封锁，可以尝试此方式。安装后会作为独立入站配置出现在 3X-UI 面板中。

> [!IMPORTANT]
> **XTLS Vision 需要第三个独立域名**，不能与面板或 REALITY 域名相同。其 DNS 记录必须指向 VPS IP；HTTPS 证书与 nginx 路由将自动配置。
>
> 选择 `Y` 后，安装程序还会提示输入该域名： `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

### 5. 🔑 Amnezia WG

> `Set up an additional AmneziaWG connection? [y/N]:`

*附加连接 · 默认关闭（`N`）*

在 3X-UI 面板中创建独立的 AmneziaWG 连接，无须额外域名。

<details>
<summary>ℹ️ 了解 Amnezia WG</summary>

安装程序会在 **UDP/8443** 上配置 AmneziaWG 3.1，并自动添加所需的 UFW 规则。

安装完成后，请在 3X-UI 面板中单独创建客户端，获取适用于兼容 Amnezia 应用的配置文件或 `vpn://` 链接。

安装程序仅创建服务端连接，不会自动生成 AmneziaWG 客户端。

其配置及相关防火墙规则均包含在 **Backup / Restore v3** 中。

</details>

---

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS

> `Install and configure AdGuard Home? [y/N]:`

*可选 DNS 服务器 · 默认关闭（`N`）*

个人 DNS 服务器，可屏蔽广告与跟踪请求、管理客户端并提供加密 DNS 查询。

<details>
<summary>ℹ️ AdGuard Home 与访问控制说明</summary>

无须额外域名。

安装完成后可访问：

- **AdGuard Home 管理面板：** `https://panel.example.com/adg-.../` — 独立生成的随机路径.
- **DNS-over-HTTPS：** `https://panel.example.com/dns-query`.

不会向公网开放 TCP/UDP **53** 端口。AdGuard Home 的配置和数据将纳入 **Backup / Restore v3**。

**⚠️ 安全建议**

个人 VPS 建议为每台设备创建独立的 [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid)。

在 AdGuard Home 的 **设置 → DNS 设置 → 访问设置 → 允许的客户端** 中，**仅添加这些 ClientID**，不要添加 IP 地址或子网。

DoH 地址格式示例：

`https://panel.example.com/dns-query/<ClientID>`

配置后，没有携带获准 ClientID 的查询（包括对普通 `/dns-query` 的请求）都会被拒绝。

请使用较长的随机标识符。参见 [AdGuard Home 官方安全建议](https://adguard-dns.io/kb/adguard-home/running-securely/)。

</details>

---

### 7. 👤 自动创建客户端和订阅

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*推荐启用 · 默认启用（`Y`）*

安装程序会在 3X-UI 中创建客户端，并为已配置且受支持的连接生成专属 HTTPS 订阅链接。

订阅链接会显示在最终安装报告中。如果选择不自动创建，也可以之后在面板中手动添加客户端。

---

安装报告会显示 **面板地址、用户名和密码、诊断地址及订阅链接**（如果选择自动创建客户端）。启用 AdGuard Home 时，还会显示其管理地址、密码和 DoH 端点。

如果操作系统更新后需要重启，安装程序会给出提示。**首次重启需手动执行** `sudo reboot`。

## 🚀 连接配置

| 连接 | 状态 |
| --- | :---: |
| VLESS + REALITY | ✅ 可直接使用 |
| VLESS + XHTTP | ✅ 可直接使用 |
| Hysteria2 | ✅ 可直接使用 |
| VLESS + WebSocket (TLS) | ✅ 可直接使用 |
| Trojan + gRPC | ✅ 可直接使用 |
| VLESS + XTLS Vision | ✅ 可选 |
| Amnezia WG | ✅ 可选 |

安装程序预先配置五个基本连接：REALITY、XHTTP 和 Hysteria2 默认启用；WebSocket 和 Trojan gRPC 可按需在 3X-UI 面板中启用。

XTLS Vision 和 Amnezia WG 只有在安装时选择才会添加。**使用这些连接之前需要创建客户端**，可以在安装时自动创建，也可以之后在面板中手动创建。Amnezia WG 客户端需要单独添加。

兼容性取决于客户端应用及其版本。

### 订阅

普通订阅、JSON 和 **Mihomo / Clash** 均通过 nginx 的 HTTPS 提供。`provider=1` 返回供代理提供者使用的原始订阅，而不是完整的 Clash 配置。


<a id="change-domains"></a>

## 🌐 更换域名

在主菜单中选择 **2 — Change Domains**。无需重装服务器，即可更换面板域名、REALITY 域名或两者。新的 DNS 记录必须指向该 VPS，且 TCP/80 端口须可访问以申请证书。各域名必须互不相同，也不能与 Vision 域名相同。

更改前会自动创建完整的 Backup v3。客户端、密钥、设置和流量统计数据都会保留。Vision 域名不变。更改后可能需要更新订阅 URL 和客户端配置。

仅支持能够明确识别的项目安装，包括兼容的 v2.1.7 安装。如果出现错误，**请勿删除备份或恢复数据**。若出现 `ROLLBACK_UNVERIFIED`，请停止操作并保留诊断信息。[详情、限制和恢复说明](docs/MANAGER.md#change-domains)。

## 💾 备份与恢复

在主菜单中打开 **3 — Backups**，即可创建备份、查看备份文件或执行 Restore。重装操作系统后，或者迁移到另一台 VPS 时，都可以使用备份。恢复时，操作系统、其版本和处理器架构必须与备份一致。

也可以使用以下命令（以 root 身份运行）：

```bash
# 创建备份
x-ui-backup backup

# 列出备份
x-ui-backup list

# 恢复指定备份
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

备份文件保存在 `/var/backups/x-ui/`。

> **备份包含敏感数据：** 客户端数据库、密码和证书私钥。请在 **VPS 之外** 保存副本，并且只恢复来源可信的备份文件。

[在新 VPS 上恢复](#restore-on-new-vps)。

## 🔐 安全性

服务接口不会直接暴露到互联网。面板、订阅和附加服务均通过 nginx 和 HTTPS 访问，内部端口仅在本机监听。


**不确定怎样保护自己的 VPS？** 安装时可以启用增强安全配置，由安装程序自动设置 SSH 防暴力破解、加密 DNS 和安全更新。启用前请先阅读“快速开始”中的详细说明和夜间自动重启计划。

**注意：** 请妥善保护服务器登录方式。建议使用 SSH 密钥，确认密钥登录正常后再关闭密码认证。安装程序不会自动关闭密码登录。

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[配套项目](https://github.com/xPROMSx/telegram-web-proxy-manager)，用于搭建自己的 Telegram WEB Proxy，支持 HTTPS、伪装网站以及带回滚机制的更新。

两个项目相互独立；**此安装脚本不会安装 Telegram Web Proxy Manager**。

<a id="technical-details"></a>

## ⚙️ 技术细节与兼容性

- **系统：** Ubuntu 24.04、Ubuntu 26.04 和 Debian 13。
- **UFW：**允许 80/tcp、443/tcp 和 443/udp（选择 AmneziaWG 时还会开放 8443/udp）。Installation 期间，只有确认 SSH 访问安全后才会启用 UFW；否则保持关闭并显示警告。通过菜单执行 Restore 后，**只有明确选择启用**且通过安全检查时，管理器才会启用 UFW。独立命令 `x-ui-backup restore` 不会启用 UFW。
- **证书：** 通过 Let's Encrypt webroot 和系统 `certbot.timer` 自动续期，无需停止 nginx。
- **3x-ui 版本：** 默认安装已针对 3X-UI AUTO NGINX 进行充分兼容性测试的最新版本，并不一定是 3x-ui 上游刚发布的最新版。安装完成后，你可以通过 3x-ui 自带的更新功能自行升级，但新版本与现有配置的兼容性可能尚未得到验证。也可以通过 `-version <tag>` 明确指定其他稳定版（最低支持 v3.8.0）；安装程序会提醒该版本尚未通过兼容性验证。

<a id="restore-on-new-vps"></a>

### 在新 VPS 上恢复

操作系统、版本和 CPU 架构应与备份对应。如果 VPS 的 IP 地址发生变化，请更新域名的 DNS 记录。**不要运行** `x-ui-latest.sh`；仅安装备份工具，然后恢复可信的归档文件：

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

SSH、系统配置及基础防火墙仍由管理员负责。对于 v2 备份，请使用对应旧版本中的恢复工具。

## 🤝 致谢与项目来源

本项目基于 [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro) 开发，并独立维护。Fork 之后，对 nginx/SNI 路由和 XHTTP 配置进行了大幅重构，重新设计了 TLS 证书签发与自动续期流程，并引入支持恢复和回滚的 Backup / Restore v3。此外还增加了运行于 UDP/443 的 Hysteria2，并修复了已发现的安全问题。

面板本身来自 [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui)。第三方组件的权利及其现有许可仍归原作者所有。

xPROMSx 贡献者原创的开发内容和修改部分以 [GNU GPL-3.0-only](LICENSE) 授权。Copyright (C) 2026 xPROMSx contributors. 此许可仅适用于贡献者有权授权的内容，不会自动为继承代码重新授权，也不意味着整个仓库均采用 GPL。许可范围及第三方组件声明详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

<a id="windows-flag-emojis"></a>

## 🖥️ Windows 11 中的国家旗帜

如果在 Windows 11 上使用 **Chrome、Edge 或 Brave** 打开 **3x-ui** 面板时，国家旗帜显示为双字母代码（`FI`、`DE`、`US`），可以试试我们的小工具 [**Flag Emojis Windows Installer**](https://github.com/xPROMSx/flag-emojis-windows-installer)。它可以恢复国旗表情的正常显示，保留 Windows 原始字体，并支持卸载后恢复原有设置。

<a id="support-development"></a>

## ❤️ 支持开发

如果这个项目对你有帮助，欢迎自愿支持后续开发。无论是否捐赠，项目及其所有功能始终免费且开源。

- **🌍 国际:** [通过 Tribute 支持（银行卡）](https://web.tribute.tg/d/S0p)
- **🇷🇺 俄罗斯:** [通过 SBP / Mir 支持（银行应用）](https://pay.cloudtips.ru/p/9f240c8b)
- [所有支持方式](docs/SUPPORT_ZH_CN.md) — 包括 USDT、USDC 和 Bitcoin。

<div align="center">

**两个域名，几分钟，搭建自己的 3x-ui / Xray 服务器。**

⭐ 如果这个安装脚本对你有帮助，欢迎在 [GitHub 上点个 Star](https://github.com/xPROMSx/3x-ui-auto-nginx)，让更多人发现它。

[安装](#installation) · [发布版本](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [问题反馈](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
