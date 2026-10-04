from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI

from . import db

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        db.init()
    except psycopg.OperationalError as e:
        raise RuntimeError("PostgreSQL недоступен: запустите docker compose up -d") from e
    yield


app = FastAPI(title="AI Redesign", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "db": db.ping()}
