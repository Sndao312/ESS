import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from urllib.request import HTTPRedirectHandler, build_opener

import server


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class QuietHandler(server.Handler):
    def log_message(self, *_args):
        pass


class FakeWoo:
    def __init__(self):
        self.product = {
            "id": 41, "name": "Produit WordPress", "slug": "produit-wordpress", "sku": "ESS-41",
            "price": "12500", "regularPrice": "15000", "salePrice": "12500", "onSale": True,
            "hasPrice": True, "stockStatus": "instock", "inStock": True,
            "availability": "En stock", "purchasable": True, "type": "simple", "images": [], "categories": [],
            "shortDescription": "", "description": "", "relatedIds": [],
        }
        self.checkout_body = None

    def homepage(self, **kwargs):
        return {
            "backend": "woocommerce", "brand": kwargs["brand"], "phone": kwargs["phone"],
            "whatsapp": "221777477778", "currency": "FCFA",
            "categories": [{"id": 3, "name": "Bureau", "slug": "bureau", "count": 1, "image": None}],
            "featured": [self.product], "newest": [self.product], "popular": [self.product],
        }

    def product_list(self, filters):
        return {"products": [self.product], "total": 1, "page": 1, "perPage": 18, "totalPages": 1, "filters": filters}

    def product_by_slug(self, slug):
        return self.product if slug == self.product["slug"] else None

    def create_checkout_handoff(self, body):
        self.checkout_body = body
        return {
            "checkoutAction": "https://wp.example.test/wp-admin/admin-post.php",
            "checkoutToken": "signed-test-token",
            "preview": False,
        }


class StorefrontRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_backend = server.STORE_BACKEND
        cls.old_client = server._WOO_CLIENT
        cls.old_public_mode = server.PUBLIC_MODE
        cls.old_site_url = os.environ.get("ESS_WC_SITE_URL")
        server.STORE_BACKEND = "woocommerce"
        server.PUBLIC_MODE = False
        server._WOO_CLIENT = FakeWoo()
        os.environ["ESS_WC_SITE_URL"] = "https://wp.example.test"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        cls.opener = build_opener(NoRedirect())

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        server.STORE_BACKEND = cls.old_backend
        server._WOO_CLIENT = cls.old_client
        server.PUBLIC_MODE = cls.old_public_mode
        if cls.old_site_url is None:
            os.environ.pop("ESS_WC_SITE_URL", None)
        else:
            os.environ["ESS_WC_SITE_URL"] = cls.old_site_url

    def request(self, path, method="GET", payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base + path, method=method, data=body,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        try:
            with self.opener.open(request, timeout=3) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read()

    def test_wordpress_store_routes_and_legacy_management_isolation(self):
        status, _, payload = self.request("/api/store/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["backend"], "woocommerce")

        status, _, payload = self.request("/api/store/products?search=papier&per_page=18")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["filters"]["search"], "papier")

        product_status, _, product_body = self.request("/api/store/products/produit-wordpress")
        self.assertEqual(product_status, 200)
        self.assertTrue(json.loads(product_body)["onSale"])
        self.assertEqual(self.request("/api/state")[0], 404)
        self.assertEqual(self.request("/api/products")[0], 404)

    def test_checkout_handoff_and_wordpress_admin_redirect(self):
        status, headers, _ = self.request("/admin")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("Location"), "https://wp.example.test/wp-admin/")

        payload = {"items": [{"id": 41, "qty": 2}]}
        status, _, body = self.request("/api/store/checkout", method="POST", payload=payload)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertFalse(result["preview"])
        self.assertEqual(result["checkoutAction"], "https://wp.example.test/wp-admin/admin-post.php")
        self.assertEqual(result["checkoutToken"], "signed-test-token")
        self.assertEqual(server._WOO_CLIENT.checkout_body, payload)

    def test_old_orders_api_route_is_retired_in_woocommerce_mode(self):
        payload = {"items": [{"id": 41, "qty": 1}]}
        status, _, body = self.request("/api/store/orders", method="POST", payload=payload)
        self.assertEqual(status, 410)
        self.assertIn("checkout WooCommerce", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
