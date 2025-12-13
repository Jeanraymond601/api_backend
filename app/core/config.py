from pydantic_settings import BaseSettings
from typing import Optional, List
import json

class Settings(BaseSettings):
    # Database
    DATABASE_URL: Optional[str] = None
    
    # JWT Authentication
    SECRET_KEY: str 
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 jours
    
    # SMTP Configuration
    SMTP_HOST: Optional[str] = "smtp.gmail.com"
    SMTP_PORT: Optional[int] = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: Optional[str] = None
    FROM_NAME: Optional[str] = "Live Commerce"
    DISABLE_EMAIL_SENDING: Optional[bool] = False
    
    # SendGrid (optionnel)
    SENDGRID_API_KEY: Optional[str] = None
    
    # Geocoding
    GEOCODING_PROVIDER: Optional[str] = "openstreetmap"
    USER_AGENT: Optional[str] = "LiveCommerceApp/1.0"
    
    # ==================== CONFIGURATION FACEBOOK COMPLÈTE ====================
    # Facebook Integration
    FACEBOOK_APP_ID: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    FACEBOOK_REDIRECT_URI: Optional[str] = "http://localhost:8000/api/v1/facebook/callback"
    FACEBOOK_API_VERSION: Optional[str] = "v18.0"
    
    # ⭐ NOUVEAU : Webhook Facebook
    FACEBOOK_WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    FACEBOOK_WEBHOOK_URL: Optional[str] = "http://localhost:8000/api/v1/facebook/webhook"
    # ==========================================================================
    
    # ⭐ AJOUTE CETTE LIGNE :
    APP_URL: Optional[str] = "http://localhost:8000"  # ← AJOUTÉ ICI
    
    # Application
    ENV: Optional[str] = "development"
    PROJECT_NAME: Optional[str] = "Live Commerce API"
    API_V1_STR: Optional[str] = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000", "https://clever-dolphin-d2a83e.netlify.app"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"
        
        @classmethod
        def parse_cors_origins(cls, v):
            if isinstance(v, str):
                if v.startswith("["):
                    return json.loads(v)
                return [origin.strip() for origin in v.split(",")]
            return v

# ⭐⭐⭐ AJOUTE CETTE LIGNE À LA FIN DU FICHIER ⭐⭐⭐
settings = Settings()

# Garde le code de test si tu veux
if __name__ == "__main__":
    print("✅ Configuration chargée avec succès!")
    print("="*50)
    
    print("Database URL:", settings.DATABASE_URL)
    print("JWT Secret:", settings.SECRET_KEY[:10] + "..." if settings.SECRET_KEY else "NON DÉFINI")
    
    # ========== CONFIGURATION FACEBOOK COMPLÈTE ==========
    print("\n📱 Facebook Configuration:")
    print("  FACEBOOK_APP_ID:", settings.FACEBOOK_APP_ID or "❌ NON DÉFINI")
    print("  FACEBOOK_APP_SECRET:", "✅ DÉFINI" if settings.FACEBOOK_APP_SECRET else "❌ NON DÉFINI")
    print("  FACEBOOK_REDIRECT_URI:", settings.FACEBOOK_REDIRECT_URI)
    print("  FACEBOOK_API_VERSION:", settings.FACEBOOK_API_VERSION)
    
    # ⭐ NOUVEAU : Webhook Facebook
    print("\n🔗 Facebook Webhook:")
    print("  FACEBOOK_WEBHOOK_VERIFY_TOKEN:", "✅ DÉFINI" if settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN else "❌ NON DÉFINI")
    print("  FACEBOOK_WEBHOOK_URL:", settings.FACEBOOK_WEBHOOK_URL)
    # ====================================================
    
    print("\n📧 Email:")
    print("  SMTP Host:", settings.SMTP_HOST)
    print("  SMTP Username:", settings.SMTP_USERNAME or "NON DÉFINI")
    
    print("\n🌍 Geocoding:")
    print("  Provider:", settings.GEOCODING_PROVIDER)
    print("  User Agent:", settings.USER_AGENT)
    
    print("\n🌐 CORS Origins:")
    for origin in settings.BACKEND_CORS_ORIGINS:
        print(f"  - {origin}")
    
    print("\n⚙️ Application:")
    print("  Environment:", settings.ENV)
    print("  APP_URL:", settings.APP_URL)  # ⭐ NOUVEAU
    
    print("\n" + "="*50)
    
    # Vérification des variables critiques
    errors = []
    warnings = []
    
    if not settings.DATABASE_URL:
        errors.append("❌ DATABASE_URL non définie")
    if not settings.SECRET_KEY:
        errors.append("❌ SECRET_KEY non définie")
    if not settings.FACEBOOK_APP_ID:
        warnings.append("⚠️  FACEBOOK_APP_ID non définie (Facebook inactif)")
    if not settings.FACEBOOK_APP_SECRET:
        warnings.append("⚠️  FACEBOOK_APP_SECRET non définie (Facebook inactif)")
    
    # ⭐ NOUVEAU : Warning pour webhook
    if not settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN:
        warnings.append("⚠️  FACEBOOK_WEBHOOK_VERIFY_TOKEN non définie (Webhook vulnérable)")
    else:
        if settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN == "LiveCommerceSecretToken2024!":
            warnings.append("⚠️  Utilise le token webhook par défaut - Change-le en production!")
    
    if warnings:
        print("\n⚠️  AVERTISSEMENTS:")
        for warning in warnings:
            print(f"  {warning}")
    
    if errors:
        print("\n❌ ERREURS CRITIQUES:")
        for error in errors:
            print(f"  {error}")
        print("\nL'application ne fonctionnera pas correctement.")
    
    print("\n" + "="*50)