from sqlalchemy import Column, String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.db.database import Base

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fetched_at = Column(DateTime, default=datetime.now, index=True)
    source = Column(String(100))
    category = Column(String(50), index=True)
    impact = Column(String(50))
    title = Column(Text)
    url = Column(Text, unique=True, index=True)
    breaking_flag = Column(Boolean, default=False)
    content = Column(Text)
    image_url = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    video_platform = Column(String(50), nullable=True)
