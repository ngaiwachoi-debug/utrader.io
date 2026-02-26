import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load .env from project root (same directory as this file) so it works regardless of cwd
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

# Do not hardcode DATABASE_URL; use .env only to avoid exposing credentials in git.
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Set it in .env (e.g. postgresql://user:password@host/dbname?sslmode=require)."
    )

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()