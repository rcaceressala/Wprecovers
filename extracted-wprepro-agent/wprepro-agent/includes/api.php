<?php
/**
 * WPRepro Agent — Registro de endpoints REST API
 *
 * Base URL: https://tusitio.com/wp-json/wprepro/v1/
 *
 * Endpoints:
 *   GET  /status          → Info del sitio y estado del agente
 *   POST /fix/images      → Optimizar imágenes
 *   POST /fix/plugins     → Activar/desactivar plugins
 *   POST /fix/cache       → Limpiar caché
 *   POST /fix/security    → Aplicar headers de seguridad
 *   POST /fix/database    → Optimizar base de datos
 *   POST /fix/vitals      → Lazy load y Core Web Vitals
 *   POST /fix/all         → Ejecutar todos los fixes
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_register_routes() {

    $auth = 'wprepro_authenticate';

    // ── Status ──────────────────────────────────────────────────────────────
    register_rest_route( WPREPRO_API_NS, '/status', [
        'methods'             => 'GET',
        'callback'            => 'wprepro_route_status',
        'permission_callback' => $auth,
    ]);

    // ── Fixes individuales ──────────────────────────────────────────────────
    $fixes = [ 'images', 'plugins', 'cache', 'security', 'database', 'vitals' ];

    foreach ( $fixes as $fix ) {
        register_rest_route( WPREPRO_API_NS, "/fix/{$fix}", [
            'methods'             => 'POST',
            'callback'            => "wprepro_fix_{$fix}",
            'permission_callback' => $auth,
        ]);
    }

    // ── Fix all ─────────────────────────────────────────────────────────────
    register_rest_route( WPREPRO_API_NS, '/fix/all', [
        'methods'             => 'POST',
        'callback'            => 'wprepro_route_fix_all',
        'permission_callback' => $auth,
    ]);
}

// ── Callback: status ─────────────────────────────────────────────────────────
function wprepro_route_status( WP_REST_Request $request ): WP_REST_Response {
    global $wpdb;

    return wprepro_success( 'WPRepro Agent activo', [
        'agent_version' => WPREPRO_VERSION,
        'wp_version'    => get_bloginfo( 'version' ),
        'php_version'   => PHP_VERSION,
        'site_url'      => get_site_url(),
        'db_prefix'     => $wpdb->prefix,
        'multisite'     => is_multisite(),
        'memory_limit'  => WP_MEMORY_LIMIT,
        'debug_mode'    => WP_DEBUG,
        'active_plugins'=> get_option( 'active_plugins', [] ),
        'timestamp'     => current_time( 'c' ),
    ]);
}

// ── Callback: fix/all ────────────────────────────────────────────────────────
function wprepro_route_fix_all( WP_REST_Request $request ): WP_REST_Response {
    $results = [];

    $fixes = [
        'images'   => 'wprepro_fix_images',
        'cache'    => 'wprepro_fix_cache',
        'security' => 'wprepro_fix_security',
        'database' => 'wprepro_fix_database',
        'vitals'   => 'wprepro_fix_vitals',
    ];

    foreach ( $fixes as $key => $fn ) {
        $response       = $fn( $request );
        $results[ $key ] = $response->get_data();
    }

    return wprepro_success( 'Todos los fixes ejecutados', $results );
}
