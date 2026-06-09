<?php
/**
 * WPRepro Fix — Lazy Load & Core Web Vitals
 *
 * Optimizaciones:
 *  1. Lazy loading de iframes (YouTube, etc.)
 *  2. Deshabilitar emojis de WordPress (reduce requests)
 *  3. Deshabilitar embeds de WordPress (reduce JS)
 *  4. Mover scripts al footer
 *  5. Deshabilitar jQuery Migrate
 *  6. Añadir preconnect/dns-prefetch para dominios externos comunes
 *  7. Deshabilitar Heartbeat API o reducir su frecuencia
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_fix_vitals( WP_REST_Request $request ): WP_REST_Response {
    $actions = [];

    // ── 1. Emojis WP ────────────────────────────────────────────────────────
    if ( ! get_option( 'wprepro_disable_emojis' ) ) {
        update_option( 'wprepro_disable_emojis', true );
        $actions[] = 'Emojis de WordPress desactivados (ahorra ~10KB y 1 request)';
    } else {
        $actions[] = 'Emojis ya estaban desactivados';
    }

    // ── 2. WP Embeds ────────────────────────────────────────────────────────
    if ( ! get_option( 'wprepro_disable_embeds' ) ) {
        update_option( 'wprepro_disable_embeds', true );
        $actions[] = 'WP Embeds desactivados (ahorra wp-embed.min.js)';
    } else {
        $actions[] = 'Embeds ya estaban desactivados';
    }

    // ── 3. jQuery Migrate ───────────────────────────────────────────────────
    if ( ! get_option( 'wprepro_disable_jquery_migrate' ) ) {
        update_option( 'wprepro_disable_jquery_migrate', true );
        $actions[] = 'jQuery Migrate desactivado en frontend';
    } else {
        $actions[] = 'jQuery Migrate ya estaba desactivado';
    }

    // ── 4. Heartbeat API ────────────────────────────────────────────────────
    if ( ! get_option( 'wprepro_heartbeat_optimized' ) ) {
        update_option( 'wprepro_heartbeat_optimized', true );
        $actions[] = 'Heartbeat API reducida a 120s (solo en admin)';
    } else {
        $actions[] = 'Heartbeat ya estaba optimizada';
    }

    // ── 5. Lazy loading iframes ─────────────────────────────────────────────
    if ( ! get_option( 'wprepro_lazy_iframes' ) ) {
        update_option( 'wprepro_lazy_iframes', true );
        $actions[] = 'Lazy loading de iframes habilitado via filtro the_content';
    } else {
        $actions[] = 'Lazy loading de iframes ya estaba habilitado';
    }

    // ── 6. DNS Prefetch ─────────────────────────────────────────────────────
    if ( ! get_option( 'wprepro_dns_prefetch' ) ) {
        update_option( 'wprepro_dns_prefetch', true );
        $actions[] = 'Preconnect/DNS-prefetch añadidos para Google Fonts, GA y CDNs comunes';
    }

    return wprepro_success( 'Fix de Core Web Vitals completado', [
        'actions' => $actions,
        'note'    => 'Los filtros se aplican automáticamente en el siguiente carga de página.',
    ]);
}

// ── Aplicar optimizaciones cuando las opciones están activas ─────────────────

// Desactivar emojis
add_action( 'init', function() {
    if ( ! get_option( 'wprepro_disable_emojis' ) ) return;
    remove_action( 'wp_head',             'print_emoji_detection_script', 7 );
    remove_action( 'admin_print_scripts', 'print_emoji_detection_script' );
    remove_action( 'wp_print_styles',     'print_emoji_styles' );
    remove_action( 'admin_print_styles',  'print_emoji_styles' );
    remove_filter( 'the_content_feed',    'wp_staticize_emoji' );
    remove_filter( 'comment_text_rss',    'wp_staticize_emoji' );
    remove_filter( 'wp_mail',             'wp_staticize_emoji_for_email' );
    add_filter( 'tiny_mce_plugins',       fn($p) => array_diff( $p, ['wpemoji'] ) );
    add_filter( 'wp_resource_hints',      fn($urls, $relation_type) =>
        $relation_type === 'dns-prefetch'
            ? array_filter( $urls, fn($u) => strpos( $u, 'emoji' ) === false )
            : $urls,
        10, 2
    );
});

// Desactivar embeds
add_action( 'init', function() {
    if ( ! get_option( 'wprepro_disable_embeds' ) ) return;
    remove_action( 'rest_api_init',       'wp_oembed_register_route' );
    remove_filter( 'oembed_dataparse',    'wp_filter_oembed_result' );
    remove_action( 'wp_head',             'wp_oembed_add_discovery_links' );
    remove_action( 'wp_head',             'wp_oembed_add_host_js' );
    add_filter( 'embed_oembed_discover',  '__return_false' );
    add_filter( 'rewrite_rules_array',    fn($rules) => array_filter( $rules, fn($k) => strpos($k,'embed') === false, ARRAY_FILTER_USE_KEY ) );
    wp_deregister_script( 'wp-embed' );
});

// Desactivar jQuery Migrate
add_action( 'wp_default_scripts', function( $scripts ) {
    if ( ! get_option( 'wprepro_disable_jquery_migrate' ) ) return;
    if ( ! is_admin() && isset( $scripts->registered['jquery'] ) ) {
        $scripts->registered['jquery']->deps = array_diff(
            $scripts->registered['jquery']->deps,
            [ 'jquery-migrate' ]
        );
    }
});

// Optimizar Heartbeat
add_filter( 'heartbeat_settings', function( $settings ) {
    if ( ! get_option( 'wprepro_heartbeat_optimized' ) ) return $settings;
    $settings['interval'] = 120;
    return $settings;
});
add_action( 'init', function() {
    if ( ! get_option( 'wprepro_heartbeat_optimized' ) ) return;
    if ( ! is_admin() ) {
        wp_deregister_script( 'heartbeat' );
    }
});

// Lazy loading iframes
add_filter( 'the_content', function( $content ) {
    if ( ! get_option( 'wprepro_lazy_iframes' ) ) return $content;
    return preg_replace( '/<iframe(?![^>]*\bloading\b)/', '<iframe loading="lazy"', $content );
});

// DNS Prefetch / Preconnect
add_action( 'wp_head', function() {
    if ( ! get_option( 'wprepro_dns_prefetch' ) ) return;
    $hints = [
        'https://fonts.googleapis.com',
        'https://fonts.gstatic.com',
        'https://www.google-analytics.com',
        'https://www.googletagmanager.com',
        'https://cdnjs.cloudflare.com',
    ];
    foreach ( $hints as $url ) {
        echo "<link rel='preconnect' href='{$url}' crossorigin>\n";
        echo "<link rel='dns-prefetch' href='{$url}'>\n";
    }
}, 1 );
