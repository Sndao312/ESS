import base64
import hashlib
import hmac
import json
import unittest
from unittest.mock import Mock

from woocommerce_api import WooCommerceClient, WooCommerceError, normalise_product


class FakeResponse:
    def __init__(self, body, headers=None, status=200):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.headers = headers or {}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount=-1):
        return self._body if amount < 0 else self._body[:amount]


class FakeOpener:
    def __init__(self, body, headers=None, status=200):
        self.body = body
        self.headers = headers or {}
        self.status = status
        self.last_request = None

    def open(self, request, timeout=0):
        self.last_request = request
        return FakeResponse(self.body, self.headers, self.status)


class WooCommerceApiTests(unittest.TestCase):
    def make_client(self, opener=None, handoff_secret="h" * 64):
        return WooCommerceClient(
            "https://wp.example.test/shop", "ck_secret_key", "cs_secret_key",
            opener=opener, handoff_secret=handoff_secret,
        )

    def test_product_normalisation_returns_current_regular_and_sale_prices_only(self):
        product = normalise_product({
            "id": 14, "name": "Toner de test", "slug": "toner-test", "sku": "TON-014",
            "price": "12500", "regular_price": "16000", "sale_price": "12500", "on_sale": True,
            "purchase_price": "9000", "stock_status": "instock", "purchasable": True,
            "images": [{"src": "https://wp.example.test/uploads/toner.jpg", "alt": "Toner"}],
            "categories": [{"id": 2, "name": "Impression", "slug": "impression", "count": 2}],
            "description": '<p>Bon <strong>produit</strong><script>alert(1)</script><a href="javascript:alert(2)">lien</a></p>',
        })
        self.assertEqual(product["price"], "12500")
        self.assertEqual(product["regularPrice"], "16000")
        self.assertEqual(product["salePrice"], "12500")
        self.assertTrue(product["onSale"])
        self.assertTrue(product["hasPrice"])
        self.assertNotIn("quoteOnly", product)
        self.assertNotIn("regular_price", product)
        self.assertNotIn("purchase_price", product)
        self.assertNotIn("<script", product["description"])
        self.assertNotIn("javascript:", product["description"])
        self.assertEqual(product["categories"][0]["id"], 2)

    def test_blank_price_is_not_purchasable_and_image_must_be_safe(self):
        product = normalise_product({
            "id": 8, "name": "Article sans prix", "slug": "article-sans-prix", "price": "",
            "purchasable": False, "stock_status": "unknown",
            "images": [{"src": "javascript:alert(1)"}, {"src": "https://wp.example.test/a.png"}],
        })
        self.assertFalse(product["hasPrice"])
        self.assertIsNone(product["price"])
        self.assertFalse(product["purchasable"])
        self.assertNotIn("quoteOnly", product)
        self.assertEqual(len(product["images"]), 1)
        self.assertEqual(product["images"][0]["src"], "https://wp.example.test/a.png")

    def test_variable_products_are_not_directly_purchasable_without_a_variation_selector(self):
        product = normalise_product({
            "id": 9, "type": "variable", "price": "100", "purchasable": True,
            "stock_status": "instock",
        })
        self.assertTrue(product["hasPrice"])
        self.assertFalse(product["purchasable"])
        self.assertEqual(product["type"], "variable")

    def test_api_uses_v3_route_and_private_basic_auth_server_side(self):
        opener = FakeOpener([{"id": 2, "name": "Produit", "slug": "produit", "price": "99", "purchasable": True, "stock_status": "instock"}], {"X-WP-Total": "1", "X-WP-TotalPages": "1"})
        result = self.make_client(opener).product_list({"search": "classeur", "page": 1, "per_page": 8})
        self.assertEqual(result["total"], 1)
        request = opener.last_request
        self.assertIn("/wp-json/wc/v3/products?", request.full_url)
        self.assertEqual(request.get_header("Authorization").split()[0], "Basic")
        self.assertIn("search=classeur", request.full_url)

    def test_checkout_handoff_is_signed_and_only_contains_product_ids_and_quantities(self):
        client = self.make_client()
        client.product_by_id = Mock(return_value={
            "id": 22, "price": "18000", "hasPrice": True, "stockStatus": "instock",
            "purchasable": True, "type": "simple",
        })
        client._request = Mock(side_effect=AssertionError("native checkout handoff must not create a REST order"))
        response = client.create_checkout_handoff({"items": [{"id": 22, "qty": 2, "price": 1}]})
        self.assertEqual(response["checkoutAction"], "https://wp.example.test/shop/wp-admin/admin-post.php")
        encoded, signature = response["checkoutToken"].split(".")
        expected = hmac.new(b"h" * 64, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(signature, expected))
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        self.assertEqual(payload["items"], [{"id": 22, "qty": 2}])
        self.assertGreater(payload["exp"], payload["iat"])
        self.assertEqual(payload["exp"] - payload["iat"], 300)
        self.assertNotIn("price", payload)
        self.assertFalse(response["preview"])
        client.product_by_id.assert_called_once_with(22)

    def test_unpriced_product_is_rejected_and_never_handed_off(self):
        client = self.make_client()
        client.product_by_id = Mock(return_value={
            "id": 31, "price": None, "hasPrice": False, "stockStatus": "unknown",
            "purchasable": False, "type": "simple",
        })
        with self.assertRaisesRegex(ValueError, "Prix bientôt disponible"):
            client.create_checkout_handoff({"items": [{"id": 31, "qty": 1}]})

    def test_checkout_rejects_empty_cart_invalid_quantities_and_bot_field(self):
        with self.assertRaisesRegex(ValueError, "panier est vide"):
            WooCommerceClient.validate_cart({"items": []})
        with self.assertRaisesRegex(ValueError, "Quantité"):
            WooCommerceClient.validate_cart({"items": [{"id": 1, "qty": 100}]})
        with self.assertRaisesRegex(ValueError, "invalide"):
            WooCommerceClient.validate_cart({"website": "bot", "items": [{"id": 1, "qty": 1}]})

    def test_checkout_requires_a_server_side_handoff_secret(self):
        client = self.make_client(handoff_secret="short")
        client.product_by_id = Mock()
        with self.assertRaisesRegex(WooCommerceError, "ESS_WC_HANDOFF_SECRET"):
            client.create_checkout_handoff({"items": [{"id": 1, "qty": 1}]})
        client.product_by_id.assert_not_called()

    def test_homepage_uses_the_wordpress_featured_newest_and_popular_lists(self):
        client = self.make_client()
        rows = {
            "categories:1": ([{"id": 3, "name": "Bureau", "slug": "bureau", "count": 4}], {"X-WP-TotalPages": "1"}),
            "homepage:featured": ([{"id": 7, "name": "Mis en avant", "slug": "mise-en-avant", "price": "100", "purchasable": True, "stock_status": "instock"}], {}),
            "homepage:newest": ([{"id": 8, "name": "Nouveau", "slug": "nouveau", "price": "200", "purchasable": True, "stock_status": "instock"}], {}),
            "homepage:popular": ([{"id": 9, "name": "Populaire", "slug": "populaire", "price": "300", "purchasable": True, "stock_status": "instock"}], {}),
        }
        client._get_cached = Mock(side_effect=lambda key, _endpoint, _params=None: rows[key])
        home = client.homepage(brand="E.S.S.", phone="+221777477778", currency="FCFA")
        self.assertEqual(home["categories"][0]["id"], 3)
        self.assertEqual(home["featured"][0]["id"], 7)
        self.assertEqual(home["newest"][0]["id"], 8)
        self.assertEqual(home["popular"][0]["id"], 9)
        self.assertNotIn("devis", json.dumps(home, ensure_ascii=False).lower())

    def test_remote_http_wordpress_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            WooCommerceClient("http://wp.example.test", "ck", "cs")


if __name__ == "__main__":
    unittest.main()
