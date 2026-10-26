<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · 🇹🇷 **Türkçe**

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Kendi VPS sunucunuzda otomatik 3X-UI / XRAY-CORE kurulumu

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

İki alan adı, temiz bir VPS ve kurulumu tamamlamak için yalnızca birkaç dakika.

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT_TR.md)

[📦 Sürümler](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ Destek](#support-development) · [🐛 Sorun bildir](https://github.com/xPROMSx/3x-ui-auto-nginx/issues) · [💬 İletişim](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX**, [3x-ui](https://github.com/MHSanaei/3x-ui) ve Xray'i kurar; nginx, HTTPS, bağlantı profilleri, abonelikler, ağ tanılama ve yedekleme/geri yükleme yapılandırmasını hazırlar. AmneziaWG 3.1 ve DoH destekli AdGuard Home isteğe bağlıdır.

İki alan adı ve temiz bir VPS yeterlidir. Kurulum aracı bir kamuflaj web sitesini otomatik seçip yayınlar.

## ✨ Neden bu proje?

| | |
| --- | --- |
| **Hazır bağlantı profilleri**<br>REALITY, XHTTP, Hysteria2, Amnezia WG, VLESS XTLS Vision, WebSocket TLS ve Trojan gRPC. | **Dışarıya kapalı dahili hizmetler**<br>Panelin ve abonelik hizmetinin dahili portları doğrudan internete açılmaz. |
| **Kısıtlı nginx yönlendirmesi**<br>İstekler rastgele yerel portlara yönlendirilemez. | **Backup / Restore v3**<br>Mevcut VPS'i önceki durumuna döndürün veya farklı bir sağlayıcıdaki yeni sunucuya geri yükleyin. |
| **Otomatik sertifikalar**<br>Let's Encrypt sertifikaları elle yapılandırma gerektirmeden alınır ve yenilenir. | **AdGuard Home + DoH**<br>Kurulumda isteğe bağlıdır; üçüncü bir alan adı gerekmez. |

<a id="installation"></a>

## 🚀 Hızlı başlangıç

**İki alan adının** DNS kayıtlarını VPS IP adresinize yönlendirin: biri panel, diğeri REALITY için. SSH üzerinden **root** olarak bağlanın ve TCP **80/443** ile UDP **443** erişimine izin verin. [Desteklenen sistemler](#technical-details).

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Etkileşimli SSH terminali menüyü açar: **1 — Installation**, **3 — Backups**, **0 — Exit**. `ssh -t` ile TTY ayırın; TTY yoksa açık kurulum seçeneklerini kullanın. [Menü ve yedekleme komutları](docs/MANAGER.md).

<details>
<summary><strong>Alternatif indirme — GitHub Releases kullanılamıyorsa</strong></summary>

Doğrudan güncel `main` dalından kurulum yapar. İçeriği, yayımlanan son sürümden farklı olabilir.

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

</details>

<a id="installation-vs-update"></a>

> [!CAUTION]
> **Kurulum ≠ güncelleme**
>
> **3X-UI AUTO NGINX**, temiz bir VPS üzerine ilk kurulum veya tamamen yeniden kurulum için tasarlanmıştır.
>
> Daha önce yapılandırılmış bir sunucuda betiği yeniden çalıştırmak **mevcut kurulumu güncellemez**; bunun yerine bileşenleri yeniden kurar ve eski 3X-UI veritabanını ve nginx yapılandırmasını siler.

<details>
<summary><strong>Nasıl güncellenir?</strong></summary>

- **3X-UI ve Xray:** 3X-UI'nin yerleşik güncelleme araçlarını kullanın.
- **3X-UI AUTO NGINX:** kurulu sistemin yerinde güncellenmesi desteklenmez. Yeni sürümlerdeki değişiklikler yalnızca sıfırdan kurulum veya tamamen yeniden kurulum sırasında uygulanır.
- **Backup / Restore:** projeyi güncellemek için değil, verileri yedeklemek ve geri yüklemek içindir.

**Yalnızca güncelleme yapmak için kurulum betiğini yeniden çalıştırmayın!** VPS'nizin güvenliği için nginx'i, Linux çekirdeğini ve diğer sistem bileşenlerini işletim sisteminizin paket yöneticisiyle düzenli olarak güncelleyin.

</details>


Kurulum aracı başlatıldığında aşağıdaki adımları sırayla sunar. Terminalde göreceğiniz sorular, karşılaştırabilmeniz için özgün İngilizce biçimleriyle verilmiştir:

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

Kurulum aracı ek sunucu korumasını otomatik olarak yapılandırır: SSH parola kaba kuvvet saldırılarına karşı Fail2ban, şifreli sistem DNS’i (DoT), sistem ve paketler için otomatik güvenlik güncellemeleri ve bellek yetersizliğinde kararlılığı artırmak için 1 GiB swap dosyası.

**Bu seçeneği etkinleştirmeden önce aşağıdaki ayrıntıları**, özellikle otomatik yeniden başlatma takvimini okuyun.

<details>
<summary>🔐 Güvenlik ayarlarının ayrıntıları</summary>

`Y` seçildiğinde şu ayarlar uygulanır:

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

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS

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

</details>

---

### 7. 👤 Otomatik istemci ve abonelik oluşturma

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*Önerilir · Varsayılan olarak açık (`Y`)*

Kurulum aracı 3X-UI panelinde bir istemci oluşturur ve yapılandırılmış, desteklenen bağlantılar için kişisel bir HTTPS abonelik bağlantısı üretir.

Abonelik bağlantısı kurulum sonu raporunda gösterilir. Bu seçeneği reddederseniz istemcileri daha sonra panel üzerinden elle oluşturabilirsiniz.

---

> [!CAUTION]
> **Yalnızca temiz kurulum veya tam yeniden kurulum içindir.** `x-ui-latest.sh` önceki 3x-ui veritabanını ve nginx yapılandırmasını siler; **çalışan bir VPS'i güncellemek için kullanılmamalıdır**. Yeniden kurmadan önce Backup kopyasını VPS dışında saklayın. Var olan kurulum algılandığında yeniden kurulum veya kaldırma için tam olarak büyük harflerle `YES` yazmak gerekir.

Kurulum sonunda **panel adresi, kullanıcı adı ve parola, tanılama adresi ve abonelik bağlantısı** (otomatik istemci oluşturulduysa) gösterilir. AdGuard Home seçildiyse yönetim adresi, parolası ve DoH uç noktası da görüntülenir.

İşletim sistemi güncellemesi yeniden başlatma gerektiriyorsa kurulum aracı bunu bildirir. **İlk yeniden başlatma elle yapılır:** `sudo reboot`.

## 🚀 Bağlantı profilleri

| Bağlantı | Durum |
| --- | :---: |
| VLESS + REALITY | ✅ Kullanıma hazır |
| VLESS + XHTTP | ✅ Kullanıma hazır |
| Hysteria2 | ✅ Kullanıma hazır |
| VLESS + WebSocket (TLS) | ✅ Kullanıma hazır |
| Trojan + gRPC | ✅ Kullanıma hazır |
| VLESS + XTLS Vision | ✅ İsteğe bağlı |
| Amnezia WG | ✅ İsteğe bağlı |

Kurulum aracı beş temel profili hazırlar: REALITY, XHTTP ve Hysteria2 baştan etkindir; WebSocket ve Trojan gRPC ise gerektiğinde 3X-UI panelinden etkinleştirilebilir.

XTLS Vision ve Amnezia WG yalnızca kurulumda seçildiklerinde eklenir. **Bağlantıları kullanmak için istemci oluşturmanız gerekir**; istemciler kurulumda otomatik veya panelde elle oluşturulabilir. Amnezia WG istemcileri ayrı oluşturulur.

Uyumluluk kullandığınız istemci uygulamasına ve sürümüne bağlıdır.

### Abonelikler

Standart abonelikler, JSON ve **Mihomo / Clash** nginx üzerinden HTTPS ile sunulur. `provider=1`, tam Clash yapılandırması yerine proxy provider'lar için özgün aboneliği döndürür.


## 💾 Yedekleme ve geri yükleme

**Backup / Restore v3**, VPS'inizi eski durumuna döndürmenizi veya işletim sistemini yeniden kurduktan sonra uyumlu bir sunucuda kurtarmanızı sağlar. Araç kurulumla birlikte yüklenir; komutları root olarak çalıştırın:

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

## 🔐 Güvenlik

Hizmet arayüzleri doğrudan internete açılmaz. Panel, abonelikler ve ek hizmetlere nginx ve HTTPS üzerinden erişilir; dahili portlar yalnızca yerel bağlantıları kabul eder.

İstekleri rastgele localhost portlarına ileten genel amaçlı bir proxy yoktur. Kritik hata oluşursa eksik bir yapılandırma başlatılmak yerine kurulum veya geri yükleme durdurulur.


**VPS'inizi nasıl güvenceye alacağınızdan emin değil misiniz?** Kurulum sırasında gelişmiş güvenlik seçeneğini etkinleştirerek SSH kaba kuvvet saldırılarına karşı korumayı, şifreli DNS'i ve güvenlik güncellemelerini otomatik ayarlayabilirsiniz. Önce **Hızlı başlangıç** bölümündeki ayrıntıları ve gece yeniden başlatma takvimini okuyun.

**Önemli:** Sunucuya erişimi de koruyun. SSH anahtarları kullanın ve anahtarla girişin çalıştığını doğruladıktan sonra parola ile kimlik doğrulamayı kapatın. Kurulum aracı bunu otomatik yapmaz.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Kardeş projemiz](https://github.com/xPROMSx/telegram-web-proxy-manager), kendi Telegram WEB Proxy sunucunuzu HTTPS, kamuflaj sitesi ve geri alma destekli güncellemelerle kurmanızı sağlar.

Projeler birbirinden bağımsızdır; **bu kurulum aracı Telegram Web Proxy Manager'ı yüklemez**.

<a id="technical-details"></a>

## ⚙️ Teknik ayrıntılar ve uyumluluk

- **Sistemler:** Ubuntu 24.04, Ubuntu 26.04 ve Debian 13.
- **UFW:** 80/tcp, 443/tcp ve 443/udp portlarına izin verir (AmneziaWG seçilirse isteğe bağlı olarak 8443/udp da eklenir). UFW kapalıysa SSH portu bulunup erişime izin verilmeden etkinleştirilmez; bu mümkün değilse uyarıyla kapalı kalır. **⚠️ Geri yükleme işlemi UFW'yi hiçbir zaman etkinleştirmez.**
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

Proje [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro) temel alınarak geliştirilmiş ve bağımsız olarak sürdürülmektedir. Fork sonrasında nginx/SNI yönlendirmesi ile XHTTP yapılandırması kapsamlı biçimde yeniden düzenlenmiş, TLS sertifikalarının alınması ve otomatik yenilenmesi yeniden tasarlanmış ve kurtarma/geri alma özellikli Backup / Restore v3 eklenmiştir. Ayrıca UDP/443 üzerinde Hysteria2 desteği sağlanmış ve tespit edilen güvenlik sorunları giderilmiştir.

Resmî panel [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) projesinden sağlanır. Üçüncü taraf bileşenlerin sahipleri haklarını ve mevcut lisanslarını korur.

xPROMSx tarafından geliştirilen özgün katkılar ve değişiklikler [GNU GPL-3.0-only](LICENSE) kapsamında sunulur. Copyright (C) 2026 xPROMSx contributors. Bu lisans yalnızca söz konusu materyaller üzerinde sahip olduğumuz hakları kapsar; devralınmış kodu yeniden lisanslamaz veya deponun tamamının GPL kapsamında olduğunu göstermez. Ayrıntılar için [lisans kapsamına ve üçüncü taraf bildirimlerine](THIRD_PARTY_NOTICES.md) bakın.

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
