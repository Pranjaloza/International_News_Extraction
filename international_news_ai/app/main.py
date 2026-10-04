from fastapi import FastAPI
from app.routers.news_router import router as news_router
from app.db.database import engine
from app.db.models import Base

# Create tables on startup (no-op if they already exist)
Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="International Fast News AI System",
    version="1.0",
    description="High speed intelligent global news extraction service."
)

app.include_router(news_router, prefix="/news")

@app.get("/")
def home():
    return {"status": "running", "message": "News AI Backend Active"}
