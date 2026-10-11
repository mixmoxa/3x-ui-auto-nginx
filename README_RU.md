<div align="center">

🇷🇺 **Русский** · [🇬🇧 English](README.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · [🇪🇸 Español](README_ES.md) · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Автоматическое развёртывание 3X-UI / XRAY-CORE на собственном VPS

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

Два домена, чистый VPS и несколько минут на установку.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[Релизы](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Telegram Web Proxy Manager](#telemt-web-manager) · [Ошибки](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>

**3X-UI AUTO NGINX** устанавливает [3x-ui](https://github.com/MHSanaei/3x-ui) и Xray, настраивает nginx, HTTPS, подключения, подписки, диагностику и Backup / Restore. AmneziaWG 3.1 и AdGuard Home с DoH — по желанию.

Нужны два домена и чистый VPS. Сайт-прикрытие установщик выбирает и разворачивает автоматически.

## ✨ Почему этот проект?

| | |
| --- | --- |
| **Готовые профили подключения**<br>REALITY, XHTTP, Hysteria2, WebSocket и Trojan gRPC уже настроены. | **Закрытые внутренние сервисы**<br>Панель и подписки не публикуют свои служебные порты напрямую в интернет. |
| **Безопасная схема nginx**<br>Нет проксирования запросов на произвольные локальные порты. | **Backup / Restore v3**<br>Откат текущего VPS или восстановление на новом сервере, в том числе у другого хостера. |
| **Автоматические сертификаты**<br>Let's Encrypt выпускается и продлевается без ручной настройки. | **AdGuard Home + DoH**<br>Устанавливается по желанию и не требует третьего домена. |

<a id="installation"></a>

## 🚀 Быстрый старт

Настройте DNS-записи **двух доменов**, указав IP-адрес вашего VPS: один для панели, другой для REALITY. Подключитесь по SSH под **root** и разрешите входящие TCP **80/443** и UDP **443**. [Поддерживаемые ОС](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

До переустановки установщик запросит два домена и предложит VPS Security + DoT, RAW TLS Vision, AmneziaWG, AdGuard Home и создание клиента. Третий домен нужен только для Vision. Основные домены можно передать сразу:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

> **⚠️ Чистая установка или полная переустановка.** `x-ui-latest.sh` удаляет прежнюю базу 3x-ui и конфигурацию nginx — **это не команда обновления рабочего VPS**. Перед переустановкой сохраните Backup вне сервера. Переустановка обнаруженной установки и удаление проекта требуют точного `YES` в верхнем регистре, чтобы избежать ошибок при случайном запуске скрипта.

В конце — **URL панели, случайные логин/пароль и адрес диагностики** (MTR/LibreSpeed с авторизацией через 3x-ui). При выборе AdGuard Home — его адрес, пароль и DoH. При выборе создания клиента также выводится проверенная ссылка подписки.

## 🚀 Профили подключения

| Подключение | Статус |
| --- | :---: |
| VLESS + REALITY | ✅ Готов к работе |
| VLESS + XHTTP | ✅ Готов к работе |
| Hysteria2 | ✅ Готов к работе |
| VLESS + WebSocket | ✅ Готов к работе |
| Trojan + gRPC | ✅ Готов к работе |
| AmneziaWG 3.1 | ✅ Опционально |
| VLESS + RAW TLS Vision | ✅ Опционально |

Пять основных профилей уже настроены установщиком: нужный можно включить в 3x-ui без изменения nginx. AmneziaWG добавляется по выбору при установке. Клиента можно создать автоматически или вручную в панели; совместимость зависит от приложения и версии.

### Подписки

Обычная подписка, JSON и **Mihomo / Clash** — через nginx и HTTPS. `provider=1` возвращает исходную подписку для proxy providers вместо полной конфигурации Clash.

## 🧩 Опциональные функции

Выбор выполняется до переустановки. Security и создание клиента по умолчанию включены; Vision, AWG и AGH — отключены.

### VPS Security + DNS-over-TLS по желанию

Перед удалением предыдущего развёртывания установщик проверяет совместимость, выполняет обязательный `apt-get --no-remove -y dist-upgrade`, устанавливает системные зависимости и повторно проверяет SSH/DNS. При переустановке требуется подтверждение: обновление ОС может перезапустить службы и не откатывается. Если нужна перезагрузка, она назначается только после успешной установки, проверок и итогового отчёта; проверку после reboot выполняет владелец.

`Enhance VPS security? [Y/n]:` настраивает SSH jail Fail2ban, APT update на 02:30, unattended upgrade на 02:50 и автоматическую перезагрузку на 04:38, даже при вошедших пользователях. Используется отображаемый локальный часовой пояс VPS; SSH-политика и ключи не меняются. Выбор Security применяет DNS-политику проекта независимо от прежнего провайдера или наличия старых DNS-директив. Установщик сохраняет исходный файл/ссылку resolver, собственный drop-in и состояние службы, обеспечивает установку systemd-resolved, затем применяет и проверяет strict DoT. Основной resolved.conf и файлы сети/VPN не изменяются. Конфликт эффективных DNS-маршрутов или ошибка TLS/DNS вызывают проверяемый rollback; само наличие старой конфигурации не блокирует preflight. Изменения пакетов не откатываются. Security=N не меняет DNS. Host-specific безопасность/DNS не переносятся через Backup / Restore.

### VLESS RAW TLS Vision по желанию

`Set up an additional VLESS Vision connection? (requires a separate domain) [y/N]:` требует один дополнительный домен или поддомен, направленный на VPS. Vision использует общий TCP/443 через nginx SNI, отдельный сертификат и HTTPS-сайт-прикрытие. Дополнительный публичный порт не открывается. Backup / Restore v3 поддерживает третий сертификат и сохраняет совместимость с архивами без Vision.

### Автоматическое создание клиента и подписки

`Create a client in 3X-UI and display a subscription link after installation? [Y/n]:` создаёт одного клиента через официальный API 3x-ui v3.9.0, привязывает его к поддерживаемым активным локальным inbound и проверяет штатную подписку. Используется домен панели; отдельный домен подписки не требуется. N сохраняет существующие настройки клиентов/подписок. Итоговый отчёт показывает ссылку только после проверки. Экспорт AWG `vpn://` требует совместимого приложения Amnezia.


### AdGuard Home + DoH

Ответьте `y` на запрос `Install and configure AdGuard Home? [y/N]:`. Третий домен не нужен: панель AdGuard Home доступна по случайному пути `/adg-.../` на домене панели, а DoH — по адресу `https://panel.example.com/dns-query`. Публичный TCP/UDP **53** не открывается. Конфигурация и данные входят в **Backup / Restore v3**.

<details>
<summary>⚠️ <strong>Рекомендация по безопасности</strong></summary>

Для личного VPS создайте [ClientID](https://adguard-dns.io/kb/ru/adguard-home/clients/#clientid) для каждого устройства и добавьте **только эти идентификаторы** в **Настройки → Настройки DNS → Настройки доступа → Разрешённые клиенты** (без IP-адресов и подсетей).

Используйте DoH-адреса вида `/dns-query/<ClientID>`. Запросы без разрешённого ClientID, включая стандартный `/dns-query`, будут отклоняться. Выбирайте длинные случайные идентификаторы. [Официальные рекомендации AdGuard Home](https://adguard-dns.io/kb/ru/adguard-home/running-securely/).

</details>

---

### AmneziaWG 3.1

При установке можно настроить **AmneziaWG 3.1 на UDP/8443** (по умолчанию отключён). Для этого ответьте `y` на запрос `Set up an additional AmneziaWG connection? [y/N]:`. Он встроен в 3x-ui и использует домен панели. После установки добавьте клиента в панели 3x-ui и получите конфигурацию или ссылку `vpn://`; автоматическое создание клиента включает AWG, если он выбран. UFW автоматически разрешает UDP/8443; **Backup / Restore v3** сохраняет конфигурацию и восстанавливает правило.

## 💾 Backup / Restore

Backup / Restore **v3** позволяет откатить текущий VPS или восстановить совместимый сервер после переустановки. Утилита устанавливается вместе с сервером; выполняйте от root:

```bash
# Создать новую резервную копию
x-ui-backup backup

# Показать доступные копии
x-ui-backup list

# Восстановить выбранную копию
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

Архивы сохраняются в `/var/backups/x-ui/`.

> **Backup содержит чувствительные данные:** базу клиентов, пароли и приватные ключи сертификатов. Храните копию **вне VPS** и восстанавливайте только доверенные архивы.

[Восстановление на новом VPS](#restore-on-new-vps).

## 🔐 Безопасность

Служебные интерфейсы не открываются напрямую в интернет: панель, подписки и дополнительные сервисы доступны через nginx и HTTPS, а внутренние порты остаются локальными.

Нет универсального proxy на произвольные localhost-порты. Критическая ошибка останавливает установку или восстановление вместо запуска неполной конфигурации.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Мой дополнительный проект](https://github.com/xPROMSx/telegram-web-proxy-manager) для собственного Telegram WEB Proxy: HTTPS, сайт-прикрытие и обновления с аварийным откатом.

Проекты независимы; **этот установщик 3X-UI не устанавливает Telegram Web Proxy Manager**.

<a id="technical-details"></a>

## ⚙️ Технические подробности и совместимость

- **ОС:** Ubuntu 24.04, Ubuntu 26.04 и Debian 13.
- **UFW:** разрешаются 80/tcp, 443/tcp и 443/udp (8443/udp — при выборе AmneziaWG). Неактивный UFW включается только после определения и разрешения SSH-порта; иначе остаётся неактивным с предупреждением. **⚠️ Restore никогда не включает UFW.**
- **Сертификаты:** Let's Encrypt webroot и `certbot.timer` продлевают сертификаты автоматически, без остановки nginx.
- **Версия 3x-ui:** по умолчанию устанавливается последняя версия, тщательно протестированная на совместимость с 3X-UI AUTO NGINX. После установки вы можете самостоятельно обновить 3x-ui штатными средствами панели, но совместимость новой версии с нашей конфигурацией может быть ещё не подтверждена. Другой стабильный релиз можно явно выбрать через `-version <tag>` (минимальная поддерживаемая версия — v3.8.0); установщик предупредит о неподтверждённой совместимости.

<a id="restore-on-new-vps"></a>

### Восстановление на новом VPS

Нужны те же ОС, версия и архитектура, что у копии. При смене IP VPS обновите DNS-записи доменов. Не запускайте `x-ui-latest.sh` — установите только утилиту и восстановите доверенный архив:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

SSH, настройки ОС и базовый firewall остаются ответственностью администратора. Для архивов v2 нужна утилита из соответствующего старого релиза.

## 🤝 Происхождение и авторы

Проект основан на [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro), но развивается независимо. После создания форка существенно переработаны маршрутизация nginx/SNI и конфигурация XHTTP, механизм выпуска и автоматического продления TLS-сертификатов, а также Backup / Restore v3 с восстановлением и откатом. Добавлен Hysteria2 на UDP/443 и устранены выявленные проблемы безопасности.

Панель предоставляет [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui). Права авторов сторонних компонентов и существующие лицензии сохраняются.

Собственные разработки и изменения xPROMSx распространяются под [GNU GPL-3.0-only](LICENSE). Copyright (C) 2026 xPROMSx contributors. Лицензия охватывает только наши права на эти материалы; она не перелицензирует унаследованный код и не подтверждает GPL-статус всего репозитория. Область действия нашей лицензии и сведения о сторонних компонентах приведены в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

<div align="center">

**Два домена. Несколько минут. Собственный 3x-ui / Xray сервер.**

⭐ Если установщик оказался полезен, [поставьте Star](https://github.com/xPROMSx/3x-ui-auto-nginx). Это поможет другим найти проект.

[Установка](#installation) · [Релизы](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Ошибки](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
