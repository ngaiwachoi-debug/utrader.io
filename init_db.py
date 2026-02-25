from database import engine, Base
import models

def init_db():
    print("Connecting to Neon and creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Success! Your database is ready.")

if __name__ == "__main__":
    init_db()