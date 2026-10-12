<div align="center">

[🇷🇺 Русский](README_RU.md) · [🇬🇧 English](README.md) · [🇪🇬 العربية](README_AR.md) · 🇮🇷 **فارسی** · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### راه‌اندازی خودکار 3X-UI / XRAY-CORE روی VPS شخصی

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

دو دامنه، یک VPS تازه و تنها چند دقیقه برای نصب.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[نسخه‌های منتشرشده](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Telegram Web Proxy Manager](#telemt-web-manager) · [گزارش مشکل](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>

**3X-UI AUTO NGINX** پنل [3x-ui](https://github.com/MHSanaei/3x-ui) و Xray را نصب می‌کند و nginx، HTTPS، پروفایل‌های اتصال، اشتراک‌ها، ابزارهای عیب‌یابی و Backup / Restore را پیکربندی می‌کند. AmneziaWG 3.1 و AdGuard Home همراه با DoH قابلیت‌هایی اختیاری هستند.

تنها به دو دامنه و یک VPS تازه نیاز دارید. اسکریپت به‌صورت خودکار یک وب‌سایت پوششی انتخاب و راه‌اندازی می‌کند.

## ✨ چرا این پروژه؟

| | |
| --- | --- |
| **اتصال‌های از پیش پیکربندی‌شده**<br>REALITY، XHTTP، Hysteria2، WebSocket و Trojan gRPC آماده‌اند. | **سرویس‌های داخلی غیرعمومی**<br>پورت‌های داخلی پنل و سرویس اشتراک مستقیماً در اینترنت در دسترس نیستند. |
| **مسیریابی محدود nginx**<br>درخواست‌ها به پورت‌های دلخواه localhost هدایت نمی‌شوند. | **Backup / Restore v3**<br>بازگشت به وضعیت پیشین VPS یا بازیابی روی سرور جدید، حتی نزد ارائه‌دهنده میزبانی دیگر. |
| **گواهی‌های خودکار**<br>صدور و تمدید گواهی Let's Encrypt بدون تنظیم دستی انجام می‌شود. | **AdGuard Home + DoH**<br>اختیاری است و به دامنه سوم نیازی ندارد. |

<a id="installation"></a>

## 🚀 شروع سریع

رکوردهای DNS **دو دامنه** را طوری تنظیم کنید که به نشانی IP سرور VPS شما اشاره کنند: یکی برای پنل و دیگری برای REALITY. با SSH و کاربر **root** وارد شوید و پورت‌های TCP **80/443** و UDP **443** را باز کنید. [سیستم‌عامل‌های پشتیبانی‌شده](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

نصب‌کننده دو دامنه را می‌پرسد و سپس امکان انتخاب AmneziaWG و AdGuard Home را می‌دهد. می‌توانید دامنه‌ها را مستقیماً نیز مشخص کنید:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

> **⚠️ فقط برای نصب تازه یا نصب مجدد کامل.** اجرای `x-ui-latest.sh` پایگاه داده فعلی 3x-ui و تنظیمات nginx را حذف می‌کند. **برای به‌روزرسانی VPS در حال کار از این اسکریپت استفاده نکنید.** پیش از نصب مجدد، یک نسخه پشتیبان خارج از سرور ذخیره کنید. در صورت شناسایی نصب قبلی، نصب مجدد یا حذف برنامه به تأیید با عبارت `YES` (با حروف بزرگ) نیاز دارد.

در پایان، **آدرس پنل، اطلاعات ورود تصادفی و نشانی عیب‌یابی** (MTR/LibreSpeed با احراز هویت 3x-ui) نمایش داده می‌شود. در صورت انتخاب AdGuard Home، آدرس مدیریت، گذرواژه و نشانی DoH نیز ارائه می‌شوند.

## 🚀 پروفایل‌های اتصال

| اتصال | وضعیت |
| --- | :---: |
| VLESS + REALITY | ✅ آماده استفاده |
| VLESS + XHTTP | ✅ آماده استفاده |
| Hysteria2 | ✅ آماده استفاده |
| VLESS + WebSocket | ✅ آماده استفاده |
| Trojan + gRPC | ✅ آماده استفاده |
| AmneziaWG 3.1 | ✅ اختیاری |

پنج پروفایل اصلی از پیش پیکربندی شده‌اند؛ هرکدام را که نیاز دارید در 3x-ui فعال کنید، بدون آنکه لازم باشد nginx را تغییر دهید. AmneziaWG تنها در صورت انتخاب هنگام نصب اضافه می‌شود. **کلاینت‌ها را در پنل ایجاد کنید**؛ سازگاری به برنامهٔ کلاینت و نسخهٔ آن بستگی دارد.

### اشتراک‌ها

اشتراک‌های استاندارد، JSON و **Mihomo / Clash** از طریق nginx و HTTPS ارائه می‌شوند. پارامتر `provider=1` به‌جای پیکربندی کامل Clash، اشتراک اصلی مناسب برای proxy provider را برمی‌گرداند.

## 🧩 قابلیت‌های اختیاری

هر دو قابلیت هنگام نصب قابل انتخاب‌اند و به‌صورت پیش‌فرض غیرفعال هستند.

### AdGuard Home + DoH

در پاسخ به `Install AdGuard Home with DNS-over-HTTPS? [y/N]:` حرف `y` را وارد کنید. به دامنهٔ سوم نیازی نیست: پنل مدیریت از مسیر تصادفی `/adg-.../` روی دامنهٔ پنل استفاده می‌کند و DoH در `https://panel.example.com/dns-query` در دسترس است. پورت عمومی TCP/UDP **53** باز نمی‌شود. تنظیمات و داده‌ها در **Backup / Restore v3** گنجانده می‌شوند.

<details>
<summary>⚠️ <strong>توصیه امنیتی</strong></summary>

برای VPS شخصی، برای هر دستگاه یک [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) بسازید و **فقط همین شناسه‌ها** را در **تنظیمات ← تنظیمات DNS ← تنظیمات دسترسی ← کلاینت‌های مجاز** اضافه کنید (بدون آدرس IP یا محدوده‌های CIDR).

از نشانی‌های DoH مانند `/dns-query/<ClientID>` استفاده کنید. درخواست‌های DNS بدون ClientID مجاز، از جمله درخواست به مسیر معمول `/dns-query`، رد می‌شوند. شناسه‌های طولانی و تصادفی انتخاب کنید. [راهنمای رسمی امنیت AdGuard Home](https://adguard-dns.io/kb/adguard-home/running-securely/).

</details>

---

### AmneziaWG 3.1

هنگام نصب می‌توانید **AmneziaWG 3.1 روی UDP/8443** را پیکربندی کنید (به‌صورت پیش‌فرض غیرفعال است). در پاسخ به `Install AmneziaWG on UDP port 8443? [y/N]:` حرف `y` را وارد کنید. این قابلیت داخل 3x-ui اجرا می‌شود و از دامنهٔ پنل استفاده می‌کند. پس از نصب، یک کلاینت در پنل 3x-ui اضافه کنید تا پیکربندی یا پیوند `vpn://` آن را دریافت کنید؛ نصب‌کننده به‌صورت خودکار کلاینت نمی‌سازد. UFW به‌طور خودکار UDP/8443 را مجاز می‌کند؛ **Backup / Restore v3** پیکربندی را حفظ کرده و قانون فایروال را بازیابی می‌کند.

## 💾 پشتیبان‌گیری و بازیابی

**Backup / Restore v3** امکان بازگشت به وضعیت پیشین VPS یا بازیابی روی سرور سازگار پس از نصب مجدد سیستم‌عامل را فراهم می‌کند. این ابزار همراه با نصب سرور نصب می‌شود و باید با دسترسی root اجرا شود:

```bash
# ایجاد نسخه پشتیبان
x-ui-backup backup

# نمایش نسخه‌های پشتیبان
x-ui-backup list

# بازیابی یک نسخه پشتیبان
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

فایل‌های پشتیبان در `/var/backups/x-ui/` ذخیره می‌شوند.

> **نسخه‌های پشتیبان حاوی اطلاعات حساس‌اند:** پایگاه داده کاربران، گذرواژه‌ها و کلیدهای خصوصی گواهی‌ها. یک نسخه را **خارج از VPS** نگه دارید و فقط فایل‌های پشتیبان قابل اعتماد را بازیابی کنید.

[بازیابی روی VPS جدید](#restore-on-new-vps).

## 🔐 امنیت

رابط‌های سرویس‌ها مستقیماً در اینترنت منتشر نمی‌شوند. پنل، اشتراک‌ها و سرویس‌های جانبی از طریق nginx و HTTPS در دسترس‌اند و پورت‌های داخلی فقط روی میزبان محلی گوش می‌دهند.

پروکسی عمومی به پورت‌های دلخواه localhost وجود ندارد. در صورت بروز خطای مهم، نصب یا بازیابی متوقف می‌شود تا پیکربندی ناقص اجرا نشود.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[پروژه مکمل](https://github.com/xPROMSx/telegram-web-proxy-manager) برای راه‌اندازی Telegram WEB Proxy شخصی با HTTPS، وب‌سایت پوششی و به‌روزرسانی با امکان بازگشت به نسخه قبلی.

این دو پروژه مستقل‌اند؛ **این نصب‌کننده، Telegram Web Proxy Manager را نصب نمی‌کند**.

<a id="technical-details"></a>

## ⚙️ جزئیات فنی و سازگاری

- **سیستم‌عامل‌ها:** Ubuntu 24.04، Ubuntu 26.04 و Debian 13.
- **UFW:** پورت‌های 80/tcp، 443/tcp و 443/udp را مجاز می‌کند (8443/udp نیز در صورت انتخاب AmneziaWG به‌صورت اختیاری افزوده می‌شود). UFW غیرفعال تنها پس از شناسایی و مجاز کردن پورت SSH فعال می‌شود؛ در غیر این صورت همراه با هشدار غیرفعال می‌ماند. **⚠️ فرایند بازیابی هرگز UFW را فعال نمی‌کند.**
- **گواهی‌ها:** گواهی‌های Let's Encrypt با روش webroot و تایمر استاندارد `certbot.timer` بدون توقف nginx تمدید می‌شوند.
- **نسخه 3x-ui:** به‌صورت پیش‌فرض جدیدترین نسخه‌ای نصب می‌شود که سازگاری آن با 3X-UI AUTO NGINX به‌دقت آزمایش شده است؛ این نسخه لزوماً آخرین انتشار رسمی 3x-ui نیست. پس از نصب می‌توانید 3x-ui را با روش به‌روزرسانی داخلی خودش ارتقا دهید، اما ممکن است سازگاری نسخه جدید با پیکربندی فعلی هنوز تأیید نشده باشد. همچنین می‌توانید با `-version <tag>` نسخه پایدار دیگری را انتخاب کنید (حداقل نسخه پشتیبانی‌شده v3.8.0 است)؛ نصب‌کننده درباره تأیید نشدن سازگاری هشدار می‌دهد.

<a id="restore-on-new-vps"></a>

### بازیابی روی VPS جدید

سیستم‌عامل، نسخه آن و معماری پردازنده باید با نسخه پشتیبان مطابقت داشته باشند. اگر آدرس IP سرور VPS تغییر کرد، رکوردهای DNS دامنه‌ها را به‌روزرسانی کنید. **اسکریپت `x-ui-latest.sh` را اجرا نکنید**؛ فقط ابزار بازیابی را نصب کرده و یک آرشیو معتبر را بازیابی کنید:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

SSH، تنظیمات سیستم‌عامل و فایروال پایه همچنان بر عهده مدیر سرور است. برای آرشیوهای v2 باید از ابزار نسخه قدیمی متناظر استفاده شود.

## 🤝 خاستگاه پروژه و قدردانی

این پروژه بر پایه [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro) ساخته شده و به‌صورت مستقل نگهداری می‌شود. پس از فورک، مسیریابی nginx/SNI و پیکربندی XHTTP به‌طور گسترده بازطراحی شده‌اند، فرایند صدور و تمدید خودکار گواهی‌های TLS اصلاح شده و Backup / Restore v3 با قابلیت بازیابی و بازگشت به وضعیت پیشین ارائه شده است. Hysteria2 روی UDP/443 اضافه شده و مشکلات امنیتی شناسایی‌شده برطرف شده‌اند.

پنل اصلی از [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) ارائه می‌شود. حقوق نویسندگان اجزای شخص ثالث و مجوزهای موجود آن‌ها محفوظ است.

توسعه‌ها و تغییرات اصیل نویسندگان xPROMSx تحت [GNU GPL-3.0-only](LICENSE) ارائه می‌شوند. Copyright (C) 2026 xPROMSx contributors. این مجوز فقط حقوقی را شامل می‌شود که مشارکت‌کنندگان بر این بخش‌ها دارند؛ کد به‌ارث‌رسیده را مجدداً مجوزدهی نمی‌کند و به معنای تحت GPL بودن کل مخزن نیست. دامنهٔ مجوز و اطلاعیه‌های اجزای شخص ثالث در [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) توضیح داده شده است.

## ❤️ حمایت از توسعه

اگر این پروژه برایتان مفید بوده، می‌توانید به‌صورت داوطلبانه [از توسعهٔ آن حمایت کنید](docs/SUPPORT_FA.md). پروژه و همهٔ قابلیت‌های آن، چه کمک مالی کنید و چه نکنید، رایگان و متن‌باز می‌مانند.

<div align="center">

**دو دامنه، چند دقیقه و سرور 3x-ui / Xray شخصی شما.**

⭐ اگر این نصب‌کننده برایتان مفید بود، با دادن [Star در GitHub](https://github.com/xPROMSx/3x-ui-auto-nginx) از پروژه حمایت کنید تا دیگران راحت‌تر آن را پیدا کنند.

[نصب](#installation) · [نسخه‌های منتشرشده](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [گزارش مشکل](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
