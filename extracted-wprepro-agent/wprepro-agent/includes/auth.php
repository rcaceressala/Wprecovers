<?php
/**
 * WPRepro Agent — Autenticación
 *
 * Valida que cada request al REST API incluya el header:
 *   X-WPRepro-Key: <valor de WPREPRO_API_KEY en wp-config.php>
 *
 * Uso en wp-config.php:
 *   define( 'WPREPRO_API_KEY', 'genera-una-clave-larga-y-aleatoria' );
 */

if ( ! defined( 'ABSPATH' ) ) exit;

/**
 * Verifica el header de autenticación en cada request.
 *
 * @param  WP_REST_Request $request
 * @return true|WP_Error
 */
function wprepro_authenticate( WP_REST_Request $request ) {

    // Si la constante no está definida, el plugin no está configurado
    if ( ! defined( 'WPREPRO_API_KEY' ) || empty( WPREPRO_API_KEY ) ) {
        return new WP_Error(
            'wprepro_not_configured',
            'WPRepro Agent no está configurado. Define WPREPRO_API_KEY en wp-config.php.',
            [ 'status' => 500 ]
        );
    }

    // Leer el header enviado por el backend FastAPI
    $provided_key = $request->get_header( 'X-WPRepro-Key' );

    if ( empty( $provided_key ) ) {
        return new WP_Error(
            'wprepro_missing_key',
            'Header X-WPRepro-Key requerido.',
            [ 'status' => 401 ]
        );
    }

    // Comparación segura contra timing attacks
    if ( ! hash_equals( WPREPRO_API_KEY, $provided_key ) ) {
        return new WP_Error(
            'wprepro_invalid_key',
            'API Key inválida.',
            [ 'status' => 403 ]
        );
    }

    return true;
}

/**
 * Helper: respuesta estandarizada de éxito
 */
function wprepro_success( string $message, array $data = [] ): WP_REST_Response {
    return new WP_REST_Response( [
        'success' => true,
        'message' => $message,
        'data'    => $data,
    ], 200 );
}

/**
 * Helper: respuesta estandarizada de error
 */
function wprepro_error( string $message, int $status = 400, array $data = [] ): WP_REST_Response {
    return new WP_REST_Response( [
        'success' => false,
        'message' => $message,
        'data'    => $data,
    ], $status );
}
