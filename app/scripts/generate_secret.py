# scripts/generate_secret.py
import secrets
import base64

def generate_secret_key():
    # Génère une clé de 32 bytes (256 bits) pour HS256
    secret_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    print(f"🔑 Votre nouvelle clé secrète :")
    print(f"SECRET_KEY={secret_key}")
    
if __name__ == "__main__":
    generate_secret_key()