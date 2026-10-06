<?php
/**
 * Plugin Name: E.S.S. Storefront Checkout Handoff
 * Description: Restores a signed headless storefront cart into a WooCommerce session and redirects to native checkout.
 * Version: 1.0.0
 * Requires Plugins: woocommerce
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

final class ESS_Storefront_Checkout_Handoff {
    private const ACTION = 'ess_storefront_checkout';
    private const MAX_TOKEN_LENGTH = 12000;

    public function __construct() {
        add_action( 'admin_post_nopriv_' . self::ACTION, array( $this, 'handle' ) );
        add_action( 'admin_post_' . self::ACTION, array( $this, 'handle' ) );
        add_action( 'woocommerce_checkout_create_order', array( $this, 'tag_order' ), 10, 2 );
        add_action( 'ess_sf_cleanup_handoff_token', array( $this, 'cleanup_handoff_token' ), 10, 1 );
    }

    private function fail( $message = 'Impossible de préparer le panier. Revenez à la boutique E.S.S. et réessayez.' ) {
        wp_die(
            esc_html( $message ),
            esc_html__( 'Commande E.S.S.', 'ess-storefront-checkout' ),
            array( 'response' => 400, 'back_link' => true )
        );
    }

    private function decode_token( $token ) {
        if ( ! defined( 'ESS_WC_HANDOFF_SECRET' ) || ! is_string( ESS_WC_HANDOFF_SECRET ) || strlen( ESS_WC_HANDOFF_SECRET ) < 32 ) {
            $this->fail( 'Le checkout E.S.S. n’est pas configuré. Contactez la boutique.' );
        }

        if ( ! is_string( $token ) || '' === $token || strlen( $token ) > self::MAX_TOKEN_LENGTH ) {
            $this->fail();
        }

        $parts = explode( '.', $token );
        if ( 2 !== count( $parts ) || ! preg_match( '/^[a-f0-9]{64}$/', $parts[1] ) ) {
            $this->fail();
        }

        $expected = hash_hmac( 'sha256', $parts[0], ESS_WC_HANDOFF_SECRET );
        if ( ! hash_equals( $expected, $parts[1] ) ) {
            $this->fail();
        }

        $encoded = strtr( $parts[0], '-_', '+/' );
        $padding = strlen( $encoded ) % 4;
        if ( $padding ) {
            $encoded .= str_repeat( '=', 4 - $padding );
        }
        $json = base64_decode( $encoded, true );
        $payload = is_string( $json ) ? json_decode( $json, true ) : null;
        if ( ! is_array( $payload ) ) {
            $this->fail();
        }

        $now = time();
        $issued = isset( $payload['iat'] ) ? absint( $payload['iat'] ) : 0;
        $expires = isset( $payload['exp'] ) ? absint( $payload['exp'] ) : 0;
        $jti = isset( $payload['jti'] ) ? (string) $payload['jti'] : '';
        if (
            1 !== absint( $payload['v'] ?? 0 ) ||
            ! preg_match( '/^[a-f0-9]{32}$/', $jti ) ||
            $issued < 1 ||
            $issued > $now + 60 ||
            $expires < $now ||
            $expires <= $issued ||
            $expires - $issued > 600
        ) {
            $this->fail( 'Ce lien de commande a expiré. Revenez au panier et réessayez.' );
        }

        $option_key = '_ess_sf_handoff_' . substr( hash( 'sha256', $jti ), 0, 40 );
        if ( ! add_option( $option_key, $expires, '', false ) ) {
            $this->fail( 'Ce lien de commande a déjà été utilisé. Revenez au panier et réessayez.' );
        }
        wp_schedule_single_event( $expires + 60, 'ess_sf_cleanup_handoff_token', array( $option_key ) );

        return $payload;
    }

    public function cleanup_handoff_token( $option_key ) {
        if ( is_string( $option_key ) && preg_match( '/^_ess_sf_handoff_[a-f0-9]{40}$/', $option_key ) ) {
            delete_option( $option_key );
        }
    }

    public function handle() {
        nocache_headers();

        if ( 'POST' !== strtoupper( sanitize_text_field( wp_unslash( $_SERVER['REQUEST_METHOD'] ?? '' ) ) ) ) {
            $this->fail();
        }
        if ( ! class_exists( 'WooCommerce' ) || ! function_exists( 'wc_load_cart' ) ) {
            $this->fail( 'Le checkout WooCommerce n’est pas disponible. Contactez la boutique E.S.S.' );
        }

        $token   = isset( $_POST['token'] ) ? sanitize_text_field( wp_unslash( $_POST['token'] ) ) : '';
        $payload = $this->decode_token( $token );
        $items   = $payload['items'] ?? null;
        if ( ! is_array( $items ) || empty( $items ) || count( $items ) > 30 ) {
            $this->fail();
        }

        wc_load_cart();
        if ( ! WC()->cart || ! WC()->session ) {
            $this->fail( 'La session WooCommerce n’a pas pu être ouverte. Réessayez.' );
        }

        $quantities = array();
        foreach ( $items as $item ) {
            if ( ! is_array( $item ) ) {
                $this->fail();
            }
            $product_id = isset( $item['id'] ) ? absint( $item['id'] ) : 0;
            $quantity   = isset( $item['qty'] ) ? absint( $item['qty'] ) : 0;
            if ( $product_id < 1 || $quantity < 1 || $quantity > 99 ) {
                $this->fail();
            }
            $quantities[ $product_id ] = ( $quantities[ $product_id ] ?? 0 ) + $quantity;
            if ( $quantities[ $product_id ] > 99 ) {
                $this->fail();
            }
        }

        WC()->cart->empty_cart( true );
        foreach ( $quantities as $product_id => $quantity ) {
            $product = wc_get_product( $product_id );
            if (
                ! $product ||
                'publish' !== get_post_status( $product_id ) ||
                ! $product->is_type( 'simple' ) ||
                '' === (string) $product->get_price( 'edit' ) ||
                ! $product->is_purchasable() ||
                ! $product->is_in_stock()
            ) {
                WC()->cart->empty_cart( true );
                $this->fail( 'Un produit du panier n’est plus disponible au prix affiché. Actualisez le catalogue E.S.S.' );
            }

            $added = WC()->cart->add_to_cart( $product_id, $quantity );
            if ( ! $added ) {
                WC()->cart->empty_cart( true );
                $this->fail( 'Un produit n’a pas pu être ajouté au panier WooCommerce. Actualisez le catalogue E.S.S.' );
            }
        }

        WC()->session->set( 'ess_storefront_handoff', time() );
        WC()->session->set_customer_session_cookie( true );
        WC()->cart->calculate_totals();

        $checkout_url = wc_get_checkout_url();
        if ( ! is_string( $checkout_url ) || '' === $checkout_url ) {
            $this->fail( 'La page de commande WooCommerce n’est pas configurée.' );
        }
        wp_safe_redirect( $checkout_url );
        exit;
    }

    public function tag_order( $order, $data ) {
        if ( ! $order instanceof WC_Order || ! WC()->session ) {
            return;
        }
        if ( WC()->session->get( 'ess_storefront_handoff' ) ) {
            $order->update_meta_data( '_ess_order_source', 'Boutique E.S.S. en ligne' );
        }
    }
}

new ESS_Storefront_Checkout_Handoff();
