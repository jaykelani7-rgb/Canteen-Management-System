"""Automatically match dishes to commercially reusable Wikimedia Commons food photos."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from food_image_models import FoodImage
from image_service import ImageUploadMetadata, optimize_photo, persist_photo

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_FILE_PREFIX = "https://commons.wikimedia.org/wiki/"
ALLOWED_IMAGE_HOSTS = {"upload.wikimedia.org"}
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
USER_AGENT = "CanteenOS/1.0 (automatic food-photo catalogue; licensed reuse with attribution)"


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
        return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()
    except Exception:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value))).strip()


def is_reusable_license(value):
    """Accept commercial reuse and adaptations; reject non-commercial/no-derivatives."""
    name = re.sub(r"\s+", " ", (value or "").strip()).upper()
    if name.startswith(("CC0", "PUBLIC DOMAIN", "PDM")):
        return True
    if any(term in name for term in ("NONCOMMERCIAL", "NODERIV", "-NC", "-ND")):
        return False
    return bool(re.match(r"^CC BY(?:-SA)?(?:\s|$)", name))


def _words(value):
    ignored = {"the", "and", "with", "from", "food", "dish", "image", "photo", "file"}
    return {word for word in re.findall(r"[a-z0-9]+", (value or "").lower())
            if len(word) > 1 and word not in ignored}


def _relevance(dish_name, title, metadata):
    terms = _words(dish_name)
    if not terms:
        return 0
    description = " ".join(plain_metadata((metadata.get(key) or {}).get("value", ""))
                           for key in ("ObjectName", "ImageDescription"))
    return len(terms & _words(title + " " + description))


def _field(metadata, key):
    return plain_metadata((metadata.get(key) or {}).get("value", ""))


def _safe_image_url(value):
    try:
        parsed = urlsplit(value or "")
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.hostname in ALLOWED_IMAGE_HOSTS
            and not parsed.username and not parsed.password and not parsed.fragment)


def _safe_license_url(value):
    try:
        parsed = urlsplit(value or "")
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.hostname == "creativecommons.org"
            and not parsed.username and not parsed.password and not parsed.fragment)


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


async def find_and_store_food_image(db: AsyncSession, dish_name: str, admin_id: int):
    """Find a high-resolution, reusable photo; validate it and save the bytes to PostgreSQL."""
    dish_name = re.sub(r"\s+", " ", (dish_name or "").strip())[:100]
    if len(dish_name) < 2 or settings.ENVIRONMENT == "test":
        return None

    existing = (await db.execute(
        select(FoodImage).where(
            func.lower(FoodImage.dish_name) == dish_name.lower(),
            FoodImage.source.startswith("Wikimedia Commons:"),
            FoodImage.is_archived.is_(False),
        ).order_by(FoodImage.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing:
        return existing

    timeout = httpx.Timeout(4.5, connect=2.0, pool=2.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
            response = await client.get(COMMONS_API, params={
                "action": "query", "generator": "search",
                "gsrsearch": f'"{dish_name}" filetype:bitmap',
                "gsrnamespace": "6", "gsrlimit": "15",
                "prop": "imageinfo", "iiprop": "url|extmetadata",
                "iiurlwidth": "1280", "format": "json", "formatversion": "2",
            })
            response.raise_for_status()
            data = response.json()
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
                    # Prioritize real photography over icons/tiny thumbnails.
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
                try:
                    async with client.stream("GET", image_url, headers={"Accept": "image/jpeg,image/png,image/webp"}) as image_response:
                        if image_response.status_code != 200:
                            continue
                        raw, mime = await _bounded_image(image_response)
                except httpx.HTTPError:
                    continue
                if not raw or not mime:
                    continue
                try:
                    optimized, width, height = optimize_photo(raw, mime)
                except HTTPException:
                    continue

                author = _field(metadata, "Artist") or "Author listed on Wikimedia Commons file page"
                credit = _field(metadata, "Credit")
                attribution = f"{author}; Wikimedia Commons"
                if credit and credit.casefold() not in attribution.casefold():
                    attribution += f"; credit: {credit}"
                file_url = COMMONS_FILE_PREFIX + quote(title.replace(" ", "_"), safe=":_()'")
                try:
                    details = ImageUploadMetadata(
                        dishName=dish_name, source="Wikimedia Commons: " + file_url,
                        license=license_name[:200], attribution=attribution[:3000],
                        author=author[:200],
                        licenseUrl=license_url if _safe_license_url(license_url) else "",
                        modifications="Matched automatically; resized and converted to WebP.",
                        rightsConfirmed=True,
                    )
                except ValidationError:
                    continue
                return await persist_photo(db, optimized, width, height, details, admin_id)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    return None
