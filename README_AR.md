<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · 🇪🇬 **العربية** · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### نشر 3X-UI / XRAY-CORE تلقائيًا على خادم VPS الخاص بك

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

نطاقان وخادم VPS جديد وبضع دقائق لإكمال التثبيت.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[📦 الإصدارات](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [🐛 الإبلاغ عن مشكلة](https://github.com/xPROMSx/3x-ui-auto-nginx/issues) · [💬 التواصل](https://t.me/promsdev)

</div>

يُثبّت **3X-UI AUTO NGINX** لوحة [3x-ui](https://github.com/MHSanaei/3x-ui) وXray، ويضبط nginx وHTTPS وملفات الاتصال والاشتراكات وأدوات تشخيص الشبكة والنسخ الاحتياطي والاستعادة. ويمكن تثبيت AmneziaWG 3.1 وAdGuard Home مع DoH اختياريًا.

كل ما تحتاج إليه نطاقان وخادم VPS جديد. يختار المُثبّت موقع تمويه وينشره تلقائيًا.

## ✨ لماذا هذا المشروع؟

| | |
| --- | --- |
| **اتصالات مُعدّة مسبقًا**<br>REALITY وXHTTP وHysteria2 وAmnezia WG وVLESS XTLS Vision وWebSocket TLS وTrojan gRPC. | **خدمات داخلية غير مكشوفة**<br>لا تُعرَض منافذ اللوحة وخدمة الاشتراكات الداخلية مباشرةً للإنترنت. |
| **توجيه nginx مقيّد**<br>لا يمكن تمرير الطلبات إلى منافذ محلية عشوائية. | **Backup / Restore v3**<br>استعادة حالة خادمك أو نقل النسخة الاحتياطية إلى خادم جديد، حتى لدى مزوّد استضافة مختلف. |
| **شهادات تلقائية**<br>إصدار شهادات Let's Encrypt وتجديدها دون إعداد يدوي. | **AdGuard Home + DoH**<br>خيار إضافي أثناء التثبيت، ولا يتطلب نطاقًا ثالثًا. |

<a id="installation"></a>

## 🚀 بدء التثبيت

وجّه سجلات DNS الخاصة بـ **نطاقين** إلى عنوان IP لخادمك: أحدهما للوحة والآخر لاتصالات REALITY. اتصل عبر SSH بحساب **root** واسمح بالوصول عبر TCP **80/443** وUDP **443**. راجع [الأنظمة المدعومة](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```


بعد التشغيل، سيرشدك المُثبّت عبر الخطوات التالية بالترتيب. أُبقيت نصوص الأسئلة باللغة الإنجليزية كما تظهر فعلًا في الطرفية لتسهيل متابعتها:

---

### 1. 🌐 نطاق لوحة 3X-UI

> `Enter the domain for your 3X-UI panel:`

أدخل النطاق الذي ستُتاح عبره لوحة الإدارة والاشتراكات وخدمات الويب الإضافية.

---

### 2. 🛰️ نطاق VLESS REALITY

> `Enter the domain for VLESS REALITY:`

أدخل نطاقًا ثانيًا لاتصال REALITY. يجب أن تشير سجلات DNS لكلا النطاقين إلى عنوان IP الخاص بخادم VPS.

<details>
<summary>ℹ️ خيارات تشغيل إضافية</summary>

يمكنك تمرير النطاقين مباشرة عبر سطر الأوامر دون إدخالهما عند ظهور الأسئلة:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

استبدل `panel.example.com` و`reality.example.com` بنطاقيك. سيستمر اختيار الميزات الاختيارية تفاعليًا أثناء التثبيت.

</details>

---

### 3. 🔐 تعزيز أمان خادم VPS

> `Enhance VPS security? [Y/n]:`

*يُنصح به للمستخدمين الأقل خبرة · مفعّل افتراضيًا (`Y`)*

يُعدّ المُثبّت تلقائيًا حماية إضافية للخادم: Fail2ban لحماية SSH من تخمين كلمات المرور، وDNS مشفّر للنظام (DoT)، وتحديثات أمنية تلقائية للنظام والحزم، كما ينشئ ملف swap بحجم 1 GiB لتحسين استقرار النظام عند نقص الذاكرة.

**اطّلع على التفاصيل التالية قبل تفعيل هذا الخيار**، وخاصة جدول إعادة التشغيل التلقائي.

<details>
<summary>🔐 تفاصيل إعدادات الأمان</summary>

عند اختيار `Y`، تُطبّق الإعدادات التالية:

- **Swap بحجم 1 GiB.** إذا لم تكن هناك مساحة swap نشطة، وكان نظام الملفات مدعومًا وتوفرت مساحة حرة لا تقل عن 4 GiB، ينشئ المُثبّت ملف swap ويُفعّله. لا تتغير إعدادات swap الحالية. إذا لم تتحقق الشروط، تُتخطى هذه الخطوة دون إيقاف التثبيت.
- **حماية SSH — Fail2ban.** الحدّ من محاولات تسجيل الدخول الفاشلة المتكررة بناءً على منافذ SSH الفعلية، دون تغيير إعدادات المصادقة الحالية.
- **DNS مشفّر (DoT).** تستخدم خوادم Cloudflare وGoogle العامة DNS-over-TLS الإلزامي عبر `systemd-resolved`. تُحفظ مسارات DNS ونطاقات البحث الخاصة بالواجهات وVPN؛ وقد تبقى استعلاماتها غير مشفّرة. إذا فشل إعداد DoT واستُعيد DNS الأصلي بنجاح، يستمر تثبيت المكونات الأساسية وFail2ban والتحديثات التلقائية بشكل مستقل عن DoT؛ وتُظهر النتيجة النهائية الفشل مع رمز خروج غير صفري.
- **تحديثات أمنية تلقائية.** تحديث قوائم الحزم الساعة 02:30 وتثبيت التحديثات الأمنية الساعة 02:50.
- **إعادة التشغيل التلقائية — 04:38.** إذا تطلّبت التحديثات إعادة التشغيل، فستتم في الوقت المحدد **حتى مع وجود جلسات مستخدمين نشطة**، وقد تنقطع الاتصالات.

تُحسب المواعيد حسب المنطقة الزمنية المحلية لخادم VPS.

تُفحص إعدادات النظام الحالية للتأكد من التوافق قبل التعديل، وتتوفر آلية تراجع منضبطة عند فشل إعدادات الأمان.

**مهم:** لا يعطّل هذا الخيار تسجيل الدخول إلى SSH بكلمة مرور ولا يغني عن إدارة الخادم. اضبط الدخول بمفاتيح SSH أولًا، ثم عطّل المصادقة بكلمة المرور بنفسك.

</details>

---

### 4. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*اتصال إضافي · معطّل افتراضيًا (`N`)*

اتصال VLESS بديل عبر TLS قد يكون مفيدًا إذا كان REALITY غير مستقر أو محجوبًا على شبكتك. يُضاف كملف اتصال مستقل في لوحة 3X-UI.

> [!IMPORTANT]
> **يتطلّب XTLS Vision نطاقًا ثالثًا مستقلًا** يختلف عن نطاقَي اللوحة وREALITY. يجب أن يشير سجل DNS الخاص به إلى IP الخادم. يجري إعداد شهادة HTTPS وتوجيه nginx تلقائيًا.
>
> بعد اختيار `Y`، سيطلب المُثبّت أيضًا إدخال هذا النطاق: `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

### 5. 🔑 Amnezia WG

> `Set up an additional AmneziaWG connection? [y/N]:`

*اتصال إضافي · معطّل افتراضيًا (`N`)*

يُنشأ اتصال AmneziaWG مستقل داخل لوحة 3X-UI. لا يلزم نطاق إضافي.

<details>
<summary>ℹ️ المزيد عن Amnezia WG</summary>

يُعدّ المُثبّت AmneziaWG 3.1 عبر **UDP/8443** ويضيف قاعدة UFW المطلوبة تلقائيًا.

بعد التثبيت، أنشئ عميلًا من لوحة 3X-UI للحصول على ملف الإعداد أو رابط `vpn://` لتطبيق Amnezia متوافق.

يُنشئ المُثبّت اتصال الخادم لكنه لا ينشئ عملاء AmneziaWG تلقائيًا.

تُضمَّن الإعدادات وقاعدة جدار الحماية اللازمة في **Backup / Restore v3**.

</details>

---

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS

> `Install and configure AdGuard Home? [y/N]:`

*خادم DNS اختياري · معطّل افتراضيًا (`N`)*

خادم DNS شخصي لحجب الإعلانات والتتبّع وإدارة العملاء وإرسال استعلامات DNS مشفّرة.

<details>
<summary>ℹ️ تفاصيل AdGuard Home والتحكم في الوصول</summary>

لا يلزم نطاق إضافي.

بعد التثبيت، تتوفر العناوين التالية:

- **لوحة إدارة AdGuard Home:** `https://panel.example.com/adg-.../` — مسار عشوائي فريد.
- **DNS-over-HTTPS:** `https://panel.example.com/dns-query`.

لا يُفتح المنفذ العام **53** عبر TCP أو UDP. تُضمَّن إعدادات AdGuard Home وبياناته في **Backup / Restore v3**.

**⚠️ توصية أمنية**

لخادم VPS شخصي، أنشئ [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) مستقلًا لكل جهاز.

في AdGuard Home افتح **الإعدادات ← إعدادات DNS ← إعدادات الوصول ← العملاء المسموح لهم**، وأضف **معرّفات ClientID هذه فقط**، دون عناوين IP أو شبكات فرعية.

استخدم روابط DoH بالشكل التالي:

`https://panel.example.com/dns-query/<ClientID>`

بعد ضبط ذلك ستُرفض الطلبات التي لا تتضمن ClientID مسموحًا به، بما فيها الطلبات إلى `/dns-query` الافتراضي.

اختر معرّفات عشوائية طويلة. راجع [إرشادات AdGuard Home الرسمية للأمان](https://adguard-dns.io/kb/adguard-home/running-securely/).

</details>

---

### 7. 👤 إنشاء العميل والاشتراك تلقائيًا

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*موصى به · مفعّل افتراضيًا (`Y`)*

ينشئ المُثبّت عميلًا في 3X-UI ويولّد رابط اشتراك HTTPS شخصيًا للاتصالات المُهيّأة والمدعومة.

يظهر رابط الاشتراك في تقرير التثبيت النهائي. إذا لم تختر إنشاء العميل تلقائيًا، يمكنك إنشاؤه يدويًا من اللوحة.

---

> [!CAUTION]
> **للتثبيت الجديد أو إعادة التثبيت الكاملة فقط.** يحذف `x-ui-latest.sh` قاعدة بيانات 3x-ui السابقة وإعدادات nginx؛ **وليس أداة لتحديث VPS يعمل بالفعل**. احتفظ بنسخة Backup خارج الخادم قبل إعادة التثبيت. إذا اكتُشف تثبيت قائم، يجب كتابة `YES` بأحرف كبيرة تمامًا لتأكيد إعادة التثبيت أو الإزالة.

يعرض التقرير النهائي **عنوان اللوحة واسم المستخدم وكلمة المرور وعنوان التشخيص ورابط الاشتراك** (إذا اخترت إنشاء عميل). وعند تثبيت AdGuard Home، يعرض أيضًا عنوان الإدارة وكلمة المرور وعنوان DoH.

إذا استلزم تحديث نظام التشغيل إعادة التشغيل، فسينبّهك المُثبّت. **إعادة التشغيل الأولى يدوية** باستخدام `sudo reboot`.

## 🚀 ملفات الاتصال

| الاتصال | الحالة |
| --- | :---: |
| VLESS + REALITY | ✅ جاهز للاستخدام |
| VLESS + XHTTP | ✅ جاهز للاستخدام |
| Hysteria2 | ✅ جاهز للاستخدام |
| VLESS + WebSocket (TLS) | ✅ جاهز للاستخدام |
| Trojan + gRPC | ✅ جاهز للاستخدام |
| VLESS + XTLS Vision | ✅ اختياري |
| Amnezia WG | ✅ اختياري |

يُجهّز المُثبّت خمسة ملفات اتصال أساسية: تُفعّل REALITY وXHTTP وHysteria2 فورًا، بينما يمكن تفعيل WebSocket وTrojan gRPC لاحقًا من لوحة 3X-UI عند الحاجة.

لا يُضاف XTLS Vision وAmnezia WG إلا إذا اخترتهما أثناء التثبيت. **يجب إنشاء عملاء لاستخدام الاتصالات**، تلقائيًا خلال التثبيت أو يدويًا من اللوحة. يُنشأ عملاء Amnezia WG بصورة منفصلة.

يعتمد التوافق على تطبيق العميل وإصداره.

### الاشتراكات

تُقدَّم الاشتراكات العادية وJSON و**Mihomo / Clash** عبر nginx وHTTPS. يعيد `provider=1` الاشتراك الأصلي لمزوّدي البروكسي بدلًا من إعداد Clash كامل.


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


**لست متأكدًا من كيفية حماية خادم VPS؟** يمكنك تفعيل إعدادات الأمان المحسّنة أثناء التثبيت لضبط حماية SSH من محاولات التخمين وDNS المشفّر والتحديثات الأمنية تلقائيًا. اقرأ أولًا الشرح التفصيلي وجدول إعادة التشغيل الليلية في قسم **بدء التثبيت**.

**مهم:** احرص على حماية الوصول إلى الخادم نفسه. استخدم مفاتيح SSH، وتحقّق من نجاح الدخول بها قبل تعطيل المصادقة بكلمة المرور. لا يعطّل المُثبّت الدخول بكلمة المرور تلقائيًا.

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
