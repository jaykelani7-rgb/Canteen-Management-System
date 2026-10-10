"""Admin-only library operations; public immutable bytes only after publication."""
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import defer
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException

from auth import get_current_admin
from database import cache_invalidate_prefix, get_db
from food_image_models import FoodImage
from models import FoodItem
from image_service import (ImageUploadMetadata, MAX_EDGE, MAX_IMAGE_PIXELS, MAX_OUTPUT_BYTES, MAX_UPLOAD_BYTES,
    decode_semaphore, image_metadata, optimize_photo, persist_photo, stored_image)

image_router = APIRouter(tags=["Food Image Library"])


@image_router.get("/admin/food-images/config")
async def image_limits(admin=Depends(get_current_admin)):
    return {"maxUploadBytes": MAX_UPLOAD_BYTES, "maxOutputBytes": MAX_OUTPUT_BYTES,
        "maxImagePixels": MAX_IMAGE_PIXELS, "maxEdge": MAX_EDGE, "mimeTypes": ["image/jpeg", "image/png", "image/webp"]}


@image_router.get("/admin/food-images")
async def library(query: str = Query("", max_length=100), limit: int = Query(100, ge=1, le=100),
                  offset: int = Query(0, ge=0), admin=Depends(get_current_admin), db=Depends(get_db)):
    statement = select(FoodImage).options(defer(FoodImage.data)).where(FoodImage.is_archived.is_(False))
    if query:
        statement = statement.where(FoodImage.dish_name.icontains(query, autoescape=True))
    rows = (await db.execute(statement.order_by(FoodImage.created_at.desc(), FoodImage.id).limit(limit).offset(offset))).scalars()
    return [image_metadata(row) for row in rows]


@image_router.post("/admin/food-images", status_code=201)
async def upload(request: Request, admin=Depends(get_current_admin), db=Depends(get_db)):
    # Authenticate before reading multipart data; cap even chunked requests before parsing.
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, "Send the photograph as multipart form data")
    cap = MAX_UPLOAD_BYTES + 16 * 1024
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > cap:
            raise HTTPException(413, "Photographs must be 5 MiB or smaller")
        body.extend(chunk)
    request._body = bytes(body)
    try:
        async with request.form(max_files=1, max_fields=9, max_part_size=4096) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise HTTPException(400, "Choose a photograph to upload")
            fields = {key: value for key, value in form.items() if key != "file"}
            if any(not isinstance(value, str) for value in fields.values()):
                raise HTTPException(422, "Image metadata must contain text fields")
            try:
                metadata = ImageUploadMetadata.model_validate(fields)
            except ValidationError:
                raise HTTPException(422, "Provide a dish name, source, licence, attribution and permission confirmation") from None
            if not metadata.rightsConfirmed:
                raise HTTPException(422, "Confirm that you have permission to use this photograph")
            raw = await file.read(MAX_UPLOAD_BYTES + 1)
            async with decode_semaphore:
                content, width, height = await run_in_threadpool(optimize_photo, raw, file.content_type or "")
        row = await persist_photo(db, content, width, height, metadata, admin.id)
        result = image_metadata(row)  # Delivery must be configured before committing.
        await db.commit()
        return result
    except MultiPartException:
        raise HTTPException(400, "Malformed multipart upload") from None


@image_router.get("/admin/food-images/{image_id}")
async def metadata(image_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    return image_metadata(await stored_image(db, image_id))


async def content(db, image_id, *, public):
    row = await stored_image(db, image_id, include_archived=public)
    if public and row.published_at is None:
        raise HTTPException(404, "Photograph not found")
    binary = (await db.execute(select(FoodImage.data).where(FoodImage.id == row.id))).scalar_one()
    return row, binary


@image_router.get("/admin/food-images/{image_id}/content")
async def private_preview(image_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    row, binary = await content(db, image_id, public=False)
    return Response(binary, media_type="image/webp", headers={"Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff", "Content-Disposition": 'inline; filename="' + row.id + '.webp"'})


@image_router.delete("/admin/food-images/{image_id}")
async def archive(image_id: str, admin=Depends(get_current_admin), db=Depends(get_db)):
    row = await stored_image(db, image_id, lock=True)
    attached = (await db.execute(select(FoodItem.id).where(FoodItem.image_id == row.id).limit(1))).first()
    if attached:
        raise HTTPException(409, "Remove this photograph from its menu items before archiving it")
    row.is_archived = True
    await db.commit()
    # Published historical bytes are retained; no original order snapshots are rewritten.
    return {"archived": True, "historicalImagesPreserved": row.published_at is not None}


@image_router.get("/food-images/{image_id}/credits")
async def public_credits(image_id: str, db=Depends(get_db)):
    row = await stored_image(db, image_id, include_archived=True)
    if row.published_at is None:
        raise HTTPException(404, "Photograph not found")
    return {key: value for key, value in image_metadata(row).items() if key in {
        "dishName", "source", "license", "licenseUrl", "author", "attribution", "modifications"}}


@image_router.get("/food-images/{image_id}")
async def public_image(image_id: str, request: Request, db=Depends(get_db)):
    row, binary = await content(db, image_id, public=True)
    etag = '"' + row.sha256 + '"'
    headers = {"Cache-Control": "public, max-age=86400, immutable", "ETag": etag,
               "X-Content-Type-Options": "nosniff", "Content-Disposition": 'inline; filename="' + row.id + '.webp"'}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(binary, media_type="image/webp", headers=headers)
