#!/usr/bin/env python3
"""Kostenloser E-Mail-Verfügbarkeitsmonitor.

Der Bot überwacht einzelne Produktseiten (Midea PortaSplit) sowie komplette
Sortimentsseiten (Knuffelwuff). Er sendet E-Mails bei einem Wechsel auf
"verfügbar" und bei Knuffelwuff zusätzlich, wenn ein neuer lieferbarer Artikel
im Sortiment erscheint.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import smtplib
import ssl
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


def load_env_file(path: Path = Path(".env")) -> None:
    """Load a small .env file without an additional dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


load_env_file()

LOG = logging.getLogger("stock-bot")
DEFAULT_CONFIG = Path(os.getenv("BOT_CONFIG", "config.toml"))
DEFAULT_STATE = Path(os.getenv("BOT_STATE", "state.json"))


@dataclass(frozen=True)
class Product:
    name: str
    retailer: str
    url: str
    enabled: bool = True
    available_phrases: tuple[str, ...] = ()
    unavailable_phrases: tuple[str, ...] = ()
    buy_selectors: tuple[str, ...] = ()
    availability_selectors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Catalog:
    name: str
    retailer: str
    urls: tuple[str, ...]
    enabled: bool = True
    max_pages_per_category: int = 5
    available_phrases: tuple[str, ...] = ()
    unavailable_phrases: tuple[str, ...] = ()


@dataclass
class CheckResult:
    key: str
    name: str
    retailer: str
    url: str
    available: bool | None
    reason: str
    checked_at: str
    page_title: str = ""
    price: str | None = None


@dataclass
class CatalogItem:
    key: str
    name: str
    url: str
    available: bool | None
    price: str | None = None
    new_badge: bool = False
    source_url: str = ""


@dataclass
class CatalogCheck:
    catalog: Catalog
    items: dict[str, CatalogItem]
    pages_checked: int
    checked_at: str
    errors: list[str]


@dataclass
class CatalogEvent:
    kind: str  # "new" or "restocked"
    item: CatalogItem


GENERIC_AVAILABLE = (
    "auf lager",
    "online verfügbar",
    "lieferbar",
    "sofort lieferbar",
    "sofort verfügbar",
    "in stock",
    "add to cart",
    "in den warenkorb",
)
GENERIC_UNAVAILABLE = (
    "online nicht verfügbar",
    "derzeit nicht verfügbar",
    "momentan nicht verfügbar",
    "nicht verfügbar",
    "nicht lieferbar",
    "ausverkauft",
    "sold out",
    "currently unavailable",
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_text(value)).strip("-")


def product_key(product: Product) -> str:
    host = urlparse(product.url).netloc.removeprefix("www.")
    return f"{host}:{slugify(product.name)}"


def catalog_key(catalog: Catalog) -> str:
    host = urlparse(catalog.urls[0]).netloc.removeprefix("www.") if catalog.urls else "catalog"
    return f"{host}:catalog:{slugify(catalog.name)}"


def canonical_product_url(value: str, base_url: str = "") -> str:
    absolute = urljoin(base_url, value)
    parts = urlsplit(absolute)
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def catalog_item_key(url: str) -> str:
    canonical = canonical_product_url(url)
    parts = urlsplit(canonical)
    return f"{parts.netloc.removeprefix('www.').casefold()}:{parts.path.casefold()}"


def load_config(path: Path) -> tuple[dict[str, Any], list[Product], list[Catalog]]:
    with path.open("rb") as handle:
        raw = tomllib.load(handle)

    products: list[Product] = []
    for item in raw.get("products", []):
        products.append(
            Product(
                name=item["name"],
                retailer=item["retailer"],
                url=item["url"],
                enabled=item.get("enabled", True),
                available_phrases=tuple(item.get("available_phrases", [])),
                unavailable_phrases=tuple(item.get("unavailable_phrases", [])),
                buy_selectors=tuple(item.get("buy_selectors", [])),
                availability_selectors=tuple(item.get("availability_selectors", [])),
            )
        )

    catalogs: list[Catalog] = []
    for item in raw.get("catalogs", []):
        catalogs.append(
            Catalog(
                name=item["name"],
                retailer=item["retailer"],
                urls=tuple(item.get("urls", [])),
                enabled=item.get("enabled", True),
                max_pages_per_category=max(1, int(item.get("max_pages_per_category", 5))),
                available_phrases=tuple(item.get("available_phrases", [])),
                unavailable_phrases=tuple(item.get("unavailable_phrases", [])),
            )
        )
    return raw, products, catalogs


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"products": {}, "catalogs": {}}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError("State root is not an object")
        state.setdefault("products", {})
        state.setdefault("catalogs", {})
        return state
    except (json.JSONDecodeError, OSError, ValueError):
        LOG.warning("State file could not be read; starting with empty state")
        return {"products": {}, "catalogs": {}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def availability_from_value(value: Any) -> bool | None:
    normalized = normalize_text(str(value)).replace("-", "")
    if any(token in normalized for token in ("outofstock", "soldout", "discontinued")):
        return False
    if any(token in normalized for token in ("instock", "limitedavailability", "preorder", "onlineonly")):
        return True
    return None


def structured_availability(json_ld_blocks: Iterable[str]) -> tuple[bool | None, str | None, str | None]:
    """Return availability, reason and price from schema.org JSON-LD."""
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in walk_json(data):
            availability = node.get("availability")
            status = availability_from_value(availability)
            price = node.get("price") or node.get("lowPrice")
            currency = node.get("priceCurrency")
            price_label = f"{price} {currency}" if price and currency else (str(price) if price else None)
            if status is not None:
                return status, f"Strukturierte Produktdaten melden {availability}", price_label
    return None, None, None


def _schema_type_is_product(value: Any) -> bool:
    if isinstance(value, list):
        return any(_schema_type_is_product(entry) for entry in value)
    return normalize_text(str(value)).endswith("product")


def structured_catalog_items(json_ld_blocks: Iterable[str], base_url: str) -> dict[str, CatalogItem]:
    """Extract catalog products from schema.org JSON-LD blocks."""
    items: dict[str, CatalogItem] = {}
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in walk_json(data):
            if not _schema_type_is_product(node.get("@type", "")):
                continue
            name = str(node.get("name", "")).strip()
            offers = node.get("offers")
            offer_nodes = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
            url = str(node.get("url", "") or "")
            status: bool | None = availability_from_value(node.get("availability"))
            price: str | None = None
            for offer in offer_nodes:
                url = url or str(offer.get("url", "") or "")
                offer_status = availability_from_value(offer.get("availability"))
                if offer_status is not None:
                    status = offer_status
                raw_price = offer.get("price") or offer.get("lowPrice")
                currency = offer.get("priceCurrency")
                if raw_price is not None:
                    price = f"{raw_price} {currency}" if currency else str(raw_price)
                    break
            if not name or not url:
                continue
            canonical = canonical_product_url(url, base_url)
            if urlsplit(canonical).netloc != urlsplit(base_url).netloc:
                continue
            key = catalog_item_key(canonical)
            items[key] = CatalogItem(
                key=key,
                name=name,
                url=canonical,
                available=status,
                price=price,
                source_url=base_url,
            )
    return items


def classify_availability(
    text: str,
    *,
    available_phrases: Iterable[str] = (),
    unavailable_phrases: Iterable[str] = (),
    buy_button_found: bool = False,
) -> tuple[bool | None, str]:
    normalized = normalize_text(text)
    negatives = tuple(unavailable_phrases) + GENERIC_UNAVAILABLE
    positives = tuple(available_phrases) + GENERIC_AVAILABLE

    for phrase in negatives:
        if normalize_text(phrase) in normalized:
            return False, f'Statushinweis gefunden: "{phrase}"'

    if buy_button_found:
        return True, "Aktiver Kaufen-/Warenkorb-Button gefunden"

    for phrase in positives:
        if normalize_text(phrase) in normalized:
            return True, f'Verfügbarkeitshinweis gefunden: "{phrase}"'

    return None, "Kein eindeutiger Verfügbarkeitsstatus erkannt"


def selector_is_actionable(page: Page, selector: str) -> bool:
    locator = page.locator(selector).first
    try:
        if locator.count() == 0 or not locator.is_visible(timeout=800):
            return False
        if not locator.is_enabled(timeout=800):
            return False
        aria_disabled = locator.get_attribute("aria-disabled")
        disabled = locator.get_attribute("disabled")
        return aria_disabled != "true" and disabled is None
    except Exception:
        return False


def new_browser_context(browser: Browser):
    return browser.new_context(
        locale="de-DE",
        timezone_id="Europe/Berlin",
        viewport={"width": 1440, "height": 1100},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    )


def check_product(browser: Browser, product: Product, timeout_ms: int) -> CheckResult:
    checked_at = datetime.now(timezone.utc).isoformat()
    context = new_browser_context(browser)
    page = context.new_page()
    page.set_default_timeout(timeout_ms)

    try:
        response = page.goto(product.url, wait_until="domcontentloaded", timeout=timeout_ms)
        if response and response.status >= 400:
            return CheckResult(
                key=product_key(product), name=product.name, retailer=product.retailer,
                url=product.url, available=None,
                reason=f"Shop antwortete mit HTTP {response.status}", checked_at=checked_at,
            )

        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
        except PlaywrightTimeoutError:
            pass

        title = page.title()
        json_ld = page.locator('script[type="application/ld+json"]').all_text_contents()
        structured, structured_reason, price = structured_availability(json_ld)

        relevant_texts: list[str] = []
        for selector in product.availability_selectors:
            try:
                locator = page.locator(selector)
                if locator.count():
                    relevant_texts.extend(locator.all_inner_texts())
            except Exception:
                continue
        if not relevant_texts:
            relevant_texts.append(page.locator("body").inner_text(timeout=timeout_ms))

        buy_button_found = any(selector_is_actionable(page, selector) for selector in product.buy_selectors)
        text_status, text_reason = classify_availability(
            "\n".join(relevant_texts),
            available_phrases=product.available_phrases,
            unavailable_phrases=product.unavailable_phrases,
            buy_button_found=buy_button_found,
        )

        if text_status is False:
            available, reason = False, text_reason
        elif structured is not None:
            available, reason = structured, structured_reason or "Strukturierte Produktdaten ausgewertet"
        else:
            available, reason = text_status, text_reason

        return CheckResult(
            key=product_key(product), name=product.name, retailer=product.retailer,
            url=product.url, available=available, reason=reason,
            checked_at=checked_at, page_title=title, price=price,
        )
    except PlaywrightTimeoutError:
        return CheckResult(
            key=product_key(product), name=product.name, retailer=product.retailer,
            url=product.url, available=None, reason="Zeitüberschreitung beim Laden der Seite",
            checked_at=checked_at,
        )
    except Exception as exc:
        LOG.exception("Check failed for %s", product.url)
        return CheckResult(
            key=product_key(product), name=product.name, retailer=product.retailer,
            url=product.url, available=None, reason=f"Prüffehler: {type(exc).__name__}: {exc}",
            checked_at=checked_at,
        )
    finally:
        context.close()


def with_page_size(url: str, page_size: int = 50) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["af"] = str(page_size)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _dom_catalog_items(page: Page, catalog: Catalog, source_url: str) -> dict[str, CatalogItem]:
    raw_items = page.evaluate(
        """
        ({positivePhrases, negativePhrases, baseUrl, expectedHost}) => {
          const norm = value => (value || '').replace(/\\s+/g, ' ').trim();
          const lower = value => norm(value).toLocaleLowerCase('de-DE');
          const selectors = [
            "[itemtype*='Product']",
            ".productbox",
            "[class*='productbox']",
            ".product-wrapper",
            ".product-cell",
            "[data-product-id]",
            "[data-productid]"
          ];
          const cards = [];
          const seenCards = new Set();
          for (const selector of selectors) {
            for (const element of document.querySelectorAll(selector)) {
              if (!seenCards.has(element)) {
                seenCards.add(element);
                cards.push(element);
              }
            }
          }
          const output = [];
          for (const card of cards) {
            const cardText = norm(card.innerText || card.textContent || '');
            const cardLower = lower(cardText);
            if (!cardText || (!cardText.includes('€') && !/verfügbar|lieferbar|ausverkauft|auf lager/i.test(cardText))) {
              continue;
            }
            const links = [...card.querySelectorAll('a[href]')];
            let link = links.find(a =>
              a.matches('[itemprop="url"], .productbox-title, [class*="productbox-title"], h2 a, h3 a, h4 a') &&
              norm(a.textContent || a.getAttribute('title') || '').length >= 8
            );
            if (!link) {
              link = links.find(a => lower(a.textContent || a.getAttribute('title') || '').includes('knuffelwuff'));
            }
            if (!link) {
              link = links.find(a => norm(a.textContent || a.getAttribute('title') || '').length >= 12);
            }
            if (!link) continue;

            let name = norm(
              card.querySelector('[itemprop="name"]')?.textContent ||
              card.querySelector('.productbox-title, [class*="productbox-title"], h2, h3, h4')?.textContent ||
              link.getAttribute('title') || link.getAttribute('aria-label') || link.textContent
            );
            if (!name || name.length < 8) {
              name = norm(card.querySelector('img[alt]')?.getAttribute('alt') || '');
            }
            if (!name || name.length < 8 || name.length > 350) continue;

            let url;
            try { url = new URL(link.getAttribute('href'), baseUrl); } catch { continue; }
            if (url.host.toLocaleLowerCase('de-DE') !== expectedHost) continue;
            if (/\\.(jpg|jpeg|png|webp|gif|svg)$/i.test(url.pathname)) continue;

            const negative = negativePhrases.some(p => cardLower.includes(lower(p)));
            const positive = positivePhrases.some(p => cardLower.includes(lower(p)));
            const available = negative ? false : positive ? true : null;
            const priceMatch = cardText.match(/(?:ab\\s*)?\\d{1,4}(?:[.,]\\d{2})?\\s*€/i);
            const newBadge = /(^|\\s)neu(\\s|$)/i.test(cardText);
            output.push({name, url: url.href, available, price: priceMatch ? priceMatch[0] : null, newBadge});
          }
          return output;
        }
        """,
        {
            "positivePhrases": list(catalog.available_phrases or GENERIC_AVAILABLE),
            "negativePhrases": list(catalog.unavailable_phrases or GENERIC_UNAVAILABLE),
            "baseUrl": source_url,
            "expectedHost": urlsplit(source_url).netloc.casefold(),
        },
    )

    items: dict[str, CatalogItem] = {}
    expected_host = urlsplit(source_url).netloc.casefold()
    category_paths = {
        "/", "/schlafplatz", "/reise-transport", "/hundefutter", "/bekleidung",
        "/leinen-halsbaender", "/spielzeug", "/outlet", "/sitemap",
    }
    for raw in raw_items:
        canonical = canonical_product_url(str(raw.get("url", "")), source_url)
        parts = urlsplit(canonical)
        if parts.netloc.casefold() != expected_host or parts.path.casefold() in category_paths:
            continue
        name = re.sub(r"\s+", " ", str(raw.get("name", ""))).strip()
        if not name:
            continue
        key = catalog_item_key(canonical)
        items[key] = CatalogItem(
            key=key,
            name=name,
            url=canonical,
            available=raw.get("available") if raw.get("available") in {True, False} else None,
            price=str(raw.get("price")) if raw.get("price") else None,
            new_badge=bool(raw.get("newBadge")),
            source_url=source_url,
        )
    return items


def _merge_catalog_item(existing: CatalogItem | None, incoming: CatalogItem) -> CatalogItem:
    if existing is None:
        return incoming
    statuses = {existing.available, incoming.available}
    if True in statuses:
        available: bool | None = True
    elif False in statuses:
        available = False
    else:
        available = None
    return CatalogItem(
        key=incoming.key,
        name=incoming.name if len(incoming.name) >= len(existing.name) else existing.name,
        url=incoming.url or existing.url,
        available=available,
        price=incoming.price or existing.price,
        new_badge=existing.new_badge or incoming.new_badge,
        source_url=incoming.source_url or existing.source_url,
    )


def _pagination_links(page: Page, category_url: str, max_pages: int) -> list[str]:
    base = urlsplit(category_url)
    base_path = re.sub(r"_s\d+$", "", base.path.rstrip("/"))
    hrefs = page.locator("a[href]").evaluate_all(
        "els => els.map(a => a.href).filter(Boolean)"
    )
    links: set[str] = set()
    for href in hrefs:
        parts = urlsplit(str(href))
        if parts.netloc.casefold() != base.netloc.casefold():
            continue
        match = re.fullmatch(re.escape(base_path) + r"_s(\d+)", parts.path.rstrip("/"), flags=re.IGNORECASE)
        if not match:
            continue
        page_number = int(match.group(1))
        if 2 <= page_number <= max_pages:
            links.add(with_page_size(urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))))
    return sorted(links)


def check_catalog(
    browser: Browser,
    catalog: Catalog,
    timeout_ms: int,
    seconds_between_pages: float = 1.0,
) -> CatalogCheck:
    checked_at = datetime.now(timezone.utc).isoformat()
    context = new_browser_context(browser)
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    items: dict[str, CatalogItem] = {}
    errors: list[str] = []
    pages_checked = 0

    try:
        for category_url in catalog.urls:
            queue = [with_page_size(category_url)]
            visited: set[str] = set()
            while queue and len(visited) < catalog.max_pages_per_category:
                target = queue.pop(0)
                canonical_target = canonical_product_url(target)
                if canonical_target in visited:
                    continue
                visited.add(canonical_target)
                try:
                    response = page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
                    if response and response.status >= 400:
                        errors.append(f"{target}: HTTP {response.status}")
                        continue
                    try:
                        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 8_000))
                    except PlaywrightTimeoutError:
                        pass

                    pages_checked += 1
                    json_ld = page.locator('script[type="application/ld+json"]').all_text_contents()
                    page_items = structured_catalog_items(json_ld, target)
                    for key, item in _dom_catalog_items(page, catalog, target).items():
                        page_items[key] = _merge_catalog_item(page_items.get(key), item)
                    for key, item in page_items.items():
                        items[key] = _merge_catalog_item(items.get(key), item)

                    for link in _pagination_links(page, category_url, catalog.max_pages_per_category):
                        link_key = canonical_product_url(link)
                        if link_key not in visited and link not in queue:
                            queue.append(link)
                except PlaywrightTimeoutError:
                    errors.append(f"{target}: Zeitüberschreitung")
                except Exception as exc:
                    LOG.exception("Catalog page failed: %s", target)
                    errors.append(f"{target}: {type(exc).__name__}: {exc}")
                if queue and seconds_between_pages > 0:
                    time.sleep(seconds_between_pages)
    finally:
        context.close()

    return CatalogCheck(
        catalog=catalog,
        items=items,
        pages_checked=pages_checked,
        checked_at=checked_at,
        errors=errors,
    )


def compare_catalog_items(
    current: dict[str, CatalogItem],
    old_items: dict[str, Any],
    *,
    initialized: bool,
) -> list[CatalogEvent]:
    """Return only new available products and unavailable->available changes."""
    if not initialized:
        return []
    events: list[CatalogEvent] = []
    for key, item in current.items():
        if item.available is not True:
            continue
        old = old_items.get(key)
        if old is None:
            events.append(CatalogEvent(kind="new", item=item))
        elif old.get("available") is not True:
            events.append(CatalogEvent(kind="restocked", item=item))
    return sorted(events, key=lambda event: (event.kind, normalize_text(event.item.name)))


def update_catalog_state(old_record: dict[str, Any], check: CatalogCheck) -> dict[str, Any]:
    old_items = old_record.get("items", {}) if isinstance(old_record.get("items", {}), dict) else {}
    updated_items: dict[str, Any] = dict(old_items)
    now = check.checked_at

    # A clean scan may mark disappeared products as unavailable. On partial errors,
    # old availability is preserved to avoid false restock notifications.
    if not check.errors:
        for key, old in list(updated_items.items()):
            if key not in check.items and isinstance(old, dict):
                missing = dict(old)
                missing["available"] = False
                missing["last_missing_at"] = now
                updated_items[key] = missing

    for key, item in check.items.items():
        record = asdict(item)
        record["last_seen_at"] = now
        updated_items[key] = record

    return {
        "initialized": True,
        "last_checked_at": now,
        "pages_checked": check.pages_checked,
        "last_errors": check.errors,
        "items": updated_items,
    }


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().casefold() in {"1", "true", "yes", "ja", "on"}


def send_email(subject: str, body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("EMAIL_FROM", username)
    recipient = os.environ["EMAIL_TO"]
    use_ssl = env_bool("SMTP_SSL", port == 465)

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            if env_bool("SMTP_STARTTLS", True):
                smtp.starttls(context=context)
                smtp.ehlo()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)


def notify(result: CheckResult, *, test: bool = False) -> None:
    status = "TEST" if test else "WIEDER VERFÜGBAR"
    subject = f"Midea PortaSplit: {status} bei {result.retailer}"
    price_line = f"Preis laut Produktdaten: {result.price}\n" if result.price else ""
    body = (
        f"{result.name} ist bei {result.retailer} verfügbar.\n"
        f"{price_line}"
        f"Erkennung: {result.reason}\n"
        f"Geprüft: {result.checked_at}\n\n"
        f"Direkt zum Produkt:\n{result.url}\n"
    )
    try:
        send_email(subject, body)
        LOG.info("Email sent for %s", result.key)
    except Exception as exc:
        LOG.exception("Email notification failed")
        raise RuntimeError(f"E-Mail konnte nicht gesendet werden: {exc}") from exc


def notify_catalog_changes(check: CatalogCheck, events: list[CatalogEvent], *, test: bool = False) -> None:
    if test:
        subject = "Knuffelwuff-Bot: TESTNACHRICHT"
    elif len(events) == 1:
        label = "NEU UND LIEFERBAR" if events[0].kind == "new" else "WIEDER LIEFERBAR"
        subject = f"Knuffelwuff: {label} – {events[0].item.name[:80]}"
    else:
        subject = f"Knuffelwuff: {len(events)} neue Verfügbarkeitsänderungen"

    headline = (
        "Der Knuffelwuff-Bot hat folgende Änderung erkannt:"
        if len(events) == 1
        else "Der Knuffelwuff-Bot hat folgende Änderungen erkannt:"
    )
    lines = [headline, ""]

    for event in events:
        label = "NEU UND LIEFERBAR" if event.kind == "new" else "WIEDER LIEFERBAR"
        lines.extend([
            f"[{label}] {event.item.name}",
            f"Preis: {event.item.price}" if event.item.price else "Preis: nicht eindeutig erkannt",
            event.item.url,
            "",
        ])
    lines.extend([
        f"Geprüft: {check.checked_at}",
        f"Ausgewertete Sortimentsseiten: {check.pages_checked}",
    ])
    if check.errors:
        lines.append(f"Hinweis: {len(check.errors)} Seite(n) konnten nicht vollständig geprüft werden.")

    try:
        send_email(subject, "\n".join(lines).strip() + "\n")
        LOG.info("Catalog email sent with %s event(s)", len(events))
    except Exception as exc:
        LOG.exception("Catalog email notification failed")
        raise RuntimeError(f"Knuffelwuff-E-Mail konnte nicht gesendet werden: {exc}") from exc


def hours_since(iso_timestamp: str | None) -> float | None:
    if not iso_timestamp:
        return None
    try:
        then = datetime.fromisoformat(iso_timestamp)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - then).total_seconds() / 3600
    except ValueError:
        return None


def should_notify(result: CheckResult, old: dict[str, Any], cooldown_hours: float) -> bool:
    if result.available is not True:
        return False
    if old.get("available") is not True:
        return True
    elapsed = hours_since(old.get("last_notified_at"))
    return cooldown_hours > 0 and elapsed is not None and elapsed >= cooldown_hours


def launch_browser(playwright) -> Browser:
    launch_errors: list[str] = []
    for channel in ("msedge", "chrome"):
        try:
            browser = playwright.chromium.launch(channel=channel, headless=True)
            LOG.info("Using installed browser channel: %s", channel)
            return browser
        except Exception as exc:
            launch_errors.append(f"{channel}: {type(exc).__name__}: {exc}")
    try:
        browser = playwright.chromium.launch(headless=True)
        LOG.info("Using Playwright Chromium")
        return browser
    except Exception as exc:
        launch_errors.append(f"chromium: {type(exc).__name__}: {exc}")
        details = "\n".join(launch_errors)
        raise RuntimeError(
            "Kein unterstützter Browser konnte gestartet werden. "
            "Bitte Microsoft Edge oder Google Chrome installieren.\n" + details
        ) from exc


def run_once(config_path: Path, state_path: Path, *, dry_run: bool = False) -> list[CheckResult]:
    config, products, catalogs = load_config(config_path)
    settings = config.get("settings", {})
    timeout_ms = int(settings.get("timeout_seconds", 30)) * 1000
    cooldown_hours = float(settings.get("notification_cooldown_hours", 24))
    between_checks = float(settings.get("seconds_between_checks", 3))
    between_catalog_pages = float(settings.get("catalog_seconds_between_pages", 1))
    state = load_state(state_path)

    results: list[CheckResult] = []
    with sync_playwright() as playwright:
        browser = launch_browser(playwright)
        try:
            enabled_products = [product for product in products if product.enabled]
            for index, product in enumerate(enabled_products):
                LOG.info("Checking %s: %s", product.retailer, product.url)
                result = check_product(browser, product, timeout_ms)
                results.append(result)
                old = state["products"].get(result.key, {})
                notified = False

                if should_notify(result, old, cooldown_hours):
                    if dry_run:
                        LOG.info("DRY RUN: notification would be sent for %s", result.key)
                    else:
                        notify(result)
                        notified = True

                new_record = asdict(result)
                new_record["last_notified_at"] = (
                    datetime.now(timezone.utc).isoformat() if notified else old.get("last_notified_at")
                )
                state["products"][result.key] = new_record
                save_state(state_path, state)

                status = {True: "VERFÜGBAR", False: "nicht verfügbar", None: "unklar"}[result.available]
                LOG.info("%s: %s (%s)", result.retailer, status, result.reason)
                if index < len(enabled_products) - 1 and between_checks > 0:
                    time.sleep(between_checks)

            for catalog in (entry for entry in catalogs if entry.enabled and entry.urls):
                LOG.info("Checking catalog %s", catalog.name)
                check = check_catalog(
                    browser,
                    catalog,
                    timeout_ms,
                    seconds_between_pages=between_catalog_pages,
                )
                key = catalog_key(catalog)
                old_record = state["catalogs"].get(key, {})
                initialized = bool(old_record.get("initialized"))
                old_items = old_record.get("items", {}) if isinstance(old_record.get("items", {}), dict) else {}
                events = compare_catalog_items(check.items, old_items, initialized=initialized)

                if events:
                    if dry_run:
                        LOG.info("DRY RUN: %s Knuffelwuff notification(s) would be sent", len(events))
                    else:
                        notify_catalog_changes(check, events)
                elif not initialized:
                    LOG.info("Catalog baseline saved; no first-run notification")

                state["catalogs"][key] = update_catalog_state(old_record, check)
                save_state(state_path, state)

                if not initialized:
                    reason = f"Ausgangsbestand gespeichert: {len(check.items)} Artikel auf {check.pages_checked} Seite(n)"
                else:
                    reason = f"{len(check.items)} Artikel geprüft; {len(events)} Änderung(en)"
                if check.errors:
                    reason += f"; {len(check.errors)} Teilfehler"
                results.append(CheckResult(
                    key=key,
                    name=catalog.name,
                    retailer=catalog.retailer,
                    url=catalog.urls[0],
                    available=True if check.items else None,
                    reason=reason,
                    checked_at=check.checked_at,
                ))
        finally:
            browser.close()
    return results


def print_summary(results: list[CheckResult]) -> None:
    print("\nErgebnis:")
    for result in results:
        marker = {True: "✅", False: "❌", None: "⚠️"}[result.available]
        print(f"{marker} {result.retailer}: {result.name} — {result.reason}")


def test_notification() -> None:
    fake = CheckResult(
        key="test:midea-portasplit",
        name="Midea PortaSplit (Testnachricht)",
        retailer="Test-Shop",
        url="https://example.com/midea-portasplit",
        available=True,
        reason="Manueller Benachrichtigungstest",
        checked_at=datetime.now(timezone.utc).isoformat(),
    )
    notify(fake, test=True)


def test_knuffelwuff_notification() -> None:
    catalog = Catalog(
        name="Knuffelwuff Sortiment",
        retailer="Knuffelwuff",
        urls=("https://www.knuffelwuff.de/",),
    )
    item = CatalogItem(
        key="test:knuffelwuff",
        name="Knuffelwuff Testartikel",
        url="https://www.knuffelwuff.de/",
        available=True,
        price="29,95 €",
        new_badge=True,
        source_url="https://www.knuffelwuff.de/",
    )
    check = CatalogCheck(
        catalog=catalog,
        items={item.key: item},
        pages_checked=1,
        checked_at=datetime.now(timezone.utc).isoformat(),
        errors=[],
    )
    notify_catalog_changes(check, [CatalogEvent(kind="new", item=item)], test=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Midea- und Knuffelwuff-Verfügbarkeits-Bot")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--once", action="store_true", help="Einmal prüfen und beenden")
    parser.add_argument("--dry-run", action="store_true", help="Prüfen, aber keine Nachricht senden")
    parser.add_argument("--test-notification", action="store_true", help="Midea-Testnachricht senden")
    parser.add_argument("--test-knuffelwuff", action="store_true", help="Knuffelwuff-Testnachricht senden")
    parser.add_argument("--interval", type=int, default=None, help="Prüfintervall in Minuten")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.test_notification:
        test_notification()
        print("Midea-Testnachricht wurde versendet.")
        return 0
    if args.test_knuffelwuff:
        test_knuffelwuff_notification()
        print("Knuffelwuff-Testnachricht wurde versendet.")
        return 0

    if not args.config.exists():
        LOG.error("Konfigurationsdatei nicht gefunden: %s", args.config)
        return 2

    try:
        if args.once:
            print_summary(run_once(args.config, args.state, dry_run=args.dry_run))
            return 0

        config, _, _ = load_config(args.config)
        interval_minutes = args.interval or int(config.get("settings", {}).get("check_interval_minutes", 30))
        if interval_minutes < 10:
            LOG.warning("Ein Intervall unter 10 Minuten belastet Shops unnötig; verwende 10 Minuten.")
            interval_minutes = 10
        while True:
            print_summary(run_once(args.config, args.state, dry_run=args.dry_run))
            LOG.info("Next check in %s minutes", interval_minutes)
            time.sleep(interval_minutes * 60)
    except KeyboardInterrupt:
        LOG.info("Stopped by user")
        return 130
    except Exception as exc:
        LOG.exception("Bot failed")
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
