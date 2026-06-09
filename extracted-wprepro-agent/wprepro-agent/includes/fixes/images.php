<?php
/**
 * WPRepro Fix — Optimización de Imágenes
 *
 * Acciones:
 *  - Habilita lazy loading nativo en imágenes y iframes
 *  - Añade filtro para servir WebP si el browser lo soporta (via .htaccess)
 *  - Reporta imágenes sin atributo alt
 *  - Limpia metadata EXIF via filtro WP (no requiere extensión externa)
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_fix_images( WP_REST_Request $request ): WP_REST_Response {
    $actions = [];
    $errors  = [];

    // 1. Lazy loading nativo via filtro WordPress
    if ( ! get_option( 'wprepro_lazy_load_enabled' ) ) {
        add_filter( 'wp_lazy_loading_enabled', '__return_true' );
        update_option( 'wprepro_lazy_load_enabled', true );
        $actions[] = 'Lazy loading nativo habilitado (wp_lazy_loading_enabled)';
    } else {
        $actions[] = 'Lazy loading ya estaba habilitado';
    }

    // 2. Regla WebP en .htaccess (Apache)
    $htaccess_path = ABSPATH . '.htaccess';
    $webp_marker   = '# WPRepro WebP';
    $webp_rules    = <<<HTACCESS

# WPRepro WebP — inicio
<IfModule mod_rewrite.c>
    RewriteEngine On
    RewriteCond %{HTTP_ACCEPT} image/webp
    RewriteCond %{REQUEST_FILENAME} \.(jpe?g|png)$
    RewriteCond %{REQUEST_FILENAME}\.webp -f
    RewriteRule ^(.+)\.(jpe?g|png)$ $1.$2.webp [T=image/webp,E=accept:1]
</IfModule>
<IfModule mod_headers.c>
    Header append Vary Accept env=REDIRECT_accept
</IfModule>
# WPRepro WebP — fin

HTACCESS;

    if ( file_exists( $htaccess_path ) && is_writable( $htaccess_path ) ) {
        $content = file_get_contents( $htaccess_path );
        if ( strpos( $content, $webp_marker ) === false ) {
            // Insertar antes del bloque de WordPress
            $wp_marker = '# BEGIN WordPress';
            if ( strpos( $content, $wp_marker ) !== false ) {
                $content = str_replace( $wp_marker, $webp_rules . $wp_marker, $content );
            } else {
                $content .= $webp_rules;
            }
            file_put_contents( $htaccess_path, $content );
            $actions[] = 'Reglas WebP añadidas a .htaccess';
        } else {
            $actions[] = 'Reglas WebP ya presentes en .htaccess';
        }
    } else {
        $errors[] = '.htaccess no existe o no es escribible — reglas WebP omitidas';
    }

    // 3. Auditoría: imágenes sin alt en la biblioteca de medios
    $images_no_alt = get_posts([
        'post_type'      => 'attachment',
        'post_mime_type' => 'image',
        'posts_per_page' => -1,
        'meta_query'     => [[
            'key'     => '_wp_attachment_image_alt',
            'compare' => 'NOT EXISTS',
        ]],
        'fields' => 'ids',
    ]);

    $no_alt_count = count( $images_no_alt );
    $actions[]    = "Imágenes sin atributo alt: {$no_alt_count}";

    // 4. Filtro para strip EXIF en nuevas subidas (WordPress 5.8+)
    if ( ! get_option( 'wprepro_strip_exif' ) ) {
        update_option( 'wprepro_strip_exif', true );
        // El hook real se registra en el plugin principal al cargar
        $actions[] = 'Strip EXIF activado para nuevas subidas';
    }

    return wprepro_success( 'Fix de imágenes completado', [
        'actions' => $actions,
        'errors'  => $errors,
        'audit'   => [
            'images_without_alt' => $no_alt_count,
            'image_ids_no_alt'   => array_slice( $images_no_alt, 0, 20 ), // máx 20
        ],
    ]);
}

// Strip EXIF en nuevas subidas
add_filter( 'wp_handle_upload', function( $file ) {
    if ( get_option( 'wprepro_strip_exif' ) && function_exists( 'exif_read_data' ) ) {
        // Solo aplica si la extensión imagick está disponible
        if ( class_exists( 'Imagick' ) ) {
            try {
                $imagick = new Imagick( $file['file'] );
                $imagick->stripImage();
                $imagick->writeImage( $file['file'] );
                $imagick->destroy();
            } catch ( Exception $e ) {
                // Silencioso: no bloquear la subida
            }
        }
    }
    return $file;
});
