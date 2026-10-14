"""Automatically find and persist commercially reusable food photos from open image libraries.

Search Wikimedia Commons first, then Openverse as a broad second source. Both paths are
shared by every dish; no dish is hard-coded into the catalogue flow.
"""
import html
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from food_image_models import FoodImage
from image_service import ImageUploadMetadata, optimize_photo, persist_photo

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILE_PREFIX = "https://commons.wikimedia.org/wiki/"
OPENVERSE_API = "https://api.openverse.org/v1"
ALLOWED_IMAGE_HOSTS = {"upload.wikimedia.org"}
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
USER_AGENT = "CanteenOS/1.0 (https://github.com/jaykelani7-rgb/Canteen-Management-System; automatic food-photo matching)"
REQUEST_TIMEOUT = httpx.Timeout(3.5, connect=1.8, pool=1.0)
IMAGE_TIMEOUT_SECONDS = 2.5

# Search aliases improve recall for common spelling/transliteration differences in Indian menus.
# Every dish still follows the same generic search flow; this only broadens search vocabulary.
SEARCH_SYNONYMS = {
    "sabudana": ("sago", "tapioca pearls"),
    "sago": ("sabudana", "tapioca pearls"),
    "tapioca": ("sabudana", "sago pearls"),
    "pohe": ("poha", "kanda poha"),
    "poha": ("pohe", "kanda poha"),
    "khichdi": ("khichri", "khichadi"),
    "khichri": ("khichdi", "khichadi"),
    "dosa": ("dosai", "masala dosa"),
    "dosai": ("dosa",),
    "idli": ("idly",),
    "idly": ("idli",),
    "vada": ("vadai", "fritter"),
    "pakora": ("pakoda", "fritter"),
    "pakoda": ("pakora", "fritter"),
    "puri": ("poori",),
    "poori": ("puri",),
    "chole": ("chana", "chickpea curry"),
    "chana": ("chole", "chickpea curry"),
    "gobi": ("cauliflower",),
    "aloo": ("potato",),
    "mutter": ("peas",),
    "matar": ("peas",),
    "paneer": ("indian cheese",),
    "upma": ("rava upma", "semolina"),
    "jalebi": ("jilebi",),
    "biryani": ("biriyani",),
    "bhakri": ("flatbread",),
    "misal": ("misal pav",),
    "maggi": ("instant noodles",),
}
OPENVERSE_LICENSES = {
    "by": "CC BY",
    "by-sa": "CC BY-SA",
    "cc0": "CC0",
    "pdm": "Public Domain Mark",
}


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        value = data.strip()
        if value:
            self.parts.append(value)


def plain_metadata(value):
    if not isinstance(value, str):
        return ""
    parser = _TextOnly()
    try:
        parser.feed(value)
        parser.close()
        return re.sub(r"\\s+", " ", html.unescape(" ".join(parser.parts))).strip()
    except Exception:
        return re.sub(r"\\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()


def is_reusable_license(value):
    """Accept commercial reuse and adaptations; reject non-commercial/no-derivatives."""
    name = re.sub(r"\\s+", " ", (value or "").strip()).upper()
    if name.startswith(("CC0", "PUBLIC DOMAIN", "PDM")):
        return True
    if any(term in name for term in ("NONCOMMERCIAL", "NODERIV", "-NC", "-ND")):
        return False
    return bool(re.match(r"^CC BY(?:-SA)?(?:\\s|$)", name))


def _words(value):
    ignored = {"the", "and", "with", "from", "food", "dish", "image", "photo", "file"}
    return {
        word for word in re.findall(r"[a-z0-9]+", (value or "").lower())
        if len(word) > 1 and word not in ignored
    }


def _expanded_terms(dish_name):
    terms = _words(dish_name)
    expanded = set(terms)
    for term in terms:
        expanded.update(_words(" ".join(SEARCH_SYNONYMS.get(term, ()))))
    return expanded


def _openverse_search_query(dish_name):
    """Build a generic query with spelling/ingredient alternatives, bounded to API limits."""
    clean = re.sub(r"\\s+", " ", (dish_name or "").strip())[:100]
    if not clean:
        return ""
    phrases = [f'"{clean}"', f'"{clean} food"', f'"{clean} Indian food"']
    aliases = []
    for word in _words(clean):
        aliases.extend(SEARCH_SYNONYMS.get(word, ()))
    for alias in aliases:
        phrase = f'"{alias}"'
        if phrase not in phrases:
            phrases.append(phrase)
    return " OR ".join(phrases)[:195]


def _relevance(dish_name, title, metadata):
    terms = _words(dish_name)
    description = " ".join(
        plain_metadata((metadata.get(key) or {}).get("value", ""))
        for key in ("ObjectName", "ImageDescription")
    )
    return len(terms & _words(title + " " + description))


def _openverse_relevance(dish_name, result):
    terms = _words(dish_name)
    title = result.get("title") or ""
    description = result.get("description") or ""
    tags = result.get("tags") or []
    tag_text = " ".join(
        str(tag.get("name") or tag.get("title") or "") if isinstance(tag, dict) else str(tag)
        for tag in tags
    )
    searchable = title + " " + description + " " + tag_text
    found = _words(searchable)
    direct = len(terms & found)
    if direct:
        return direct * 10 + len((_expanded_terms(dish_name) - terms) & found)

    # Synonyms are a fallback for spelling and regional naming differences. Require food-photo
    # context so an ingredient/plant photo is not mistaken for the prepared dish.
    aliases = (_expanded_terms(dish_name) - terms) & found
    context = {"plate", "plated", "cooked", "recipe", "cuisine", "meal", "snack", "breakfast",
               "lunch", "dinner", "curry", "restaurant", "kitchen", "culinary", "served"}
    return 1 if aliases and context & found else 0


def _field(metadata, key):
    return plain_metadata((metadata.get(key) or {}).get("value", ""))


def _safe_image_url(value):
    try:
        parsed = urlsplit(value or "")
    except ValueError:
        return False
    return (
        parsed.scheme == "https" and parsed.hostname in ALLOWED_IMAGE_HOSTS
        and not parsed.username and not parsed.password and not parsed.fragment
    )


def _safe_license_url(value):
    try:
        parsed = urlsplit(value or "")
    except ValueError:
        return False
    return (
        parsed.scheme == "https" and parsed.hostname == "creativecommons.org"
        and not parsed.username and not parsed.password and not parsed.fragment
    )


def _openverse_license_name(code, version):
    """Translate Openverse's compact license codes to a strict allowlist."""
    code = (code or "").strip().lower()
    if code not in OPENVERSE_LICENSES:
        return ""
    prefix = OPENVERSE_LICENSES[code]
    version = (version or "").strip()
    if code in {"by", "by-sa"}:
        if not re.fullmatch(r"\\d+(?:\\.\\d+)?", version):
            return ""
        return f"{prefix} {version}"
    return f"{prefix} {version}" if version else prefix


def _safe_landing_url(value):
    try:
        parsed = urlsplit(value or "")
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


async def _bounded_image(response):
    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        return None, None
    body = bytearray()
    async for chunk in response.aiter_bytes():
        if len(body) + len(chunk) > MAX_DOWNLOAD_BYTES:
            return None, None
        body.extend(chunk)
    return bytes(body), mime


async def _download_image(client, image_url, allowed_hosts):
    try:
        parsed = urlsplit(image_url)
        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
            return None, None
        async with client.stream(
            "GET", image_url,
            headers={"Accept": "image/jpeg,image/png,image/webp"},
            timeout=IMAGE_TIMEOUT_SECONDS,
        ) as response:
            if response.status_code != 200:
                return None, None
            return await _bounded_image(response)
    except (httpx.HTTPError, ValueError):
        return None, None


async def _persist_candidate(db, client, image_url, allowed_hosts, metadata, admin_id):
    raw, mime = await _download_image(client, image_url, allowed_hosts)
    if not raw or not mime:
        return None
    try:
        optimized, width, height = optimize_photo(raw, mime)
    except HTTPException:
        return None
    try:
        details = ImageUploadMetadata(**metadata)
    except ValidationError:
        return None
    return await persist_photo(db, optimized, width, height, details, admin_id)


async def _find_commons_photo(db, client, dish_name, admin_id):
    try:
        response = await client.get(COMMONS_API, params={
            "action": "query", "generator": "search",
            # Unquoted full text is much more forgiving than an exact-phrase-only search.
            "gsrsearch": f"{dish_name} filetype:bitmap",
            "gsrnamespace": "6", "gsrlimit": "30",
            "prop": "imageinfo", "iiprop": "url|extmetadata",
            "iiurlwidth": "1280", "format": "json", "formatversion": "2",
        }, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None

    raw_pages = (data.get("query") or {}).get("pages") or []
    pages = list(raw_pages.values()) if isinstance(raw_pages, dict) else raw_pages if isinstance(raw_pages, list) else []
    terms = _words(dish_name)
    min_overlap = max(1, (len(terms) + 1) // 2)
    candidates = []
    for page in pages:
        title = page.get("title", "")
        info_list = page.get("imageinfo") or []
        if not title.startswith("File:") or not info_list:
            continue
        info = info_list[0]
        try:
            if int(info.get("width", 0)) < 600 or int(info.get("height", 0)) < 400:
                continue
        except (TypeError, ValueError):
            continue
        metadata = info.get("extmetadata") or {}
        license_name = _field(metadata, "LicenseShortName")
        license_url = _field(metadata, "LicenseUrl")
        if not is_reusable_license(license_name):
            continue
        if license_name.upper().startswith("CC") and not _safe_license_url(license_url):
            continue
        image_url = info.get("thumburl") or info.get("url")
        if not _safe_image_url(image_url):
            continue
        score = _relevance(dish_name, title.removeprefix("File:"), metadata)
        if score < min_overlap:
            continue
        candidates.append((score, title, metadata, license_name, license_url, image_url))

    candidates.sort(key=lambda value: (-value[0], value[1].casefold()))
    for _, title, metadata, license_name, license_url, image_url in candidates[:2]:
        author = _field(metadata, "Artist") or "Author listed on Wikimedia Commons file page"
        credit = _field(metadata, "Credit")
        attribution = f"{author}; Wikimedia Commons"
        if credit and credit.casefold() not in attribution.casefold():
            attribution += f"; credit: {credit}"
        file_url = COMMONS_FILE_PREFIX + quote(title.replace(" ", "_"), safe=":_()'")
        result = await _persist_candidate(db, client, image_url, ALLOWED_IMAGE_HOSTS, {
            "dishName": dish_name,
            "source": "Wikimedia Commons: " + file_url,
            "license": license_name[:200],
            "attribution": attribution[:3000],
            "author": author[:200],
            "licenseUrl": license_url if _safe_license_url(license_url) else "",
            "modifications": "Auto-matched; resized and converted to WebP.",
            "rightsConfirmed": True,
        }, admin_id)
        if result:
            return result
    return None


async def _find_openverse_photo(db, client, dish_name, admin_id):
    try:
        response = await client.get(OPENVERSE_API + "/images/", params={
            "q": _openverse_search_query(dish_name),
            "license_type": "commercial",
            "size": "large",
            "filter_dead": "true",
            "page_size": 25,
            "page": 1,
        }, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None

    candidates = []
    for item in data.get("results") or []:
        license_name = _openverse_license_name(item.get("license"), item.get("license_version"))
        license_url = item.get("license_url") or ""
        if not license_name or not is_reusable_license(license_name) or not _safe_license_url(license_url):
            continue
        if not _safe_landing_url(item.get("foreign_landing_url")):
            continue
        try:
            width, height = int(item.get("width") or 0), int(item.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if width < 600 or height < 400:
            continue
        identifier = str(item.get("id") or "").strip()
        if not identifier or len(identifier) > 300:
            continue
        score = _openverse_relevance(dish_name, item)
        if score <= 0:
            continue
        candidates.append((score, width * height, item, license_name, license_url))

    candidates.sort(key=lambda value: (-value[0], -value[1], str(value[2].get("title") or "").casefold()))
    for _, _, item, license_name, license_url in candidates[:2]:
        identifier = quote(str(item["id"]), safe="")
        # Download through Openverse's image proxy rather than contacting an arbitrary result URL.
        image_url = f"{OPENVERSE_API}/images/{identifier}/thumb/?full_size=true&compressed=true"
        creator = re.sub(r"\\s+", " ", str(item.get("creator") or "Creator not listed")).strip()
        provider = re.sub(r"\\s+", " ", str(item.get("provider") or item.get("source") or "Openverse source")).strip()
        landing = item["foreign_landing_url"]
        attribution = f"Creator: {creator}; provider: {provider}; source page: {landing}"
        result = await _persist_candidate(db, client, image_url, {"api.openverse.org"}, {
            "dishName": dish_name,
            "source": ("Openverse: " + landing)[:1000],
            "license": license_name[:200],
            "attribution": attribution[:3000],
            "author": creator[:200],
            "licenseUrl": license_url,
            "modifications": "Auto-matched via Openverse; resized and converted to WebP.",
            "rightsConfirmed": True,
        }, admin_id)
        if result:
            return result
    return None


async def find_and_store_food_image(db: AsyncSession, dish_name: str, admin_id: int):
    """Search Wikimedia Commons then Openverse; persist validated image bytes in PostgreSQL."""
    dish_name = re.sub(r"\\s+", " ", (dish_name or "").strip())[:100]
    if len(dish_name) < 2 or settings.ENVIRONMENT == "test":
        return None

    existing = (await db.execute(
        select(FoodImage).where(
            func.lower(FoodImage.dish_name) == dish_name.lower(),
            or_(
                FoodImage.source.startswith("Wikimedia Commons:"),
                FoodImage.source.startswith("Openverse:"),
            ),
            FoodImage.is_archived.is_(False),
        ).order_by(FoodImage.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing:
        return existing

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            image = await _find_commons_photo(db, client, dish_name, admin_id)
            if image:
                return image
            return await _find_openverse_photo(db, client, dish_name, admin_id)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # An upstream photo index should never crash catalogue editing.
        return None
