<div align="center">

[🇷🇺 Русский](README_RU.md) · [🇬🇧 English](README.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · 🇹🇷 **Türkçe**

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Kendi VPS sunucunuzda otomatik 3X-UI / XRAY-CORE kurulumu

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

İki alan adı, temiz bir VPS ve kurulumu tamamlamak için yalnızca birkaç dakika.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[Sürümler](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Telegram Web Proxy Manager](#telemt-web-manager) · [Sorun bildirimleri](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>

**3X-UI AUTO NGINX**, [3x-ui](https://github.com/MHSanaei/3x-ui) ve Xray'i kurar; nginx, HTTPS, bağlantı profilleri, abonelikler, ağ tanılama ve yedekleme/geri yükleme yapılandırmasını hazırlar. AmneziaWG 3.1 ve DoH destekli AdGuard Home isteğe bağlıdır.

İki alan adı ve temiz bir VPS yeterlidir. Kurulum aracı bir kamuflaj web sitesini otomatik seçip yayınlar.

## ✨ Neden bu proje?

| | |
| --- | --- |
| **Hazır bağlantı profilleri**<br>REALITY, XHTTP, Hysteria2, WebSocket ve Trojan gRPC önceden yapılandırılmıştır. | **Dışarıya kapalı dahili hizmetler**<br>Panelin ve abonelik hizmetinin dahili portları doğrudan internete açılmaz. |
| **Kısıtlı nginx yönlendirmesi**<br>İstekler rastgele yerel portlara yönlendirilemez. | **Backup / Restore v3**<br>Mevcut VPS'i önceki durumuna döndürün veya farklı bir sağlayıcıdaki yeni sunucuya geri yükleyin. |
| **Otomatik sertifikalar**<br>Let's Encrypt sertifikaları elle yapılandırma gerektirmeden alınır ve yenilenir. | **AdGuard Home + DoH**<br>Kurulumda isteğe bağlıdır; üçüncü bir alan adı gerekmez. |

<a id="installation"></a>

## 🚀 Hızlı başlangıç

**İki alan adının** DNS kayıtlarını VPS IP adresinize yönlendirin: biri panel, diğeri REALITY için. SSH üzerinden **root** olarak bağlanın ve TCP **80/443** ile UDP **443** erişimine izin verin. [Desteklenen sistemler](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Kurulum aracı iki alan adını sorar ve isteğe bağlı AmneziaWG ile AdGuard Home kurulumu sunar. Alan adlarını doğrudan da belirtebilirsiniz:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

> **⚠️ Yalnızca temiz kurulum veya tamamen yeniden kurulum içindir.** `x-ui-latest.sh` mevcut 3x-ui veritabanını ve nginx yapılandırmasını siler. **Çalışan bir VPS'i güncellemek için kullanmayın.** Önce yedeğinizi sunucu dışında saklayın. Mevcut bir kurulum algılanırsa yeniden kurma veya kaldırma işlemi için büyük harflerle tam olarak `YES` yazılması gerekir.

Kurulum sonunda **panel adresi, rastgele oluşturulmuş giriş bilgileri ve tanılama adresi** (3x-ui üzerinden kimlik doğrulamalı MTR/LibreSpeed) gösterilir. AdGuard Home seçildiyse yönetim adresi, parola ve DoH adresi de verilir.

## 🚀 Bağlantı profilleri

| Bağlantı | Durum |
| --- | :---: |
| VLESS + REALITY | ✅ Kullanıma hazır |
| VLESS + XHTTP | ✅ Kullanıma hazır |
| Hysteria2 | ✅ Kullanıma hazır |
| VLESS + WebSocket | ✅ Kullanıma hazır |
| Trojan + gRPC | ✅ Kullanıma hazır |
| AmneziaWG 3.1 | ✅ İsteğe bağlı |

Beş temel profil önceden yapılandırılmıştır; ihtiyacınız olanları nginx'i değiştirmeden 3x-ui panelinden etkinleştirebilirsiniz. AmneziaWG yalnızca kurulum sırasında seçildiğinde eklenir. **İstemcileri panelde oluşturun**; uyumluluk kullandığınız uygulamaya ve sürümüne bağlıdır.

### Abonelikler

Standart abonelikler, JSON ve **Mihomo / Clash** yapılandırmaları nginx ve HTTPS üzerinden sunulur. `provider=1` parametresi, tam Clash yapılandırması yerine proxy sağlayıcıları için özgün aboneliği döndürür.

## 🧩 İsteğe bağlı özellikler

Her iki özellik de kurulum sırasında seçilebilir ve varsayılan olarak kapalıdır.

### AdGuard Home + DoH

`Install AdGuard Home with DNS-over-HTTPS? [y/N]:` sorusuna `y` yanıtını verin. Üçüncü bir alan adı gerekmez: yönetim arayüzü panel alan adınız altında rastgele oluşturulan `/adg-.../` yolunu kullanır; DoH adresi `https://panel.example.com/dns-query` olur. Genel erişime açık TCP/UDP **53** portu açılmaz. Yapılandırma ve veriler **Backup / Restore v3** kapsamındadır.

<details>
<summary>⚠️ <strong>Güvenlik önerisi</strong></summary>

Kişisel VPS'inizde her cihaz için bir [ClientID](https://adguard-dns.io/kb/tr/adguard-home/clients/#clientid) oluşturun ve **yalnızca bu kimlikleri** **Ayarlar → DNS ayarları → Erişim ayarları → İzin verilen istemciler** bölümüne ekleyin (IP adresi veya CIDR aralığı eklemeyin).

`/dns-query/<ClientID>` biçiminde DoH adresleri kullanın. Standart `/dns-query` yoluna yapılanlar da dahil, izin verilen bir ClientID içermeyen DNS sorguları reddedilir. Uzun ve rastgele kimlikler seçin. [AdGuard Home'un resmî güvenlik önerileri](https://adguard-dns.io/kb/tr/adguard-home/running-securely/).

</details>

---

### AmneziaWG 3.1

Kurulum sırasında **UDP/8443 üzerinde AmneziaWG 3.1** yapılandırabilirsiniz (varsayılan olarak kapalıdır). `Install AmneziaWG on UDP port 8443? [y/N]:` sorusuna `y` yanıtını verin. 3x-ui içine gömülüdür ve panel alan adını kullanır. Kurulumdan sonra 3x-ui paneline bir istemci ekleyerek yapılandırmasını veya `vpn://` bağlantısını alın; kurulum aracı kendiliğinden istemci oluşturmaz. UFW, UDP/8443 erişimine otomatik izin verir; **Backup / Restore v3** yapılandırmayı korur ve güvenlik duvarı kuralını geri yükler.

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

## ❤️ Geliştirmeyi destekleyin

Bu proje işinize yarıyorsa [geliştirilmesine gönüllü olarak destek olabilirsiniz](docs/SUPPORT_TR.md). Bağış yapıp yapmamanızdan bağımsız olarak proje ve tüm özellikleri ücretsiz ve açık kaynaklı kalır.

<div align="center">

**İki alan adı. Birkaç dakika. Kendi 3x-ui / Xray sunucunuz.**

⭐ Kurulum aracı işinize yaradıysa başkalarının da projeyi keşfetmesi için [GitHub'da yıldız verebilirsiniz](https://github.com/xPROMSx/3x-ui-auto-nginx).

[Kurulum](#installation) · [Sürümler](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Sorunlar](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
