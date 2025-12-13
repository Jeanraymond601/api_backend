import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

def test_both_urls():
    password = "b4iU4WJOAikxBqqO"  # Votre mot de passe
    
    urls = [
        # URL avec "db." (celle que Supabase vous donne)
        f"postgresql://postgres:{password}@db.oxxuwesviinerhmuusxz.supabase.co:5432/postgres",
        
        # URL sans "db." (celle que vous utilisez en frontend)
        f"postgresql://postgres:{password}@oxxuwesviinerhmuusxz.supabase.co:5432/postgres"
    ]
    
    descriptions = [
        "Avec 'db.' (URL Supabase)",
        "Sans 'db.' (URL Frontend)"
    ]
    
    for i, (url, desc) in enumerate(zip(urls, descriptions), 1):
        print(f"\n🧪 Test {i}: {desc}")
        print(f"🔗 URL: {url.split('@')[0]}@...")
        
        try:
            conn = psycopg2.connect(url, connect_timeout=10)
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            print(f"✅ SUCCÈS: {version.split(',')[0]}")
            cursor.close()
            conn.close()
            return url, desc
        except Exception as e:
            print(f"❌ ÉCHEC: {e}")
    
    return None, None

if __name__ == "__main__":
    working_url, description = test_both_urls()
    if working_url:
        print(f"\n🎉 URL fonctionnelle: {description}")
        print(f"💡 Utilisez cette URL dans votre .env")
        
        # Afficher l'URL masquée
        masked_url = working_url.split('@')[0] + "@..."
        print(f"🔧 URL: {masked_url}")
    else:
        print("\n💥 Aucune URL ne fonctionne")
        print("🔧 Vérifiez:")
        print("   - Votre mot de passe")
        print("   - Votre connexion Internet")
        print("   - Les paramètres réseau/firewall")