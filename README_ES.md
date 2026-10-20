<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · 🇪🇸 **Español** · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Despliegue automático de 3X-UI / XRAY-CORE en tu propio VPS

**REALITY · XHTTP · HYSTERIA2 · WebSocket · gRPC · NGINX · HTTPS · BACKUP / RESTORE**

Dos dominios, un VPS limpio y unos minutos para completar la instalación.

[![Security](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-xhttp.yml?branch=main&label=Security)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-xhttp.yml)
[![Backup](https://img.shields.io/github/actions/workflow/status/xPROMSx/3x-ui-auto-nginx/stack-backup.yml?branch=main&label=Backup)](https://github.com/xPROMSx/3x-ui-auto-nginx/actions/workflows/stack-backup.yml)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)

[📦 Versiones](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ Apoyar](#support-development) · [🐛 Informar de un problema](https://github.com/xPROMSx/3x-ui-auto-nginx/issues) · [💬 Contacto](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX** instala [3x-ui](https://github.com/MHSanaei/3x-ui) y Xray, y configura nginx, HTTPS, perfiles de conexión, suscripciones, diagnósticos de red y copias de seguridad y restauración. AmneziaWG 3.1 y AdGuard Home con DoH son opcionales.

Solo necesitas dos dominios y un VPS limpio. El instalador selecciona y despliega automáticamente un sitio web de camuflaje.

## ✨ ¿Por qué elegir este proyecto?

| | |
| --- | --- |
| **Conexiones preconfiguradas**<br>REALITY, XHTTP, Hysteria2, Amnezia WG, VLESS XTLS Vision, WebSocket TLS y Trojan gRPC. | **Servicios internos protegidos**<br>El panel y las suscripciones no exponen sus puertos internos directamente a Internet. |
| **Enrutamiento nginx restringido**<br>Las solicitudes no pueden redirigirse a puertos locales arbitrarios. | **Backup / Restore v3**<br>Recupera tu VPS o restaura una copia en un servidor nuevo, incluso de otro proveedor. |
| **Certificados automáticos**<br>Emisión y renovación de Let's Encrypt sin configuración manual. | **AdGuard Home + DoH**<br>Activación opcional durante la instalación, sin necesidad de un tercer dominio. |

<a id="installation"></a>

## 🚀 Inicio rápido

Configura los registros DNS de **dos dominios** para que apunten a la IP de tu VPS: uno para el panel y otro para REALITY. Conéctate por SSH como **root** y permite TCP **80/443** y UDP **443**. Consulta los [sistemas compatibles](#technical-details).

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

<details>
<summary>Descarga alternativa (si el método principal no está disponible)</summary>

Versión fijada v2.1.5: el instalador y sus archivos auxiliares proceden de la misma versión.

```bash
curl -fSL https://cdn.jsdelivr.net/gh/xPROMSx/3x-ui-auto-nginx@v2.1.5/x-ui-latest.sh -o x-ui-latest.sh && XUI_AUTO_REF=v2.1.5 bash x-ui-latest.sh
```

Alternativa de emergencia mediante raw:

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/v2.1.5/x-ui-latest.sh -o x-ui-latest.sh && XUI_AUTO_REF=v2.1.5 bash x-ui-latest.sh
```

</details>

<a id="installation-vs-update"></a>

> [!CAUTION]
> **Instalación ≠ actualización**
>
> **3X-UI AUTO NGINX** está diseñado para una instalación inicial en un VPS limpio o para una reinstalación completa.
>
> Volver a ejecutar el script en un servidor ya configurado **no actualiza la instalación existente**: reinstala los componentes y elimina la base de datos anterior de 3X-UI y la configuración de nginx.

<details>
<summary><strong>¿Cómo se actualiza?</strong></summary>

- **3X-UI y Xray:** utiliza las herramientas de actualización integradas en 3X-UI.
- **3X-UI AUTO NGINX:** no admite actualizaciones de la instalación existente sin reinstalar. Los cambios de las nuevas versiones solo se aplican con una instalación desde cero o una reinstalación completa.
- **Backup / Restore:** sirve para guardar y restaurar datos, no para actualizar el proyecto.

**¡No vuelvas a ejecutar el instalador solo para actualizar!** Para mantener seguro tu VPS, actualiza periódicamente nginx, el kernel de Linux y otros componentes del sistema con el gestor de paquetes del sistema operativo.

</details>


Tras iniciarse, el instalador te guiará por las siguientes etapas. Las preguntas aparecen exactamente como se muestran en la terminal:

---

### 1. 🌐 Dominio del panel 3X-UI

> `Enter the domain for your 3X-UI panel:`

Indica el dominio de acceso al panel de administración, las suscripciones y los servicios web adicionales.

---

### 2. 🛰️ Dominio de VLESS REALITY

> `Enter the domain for VLESS REALITY:`

Indica un segundo dominio para REALITY. Los registros DNS de ambos dominios deben apuntar a la IP de tu VPS.

<details>
<summary>ℹ️ Parámetros adicionales de ejecución</summary>

Puedes indicar ambos dominios directamente, sin introducirlos de forma interactiva:

```bash
bash x-ui-latest.sh -subdomain panel.example.com -reality_domain reality.example.com
```

Sustituye `panel.example.com` y `reality.example.com` por tus propios dominios. Las funciones opcionales se seguirán eligiendo de forma interactiva.

</details>

---

### 3. 🔐 Seguridad avanzada del VPS

> `Enhance VPS security? [Y/n]:`

*Recomendado para usuarios con poca experiencia · Activado por defecto (`Y`)*

El instalador configura automáticamente protección adicional para el servidor: Fail2ban contra ataques de fuerza bruta a las contraseñas de SSH, DNS del sistema cifrado (DoT), actualizaciones de seguridad automáticas del sistema y los paquetes, y un archivo swap de 1 GiB para mejorar la estabilidad cuando falta memoria.

**Lee los detalles siguientes antes de activar esta opción**, especialmente el horario de reinicios automáticos.

<details>
<summary>🔐 Descripción detallada de los ajustes de seguridad</summary>

Al elegir `Y`, el instalador configura:

- **Swap de 1 GiB.** Si no hay swap activo, el sistema de archivos es compatible y hay al menos 4 GiB libres, el instalador crea y activa un archivo swap. Los ajustes de swap existentes no cambian. Si no se cumplen estas condiciones, se omite este paso sin detener la instalación.
- **Protección SSH — Fail2ban.** Limita los intentos de acceso fallidos en los puertos SSH reales. No modifica los ajustes existentes de autenticación SSH.
- **DNS cifrado (DoT).** Los resolutores globales de Cloudflare y Google usan DNS-over-TLS estricto mediante `systemd-resolved`. Se conservan las rutas DNS y los dominios de búsqueda de las interfaces/VPN; sus consultas pueden seguir sin cifrar. Si falla la preparación de DoT y se restaura correctamente el DNS original, la instalación principal, Fail2ban y las actualizaciones automáticas continúan de forma independiente de DoT; el resultado final informa del fallo y devuelve un código distinto de cero.
- **Actualizaciones de seguridad automáticas.** Las listas de paquetes se actualizan a las 02:30 y las actualizaciones se instalan a las 02:50.
- **Reinicio automático — 04:38.** Si una actualización requiere reiniciar, el servidor lo hará a esa hora, **incluso con sesiones de usuario activas**, lo que puede interrumpir las conexiones.

Los horarios corresponden a la zona horaria local del VPS.

Se comprueba la compatibilidad de los ajustes existentes antes de modificarlos. Si falla la configuración de seguridad, se realiza una reversión controlada.

**Importante:** esta opción no desactiva el acceso SSH mediante contraseña ni sustituye la administración del servidor. Configura primero el acceso con claves SSH y después desactiva manualmente la autenticación por contraseña.

</details>

---

### 4. 🔗 VLESS XTLS Vision

> `Set up an additional VLESS TCP/TLS (XTLS Vision) connection? (requires a separate domain) [y/N]:`

*Conexión adicional · Desactivada por defecto (`N`)*

Una conexión VLESS alternativa mediante TLS que puede ser útil si REALITY funciona de forma inestable o está bloqueado en tu red. Se crea como un perfil independiente en 3X-UI.

> [!IMPORTANT]
> **XTLS Vision necesita un tercer dominio**, distinto de los usados para el panel y REALITY. Su registro DNS debe apuntar a la IP del VPS. El certificado HTTPS y el enrutamiento nginx se configuran automáticamente.
>
> Si respondes `Y`, el instalador también solicitará este dominio: `Enter the domain for VLESS TLS Vision (must differ from the panel and REALITY domains):`.

---

### 5. 🔑 Amnezia WG

> `Set up an additional AmneziaWG connection? [y/N]:`

*Conexión adicional · Desactivada por defecto (`N`)*

Se crea una conexión AmneziaWG independiente en el panel 3X-UI. No es necesario otro dominio.

<details>
<summary>ℹ️ Más información sobre Amnezia WG</summary>

El instalador configura AmneziaWG 3.1 en **UDP/8443** y añade automáticamente la regla necesaria de UFW.

Después, crea un cliente en el panel 3X-UI para obtener una configuración o un enlace `vpn://` para una aplicación Amnezia compatible.

El instalador crea la conexión del servidor, pero no genera clientes AmneziaWG automáticamente.

La configuración y la regla del cortafuegos están incluidas en **Backup / Restore v3**.

</details>

---

### 6. 🛡️ AdGuard Home + DNS-over-HTTPS

> `Install and configure AdGuard Home? [y/N]:`

*Servidor DNS opcional · Desactivado por defecto (`N`)*

Un servidor DNS personal para bloquear anuncios y rastreadores, administrar clientes y realizar consultas DNS cifradas.

<details>
<summary>ℹ️ AdGuard Home y el control de acceso</summary>

No se necesita un dominio adicional.

Después de instalarlo, estarán disponibles:

- **Panel de administración de AdGuard Home:** `https://panel.example.com/adg-.../` — una ruta aleatoria y exclusiva.
- **DNS-over-HTTPS:** `https://panel.example.com/dns-query`.

No se abren los puertos públicos TCP/UDP **53**. La configuración y los datos de AdGuard Home se incluyen en **Backup / Restore v3**.

**⚠️ Recomendación de seguridad**

Para un VPS personal, crea un [ClientID](https://adguard-dns.io/kb/adguard-home/clients/#clientid) para cada dispositivo.

En AdGuard Home, entra en **Configuración → Configuración DNS → Configuración de acceso → Clientes permitidos** y añade **solo los ClientID** creados, sin direcciones IP ni subredes.

Utiliza direcciones DoH como:

`https://panel.example.com/dns-query/<ClientID>`

Tras configurarlo, se rechazarán las consultas que no tengan un ClientID permitido, incluidas las dirigidas a `/dns-query`.

Utiliza identificadores largos y aleatorios. Consulta las [recomendaciones oficiales de seguridad de AdGuard Home](https://adguard-dns.io/kb/adguard-home/running-securely/).

</details>

---

### 7. 👤 Creación automática del cliente y la suscripción

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*Recomendado · Activado por defecto (`Y`)*

El instalador crea un cliente en 3X-UI y genera una URL de suscripción HTTPS personal para las conexiones configuradas y compatibles.

El enlace aparecerá en el informe final. Si rechazas esta opción, podrás crear clientes manualmente desde el panel.

---

> [!CAUTION]
> **Solo para instalaciones nuevas o reinstalaciones completas.** `x-ui-latest.sh` elimina la base de datos anterior de 3x-ui y la configuración de nginx: **no es un comando para actualizar un VPS en funcionamiento**. Guarda antes una copia de seguridad fuera del VPS. Para reinstalar o desinstalar una instalación existente debes introducir exactamente `YES` en mayúsculas.

Al terminar se mostrarán **la URL del panel, el usuario y la contraseña, la URL de diagnóstico y el enlace de suscripción** (si elegiste crear un cliente). Si instalaste AdGuard Home, también verás la dirección de administración, la contraseña y el endpoint DoH.

Si una actualización del sistema operativo requiere reiniciar, el instalador lo indicará. **El primer reinicio es manual**: ejecuta `sudo reboot`.

## 🚀 Perfiles de conexión

| Conexión | Estado |
| --- | :---: |
| VLESS + REALITY | ✅ Listo para usar |
| VLESS + XHTTP | ✅ Listo para usar |
| Hysteria2 | ✅ Listo para usar |
| VLESS + WebSocket (TLS) | ✅ Listo para usar |
| Trojan + gRPC | ✅ Listo para usar |
| VLESS + XTLS Vision | ✅ Opcional |
| Amnezia WG | ✅ Opcional |

El instalador configura cinco perfiles básicos: REALITY, XHTTP y Hysteria2 quedan habilitados de inmediato; WebSocket y Trojan gRPC se pueden habilitar desde el panel 3X-UI cuando sea necesario.

XTLS Vision y Amnezia WG solo se añaden si los eliges durante la instalación. **Para usar las conexiones debes crear clientes**, automáticamente durante la instalación o manualmente desde el panel. Los clientes de Amnezia WG se crean por separado.

La compatibilidad depende de la aplicación cliente y de su versión.

### Suscripciones

Las suscripciones estándar, JSON y **Mihomo / Clash** se sirven mediante nginx y HTTPS. `provider=1` devuelve la suscripción original para los proveedores de proxy en lugar de una configuración completa de Clash.


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


**¿No sabes cómo proteger tu VPS?** Puedes activar la seguridad avanzada durante la instalación para configurar protección SSH contra ataques de fuerza bruta, DNS cifrado y actualizaciones de seguridad. Antes, consulta los detalles y el horario de reinicios nocturnos en **Inicio rápido**.

**Importante:** protege también el acceso al servidor. Usa claves SSH y comprueba que funcionan antes de desactivar la autenticación por contraseña. El instalador no la desactiva automáticamente.

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

<a id="windows-flag-emojis"></a>

## 🖥️ Banderas de países en Windows 11

Si al abrir el panel de **3x-ui** en **Chrome, Edge o Brave** con Windows 11 aparecen códigos de dos letras (`FI`, `DE`, `US`) en lugar de las banderas, puedes utilizar nuestro pequeño proyecto [**Flag Emojis Windows Installer**](https://github.com/xPROMSx/flag-emojis-windows-installer). Permite mostrar las banderas, conserva la fuente original de Windows y ofrece la posibilidad de revertir los cambios.

<a id="support-development"></a>

## ❤️ Apoya el desarrollo

Si este proyecto te resulta útil, puedes apoyar voluntariamente su desarrollo continuo. El proyecto y todas sus funciones siguen siendo gratuitos y de código abierto, independientemente de las donaciones.

- **🌍 Internacional:** [Apoyar mediante Tribute (tarjeta bancaria)](https://web.tribute.tg/d/S0p)
- **🇷🇺 Rusia:** [Apoyar mediante SBP / Mir (aplicación bancaria)](https://pay.cloudtips.ru/p/9f240c8b)
- [Todas las formas de apoyar](docs/SUPPORT_ES.md) — incluidos USDT, USDC y Bitcoin.

<div align="center">

**Dos dominios. Unos minutos. Tu propio servidor 3x-ui / Xray.**

⭐ Si este instalador te ha resultado útil, puedes darle una [estrella en GitHub](https://github.com/xPROMSx/3x-ui-auto-nginx) para ayudar a otros a descubrirlo.

[Instalación](#installation) · [Versiones](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [Incidencias](https://github.com/xPROMSx/3x-ui-auto-nginx/issues)

</div>
