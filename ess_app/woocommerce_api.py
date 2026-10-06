"""Server-side WooCommerce REST API adapter for the E.S.S. storefront.

The consumer key and secret are read only from the server environment (or the
untracked .env file). They are never returned by this module to the browser.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 20
MAX_PAGES = 40
CACHE_SECONDS = 45


class WooCommerceError(RuntimeError):
    """Safe-to-display error raised by the server-side WooCommerce adapter."""


class _SameHostRedirects(HTTPRedirectHandler):
    """Do not forward WooCommerce credentials to a different host or plain HTTP."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if old.hostname != new.hostname or old.port != new.port:
            return None
        if old.scheme == "https" and new.scheme != "https":
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _DescriptionSanitizer(HTMLParser):
    """Keep a small, safe subset of WordPress product-description markup."""

    ALLOWED_TAGS = {
        "p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "h2", "h3", "h4",
        "blockquote", "a", "table", "thead", "tbody", "tr", "th", "td", "hr",
    }
    VOID_TAGS = {"br", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag not in self.ALLOWED_TAGS:
            return
        if tag == "a":
            href = next((value for key, value in attrs if key.lower() == "href"), None)
            if href:
                value = str(href).strip()
                scheme = urlsplit(value).scheme.lower()
                if scheme in ("http", "https", "mailto"):
                    self.parts.append(f'<a href="{escape(value, quote=True)}" rel="nofollow noopener noreferrer">')
                    return
        self.parts.append(f"<{tag}>")

    def handle_endtag(self, tag: str):
        tag = tag.lower()
        if tag in self.ALLOWED_TAGS and tag not in self.VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str):
        self.parts.append(escape(data))


def sanitize_description(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    parser = _DescriptionSanitizer()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return escape(re.sub(r"<[^>]*>", " ", value))
    return "".join(parser.parts)


def _as_price(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return format(number, "f")


def _safe_image_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("/assets/"):
        return value
    parsed = urlsplit(value)
    if parsed.scheme in ("http", "https") and parsed.netloc and not parsed.username and not parsed.password:
        return value
    return None


def normalise_product(raw: dict[str, Any]) -> dict[str, Any]:
    """Reduce a WooCommerce product to fields that are safe for the storefront."""
    if not isinstance(raw, dict):
        return {}
    raw_price = _as_price(raw.get("price"))
    regular_price = _as_price(raw.get("regular_price"))
    sale_price = _as_price(raw.get("sale_price"))
    stock_status = raw.get("stock_status")
    if stock_status not in ("instock", "outofstock", "onbackorder"):
        stock_status = "unknown"
    product_type = str(raw.get("type") or "simple")
    purchasable = bool(raw.get("purchasable", raw_price is not None and stock_status != "outofstock")) and product_type == "simple"
    on_sale = bool(raw.get("on_sale")) and regular_price is not None and sale_price is not None and sale_price < regular_price

    images = []
    for image in raw.get("images") or []:
        if not isinstance(image, dict):
            continue
        src = _safe_image_url(image.get("src"))
        if src:
            images.append({"src": src, "alt": str(image.get("alt") or raw.get("name") or "Produit E.S.S.")[:240]})

    categories = []
    for category in raw.get("categories") or []:
        if not isinstance(category, dict):
            continue
        try:
            category_id = int(category.get("id"))
        except (TypeError, ValueError):
            continue
        categories.append({
            "id": category_id,
            "name": str(category.get("name") or "Autres produits")[:160],
            "slug": str(category.get("slug") or "")[:160],
        })

    related_ids = []
    for item in raw.get("related_ids") or []:
        try:
            related_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    related_ids = related_ids[:12]

    return {
        "id": int(raw.get("id") or 0),
        "name": str(raw.get("name") or "Produit E.S.S.")[:240],
        "slug": str(raw.get("slug") or "")[:200],
        "sku": str(raw.get("sku") or "")[:100],
        "price": raw_price,
        "regularPrice": regular_price,
        "salePrice": sale_price,
        "onSale": on_sale,
        "hasPrice": raw_price is not None,
        "stockStatus": stock_status,
        "inStock": stock_status == "instock",
        "availability": {
            "instock": "En stock",
            "outofstock": "Rupture de stock",
            "onbackorder": "Disponibilité à confirmer",
            "unknown": "Disponibilité à confirmer",
        }[stock_status],
        "purchasable": purchasable,
        "type": str(raw.get("type") or "simple"),
        "featured": bool(raw.get("featured")),
        "dateCreated": str(raw.get("date_created") or ""),
        "images": images[:10],
        "categories": categories[:20],
        "shortDescription": sanitize_description(raw.get("short_description")),
        "description": sanitize_description(raw.get("description")),
        "relatedIds": related_ids,
    }


def _normalise_category(raw: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    try:
        category_id = int(raw.get("id"))
    except (TypeError, ValueError):
        return None
    image = raw.get("image") if isinstance(raw.get("image"), dict) else {}
    try:
        count = max(0, int(raw.get("count") or 0))
    except (TypeError, ValueError):
        count = 0
    return {
        "id": category_id,
        "name": str(raw.get("name") or "Autres produits")[:160],
        "slug": str(raw.get("slug") or "")[:160],
        "count": count,
        "image": _safe_image_url(image.get("src")),
    }


def _positive_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} invalide.")
    if result < minimum or result > maximum:
        raise ValueError(f"{label} doit être compris entre {minimum} et {maximum}.")
    return result


def _person_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


class WooCommerceClient:
    """Minimal WooCommerce REST v3 client using server-side Basic authentication."""

    def __init__(self, site_url: str, consumer_key: str, consumer_secret: str, *, opener=None,
                 handoff_secret: str = ""):
        site_url = str(site_url or "").strip().rstrip("/")
        parsed = urlsplit(site_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ValueError("ESS_WC_SITE_URL doit être l’URL de base WordPress (http(s)://…).")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ESS_WC_SITE_URL ne doit pas contenir d’identifiants, de paramètres ou de fragment.")
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("WooCommerce doit utiliser HTTPS hors environnement local.")
        self.site_url = site_url
        self.api_root = site_url + "/wp-json/wc/v3/"
        self.handoff_secret = str(handoff_secret or "").strip()
        self.consumer_key = str(consumer_key or "").strip()
        self.consumer_secret = str(consumer_secret or "").strip()
        if not self.consumer_key or not self.consumer_secret:
            raise ValueError("Renseignez ESS_WC_CONSUMER_KEY et ESS_WC_CONSUMER_SECRET côté serveur.")
        self._opener = opener or build_opener(_SameHostRedirects())
        self._cache: dict[str, tuple[float, Any]] = {}

    @classmethod
    def from_environment(cls) -> "WooCommerceClient":
        return cls(
            os.environ.get("ESS_WC_SITE_URL", ""),
            os.environ.get("ESS_WC_CONSUMER_KEY", ""),
            os.environ.get("ESS_WC_CONSUMER_SECRET", ""),
            handoff_secret=os.environ.get("ESS_WC_HANDOFF_SECRET", ""),
        )

    def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None,
                 payload: dict[str, Any] | None = None):
        endpoint = "/".join(part for part in str(endpoint).strip("/").split("/") if part)
        if not endpoint or any(part in (".", "..") for part in endpoint.split("/")):
            raise ValueError("Route WooCommerce invalide.")
        url = self.api_root + endpoint
        if params:
            query = {key: value for key, value in params.items() if value is not None and value != ""}
            if query:
                url += "?" + urlencode(query, doseq=True)
        token = base64.b64encode(f"{self.consumer_key}:{self.consumer_secret}".encode("utf-8")).decode("ascii")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = Request(url, data=data, method=method.upper(), headers={
            "Authorization": "Basic " + token,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "ESS-Storefront/1.0",
        })
        try:
            with self._opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise WooCommerceError("La réponse de WooCommerce est trop volumineuse.")
                headers = response.headers
                status = response.status
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read(64_000).decode("utf-8", errors="replace"))
            except Exception:
                detail = {}
            if exc.code in (401, 403):
                message = "WooCommerce a refusé l’accès. Vérifiez l’URL et les droits de la clé API côté serveur."
            elif exc.code == 404:
                message = "La route WooCommerce est introuvable. Vérifiez que l’API REST WooCommerce est activée."
            elif exc.code == 429:
                message = "WooCommerce limite temporairement les requêtes. Réessayez dans quelques instants."
            elif isinstance(detail, dict) and detail.get("message"):
                message = "WooCommerce n’a pas accepté la requête. Vérifiez les réglages du produit ou de la commande."
            else:
                message = f"WooCommerce a renvoyé une erreur HTTP {exc.code}."
            raise WooCommerceError(message) from None
        except URLError:
            raise WooCommerceError("Impossible de joindre WordPress. Vérifiez l’URL, HTTPS et la disponibilité du site.") from None
        except TimeoutError:
            raise WooCommerceError("WordPress met trop de temps à répondre. Réessayez dans quelques instants.") from None
        except OSError:
            raise WooCommerceError("Connexion à WordPress impossible pour le moment.") from None
        if status < 200 or status >= 300:
            raise WooCommerceError(f"WooCommerce a renvoyé une erreur HTTP {status}.")
        try:
            decoded = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WooCommerceError("WordPress a renvoyé une réponse JSON invalide.") from None
        return decoded, headers

    def _get_cached(self, cache_key: str, endpoint: str, params: dict[str, Any] | None = None):
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]
        result = self._request("GET", endpoint, params=params)
        self._cache[cache_key] = (now + CACHE_SECONDS, result)
        return result

    def categories(self) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        page = 1
        while page <= MAX_PAGES:
            rows, headers = self._get_cached(
                f"categories:{page}", "products/categories",
                {"per_page": 100, "page": page, "hide_empty": "true", "orderby": "name", "order": "asc"},
            )
            if not isinstance(rows, list):
                raise WooCommerceError("La réponse des catégories WordPress est invalide.")
            all_rows.extend(row for row in rows if isinstance(row, dict))
            try:
                pages = int(headers.get("X-WP-TotalPages", "1"))
            except (TypeError, ValueError):
                pages = 1
            if page >= pages or not rows:
                break
            page += 1
        return [category for row in all_rows if (category := _normalise_category(row))]

    def product_list(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = dict(filters or {})
        page = _positive_int(filters.pop("page", 1), "Page", 1, 10000)
        per_page = _positive_int(filters.pop("per_page", 24), "Nombre de produits", 1, 48)
        params: dict[str, Any] = {"status": "publish", "page": page, "per_page": per_page}

        search = str(filters.pop("search", "")).strip()
        if search:
            params["search"] = search[:100]
        category = filters.pop("category", None)
        if category not in (None, ""):
            params["category"] = _positive_int(category, "Catégorie", 1, 2_147_483_647)
        minimum = filters.pop("min_price", None)
        maximum = filters.pop("max_price", None)
        for key, value in (("min_price", minimum), ("max_price", maximum)):
            if value not in (None, ""):
                try:
                    decimal = Decimal(str(value))
                except (InvalidOperation, ValueError):
                    raise ValueError("Les bornes de prix doivent être des nombres valides.")
                if not decimal.is_finite() or decimal < 0 or decimal > Decimal("999999999999"):
                    raise ValueError("Les bornes de prix doivent être positives et raisonnables.")
                params[key] = format(decimal, "f")
        if "min_price" in params and "max_price" in params and Decimal(params["min_price"]) > Decimal(params["max_price"]):
            raise ValueError("Le prix minimum ne peut pas dépasser le prix maximum.")
        stock_status = filters.pop("stock_status", None)
        if stock_status in ("instock", "outofstock", "onbackorder"):
            params["stock_status"] = stock_status
        orderby = filters.pop("orderby", "date")
        if orderby not in ("date", "title", "price", "popularity", "rating", "menu_order"):
            orderby = "date"
        order = str(filters.pop("order", "asc")).lower()
        if order not in ("asc", "desc"):
            order = "asc"
        params["orderby"] = orderby
        params["order"] = order
        include = filters.pop("include", None)
        if include:
            ids = []
            for raw_id in str(include).split(",")[:48]:
                try:
                    product_id = int(raw_id)
                except ValueError:
                    continue
                if product_id > 0:
                    ids.append(product_id)
            if not ids:
                return {"products": [], "total": 0, "page": page, "perPage": per_page, "totalPages": 0}
            params["include"] = ",".join(map(str, dict.fromkeys(ids)))
        rows, headers = self._request("GET", "products", params=params)
        if not isinstance(rows, list):
            raise WooCommerceError("La réponse du catalogue WordPress est invalide.")
        try:
            total = max(0, int(headers.get("X-WP-Total", len(rows))))
        except (TypeError, ValueError):
            total = len(rows)
        try:
            total_pages = max(0, int(headers.get("X-WP-TotalPages", (total + per_page - 1) // per_page)))
        except (TypeError, ValueError):
            total_pages = (total + per_page - 1) // per_page
        return {
            "products": [normalise_product(row) for row in rows if isinstance(row, dict)],
            "total": total,
            "page": page,
            "perPage": per_page,
            "totalPages": total_pages,
        }

    def product_by_slug(self, slug: str) -> dict[str, Any] | None:
        slug = str(slug or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,199}", slug):
            return None
        rows, _ = self._request("GET", "products", params={"slug": slug, "status": "publish", "per_page": 1})
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
            return None
        return normalise_product(rows[0])

    def product_by_id(self, product_id: int) -> dict[str, Any] | None:
        # Use the collection endpoint so a product removed from WordPress yields an
        # empty result rather than looking like a missing REST route to the shopper.
        result = self.product_list({"include": str(int(product_id)), "page": 1, "per_page": 1})
        rows = result.get("products", [])
        if not rows or int(rows[0].get("id") or 0) != int(product_id):
            return None
        return rows[0]

    def homepage(self, *, brand: str, phone: str, currency: str) -> dict[str, Any]:
        categories = self.categories()
        rows, _ = self._get_cached(
            "homepage:featured", "products",
            {"status": "publish", "featured": "true", "per_page": 8, "orderby": "menu_order", "order": "asc"},
        )
        featured_products = [normalise_product(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        newest, _ = self._get_cached(
            "homepage:newest", "products",
            {"status": "publish", "per_page": 8, "orderby": "date", "order": "desc"},
        )
        popular, _ = self._get_cached(
            "homepage:popular", "products",
            {"status": "publish", "per_page": 8, "orderby": "popularity", "order": "desc"},
        )
        newest_products = [normalise_product(row) for row in newest if isinstance(row, dict)] if isinstance(newest, list) else []
        popular_products = [normalise_product(row) for row in popular if isinstance(row, dict)] if isinstance(popular, list) else []
        if not popular_products:
            popular_products = newest_products[:]
        return {
            "brand": brand,
            "phone": phone,
            "whatsapp": re.sub(r"\D", "", phone),
            "currency": currency,
            "taxMode": "HT",
            "backend": "woocommerce",
            "categories": categories,
            "featured": featured_products,
            "newest": newest_products,
            "popular": popular_products,
            "orderPolicy": "Les commandes et règlements sont traités par WooCommerce.",
            "fulfillmentPolicy": "Les modes et frais applicables dépendent des réglages de la boutique WooCommerce.",
        }

    @staticmethod
    def validate_cart(body: dict[str, Any]) -> dict[int, int]:
        if not isinstance(body, dict):
            raise ValueError("Le panier transmis est invalide.")
        if body.get("website"):
            raise ValueError("Requête invalide.")
        requested = body.get("items")
        if not isinstance(requested, list) or not requested or len(requested) > 30:
            raise ValueError("Le panier est vide ou contient trop d’articles (maximum 30 références).")
        quantities: dict[int, int] = {}
        for line in requested:
            if not isinstance(line, dict):
                raise ValueError("Une ligne du panier est invalide.")
            product_id = _positive_int(line.get("id"), "Produit", 1, 2_147_483_647)
            quantity = _positive_int(line.get("qty"), "Quantité", 1, 99)
            quantities[product_id] = quantities.get(product_id, 0) + quantity
            if quantities[product_id] > 99:
                raise ValueError("Maximum 99 unités par référence.")
        return quantities

    def create_checkout_handoff(self, body: dict[str, Any]) -> dict[str, Any]:
        """Sign a short-lived cart handoff for the native WooCommerce checkout.

        The browser posts this token to the companion WordPress plugin. The
        plugin restores the products into a real WooCommerce session, then
        redirects the shopper to the configured checkout page where shipping,
        taxes, gateway fields and payment are handled natively by WooCommerce.
        """
        if len(self.handoff_secret.encode("utf-8")) < 32:
            raise WooCommerceError("Le parcours de paiement n’est pas configuré côté serveur (ESS_WC_HANDOFF_SECRET).")

        quantities = self.validate_cart(body)
        handoff_items = []
        for product_id, quantity in quantities.items():
            product = self.product_by_id(product_id)
            if not product:
                raise ValueError("Un produit n’est plus publié. Actualisez le catalogue et réessayez.")
            if not product.get("hasPrice") or product.get("price") is None:
                raise ValueError("Prix bientôt disponible. Ce produit ne peut pas être commandé pour le moment.")
            if product.get("stockStatus") == "outofstock" or not product.get("purchasable"):
                raise ValueError("Un produit n’est pas disponible à l’achat. Actualisez le catalogue et réessayez.")
            if product.get("type") != "simple":
                raise ValueError("Ce type de produit n’est pas encore disponible dans le panier en ligne.")
            handoff_items.append({"id": product_id, "qty": quantity})

        now = int(time.time())
        payload = {
            "v": 1,
            "iat": now,
            "exp": now + 300,
            "jti": uuid.uuid4().hex,
            "items": handoff_items,
        }
        raw_payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded_payload = base64.urlsafe_b64encode(raw_payload).decode("ascii").rstrip("=")
        signature = hmac.new(self.handoff_secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).hexdigest()
        token = encoded_payload + "." + signature
        return {
            "checkoutAction": self.site_url + "/wp-admin/admin-post.php",
            "checkoutToken": token,
            "preview": False,
        }
