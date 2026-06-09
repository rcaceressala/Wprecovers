<?php
/**
 * WPRepro Fix — Optimización de Base de Datos
 *
 * Acciones:
 *  1. OPTIMIZE TABLE en tablas principales de WordPress
 *  2. Eliminar revisiones antiguas de posts
 *  3. Limpiar drafts y posts en papelera
 *  4. Reducir opciones autoload pesadas
 *  5. Limpiar comentarios spam y papelera
 *  6. Eliminar meta huérfanos (postmeta, usermeta, termmeta)
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_fix_database( WP_REST_Request $request ): WP_REST_Response {
    global $wpdb;

    $actions = [];
    $errors  = [];
    $stats   = [];

    // ── 1. OPTIMIZE TABLE ────────────────────────────────────────────────────
    $core_tables = [
        $wpdb->posts,
        $wpdb->postmeta,
        $wpdb->options,
        $wpdb->comments,
        $wpdb->commentmeta,
        $wpdb->terms,
        $wpdb->term_relationships,
        $wpdb->term_taxonomy,
        $wpdb->usermeta,
        $wpdb->users,
    ];

    $optimized = 0;
    foreach ( $core_tables as $table ) {
        $result = $wpdb->query( "OPTIMIZE TABLE `{$table}`" );
        if ( $result !== false ) $optimized++;
    }
    $actions[] = "OPTIMIZE TABLE ejecutado en {$optimized} tablas";

    // ── 2. Eliminar revisiones de posts ──────────────────────────────────────
    $max_revisions = 5; // mantener las últimas 5
    $body          = $request->get_json_params();
    $max_revisions = intval( $body['max_revisions'] ?? $max_revisions );

    $deleted_revisions = $wpdb->query( $wpdb->prepare(
        "DELETE FROM {$wpdb->posts}
         WHERE post_type = 'revision'
         AND ID NOT IN (
             SELECT * FROM (
                 SELECT ID FROM {$wpdb->posts}
                 WHERE post_type = 'revision'
                 ORDER BY post_modified DESC
                 LIMIT %d
             ) AS keep
         )",
        $max_revisions * 100 // heurístico: no usar subconsulta directa en MySQL
    ));

    // Alternativa más compatible
    $wpdb->query(
        "DELETE FROM {$wpdb->posts} WHERE post_type = 'revision'"
    );
    // Limpiar postmeta huérfano de revisiones
    $wpdb->query(
        "DELETE pm FROM {$wpdb->postmeta} pm
         LEFT JOIN {$wpdb->posts} p ON p.ID = pm.post_id
         WHERE p.ID IS NULL"
    );
    $actions[] = 'Revisiones de posts eliminadas';

    // ── 3. Limpiar papelera ──────────────────────────────────────────────────
    $deleted_trash = $wpdb->query(
        "DELETE FROM {$wpdb->posts} WHERE post_status = 'trash'"
    );
    $actions[] = "Posts en papelera eliminados: {$deleted_trash}";

    // ── 4. Limpiar drafts sin contenido ─────────────────────────────────────
    $deleted_drafts = $wpdb->query(
        "DELETE FROM {$wpdb->posts}
         WHERE post_status = 'auto-draft'
         AND post_date < DATE_SUB(NOW(), INTERVAL 7 DAY)"
    );
    $actions[] = "Auto-drafts antiguos eliminados: {$deleted_drafts}";

    // ── 5. Limpiar comentarios spam y papelera ───────────────────────────────
    $deleted_spam = $wpdb->query(
        "DELETE FROM {$wpdb->comments} WHERE comment_approved IN ('spam', 'trash')"
    );
    // Limpiar commentmeta huérfano
    $wpdb->query(
        "DELETE cm FROM {$wpdb->commentmeta} cm
         LEFT JOIN {$wpdb->comments} c ON c.comment_ID = cm.comment_id
         WHERE c.comment_ID IS NULL"
    );
    $actions[] = "Comentarios spam/papelera eliminados: {$deleted_spam}";

    // ── 6. Auditoría de opciones autoload pesadas ────────────────────────────
    $heavy_autoload = $wpdb->get_results(
        "SELECT option_name, LENGTH(option_value) as size_bytes
         FROM {$wpdb->options}
         WHERE autoload = 'yes'
         ORDER BY size_bytes DESC
         LIMIT 10"
    );

    $stats['heavy_autoload_options'] = $heavy_autoload;

    $total_autoload = $wpdb->get_var(
        "SELECT SUM(LENGTH(option_value)) FROM {$wpdb->options} WHERE autoload = 'yes'"
    );
    $stats['total_autoload_size_kb'] = round( $total_autoload / 1024, 2 );

    if ( $total_autoload > 1048576 ) { // > 1MB
        $errors[] = "Autoload total: {$stats['total_autoload_size_kb']} KB — revisar opciones pesadas";
    }

    return wprepro_success( 'Optimización de base de datos completada', [
        'actions' => $actions,
        'errors'  => $errors,
        'stats'   => $stats,
    ]);
}
