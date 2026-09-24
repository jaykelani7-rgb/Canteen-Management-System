import json
from typing import List
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

ocr_router = APIRouter(prefix="/admin/menu", tags=["Admin Menu OCR"])


# -------------------------------------------------------------------------
# Pydantic Schemas for Structured Output
# -------------------------------------------------------------------------
class MenuMeal(BaseModel):
    day: str = Field(..., description="Day of the week (e.g., Monday, Tuesday)")
    meal_type: str = Field(..., description="Meal category (e.g., Breakfast, Lunch, Dinner)")
    items: List[str] = Field(..., description="List of food dishes served for this meal")


class WeeklyMenu(BaseModel):
    schedule: List[MenuMeal] = Field(..., description="List of scheduled meals for the week")


# -------------------------------------------------------------------------
# Vision OCR Endpoint (POST /api/admin/menu/upload-ocr)
# -------------------------------------------------------------------------
@ocr_router.post(
    "/upload-ocr",
    response_model=WeeklyMenu,
    summary="Extract weekly canteen menu from an image via Gemini Vision",
    status_code=status.HTTP_200_OK,
)
async def upload_menu_ocr(
    file: UploadFile = File(..., description="Weekly menu image file")
):
    # 1. Validate MIME type
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type '{content_type}'. Uploaded file must be an image.",
        )

    # 2. Read image buffer directly into memory (no disk write)
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded image file is empty.",
        )

    # 3. Call Google Gemini Vision with Structured Output
    try:
        client = genai.Client()

        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=content_type,
        )

        prompt = (
            "Extract the weekly food menu from this image. "
            "Ignore headers like 'WEEKLY MENU'. "
            "Group the food items by day (e.g., Monday, Tuesday) and meal_type (Lunch, Dinner)."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=WeeklyMenu,
            ),
        )

        if not response.text:
            raise ValueError("Gemini returned an empty response.")

        parsed_data = json.loads(response.text)
        return WeeklyMenu(**parsed_data)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gemini Vision extraction failed: {str(e)}",
        )
