from fastapi import APIRouter
from news_service import get_latest_news

router = APIRouter()

@router.get("/news/latest")
async def latest_news():
    return await get_latest_news()