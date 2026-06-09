<?php
/**
 * Plugin Name: WPRepro Agent
 * Plugin URI:  https://wprecoverpro.com
 * Description: Agente remoto de WPRecover 2.0. Conecta con el backend FastAPI y aplica fixes automáticamente.
 * Version:     2.0.0
 * Author:      WPRecover Pro
 * License:     GPL-2.0+
 * Text Domain: wprepro-agent
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'WPREPRO_VERSION', '2.0.0' );
define( 'WPREPRO_API_NS',  'wprepro/v1' );

// ── Settings ─────────────────────────────────────────────────────────────────

add_action( 'admin_init', function () {
    register_setting( 'wprepro_group', 'wprepro_api_url', [
        'type'              => 'string',
        'sanitize_callback' => 'esc_url_raw',
        'default'           => 'http://localhost:8000',
    ]);
});

// ── Admin menu ────────────────────────────────────────────────────────────────

add_action( 'admin_menu', function () {
    add_options_page( 'WPRepro Agent', 'WPRepro Agent', 'manage_options', 'wprepro-agent', 'wprepro_settings_page' );
});

function wprepro_settings_page(): void {
    if ( ! current_user_can( 'manage_options' ) ) return;

    $api_url = get_option( 'wprepro_api_url', 'http://localhost:8000' );
    $status  = wprepro_check_connection( $api_url );
    ?>
    <div class="wrap">
        <h1>WPRepro Agent</h1>

        <div style="margin:12px 0;padding:10px 14px;border-left:4px solid <?php echo $status['ok'] ? '#46b450' : '#dc3232'; ?>;background:#fff;">
            <?php if ( $status['ok'] ) : ?>
                &#9989; <strong>Conectado</strong> — <?php echo esc_html( $api_url ); ?>
            <?php else : ?>
                &#10060; <strong>Sin conexión</strong> — <?php echo esc_html( $status['error'] ); ?>
            <?php endif; ?>
        </div>

        <form method="post" action="options.php">
            <?php settings_fields( 'wprepro_group' ); ?>
            <table class="form-table">
                <tr>
                    <th><label for="wprepro_api_url">URL del backend</label></th>
                    <td>
                        <input type="url" id="wprepro_api_url" name="wprepro_api_url"
                               value="<?php echo esc_attr( $api_url ); ?>"
                               class="regular-text" placeholder="http://localhost:8000" />
                        <p class="description">Ejemplo: <code>http://localhost:8000</code> (dev) o <code>https://api.wprecoverpro.com</code> (prod)</p>
                    </td>
                </tr>
            </table>
            <?php submit_button( 'Guardar' ); ?>
        </form>
    </div>
    <?php
}

// ── Connection check ──────────────────────────────────────────────────────────

function wprepro_check_connection( string $api_url ): array {
    $response = wp_remote_get( trailingslashit( $api_url ) . 'status', [
        'timeout' => 5,
        'headers' => [ 'Accept' => 'application/json' ],
    ]);

    if ( is_wp_error( $response ) ) {
        return [ 'ok' => false, 'error' => $response->get_error_message() ];
    }

    $code = wp_remote_retrieve_response_code( $response );
    if ( $code >= 200 && $code < 300 ) {
        return [ 'ok' => true ];
    }

    return [ 'ok' => false, 'error' => "HTTP {$code}" ];
}
