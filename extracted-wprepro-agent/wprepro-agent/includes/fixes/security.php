<?php
/**
 * WPRepro Fix — Headers de Seguridad
 *
 * Añade / actualiza headers HTTP de seguridad en .htaccess:
 *  - X-Frame-Options
 *  - X-Content-Type-Options
 *  - X-XSS-Protection
 *  - Referrer-Policy
 *  - Permissions-Policy
 *  - Strict-Transport-Security (HSTS)
 *  - Content-Security-Policy básico
 *
 * También desactiva XML-RPC y oculta la versión de WordPress.
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_fix_security( WP_REST_Request $request ): WP_REST_Response {
    $actions = [];
    $errors  = [];

    // ── 1. Headers HTTP via .htaccess ────────────────────────────────────────
    $htaccess_path  = ABSPATH . '.htaccess';
    $security_start = '# WPRepro Security Headers — inicio';
    $security_end   = '# WPRepro Security Headers — fin';

    $security_block = <<<HTACCESS
{$security_start}
<IfModule mod_headers.c>
    # Prevenir clickjacking
    Header always set X-Frame-Options "SAMEORIGIN"
    # Prevenir MIME sniffing
    Header always set X-Content-Type-Options "nosniff"
    # XSS Protection legacy
    Header always set X-XSS-Protection "1; mode=block"
    # Referrer Policy
    Header always set Referrer-Policy "strict-origin-when-cross-origin"
    # Permissions Policy
    Header always set Permissions-Policy "geolocation=(), microphone=(), camera=()"
    # HSTS (1 año) — solo activar si el sitio tiene SSL válido
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
    # CSP básico
    Header always set Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; frame-ancestors 'self';"
    # Eliminar header de versión de servidor
    Header unset X-Powered-By
    Header always unset X-Powered-By
</IfModule>
{$security_end}
HTACCESS;

    if ( file_exists( $htaccess_path ) && is_writable( $htaccess_path ) ) {
        $content = file_get_contents( $htaccess_path );

        // Reemplazar bloque existente o insertar nuevo
        if ( strpos( $content, $security_start ) !== false ) {
            $pattern = '/' . preg_quote( $security_start, '/' ) . '.*?' . preg_quote( $security_end, '/' ) . '/s';
            $content = preg_replace( $pattern, $security_block, $content );
            $actions[] = 'Headers de seguridad actualizados en .htaccess';
        } else {
            // Insertar al inicio del archivo, antes del bloque WP
            $wp_marker = '# BEGIN WordPress';
            if ( strpos( $content, $wp_marker ) !== false ) {
                $content = str_replace( $wp_marker, $security_block . "\n\n" . $wp_marker, $content );
            } else {
                $content = $security_block . "\n\n" . $content;
            }
            $actions[] = 'Headers de seguridad añadidos a .htaccess';
        }

        file_put_contents( $htaccess_path, $content );
    } else {
        $errors[] = '.htaccess no encontrado o no escribible';
    }

    // ── 2. Deshabilitar XML-RPC ──────────────────────────────────────────────
    if ( ! get_option( 'wprepro_xmlrpc_disabled' ) ) {
        update_option( 'wprepro_xmlrpc_disabled', true );
        $actions[] = 'XML-RPC desactivado via filtro WordPress';
    } else {
        $actions[] = 'XML-RPC ya estaba desactivado';
    }

    // ── 3. Ocultar versión de WordPress ─────────────────────────────────────
    if ( ! get_option( 'wprepro_hide_wp_version' ) ) {
        update_option( 'wprepro_hide_wp_version', true );
        $actions[] = 'Versión de WordPress ocultada del HTML (remove_action wp_head)';
    } else {
        $actions[] = 'Versión de WordPress ya estaba oculta';
    }

    // ── 4. Deshabilitar edición de archivos desde el admin ───────────────────
    if ( ! defined( 'DISALLOW_FILE_EDIT' ) ) {
        // No podemos definir constantes en runtime, sugerimos
        $actions[] = 'SUGERENCIA: Añade define("DISALLOW_FILE_EDIT", true) en wp-config.php';
    } else {
        $actions[] = 'DISALLOW_FILE_EDIT ya está definida';
    }

    return wprepro_success( 'Fix de seguridad completado', [
        'actions' => $actions,
        'errors'  => $errors,
    ]);
}

// Aplicar filtros de seguridad cuando las opciones están activas
add_filter( 'xmlrpc_enabled', function( $enabled ) {
    return get_option( 'wprepro_xmlrpc_disabled' ) ? false : $enabled;
});

add_action( 'init', function() {
    if ( get_option( 'wprepro_hide_wp_version' ) ) {
        remove_action( 'wp_head', 'wp_generator' );
        add_filter( 'the_generator', '__return_empty_string' );
    }
});
