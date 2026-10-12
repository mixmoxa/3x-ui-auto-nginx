<div align="center">

[🇷🇺 Русский](README_RU.md) · [🇬🇧 English](README.md) · 🇪🇬 **العربية** · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### نشر 3X-UI / XRAY-CORE تلقائيًا على خادم VPS الخاص بك

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

نطاقان وخادم VPS جديد وبضع دقائق لإكمال التثبيت.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[الإصدارات](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Telegram Web Proxy Manager](#telemt-web-manager) · [الإبلاغ عن المشكلات](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>

يُثبّت **3X-UI AUTO NGINX** لوحة [3x-ui](https://github.com/MHSanaei/3x-ui) وXray، ويضبط nginx وHTTPS وملفات الاتصال والاشتراكات وأدوات تشخيص الشبكة والنسخ الاحتياطي والاستعادة. ويمكن تثبيت AmneziaWG 3.1 وAdGuard Home مع DoH اختياريًا.

كل ما تحتاج إليه نطاقان وخادم VPS جديد. يختار المُثبّت موقع تمويه وينشره تلقائيًا.

## ✨ لماذا هذا المشروع؟

| | |
| --- | --- |
| **اتصالات مُعدّة مسبقًا**<br>إعدادات REALITY وXHTTP وHysteria2 وWebSocket وTrojan gRPC جاهزة. | **خدمات داخلية غير مكشوفة**<br>لا تُعرَض منافذ اللوحة وخدمة الاشتراكات الداخلية مباشرةً للإنترنت. |
| **توجيه nginx مقيّد**<br>لا يمكن تمرير الطلبات إلى منافذ محلية عشوائية. | **Backup / Restore v3**<br>استعادة حالة خادمك أو نقل النسخة الاحتياطية إلى خادم جديد، حتى لدى مزوّد استضافة مختلف. |
| **شهادات تلقائية**<br>إصدار شهادات Let's Encrypt وتجديدها دون إعداد يدوي. | **AdGuard Home + DoH**<br>خيار إضافي أثناء التثبيت، ولا يتطلب نطاقًا ثالثًا. |

<a id="installation"></a>

## 🚀 بدء التثبيت

وجّه سجلات DNS الخاصة بـ **نطاقين** إلى عنوان IP لخادمك: أحدهما للوحة والآخر لاتصالات REALITY. اتصل عبر SSH بحساب **root** واسمح بالوصول عبر TCP **80/443** وUDP **443**. راجع [الأنظمة المدعومة](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

يسألك المُثبّت عن النطاقين، ثم يتيح اختيار AmneziaWG وAdGuard Home. ويمكنك أيضًا تحديد النطاقين مباشرةً:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

> **⚠️ للتثبيت الجديد أو إعادة التثبيت الكاملة فقط.** يحذف `x-ui-latest.sh` قاعدة بيانات 3x-ui وإعدادات nginx السابقة. **لا تستخدمه لتحديث خادم VPS يعمل حاليًا.** احتفظ أولًا بنسخة احتياطية خارج الخادم. عند اكتشاف تثبيت موجود، تتطلب إعادة التثبيت أو الإزالة إدخال `YES` بأحرف كبيرة تمامًا.

عند الانتهاء ستظهر **رابط اللوحة وبيانات دخول عشوائية ورابط التشخيص** (MTR/LibreSpeed مع تسجيل الدخول عبر 3x-ui). وإذا ثبّتَّ AdGuard Home فستظهر أيضًا لوحة إدارته وكلمة المرور وعنوان DoH.

## 🚀 ملفات الاتصال

| الاتصال | الحالة |
| --- | :---: |
| VLESS + REALITY | ✅ جاهز للاستخدام |
| VLESS + XHTTP | ✅ جاهز للاستخدام |
| Hysteria2 | ✅ جاهز للاستخدام |
| VLESS + WebSocket | ✅ جاهز للاستخدام |
| Trojan + gRPC | ✅ جاهز للاستخدام |
| AmneziaWG 3.1 | ✅ اختياري |

ملفات الاتصال الأساسية الخمسة مُعدّة مسبقًا؛ فعّل ما تحتاج إليه من لوحة 3x-ui دون تعديل nginx. لا يُضاف AmneziaWG إلا إذا اخترته أثناء التثبيت. **أنشئ العملاء من داخل اللوحة**؛ وتعتمد التوافقية على تطبيق العميل وإصداره.

### الاشتراكات

تُقدَّم الاشتراكات العادية وJSON و**Mihomo / Clash** عبر nginx وHTTPS. يعيد المعامل `provider=1` الاشتراك الأصلي لمزوّدي البروكسي بدلًا من ملف إعداد Clash الكامل.

## 🧩 ميزات اختيارية

يمكن اختيار الميزتين أثناء التثبيت، وهما معطّلتان افتراضيًا.

### AdGuard Home + DoH

أدخل `y` عند ظهور السؤال `Install AdGuard Home with DNS-over-HTTPS? [y/N]:`. لا حاجة إلى نطاق ثالث: تستخدم واجهة الإدارة مسارًا عشوائيًا `/adg-.../` على نطاق اللوحة، وتتوفر خدمة DoH على `https://panel.example.com/dns-query`. لا يُفتح منفذ TCP/UDP العام **53**. تُضمَّن إعدادات AdGuard Home وبياناته في **Backup / Restore v3**.

<details>
<summary>⚠️ <strong>توصية أمنية</strong></summary>

لخادم VPS شخصي، أنشئ [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) لكل جهاز وأضف **هذه المعرّفات فقط** في **الإعدادات ← إعدادات DNS ← إعدادات الوصول ← العملاء المسموح لهم** (دون إضافة عناوين IP أو نطاقات CIDR).

استخدم عناوين DoH بالشكل `/dns-query/<ClientID>`. ستُرفض استعلامات DNS التي لا تحتوي على ClientID مسموح به، بما فيها الاستعلامات إلى المسار الافتراضي `/dns-query`. اختر معرّفات طويلة وعشوائية. [توصيات الأمان الرسمية من AdGuard Home](https://adguard-dns.io/kb/adguard-home/running-securely/).

</details>

---

### AmneziaWG 3.1

يمكن إعداد **AmneziaWG 3.1 على UDP/8443** أثناء التثبيت (معطّل افتراضيًا). أدخل `y` عند ظهور السؤال `Install AmneziaWG on UDP port 8443? [y/N]:`. يعمل داخل 3x-ui ويستخدم نطاق اللوحة. بعد التثبيت، أضف عميلًا في لوحة 3x-ui للحصول على ملف إعداد أو رابط `vpn://`؛ لا ينشئ المُثبّت عملاء تلقائيًا. يسمح UFW تلقائيًا بالاتصال عبر UDP/8443؛ ويحفظ **Backup / Restore v3** الإعدادات ويستعيد القاعدة.

## 💾 النسخ الاحتياطي والاستعادة

تتيح **Backup / Restore v3** استرجاع حالة VPS أو استعادة النظام على خادم متوافق بعد إعادة تثبيت نظام التشغيل. تُثبَّت الأداة مع المشروع؛ شغّل الأوامر بحساب root:

```bash
# إنشاء نسخة احتياطية
x-ui-backup backup

# عرض النسخ الاحتياطية
x-ui-backup list

# استعادة نسخة محددة
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

تُحفظ الأرشيفات في `/var/backups/x-ui/`.

> **تحتوي النسخ الاحتياطية على بيانات حساسة:** قاعدة بيانات العملاء وكلمات المرور والمفاتيح الخاصة للشهادات. احتفظ بنسخة **خارج VPS** ولا تستعد إلا أرشيفات موثوقة.

[الاستعادة على خادم VPS جديد](#restore-on-new-vps).

## 🔐 الأمان

لا تُعرَض واجهات الخدمات مباشرةً على الإنترنت. تُتاح اللوحة والاشتراكات والخدمات الإضافية عبر nginx وHTTPS، بينما تظل المنافذ الداخلية محلية.

لا يوجد مسار بروكسي عام يتيح التوجيه إلى منافذ localhost عشوائية. عند حدوث خطأ حرج تتوقف عملية التثبيت أو الاستعادة بدلًا من تشغيل إعداد غير مكتمل.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[مشروع مرافق](https://github.com/xPROMSx/telegram-web-proxy-manager) لإنشاء Telegram WEB Proxy خاص بك، مع HTTPS وموقع تمويه وتحديثات تدعم التراجع عند حدوث خطأ.

المشروعان مستقلان؛ **هذا المُثبّت لا يثبّت Telegram Web Proxy Manager**.

<a id="technical-details"></a>

## ⚙️ التفاصيل التقنية والتوافقية

- **الأنظمة:** Ubuntu 24.04 وUbuntu 26.04 وDebian 13.
- **UFW:** يسمح بالمنافذ 80/tcp و443/tcp و443/udp (ويضيف 8443/udp اختياريًا عند اختيار AmneziaWG). لا يُفعّل UFW غير النشط إلا بعد اكتشاف منفذ SSH والسماح به؛ وإلا يبقى غير نشط مع إظهار تحذير. **⚠️ لا تفعّل عملية الاستعادة UFW أبدًا.**
- **الشهادات:** يجري إصدار شهادات Let's Encrypt وتجديدها تلقائيًا باستخدام webroot و`certbot.timer`، دون إيقاف nginx.
- **إصدار 3x-ui:** يثبّت المُثبّت افتراضيًا أحدث إصدار جرى التحقق جيدًا من توافقه مع 3x-ui Auto Nginx، وقد لا يكون أحدث إصدار صادر عن المشروع الأصلي. يمكنك تحديث 3x-ui لاحقًا بآليته المدمجة، لكن قد لا يكون توافق الإصدار الجديد مع إعداداتنا قد اختُبر بعد. ويمكنك اختيار إصدار مستقر آخر صراحةً باستخدام `-version <tag>` (الحد الأدنى المدعوم v3.8.0)؛ وسيظهر تحذير إذا لم يُتحقق من توافقه.

<a id="restore-on-new-vps"></a>

### الاستعادة على خادم VPS جديد

يجب أن تتطابق توزيعة نظام التشغيل وإصداره ومعمارية المعالج مع النسخة الاحتياطية. إذا تغيّر عنوان IP لخادم VPS، فحدّث سجلات DNS الخاصة بالنطاقات. **لا تشغّل** `x-ui-latest.sh`؛ ثبّت أداة النسخ الاحتياطي فقط، ثم استعد أرشيفًا موثوقًا:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

تبقى إدارة SSH ونظام التشغيل وجدار الحماية الأساسي مسؤولية مدير الخادم. لاستعادة أرشيفات v2، استخدم أداة الإصدار الأقدم المطابق.

## 🤝 الشكر وأصل المشروع

يستند المشروع إلى [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro)، ويُطوَّر ويُصان بصورة مستقلة. بعد إنشاء التفريع، أُعيدت هندسة توجيه nginx/SNI وإعداد XHTTP بشكل واسع، وأُعيد تصميم إصدار شهادات TLS وتجديدها التلقائي، وأضيفت Backup / Restore v3 مع إمكانات الاستعادة والتراجع. كما أضيف Hysteria2 على UDP/443 وعولجت مشكلات أمنية مكتشفة.

اللوحة الأصلية من [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui). يحتفظ مؤلفو المكونات الخارجية بحقوقهم وتراخيصهم الحالية.

تُتاح مساهمات xPROMSx الأصلية وتعديلاته بموجب [GNU GPL-3.0-only](LICENSE). Copyright (C) 2026 xPROMSx contributors. ينطبق الترخيص فقط على الحقوق التي نملكها في هذه المواد، ولا يعيد ترخيص الشيفرة الموروثة أو يثبت أن المستودع بأكمله خاضع لـ GPL. راجع [إشعارات المكونات الخارجية ونطاق الترخيص](THIRD_PARTY_NOTICES.md).

## ❤️ دعم التطوير

إذا كان المشروع مفيدًا لك، يمكنك [دعم تطويره طوعًا](docs/SUPPORT_AR.md). يبقى المشروع وجميع ميزاته مجانيًا ومفتوح المصدر سواء تبرعت أم لا.

<div align="center">

**نطاقان. بضع دقائق. خادم 3x-ui / Xray خاص بك.**

⭐ إذا أفادك المُثبّت، فادعم المشروع بإضافة [نجمة على GitHub](https://github.com/xPROMSx/3x-ui-auto-nginx) لتساعد الآخرين على اكتشافه.

[التثبيت](#installation) · [الإصدارات](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [المشكلات](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
