<?php
/**
 * WPRepro Fix — Gestión de Plugins
 *
 * Permite al backend FastAPI activar o desactivar plugins remotamente.
 *
 * Request body (JSON):
 * {
 *   "action": "deactivate",          // "activate" | "deactivate"
 *   "plugins": ["plugin-slug/plugin-slug.php"]
 * }
 *
 * Endpoint especial GET /fix/plugins/list → lista todos los plugins con estado
 */

if ( ! defined( 'ABSPATH' ) ) exit;

function wprepro_fix_plugins( WP_REST_Request $request ): WP_REST_Response {

    // Necesario para activate/deactivate
    if ( ! function_exists( 'activate_plugin' ) ) {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
    }

    $body   = $request->get_json_params();
    $action = sanitize_text_field( $body['action'] ?? 'list' );

    // ── Listar todos los plugins ───────────────────────────────────────────
    if ( $action === 'list' ) {
        $all_plugins    = get_plugins();
        $active_plugins = get_option( 'active_plugins', [] );
        $list           = [];

        foreach ( $all_plugins as $slug => $data ) {
            $list[] = [
                'slug'    => $slug,
                'name'    => $data['Name'],
                'version' => $data['Version'],
                'active'  => in_array( $slug, $active_plugins, true ),
            ];
        }

        return wprepro_success( 'Lista de plugins obtenida', [ 'plugins' => $list ] );
    }

    // ── Activar / Desactivar ───────────────────────────────────────────────
    $plugins = $body['plugins'] ?? [];

    if ( empty( $plugins ) || ! is_array( $plugins ) ) {
        return wprepro_error( 'Debes enviar un array "plugins" con los slugs a gestionar.' );
    }

    $results = [];

    foreach ( $plugins as $plugin_slug ) {
        $plugin_slug = sanitize_text_field( $plugin_slug );

        // Validar que el plugin existe
        if ( ! file_exists( WP_PLUGIN_DIR . '/' . $plugin_slug ) ) {
            $results[ $plugin_slug ] = [
                'success' => false,
                'message' => 'Plugin no encontrado en el servidor',
            ];
            continue;
        }

        if ( $action === 'deactivate' ) {
            deactivate_plugins( $plugin_slug );
            $results[ $plugin_slug ] = [
                'success' => true,
                'message' => 'Desactivado correctamente',
            ];

        } elseif ( $action === 'activate' ) {
            $result = activate_plugin( $plugin_slug );

            if ( is_wp_error( $result ) ) {
                $results[ $plugin_slug ] = [
                    'success' => false,
                    'message' => $result->get_error_message(),
                ];
            } else {
                $results[ $plugin_slug ] = [
                    'success' => true,
                    'message' => 'Activado correctamente',
                ];
            }

        } else {
            $results[ $plugin_slug ] = [
                'success' => false,
                'message' => "Acción desconocida: {$action}",
            ];
        }
    }

    return wprepro_success( "Acción '{$action}' ejecutada", [ 'results' => $results ] );
}
