<div align="center">

[🇷🇺 Русский](README.md) · [🇬🇧 English](README_EN.md) · [🇪🇬 العربية](README_AR.md) · [🇮🇷 فارسی](README_FA.md) · [🇨🇳 简体中文](README_ZH_CN.md) · 🇪🇸 **Español** · [🇹🇷 Türkçe](README_TR.md)

<h1 align="center"><img src="assets/branding/logo.png" alt="3X-UI AUTO NGINX" width="560"></h1>

### Despliegue automático de 3X-UI / XRAY-CORE en tu propio VPS

**REALITY · XHTTP · HYSTERIA2 · NGINX · HTTPS · BACKUP / RESTORE**

Dos dominios, un VPS limpio y unos minutos para completar la instalación.

[![Releases](https://img.shields.io/github/v/release/xPROMSx/3x-ui-auto-nginx)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Downloads](https://img.shields.io/github/downloads/xPROMSx/3x-ui-auto-nginx/total?label=Downloads)](https://github.com/xPROMSx/3x-ui-auto-nginx/releases)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04%20%7C%2026.04-E95420?logo=ubuntu&logoColor=white)](#technical-details)
[![Support](https://img.shields.io/badge/Support-Donate-EA4AAA)](docs/SUPPORT_ES.md)

[📦 Versiones](https://github.com/xPROMSx/3x-ui-auto-nginx/releases) · [✈️ Telegram Web Proxy Manager](#telemt-web-manager) · [❤️ Apoyar](#support-development) · [🐛 Informar de un problema](https://github.com/xPROMSx/3x-ui-auto-nginx/issues) · [💬 Contacto](https://t.me/promsdev)

</div>

**3X-UI AUTO NGINX** es un instalador gratuito de [3x-ui](https://github.com/MHSanaei/3x-ui) y Xray para tu propio VPS. Configura Nginx, certificados HTTPS, REALITY, XHTTP, Hysteria2, suscripciones y herramientas de diagnóstico. Su gestor interactivo permite instalar el servidor, cambiar dominios y administrar Backup/Restore v3. Entre las funciones opcionales están XTLS Vision, AmneziaWG 3.1 y AdGuard Home con DNS-over-HTTPS (DoH).

**Más que una instalación estándar de 3x-ui:** cada instalación nueva recibe sitios web multipágina distintos y personalizados para el panel y REALITY. En el dominio de REALITY, las solicitudes HTTPS habituales por TCP y las solicitudes HTTP/3 no autenticadas por UDP muestran el mismo sitio. Todo funciona con Nginx y Xray, sin Docker ni servidores web adicionales. Los cambios de v2.4.0 no se aplican automáticamente a los VPS instalados anteriormente.

## ✨ ¿Por qué elegir este proyecto?

| | |
| --- | --- |
| **Conexiones listas para usar**<br>REALITY, XHTTP y Hysteria2 quedan activados al instalar; hay transportes adicionales opcionales. | **Sitios de camuflaje completos**<br>Seis plantillas multipágina adaptables, con personalización única en cada instalación nueva. |
| **Camuflaje HTTP/3 de Hysteria2**<br>Las solicitudes HTTPS normales por TCP y las HTTP/3 no autenticadas por UDP muestran el mismo sitio en el dominio REALITY. | **Interfaces internas aisladas**<br>El panel y las suscripciones utilizan Nginx y HTTPS; sus puertos internos no se exponen directamente a internet. |
| **Backup / Restore v3**<br>Copias de seguridad, recuperación y migración a otro VPS conservando los datos y los sitios personalizados. | **Gestor y cambio de dominios**<br>Menú en ruso e inglés; cambia el dominio del panel, el de REALITY o ambos sin reinstalar. |
| **Certificados y seguridad automáticos**<br>Let's Encrypt con renovación automática; protección SSH y actualizaciones de seguridad opcionales. | **Funciones adicionales**<br>XTLS Vision, AmneziaWG 3.1, XHTTP para CDN y AdGuard Home con DoH. |

<a id="installation"></a>

## 🚀 Inicio rápido

Configura los registros DNS de **dos dominios** para que apunten a la IP de tu VPS: uno para el panel y otro para REALITY. Conéctate por SSH como **root** y comprueba que los puertos TCP **80 y 443** y el puerto UDP **443** sean accesibles desde internet. Consulta los [sistemas compatibles](#technical-details).

```bash
curl -fSL https://github.com/xPROMSx/3x-ui-auto-nginx/releases/latest/download/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

Al ejecutar el script, elige **1 — English** o **2 — Русский**. Después se abrirá el menú principal:

- **1 — Installation:** configurar un servidor nuevo o realizar una reinstalación completa.
- **2 — Change Domains:** cambiar el dominio del panel, de REALITY o ambos sin reinstalar.
- **3 — Backups:** crear, consultar y restaurar copias de seguridad.
- **4 — Telegram Web Proxy Manager:** abrir o instalar el gestor independiente del proxy de Telegram.
- **0 — Exit:** salir.

El menú requiere una sesión SSH con terminal interactiva.

<details>
<summary><strong>Descarga alternativa — si GitHub Releases no está disponible</strong></summary>

**La rama `main` se utiliza para el desarrollo.** Puede incluir cambios todavía no incorporados a una versión estable, con funciones insuficientemente probadas o errores. Para instalaciones habituales, utiliza la versión estable indicada arriba.

```bash
curl -fSL https://raw.githubusercontent.com/xPROMSx/3x-ui-auto-nginx/main/x-ui-latest.sh -o x-ui-latest.sh && bash x-ui-latest.sh
```

</details>

<a id="installation-vs-update"></a>

> [!CAUTION]
> **¡Instalar no significa actualizar!**
>
> Volver a ejecutar el script **sin parámetros** abre el gestor, pero no reinstala el servidor. Sin embargo, **Installation** sirve para un VPS limpio o una reinstalación completa.
>
> Si detecta una instalación existente, el script avisa de que se eliminarán los datos gestionados y solicita la confirmación exacta **YES**. La reinstalación sustituye la base de datos de 3X-UI y la configuración de nginx. **Guarda antes una copia de seguridad fuera del VPS.**
>
> **Change Domains** y **Backups** son operaciones independientes que no reinstalan el panel.

<details>
<summary><strong>¿Cómo se actualiza?</strong></summary>

- **3X-UI y Xray:** utiliza las herramientas de actualización del panel. Es posible que las nuevas versiones aún no se hayan probado con la configuración del proyecto.
- **3X-UI AUTO NGINX:** no se admite actualizar los componentes instalados sin reinstalarlos. Para usar funciones del gestor más reciente, descarga el script actual y elige la operación necesaria; el gestor comprobará si la instalación es compatible.
- **Backup / Restore:** guarda y restaura los datos, pero no actualiza los componentes.

**¡No selecciones Installation solo para actualizar!** Actualiza nginx, el kernel de Linux y otros paquetes con las herramientas del sistema operativo.

</details>

A continuación se describen las opciones que ofrece el instalador al elegir **Installation** en el menú principal.

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

El instalador configura Fail2ban para proteger SSH, DNS cifrado del sistema (DoT) y actualizaciones de seguridad automáticas. Si se cumplen las condiciones, también crea un archivo swap de 1 GiB, independientemente de la opción de seguridad avanzada.

**Lee los detalles siguientes antes de activar esta opción**, especialmente el horario de reinicios automáticos.

<details>
<summary>🔐 Descripción detallada de los ajustes de seguridad</summary>

Al elegir `Y` se activan las opciones de seguridad adicionales. La configuración del swap es independiente de esta elección:

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

<a id="xhttp-cdn"></a>

### 6. 🌐 VLESS + XHTTP para CDN

> `Add an additional CDN-compatible XHTTP connection? [y/N]:`

*Conexión adicional · No se instala por defecto (`N`)*

Se crea una conexión VLESS independiente con transporte XHTTP en modo packet-up, preparada para usarla a través de una CDN. La conexión se crea desactivada en 3X-UI.

Se utiliza el dominio HTTPS existente del panel, sin necesidad de otro dominio ni certificado. Una vez activada, la conexión también se puede usar directamente, sin CDN.

Para utilizar una CDN, debes configurar tu proveedor y ajustar los parámetros de Host en 3X-UI. El instalador no configura servicios CDN; proporciona un perfil de servidor listo para adaptarlo a tus necesidades.

---

<a id="6--adguard-home--dns-over-https"></a>

### 7. 🛡️ AdGuard Home + DNS-over-HTTPS

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

Desde **v2.4.1**, las instalaciones nuevas permiten buscar e instalar actualizaciones de AdGuard Home desde su interfaz web. Si instalaste AdGuard Home con una versión anterior de este instalador, habilita las actualizaciones con un solo comando en tu VPS:

```bash
sudo bash -c 'set -euo pipefail; umask 077; d=$(mktemp -d); trap '\''rm -rf -- "$d"'\'' EXIT; cd "$d"; u=https://github.com/xPROMSx/3x-ui-auto-nginx/releases/download/v2.4.1; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh" -o x-ui-latest.sh; curl -fLsS --connect-timeout 15 --max-time 120 "$u/x-ui-latest.sh.sha256" -o x-ui-latest.sh.sha256; sha256sum --check --strict x-ui-latest.sh.sha256; bash ./x-ui-latest.sh --enable-agh-updates'
```

</details>

---

<a id="7--creación-automática-del-cliente-y-la-suscripción"></a>

### 8. 👤 Creación automática del cliente y la suscripción

> `Create a client in 3X-UI and display a subscription link after installation? [Y/n]:`

*Recomendado · Activado por defecto (`Y`)*

El instalador crea un cliente en 3X-UI y genera una URL de suscripción HTTPS personal para las conexiones configuradas y compatibles.

El enlace aparecerá en el informe final. Si rechazas esta opción, podrás crear clientes manualmente desde el panel.

---

Al terminar se mostrarán **la URL del panel, el usuario y la contraseña, la URL de diagnóstico y el enlace de suscripción** (si elegiste crear un cliente). Si instalaste AdGuard Home, también verás la dirección de administración, la contraseña y el endpoint DoH.

Si una actualización del sistema operativo requiere reiniciar, el instalador lo indicará. **El primer reinicio es manual**: ejecuta `sudo reboot`.

## 🌐 Sitios de camuflaje y HTTP/3

**Sitios web completos en lugar de páginas de relleno.** Cada instalación nueva crea automáticamente sitios multipágina distintos para el panel y REALITY. Hay seis plantillas modernas con navegación funcional, ilustraciones y diseño adaptable a móviles. XTLS Vision, si se activa, recibe su propio sitio.

**Cada instalación tiene su propia apariencia.** El nombre, la paleta de colores, las imágenes y los textos se personalizan automáticamente. El diseño elegido se conserva al realizar Backup/Restore y al cambiar dominios.

**Hysteria2 con camuflaje HTTP/3.** Las solicitudes HTTPS normales por TCP y las solicitudes HTTP/3 no autenticadas por UDP en el dominio de REALITY muestran el mismo sitio completo. El panel y las suscripciones permanecen aislados del camuflaje HTTP/3 público.

## 🚀 Perfiles de conexión

| Conexión | Estado |
| --- | :---: |
| VLESS + REALITY | ✅ Activado por defecto |
| VLESS + XHTTP | ✅ Activado por defecto |
| VLESS + XHTTP para CDN | 🔧 Opcional, desactivado |
| Hysteria2 | ✅ Activado por defecto |
| VLESS + WebSocket (TLS) | ◻️ Desactivado por defecto |
| Trojan + gRPC | ◻️ Desactivado por defecto |
| VLESS + XTLS Vision | 🔧 Opcional |
| Amnezia WG | 🔧 Opcional |

REALITY, XHTTP y Hysteria2 quedan activados tras la instalación. WebSocket TLS y Trojan gRPC se crean, pero permanecen desactivados hasta que los habilites en el panel 3X-UI.

XTLS Vision, Amnezia WG y XHTTP para CDN solo se añaden si los seleccionas durante la instalación. XHTTP para CDN se crea desactivado y no aparece en las suscripciones hasta que lo actives y vincules un cliente.

Para usar las conexiones, crea clientes automáticamente durante la instalación o manualmente en el panel. Los clientes de Amnezia WG se crean por separado.

La compatibilidad depende de la aplicación cliente y de su versión. Con XHTTP a través de una CDN, también influyen la configuración y las limitaciones del proveedor.

### Suscripciones

Las suscripciones estándar, JSON y **Mihomo / Clash** se sirven mediante nginx y HTTPS. `provider=1` devuelve la suscripción original para los proveedores de proxy en lugar de una configuración completa de Clash.


<a id="change-domains"></a>

## 🌐 Cambiar dominios

En el menú principal, selecciona **2 — Change Domains**. Puedes cambiar el dominio del panel, el de REALITY o ambos sin reinstalar. Los nuevos registros DNS deben apuntar al VPS; el puerto TCP/80 debe estar accesible para emitir los certificados. Los dominios deben ser diferentes entre sí y del dominio de Vision.

Antes de los cambios se crea automáticamente un Backup v3 completo. Se conservan clientes, claves, ajustes y estadísticas de tráfico. El dominio de Vision no cambia. Después, puede que tengas que actualizar las URL de suscripción y la configuración de los clientes.

Solo se admiten instalaciones del proyecto que puedan reconocerse, incluidas las instalaciones v2.1.7 compatibles. Si ocurre un error, **no elimines las copias ni los datos de recuperación**. Si aparece `ROLLBACK_UNVERIFIED`, detente y conserva los datos de diagnóstico. [Detalles, limitaciones y recuperación](docs/MANAGER.md#change-domains).

## 💾 Copias de seguridad y restauración

En el menú principal, abre **3 — Backups** para crear copias, consultar los archivos disponibles o restaurarlos. Puedes utilizar una copia después de reinstalar el sistema operativo o al cambiar de VPS. Para restaurarla, deben coincidir el sistema operativo, su versión y la arquitectura del procesador.

También puedes utilizar estos comandos como root:

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


**¿No sabes cómo proteger tu VPS?** Puedes activar la seguridad avanzada durante la instalación para configurar protección SSH contra ataques de fuerza bruta, DNS cifrado y actualizaciones de seguridad. Antes, consulta los detalles y el horario de reinicios nocturnos en **Inicio rápido**.

**Importante:** protege también el acceso al servidor. Usa claves SSH y comprueba que funcionan antes de desactivar la autenticación por contraseña. El instalador no la desactiva automáticamente.

<a id="telemt-web-manager"></a>

## ✈️ Telegram Web Proxy Manager

[Telegram Web Proxy Manager](https://github.com/xPROMSx/telegram-web-proxy-manager) es un proyecto independiente para crear tu propio Telegram WEB Proxy con HTTPS, un sitio de camuflaje y actualizaciones con posibilidad de reversión.

**TWPM no forma parte de la instalación básica de 3X-UI.** La opción 4 del menú principal permite abrirlo o iniciar su instalación por separado tras confirmarla. Ambos proyectos se administran de manera independiente.

<a id="technical-details"></a>

## ⚙️ Detalles técnicos y compatibilidad

- **Sistemas:** Ubuntu 24.04, Ubuntu 26.04 y Debian 13.
- **UFW:** permite 80/tcp, 443/tcp y 443/udp (también 8443/udp al seleccionar AmneziaWG). Durante Installation, UFW solo se activa después de comprobar el acceso SSH; si no es seguro hacerlo, permanece desactivado y se muestra una advertencia. Después de Restore, el gestor puede activarlo **solo si se solicita expresamente** y se superan las comprobaciones de seguridad. El comando `x-ui-backup restore` no activa UFW.
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
