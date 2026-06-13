from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.webhook import router as webhook_router
from app.api.feedback import router as feedback_router
from app.api.security import limiter
import os


app = FastAPI(
    title="AutoReviewer",
    description="Autonomous GitHub code review agent",
    version="0.1.0"
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(feedback_router)
app.include_router(webhook_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "auto-reviewer"}