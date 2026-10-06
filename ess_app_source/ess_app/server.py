#!/usr/bin/env python3
"""Local E.S.S. catalogue, sales and stock application backed by SQLite."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import hmac
import re
import sqlite3
import unicodedata
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    """Load a simple, untracked KEY=VALUE .env file without overriding real env vars."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '\"'):
            value = value[1:-1]
        os.environ[key] = value


load_env_file(ROOT / ".env")
from woocommerce_api import WooCommerceClient, WooCommerceError
from storefront_data import build_local_home, find_local_product_by_slug, list_local_products

DATA = ROOT / "data"
ASSETS = ROOT / "assets"
UPLOADS = ASSETS / "uploads"
DB_PATH = DATA / "ess_local.db"
SEED_PATH = DATA / "catalog.json"
PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ESS_ADMIN_PASSWORD", "")
PUBLIC_MODE = os.environ.get("ESS_PUBLIC_MODE", "0") == "1"
STORE_BACKEND = os.environ.get("ESS_STORE_BACKEND", "local").strip().lower()
STORE_PHONE = os.environ.get("ESS_STORE_PHONE", "+221777477778")
STORE_CURRENCY = os.environ.get("ESS_STORE_CURRENCY", "FCFA")
STORE_BRAND = os.environ.get("ESS_STORE_BRAND", "ELMANSOUR SUPPLIES & SERVICES")
MAX_BODY = 120 * 1024 * 1024
MAX_STORE_ORDER_BODY = 64 * 1024
MAX_IMAGE = 8 * 1024 * 1024
_ORDER_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
_ORDER_ATTEMPTS_LOCK = Lock()
_WOO_CLIENT: WooCommerceClient | None = None
_WOO_CLIENT_LOCK = Lock()
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_local_product(record: dict) -> dict:
    """Drop the retired local quote flag and its old display-only pack label."""
    product = dict(record)
    product.pop("quoteOnly", None)
    if str(product.get("pack") or "").strip().casefold() in {"sur devis", "devis"}:
        product["pack"] = "Conditionnement non précisé"
    return product


def clean_local_order(record: dict) -> dict:
    """Keep legacy order history while removing obsolete quote-only markers."""
    order = dict(record)
    items = record.get("items")
    if isinstance(items, list):
        order["items"] = [dict(item) if isinstance(item, dict) else item for item in items]
    if order.get("status") == "quote_sent":
        order["status"] = "contacted"
    order.pop("quoteRequested", None)
    for item in order.get("items", []) if isinstance(order.get("items"), list) else []:
        if isinstance(item, dict):
            item.pop("quoteRequested", None)
    return order


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    with connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            ref TEXT NOT NULL UNIQUE,
            family TEXT NOT NULL,
            name TEXT NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_family ON products(family)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_ref ON products(ref)")
        conn.execute("""CREATE TABLE IF NOT EXISTS sales (
            number TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS receipts (
            receipt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS web_orders (
            number TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            sale_number TEXT
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_web_orders_date ON web_orders(created_at)")
        conn.execute("""CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""")
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            if not SEED_PATH.exists():
                raise RuntimeError(f"Catalogue de départ absent: {SEED_PATH}")
            seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
            stamp = now_iso()
            for product in seed.get("products", []):
                conn.execute(
                    "INSERT OR IGNORE INTO products(id,ref,family,name,data_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (product["id"], product["ref"], product["family"], product["name"],
                     json.dumps(product, ensure_ascii=False), stamp, stamp),
                )
            conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('initialized_from_catalog','2026')")
            print(f"Initialised SQLite with {len(seed.get('products', []))} catalogue records", flush=True)
        # Migrate old local records in place without deleting products, sales, or orders.
        for row in conn.execute("SELECT id,data_json FROM products").fetchall():
            original = json.loads(row["data_json"])
            clean = clean_local_product(original)
            if clean != original:
                conn.execute("UPDATE products SET data_json=? WHERE id=?",
                             (json.dumps(clean, ensure_ascii=False), row["id"]))
        for row in conn.execute("SELECT number,payload_json FROM web_orders").fetchall():
            original = json.loads(row["payload_json"])
            clean = clean_local_order(original)
            if clean != original:
                conn.execute("UPDATE web_orders SET status=?,payload_json=? WHERE number=?",
                             (clean.get("status", "pending_confirmation"),
                              json.dumps(clean, ensure_ascii=False), row["number"]))


def parse_json_body(handler: SimpleHTTPRequestHandler, max_bytes: int = MAX_BODY) -> dict:
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        raise ValueError("Taille de requête invalide.")
    if length <= 0:
        return {}
    if length > max_bytes:
        raise ValueError("Requête trop volumineuse.")
    try:
        value = json.loads(handler.rfile.read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON invalide.") from exc
    if not isinstance(value, dict):
        raise ValueError("Le corps doit être un objet JSON.")
    return value


def save_data_image(data_url: str) -> str:
    if not isinstance(data_url, str) or "," not in data_url:
        raise ValueError("Image invalide.")
    header, encoded = data_url.split(",", 1)
    match = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64$", header)
    if not match:
        raise ValueError("Format d’image non pris en charge (JPEG, PNG ou WebP uniquement).")
    mime = match.group(1).lower()
    ext = ALLOWED_IMAGE_TYPES.get(mime)
    if not ext:
        raise ValueError("Format d’image non pris en charge (JPEG, PNG ou WebP uniquement).")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("Contenu de l’image invalide.") from exc
    if not raw or len(raw) > MAX_IMAGE:
        raise ValueError("L’image doit faire au maximum 8 Mo.")
    # Check common signatures; do not trust the filename supplied by the browser.
    valid = (mime == "image/jpeg" and raw.startswith(b"\xff\xd8\xff")) or \
            (mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n")) or \
            (mime == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP")
    if not valid:
        raise ValueError("Le fichier ne semble pas être une image valide.")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = f"ess-{uuid.uuid4().hex}.{ext}"
    (UPLOADS / name).write_bytes(raw)
    return f"/assets/uploads/{name}"


def prepare_product_photo(product: dict) -> None:
    photo_data = product.pop("photoData", None)
    if photo_data:
        product["photo"] = save_data_image(photo_data)
        # Keep existing attribution for catalogue imagery during a backup restore.
        if not product.get("photoSourceKind") or product.get("photoSourceKind") == "upload":
            product["photoKind"] = "photo locale ajoutée par E.S.S."
            product["photoSource"] = None
            product["photoSourceKind"] = "upload"
            product["photoNote"] = "Image ajoutée à la base locale E.S.S."


def read_products(conn: sqlite3.Connection, include_images: bool = False) -> list[dict]:
    rows = conn.execute("SELECT data_json FROM products ORDER BY rowid").fetchall()
    products = [clean_local_product(json.loads(row["data_json"])) for row in rows]
    if include_images:
        assets_root = ASSETS.resolve()
        for product in products:
            photo = product.get("photo") or ""
            if photo.startswith("/assets/"):
                path = (ROOT / photo.lstrip("/")).resolve()
                try:
                    path.relative_to(assets_root)
                except ValueError:
                    continue
                mime = mimetypes.guess_type(path.name)[0] or ""
                if path.is_file() and mime.startswith("image/") and path.stat().st_size <= MAX_IMAGE:
                    product["photoData"] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return products


def read_state(conn: sqlite3.Connection, include_images: bool = False) -> dict:
    products = read_products(conn, include_images=include_images)
    sales = [json.loads(r["payload_json"]) for r in conn.execute("SELECT payload_json FROM sales ORDER BY date, rowid")]
    receipts = [json.loads(r["payload_json"]) for r in conn.execute("SELECT payload_json FROM receipts ORDER BY receipt_id")]
    orders = [clean_local_order(json.loads(r["payload_json"]))
              for r in conn.execute("SELECT payload_json FROM web_orders ORDER BY created_at DESC")]
    families = []
    for p in products:
        if p.get("active", True) and p.get("family") and p["family"] not in families:
            families.append(p["family"])
    catalog_count = sum(1 for p in products if p.get("source") == "catalogue" and p.get("active", True))
    supplier_count = sum(1 for p in products if p.get("source") == "liste_fournisseur" and p.get("active", True))
    active_count = sum(1 for p in products if p.get("active", True))
    notes = []
    missing_prices = []
    try:
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        notes = seed.get("notes", [])
        missing_prices = seed.get("missingSupplierPriceRefs", [])
    except Exception:
        pass
    return {
        "brand": "ELMANSOUR SUPPLIES & SERVICES",
        "catalogEdition": 2026,
        "currency": "FCFA",
        "taxMode": "HT",
        "catalogCount": catalog_count,
        "supplierOnlyCount": supplier_count,
        "productCount": active_count,
        "categories": families,
        "products": products,
        "sales": sales,
        "receipts": receipts,
        "orders": orders,
        "missingSupplierPriceRefs": missing_prices,
        "notes": notes,
        "storage": "SQLite local",
    }


def save_product(conn: sqlite3.Connection, product: dict, created: bool = False) -> None:
    product = clean_local_product(product)
    stamp = now_iso()
    prior = conn.execute("SELECT created_at FROM products WHERE id=?", (product["id"],)).fetchone()
    created_at = stamp if created or not prior else prior["created_at"]
    conn.execute(
        """INSERT INTO products(id,ref,family,name,data_json,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET ref=excluded.ref,family=excluded.family,name=excluded.name,
             data_json=excluded.data_json,updated_at=excluded.updated_at""",
        (product["id"], product["ref"], product["family"], product["name"],
         json.dumps(product, ensure_ascii=False), created_at, stamp),
    )


def get_product(conn: sqlite3.Connection, product_id: str) -> dict | None:
    row = conn.execute("SELECT data_json FROM products WHERE id=?", (product_id,)).fetchone()
    return clean_local_product(json.loads(row["data_json"])) if row else None


def optional_int(value, label: str, *, allow_negative: bool = False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label}: entrez un nombre entier.")
    try:
        numeric = float(value)
        if not numeric.is_integer():
            raise ValueError
        number = int(numeric)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label}: entrez un nombre entier.")
    if not allow_negative and number < 0:
        raise ValueError(f"{label}: la valeur ne peut pas être négative.")
    return number


def next_ref(conn: sqlite3.Connection) -> str:
    numbers = []
    for row in conn.execute("SELECT ref FROM products WHERE ref LIKE 'ESS-%'"):
        match = re.fullmatch(r"ESS-(\d+)", row["ref"])
        if match:
            numbers.append(int(match.group(1)))
    return f"ESS-{max(numbers, default=0)+1:05d}"


def insert_product(conn: sqlite3.Connection, product: dict) -> None:
    product = clean_local_product(product)
    stamp = now_iso()
    conn.execute(
        "INSERT INTO products(id,ref,family,name,data_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (product["id"], product["ref"], product["family"], product["name"],
         json.dumps(product, ensure_ascii=False), stamp, stamp),
    )


def migrate_legacy(conn: sqlite3.Connection, legacy: dict) -> bool:
    done = conn.execute("SELECT value FROM app_meta WHERE key='legacy_browser_migration'").fetchone()
    if done:
        return False
    overrides = legacy.get("overrides") or {}
    legacy_sales = legacy.get("sales") or []
    legacy_receipts = legacy.get("receipts") or []
    # An empty first visit should not block a later import of existing browser data.
    if not overrides and not legacy_sales and not legacy_receipts:
        return False
    for product_id, override in overrides.items():
        product = get_product(conn, str(product_id))
        if not product or not isinstance(override, dict):
            continue
        for key in ("sellPrice", "purchasePrice", "stock", "supplierRef", "userNote"):
            if key in override:
                product[key] = override[key]
        save_product(conn, product)
    for sale in legacy_sales:
        if isinstance(sale, dict) and sale.get("number") and sale.get("date"):
            conn.execute("INSERT OR IGNORE INTO sales(number,date,payload_json) VALUES(?,?,?)",
                         (str(sale["number"]), str(sale["date"]), json.dumps(sale, ensure_ascii=False)))
    for receipt in legacy_receipts:
        if isinstance(receipt, dict) and receipt.get("date"):
            conn.execute("INSERT INTO receipts(date,payload_json) VALUES(?,?)",
                         (str(receipt["date"]), json.dumps(receipt, ensure_ascii=False)))
    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('legacy_browser_migration',?)", (now_iso(),))
    return True


def restore_state(conn: sqlite3.Connection, snapshot: dict) -> None:
    products = snapshot.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("La sauvegarde ne contient pas de produits.")
    clean_products = []
    for item in products:
        if not isinstance(item, dict) or not item.get("id") or not item.get("ref") or not item.get("name") or not item.get("family"):
            raise ValueError("Une fiche produit de la sauvegarde est incomplète (id, référence, nom ou famille manquant).")
        item = dict(item)
        item["id"] = str(item["id"]).strip()
        item["ref"] = str(item["ref"]).strip()
        item["name"] = str(item["name"]).strip()
        item["family"] = str(item["family"]).strip()
        if not all((item["id"], item["ref"], item["name"], item["family"])):
            raise ValueError("Les champs obligatoires d’une fiche produit ne peuvent pas être vides.")
        prepare_product_photo(item)
        item.pop("photoData", None)
        item.setdefault("active", True)
        item.setdefault("source", "local")
        clean_products.append(item)
    # Validate uniqueness before replacing the existing database.
    refs = [p["ref"] for p in clean_products]
    ids = [p["id"] for p in clean_products]
    if len(refs) != len(set(refs)) or len(ids) != len(set(ids)):
        raise ValueError("La sauvegarde contient des références ou identifiants en double.")
    conn.execute("DELETE FROM products")
    conn.execute("DELETE FROM sales")
    conn.execute("DELETE FROM receipts")
    conn.execute("DELETE FROM web_orders")
    for product in clean_products:
        insert_product(conn, product)
    for sale in snapshot.get("sales", []):
        if isinstance(sale, dict) and sale.get("number") and sale.get("date"):
            conn.execute("INSERT INTO sales(number,date,payload_json) VALUES(?,?,?)",
                         (str(sale["number"]), str(sale["date"]), json.dumps(sale, ensure_ascii=False)))
    for receipt in snapshot.get("receipts", []):
        if isinstance(receipt, dict) and receipt.get("date"):
            conn.execute("INSERT INTO receipts(date,payload_json) VALUES(?,?)",
                         (str(receipt["date"]), json.dumps(receipt, ensure_ascii=False)))
    for order in snapshot.get("orders", []):
        if isinstance(order, dict) and order.get("number") and order.get("createdAt"):
            order = clean_local_order(order)
            conn.execute("INSERT INTO web_orders(number,created_at,status,payload_json,sale_number) VALUES(?,?,?,?,?)",
                         (str(order["number"]), str(order["createdAt"]), str(order.get("status", "pending_confirmation")),
                          json.dumps(order, ensure_ascii=False), order.get("saleNumber")))
    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES('restored_at',?)", (now_iso(),))


PUBLIC_FAMILY_LABELS = {
    "Références fournisseurs — cartouches & toners": "Toners & consommables d’impression",
    "Tambours & consommables": "Tambours & consommables",
}


def public_product(product: dict) -> dict:
    """Return only customer-safe catalogue fields; never expose costs or internal notes."""
    photo = product.get("photo")
    if isinstance(photo, str) and photo.startswith("/assets/"):
        photo_path = (ROOT / photo.lstrip("/")).resolve()
        try:
            photo_path.relative_to(ASSETS.resolve())
        except ValueError:
            photo = None
        else:
            if not photo_path.is_file():
                photo = None
    else:
        photo = None
    price = product.get("sellPrice")
    if price is not None:
        price = optional_int(price, "Prix client")
    kind = str(product.get("photoKind") or "")
    if "famille" in kind.lower():
        image_caption = "Visuel illustratif du type de produit"
    elif product.get("photoSourceKind") == "upload":
        image_caption = "Photo ajoutée par E.S.S."
    elif photo:
        image_caption = "Photo indicative : vérifier la variante et le conditionnement"
    else:
        image_caption = "Photo à confirmer"
    return {
        "id": str(product["id"]),
        "ref": str(product.get("ref") or ""),
        "name": str(product.get("name") or ""),
        "family": PUBLIC_FAMILY_LABELS.get(product.get("family"), product.get("family") or "Autres produits"),
        "pack": str(product.get("pack") or "Unité"),
        "brand": product.get("brand"),
        "declaredType": product.get("declaredType"),
        "price": price,
        "hasPrice": price is not None,
        "photo": photo,
        "imageCaption": image_caption,
        "availability": "Disponibilité à confirmer",
    }


def build_store_catalog(conn: sqlite3.Connection) -> dict:
    products = []
    for row in conn.execute("SELECT data_json FROM products ORDER BY name COLLATE NOCASE, ref"):
        product = json.loads(row["data_json"])
        if product.get("active", True):
            products.append(public_product(product))
    categories = sorted({p["family"] for p in products if p.get("family")}, key=str.casefold)
    phone_digits = re.sub(r"\D", "", STORE_PHONE)
    return {
        "brand": "ELMANSOUR SUPPLIES & SERVICES",
        "phone": STORE_PHONE,
        "whatsapp": phone_digits,
        "currency": "FCFA",
        "taxMode": "HT",
        "categories": categories,
        "products": products,
        "orderPolicy": "Mode aperçu : les commandes de démonstration ne sont pas transmises à WooCommerce.",
        "fulfillmentPolicy": "Les commandes réelles et paiements sont traités par la boutique WooCommerce.",
    }


def woo_client() -> WooCommerceClient:
    global _WOO_CLIENT
    if _WOO_CLIENT is None:
        with _WOO_CLIENT_LOCK:
            if _WOO_CLIENT is None:
                _WOO_CLIENT = WooCommerceClient.from_environment()
    return _WOO_CLIENT


def storefront_home() -> dict:
    if STORE_BACKEND == "woocommerce":
        return woo_client().homepage(brand=STORE_BRAND, phone=STORE_PHONE, currency=STORE_CURRENCY)
    with connection() as conn:
        return build_local_home(conn, read_products, public_product, PUBLIC_FAMILY_LABELS,
                                brand=STORE_BRAND, phone=STORE_PHONE, currency=STORE_CURRENCY)


def storefront_products(query: dict[str, list[str]]) -> dict:
    filters = {key: (values[-1] if values else "") for key, values in query.items()}
    # The UI calls this field q; WooCommerce names its REST parameter search.
    filters["search"] = filters.pop("q", filters.get("search", ""))
    if STORE_BACKEND == "woocommerce":
        return woo_client().product_list(filters)
    with connection() as conn:
        return list_local_products(conn, read_products, public_product, PUBLIC_FAMILY_LABELS, filters)


def storefront_product(slug: str) -> dict | None:
    if STORE_BACKEND == "woocommerce":
        return woo_client().product_by_slug(slug)
    with connection() as conn:
        return find_local_product_by_slug(conn, read_products, public_product, PUBLIC_FAMILY_LABELS, slug)


def submit_store_order(body: dict) -> dict:
    if STORE_BACKEND == "woocommerce":
        raise ValueError("Les commandes WooCommerce doivent passer par le checkout natif.")
    with connection() as conn:
        order = build_store_order(conn, body)
        conn.execute("INSERT INTO web_orders(number,created_at,status,payload_json,sale_number) VALUES(?,?,?,?,NULL)",
                     (order["number"], order["createdAt"], order["status"], json.dumps(order, ensure_ascii=False)))
        conn.commit()
    return {"number": order["number"], "status": order["status"],
            "total": order["total"], "preview": True, "paymentUrl": None}


def submit_store_checkout(body: dict) -> dict:
    if STORE_BACKEND == "woocommerce":
        return woo_client().create_checkout_handoff(body)
    # The local SQLite preview has no WooCommerce checkout or real payment gateway.
    # Keep it available for catalogue/admin work without pretending to take payment.
    if not isinstance(body, dict) or not isinstance(body.get("items"), list) or not body["items"]:
        raise ValueError("Le panier est vide.")
    return {"preview": True, "checkoutAction": None, "checkoutToken": None}


def order_rate_limited(client_ip: str, *, limit: int = 12, window_seconds: int = 900) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    with _ORDER_ATTEMPTS_LOCK:
        attempts = _ORDER_ATTEMPTS[client_ip or "unknown"]
        while attempts and now - attempts[0] > window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            return True
        attempts.append(now)
        return False


def build_store_order(conn: sqlite3.Connection, body: dict) -> dict:
    if body.get("website"):
        raise ValueError("Demande invalide.")
    customer = body.get("customer")
    if not isinstance(customer, dict):
        raise ValueError("Renseignez votre nom et votre téléphone.")
    name = str(customer.get("name", "")).strip()
    phone = str(customer.get("phone", "")).strip()
    email = str(customer.get("email", "")).strip()
    if len(name) < 2 or len(name) > 120:
        raise ValueError("Le nom doit comporter entre 2 et 120 caractères.")
    normalized_phone = re.sub(r"[\s().-]", "", phone)
    digits = re.sub(r"\D", "", normalized_phone)
    if len(digits) < 7 or len(digits) > 15 or not re.fullmatch(r"\+?[0-9]+", normalized_phone):
        raise ValueError("Entrez un numéro de téléphone valide avec son indicatif si nécessaire.")
    if email and (len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        raise ValueError("L’adresse e-mail n’est pas valide.")
    fulfillment = body.get("fulfillment") or {}
    if not isinstance(fulfillment, dict):
        raise ValueError("Choisissez livraison ou retrait.")
    method = str(fulfillment.get("method", "")).strip()
    if method not in ("delivery", "pickup"):
        raise ValueError("Choisissez livraison ou retrait.")
    address = str(fulfillment.get("address", "")).strip()
    zone = str(fulfillment.get("zone", "")).strip()
    if method == "delivery" and not address:
        raise ValueError("Indiquez l’adresse souhaitée pour la livraison.")
    if len(address) > 500 or len(zone) > 120:
        raise ValueError("L’adresse ou la zone est trop longue.")
    note = str(body.get("note", "")).strip()
    if len(note) > 1500:
        raise ValueError("La note ne peut pas dépasser 1 500 caractères.")
    requested = body.get("items")
    if not isinstance(requested, list) or not requested or len(requested) > 30:
        raise ValueError("Le panier est vide ou contient trop d’articles (maximum 30 références).")
    quantities: dict[str, int] = {}
    for line in requested:
        if not isinstance(line, dict):
            raise ValueError("Une ligne de panier est invalide.")
        product_id = str(line.get("id", "")).strip()
        qty = optional_int(line.get("qty"), "Quantité")
        if not product_id or qty is None or qty < 1 or qty > 99:
            raise ValueError("Chaque quantité doit être comprise entre 1 et 99.")
        quantities[product_id] = quantities.get(product_id, 0) + qty
        if quantities[product_id] > 99:
            raise ValueError("Maximum 99 unités par référence.")
    items = []
    subtotal = 0
    for product_id, qty in quantities.items():
        product = get_product(conn, product_id)
        if not product or product.get("active", True) is False:
            raise ValueError("Un produit du panier n’est plus publié. Actualisez le catalogue et réessayez.")
        if product.get("sellPrice") in (None, ""):
            raise ValueError("Prix bientôt disponible. Ce produit ne peut pas être commandé pour le moment.")
        price = optional_int(product.get("sellPrice"), "Prix de vente")
        if price is None:
            raise ValueError("Prix bientôt disponible. Ce produit ne peut pas être commandé pour le moment.")
        if product.get("stock") is not None and int(product["stock"]) <= 0:
            raise ValueError("Un produit est en rupture de stock. Actualisez le catalogue et réessayez.")
        line_total = price * qty
        subtotal += line_total
        items.append({
            "id": product_id,
            "ref": str(product.get("ref") or ""),
            "name": str(product.get("name") or ""),
            "family": PUBLIC_FAMILY_LABELS.get(product.get("family"), product.get("family") or "Autres produits"),
            "pack": str(product.get("pack") or "Unité"),
            "qty": qty,
            "unitPrice": price,
            "lineTotal": line_total,
            "availability": "À confirmer",
        })
    created = now_iso()
    number = f"WEB-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    return {
        "number": number,
        "createdAt": created,
        "updatedAt": created,
        "status": "pending_confirmation",
        "type": "order",
        "customer": {"name": name, "phone": normalized_phone, "email": email or None},
        "fulfillment": {"method": method, "address": address, "zone": zone},
        "note": note,
        "items": items,
        "pricedSubtotal": subtotal,
        "total": subtotal,
        "payment": "Aperçu local — paiement WooCommerce non simulé",
        "saleNumber": None,
    }


def convert_web_order(conn: sqlite3.Connection, number: str, allow_negative: bool = False) -> dict:
    row = conn.execute("SELECT payload_json FROM web_orders WHERE number=?", (number,)).fetchone()
    if not row:
        raise ValueError("Commande web introuvable.")
    order = clean_local_order(json.loads(row["payload_json"]))
    if order.get("status") == "converted":
        raise ValueError("Cette commande a déjà été convertie en vente.")
    if order.get("status") == "cancelled":
        raise ValueError("Une commande annulée ne peut pas être convertie.")
    if not order.get("items"):
        raise ValueError("Cette commande ne contient aucun article.")
    sale_items = []
    products = []
    shortages = []
    for line in order["items"]:
        product = get_product(conn, str(line.get("id", "")))
        qty = optional_int(line.get("qty"), "Quantité")
        price = optional_int(line.get("unitPrice"), "Prix client")
        if not product or product.get("active", True) is False or qty is None or qty < 1 or price is None:
            raise ValueError("Un produit de la commande a changé ou n’est plus disponible.")
        if product.get("stock") is not None and int(product["stock"]) < qty:
            shortages.append(product["ref"])
        sale_items.append({
            "id": product["id"], "ref": line["ref"], "name": line["name"], "qty": qty,
            "unitPrice": price, "lineTotal": price * qty,
            "purchasePrice": product.get("purchasePrice"),
        })
        products.append((product, qty))
    if shortages and not allow_negative:
        return {"shortage": True, "references": shortages}
    total = sum(line["lineTotal"] for line in sale_items)
    sale = {
        "number": number,
        "date": now_iso(),
        "client": order.get("customer", {}).get("name") or "Commande boutique E.S.S.",
        "payment": "À confirmer avec E.S.S.",
        "discount": 0,
        "items": sale_items,
        "total": total,
        "webOrder": number,
    }
    conn.execute("INSERT INTO sales(number,date,payload_json) VALUES(?,?,?)",
                 (number, sale["date"], json.dumps(sale, ensure_ascii=False)))
    changed = []
    for product, qty in products:
        if product.get("stock") is not None:
            product["stock"] = int(product["stock"]) - qty
            save_product(conn, product)
            changed.append(product)
    order["status"] = "converted"
    order["updatedAt"] = now_iso()
    order["saleNumber"] = number
    conn.execute("UPDATE web_orders SET status=?,payload_json=?,sale_number=? WHERE number=?",
                 (order["status"], json.dumps(order, ensure_ascii=False), number, number))
    return {"order": order, "sale": sale, "products": changed}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_json(self, status: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def require_admin(self) -> bool:
        if not ADMIN_PASSWORD:
            return True
        expected = "Basic " + base64.b64encode(("ess:" + ADMIN_PASSWORD).encode("utf-8")).decode("ascii")
        supplied = self.headers.get("Authorization", "")
        if hmac.compare_digest(supplied, expected):
            return True
        self.send_json(401, {"error": "Accès gestion réservé à E.S.S.", "adminAuthRequired": True})
        return False

    def api_error(self, exc: Exception):
        if isinstance(exc, ValueError):
            self.send_json(400, {"error": str(exc)})
        elif isinstance(exc, WooCommerceError):
            self.send_json(502, {"error": str(exc)})
        elif isinstance(exc, sqlite3.IntegrityError):
            self.send_json(409, {"error": "Cette référence existe déjà. Choisissez-en une autre."})
        else:
            print("API error:", repr(exc), flush=True)
            message = ("Erreur lors de la lecture de la boutique WooCommerce. Réessayez dans quelques instants."
                       if STORE_BACKEND == "woocommerce" else
                       "Erreur de base de données locale. Réessayez ou exportez une sauvegarde.")
            self.send_json(500, {"error": message})

    def do_GET(self):
        parsed = urlsplit(self.path)
        public_routes = {"/", "/boutique", "/boutique/", "/catalogue", "/catalogue/",
                         "/a-propos", "/a-propos/", "/contact", "/contact/", "/faq", "/faq/",
                         "/livraison-retours", "/livraison-retours/", "/confidentialite", "/confidentialite/"}
        if parsed.path in public_routes or re.fullmatch(r"/produit/[^/]+/?", parsed.path):
            self.path = "/storefront/index.html"
            super().do_GET()
            return
        if parsed.path in ("/admin", "/admin/", "/admin/index.html"):
            if STORE_BACKEND == "woocommerce":
                site_url = os.environ.get("ESS_WC_SITE_URL", "").rstrip("/")
                if not site_url:
                    self.send_error(503, "WordPress n’est pas configuré.")
                    return
                self.send_response(302)
                self.send_header("Location", site_url + "/wp-admin/")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.path = "/index.html"
            super().do_GET()
            return
        if parsed.path == "/api/health":
            self.send_json(200, {"ok": True, "storeBackend": STORE_BACKEND})
            return
        if parsed.path == "/api/store/catalog":
            try:
                self.send_json(200, storefront_home())
            except Exception as exc:
                self.api_error(exc)
            return
        if parsed.path in ("/api/store/products", "/api/store/products/"):
            try:
                self.send_json(200, storefront_products(parse_qs(parsed.query, keep_blank_values=True)))
            except Exception as exc:
                self.api_error(exc)
            return
        if parsed.path.startswith("/api/store/products/"):
            slug = unquote(parsed.path[len("/api/store/products/"):]).strip("/")
            if not slug or "/" in slug:
                self.send_json(404, {"error": "Produit introuvable."})
                return
            try:
                product = storefront_product(slug)
                if not product:
                    self.send_json(404, {"error": "Produit introuvable ou retiré du catalogue."})
                else:
                    self.send_json(200, product)
            except Exception as exc:
                self.api_error(exc)
            return
        if STORE_BACKEND == "woocommerce" and parsed.path.startswith("/api/"):
            self.send_json(404, {"error": "En mode WooCommerce, la gestion des produits et commandes se fait dans WordPress."})
            return
        if parsed.path.startswith("/api/") and not self.require_admin():
            return
        if parsed.path == "/api/state":
            include_images = parse_qs(parsed.query).get("includeImages", [""])[0] == "1"
            try:
                with connection() as conn:
                    self.send_json(200, read_state(conn, include_images=include_images))
            except Exception as exc:
                self.api_error(exc)
            return
        if parsed.path.startswith("/api/"):
            self.send_json(404, {"error": "Route API inconnue."})
            return
        decoded = unquote(parsed.path)
        normalized = "/" + "/".join(part for part in decoded.split("/") if part not in ("", "."))
        if normalized == "/data" or normalized.startswith("/data/") or normalized.endswith((".db", ".sqlite", ".sqlite3", ".py", ".pyc", "-wal", "-shm")) or any(part.startswith(".") for part in decoded.split("/")):
            self.send_error(404)
            return
        static_path = (ROOT / normalized.lstrip("/")).resolve()
        try:
            static_path.relative_to(ROOT.resolve())
        except ValueError:
            self.send_error(404)
            return
        try:
            static_path.relative_to(DATA.resolve())
        except ValueError:
            pass
        else:
            self.send_error(404)
            return
        if PUBLIC_MODE:
            if not (normalized == "/index.html" or normalized.startswith("/assets/") or normalized.startswith("/storefront/")):
                self.send_error(404)
                return
            allowed_root = (ROOT / "storefront").resolve() if normalized.startswith("/storefront/") else ASSETS.resolve() if normalized.startswith("/assets/") else ROOT.resolve()
            try:
                static_path.relative_to(allowed_root)
            except ValueError:
                self.send_error(404)
                return
            if not static_path.is_file():
                self.send_error(404)
                return
        super().do_GET()

    def do_POST(self):
        parsed = urlsplit(self.path)
        try:
            if parsed.path == "/api/store/checkout":
                if order_rate_limited(self.client_address[0]):
                    self.send_json(429, {"error": "Trop de tentatives de commande depuis cette connexion. Réessayez plus tard."})
                    return
                body = parse_json_body(self, max_bytes=MAX_STORE_ORDER_BODY)
                checkout = submit_store_checkout(body)
                self.send_json(200, checkout)
                return
            if parsed.path == "/api/store/orders":
                if STORE_BACKEND == "woocommerce":
                    self.send_json(410, {"error": "Utilisez le checkout WooCommerce de la vitrine pour valider votre panier."})
                    return
                if order_rate_limited(self.client_address[0]):
                    self.send_json(429, {"error": "Trop de tentatives de commande depuis cette connexion. Réessayez plus tard."})
                    return
                body = parse_json_body(self, max_bytes=MAX_STORE_ORDER_BODY)
                order = submit_store_order(body)
                self.send_json(201, order)
                return
            if STORE_BACKEND == "woocommerce" and parsed.path.startswith("/api/"):
                self.send_json(404, {"error": "En mode WooCommerce, la gestion se fait dans WordPress."})
                return
            if parsed.path.startswith("/api/") and not self.require_admin():
                return
            body = parse_json_body(self)
            if parsed.path.startswith("/api/orders/") and parsed.path.endswith("/convert"):
                number = unquote(parsed.path.split("/", 3)[3].rsplit("/", 1)[0])
                with connection() as conn:
                    result = convert_web_order(conn, number, bool(body.get("allowNegative")))
                    if result.get("shortage"):
                        self.send_json(409, {"error": "Stock inférieur aux quantités commandées : " + ", ".join(result["references"]), "shortage": True})
                        return
                    conn.commit()
                    self.send_json(200, result)
                return
            if parsed.path == "/api/migrate-local":
                with connection() as conn:
                    migrated = migrate_legacy(conn, body)
                    conn.commit()
                    self.send_json(200, {"migrated": migrated})
                return
            if parsed.path == "/api/products":
                name = str(body.get("name", "")).strip()
                family = str(body.get("family", "")).strip()
                if not name or not family:
                    raise ValueError("Le nom et la famille sont obligatoires.")
                photo_data = body.get("photoData")
                with connection() as conn:
                    ref = str(body.get("ref", "")).strip() or next_ref(conn)
                    product = {
                        "id": "LOCAL-" + uuid.uuid4().hex[:12].upper(),
                        "ref": ref,
                        "family": family,
                        "name": name,
                        "pack": str(body.get("pack", "")).strip() or "Unité",
                        "catalogPrice": optional_int(body.get("catalogPrice"), "Prix catalogue"),
                        "sellPrice": optional_int(body.get("sellPrice"), "Prix client"),
                        "source": "local",
                        "purchasePrice": optional_int(body.get("purchasePrice"), "Prix d'achat"),
                        "purchaseAlt": None,
                        "supplierRef": str(body.get("supplierRef", "")).strip() or None,
                        "supplierNote": str(body.get("supplierNote", "")).strip() or None,
                        "stock": optional_int(body.get("stock"), "Stock", allow_negative=True),
                        "photo": None,
                        "photoKind": "placeholder",
                        "brand": str(body.get("brand", "")).strip() or None,
                        "declaredType": str(body.get("declaredType", "")).strip() or None,
                        "active": True,
                        "userNote": str(body.get("userNote", "")).strip(),
                        "createdAt": now_iso(),
                    }
                    if photo_data:
                        product["photoData"] = photo_data
                        prepare_product_photo(product)
                    insert_product(conn, product)
                    conn.commit()
                    self.send_json(201, {"product": product, "state": read_state(conn)})
                return
            if parsed.path.startswith("/api/sales"):
                sale = body.get("sale") if isinstance(body.get("sale"), dict) else body
                number = str(sale.get("number", "")).strip()
                lines = sale.get("items")
                if not number or not isinstance(lines, list) or not lines:
                    raise ValueError("La vente doit contenir au moins un article.")
                with connection() as conn:
                    changed = []
                    for line in lines:
                        if not isinstance(line, dict):
                            raise ValueError("Une ligne de vente est invalide.")
                        product_id = str(line.get("id", ""))
                        product = get_product(conn, product_id)
                        qty = optional_int(line.get("qty"), "Quantité")
                        price = optional_int(line.get("unitPrice"), "Prix unitaire")
                        if not product or product.get("active", True) is False or qty is None or qty < 1 or price is None:
                            raise ValueError("Une ligne de vente contient un produit, une quantité ou un prix invalide.")
                        if product.get("stock") is not None:
                            product["stock"] = int(product["stock"]) - qty
                            save_product(conn, product)
                            changed.append(product)
                    conn.execute("INSERT INTO sales(number,date,payload_json) VALUES(?,?,?)",
                                 (number, str(sale.get("date") or now_iso()), json.dumps(sale, ensure_ascii=False)))
                    conn.commit()
                    self.send_json(201, {"sale": sale, "products": changed})
                return
            if parsed.path == "/api/receipts":
                product_id = str(body.get("productId", ""))
                qty = optional_int(body.get("qty"), "Quantité")
                unit_cost = optional_int(body.get("unitCost"), "Coût d'achat")
                if not product_id or qty is None or qty < 1 or unit_cost is None:
                    raise ValueError("Produit, quantité et coût d’achat sont obligatoires.")
                with connection() as conn:
                    product = get_product(conn, product_id)
                    if not product:
                        raise ValueError("Produit introuvable.")
                    product["stock"] = int(product["stock"] or 0) + qty
                    product["purchasePrice"] = unit_cost
                    save_product(conn, product)
                    receipt = {
                        "date": now_iso(), "id": product_id, "ref": product["ref"], "name": product["name"],
                        "qty": qty, "unitCost": unit_cost,
                        "supplier": str(body.get("supplier", "")).strip(),
                        "invoice": str(body.get("invoice", "")).strip(),
                    }
                    conn.execute("INSERT INTO receipts(date,payload_json) VALUES(?,?)",
                                 (receipt["date"], json.dumps(receipt, ensure_ascii=False)))
                    conn.commit()
                    self.send_json(201, {"receipt": receipt, "product": product})
                return
            if parsed.path == "/api/restore":
                with connection() as conn:
                    restore_state(conn, body)
                    conn.commit()
                    self.send_json(200, {"ok": True, "state": read_state(conn)})
                return
            self.send_json(404, {"error": "Route API inconnue."})
        except Exception as exc:
            self.api_error(exc)

    def do_PUT(self):
        parsed = urlsplit(self.path)
        if STORE_BACKEND == "woocommerce" and parsed.path.startswith("/api/"):
            self.send_json(404, {"error": "En mode WooCommerce, la gestion se fait dans WordPress."})
            return
        if parsed.path.startswith("/api/") and not self.require_admin():
            return
        if parsed.path.startswith("/api/orders/") and parsed.path.endswith("/status"):
            try:
                body = parse_json_body(self)
                number = unquote(parsed.path.split("/", 3)[3].rsplit("/", 1)[0])
                status = str(body.get("status", "")).strip()
                if status not in {"contacted", "cancelled"}:
                    raise ValueError("Statut de commande non autorisé.")
                with connection() as conn:
                    row = conn.execute("SELECT payload_json FROM web_orders WHERE number=?", (number,)).fetchone()
                    if not row:
                        self.send_json(404, {"error": "Commande web introuvable."})
                        return
                    order = clean_local_order(json.loads(row["payload_json"]))
                    if order.get("status") in {"converted", "cancelled"}:
                        raise ValueError("Cette commande ne peut plus changer de statut.")
                    order["status"] = status
                    order["updatedAt"] = now_iso()
                    conn.execute("UPDATE web_orders SET status=?,payload_json=? WHERE number=?",
                                 (status, json.dumps(order, ensure_ascii=False), number))
                    conn.commit()
                    self.send_json(200, {"order": order})
                return
            except Exception as exc:
                self.api_error(exc)
            return
        if not parsed.path.startswith("/api/products/"):
            self.send_json(404, {"error": "Route API inconnue."})
            return
        product_id = unquote(parsed.path.rsplit("/", 1)[-1])
        try:
            body = parse_json_body(self)
            updates = body.get("updates") if isinstance(body.get("updates"), dict) else body
            photo_data = updates.pop("photoData", None)
            with connection() as conn:
                product = get_product(conn, product_id)
                if not product:
                    self.send_json(404, {"error": "Produit introuvable."})
                    return
                fields = {"name", "family", "pack", "brand", "catalogPrice", "sellPrice", "purchasePrice",
                          "stock", "supplierRef", "supplierNote", "declaredType", "userNote", "active"}
                for key in fields:
                    if key in updates:
                        if key in ("catalogPrice", "sellPrice", "purchasePrice"):
                            product[key] = optional_int(updates[key], key)
                        elif key == "stock":
                            product[key] = optional_int(updates[key], key, allow_negative=True)
                        elif key == "active":
                            product[key] = bool(updates[key])
                        else:
                            value = updates[key]
                            product[key] = str(value).strip() if value is not None else None
                if not product.get("name") or not product.get("family"):
                    raise ValueError("Le nom et la famille sont obligatoires.")
                if photo_data:
                    product["photoData"] = photo_data
                    prepare_product_photo(product)
                product["updatedAt"] = now_iso()
                save_product(conn, product)
                conn.commit()
                self.send_json(200, {"product": product})
        except Exception as exc:
            self.api_error(exc)

    def do_DELETE(self):
        parsed = urlsplit(self.path)
        if STORE_BACKEND == "woocommerce" and parsed.path.startswith("/api/"):
            self.send_json(404, {"error": "En mode WooCommerce, la gestion se fait dans WordPress."})
            return
        if parsed.path.startswith("/api/") and not self.require_admin():
            return
        if not parsed.path.startswith("/api/products/"):
            self.send_json(404, {"error": "Route API inconnue."})
            return
        product_id = unquote(parsed.path.rsplit("/", 1)[-1])
        try:
            with connection() as conn:
                product = get_product(conn, product_id)
                if not product:
                    self.send_json(404, {"error": "Produit introuvable."})
                    return
                product["active"] = False
                save_product(conn, product)
                conn.commit()
                self.send_json(200, {"product": product})
        except Exception as exc:
            self.api_error(exc)

    def log_message(self, fmt, *args):
        super().log_message(fmt, *args)


if __name__ == "__main__":
    if STORE_BACKEND not in {"local", "woocommerce"}:
        raise SystemExit("ESS_STORE_BACKEND doit valoir 'local' ou 'woocommerce'.")
    if PUBLIC_MODE and STORE_BACKEND == "local" and not ADMIN_PASSWORD:
        raise SystemExit("En mode public local, ESS_ADMIN_PASSWORD est requis pour protéger les API de gestion.")
    if STORE_BACKEND == "woocommerce":
        try:
            _WOO_CLIENT = WooCommerceClient.from_environment()
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
        print("E.S.S. storefront ready; product/order source=WordPress WooCommerce REST API v3", flush=True)
    else:
        init_db()
        if PUBLIC_MODE:
            print("WARNING: local SQLite mode is for preview/legacy use; configure ESS_STORE_BACKEND=woocommerce before public production.", flush=True)
        print(f"E.S.S. local preview listening on 0.0.0.0:{PORT}; database={DB_PATH}", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
