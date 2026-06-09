<?php
/**
 * WPRepro Agent — Página de ajustes en el admin de WordPress
 *
 * Guarda la URL del backend FastAPI en wp_options['wprepro_api_url'].
 * Por defecto: http://localhost:8000
 */

if ( ! defined( 'ABSPATH' ) ) exit;

add_action( 'admin_menu',    'wprepro_add_settings_page' );
add_action( 'admin_init',    'wprepro_register_settings' );

function wprepro_add_settings_page(): void {
    add_options_page(
        'WPRepro Agent',
        'WPRepro Agent',
        'manage_options',
        'wprepro-agent',
        'wprepro_settings_page_html'
    );
}

function wprepro_register_settings(): void {
    register_setting(
        'wprepro_settings_group',
        'wprepro_api_url',
        [
            'type'              => 'string',
            'sanitize_callback' => 'esc_url_raw',
            'default'           => 'http://localhost:8000',
        ]
    );
}

function wprepro_settings_page_html(): void {
    if ( ! current_user_can( 'manage_options' ) ) return;

    $api_url = get_option( 'wprepro_api_url', 'http://localhost:8000' );
    ?>
    <div class="wrap">
        <h1>WPRepro Agent — Configuración</h1>
        <form method="post" action="options.php">
            <?php settings_fields( 'wprepro_settings_group' ); ?>
            <table class="form-table" role="presentation">
                <tr>
                    <th scope="row">
                        <label for="wprepro_api_url">URL del backend WPRecover</label>
                    </th>
                    <td>
                        <input
                            type="url"
                            id="wprepro_api_url"
                            name="wprepro_api_url"
                            value="<?php echo esc_attr( $api_url ); ?>"
                            class="regular-text"
                            placeholder="http://localhost:8000"
                        />
                        <p class="description">
                            URL base del servidor FastAPI. Ejemplo: <code>http://localhost:8000</code>
                            para desarrollo o <code>https://api.wprecoverpro.com</code> en producción.
                        </p>
                    </td>
                </tr>
            </table>
            <?php submit_button( 'Guardar cambios' ); ?>
        </form>
    </div>
    <?php
}
