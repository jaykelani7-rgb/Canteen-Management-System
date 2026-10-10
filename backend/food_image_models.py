"""Optimized image binaries live in the existing PostgreSQL database."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from database import Base


class FoodImage(Base):
    __tablename__ = "food_images"
    id = Column(String(32), primary_key=True)
    dish_name = Column(String(100), nullable=False, index=True)
    data = Column(LargeBinary, nullable=False)
    sha256 = Column(String(64), nullable=False, unique=True)
    mime_type = Column(String(30), nullable=False, default="image/webp")
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    byte_size = Column(Integer, nullable=False)
    source = Column(String(1000), nullable=False)
    license = Column(String(200), nullable=False)
    license_url = Column(String(1000), nullable=True)
    author = Column(String(200), nullable=True)
    attribution = Column(Text, nullable=False)
    modifications = Column(String(255), nullable=False)
    rights_confirmed = Column(Boolean, nullable=False)
    uploaded_by_admin_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("byte_size > 0 AND byte_size <= 327680 AND length(data) = byte_size", name="ck_food_image_bytes"),
        CheckConstraint("width BETWEEN 64 AND 1280 AND height BETWEEN 64 AND 1280", name="ck_food_image_dimensions"),
        CheckConstraint("mime_type = 'image/webp' AND rights_confirmed", name="ck_food_image_validated"),
    )
