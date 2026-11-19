<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · 🇨🇳 **简体中文** · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### 在自己的 VPS 上自动部署 3X-UI / XRAY-CORE

**REALITY · XHTTP · HYSTERIA2 · CASCADE · ADGUARD HOME · BACKUP / RESTORE**

两个域名，一台全新的 VPS，只需几分钟即可完成安装。

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT_ZH_CN.md)

[📦 发布版本](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [🔗 级联](#cascade) · [🌐 伪装网站](#cover-sites) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ 支持开发](#support-development) · [💬 交流反馈](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX** 是一款免费的安装工具，可在自己的 VPS 上部署 [3x-ui](https://github.com/MHSanaei/3x-ui) 和 Xray。只需填写两个域名并运行一条命令。脚本会配置 Nginx、HTTPS 证书、REALITY、XHTTP、Hysteria2、订阅链接及伪装网站。通过菜单还可更换域名、管理备份、配置两台 VPS 的级联，以及部署个人 DNS 服务器。

**不只是默认占位页。** 新安装会为面板和 REALITY 创建带导航、文章与图片的多页面网站，共有至少 2592 种变化。未经认证的 Hysteria2 HTTP/3 请求也会显示伪装网站。无需 Docker 或额外 Web 服务器。

## ✨ 为什么选择这个项目？

| | |
| --- | --- |
| **几分钟即可使用**<br>两个域名、一台全新 VPS 和一条命令。自动配置 REALITY、XHTTP 和 Hysteria2，提供面板地址和订阅链接。 | **看起来像普通网站**<br>完整的多页面伪装站点，带导航、文章和图片，至少 2592 种变化，支持 Hysteria2 HTTP/3 伪装。 |
| **两台 VPS 级联**<br>设备连接入口服务器，流量从另一个出口服务器访问互联网，例如不同国家的 VPS。通过菜单配置，无需手改文件。 | **个人去广告 DNS**<br>AdGuard Home 可以拦截广告和跟踪。设备可使用 DNS-over-HTTPS（DoH）或可选的 DNS-over-TLS（DoT）。 |
| **备份和域名更换**<br>Backup / Restore v3 可将客户端及网站迁移到新的 VPS。更换面板和 REALITY 域名无需重装。 | **简便的安全保护**<br>面板和订阅通过 HTTPS 提供，内部端口仅本地使用，证书自动续期。可选择启用 SSH 防护和 VPS 安全更新。 |

**默认仅安装必要连接。** REALITY、XHTTP、Hysteria2 始终创建。WebSocket、Trojan gRPC、XTLS Vision、AmneziaWG 和 CDN 专用 XHTTP 仅在选择后创建。无需 Docker。

<a id="installation"></a>

## 🚀 快速开始

使用全新的 Ubuntu 24.04、Ubuntu 26.04 或 Debian 13 VPS，通过 SSH 以 **root** 身份登录。将两个域名的 DNS 指向 VPS IP，分别用于面板和 REALITY。需要开放 TCP **80**、**443** 及 UDP **443**。若开启 DoT，还需要 TCP **853**。参见[技术详情](#technical-details)。

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

运行脚本后，选择 **1 — English** 或 **2 — Русский**，即可进入主菜单：

- **1 — Installation：**全新部署或完整重装服务器。
- **2 — Change Domains：**无需重装即可更换面板域名、REALITY 域名或两者。
- **3 — Backups：**创建、查看和恢复备份。
- **4 — Telegram Web Proxy Manager：**启动或安装独立的 Telegram 代理管理器。
- **5 — Cascade：**连接两台服务器、查看状态或断开级联。
- **6 - My Server Details：**查看面板、订阅、AdGuard Home 地址及用户名，不更改配置，也不显示密码。
- **0 — Exit：**退出。

菜单需要在交互式 SSH 终端中使用。

<details>
<summary><strong>备用下载 — GitHub Releases 不可用时</strong></summary>

**`main` 分支包含项目的 Alpha 测试版。** 不建议安装。请使用上方主命令安装稳定版本。

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
> 如果发现已有安装，脚本会警告将删除所管理的数据，并要求准确输入 **YES**。重装将替换 3X-UI 数据库及 nginx 配置。此外：
> - 如果之前安装了 XTLS Vision，但本次不再选择，或改用其他域名，安装器会删除此前由它创建的旧 Vision 域名证书，并在要求输入 YES 之前警告；
> - 如果此前安装了 AmneziaWG，但本次不再选择，8443/udp 端口将关闭（不会另行警告）。
>
> **请提前将 Backup 保存到 VPS 之外。**
>
> **Change Domains** 和 **Backups** 是独立操作，不会重装面板。

<details>
<summary><strong>如何更新？</strong></summary>

- **3X-UI 和 Xray：**使用面板自带的更新功能。新版本与项目配置的兼容性可能尚未验证。
- **3X-UI AUTO NGINX：**不支持直接升级已安装的整套服务。要使用 **5 — Cascade** 等新版管理功能，可以下载最新脚本并选择对应操作。管理器会检查现有配置是否兼容。
- **Backup / Restore：**用于保存和恢复数据，不会升级已安装的服务。
- **对于 2.7.0 之前安装的服务器：**菜单 **6 - My Server Details** 会显示能够读取的旧数据。随机 DoH 路径、额外连接的配置问题和 DoT 仅适用于全新安装。已有的 WebSocket 和 Trojan gRPC 保持原状，DoH 继续使用 `/dns-query`。

**不要为了更新而选择 Installation！** 请使用操作系统的软件包管理工具更新 nginx、Linux 内核和其他系统软件包。

</details>

安装包含七个主要问题，其中部分会有追问。大多数用户可以使用默认值。

| # | 问题 | 默认值 | 用途 |
| --- | --- | :---: | --- |
| 1 | 面板域名 | - | 面板、订阅、伪装网站 |
| 2 | REALITY 域名 | - | REALITY 连接、伪装网站 |
| 3 | VPS 增强安全 | `Y` | Fail2ban、服务器自身的加密 DNS、安全更新 |
| 4 | 额外连接（分别选择） | `N` | WebSocket、Trojan gRPC、XTLS Vision、AmneziaWG、CDN XHTTP |
| 5 | 俄罗斯网站使用 WARP | 俄语菜单为 `Y` | 隐藏 VPS IP |
| 6 | AdGuard Home | `N` | 含 DoH 和可选 DoT 的个人 DNS |
| 7 | 客户端和订阅 | `Y` | 安装后提供订阅链接 |

仅选择启用额外连接时，才会显示 4.1 至 4.4 的追问。

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

### 4. 🧩 额外连接

> `Set up additional connections? [y/N]:`

*默认关闭 (`N`)*

默认设置 REALITY、XHTTP 和 Hysteria2。你还可以选择 VLESS WebSocket、Trojan gRPC、XTLS Vision、AmneziaWG 以及面向 CDN 的 XHTTP。

> [!WARNING]
> 这些连接可能在某些国家或网络中不可用。请自行评估风险；不确定时回答 `N`。

选择 `N` 时不会创建任何额外连接，也不会询问 4.1 至 4.4。选择 `y` 后逐一选择。

#### 4.1. WebSocket 和 Trojan gRPC

> `Set up legacy VLESS WebSocket and Trojan gRPC connections? [y/N]:`

选择 `y` 时同时创建并启用两种连接；选择 `N` 时两者都不创建。

---

<a id="4--vless-xtls-vision"></a>

#### 4.2. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*附加连接 · 默认关闭（`N`）*

这是一种通过 TLS 建立的备用 VLESS 连接。如果 REALITY 在你的网络中不稳定或被封锁，可以尝试此方式。安装后会作为独立入站配置出现在 3X-UI 面板中。

> [!IMPORTANT]
> **XTLS Vision 需要第三个独立域名**，不能与面板或 REALITY 域名相同。其 DNS 记录必须指向 VPS IP；HTTPS 证书与 nginx 路由将自动配置。
>
> 选择 `Y` 后，安装程序还会提示输入该域名： `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

<a id="5--amnezia-wg"></a>

#### 4.3. 🔑 Amnezia WG

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

<a id="xhttp-cdn"></a>

#### 4.4. 🌐 面向 CDN 的 VLESS + XHTTP

> `Add an additional CDN-compatible XHTTP connection? [y/N]:`

*附加连接 · 默认不安装（`N`）*

创建一个独立的 VLESS 连接，使用 packet-up 模式的 XHTTP 传输，并预先配置好用于 CDN 的服务端参数。该连接在 3X-UI 面板中创建时处于禁用状态。

使用面板现有的 HTTPS 域名，无须额外的域名或证书。启用后，也可以不经过 CDN，直接连接。

如需通过 CDN 使用，用户须自行配置 CDN 服务商，并在 3X-UI 中修改 Host 参数。安装程序不配置 CDN 服务，只提供便于后续使用的服务端配置。

---

<a id="warp-ru"></a>

### 5. 🌐 通过 Cloudflare WARP 访问俄罗斯网站

> `Route Russian websites through Cloudflare WARP to hide your VPS IP? [y/N]:`

*可选路由功能 · 俄语菜单默认启用（`Y`），英语菜单默认关闭（`N`）*

如果准备将此 VPS 用作级联入口服务器，请选择 `N`。入口服务器不兼容 WARP，但出口服务器可以使用 WARP。

选择 `Y` 后，安装程序会配置 Cloudflare WARP（MASQUE），让俄罗斯网站及部分网络服务看到 Cloudflare 的 IP 地址，而不是 VPS 的 IP 地址。这是为了保护 VPS 的 IP 地址。

该设置仅影响经过 VPS 的流量。如果应用直接访问网站，服务器上的 WARP 不会影响这类连接。

启用该功能时，安装程序会向 Cloudflare 注册一台设备并接受其服务条款。

如果 WARP 配置失败，安装仍会继续，但不会启用 WARP，最终报告会标明部分步骤未完成。如果无法确认配置已成功回滚，请在面板中检查 Xray 是否正常运行。

<details>
<summary>ℹ️ <strong>哪些网站会使用 WARP，以及如何检查配置</strong></summary>

安装程序会在 Xray 配置中新增一个名为 `warp-masque` 的出站连接和三条路由规则：

- **WARP - RU：** `geosite:category-ru` 中的俄罗斯域名。
- **WARP - RU2：** `geoip:ru` 中的 IP 地址。
- **WARP - RU3：** `ipify.org`、`ifconfig.me`、`checkip.amazonaws.com`、`ipapi.is`、`iplocate.io`、`ip.sb` 和 `2gis.com`。

这些规则会追加到路由列表末尾，前面的规则仍具有更高优先级。这不是独立的客户端连接配置，也不是整个系统的 VPN：路由只在 Xray 内生效。

安装后，在 3X-UI 面板的 **Xray → Outbounds** 中确认存在 `warp-masque`，并在 **Xray → Routing** 中确认存在上述三条规则。相关设置会随 3X-UI 配置一起保存到 Backup v3。

</details>

---

<a id="7--adguard-home--dns-over-https"></a>
<a id="6--adguard-home--dns-over-https"></a>

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS 和 DNS-over-TLS

> `Install and configure AdGuard Home? [y/N]:`

*附加 DNS 服务器 · 默认关闭 (`N`)*

个人 DNS 可拦截广告和跟踪、管理设备，并加密 DNS 查询。设备可使用 DoH 或可选的 DoT，例如 Android 的“私人 DNS”。

<details>
<summary>ℹ️ <strong>AdGuard Home 和访问设置</strong></summary>

无需额外域名。

安装后可使用：

- **AdGuard Home 管理页面：** `https://panel.example.com/adg-.../`，每次安装随机生成路径。
- **DNS-over-HTTPS：** `https://panel.example.com/dns-XXXXXXXXXXXX`，其中 `dns-XXXXXXXXXXXX` 为随机路径。
- **DNS-over-TLS**（选择时）：`panel.example.com`，端口 853。

安装完成后以及菜单 **6 - My Server Details** 中会显示这些地址。AdGuard Home 的密码之后无法查看，请在安装时保存。

不会开放公网 TCP/UDP **53**。只有选择 DoT 时才会为 AdGuard Home 额外开放公网 **853** 端口。配置和数据包含在 **Backup / Restore v3** 中。2.7.0 之前安装的服务器继续使用 `https://panel.example.com/dns-query`。

**⚠️ 安全建议**

随机 DoH 地址更难被猜测，但它会保存在设备的设置中。建议为每台设备创建一个独立的 [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid)。

在 AdGuard Home 中打开 **Settings → DNS settings → Access settings → Allowed clients**，填写创建的 ClientID。通常无需添加 IP 或网段；使用 DoT 时需要将 `127.0.0.1` 作为例外加入。

DoH 地址示例：

`https://panel.example.com/dns-XXXXXXXXXXXX/<ClientID>`

不带允许的 ClientID 的查询会被拒绝。请使用长且随机的标识符。阅读[官方安全指南](https://adguard-dns.io/kb/adguard-home/running-securely/)。

**DoT 与客户端允许列表：** DoT 不会传递 ClientID。启用允许列表后，DoT 查询会被拒绝而停止工作。将 `127.0.0.1` 添加到允许列表即可恢复；但这也意味着任何知道服务器地址的人都能使用 DoT，与未启用列表时一样。

自 **v2.4.1** 起，新安装可以直接在 AdGuard Home 网页界面更新。若此前使用该安装器安装的是旧版本，请在 VPS 上执行：

```bash
sudo bash -c 'set -euo pipefail; umask 077; d=$(mktemp -d); trap '\''rm -rf -- "$d"'\'' EXIT; cd "$d"; u=https://github.com/xPROMSx/3x-ui-auto-nginx/releases/download/v2.4.2; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh" -o x-ui-latest.sh; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh.sha256" -o x-ui-latest.sh.sha256; sha256sum --check --strict x-ui-latest.sh.sha256; bash ./x-ui-latest.sh --enable-agh-updates'
```

</details>

#### 6.1. DNS-over-TLS (DoT)

> `Enable DNS-over-TLS (DoT) for your devices? [y/N]:`

DoT 主要用于 Android 的“私人 DNS”，该设置仅接收主机名。若不需要，请保留默认 `N`。

- 仅在全新安装 AdGuard Home 时可选择。
- DoT 在 `panel.example.com` 的 **853** 端口接收查询。安装器会自动加入 UFW 规则并使用面板域名证书。
- **853 端口向整个互联网开放。** DoT 不传递 ClientID，因此知道地址的人均可连接。每个来源 IP 同时连接数限制在约 50 个。
- DoT 查询在 AdGuard Home 日志中显示为 `127.0.0.1`，因为 Nginx 在同一服务器上进行本地转发。因此无法在日志中区分各个 DoT 设备。
- 启用允许客户端列表后，DoT 会停止工作。修复方法见上方 ClientID 说明。
- DoT 配置保存在 Backup / Restore v3 中，并在更换域名时得到处理。

**Android 设置。** 在手机设置中找到“私人 DNS”，选择主机名模式并填写面板域名。

**关闭 DoT。** 在服务器上以 root 身份执行：

```bash
ufw delete allow 853/tcp
```

这会关闭 853 端口，其他服务保持正常。彻底删除 DoT 只能重新安装服务器。

---

<a id="7--自动创建客户端和订阅"></a>

<a id="8--自动创建客户端和订阅"></a>

### 7. 👤 自动创建客户端和订阅

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*推荐启用 · 默认启用（`Y`）*

安装程序会在 3X-UI 中创建客户端，并为已配置且受支持的连接生成专属 HTTPS 订阅链接。

订阅链接会显示在最终安装报告中。如果选择不自动创建，也可以之后在面板中手动添加客户端。

---

安装报告会显示 **面板地址、用户名和密码、诊断地址及订阅链接**（如果选择自动创建客户端）。启用 AdGuard Home 时，还会显示其管理地址、密码和 DoH 端点。 报告中还会显示 WARP 的配置结果。

如果操作系统更新后需要重启，安装程序会给出提示。**首次重启需手动执行** `sudo reboot`。

<a id="cover-sites"></a>

## 🌐 伪装网站与 HTTP/3

**告别简单的占位页，使用完整网站。**全新安装会自动为面板和 REALITY 创建不同的多页面网站。项目提供至少 2592 种现成的设计与文案组合，网站包含可用的导航、插图和适配手机的布局。启用可选的 XTLS Vision 后，它也会获得独立的网站。

**每次安装都有自己的风格。**网站名称、配色、图片、图标和文案会自动个性化配置。附加页面包含不同内容和发布日期。执行 Backup/Restore 或更换域名时，已选定的网站会保留。

**Hysteria2 的 HTTP/3 伪装。**在 REALITY 域名下，普通 TCP HTTPS 请求和未经认证的 UDP HTTP/3 请求都会获得同一个完整网站。面板和订阅接口与公开的 HTTP/3 伪装服务保持隔离。

## 🚀 连接配置

| 连接 | 创建条件 |
| --- | :---: |
| VLESS + REALITY | ✅ 始终创建并启用 |
| VLESS + XHTTP | ✅ 始终创建并启用 |
| Hysteria2 | ✅ 始终创建并启用 |
| VLESS + WebSocket (TLS) | 🔧 可选，选择后启用 |
| Trojan + gRPC | 🔧 可选，选择后启用 |
| VLESS + XTLS Vision | 🔧 可选，需要第三个域名 |
| Amnezia WG | 🔧 可选 |
| VLESS + XHTTP for CDN | 🔧 可选，创建后关闭 |

REALITY、XHTTP 和 Hysteria2 安装后即可使用。其他连接只有在第 4 步选择开启额外连接时才会创建；未选择的连接完全不创建。

面向 CDN 的 XHTTP 默认关闭，启用并绑定客户端前不会出现在订阅中。2.7.0 之前安装的服务器保留原来已创建但关闭的 WebSocket 和 Trojan gRPC。

可以在安装时或之后在面板中创建客户端。AmneziaWG 客户端需单独创建。兼容性取决于客户端程序与版本，CDN XHTTP 还受到 CDN 服务商设置限制。

### 订阅

普通订阅、JSON 和 **Mihomo / Clash** 均通过 nginx 的 HTTPS 提供。`provider=1` 返回供代理提供者使用的原始订阅，而不是完整的 Clash 配置。


<a id="change-domains"></a>

## 🌐 更换域名

在主菜单中选择 **2 — Change Domains**。无需重装服务器，即可更换面板域名、REALITY 域名或两者。新的 DNS 记录必须指向该 VPS，且 TCP/80 端口须可访问以申请证书。各域名必须互不相同，也不能与 Vision 域名相同。

更改前会自动创建完整的 Backup v3。客户端、密钥、设置和流量统计数据都会保留。Vision 域名不变。更改后可能需要更新订阅 URL 和客户端配置。

仅支持能够明确识别的项目安装，包括兼容的 v2.1.7 安装。如果出现错误，**请勿删除备份或恢复数据**。若出现 `ROLLBACK_UNVERIFIED`，请停止操作并保留诊断信息。[详情、限制和恢复说明](docs/MANAGER.md#change-domains)。

## 💾 备份与恢复

在主菜单中打开 **3 — Backups**，即可创建备份、查看备份文件或执行 Restore。重装操作系统后，或者迁移到另一台 VPS 时，都可以使用备份。恢复时，操作系统、其版本和处理器架构必须与备份一致。

在全新 VPS 上通过菜单执行 Restore 时，安装器会等待自动系统更新结束（最长 60 分钟）；此期间不要重启服务器。

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

<a id="cascade"></a>

## 🔗 两台服务器级联

级联可以将两台运行 3X-UI AUTO NGINX 的 VPS 串联起来：设备连接入口服务器，再通过出口服务器访问互联网。如果你连接某台 VPS 时遇到问题，或者希望通过其他国家的服务器访问互联网，这项功能可能会有帮助。

**设备 → 入口 VPS → 出口 VPS → 互联网**

俄罗斯网站和俄罗斯 IP 地址默认由入口服务器直接访问。完成配置后，可以在入口 VPS 的路由规则中关闭这一行为。其他未被前面路由规则匹配的流量则经出口服务器转发。

在主菜单选择 **5 — Cascade** 即可配置，无须手动修改配置文件。

<details>
<summary><strong>如何配置级联、检查状态和断开连接</strong></summary>

### 准备工作

- 两台已正常安装 3X-UI AUTO NGINX 的 VPS。
- 两台服务器各自的 3X-UI 面板用户名和密码。
- 包含 **5 — Cascade** 菜单项的最新安装脚本。
- 入口服务器不得配置 WARP（可以手动删除）。

### 1. 在出口服务器创建密钥

在你希望用来访问互联网的 VPS 上运行最新安装脚本。

选择 **5 — Cascade → 1 — Create key (exit server)**。

输入 3X-UI 面板用户名和密码。输入时不会显示字符，凭据也不会保存。管理器会在现有 REALITY 连接中创建名为 `cascade` 的客户端，并显示以 `vless://` 开头的密钥链接。

复制链接，下一步在另一台服务器上使用。

**不要公开密钥链接：**获得它的人可以使用该客户端连接。

现有客户端不会改变。

### 2. 连接入口服务器

在你的设备所连接的 VPS 上运行最新安装脚本。

选择 **5 — Cascade → 2 — Connect exit server (entry server)**。

输入 3X-UI 面板用户名和密码（同样不会保存），然后粘贴第一步复制的密钥链接。粘贴时链接会显示在终端上，但不会保存。

管理器先测试与出口服务器的连接。测试通过后，会添加名为 `cascade-exit` 的出站连接和三条 `CASCADE` 路由规则。

俄罗斯网站和 IP 地址默认从入口服务器直接访问，也可以之后关闭对应规则。其他符合条件的流量经出口服务器转发。

**应用设置时，所有用户的连接可能短暂中断几秒。** 如果检查失败，管理器会尝试恢复原有配置并报告结果。

现有客户端连接和订阅仍可使用，不必为级联单独创建客户端配置。

### 3. 检查状态

在每台 VPS 上选择 **5 — Cascade → 3 — Status**。

与其他操作一样，管理器会要求输入面板用户名和密码。

它会显示该服务器的入口和出口角色是否已配置，以及 Xray 是否运行。此操作不会修改设置。

### 4. 断开级联

在需要操作的 VPS 上选择 **5 — Cascade → 4 — Disable**。

**在入口服务器上，**管理器会询问是否删除 `cascade-exit` 以及三条 `CASCADE` 规则。其他连接和面板规则保留。

**在出口服务器上，**只会删除 `cascade` 客户端。使用这把密钥的入口服务器随后无法再通过该出口转发流量。

每个角色的移除都需要单独确认。在入口服务器应用改动时，用户连接可能短暂中断。

### 注意事项

- **WARP：**入口服务器不兼容 WARP。如果已配置，请先在 3X-UI 面板中删除对应出站连接和路由规则。出口服务器允许使用 WARP。
- **AmneziaWG：**此类连接不会经过出口服务器。
- **路由规则：**之前定义的规则可能将部分流量导向其他路径。管理器会在连接前提示。
- **出口不可用：**经该出口转发的流量会停止，直到出口恢复。没有自动备用出口。
- **Vision 上的 QUIC：**此级联无法转发 UDP/443。
- **更换域名：**如果修改出口 VPS 的域名，需要在入口服务器重新连接出口。

### 备份

Backup v3 会保存级联设置。在入口服务器恢复备份后，级联配置会与其他 3X-UI 数据一起保留。

级联已在两台真实 VPS 上通过 REALITY、XHTTP 和 Hysteria2 测试，但尚未验证所有客户端应用和配置。

如发现问题，请[在 GitHub 提交 Issue](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)。

</details>

## 🔐 安全性

服务接口不会直接暴露到互联网：面板、订阅和附加服务通过 nginx 和 HTTPS 提供，内部端口保持本地监听。只有自行启用 DNS-over-TLS (DoT) 时才会额外开放公网 853 服务端口。客户端连接端口本来就是公网开放的：TCP 和 UDP 443，选择 AmneziaWG 时还有 UDP 8443。


**不确定怎样保护自己的 VPS？** 安装时可以启用增强安全配置，由安装程序自动设置 SSH 防暴力破解、加密 DNS 和安全更新。启用前请先阅读“快速开始”中的详细说明和夜间自动重启计划。

**注意：** 请妥善保护服务器登录方式。建议使用 SSH 密钥，确认密钥登录正常后再关闭密码认证。安装程序不会自动关闭密码登录。

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager) 是一个独立的配套项目，可部署自己的 Telegram WEB Proxy，提供 HTTPS、伪装网站，以及支持回滚的更新。

**TWPM 不包含在 3X-UI 的默认安装中。**主菜单选项 4 可启动此管理器，或在确认后单独安装。两个项目分别管理。

Telegram Web Proxy Manager 可安装在 Ubuntu 24.04 和 26.04 上。

<a id="technical-details"></a>

## ⚙️ 技术细节与兼容性

- **系统：** Ubuntu 24.04、Ubuntu 26.04 和 Debian 13。
- **UFW：**允许 80/tcp、443/tcp 和 443/udp（选择 AmneziaWG 时开放 8443/udp，选择 DoT 时开放 853/tcp）。Installation 期间，只有确认 SSH 访问安全后才会启用 UFW；否则保持关闭并显示警告。通过菜单执行 Restore 后，**只有明确选择启用**且通过安全检查时，管理器才会启用 UFW。独立命令 `x-ui-backup restore` 不会启用 UFW。
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

本项目基于 mozaroc 的 [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro) 开发。该项目由 [x-ui-pro](https://github.com/mozaroc/x-ui-pro) 的一个分支演变而来，最早可追溯至 GFW4Fun 的原始 [x-ui-pro](https://github.com/GFW4Fun/x-ui-pro) 项目。本项目目前独立维护。Fork 之后，对 nginx/SNI 路由和 XHTTP 配置进行了大幅重构，重新设计了 TLS 证书签发与自动续期流程，并引入支持恢复和回滚的 Backup / Restore v3。此外还增加了运行于 UDP/443 的 Hysteria2，并修复了已发现的安全问题。

面板本身来自 [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui)。第三方组件的权利及其现有许可仍归原作者所有。

xPROMSx 贡献者原创的开发内容和修改部分以 [GNU GPL-3.0-only](LICENSE) 授权。Copyright (C) 2026 xPROMSx contributors. 此许可仅适用于贡献者有权授权的内容，不会自动为继承代码重新授权，也不意味着整个仓库均采用 GPL。许可范围及第三方组件声明详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

**如果你想使用我们的代码。** 只是安装和使用本项目，无需额外操作，项目仍然免费。如果你发布自己的版本，或把我们的代码用于其他项目，请在 README 中保留 `© xPROMSx · github.com/xPROMSx/3x-ui-auto-nginx` 署名；如果你的项目有交互式安装程序，也要在启动界面或主菜单中显示这行署名。请明确说明你的版本经过修改，不要把我们的工作说成自己的。完整条款见 [docs/NOTICE.md](docs/NOTICE.md)。

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
