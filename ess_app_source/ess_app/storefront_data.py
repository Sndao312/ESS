"""Compatibility adapter for the old local catalogue while WooCommerce is prepared.

Production data still comes only from WooCommerce when ESS_STORE_BACKEND=woocommerce.
This adapter keeps the existing SQLite-backed preview available as an explicit
local development mode and does not expose costs or internal product fields.
"""
from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:150] or "produit"


def _stock_status(value: Any) -> str:
    if value is None:
        return "unknown"
    try:
        return "instock" if int(value) > 0 else "outofstock"
    except (TypeError, ValueError):
        return "unknown"


def _price(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() and parsed >= 0 else None


def local_product(record: dict[str, Any], public_product, family_labels: dict[str, str]) -> dict[str, Any]:
    public = public_product(record)
    category = family_labels.get(record.get("family"), record.get("family") or "Autres produits")
    cat_slug = _slug(category)
    raw_stock = record.get("stock")
    status = _stock_status(raw_stock)
    availability = {
        "instock": "En stock",
        "outofstock": "Rupture de stock",
        "unknown": "Disponibilité à confirmer",
    }[status]
    photo = public.get("photo")
    slug = f"{_slug(record.get('name'))}-{_slug(record.get('ref'))}"
    return {
        "id": str(record.get("id") or ""),
        "name": str(public.get("name") or "Produit E.S.S."),
        "slug": slug[:195],
        "sku": str(public.get("ref") or ""),
        "price": str(public["price"]) if public.get("price") is not None else None,
        "regularPrice": str(public["price"]) if public.get("price") is not None else None,
        "salePrice": None,
        "onSale": False,
        "hasPrice": public.get("price") is not None,
        "stockStatus": status,
        "inStock": status == "instock",
        "availability": availability,
        "purchasable": public.get("price") is not None and status != "outofstock",
        "type": "simple",
        "featured": bool(record.get("featured")),
        "dateCreated": str(record.get("createdAt") or ""),
        "images": ([{"src": photo, "alt": str(public.get("name") or "Produit E.S.S.")}] if photo else []),
        "categories": [{"id": cat_slug, "name": str(category), "slug": cat_slug}],
        "shortDescription": "",
        "description": "",
        "relatedIds": [],
    }


def _popularity(conn) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in conn.execute("SELECT payload_json FROM sales"):
        try:
            sale = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            continue
        for item in sale.get("items", []) if isinstance(sale, dict) else []:
            if not isinstance(item, dict):
                continue
            product_id = str(item.get("id", ""))
            try:
                qty = max(0, int(item.get("qty", 0)))
            except (TypeError, ValueError):
                qty = 0
            counts[product_id] = counts.get(product_id, 0) + qty
    return counts


def build_local_home(conn, read_products, public_product, family_labels: dict[str, str], *, brand: str,
                     phone: str, currency: str) -> dict[str, Any]:
    records = [p for p in read_products(conn) if p.get("active", True)]
    products = [local_product(record, public_product, family_labels) for record in records]
    popularity = _popularity(conn)
    by_id = {str(p.get("id")): local_product(p, public_product, family_labels) for p in records}
    featured = [by_id[str(p.get("id"))] for p in records if p.get("featured")]
    newest_ids = sorted(records, key=lambda p: str(p.get("createdAt") or ""), reverse=True)
    popular_ids = sorted(records, key=lambda p: (-popularity.get(str(p.get("id")), 0), str(p.get("name") or "").casefold()))

    counts: dict[str, dict[str, Any]] = {}
    for product in products:
        category = product["categories"][0]
        key = str(category["id"])
        if key not in counts:
            counts[key] = {**category, "count": 0, "image": product["images"][0]["src"] if product["images"] else None}
        counts[key]["count"] += 1
    categories = sorted(counts.values(), key=lambda item: str(item["name"]).casefold())
    if not featured:
        featured = products[:8]
    return {
        "brand": brand,
        "phone": phone,
        "whatsapp": re.sub(r"\D", "", phone),
        "currency": currency,
        "taxMode": "HT",
        "backend": "local-preview",
        "categories": categories,
        "featured": featured[:8],
        "newest": [by_id[str(p.get("id"))] for p in newest_ids[:8]],
        "popular": [by_id[str(p.get("id"))] for p in popular_ids[:8]],
        "orderPolicy": "Mode aperçu : les commandes de démonstration ne sont pas transmises à WooCommerce.",
        "fulfillmentPolicy": "Les commandes réelles et paiements sont traités par la boutique WooCommerce.",
    }


def list_local_products(conn, read_products, public_product, family_labels: dict[str, str], filters: dict[str, str], *,
                        per_page_default: int = 18) -> dict[str, Any]:
    records = [p for p in read_products(conn) if p.get("active", True)]
    products = [local_product(record, public_product, family_labels) for record in records]
    raw_by_id = {str(record.get("id")): record for record in records}
    popularity = _popularity(conn)
    search = str(filters.get("search") or "").strip().lower()
    search_norm = unicodedata.normalize("NFKD", search).encode("ascii", "ignore").decode("ascii")
    category = str(filters.get("category") or "").strip()
    status = str(filters.get("stock_status") or "").strip()

    min_price = _price(filters.get("min_price"))
    max_price = _price(filters.get("max_price"))
    if filters.get("min_price") not in (None, "") and min_price is None:
        raise ValueError("Le prix minimum doit être un nombre valide.")
    if filters.get("max_price") not in (None, "") and max_price is None:
        raise ValueError("Le prix maximum doit être un nombre valide.")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ValueError("Le prix minimum ne peut pas dépasser le prix maximum.")

    include = [part.strip() for part in str(filters.get("include") or "").split(",") if part.strip()]
    if include:
        include_set = set(include[:48])
        products = [p for p in products if p["id"] in include_set]
    if category:
        products = [p for p in products if p["categories"] and str(p["categories"][0]["id"]) == category]
    if status in ("instock", "outofstock", "onbackorder"):
        products = [p for p in products if p["stockStatus"] == status]
    if min_price is not None:
        products = [p for p in products if _price(p.get("price")) is not None and _price(p.get("price")) >= min_price]
    if max_price is not None:
        products = [p for p in products if _price(p.get("price")) is not None and _price(p.get("price")) <= max_price]
    if search_norm:
        def searchable(product):
            text = " ".join([product.get("name", ""), product.get("sku", ""), *(c.get("name", "") for c in product.get("categories", []))])
            return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
        products = [p for p in products if search_norm in searchable(p)]

    orderby = str(filters.get("orderby") or "title")
    order = str(filters.get("order") or "asc").lower()
    if order not in ("asc", "desc"):
        order = "asc"
    reverse = order == "desc"
    if orderby == "price":
        products.sort(key=lambda p: (_price(p.get("price")) is None, _price(p.get("price")) or Decimal(0), p["name"].casefold()), reverse=reverse)
    elif orderby == "date":
        products.sort(key=lambda p: str(p.get("dateCreated") or ""), reverse=reverse)
    elif orderby == "popularity":
        products.sort(key=lambda p: popularity.get(str(p.get("id")), 0), reverse=reverse)
    else:
        products.sort(key=lambda p: p["name"].casefold(), reverse=reverse)

    try:
        page = max(1, min(10000, int(filters.get("page") or 1)))
        per_page = max(1, min(48, int(filters.get("per_page") or per_page_default)))
    except (TypeError, ValueError):
        raise ValueError("Page ou nombre de produits invalide.")
    total = len(products)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    return {"products": products[start:start + per_page], "total": total, "page": page,
            "perPage": per_page, "totalPages": total_pages}


def find_local_product_by_slug(conn, read_products, public_product, family_labels: dict[str, str], slug: str):
    for record in read_products(conn):
        if record.get("active", True) is False:
            continue
        product = local_product(record, public_product, family_labels)
        if product["slug"] == slug:
            return product
    return None
