import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def test_supabase_connection():
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if not DATABASE_URL:
        print("❌ DATABASE_URL non trouvé")
        return
    
    print("🔍 Test de connexion directe à Supabase...")
    
    # Essayer différentes URLs
    urls_to_test = [
        DATABASE_URL,
        DATABASE_URL.replace("db.oxxuwesviinerhmuusxz.supabase.co", "oxxuwesviinerhmuusxz.supabase.co"),
        "postgresql://postgres:b4iU4WJOAikxBqqO@oxxuwesviinerhmuusxz.supabase.co:5432/postgres"
    ]
    
    for i, url in enumerate(urls_to_test, 1):
        print(f"\n🔧 Test {i}: {url.split('@')[0]}@...")
        try:
            conn = psycopg2.connect(url, connect_timeout=10)
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            result = cursor.fetchone()
            print(f"✅ SUCCÈS: {result[0].split(',')[0]}")
            cursor.close()
            conn.close()
            return url
        except Exception as e:
            print(f"❌ ÉCHEC: {e}")
    
    return None

if __name__ == "__main__":
    working_url = test_supabase_connection()
    if working_url:
        print(f"\n🎉 URL fonctionnelle: {working_url}")
        print("\n💡 Copiez cette URL dans votre .env")
    else:
        print("\n💥 Aucune URL ne fonctionne")