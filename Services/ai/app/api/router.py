from fastapi import APIRouter
from app.api.routes import conversations, messages, reviews, feature_plans, build_runs

api_router = APIRouter()

api_router.include_router(conversations.router, tags=["Conversations"])
api_router.include_router(messages.router, tags=["Messages"])
api_router.include_router(reviews.router, tags=["Code Review"])
api_router.include_router(feature_plans.router, tags=["Feature Plans"])
api_router.include_router(build_runs.router, tags=["Build Runs"])
