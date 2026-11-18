<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · 🇹🇷 **Türkçe**

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Kendi VPS sunucunuzda otomatik 3X-UI / XRAY-CORE kurulumu

**REALITY · XHTTP · HYSTERIA2 · NGINX · HTTPS · BACKUP / RESTORE**

İki alan adı, temiz bir VPS ve kurulumu tamamlamak için yalnızca birkaç dakika.

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT_TR.md)

[📦 Sürümler](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [🔗 Kaskad](#cascade) · [🌐 Kamuflaj siteleri](#cover-sites) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ Destek](#support-development) · [💬 İletişim](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX**, kendi VPS sunucunuzda [3x-ui](https://github.com/MHSanaei/3x-ui) ve Xray kurmak için ücretsiz bir yükleyicidir. Nginx, HTTPS sertifikaları, REALITY, XHTTP, Hysteria2, abonelikler ve tanılama araçlarını yapılandırır. Etkileşimli yöneticiyle sunucu kurulumunu, alan adı değişikliklerini, Backup/Restore v3 işlemlerini ve iki VPS arasında Kaskad bağlantısını yönetebilirsiniz. XTLS Vision, AmneziaWG 3.1, Rus siteleri için Cloudflare WARP ve DNS-over-HTTPS (DoH) destekli AdGuard Home isteğe bağlıdır.

**Standart bir 3x-ui kurulumundan fazlası:** yeni sunucular, panel ve REALITY için kendilerine özel çok sayfalı siteler alır. En az 2592 hazır tasarım ve metin kombinasyonu bulunur; her kurulumda renkler, simgeler ve tarihler de değişir. Sitelerde çalışan gezinme bağlantıları ve ek sayfalar vardır. REALITY alan adında TCP üzerinden normal HTTPS istekleri ve UDP üzerinden kimlik doğrulaması yapılmamış HTTP/3 istekleri aynı web sitesini gösterir. Tüm bunlar mevcut Nginx ve Xray ile çalışır; Docker veya ek web sunucusu gerekmez.

## ✨ Neden bu proje?

| | |
| --- | --- |
| **Kullanıma hazır bağlantılar**<br>REALITY, XHTTP ve Hysteria2 otomatik yapılandırılır. Kurulumda seçilen XTLS Vision, AmneziaWG ve CDN için XHTTP bağlantıları da otomatik ayarlanır. | **Eksiksiz kamuflaj siteleri**<br>En az 2592 hazır tasarım ve metin kombinasyonu. Çalışan gezinme bağlantıları, özgün metinler ve görseller içeren çok sayfalı siteler; Hysteria2 için HTTP/3 kamuflajı. |
| **İki VPS ile Kaskad**<br>İki sunucuyu menü üzerinden birbirine bağlayın. Rus siteleri ve IP adresleri giriş sunucusundan doğrudan açılır; diğer trafik çıkış sunucusundan geçer. | **Kendi Nginx ve HTTPS altyapınız**<br>Gelen TCP bağlantılarını VPS'inizdeki Nginx karşılar. Panel ve aboneliklere kendi alan adınız üzerinden HTTPS ile erişilir; dahili portlar internete doğrudan açılmaz. |
| **Backup / Restore v3**<br>Verileri ve kişiselleştirilmiş siteleri koruyarak yedekleme, kurtarma ve başka bir VPS'e taşıma. | **Yönetici ve alan adı değişikliği**<br>3X-UI veya diğer hizmetleri yeniden kurmadan panelin, REALITY'nin veya ikisinin alan adını değiştirin. |
| **Otomatik sertifikalar ve güvenlik**<br>Let's Encrypt sertifikaları Nginx durdurulmadan otomatik yenilenir; SSH koruması ve otomatik VPS güvenlik güncellemeleri isteğe bağlıdır. | **Ek özellikler**<br>XTLS Vision, AmneziaWG 3.1, CDN için XHTTP, Cloudflare WARP, DoH destekli AdGuard Home ve Kaskad kurulumu. |

<a id="installation"></a>

## 🚀 Hızlı başlangıç

**İki alan adının** DNS kayıtlarını VPS IP adresinize yönlendirin: biri panel, diğeri REALITY için. SSH üzerinden **root** olarak bağlanın ve TCP **80 ile 443** ve UDP **443** portlarına internetten erişilebildiğini doğrulayın. [Desteklenen sistemler](#technical-details).

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Betiği çalıştırdıktan sonra **1 — English** veya **2 — Русский** seçin. Ardından ana menü açılır:

- **1 — Installation:** yeni sunucu kurma veya tam yeniden kurulum.
- **2 — Change Domains:** panel alan adını, REALITY alan adını veya ikisini yeniden kurmadan değiştirme.
- **3 — Backups:** yedek oluşturma, listeleme ve geri yükleme.
- **4 — Telegram Web Proxy Manager:** bağımsız Telegram proxy yöneticisini başlatma veya kurma.
- **5 — Cascade:** iki sunucuyu bağlama, durumu denetleme veya bağlantıyı kesme.
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
> Mevcut kurulum algılanırsa betik, yönetilen verilerin silineceğini bildirir ve tam olarak **YES** yazmanızı ister. Yeniden kurulum, 3X-UI veritabanını ve nginx yapılandırmasını değiştirir. **Önce yedeğinizi VPS dışında saklayın.**
>
> **Change Domains** ve **Backups**, paneli yeniden kurmayan ayrı işlemlerdir.

<details>
<summary><strong>Nasıl güncellenir?</strong></summary>

- **3X-UI ve Xray:** panelin kendi güncelleme araçlarını kullanın. Yeni sürümlerin bu projenin yapılandırmasıyla uyumluluğu henüz doğrulanmamış olabilir.
- **3X-UI AUTO NGINX:** mevcut kurulu sistemin yerinde güncellenmesi desteklenmez. **5 — Cascade** gibi yeni yönetici özelliklerini kullanmak için güncel betiği indirip ilgili işlemi seçin. Yönetici, mevcut yapılandırmanın uyumluluğunu kontrol eder.
- **Backup / Restore:** verileri yedekler ve geri yükler; kurulu sistemi güncellemez.

**Yalnızca güncelleme amacıyla Installation seçmeyin!** nginx, Linux çekirdeği ve diğer sistem paketlerini işletim sisteminizin araçlarıyla güncelleyin.

</details>

Ana menüden **Installation** seçildiğinde sunulan kurulum ayarları aşağıda açıklanmıştır.

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

### 4. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*Ek bağlantı · Varsayılan olarak kapalı (`N`)*

REALITY bağlantınız kararsızsa veya ağınızda engelleniyorsa yararlı olabilecek, TLS üzerinden çalışan alternatif bir VLESS bağlantısıdır. 3X-UI panelinde ayrı bir profil olarak oluşturulur.

> [!IMPORTANT]
> **XTLS Vision üçüncü ve ayrı bir alan adı gerektirir**; bu alan adı panel ve REALITY alan adlarından farklı olmalıdır. DNS kaydı VPS IP adresine yönlendirilmelidir. HTTPS sertifikası ve nginx yönlendirmesi otomatik yapılandırılır.
>
> `Y` seçildikten sonra kurulum aracı bu alan adını ayrıca sorar: `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

### 5. 🔑 Amnezia WG

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

### 6. 🌐 CDN için VLESS + XHTTP

> `Add an additional CDN-compatible XHTTP connection? [y/N]:`

*Ek bağlantı · Varsayılan olarak kurulmaz (`N`)*

CDN üzerinden kullanıma önceden hazırlanmış, packet-up modunda XHTTP taşımasını kullanan ayrı bir VLESS bağlantısı oluşturulur. Bağlantı 3X-UI panelinde devre dışı bırakılmış olarak oluşturulur.

Panelin mevcut HTTPS alan adı kullanılır; ek alan adı veya sertifika gerekmez. Etkinleştirdikten sonra bağlantı CDN olmadan doğrudan da kullanılabilir.

CDN kullanmak için sağlayıcınızı kendiniz yapılandırmalı ve 3X-UI içindeki Host ayarlarını değiştirmelisiniz. Kurulum aracı CDN hizmetlerini yapılandırmaz; kendi ihtiyaçlarınıza uyarlayabileceğiniz hazır bir sunucu profili sağlar.

---

<a id="warp-ru"></a>

### 7. 🌐 Rus siteleri için Cloudflare WARP

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

### 8. 🛡️ AdGuard Home + DNS-over-HTTPS

> `Install and configure AdGuard Home? [y/N]:`

*İsteğe bağlı DNS sunucusu · Varsayılan olarak kapalı (`N`)*

Reklamları ve izleyicileri engelleyebilen, istemcileri yönetebilen ve şifreli DNS sorguları sunan kişisel DNS sunucusu.

<details>
<summary>ℹ️ AdGuard Home ve erişim kontrolü</summary>

Ek alan adı gerekmez.

Kurulumdan sonra şu adresler kullanılabilir:

- **AdGuard Home yönetim paneli:** `https://panel.example.com/adg-.../` — rastgele oluşturulan benzersiz yol.
- **DNS-over-HTTPS:** `https://panel.example.com/dns-query`.

Genel TCP/UDP **53** portları açılmaz. AdGuard Home yapılandırması ve verileri **Backup / Restore v3** kapsamındadır.

**⚠️ Güvenlik önerisi**

Kişisel VPS'inizde her cihaz için ayrı bir [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) oluşturun.

AdGuard Home'da **Ayarlar → DNS ayarları → Erişim ayarları → İzin verilen istemciler** bölümüne gidin ve IP adresleri ya da alt ağlar yerine **yalnızca bu ClientID'leri** ekleyin.

Şu biçimde DoH adresleri kullanın:

`https://panel.example.com/dns-query/<ClientID>`

Yapılandırmadan sonra izin verilen bir ClientID içermeyen sorgular, normal `/dns-query` yoluna yapılanlar da dâhil, reddedilir.

Uzun ve rastgele kimlikler seçin. [Resmî AdGuard Home güvenlik önerilerine](https://adguard-dns.io/kb/adguard-home/running-securely/) bakın.

**v2.4.1** sürümünden itibaren yeni kurulumlarda AdGuard Home güncellemelerini doğrudan web arayüzünden kontrol edip yükleyebilirsiniz. AdGuard Home'u bu yükleyicinin önceki bir sürümüyle kurduysanız VPS'nizde tek komutla güncellemeleri etkinleştirin:

```bash
sudo bash -c 'set -euo pipefail; umask 077; d=$(mktemp -d); trap '\''rm -rf -- "$d"'\'' EXIT; cd "$d"; u=https://github.com/xPROMSx/3x-ui-auto-nginx/releases/download/v2.4.2; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh" -o x-ui-latest.sh; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh.sha256" -o x-ui-latest.sh.sha256; sha256sum --check --strict x-ui-latest.sh.sha256; bash ./x-ui-latest.sh --enable-agh-updates'
```

</details>

---

<a id="7--otomatik-istemci-ve-abonelik-oluşturma"></a>

<a id="8--otomatik-istemci-ve-abonelik-oluşturma"></a>

### 9. 👤 Otomatik istemci ve abonelik oluşturma

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

| Bağlantı | Durum |
| --- | :---: |
| VLESS + REALITY | ✅ Varsayılan olarak etkin |
| VLESS + XHTTP | ✅ Varsayılan olarak etkin |
| CDN için VLESS + XHTTP | 🔧 İsteğe bağlı, devre dışı |
| Hysteria2 | ✅ Varsayılan olarak etkin |
| VLESS + WebSocket (TLS) | ◻️ Varsayılan olarak devre dışı |
| Trojan + gRPC | ◻️ Varsayılan olarak devre dışı |
| VLESS + XTLS Vision | 🔧 İsteğe bağlı |
| Amnezia WG | 🔧 İsteğe bağlı |

Kurulumdan sonra REALITY, XHTTP ve Hysteria2 etkin olur. WebSocket TLS ve Trojan gRPC de oluşturulur ancak 3X-UI panelinden etkinleştirilene kadar devre dışı kalır.

XTLS Vision, Amnezia WG ve CDN için XHTTP yalnızca kurulum sırasında seçilirse eklenir. CDN için XHTTP devre dışı oluşturulur; etkinleştirilip bir istemci bağlanana kadar aboneliklerde görünmez.

Bağlantıları kullanmak için kurulum sırasında otomatik olarak veya panelde elle istemci oluşturun. Amnezia WG istemcileri ayrı oluşturulur.

Uyumluluk, istemci uygulamasına ve sürümüne bağlıdır. CDN üzerinden XHTTP kullanımında sağlayıcının ayarları ve kısıtlamaları da önemlidir.

### Abonelikler

Standart abonelikler, JSON ve **Mihomo / Clash** nginx üzerinden HTTPS ile sunulur. `provider=1`, tam Clash yapılandırması yerine proxy provider'lar için özgün aboneliği döndürür.


<a id="change-domains"></a>

## 🌐 Alan adlarını değiştirme

Ana menüden **2 — Change Domains** seçin. Panel alan adını, REALITY alan adını veya ikisini yeniden kurulum olmadan değiştirebilirsiniz. Yeni DNS kayıtları VPS'yi göstermeli ve sertifika alımı için TCP/80 erişilebilir olmalıdır. Alan adları birbirinden ve Vision alan adından farklı olmalıdır.

Değişikliklerden önce otomatik olarak tam Backup v3 oluşturulur. İstemciler, anahtarlar, ayarlar ve trafik istatistikleri korunur. Vision alan adı değişmez. İşlemden sonra abonelik URL'lerini ve istemci yapılandırmalarını güncellemeniz gerekebilir.

Yalnızca tanınan proje kurulumları desteklenir; buna uyumlu v2.1.7 kurulumları da dahildir. Hata olursa **yedekleri veya kurtarma verilerini silmeyin**. `ROLLBACK_UNVERIFIED` görürseniz işlemi durdurun ve tanılama bilgilerini saklayın. [Ayrıntılar, sınırlamalar ve kurtarma](docs/MANAGER.md#change-domains).

## 💾 Yedekleme ve geri yükleme

Ana menüde **3 — Backups** bölümünü açarak yedek oluşturabilir, arşivleri listeleyebilir veya Restore çalıştırabilirsiniz. İşletim sistemini yeniden kurduktan sonra ya da başka bir VPS'ye taşınırken yedeği kullanabilirsiniz. Geri yükleme için işletim sistemi, sürümü ve işlemci mimarisi yedekle aynı olmalıdır.

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

Hizmet arayüzleri doğrudan internete açılmaz. Panel, abonelikler ve ek hizmetlere nginx ve HTTPS üzerinden erişilir; dahili portlar yalnızca yerel bağlantıları kabul eder.


**VPS'inizi nasıl güvenceye alacağınızdan emin değil misiniz?** Kurulum sırasında gelişmiş güvenlik seçeneğini etkinleştirerek SSH kaba kuvvet saldırılarına karşı korumayı, şifreli DNS'i ve güvenlik güncellemelerini otomatik ayarlayabilirsiniz. Önce **Hızlı başlangıç** bölümündeki ayrıntıları ve gece yeniden başlatma takvimini okuyun.

**Önemli:** Sunucuya erişimi de koruyun. SSH anahtarları kullanın ve anahtarla girişin çalıştığını doğruladıktan sonra parola ile kimlik doğrulamayı kapatın. Kurulum aracı bunu otomatik yapmaz.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager), HTTPS, kamuflaj sitesi ve geri alma destekli güncellemelerle kendi Telegram WEB Proxy sunucunuzu kurmanızı sağlayan bağımsız bir projedir.

**TWPM, 3X-UI'nin varsayılan kurulumuna dahil değildir.** Ana menüdeki 4. seçenekle yöneticiyi başlatabilir veya onay verdikten sonra ayrı olarak kurabilirsiniz. İki proje bağımsız yönetilir.

<a id="technical-details"></a>

## ⚙️ Teknik ayrıntılar ve uyumluluk

- **Sistemler:** Ubuntu 24.04, Ubuntu 26.04 ve Debian 13.
- **UFW:** 80/tcp, 443/tcp ve 443/udp portlarına izin verir (AmneziaWG seçildiğinde ayrıca 8443/udp). Installation sırasında UFW yalnızca SSH erişimi doğrulandıktan sonra etkinleştirilir; bu güvenli değilse uyarıyla kapalı kalır. Restore sonrasında yönetici UFW'yi **yalnızca ayrıca seçildiğinde** ve güvenlik kontrolleri başarılı olduğunda etkinleştirebilir. `x-ui-backup restore` komutu UFW'yi etkinleştirmez.
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
