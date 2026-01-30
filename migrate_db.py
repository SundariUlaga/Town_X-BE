"""
Database migration script
Run this after updating models.py
"""
from database import engine
from models import Base

def create_tables():
    """Create all tables defined in models"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully!")
    print("\nTables created:")
    print("- properties")
    print("- stories")
    print("- story_views")

if __name__ == "__main__":
    create_tables()
