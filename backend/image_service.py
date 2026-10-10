"""Validated, immutable PostgreSQL photographs with explicit publication rights."""
import asyncio
from datetime import datetime, timezone
import hashlib
import io
import re
import uuid
import warnings
from urllib.parse import urlsplit

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import defer

from config import settings
from food_image_models import FoodImage

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 8_000_000
MAX_OUTPUT_BYTES = 320 * 1024
MAX_EDGE = 1280
MODIFICATIONS = "Resized and converted to WebP; EXIF and other embedded metadata removed."
MIME_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
decode_semaphore = asyncio.Semaphore(1)


class ImageUploadMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    dishName: str = Field(min_length=2, max_length=100)
    source: str = Field(min_length=3, max_length=1000)
    license: str = Field(min_length=3, max_length=200)
    attribution: str = Field(min_length=3, max_length=3000)
    rightsConfirmed: bool
    author: str = Field(default="", max_length=200)
    licenseUrl: str = Field(default="", max_length=1000)
    modifications: str = Field(default="", max_length=255)

    @field_validator("modifications")
    @classmethod
    def bounded_modifications(cls,value):
        if value and len(value) + len(MODIFICATIONS) + 1 > 255:
            raise ValueError("Describe source photo changes briefly so the full optimization note can be retained")
        return value

    @field_validator("licenseUrl")
    @classmethod
    def valid_license_url(cls, value):
        if value:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Licence links must be public HTTPS URLs without credentials")
        return value

    @field_validator("dishName", "source", "license", "attribution", "author", "modifications")
    @classmethod
    def readable_text(cls, value):
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Image metadata contains unsupported control characters")
        return value


def image_url(image_id):
    origin = getattr(settings, "PUBLIC_API_ORIGIN", "").rstrip("/")
    parsed = urlsplit(origin)
    if (not origin or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or parsed.scheme not in {"https", "http"}
            or (settings.ENVIRONMENT == "production" and parsed.scheme != "https")):
        raise HTTPException(503, "Public image delivery is not configured")
    if not re.fullmatch(r"[a-f0-9]{32}", image_id or ""):
        raise HTTPException(422, "Invalid managed image identifier")
    return origin + "/api/food-images/" + image_id


def image_metadata(row):
    public = image_url(row.id)
    return {"id": row.id, "dishName": row.dish_name, "source": row.source, "license": row.license,
        "licenseUrl": row.license_url or "", "author": row.author or "", "attribution": row.attribution,
        "modifications": row.modifications, "width": row.width, "height": row.height,
        "byteSize": row.byte_size, "mimeType": row.mime_type, "sha256": row.sha256,
        "previewUrl": public.replace("/api/food-images/", "/api/admin/food-images/") + "/content",
        "photo": public, "creditsUrl": public + "/credits", "published": row.published_at is not None,
        "createdAt": row.created_at.isoformat() if row.created_at else None}


def optimize_photo(raw, declared_mime):
    if not raw:
        raise HTTPException(400, "Choose a photograph to upload")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Photographs must be 5 MiB or smaller")
    if declared_mime not in MIME_TYPES.values():
        raise HTTPException(415, "Upload a JPEG, PNG or WebP photograph")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if MIME_TYPES.get(probe.format) != declared_mime:
                    raise HTTPException(415, "File content does not match its declared image type")
                if probe.width < 64 or probe.height < 64 or probe.width * probe.height > MAX_IMAGE_PIXELS:
                    raise HTTPException(422, "Photographs must be at least 64 pixels per side and at most 8 megapixels")
                if getattr(probe, "n_frames", 1) != 1:
                    raise HTTPException(422, "Animated photographs are not supported")
                probe.verify()
            with Image.open(io.BytesIO(raw)) as decoded:
                decoded.load()
                oriented = ImageOps.exif_transpose(decoded)
                oriented.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
                if min(oriented.size) < 64:
                    raise HTTPException(422, "Choose a photograph with a less extreme aspect ratio")
                mode = "RGBA" if "A" in oriented.getbands() else "RGB"
                converted = oriented.convert(mode)
                clean = Image.new(mode, converted.size)
                clean.paste(converted)
                for quality in (82, 72, 62):
                    stream = io.BytesIO()
                    clean.save(stream, format="WEBP", quality=quality, method=5)
                    value = stream.getvalue()
                    if len(value) <= MAX_OUTPUT_BYTES:
                        return value, clean.width, clean.height
                raise HTTPException(422, "This photograph cannot be optimized within the image size limit; choose a simpler or smaller photo")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "The photograph is malformed or exceeds safe decoding limits") from None


async def stored_image(db, image_id, *, lock=False, include_archived=False):
    if not re.fullmatch(r"[a-f0-9]{32}", image_id or ""):
        raise HTTPException(404, "Photograph not found")
    query = select(FoodImage).options(defer(FoodImage.data)).where(FoodImage.id == image_id)
    if not include_archived:
        query = query.where(FoodImage.is_archived.is_(False))
    if lock:
        query = query.with_for_update()
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Photograph not found")
    return row


async def persist_photo(db, raw, width, height, metadata, admin_id):
    if not metadata.rightsConfirmed:
        raise HTTPException(422, "Confirm that you have permission to use this photograph")
    digest = hashlib.sha256(raw).hexdigest()
    # Serialize both deduplication and byte accounting across all Render workers.
    if db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(7263823)"))
    existing = (await db.execute(select(FoodImage).options(defer(FoodImage.data)).where(FoodImage.sha256 == digest))).scalar_one_or_none()
    if existing:
        if existing.is_archived:
            raise HTTPException(409, "This photograph is archived; upload a different photograph or restore it through an authorized review")
        return existing
    used = (await db.execute(select(func.coalesce(func.sum(FoodImage.byte_size), 0)))).scalar_one()
    maximum = getattr(settings, "FOOD_IMAGE_LIBRARY_MAX_BYTES", 64 * 1024 * 1024)
    if used + len(raw) > maximum:
        raise HTTPException(413, "The free image library storage limit has been reached; ask the administrator to review storage")
    row = FoodImage(id=uuid.uuid4().hex, dish_name=metadata.dishName, data=raw, sha256=digest,
        mime_type="image/webp", width=width, height=height, byte_size=len(raw), source=metadata.source,
        license=metadata.license, license_url=metadata.licenseUrl or None, author=metadata.author or None,
        attribution=metadata.attribution, modifications=" ".join(part for part in (metadata.modifications,MODIFICATIONS) if part), rights_confirmed=True,
        uploaded_by_admin_id=admin_id, is_archived=False)
    db.add(row)
    await db.flush()
    return row


async def require_publishable_image(db, item):
    if not item.image_id or not item.image_confirmed:
        raise HTTPException(422, "Attach and confirm an appropriate photograph before making this dish available")
    image = await stored_image(db, item.image_id, lock=True)
    if not image.rights_confirmed:
        raise HTTPException(422, "The photograph has not been approved for use")
    item.photo = image_url(image.id)
    if image.published_at is None:
        image.published_at = datetime.now(timezone.utc)
    return image


async def apply_catalogue_image(db, item, *, image_changed=False, name_changed=False, confirmed=None):
    if image_changed or name_changed:
        item.image_confirmed = confirmed is True
    elif confirmed is not None:
        item.image_confirmed = confirmed
    if not item.image_id:
        item.photo = None
        item.image_confirmed = False
        if image_changed:
            item.is_available = False
    else:
        image = await stored_image(db, item.image_id, lock=True)
        item.photo = image_url(image.id)
    if item.is_available:
        await require_publishable_image(db, item)
