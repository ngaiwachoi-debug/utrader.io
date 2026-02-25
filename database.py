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

# Safety check: If the URL is missing, print a clear error
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL is missing! Check your .env file.")
    # If the .env file isn't working, you can temporarily paste your 
    # postgresql:// string directly here as a string.
    DATABASE_URL = "postgresql://neondb_owner:npg_pyaiQAxCnP84@ep-dawn-hall-aik0s1zx-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()