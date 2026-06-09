<?php
/**
 * Plugin Name: WPRepro Agent
 * Plugin URI:  https://wprecoverpro.com
 * Description: Agente remoto de WPRecover 2.0. Recibe instrucciones del backend FastAPI y aplica fixes automáticamente en el sitio WordPress.
 * Version:     1.0.0
 * Author:      WPRecover Pro
 * Author URI:  https://wprecoverpro.com
 * License:     GPL-2.0+
 * Text Domain: wprepro-agent
 */

// Seguridad: bloquear acceso directo
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

// Constantes del plugin
define( 'WPREPRO_VERSION',    '1.0.0' );
define( 'WPREPRO_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( 'WPREPRO_PLUGIN_URL', plugin_dir_url( __FILE__ ) );
define( 'WPREPRO_API_NS',     'wprepro/v1' );

// Cargar módulos
require_once WPREPRO_PLUGIN_DIR . 'includes/auth.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/api.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/admin.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/fixes/images.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/fixes/plugins.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/fixes/cache.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/fixes/security.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/fixes/database.php';
require_once WPREPRO_PLUGIN_DIR . 'includes/fixes/vitals.php';

// Helper: URL del backend FastAPI (configurable desde Ajustes > WPRepro Agent)
function wprepro_get_api_url(): string {
    return rtrim( get_option( 'wprepro_api_url', 'http://localhost:8000' ), '/' );
}

// Registrar REST API al iniciar WordPress
add_action( 'rest_api_init', 'wprepro_register_routes' );

// Activación: verificar que existe la API key
register_activation_hook( __FILE__, 'wprepro_on_activate' );
function wprepro_on_activate() {
    if ( ! defined( 'WPREPRO_API_KEY' ) || empty( WPREPRO_API_KEY ) ) {
        // Guardar aviso para mostrar en el admin
        set_transient( 'wprepro_missing_key_notice', true, 30 );
    }
}

// Aviso en el admin si falta la API key
add_action( 'admin_notices', 'wprepro_admin_notice_missing_key' );
function wprepro_admin_notice_missing_key() {
    if ( get_transient( 'wprepro_missing_key_notice' ) ) {
        echo '<div class="notice notice-error"><p>';
        echo '<strong>WPRepro Agent:</strong> No se encontró <code>WPREPRO_API_KEY</code> en <code>wp-config.php</code>. ';
        echo 'Agrega la siguiente línea antes de <code>/* That\'s all, stop editing! */</code>:<br>';
        echo '<code>define( \'WPREPRO_API_KEY\', \'tu-clave-secreta-aqui\' );</code>';
        echo '</p></div>';
        delete_transient( 'wprepro_missing_key_notice' );
    }
}
