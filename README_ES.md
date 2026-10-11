<div align="center">

[🇷🇺 Русский](README_RU.md) · [🇬🇧 English](README.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · 🇪🇸 **Español** · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Despliegue automático de 3X-UI / XRAY-CORE en tu propio VPS

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

Dos dominios, un VPS limpio y unos minutos para completar la instalación.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[Versiones](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Telegram Web Proxy Manager](#telemt-web-manager) · [Incidencias](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>

**3X-UI AUTO NGINX** instala [3x-ui](https://github.com/MHSanaei/3x-ui) y Xray, y configura nginx, HTTPS, perfiles de conexión, suscripciones, diagnósticos de red y copias de seguridad y restauración. AmneziaWG 3.1 y AdGuard Home con DoH son opcionales.

Solo necesitas dos dominios y un VPS limpio. El instalador selecciona y despliega automáticamente un sitio web de camuflaje.

## ✨ ¿Por qué elegir este proyecto?

| | |
| --- | --- |
| **Conexiones preconfiguradas**<br>REALITY, XHTTP, Hysteria2, WebSocket y Trojan gRPC ya vienen configurados. | **Servicios internos protegidos**<br>El panel y las suscripciones no exponen sus puertos internos directamente a Internet. |
| **Enrutamiento nginx restringido**<br>Las solicitudes no pueden redirigirse a puertos locales arbitrarios. | **Backup / Restore v3**<br>Recupera tu VPS o restaura una copia en un servidor nuevo, incluso de otro proveedor. |
| **Certificados automáticos**<br>Emisión y renovación de Let's Encrypt sin configuración manual. | **AdGuard Home + DoH**<br>Activación opcional durante la instalación, sin necesidad de un tercer dominio. |

<a id="installation"></a>

## 🚀 Inicio rápido

Configura los registros DNS de **dos dominios** para que apunten a la IP de tu VPS: uno para el panel y otro para REALITY. Conéctate por SSH como **root** y permite TCP **80/443** y UDP **443**. Consulta los [sistemas compatibles](#technical-details).

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Antes de reinstalar, se solicitan ambos dominios y las opciones VPS Security + DoT, RAW TLS Vision, AmneziaWG, AdGuard Home y creación del cliente. El tercer dominio solo es necesario para Vision. Puedes indicar los dominios principales directamente:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

> **⚠️ Solo para instalaciones nuevas o reinstalaciones completas.** `x-ui-latest.sh` elimina la base de datos anterior de 3x-ui y la configuración de nginx. **No lo utilices para actualizar un VPS en funcionamiento.** Guarda primero una copia de seguridad fuera del servidor. Si detecta una instalación existente, la reinstalación o desinstalación requiere escribir exactamente `YES` en mayúsculas.

Al terminar recibirás la **URL del panel, credenciales aleatorias y la URL de diagnóstico** (MTR/LibreSpeed con autenticación mediante 3x-ui). Si instalas AdGuard Home, también verás su URL de administración, contraseña y dirección DoH. Si eliges crear el cliente, también se muestra la URL de suscripción verificada.

## 🚀 Perfiles de conexión

| Conexión | Estado |
| --- | :---: |
| VLESS + REALITY | ✅ Listo para usar |
| VLESS + XHTTP | ✅ Listo para usar |
| Hysteria2 | ✅ Listo para usar |
| VLESS + WebSocket | ✅ Listo para usar |
| Trojan + gRPC | ✅ Listo para usar |
| AmneziaWG 3.1 | ✅ Opcional |
| VLESS + RAW TLS Vision | ✅ Opcional |

Los cinco perfiles principales ya están configurados. Activa en 3x-ui los que necesites sin modificar nginx. AmneziaWG solo se añade si lo seleccionas durante la instalación. El cliente puede crearse automáticamente o desde el panel; la compatibilidad depende de la aplicación y su versión.

### Suscripciones

Las suscripciones estándar, JSON y **Mihomo / Clash** se ofrecen mediante nginx y HTTPS. El parámetro `provider=1` devuelve la suscripción original para los proveedores de proxy, en lugar de una configuración Clash completa.

## 🧩 Funciones opcionales

Las opciones se eligen antes de reinstalar. Security y la creación del cliente están activadas por defecto; Vision, AWG y AGH están desactivadas.

### VPS Security + DNS-over-TLS opcional

Antes de eliminar un despliegue anterior, el instalador comprueba la compatibilidad, ejecuta obligatoriamente `apt-get --no-remove -y dist-upgrade`, instala dependencias y vuelve a comprobar SSH/DNS. La reinstalación requiere confirmación: la actualización puede reiniciar servicios y no se puede revertir. Si hace falta reiniciar, se programa solo tras la instalación, las comprobaciones y el informe correctos; el propietario verifica el funcionamiento después del reinicio.

`CONFIGURE VPS SECURITY + DoT? [Y/n]:` configura Fail2ban para SSH, APT update a las 02:30, unattended upgrade a las 02:50 y reinicio automático a las 04:38, incluso con usuarios conectados. Conserva y muestra la zona horaria local; no cambia la política ni las claves SSH. En una imagen mínima reconocida sin resolved, con resolv.conf normal que solo contiene DNS públicos de Cloudflare/Google, instala el paquete y verifica DoT estricto antes de cleanup. Guarda el DNS y estado del servicio originales para una recuperación verificada; no revierte los paquetes instalados. DNS personalizados/del proveedor, rutas VPN y servicios DNS competidores causan rechazo seguro antes de cleanup. No reescribe interfaces. N conserva el DNS; el full upgrade inicial sigue siendo obligatorio. Backup / Restore no transfiere seguridad/DNS específicos del servidor.

### VLESS RAW TLS Vision opcional

`INSTALL VLESS RAW TLS VISION? [y/N]:` requiere un dominio o subdominio adicional apuntando al VPS. Comparte TCP/443 mediante nginx SNI, usa un certificado independiente y ofrece un sitio de camuflaje HTTPS. No abre otro puerto público. Backup / Restore v3 admite el tercer certificado y los archivos sin Vision.

### Creación automática de cliente y suscripción

`CREATE CLIENT AND SUBSCRIPTION? [Y/n]:` crea un cliente mediante la API oficial de 3x-ui v3.9.0, lo vincula a los inbounds locales activos compatibles y verifica la suscripción oficial. Utiliza el dominio del panel, sin otro dominio. N conserva los ajustes actuales de clientes y suscripciones. El resultado muestra la URL solo tras verificarla. AWG `vpn://` requiere una aplicación Amnezia compatible.


### AdGuard Home + DoH

Responde `y` a `Install AdGuard Home with DNS-over-HTTPS? [y/N]:`. No hace falta un tercer dominio: la interfaz de administración utiliza una ruta aleatoria `/adg-.../` en el dominio del panel, y DoH está disponible en `https://panel.example.com/dns-query`. No se abre el puerto público TCP/UDP **53**. La configuración y los datos se incluyen en **Backup / Restore v3**.

<details>
<summary>⚠️ <strong>Recomendación de seguridad</strong></summary>

Para un VPS personal, crea un [ClientID](https://adguard-dns.io/kb/es/adguard-home/clients/#clientid) por dispositivo y añade **solo estos identificadores** en **Configuración → Configuración de DNS → Configuración de acceso → Clientes permitidos** (sin direcciones IP ni rangos CIDR).

Utiliza direcciones DoH como `/dns-query/<ClientID>`. Se rechazarán las consultas DNS sin un ClientID permitido, incluidas las enviadas al `/dns-query` estándar. Elige identificadores largos y aleatorios. [Recomendaciones oficiales de seguridad de AdGuard Home](https://adguard-dns.io/kb/es/adguard-home/running-securely/).

</details>

---

### AmneziaWG 3.1

Durante la instalación puedes configurar **AmneziaWG 3.1 en UDP/8443** (desactivado por defecto). Responde `y` a `Install AmneziaWG on UDP port 8443? [y/N]:`. Está integrado en 3x-ui y utiliza el dominio del panel. Después, añade un cliente desde 3x-ui para obtener su configuración o enlace `vpn://`; la creación inicial incluye AWG si está seleccionado. UFW permite automáticamente UDP/8443; **Backup / Restore v3** conserva la configuración y restaura la regla.

## 💾 Copias de seguridad y restauración

**Backup / Restore v3** permite recuperar el estado de tu VPS o restaurarlo en un servidor compatible después de reinstalar el sistema operativo. La herramienta se instala automáticamente; ejecútala como root:

```bash
# Crear una copia de seguridad
x-ui-backup backup

# Mostrar las copias disponibles
x-ui-backup list

# Restaurar una copia concreta
x-ui-backup restore /var/backups/x-ui/<archive>.tar.gz
```

Los archivos se guardan en `/var/backups/x-ui/`.

> **Las copias contienen información sensible:** base de datos de clientes, contraseñas y claves privadas de certificados. Conserva una copia **fuera del VPS** y restaura únicamente archivos de confianza.

[Restauración en un VPS nuevo](#restore-on-new-vps).

## 🔐 Seguridad

Las interfaces de los servicios no se exponen directamente a Internet. Se accede al panel, las suscripciones y los servicios adicionales mediante nginx y HTTPS, mientras que los puertos internos permanecen limitados al servidor.

No existe un proxy genérico hacia puertos arbitrarios de localhost. Si se produce un error crítico, la instalación o restauración se detiene en lugar de iniciar una configuración incompleta.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Un proyecto complementario](https://github.com/xPROMSx/telegram-web-proxy-manager) para crear tu propio Telegram WEB Proxy con HTTPS, un sitio de camuflaje y actualizaciones con posibilidad de reversión.

Los proyectos son independientes: **este instalador no instala Telegram Web Proxy Manager**.

<a id="technical-details"></a>

## ⚙️ Detalles técnicos y compatibilidad

- **Sistemas:** Ubuntu 24.04, Ubuntu 26.04 y Debian 13.
- **UFW:** permite 80/tcp, 443/tcp y 443/udp (8443/udp es opcional al seleccionar AmneziaWG). Si UFW está desactivado, solo se activa después de detectar y permitir el puerto SSH; de lo contrario, permanece desactivado con una advertencia. **⚠️ La restauración nunca activa UFW.**
- **Certificados:** Let's Encrypt con webroot y `certbot.timer` renuevan los certificados automáticamente sin detener nginx.
- **Versión de 3x-ui:** el instalador utiliza por defecto la versión más reciente cuya compatibilidad con 3x-ui Auto Nginx se ha comprobado exhaustivamente; puede no ser la última versión oficial publicada. Después puedes actualizar 3x-ui con su mecanismo integrado, aunque es posible que la nueva versión todavía no haya sido verificada con esta configuración. También puedes seleccionar expresamente otra versión estable mediante `-version <tag>` (mínimo compatible: v3.8.0); el instalador avisará si no se ha verificado su compatibilidad.

<a id="restore-on-new-vps"></a>

### Restauración en un VPS nuevo

El sistema operativo, su versión y la arquitectura deben coincidir con los de la copia de seguridad. Si cambia la IP del VPS, actualiza los registros DNS de los dominios. **No ejecutes** `x-ui-latest.sh`; instala únicamente la herramienta de copia y restaura un archivo de confianza:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/assets/backup/x-ui-backup.sh -o /tmp/x-ui-backup
install -o root -g root -m 0755 /tmp/x-ui-backup /usr/local/bin/x-ui-backup
rm -f /tmp/x-ui-backup
x-ui-backup restore /root/<archive>.tar.gz
```

La administración de SSH, el sistema operativo y el firewall básico sigue siendo responsabilidad del administrador. Para archivos v2, utiliza la herramienta de la versión anterior correspondiente.

## 🤝 Créditos y origen

Este proyecto se basa en [3x-ui-pro](https://github.com/mozaroc/3x-ui-pro), pero se mantiene de forma independiente. Desde la creación del fork se han rediseñado considerablemente el enrutamiento nginx/SNI y la configuración XHTTP, así como la emisión y renovación automática de certificados TLS. También se ha incorporado Backup / Restore v3 con recuperación y reversión, se ha añadido Hysteria2 sobre UDP/443 y se han corregido problemas de seguridad identificados.

El panel oficial procede de [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui). Los autores de los componentes de terceros conservan sus derechos y licencias.

Las contribuciones originales y modificaciones de xPROMSx se distribuyen bajo [GNU GPL-3.0-only](LICENSE). Copyright (C) 2026 xPROMSx contributors. Esta licencia solo cubre los derechos que nos corresponden sobre esos materiales; no cambia la licencia del código heredado ni significa que todo el repositorio esté sujeto a GPL. Consulta el [alcance de la licencia y los avisos de terceros](THIRD_PARTY_NOTICES.md).

<div align="center">

**Dos dominios. Unos minutos. Tu propio servidor 3x-ui / Xray.**

⭐ Si este instalador te ha resultado útil, puedes darle una [estrella en GitHub](https://github.com/xPROMSx/3x-ui-auto-nginx) para ayudar a otros a descubrirlo.

[Instalación](#installation) · [Versiones](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Incidencias](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
