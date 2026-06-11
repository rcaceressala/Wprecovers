<?php
/**
 * Plugin Name: WPRepro Agent
 * Plugin URI:  https://wprecoverpro.com
 * Description: Agente remoto de WPRecover 2.0. Conecta con el backend FastAPI, recibe recomendaciones de los agentes IA y ejecuta fixes WP-CLI permitidos automáticamente.
 * Version:     2.3.0
 * Author:      WPRecover Pro
 * License:     GPL-2.0+
 * Text Domain: wprepro-agent
 */

if ( ! defined( 'ABSPATH' ) ) exit;

define( 'WPREPRO_VERSION', '2.3.0' );
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

    $api_url    = get_option( 'wprepro_api_url', 'http://localhost:8000' );
    $status     = wprepro_check_connection( $api_url );
    $key_set    = defined( 'WPREPRO_API_KEY' ) && ! empty( WPREPRO_API_KEY );
    $execute_ep = trailingslashit( get_site_url() ) . 'wp-json/' . WPREPRO_API_NS . '/execute';
    $snippet_ep = trailingslashit( get_site_url() ) . 'wp-json/' . WPREPRO_API_NS . '/execute-snippet';
    ?>
    <div class="wrap">
        <h1>WPRepro Agent <small style="font-weight:normal;color:#646970;">v<?php echo esc_html( WPREPRO_VERSION ); ?></small></h1>

        <div style="margin:12px 0;padding:10px 14px;border-left:4px solid <?php echo $status['ok'] ? '#46b450' : '#dc3232'; ?>;background:#fff;">
            <?php if ( $status['ok'] ) : ?>
                &#9989; <strong>Conectado</strong> — <?php echo esc_html( $api_url ); ?>
            <?php else : ?>
                &#10060; <strong>Sin conexión</strong> — <?php echo esc_html( $status['error'] ); ?>
            <?php endif; ?>
        </div>

        <div style="margin:12px 0;padding:10px 14px;border-left:4px solid <?php echo $key_set ? '#46b450' : '#dc3232'; ?>;background:#fff;">
            <?php if ( $key_set ) : ?>
                &#9989; <strong>WPREPRO_API_KEY configurada</strong> — endpoints de ejecución listos:<br>
                <code><?php echo esc_html( $execute_ep ); ?></code> (WP-CLI)<br>
                <code><?php echo esc_html( $snippet_ep ); ?></code> (PHP snippets)
            <?php else : ?>
                &#10060; <strong>WPREPRO_API_KEY no definida.</strong> Agrega esto a <code>wp-config.php</code> antes de
                <code>/* That's all, stop editing! */</code>:<br>
                <code>define( 'WPREPRO_API_KEY', 'genera-una-clave-larga-y-aleatoria' );</code>
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

// ── Activation: warn if WPREPRO_API_KEY is missing ─────────────────────────────

register_activation_hook( __FILE__, function () {
    if ( ! defined( 'WPREPRO_API_KEY' ) || empty( WPREPRO_API_KEY ) ) {
        set_transient( 'wprepro_missing_key_notice', true, 30 );
    }
});

add_action( 'admin_notices', function () {
    if ( get_transient( 'wprepro_missing_key_notice' ) ) {
        echo '<div class="notice notice-error"><p>';
        echo '<strong>WPRepro Agent:</strong> No se encontró <code>WPREPRO_API_KEY</code> en <code>wp-config.php</code>. ';
        echo 'Agrega la siguiente línea antes de <code>/* That\'s all, stop editing! */</code>:<br>';
        echo '<code>define( \'WPREPRO_API_KEY\', \'tu-clave-secreta-aqui\' );</code>';
        echo '</p></div>';
        delete_transient( 'wprepro_missing_key_notice' );
    }
});

// ── wprepro_fix custom post type ────────────────────────────────────────────
//
// Approved PHP fixes generated by WPRecover's AI agents are stored as
// `wprepro_fix` posts. A `publish` post is eval()'d on every `init`; a
// `draft` post is staged but inactive until approved via
// POST /execute-snippet {action:"activate"}.

add_action( 'init', function () {
    register_post_type( 'wprepro_fix', [
        'label'    => 'WPRepro Fixes',
        'public'   => false,
        'show_ui'  => true,
        'supports' => [ 'title', 'editor' ],
    ] );
}, 10 );

// ── Run active fixes ─────────────────────────────────────────────────────────
//
// Published `wprepro_fix` posts only exist after a human approves them via
// WPRecover's pending-fix flow (or FIX_AUTO_APPROVE=true). Each post's
// content is a PHP snippet (without <?php tags) executed on every request.

add_action( 'init', function () {
    $fixes = get_posts( [
        'post_type'   => 'wprepro_fix',
        'post_status' => 'publish',
        'numberposts' => -1,
    ] );

    foreach ( $fixes as $fix ) {
        $code = trim( (string) $fix->post_content );
        $code = preg_replace( '/^\s*<\?php\s*/i', '', $code );
        $code = preg_replace( '/\?>\s*$/', '', $code );

        if ( $code === '' ) continue;

        try {
            eval( $code );
        } catch ( \Throwable $e ) {
            error_log( "WPRepro Agent: error running fix #{$fix->ID}: " . $e->getMessage() );
        }
    }
}, 20 );

// ── REST API: routes ─────────────────────────────────────────────────────────

add_action( 'rest_api_init', function () {
    register_rest_route( WPREPRO_API_NS, '/execute', [
        'methods'             => 'POST',
        'callback'            => 'wprepro_route_execute',
        'permission_callback' => 'wprepro_authenticate',
    ]);

    register_rest_route( WPREPRO_API_NS, '/execute-snippet', [
        'methods'             => 'POST',
        'callback'            => 'wprepro_route_execute_snippet',
        'permission_callback' => 'wprepro_authenticate',
    ]);
});

// ── Auth ─────────────────────────────────────────────────────────────────────
//
// Every request to /wp-json/wprepro/v1/execute must include:
//   X-WPRepro-Key: <value of WPREPRO_API_KEY in wp-config.php>
//
// Define it once in wp-config.php:
//   define( 'WPREPRO_API_KEY', 'genera-una-clave-larga-y-aleatoria' );

function wprepro_authenticate( WP_REST_Request $request ) {
    if ( ! defined( 'WPREPRO_API_KEY' ) || empty( WPREPRO_API_KEY ) ) {
        return new WP_Error(
            'wprepro_not_configured',
            'WPRepro Agent no está configurado. Define WPREPRO_API_KEY en wp-config.php.',
            [ 'status' => 500 ]
        );
    }

    $provided_key = $request->get_header( 'X-WPRepro-Key' );

    if ( empty( $provided_key ) ) {
        return new WP_Error(
            'wprepro_missing_key',
            'Header X-WPRepro-Key requerido.',
            [ 'status' => 401 ]
        );
    }

    if ( ! hash_equals( WPREPRO_API_KEY, $provided_key ) ) {
        return new WP_Error(
            'wprepro_invalid_key',
            'API Key inválida.',
            [ 'status' => 403 ]
        );
    }

    return true;
}

// ── /execute: whitelist + safe command dispatcher ───────────────────────────
//
// Commands are NOT passed to a shell — there is no exec()/shell_exec() here.
// Each whitelisted "wp ..." command is parsed and mapped to the equivalent
// native WordPress function call. This keeps the endpoint usable on hosts
// where shell access is disabled and removes any command-injection surface.

const WPREPRO_ALLOWED_PATTERNS = [
    '/^wp\s+option\s+update\s+\S+/i',
    '/^wp\s+post\s+meta\s+update\s+\d+\s+\S+/i',
    '/^wp\s+plugin\s+(activate|deactivate|update|list|status)\b/i',
    '/^wp\s+cache\s+flush\s*$/i',
    '/^wp\s+rewrite\s+flush\s*$/i',
    '/^wp\s+yoast\b/i',
];

function wprepro_is_command_allowed( string $command ): bool {
    // Defense in depth: reject shell metacharacters / chaining outright,
    // even though commands are never shelled out.
    if ( preg_match( '/[;&|`$<>\r\n]/', $command ) ) {
        return false;
    }
    foreach ( WPREPRO_ALLOWED_PATTERNS as $pattern ) {
        if ( preg_match( $pattern, $command ) ) {
            return true;
        }
    }
    return false;
}

/**
 * Split a command string into tokens, honoring single/double-quoted args.
 */
function wprepro_tokenize( string $input ): array {
    $tokens  = [];
    $current = '';
    $quote   = null;

    for ( $i = 0, $len = strlen( $input ); $i < $len; $i++ ) {
        $ch = $input[ $i ];

        if ( $quote !== null ) {
            if ( $ch === $quote ) {
                $quote = null;
            } else {
                $current .= $ch;
            }
            continue;
        }

        if ( $ch === '"' || $ch === "'" ) {
            $quote = $ch;
            continue;
        }

        if ( ctype_space( $ch ) ) {
            if ( $current !== '' ) {
                $tokens[] = $current;
                $current  = '';
            }
            continue;
        }

        $current .= $ch;
    }

    if ( $current !== '' ) {
        $tokens[] = $current;
    }

    return $tokens;
}

/**
 * Read a `--flag=value` style argument from a token list.
 */
function wprepro_get_flag( array $tokens, string $flag ): ?string {
    foreach ( $tokens as $token ) {
        if ( strpos( $token, "--{$flag}=" ) === 0 ) {
            return substr( $token, strlen( "--{$flag}=" ) );
        }
    }
    return null;
}

function wprepro_decode_value( string $value, array $tokens ) {
    if ( wprepro_get_flag( $tokens, 'format' ) === 'json' ) {
        $decoded = json_decode( $value, true );
        if ( json_last_error() === JSON_ERROR_NONE ) {
            return $decoded;
        }
    }
    return $value;
}

function wprepro_cmd_option_update( string $command, array $tokens ): array {
    // wp option update <name> <value> [--format=json]
    $name  = $tokens[3] ?? null;
    $value = $tokens[4] ?? null;

    if ( ! $name || $value === null ) {
        return [ 'command' => $command, 'output' => 'Usage: wp option update <name> <value>', 'status' => 'error' ];
    }
    if ( ! preg_match( '/^[A-Za-z0-9_\-]+$/', $name ) ) {
        return [ 'command' => $command, 'output' => "Invalid option name '{$name}'", 'status' => 'error' ];
    }

    update_option( $name, wprepro_decode_value( $value, $tokens ) );
    return [ 'command' => $command, 'output' => "Option '{$name}' updated", 'status' => 'ok' ];
}

function wprepro_cmd_post_meta_update( string $command, array $tokens ): array {
    // tokens: [0]=wp [1]=post [2]=meta [3]=update [4]=<id> [5]=<key> [6]=<value>
    $id    = $tokens[4] ?? null;
    $key   = $tokens[5] ?? null;
    $value = $tokens[6] ?? null;

    if ( ! ctype_digit( (string) $id ) || ! $key || $value === null ) {
        return [ 'command' => $command, 'output' => 'Usage: wp post meta update <id> <key> <value>', 'status' => 'error' ];
    }
    if ( ! get_post( (int) $id ) ) {
        return [ 'command' => $command, 'output' => "Post {$id} not found", 'status' => 'error' ];
    }

    update_post_meta( (int) $id, $key, wprepro_decode_value( $value, $tokens ) );
    return [ 'command' => $command, 'output' => "Post meta '{$key}' updated for post {$id}", 'status' => 'ok' ];
}

function wprepro_resolve_plugin_file( string $slug ): ?string {
    if ( ! function_exists( 'get_plugins' ) ) {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
    }
    foreach ( array_keys( get_plugins() ) as $file ) {
        if ( $file === $slug || strpos( $file, "{$slug}/" ) === 0 || $file === "{$slug}.php" ) {
            return $file;
        }
    }
    return null;
}

function wprepro_cmd_plugin( string $command, array $tokens ): array {
    $action = $tokens[2] ?? '';
    $slug   = $tokens[3] ?? null;

    if ( ! function_exists( 'get_plugins' ) ) {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
    }

    switch ( $action ) {
        case 'list':
            $active = get_option( 'active_plugins', [] );
            $lines  = [];
            foreach ( get_plugins() as $file => $data ) {
                $state   = in_array( $file, $active, true ) ? 'active' : 'inactive';
                $lines[] = "{$data['Name']} ({$file}) - {$state}";
            }
            return [ 'command' => $command, 'output' => implode( "\n", $lines ), 'status' => 'ok' ];

        case 'status':
            if ( ! $slug ) {
                $active = get_option( 'active_plugins', [] );
                return [ 'command' => $command, 'output' => count( $active ) . ' plugin(s) active', 'status' => 'ok' ];
            }
            $file = wprepro_resolve_plugin_file( $slug );
            if ( ! $file ) {
                return [ 'command' => $command, 'output' => "Plugin '{$slug}' not found", 'status' => 'error' ];
            }
            $active = in_array( $file, get_option( 'active_plugins', [] ), true );
            return [ 'command' => $command, 'output' => "{$slug}: " . ( $active ? 'active' : 'inactive' ), 'status' => 'ok' ];

        case 'activate':
        case 'deactivate':
            if ( ! $slug ) {
                return [ 'command' => $command, 'output' => "Usage: wp plugin {$action} <slug>", 'status' => 'error' ];
            }
            $file = wprepro_resolve_plugin_file( $slug );
            if ( ! $file ) {
                return [ 'command' => $command, 'output' => "Plugin '{$slug}' not found", 'status' => 'error' ];
            }
            if ( $action === 'activate' ) {
                $result = activate_plugin( $file );
                if ( is_wp_error( $result ) ) {
                    return [ 'command' => $command, 'output' => $result->get_error_message(), 'status' => 'error' ];
                }
                return [ 'command' => $command, 'output' => "Plugin '{$slug}' activated", 'status' => 'ok' ];
            }
            deactivate_plugins( $file );
            return [ 'command' => $command, 'output' => "Plugin '{$slug}' deactivated", 'status' => 'ok' ];

        case 'update':
            return wprepro_cmd_plugin_update( $command, $slug );

        default:
            return [ 'command' => $command, 'output' => "Subcommand 'wp plugin {$action}' not implemented", 'status' => 'error' ];
    }
}

function wprepro_cmd_plugin_update( string $command, ?string $slug ): array {
    if ( ! $slug ) {
        return [ 'command' => $command, 'output' => 'Usage: wp plugin update <slug>', 'status' => 'error' ];
    }
    $file = wprepro_resolve_plugin_file( $slug );
    if ( ! $file ) {
        return [ 'command' => $command, 'output' => "Plugin '{$slug}' not found", 'status' => 'error' ];
    }

    require_once ABSPATH . 'wp-admin/includes/file.php';
    require_once ABSPATH . 'wp-admin/includes/misc.php';
    require_once ABSPATH . 'wp-admin/includes/plugin-install.php';
    require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';

    wp_update_plugins();

    $upgrader = new Plugin_Upgrader( new Automatic_Upgrader_Skin() );
    $result   = $upgrader->upgrade( $file );

    if ( is_wp_error( $result ) ) {
        return [ 'command' => $command, 'output' => $result->get_error_message(), 'status' => 'error' ];
    }
    if ( $result === false ) {
        return [ 'command' => $command, 'output' => "Plugin '{$slug}' is already up to date or update unavailable", 'status' => 'ok' ];
    }
    return [ 'command' => $command, 'output' => "Plugin '{$slug}' updated", 'status' => 'ok' ];
}

function wprepro_execute_command( string $command ): array {
    $tokens = wprepro_tokenize( $command );

    try {
        if ( ( $tokens[1] ?? '' ) === 'option' && ( $tokens[2] ?? '' ) === 'update' ) {
            return wprepro_cmd_option_update( $command, $tokens );
        }
        if ( ( $tokens[1] ?? '' ) === 'post' && ( $tokens[2] ?? '' ) === 'meta' && ( $tokens[3] ?? '' ) === 'update' ) {
            return wprepro_cmd_post_meta_update( $command, $tokens );
        }
        if ( ( $tokens[1] ?? '' ) === 'plugin' ) {
            return wprepro_cmd_plugin( $command, $tokens );
        }
        if ( ( $tokens[1] ?? '' ) === 'cache' && ( $tokens[2] ?? '' ) === 'flush' ) {
            wp_cache_flush();
            return [ 'command' => $command, 'output' => 'Object cache flushed', 'status' => 'ok' ];
        }
        if ( ( $tokens[1] ?? '' ) === 'rewrite' && ( $tokens[2] ?? '' ) === 'flush' ) {
            flush_rewrite_rules( false );
            return [ 'command' => $command, 'output' => 'Rewrite rules flushed', 'status' => 'ok' ];
        }
        if ( ( $tokens[1] ?? '' ) === 'yoast' ) {
            // Yoast/Rank Math sitemaps are generated on-demand; flushing
            // rewrite rules invalidates any cached sitemap output.
            flush_rewrite_rules( false );
            return [ 'command' => $command, 'output' => 'Sitemap cache invalidated (rewrite rules flushed)', 'status' => 'ok' ];
        }

        return [ 'command' => $command, 'output' => 'Command recognized but not implemented', 'status' => 'error' ];
    } catch ( \Throwable $e ) {
        return [ 'command' => $command, 'output' => $e->getMessage(), 'status' => 'error' ];
    }
}

/**
 * POST /wp-json/wprepro/v1/execute
 * Body: {"commands": ["wp option update blog_public 1", ...]}
 * Returns: {"results": [{"command": "...", "output": "...", "status": "ok|error"}]}
 */
function wprepro_route_execute( WP_REST_Request $request ): WP_REST_Response {
    $body     = $request->get_json_params();
    $commands = $body['commands'] ?? null;

    if ( ! is_array( $commands ) || empty( $commands ) ) {
        return new WP_REST_Response( [
            'results' => [],
            'error'   => 'Field "commands" must be a non-empty array',
        ], 400 );
    }

    $results = [];
    foreach ( $commands as $command ) {
        $command = trim( (string) $command );

        if ( ! wprepro_is_command_allowed( $command ) ) {
            $results[] = [
                'command' => $command,
                'output'  => 'Command not allowed by whitelist',
                'status'  => 'error',
            ];
            continue;
        }

        $results[] = wprepro_execute_command( $command );
    }

    return new WP_REST_Response( [ 'results' => $results ], 200 );
}

// ── /execute-snippet: stage / activate / delete PHP fix snippets ────────────
//
// Backed by the `wprepro_fix` custom post type. Snippets are created as
// `draft` (inactive) unless `auto_approve` is true, and only run (via
// wprepro_run_active_fixes on `init`) once `publish` (active).

/**
 * POST /wp-json/wprepro/v1/execute-snippet
 * Body: {"action": "create"|"activate"|"delete", ...}
 *   - create:   {ticket_id, title, code, auto_approve}
 *   - activate: {snippet_id}
 *   - delete:   {snippet_id}
 * Returns: {"snippet_id": int, "status": "active"|"inactive"|"deleted"}
 */
function wprepro_route_execute_snippet( WP_REST_Request $request ): WP_REST_Response {
    $body   = $request->get_json_params();
    $action = $body['action'] ?? 'create';

    switch ( $action ) {
        case 'activate':
            return wprepro_activate_fix_snippet( $body );
        case 'delete':
            return wprepro_delete_fix_snippet( $body );
        case 'create':
        default:
            return wprepro_create_fix_snippet( $body );
    }
}

function wprepro_create_fix_snippet( array $body ): WP_REST_Response {
    $code = $body['code'] ?? '';
    if ( ! is_string( $code ) || trim( $code ) === '' ) {
        return new WP_REST_Response( [ 'error' => 'Field "code" is required' ], 400 );
    }

    $ticket_id    = (string) ( $body['ticket_id'] ?? '' );
    $title        = (string) ( $body['title'] ?? "WPRecover Fix {$ticket_id}" );
    $auto_approve = ! empty( $body['auto_approve'] );

    $post_id = wp_insert_post( [
        'post_type'    => 'wprepro_fix',
        'post_title'   => $title,
        'post_content' => $code,
        'post_status'  => $auto_approve ? 'publish' : 'draft',
    ], true );

    if ( is_wp_error( $post_id ) ) {
        return new WP_REST_Response( [ 'error' => $post_id->get_error_message() ], 400 );
    }

    if ( $ticket_id !== '' ) {
        update_post_meta( $post_id, '_wprepro_ticket_id', $ticket_id );
    }

    return new WP_REST_Response( [
        'snippet_id' => $post_id,
        'status'     => $auto_approve ? 'active' : 'inactive',
    ], 200 );
}

function wprepro_activate_fix_snippet( array $body ): WP_REST_Response {
    $snippet_id = (int) ( $body['snippet_id'] ?? 0 );
    $post       = $snippet_id ? get_post( $snippet_id ) : null;

    if ( ! $post || $post->post_type !== 'wprepro_fix' ) {
        return new WP_REST_Response( [ 'error' => "Fix #{$snippet_id} not found" ], 404 );
    }

    $result = wp_update_post( [ 'ID' => $snippet_id, 'post_status' => 'publish' ], true );
    if ( is_wp_error( $result ) ) {
        return new WP_REST_Response( [ 'error' => $result->get_error_message() ], 400 );
    }

    return new WP_REST_Response( [ 'snippet_id' => $snippet_id, 'status' => 'active' ], 200 );
}

function wprepro_delete_fix_snippet( array $body ): WP_REST_Response {
    $snippet_id = (int) ( $body['snippet_id'] ?? 0 );
    $post       = $snippet_id ? get_post( $snippet_id ) : null;

    if ( ! $post || $post->post_type !== 'wprepro_fix' ) {
        return new WP_REST_Response( [ 'error' => "Fix #{$snippet_id} not found" ], 404 );
    }

    wp_delete_post( $snippet_id, true );

    return new WP_REST_Response( [ 'snippet_id' => $snippet_id, 'status' => 'deleted' ], 200 );
}
