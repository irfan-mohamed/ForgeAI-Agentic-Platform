import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL : str = "postgresql+psycopg://forgeai:Irfan%40123@localhost:5432/forgeai"
    PROJECT_NAME : str = "ForgeAI API"
    API_V1_STR : str = "/api/v1"

    SECRET_KEY : str = "9f82d1c68e16a2b4b457e5d8f630a1122aef912048cfc5d4b53ef1234bc56de2"
    ALGORITHM : str = "HS256"
    ACCESS_TOKEN_EXPIRY_MINUTES : int = 10

    class Config:
        case_sensitive = True


settings = Settings()