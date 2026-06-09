=== WPRepro Agent ===
Contributors: wprecoverpro
Tags: performance, optimization, security, cache, remote
Requires at least: 5.8
Tested up to: 6.5
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later

Agente remoto de WPRecover 2.0. Recibe y ejecuta fixes de optimización desde el backend FastAPI.

== Descripción ==

WPRepro Agent es el componente WordPress de WPRecover 2.0.
Expone una REST API segura que permite al backend FastAPI aplicar fixes de rendimiento, seguridad y base de datos de forma remota y automática.

**Fixes incluidos:**
* Optimización de imágenes (lazy load, WebP, strip EXIF)
* Gestión remota de plugins (activar/desactivar)
* Limpieza de caché (compatible con WP Rocket, W3TC, LiteSpeed, etc.)
* Headers de seguridad HTTP en .htaccess
* Optimización de base de datos (revisiones, transients, spam)
* Core Web Vitals (emojis, embeds, jQuery Migrate, Heartbeat, DNS prefetch)

== Instalación ==

1. Sube la carpeta `wprepro-agent` a `/wp-content/plugins/`
2. Activa el plugin desde el panel de WordPress
3. Añade tu API key secreta en `wp-config.php`:
   `define( 'WPREPRO_API_KEY', 'tu-clave-secreta-larga' );`
4. Verifica la conexión desde el backend con:
   `GET https://tusitio.com/wp-json/wprepro/v1/status`
   Header: `X-WPRepro-Key: tu-clave-secreta-larga`

== Endpoints REST API ==

* `GET  /wp-json/wprepro/v1/status`       — Estado del agente
* `POST /wp-json/wprepro/v1/fix/images`   — Optimizar imágenes
* `POST /wp-json/wprepro/v1/fix/plugins`  — Gestionar plugins
* `POST /wp-json/wprepro/v1/fix/cache`    — Limpiar caché
* `POST /wp-json/wprepro/v1/fix/security` — Headers de seguridad
* `POST /wp-json/wprepro/v1/fix/database` — Optimizar DB
* `POST /wp-json/wprepro/v1/fix/vitals`   — Core Web Vitals
* `POST /wp-json/wprepro/v1/fix/all`      — Todos los fixes

== Changelog ==

= 1.0.0 =
* Versión inicial
