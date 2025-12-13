# app/db.py - VERSION ULTRA SIMPLE
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Import conditionnel pour dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ dotenv chargé")
except ImportError:
    print("⚠️  python-dotenv non installé")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL manquant dans .env")

print(f"🔗 Connexion à la base de données...")

# CONFIGURATION MINIMALE
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    """Dépendance sync ultra simple"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Fonction pour tester la connexion
def test_connection():
    """Teste la connexion à la base"""
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print(f"✅ Base de données connectée: {result.scalar()}")
            return True
    except Exception as e:
        print(f"❌ Erreur connexion DB: {e}")
        return False