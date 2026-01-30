from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency function to get database session
    Yields database session and closes it after use
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
