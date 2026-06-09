<?php
/**
 * WPRepro Fix — Limpieza de Caché
 *
 * Compatible con los principales plugins de caché:
 *  - WP Super Cache
 *  - W3 Total Cache
 *  - WP Rocket
 *  - LiteSpeed Cache
 *  - Autoptimize
 *  - Cache Enabler
 *  - WordPress Object Cache (wp_cache_flush)
 *
 * También limpia transients de la base de datos.
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_fix_cache( WP_REST_Request $request ): WP_REST_Response {
    $cleared = [];
    $skipped = [];

    // 1. WP Object Cache
    if ( function_exists( 'wp_cache_flush' ) ) {
        wp_cache_flush();
        $cleared[] = 'WordPress Object Cache (wp_cache_flush)';
    }

    // 2. WP Super Cache
    if ( function_exists( 'wp_cache_clear_cache' ) ) {
        wp_cache_clear_cache();
        $cleared[] = 'WP Super Cache';
    }

    // 3. W3 Total Cache
    if ( function_exists( 'w3tc_flush_all' ) ) {
        w3tc_flush_all();
        $cleared[] = 'W3 Total Cache';
    }

    // 4. WP Rocket
    if ( function_exists( 'rocket_clean_domain' ) ) {
        rocket_clean_domain();
        $cleared[] = 'WP Rocket';
    }

    // 5. LiteSpeed Cache
    if ( class_exists( 'LiteSpeed_Cache_API' ) ) {
        LiteSpeed_Cache_API::purge_all();
        $cleared[] = 'LiteSpeed Cache';
    }

    // 6. Autoptimize
    if ( class_exists( 'autoptimizeCache' ) ) {
        autoptimizeCache::clearall();
        $cleared[] = 'Autoptimize';
    }

    // 7. Cache Enabler
    if ( class_exists( 'Cache_Enabler' ) ) {
        Cache_Enabler::clear_total_cache();
        $cleared[] = 'Cache Enabler';
    }

    // 8. Transients expirados en la DB
    global $wpdb;
    $deleted = $wpdb->query(
        "DELETE FROM {$wpdb->options}
         WHERE option_name LIKE '_transient_%'
         AND option_name NOT LIKE '_transient_timeout_%'"
    );
    // Limpiar también los timeouts huérfanos
    $wpdb->query(
        "DELETE FROM {$wpdb->options}
         WHERE option_name LIKE '_transient_timeout_%'
         AND option_value < UNIX_TIMESTAMP()"
    );
    $cleared[] = "Transients de DB eliminados (~{$deleted} registros)";

    // 9. Caché de rewrite rules
    flush_rewrite_rules( false );
    $cleared[] = 'Rewrite rules recargadas';

    // Resumen
    if ( count( $cleared ) === 0 ) {
        return wprepro_error( 'No se encontró ningún sistema de caché compatible activo.' );
    }

    return wprepro_success( 'Caché limpiada correctamente', [
        'cleared' => $cleared,
        'skipped' => $skipped,
    ]);
}
