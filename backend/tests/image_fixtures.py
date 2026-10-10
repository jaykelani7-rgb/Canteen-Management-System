"""Only isolated tests: generate a genuine decoded image and a persisted association."""
from datetime import datetime, timezone
import hashlib
import io
import uuid
from PIL import Image
from food_image_models import FoodImage

def photo_bytes(color=(210, 90, 30), *, format='PNG', size=(128, 96)):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format=format)
    return buffer.getvalue()

async def attach_test_image(db, item, *, admin_id=1):
    # Fresh opaque colour makes each generated library photo a distinct digest.
    token = uuid.uuid4().hex
    raw = photo_bytes(tuple(bytes.fromhex(token[:6])), format='WEBP')
    image = FoodImage(id=token, dish_name=item.name, data=raw, sha256=hashlib.sha256(raw).hexdigest(),
        mime_type='image/webp', width=128, height=96, byte_size=len(raw), source='Isolated generated test photograph',
        license='Test fixture permission', attribution='Generated exclusively for isolated automated tests',
        modifications='Generated test pixels', rights_confirmed=True, uploaded_by_admin_id=admin_id,
        is_archived=False, published_at=datetime.now(timezone.utc))
    db.add(image)
    await db.flush()
    item.image_id = image.id
    item.image_confirmed = True
    from image_service import image_url
    item.photo = image_url(image.id)
    return image
