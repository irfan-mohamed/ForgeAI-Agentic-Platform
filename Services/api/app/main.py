from fastapi import FastAPI
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.database import engine
from app.api.routes import auth, users

setup_logging()

logger = logging.getLogger(__name__)

app = FastAPI(
    title= "ForgeAI API",
    version= "0.1.0",
)

Base.metadata.create_all(bind=engine)

@app.get('/')
def health_check():
    return {"message" : "ForgeAI API is Running..."}

app.include_router(auth.router, prefix = settings.API_V1_STR)
app.include_router(users.router, prefix = settings.API_V1_STR)