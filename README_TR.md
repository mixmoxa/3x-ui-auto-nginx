<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · 🇹🇷 **Türkçe**

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Kendi VPS sunucunuzda otomatik 3X-UI / XRAY-CORE kurulumu

**REALITY · XHTTP · HYSTERIA2 · CASCADE · ADGUARD HOME · BACKUP / RESTORE**

İki alan adı, temiz bir VPS ve kurulumu tamamlamak için yalnızca birkaç dakika.

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Debian](https://img.shields.io/badge/Debian-13-A81D33?logo=debian&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT_TR.md)

[📦 Sürümler](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [🔗 Kaskad](#cascade) · [🌐 Kamuflaj siteleri](#cover-sites) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ Destek](#support-development) · [💬 İletişim](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX**, kendi VPS sunucunuzda [3x-ui](https://github.com/MHSanaei/3x-ui) ve Xray kurmak için ücretsiz bir araçtır. İki alan adı girip tek komut çalıştırmanız yeterlidir. Kurulum aracı Nginx'i, HTTPS sertifikalarını, REALITY, XHTTP ve Hysteria2 bağlantılarını, abonelik bağlantısını ve kamuflaj sitesini hazırlar. Menüden alan adlarını değiştirebilir, yedekleri yönetebilir, iki sunucuyu Kaskad olarak bağlayabilir ve kişisel DNS sunucusu kurabilirsiniz.

**Boş sayfa yerine gerçek siteler.** Yeni kurulumlarda gezinme bağlantıları, makaleler ve görseller içeren çok sayfalı kamuflaj siteleri oluşturulur. En az 2592 farklı seçenek vardır. Hysteria2 üzerinden gelen yetkisiz HTTP/3 isteklerine de aynı site gösterilir. Docker veya ek web sunucusu gerekmez.

## ✨ Neden bu proje?

| | |
| --- | --- |
| **Dakikalar içinde hazır**<br>İki alan adı, temiz bir VPS ve tek komut. REALITY, XHTTP ve Hysteria2 yapılandırılır; panel adresi ile abonelik bağlantısı verilir. | **Normal bir web sitesi görünümü**<br>Gezinme bağlantılı, makaleli ve görselli çok sayfalı kamuflaj siteleri; en az 2592 farklı tasarım ve Hysteria2 HTTP/3 kamuflajı. |
| **İki sunuculu Kaskad**<br>Cihazlar giriş sunucusuna bağlanır ve internete başka bir ülkedeki çıkış sunucusu üzerinden erişebilir. Kurulum menüden yapılır. | **Reklamsız kişisel DNS**<br>AdGuard Home reklamları ve izlemeyi engeller. Cihazlar DNS-over-HTTPS (DoH) veya isteğe bağlı DNS-over-TLS (DoT) ile bağlanabilir. |
| **Yedekleme ve alan adı değişikliği**<br>Backup / Restore v3, istemci verilerini ve siteleri başka bir VPS'e taşır. Panel ve REALITY alan adları yeniden kurulum yapmadan değiştirilir. | **Kolay güvenlik**<br>Panel ve abonelikler HTTPS kullanır, dahili portlar yereldir, sertifikalar kendiliğinden yenilenir. SSH koruması ve VPS güvenlik güncellemeleri isteğe bağlıdır. |

**Varsayılan olarak sadece temel bağlantılar.** REALITY, XHTTP ve Hysteria2 her zaman kurulur. WebSocket, Trojan gRPC, XTLS Vision, AmneziaWG ve CDN için XHTTP yalnızca seçilirse oluşturulur. Docker gerekmez.

<a id="installation"></a>

## 🚀 Hızlı başlangıç

Ubuntu 24.04, Ubuntu 26.04 veya Debian 13 yüklü temiz bir VPS kullanın. SSH üzerinden **root** olarak bağlanın. Biri panel, diğeri REALITY için iki alan adının DNS kayıtlarını sunucu IP'sine yönlendirin. TCP **80** ve **443** ile UDP **443** dışarıdan erişilebilir olmalıdır. DoT açarsanız ayrıca TCP **853** gerekir. [Teknik ayrıntılar](#technical-details).

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Betiği çalıştırdıktan sonra **1 — English** veya **2 — Русский** seçin. Ardından ana menü açılır:

- **1 — Installation:** yeni sunucu kurma veya tam yeniden kurulum.
- **2 — Change Domains:** panel alan adını, REALITY alan adını veya ikisini yeniden kurmadan değiştirme.
- **3 — Backups:** yedek oluşturma, listeleme ve geri yükleme.
- **4 — Telegram Web Proxy Manager:** bağımsız Telegram proxy yöneticisini başlatma veya kurma.
- **5 — Cascade:** iki sunucuyu bağlama, durumu denetleme veya bağlantıyı kesme.
- **6 - My Server Details:** panel, abonelik ve AdGuard Home adresleriyle kullanıcı adlarını gösterir. Ayarları değiştirmez, parola göstermez.
- **0 — Exit:** çıkış.

Menü, etkileşimli bir SSH terminali gerektirir.

<details>
<summary><strong>Alternatif indirme — GitHub Releases kullanılamıyorsa</strong></summary>

**`main` dalında projenin alfa sürümü bulunur.** Bu sürümün kurulması önerilmez. Yukarıdaki ana komutla kararlı sürümü kullanın.

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

</details>

<a id="installation-vs-update"></a>

> [!CAUTION]
> **Kurulum, güncelleme değildir!**
>
> Betiği **parametresiz** yeniden çalıştırmak yöneticiyi açar; sunucuyu yeniden kurmaz. Ancak **Installation**, temiz bir VPS veya tam yeniden kurulum içindir.
>
> Mevcut bir kurulum algılanırsa betik, yönetilen verilerin silineceğini bildirir ve tam olarak **YES** yazmanızı ister. Yeniden kurulum 3X-UI veritabanını ve nginx yapılandırmasını değiştirir. Ayrıca:
> - önceki kurulumda XTLS Vision varsa ve bu kez seçmezseniz (veya farklı bir alan adı seçerseniz), yükleyicinin oluşturduğu eski Vision sertifikası silinir. YES sorulmadan önce bunun uyarısı gösterilir;
> - önceki kurulumda AmneziaWG varsa ve tekrar seçilmezse 8443/udp portu kapanır (bunun için ayrı uyarı yoktur).
>
> **Backup kopyanızı önceden VPS dışında saklayın.**
>
> **Change Domains** ve **Backups**, paneli yeniden kurmayan ayrı işlemlerdir.

<details>
<summary><strong>Nasıl güncellenir?</strong></summary>

- **3X-UI ve Xray:** panelin kendi güncelleme araçlarını kullanın. Yeni sürümlerin bu projenin yapılandırmasıyla uyumluluğu henüz doğrulanmamış olabilir.
- **3X-UI AUTO NGINX:** mevcut kurulu sistemin yerinde güncellenmesi desteklenmez. **5 — Cascade** gibi yeni yönetici özelliklerini kullanmak için güncel betiği indirip ilgili işlemi seçin. Yönetici, mevcut yapılandırmanın uyumluluğunu kontrol eder.
- **Backup / Restore:** verileri yedekler ve geri yükler; kurulu sistemi güncellemez.
- **2.7.0 öncesinde kurulan sunucular:** **6 - My Server Details** erişilebilen eski bilgileri gösterir. Rastgele DoH yolu, ek bağlantı soruları ve DoT yalnızca yeni kurulumda kullanılabilir. Mevcut WebSocket ve Trojan gRPC yapılandırmaları değişmez ve eski DoH adresi `/dns-query` olarak kalır.

**Yalnızca güncelleme amacıyla Installation seçmeyin!** nginx, Linux çekirdeği ve diğer sistem paketlerini işletim sisteminizin araçlarıyla güncelleyin.

</details>

Kurulumda yedi ana soru vardır; bazılarının ek soruları bulunur. Varsayılan yanıtlar çoğu kullanıcı için uygundur.

| No | Soru | Varsayılan | İşlev |
| --- | --- | :---: | --- |
| 1 | Panel alan adı | - | Panel, abonelik ve kamuflaj sitesi |
| 2 | REALITY alan adı | - | REALITY bağlantısı ve kamuflaj sitesi |
| 3 | Gelişmiş VPS güvenliği | `Y` | Fail2ban, VPS'nin kendi şifreli DNS'i ve güvenlik güncellemeleri |
| 4 | Ek bağlantılar (ayrı ayrı seçilir) | `N` | WebSocket, Trojan gRPC, XTLS Vision, AmneziaWG ve CDN XHTTP |
| 5 | Rus siteleri için WARP | Rusça menüde `Y` | VPS IP adresini gizleme |
| 6 | AdGuard Home | `N` | DoH ve isteğe bağlı DoT ile kişisel DNS |
| 7 | İstemci ve abonelik | `Y` | Kurulum sonunda abonelik bağlantısı |

4.1 ile 4.4 arasındaki sorular yalnızca ek bağlantıları etkinleştirirseniz sorulur.

---

### 1. 🌐 3X-UI panel alan adı

> `Enter the domain for your 3X-UI panel:`

Yönetim paneline, aboneliklere ve ek web hizmetlerine erişmek için kullanacağınız alan adını girin.

---

### 2. 🛰️ VLESS REALITY alan adı

> `Enter the domain for VLESS REALITY:`

REALITY için ikinci bir alan adı girin. Her iki alan adının DNS kayıtları da VPS'inizin IP adresine işaret etmelidir.

<details>
<summary>ℹ️ Ek çalıştırma parametreleri</summary>

Her iki alan adını etkileşimli olarak girmek yerine komut satırından belirtebilirsiniz:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

`panel.example.com` ve `reality.example.com` değerlerini kendi alan adlarınızla değiştirin. İsteğe bağlı özellikler kurulum sırasında yine sorulur.

</details>

---

### 3. 🔐 Gelişmiş VPS güvenliği

> `Enhance VPS security? [Y/n]:`

*Deneyimsiz kullanıcılara önerilir · Varsayılan olarak açık (`Y`)*

Kurulum aracı SSH koruması için Fail2ban'ı, şifreli sistem DNS'ini (DoT) ve otomatik güvenlik güncellemelerini yapılandırır. Koşullar uygunsa, ek güvenlik seçiminizden bağımsız olarak 1 GiB swap dosyası da oluşturur.

**Bu seçeneği etkinleştirmeden önce aşağıdaki ayrıntıları**, özellikle otomatik yeniden başlatma takvimini okuyun.

<details>
<summary>🔐 Güvenlik ayarlarının ayrıntıları</summary>

`Y` seçildiğinde ek güvenlik ayarları uygulanır. Swap yapılandırması bu seçimden bağımsızdır:

- **1 GiB swap.** Etkin swap yoksa, dosya sistemi destekleniyorsa ve en az 4 GiB boş alan varsa kurulum aracı swap dosyasını oluşturup etkinleştirir. Mevcut swap ayarları değiştirilmez. Koşullar sağlanmazsa kurulum durdurulmadan bu adım atlanır.
- **SSH koruması — Fail2ban.** Gerçek SSH dinleme portlarına göre tekrarlanan başarısız giriş denemelerini sınırlar. Mevcut SSH kimlik doğrulama ayarlarını değiştirmez.
- **Şifreli DNS (DoT).** Genel Cloudflare ve Google DNS sunucuları `systemd-resolved` üzerinden zorunlu DNS-over-TLS kullanır. Arayüz/VPN DNS yolları ve arama alanları korunur; bunların sorguları şifrelenmeden kalabilir. DoT hazırlığı başarısız olur ve önceki DNS başarıyla geri yüklenirse ana kurulum, Fail2ban ve otomatik güncellemeler DoT’den bağımsız olarak devam eder; sonuç ekranı hatayı bildirir ve çıkış kodu sıfırdan farklı olur.
- **Otomatik güvenlik güncellemeleri.** Paket listeleri 02:30'da güncellenir, güvenlik güncellemeleri 02:50'de yüklenir.
- **Otomatik yeniden başlatma — 04:38.** Güncellemeler yeniden başlatma gerektiriyorsa sunucu bu saatte, **aktif kullanıcı oturumları olsa bile** yeniden başlatılır; mevcut bağlantılar kesilebilir.

Saatler VPS'in yerel saat dilimine göredir.

Değişikliklerden önce mevcut ayarların uyumluluğu denetlenir. Güvenlik yapılandırması başarısız olursa kontrollü geri alma uygulanır.

**Önemli:** Bu seçenek SSH parola girişini kapatmaz ve sunucu yönetiminin yerini almaz. Önce SSH anahtarıyla girişi ayarlayın, ardından parola ile kimlik doğrulamayı kendiniz kapatın.

</details>

---

### 4. 🧩 Ek bağlantılar

> `Set up additional connections? [y/N]:`

*Varsayılan olarak kapalı (`N`)*

REALITY, XHTTP ve Hysteria2 otomatik kurulur. İsterseniz VLESS WebSocket, Trojan gRPC, XTLS Vision, AmneziaWG ve CDN için XHTTP bağlantılarını ayrıca seçebilirsiniz.

> [!WARNING]
> Bu bağlantılar her ülkede veya ağda çalışmayabilir. Kullanım sorumluluğu size aittir. Emin değilseniz `N` yanıtlayın.

`N` seçilirse ek bağlantılar oluşturulmaz ve 4.1-4.4 soruları atlanır. `y` yanıtıyla her biri ayrı ayrı sorulur.

#### 4.1. WebSocket ve Trojan gRPC

> `Set up legacy VLESS WebSocket and Trojan gRPC connections? [y/N]:`

`y` seçilirse iki bağlantı da etkin olarak oluşturulur. `N` seçilirse hiçbiri oluşturulmaz.

---

<a id="4--vless-xtls-vision"></a>

#### 4.2. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*Ek bağlantı · Varsayılan olarak kapalı (`N`)*

REALITY bağlantınız kararsızsa veya ağınızda engelleniyorsa yararlı olabilecek, TLS üzerinden çalışan alternatif bir VLESS bağlantısıdır. 3X-UI panelinde ayrı bir profil olarak oluşturulur.

> [!IMPORTANT]
> **XTLS Vision üçüncü ve ayrı bir alan adı gerektirir**; bu alan adı panel ve REALITY alan adlarından farklı olmalıdır. DNS kaydı VPS IP adresine yönlendirilmelidir. HTTPS sertifikası ve nginx yönlendirmesi otomatik yapılandırılır.
>
> `Y` seçildikten sonra kurulum aracı bu alan adını ayrıca sorar: `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

<a id="5--amnezia-wg"></a>

#### 4.3. 🔑 Amnezia WG

> `Set up an additional AmneziaWG connection? [y/N]:`

*Ek bağlantı · Varsayılan olarak kapalı (`N`)*

3X-UI panelinde ayrı bir AmneziaWG bağlantısı oluşturulur. Ek alan adı gerekmez.

<details>
<summary>ℹ️ Amnezia WG hakkında</summary>

Kurulum aracı **UDP/8443** üzerinden AmneziaWG 3.1'i yapılandırır ve gerekli UFW kuralını otomatik ekler.

Kurulumdan sonra 3X-UI panelinden bir istemci oluşturun ve uyumlu bir Amnezia uygulaması için yapılandırmayı veya `vpn://` bağlantısını alın.

Kurulum aracı sunucu bağlantısını oluşturur; AmneziaWG istemcilerini otomatik oluşturmaz.

Yapılandırma ve gerekli güvenlik duvarı kuralı **Backup / Restore v3** kapsamındadır.

</details>

---

<a id="xhttp-cdn"></a>

#### 4.4. 🌐 CDN için VLESS + XHTTP

> `Add an additional CDN-compatible XHTTP connection? [y/N]:`

*Ek bağlantı · Varsayılan olarak kurulmaz (`N`)*

CDN üzerinden kullanıma önceden hazırlanmış, packet-up modunda XHTTP taşımasını kullanan ayrı bir VLESS bağlantısı oluşturulur. Bağlantı 3X-UI panelinde devre dışı bırakılmış olarak oluşturulur.

Panelin mevcut HTTPS alan adı kullanılır; ek alan adı veya sertifika gerekmez. Etkinleştirdikten sonra bağlantı CDN olmadan doğrudan da kullanılabilir.

CDN kullanmak için sağlayıcınızı kendiniz yapılandırmalı ve 3X-UI içindeki Host ayarlarını değiştirmelisiniz. Kurulum aracı CDN hizmetlerini yapılandırmaz; kendi ihtiyaçlarınıza uyarlayabileceğiniz hazır bir sunucu profili sağlar.

---

<a id="warp-ru"></a>

### 5. 🌐 Rus siteleri için Cloudflare WARP

> `Route Russian websites through Cloudflare WARP to hide your VPS IP? [y/N]:`

*İsteğe bağlı yönlendirme · Rusça menüde varsayılan olarak açık (`Y`), İngilizce menüde kapalı (`N`)*

Bu VPS'i Kaskad giriş sunucusu olarak kullanacaksanız `N` seçin. WARP giriş sunucusuyla uyumlu değildir, ancak çıkış sunucusunda kullanılabilir.

`Y` seçildiğinde kurulum aracı Cloudflare WARP (MASQUE) yapılandırır. Böylece Rus web siteleri ve bazı ağ hizmetleri VPS'inizin IP adresi yerine Cloudflare'a ait bir IP adresi görür. Bu, VPS IP adresinizi korumak için gereklidir.

Bu ayar yalnızca VPS üzerinden geçen trafiği etkiler. Bir uygulama siteye doğrudan bağlanıyorsa sunucudaki WARP bu bağlantıyı etkilemez.

Özellik etkinleştirildiğinde kurulum aracı Cloudflare'a bir cihaz kaydeder ve hizmet koşullarını kabul eder.

WARP yapılandırması başarısız olursa kurulum WARP olmadan devam eder ve son raporda kısmi tamamlanma bildirilir. Önceki yapılandırmaya geri dönüş doğrulanamıyorsa panelden Xray'in çalıştığını kontrol edin.

<details>
<summary>ℹ️ <strong>Hangi siteler WARP kullanır ve yapılandırma nasıl kontrol edilir?</strong></summary>

Kurulum aracı, Xray yapılandırmasına `warp-masque` adlı bir giden bağlantı ve üç yönlendirme kuralı ekler:

- **WARP - RU:** `geosite:category-ru` listesindeki Rus alan adları.
- **WARP - RU2:** `geoip:ru` listesindeki IP adresleri.
- **WARP - RU3:** `ipify.org`, `ifconfig.me`, `checkip.amazonaws.com`, `ipapi.is`, `iplocate.io`, `ip.sb` ve `2gis.com`.

Kurallar yönlendirme listesinin sonuna eklenir; önceki kurallar önceliğini korur. Bu, istemciler için ayrı bir bağlantı profili veya sistem genelinde çalışan bir VPN değildir: yönlendirme Xray içinde yapılır.

Kurulumdan sonra 3X-UI panelinde **Xray → Outbounds** bölümünde `warp-masque` bağlantısını, **Xray → Routing** bölümünde ise yukarıdaki üç kuralı kontrol edin. Ayarlar, 3X-UI yapılandırmasıyla birlikte Backup v3 içinde saklanır.

</details>

---

<a id="7--adguard-home--dns-over-https"></a>
<a id="6--adguard-home--dns-over-https"></a>

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS ve DNS-over-TLS

> `Install and configure AdGuard Home? [y/N]:`

*Ek DNS sunucusu · Varsayılan olarak kapalı (`N`)*

Reklam ve izleyicileri engellemek, istemcileri yönetmek ve DNS sorgularını şifrelemek için kişisel DNS sunucusu. Cihazlar DoH veya isteğe bağlı DoT kullanabilir; örneğin Android'in «Özel DNS» ayarıyla.

<details>
<summary>ℹ️ <strong>AdGuard Home ve erişim ayarları</strong></summary>

Ek alan adı gerekmez.

Kurulum sonrasında şunlar kullanılabilir:

- **AdGuard Home paneli:** `https://panel.example.com/adg-.../`, her kurulum için rastgele yol.
- **DNS-over-HTTPS:** `https://panel.example.com/dns-XXXXXXXXXXXX`. `dns-XXXXXXXXXXXX` yolu her kurulumda rastgele oluşturulur.
- **DNS-over-TLS** (seçildiyse): `panel.example.com`, port 853.

Adresler kurulum raporunda ve daha sonra **6 - My Server Details** bölümünde gösterilir. AdGuard Home parolası sonradan görüntülenemez; kurulumda kaydedin.

Genel TCP ve UDP **53** portları açılmaz. AdGuard Home için ek genel **853** portu yalnızca DoT etkinse açılır. Yapılandırma ve veriler **Backup / Restore v3** kapsamındadır. 2.7.0 öncesi kurulumlar `https://panel.example.com/dns-query` adresini kullanmaya devam eder.

**⚠️ Güvenlik önerisi**

Rastgele DoH yolunu tahmin etmek zordur, ancak adres cihaz ayarlarında saklanır. Her cihaz için ayrı [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) oluşturun.

AdGuard Home'da **Settings → DNS settings → Access settings → Allowed clients** yolunu açın ve oluşturduğunuz ClientID'leri ekleyin. IP adresi veya alt ağ girmeniz gerekmez; DoT kullanıyorsanız istisna olarak `127.0.0.1` eklenmelidir.

Örnek DoH adresi:

`https://panel.example.com/dns-XXXXXXXXXXXX/<ClientID>`

İzin verilen ClientID'si olmayan istekler reddedilir. Uzun ve rastgele kimlikler kullanın. [AdGuard Home güvenlik kılavuzuna](https://adguard-dns.io/kb/adguard-home/running-securely/) bakın.

**DoT ve izin verilen istemciler:** DoT, ClientID iletmez. İzin verilen istemciler listesi açıldığında DoT sorguları reddedilir ve DoT çalışmaz. Yeniden çalışması için `127.0.0.1` adresini listeye ekleyin. Böylece sunucu adresini bilen herkes, liste yokken olduğu gibi DoT kullanabilir.

**v2.4.1** sürümünden itibaren yeni kurulumlarda AdGuard Home web arayüzünden güncellenebilir. Daha önceki sürümle yüklediyseniz VPS üzerinde şu komutu çalıştırın:

```bash
sudo bash -c 'set -euo pipefail; umask 077; d=$(mktemp -d); trap '\''rm -rf -- "$d"'\'' EXIT; cd "$d"; u=https://github.com/xPROMSx/3x-ui-auto-nginx/releases/download/v2.4.2; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh" -o x-ui-latest.sh; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh.sha256" -o x-ui-latest.sh.sha256; sha256sum --check --strict x-ui-latest.sh.sha256; bash ./x-ui-latest.sh --enable-agh-updates'
```

</details>

#### 6.1. DNS-over-TLS (DoT)

> `Enable DNS-over-TLS (DoT) for your devices? [y/N]:`

DoT özellikle Android'in yalnızca alan adı alan «Özel DNS» ayarında kullanılır. İhtiyacınız yoksa `N` olarak bırakın.

- Yalnızca AdGuard Home ile birlikte yeni kurulumda seçilebilir.
- DoT, `panel.example.com` adresinde **853** portunu kullanır. UFW kuralı otomatik eklenir, panel alan adının sertifikası kullanılır.
- **853 portu tüm internete açıktır.** DoT ClientID taşımaz; sunucu adresini bilen herkes bağlanabilir. Aşırı yükü önlemek için kaynak IP başına eşzamanlı bağlantı sayısı yaklaşık 50 ile sınırlıdır.
- DoT sorguları AdGuard Home günlüğünde `127.0.0.1` olarak görünür, çünkü Nginx bunları aynı sunucuda yerel olarak iletir. Günlükten farklı DoT cihazları ayırt edilemez.
- İzin verilen istemciler listesi etkinleştirilirse DoT çalışmaz. Çözüm yukarıdaki ClientID açıklamasındadır.
- DoT ayarları Backup / Restore v3 ile saklanır ve alan adı değişikliklerinde korunur.

**Android bağlantısı.** Ayarlarda «Özel DNS» seçeneğini bulun, ana bilgisayar adı modunu seçin ve panel alan adını girin.

**DoT'yi kapatmak.** Sunucuda root olarak şu komutu çalıştırın:

```bash
ufw delete allow 853/tcp
```

853 portu kapanır, diğer hizmetler eskisi gibi çalışır. DoT'yi tamamen kaldırmak için sunucuyu yeniden kurmak gerekir.

---

<a id="7--otomatik-istemci-ve-abonelik-oluşturma"></a>

<a id="8--otomatik-istemci-ve-abonelik-oluşturma"></a>

### 7. 👤 Otomatik istemci ve abonelik oluşturma

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*Önerilir · Varsayılan olarak açık (`Y`)*

Kurulum aracı 3X-UI panelinde bir istemci oluşturur ve yapılandırılmış, desteklenen bağlantılar için kişisel bir HTTPS abonelik bağlantısı üretir.

Abonelik bağlantısı kurulum sonu raporunda gösterilir. Bu seçeneği reddederseniz istemcileri daha sonra panel üzerinden elle oluşturabilirsiniz.

---

Kurulum sonunda **panel adresi, kullanıcı adı ve parola, tanılama adresi ve abonelik bağlantısı** (otomatik istemci oluşturulduysa) gösterilir. AdGuard Home seçildiyse yönetim adresi, parolası ve DoH uç noktası da görüntülenir. WARP yapılandırmasının sonucu da raporda gösterilir.

İşletim sistemi güncellemesi yeniden başlatma gerektiriyorsa kurulum aracı bunu bildirir. **İlk yeniden başlatma elle yapılır:** `sudo reboot`.

<a id="cover-sites"></a>

## 🌐 Kamuflaj siteleri ve HTTP/3

**Basit yer tutucu sayfalar yerine gerçek web siteleri.** Yeni kurulumlarda panel ve REALITY için otomatik olarak farklı, çok sayfalı siteler oluşturulur. Çalışan gezinme bağlantıları, görseller ve mobil uyumlu tasarımlarla birlikte en az 2592 hazır tasarım ve metin kombinasyonu bulunur. İsteğe bağlı XTLS Vision için ayrı bir site seçilir.

**Her kurulumun görünümü farklıdır.** Site adları, renkler, görseller, simgeler ve metinler otomatik olarak kişiselleştirilir. Ek sayfalarda farklı içerikler ve yayın tarihleri bulunur. Seçilen tasarım Backup/Restore ve alan adı değişiklikleri sırasında korunur.

**HTTP/3 kamuflajlı Hysteria2.** REALITY alan adında TCP üzerinden normal HTTPS ve UDP üzerinden kimlik doğrulaması yapılmamış HTTP/3 istekleri aynı eksiksiz web sitesini görüntüler. Panel ve abonelikler, halka açık HTTP/3 kamuflajından ayrı tutulur.

## 🚀 Bağlantı profilleri

| Bağlantı | Ne zaman oluşturulur |
| --- | :---: |
| VLESS + REALITY | ✅ Her zaman, etkin |
| VLESS + XHTTP | ✅ Her zaman, etkin |
| Hysteria2 | ✅ Her zaman, etkin |
| VLESS + WebSocket (TLS) | 🔧 İsteğe bağlı, seçilirse etkin |
| Trojan + gRPC | 🔧 İsteğe bağlı, seçilirse etkin |
| VLESS + XTLS Vision | 🔧 İsteğe bağlı, üçüncü alan adı gerekir |
| Amnezia WG | 🔧 İsteğe bağlı |
| VLESS + XHTTP for CDN | 🔧 İsteğe bağlı, kapalı oluşturulur |

REALITY, XHTTP ve Hysteria2 kurulumdan hemen sonra çalışır. Diğer bağlantılar yalnızca 4. adımdaki ek bağlantı sorusuna `y` yanıtı verilirse oluşturulur. Seçilmeyen bağlantılar oluşturulmaz.

CDN için XHTTP kapalı oluşturulur; etkinleştirilip istemci bağlanana kadar aboneliklerde yer almaz. 2.7.0 öncesinde kurulmuş sunuculardaki WebSocket ve Trojan gRPC ise eskisi gibi mevcut ve devre dışı kalır.

İstemcileri kurulum sırasında veya daha sonra panelde oluşturabilirsiniz. AmneziaWG için ayrı istemci gerekir. Uyumluluk kullanılan istemci uygulamasına ve sürümüne, CDN XHTTP için ayrıca CDN sağlayıcısına bağlıdır.

### Abonelikler

Standart abonelikler, JSON ve **Mihomo / Clash** nginx üzerinden HTTPS ile sunulur. `provider=1`, tam Clash yapılandırması yerine proxy provider'lar için özgün aboneliği döndürür.


<a id="change-domains"></a>

## 🌐 Alan adlarını değiştirme

Ana menüden **2 — Change Domains** seçin. Panel alan adını, REALITY alan adını veya ikisini yeniden kurulum olmadan değiştirebilirsiniz. Yeni DNS kayıtları VPS'yi göstermeli ve sertifika alımı için TCP/80 erişilebilir olmalıdır. Alan adları birbirinden ve Vision alan adından farklı olmalıdır.

Değişikliklerden önce otomatik olarak tam Backup v3 oluşturulur. İstemciler, anahtarlar, ayarlar ve trafik istatistikleri korunur. Vision alan adı değişmez. İşlemden sonra abonelik URL'lerini ve istemci yapılandırmalarını güncellemeniz gerekebilir.

Yalnızca tanınan proje kurulumları desteklenir; buna uyumlu v2.1.7 kurulumları da dahildir. Hata olursa **yedekleri veya kurtarma verilerini silmeyin**. `ROLLBACK_UNVERIFIED` görürseniz işlemi durdurun ve tanılama bilgilerini saklayın. [Ayrıntılar, sınırlamalar ve kurtarma](docs/MANAGER.md#change-domains).

## 💾 Yedekleme ve geri yükleme

Ana menüde **3 — Backups** bölümünü açarak yedek oluşturabilir, arşivleri listeleyebilir veya Restore çalıştırabilirsiniz. İşletim sistemini yeniden kurduktan sonra ya da başka bir VPS'ye taşınırken yedeği kullanabilirsiniz. Geri yükleme için işletim sistemi, sürümü ve işlemci mimarisi yedekle aynı olmalıdır.

Yeni bir VPS'te menüden Restore yapıldığında otomatik sistem güncellemelerinin bitmesi beklenir (en fazla 60 dakika); bu sırada sunucuyu yeniden başlatmayın.

Komut satırından root olarak şunları çalıştırabilirsiniz:

```bash
# Yeni yedek oluştur
x-ui-backup backup

# Kullanılabilir yedekleri listele
x-ui-backup list

# Seçilen yedeği geri yükle
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

Arşivler `/var/backups/x-ui/` dizinine kaydedilir.

> **Yedekler hassas bilgiler içerir:** istemci veritabanı, parolalar ve sertifika özel anahtarları. Bir kopyayı mutlaka **VPS dışında** saklayın ve yalnızca güvendiğiniz arşivleri geri yükleyin.

[Yeni bir VPS'e geri yükleme](#restore-on-new-vps).

<a id="cascade"></a>

## 🔗 İki sunuculu Kaskad

Kaskad, 3X-UI AUTO NGINX kurulu iki VPS'i birbirine bağlar: cihazlar giriş sunucusuna bağlanır ve internete çıkış sunucusu üzerinden erişir. Bir VPS'e bağlanmakta sorun yaşıyorsanız veya başka bir ülkedeki sunucu üzerinden internete çıkmanız gerekiyorsa yararlı olabilir.

**Cihaz → Giriş VPS → Çıkış VPS → İnternet**

Rus siteleri ve Rus IP adreslerine giriş sunucusundan doğrudan erişilir. Kurulumdan sonra giriş VPS'inin yönlendirme kurallarından bu davranışı kapatabilirsiniz. Önceki yönlendirme kurallarının eşleşmediği diğer trafik çıkış sunucusundan geçer.

Kurulum için ana menüden **5 — Cascade** seçin. Yapılandırma dosyalarını elle düzenlemeniz gerekmez.

<details>
<summary><strong>Kaskad kurulumu, durum kontrolü ve bağlantıyı kesme</strong></summary>

### Gerekenler

- 3X-UI AUTO NGINX çalışan iki VPS.
- Her sunucunun 3X-UI panel kullanıcı adı ve parolası.
- Menüde **5 — Cascade** bulunan güncel kurulum betiği.
- Giriş sunucusunda WARP kurulu olmamalıdır (elle kaldırabilirsiniz).

### 1. Çıkış sunucusunda anahtar oluşturma

İnternete çıkış için kullanacağınız VPS'te güncel kurulum betiğini çalıştırın.

**5 — Cascade → 1 — Create key (exit server)** seçin.

3X-UI panel kullanıcı adı ve parolasını girin. Giriş sırasında karakterler gizlenir ve bilgiler kaydedilmez. Yönetici, mevcut REALITY bağlantısında `cascade` adlı bir istemci oluşturur ve `vless://` ile başlayan bir anahtar bağlantısı gösterir.

Bağlantıyı kopyalayın. İkinci sunucuda kullanacaksınız.

**Anahtar bağlantısını paylaşmayın:** bu bağlantıya sahip olanlar istemciyi kullanarak bağlanabilir.

Mevcut istemciler değişmez.

### 2. Giriş sunucusunu bağlama

Cihazlarınızın bağlandığı VPS'te güncel kurulum betiğini çalıştırın.

**5 — Cascade → 2 — Connect exit server (entry server)** seçin.

3X-UI panel kullanıcı adı ve parolasını girin (kaydedilmezler), ardından ilk adımdaki anahtar bağlantısını yapıştırın. Yapıştırdığınız bağlantı terminalde görünür ancak kaydedilmez.

Yönetici önce çıkış sunucusuyla bağlantıyı test eder. Başarılı olursa `cascade-exit` adlı giden bağlantıyı ve üç `CASCADE` yönlendirme kuralını ekler.

Rus siteleri ve IP adresleri, ilgili kuralları daha sonra kapatmadığınız sürece giriş sunucusundan doğrudan açılır. Diğer uygun trafik çıkış sunucusundan geçer.

**Ayarlar uygulanırken tüm kullanıcıların bağlantısı birkaç saniyeliğine kesilebilir.** Denetim başarısız olursa yönetici önceki yapılandırmayı geri yüklemeyi dener ve sonucu bildirir.

Mevcut istemci bağlantıları ve abonelikler kullanılmaya devam eder. Kaskad için ayrı istemci profili oluşturmanız gerekmez.

### 3. Durumu kontrol etme

Her VPS'te **5 — Cascade → 3 — Status** bölümünü açın.

Yönetici diğer işlemlerde olduğu gibi panel kullanıcı adını ve parolasını sorar.

Sunucudaki giriş ve çıkış rollerinin yapılandırılıp yapılandırılmadığını ve Xray'in çalışıp çalışmadığını gösterir. Bu işlem ayarları değiştirmez.

### 4. Kaskad bağlantısını kesme

İlgili VPS'te **5 — Cascade → 4 — Disable** bölümünü açın.

**Giriş sunucusunda** yönetici `cascade-exit` bağlantısını ve üç `CASCADE` kuralını kaldırmayı önerir. Diğer bağlantılar ve panel kuralları korunur.

**Çıkış sunucusunda** yalnızca `cascade` istemcisi silinir. Bu anahtarı kullanan giriş sunucuları artık ilgili çıkış üzerinden trafik gönderemez.

Her rolün kaldırılması ayrı onay gerektirir. Giriş sunucusundaki değişiklikler kullanıcı bağlantılarını kısa süreliğine kesebilir.

### Bilinmesi gerekenler

- **WARP:** giriş sunucusuyla uyumlu değildir. Yapılandırılmışsa bağlamadan önce 3X-UI panelinden giden bağlantısını ve kurallarını kaldırın. Çıkış sunucusunda kullanılabilir.
- **AmneziaWG:** bu bağlantılar çıkış sunucusundan geçmez.
- **Yönlendirme kuralları:** daha önce tanımlanan kurallar trafiğin bir kısmını başka yollara yönlendirebilir. Yönetici bağlanmadan önce uyarır.
- **Çıkışa ulaşılamazsa:** bu çıkışa yönlendirilen trafik bağlantı geri gelene kadar çalışmaz. Otomatik yedek çıkış yoktur.
- **Vision üzerinden QUIC:** UDP/443 bu Kaskad üzerinden geçmez.
- **Alan adı değişikliği:** çıkış VPS'inin alan adlarını değiştirirseniz giriş sunucusundan yeniden bağlamanız gerekir.

### Yedeklemeler

Backup v3, Kaskad ayarlarını kaydeder. Giriş sunucusunda yedek geri yüklendiğinde Kaskad yapılandırması diğer 3X-UI verileriyle birlikte korunur.

Kaskad, REALITY, XHTTP ve Hysteria2 ile iki gerçek VPS üzerinde test edilmiştir. Tüm istemci uygulamaları ve yapılandırmalarla uyumluluğu doğrulanmamıştır.

Hata bulursanız [GitHub'da bildirin](https://github.com/xPROMSx/3x-ui-auto-nginx/issues).

</details>

## 🔐 Güvenlik

Hizmet arayüzleri doğrudan internete açılmaz: panel, abonelikler ve ek hizmetlere nginx ve HTTPS üzerinden erişilir; dahili portlar yalnızca yereldir. Sadece DNS-over-TLS (DoT) etkinleştirirseniz ek hizmet portu 853 açılır. İstemci bağlantı portları doğası gereği açıktır: TCP ve UDP 443, AmneziaWG seçilirse ayrıca UDP 8443.


**VPS'inizi nasıl güvenceye alacağınızdan emin değil misiniz?** Kurulum sırasında gelişmiş güvenlik seçeneğini etkinleştirerek SSH kaba kuvvet saldırılarına karşı korumayı, şifreli DNS'i ve güvenlik güncellemelerini otomatik ayarlayabilirsiniz. Önce **Hızlı başlangıç** bölümündeki ayrıntıları ve gece yeniden başlatma takvimini okuyun.

**Önemli:** Sunucuya erişimi de koruyun. SSH anahtarları kullanın ve anahtarla girişin çalıştığını doğruladıktan sonra parola ile kimlik doğrulamayı kapatın. Kurulum aracı bunu otomatik yapmaz.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager), HTTPS, kamuflaj sitesi ve geri alma destekli güncellemelerle kendi Telegram WEB Proxy sunucunuzu kurmanızı sağlayan bağımsız bir projedir.

**TWPM, 3X-UI'nin varsayılan kurulumuna dahil değildir.** Ana menüdeki 4. seçenekle yöneticiyi başlatabilir veya onay verdikten sonra ayrı olarak kurabilirsiniz. İki proje bağımsız yönetilir.

Telegram Web Proxy Manager, Ubuntu 24.04 ve 26.04 üzerinde kurulabilir.

<a id="technical-details"></a>

## ⚙️ Teknik ayrıntılar ve uyumluluk

- **Sistemler:** Ubuntu 24.04, Ubuntu 26.04 ve Debian 13.
- **UFW:** 80/tcp, 443/tcp ve 443/udp portlarına izin verir (AmneziaWG seçildiğinde 8443/udp, DoT seçildiğinde 853/tcp). Installation sırasında UFW yalnızca SSH erişimi doğrulandıktan sonra etkinleştirilir; bu güvenli değilse uyarıyla kapalı kalır. Restore sonrasında yönetici UFW'yi **yalnızca ayrıca seçildiğinde** ve güvenlik kontrolleri başarılı olduğunda etkinleştirebilir. `x-ui-backup restore` komutu UFW'yi etkinleştirmez.
- **Sertifikalar:** Let's Encrypt webroot ve `certbot.timer`, nginx'i durdurmadan sertifikaları otomatik yeniler.
- **3x-ui sürümü:** kurulum aracı, varsayılan olarak 3x-ui Auto Nginx ile uyumluluğu kapsamlı biçimde doğrulanmış en yeni sürümü yükler. Bu, resmi projenin en son yayımladığı sürüm olmayabilir. Kurulum sonrasında 3x-ui'nin kendi güncelleme mekanizmasını kullanabilirsiniz; ancak yeni sürümün mevcut yapılandırmayla uyumluluğu henüz doğrulanmamış olabilir. `-version <tag>` ile başka bir kararlı sürümü açıkça seçebilirsiniz (desteklenen en düşük sürüm v3.8.0); doğrulanmamış uyumluluk için uyarı gösterilir.

<a id="restore-on-new-vps"></a>

### Yeni bir VPS'e geri yükleme

İşletim sistemi, sürümü ve işlemci mimarisi yedektekiyle aynı olmalıdır. VPS IP adresi değişirse alan adlarının DNS kayıtlarını güncelleyin. **`x-ui-latest.sh` dosyasını çalıştırmayın**; yalnızca yedekleme aracını kurup güvenilir bir arşivi geri yükleyin:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

SSH, işletim sistemi yapılandırması ve temel güvenlik duvarı yöneticinin sorumluluğundadır. v2 yedek arşivleri için ilgili eski sürümün aracını kullanın.

## 🤝 Katkılar ve köken

Bu proje, mozaroc'un [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro) projesini temel alır. Bu proje, [x-ui-pro](https://github.com/mozaroc/x-ui-pro) çatallanmasından doğmuş ve GFW4Fun'ın özgün [x-ui-pro](https://github.com/GFW4Fun/x-ui-pro) projesinden gelmiştir. Mevcut proje artık bağımsız olarak geliştirilmektedir. Fork sonrasında nginx/SNI yönlendirmesi ile XHTTP yapılandırması kapsamlı biçimde yeniden düzenlenmiş, TLS sertifikalarının alınması ve otomatik yenilenmesi yeniden tasarlanmış ve kurtarma/geri alma özellikli Backup / Restore v3 eklenmiştir. Ayrıca UDP/443 üzerinde Hysteria2 desteği sağlanmış ve tespit edilen güvenlik sorunları giderilmiştir.

Resmî panel [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) projesinden sağlanır. Üçüncü taraf bileşenlerin sahipleri haklarını ve mevcut lisanslarını korur.

xPROMSx tarafından geliştirilen özgün katkılar ve değişiklikler [GNU GPL-3.0-only](LICENSE) kapsamında sunulur. Copyright (C) 2026 xPROMSx contributors. Bu lisans yalnızca söz konusu materyaller üzerinde sahip olduğumuz hakları kapsar; devralınmış kodu yeniden lisanslamaz veya deponun tamamının GPL kapsamında olduğunu göstermez. Ayrıntılar için [lisans kapsamına ve üçüncü taraf bildirimlerine](THIRD_PARTY_NOTICES.md) bakın.

**Kodumuzu kullanmak istiyorsanız.** Bu projeyi kurup kullanmak için ayrıca bir şey yapmanız gerekmiyor; proje eskisi gibi ücretsiz. Kendi sürümünüzü yayımlıyor veya kodumuzu başka bir projeye aktarıyorsanız `© xPROMSx · github.com/xPROMSx/3x-ui-auto-nginx` ibaresini README dosyasında, etkileşimli bir yükleyiciniz varsa onun açılış ekranında veya ana menüsünde de gösterin. Sürümün değiştirildiğini açıkça belirtin ve çalışmalarımızı kendinize aitmiş gibi göstermeyin. Ayrıntılı koşullar: [docs/NOTICE.md](docs/NOTICE.md).

<a id="windows-flag-emojis"></a>

## 🖥️ Windows 11'de ülke bayrakları

Windows 11'de **3x-ui** panelini **Chrome, Edge veya Brave** ile açtığınızda ülke bayrakları yerine iki harfli kodlar (`FI`, `DE`, `US`) görüyorsanız, küçük yan projemiz [**Flag Emojis Windows Installer**](https://github.com/xPROMSx/flag-emojis-windows-installer) size yardımcı olabilir. Bayrakların görüntülenmesini sağlar, Windows'un özgün yazı tipini korur ve yapılan değişiklikleri geri alma imkânı sunar.

<a id="support-development"></a>

## ❤️ Geliştirmeyi destekleyin

Bu projeyi yararlı buluyorsanız geliştirilmesine gönüllü olarak destek olabilirsiniz. Proje ve tüm özellikleri, bağışlardan bağımsız olarak ücretsiz ve açık kaynaklı kalır.

- **🌍 Uluslararası:** [Tribute ile destekleyin (banka kartı)](https://web.tribute.tg/d/S0p)
- **🇷🇺 Rusya:** [SBP / Mir ile destekleyin (banka uygulaması)](https://pay.cloudtips.ru/p/9f240c8b)
- [Tüm destek yöntemleri](docs/SUPPORT_TR.md) — USDT, USDC ve Bitcoin dahil.

<div align="center">

**İki alan adı. Birkaç dakika. Kendi 3x-ui / Xray sunucunuz.**

⭐ Kurulum aracı işinize yaradıysa başkalarının da projeyi keşfetmesi için [GitHub'da yıldız verebilirsiniz](https://github.com/xPROMSx/3x-ui-auto-nginx).

[Kurulum](#installation) · [Sürümler](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Sorunlar](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
