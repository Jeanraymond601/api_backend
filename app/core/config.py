# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional, List
import os
import json
from pydantic import field_validator

class Settings(BaseSettings):
    # ======================================================
    # ENVIRONNEMENT
    # ======================================================
    ENV: str = "production"

    # ======================================================
    # RÉSEAU (LOCAL + NGROK)
    # ======================================================
    LOCAL_IP: str = "192.168.137.13"
    LOCAL_PORT: int = 8000
    FLUTTER_PORT: int = 3000

    # 👉 URL PUBLIQUE NGROK
    PUBLIC_URL: Optional[str] = None

    # ======================================================
    # FRONTEND
    # ======================================================
    FRONTEND_URL: Optional[str] = None

    # ======================================================
    # URLS DYNAMIQUES
    # ======================================================
    @property
    def APP_URL(self) -> str:
        if self.PUBLIC_URL:
            return self.PUBLIC_URL.rstrip("/")
        return f"http://{self.LOCAL_IP}:{self.LOCAL_PORT}"

    @property
    def FLUTTER_URL(self) -> str:
        return f"http://{self.LOCAL_IP}:{self.FLUTTER_PORT}"

    API_V1_STR: str = "/api/v1"

    # ======================================================
    # BASE DE DONNÉES
    # ======================================================
    DATABASE_URL: Optional[str] = None

    # ======================================================
    # AUTH / JWT
    # ======================================================
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ======================================================
    # EMAIL
    # ======================================================
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: str = "noreply@livecommerce.com"
    FROM_NAME: str = "Live Commerce"
    DISABLE_EMAIL_SENDING: bool = False
    SENDGRID_API_KEY: Optional[str] = None

    # ======================================================
    # GEOCODING
    # ======================================================
    GEOCODING_PROVIDER: str = "openstreetmap"
    USER_AGENT: str = "LiveCommerceApp/1.0"
    GEOCODING_CACHE_TTL: int = 86400

    # ======================================================
    # OCR / NLP - Variables qui peuvent venir du .env
    # ======================================================
    OCR_ENGINE: str = "paddleocr"
    TESSERACT_PATH: Optional[str] = None
    
    # Ces variables acceptent soit du JSON, soit du CSV
    PADDLE_OCR_LANGS: Optional[str] = None
    TESSERACT_LANGS: Optional[str] = None
    ALLOWED_IMAGE_TYPES: Optional[str] = None
    ALLOWED_DOC_TYPES: Optional[str] = None
    CORS_ORIGINS: Optional[str] = None

    OCR_UPLOAD_DIR: str = "./ocr_uploads"
    OCR_TEMP_DIR: str = "./ocr_temp"
    OCR_MAX_FILE_SIZE: int = 20971520
    OCR_CLEANUP_INTERVAL: int = 3600
    OCR_TIMEOUT: int = 30
    MAX_CONCURRENT_OCR: int = 3
    OCR_CACHE_TTL: int = 3600
    OCR_USE_GPU: bool = False
    OCR_SERVICE_PREFIX: str = "/api/v1/ocr"
    OCR_DEBUG: bool = True
    OCR_LOG_LEVEL: str = "INFO"

    # ======================================================
    # PROPRIÉTÉS CALCULÉES
    # ======================================================
    @property
    def order_service_url(self) -> str:
        return f"{self.APP_URL}{self.API_V1_STR}/orders"

    @property
    def paddle_ocr_langs_list(self) -> List[str]:
        """Parse PADDLE_OCR_LANGS en liste"""
        if not self.PADDLE_OCR_LANGS:
            return ["fr", "en", "mg"]
        return self._parse_string_to_list(self.PADDLE_OCR_LANGS)

    @property
    def tesseract_langs_list(self) -> List[str]:
        """Parse TESSERACT_LANGS en liste"""
        if not self.TESSERACT_LANGS:
            return ["fra", "eng", "mg"]
        return self._parse_string_to_list(self.TESSERACT_LANGS)

    @property
    def allowed_image_types_list(self) -> List[str]:
        """Parse ALLOWED_IMAGE_TYPES en liste"""
        if not self.ALLOWED_IMAGE_TYPES:
            return [
                "image/jpeg", "image/png", "image/jpg", 
                "image/webp", "image/bmp", "image/tiff"
            ]
        return self._parse_string_to_list(self.ALLOWED_IMAGE_TYPES)

    @property
    def allowed_doc_types_list(self) -> List[str]:
        """Parse ALLOWED_DOC_TYPES en liste"""
        if not self.ALLOWED_DOC_TYPES:
            return [
                "application/pdf",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.ms-word",
                "application/octet-stream",
                "application/zip",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
            ]
        return self._parse_string_to_list(self.ALLOWED_DOC_TYPES)

    @property
    def backend_cors_origins(self) -> List[str]:
        """Liste des origines CORS"""
        default_origins = [
            "http://localhost:3000",
            "http://localhost:8000",
            f"http://{self.LOCAL_IP}",
            f"http://{self.LOCAL_IP}:{self.FLUTTER_PORT}",
            f"http://{self.LOCAL_IP}:{self.LOCAL_PORT}",
            self.FLUTTER_URL,
            self.APP_URL,
        ]

        if self.FRONTEND_URL:
            default_origins.append(self.FRONTEND_URL)
            
        if self.PUBLIC_URL:
            default_origins.append(self.PUBLIC_URL)

        # Ajouter les origines du .env si définies
        if self.CORS_ORIGINS:
            env_origins = self._parse_string_to_list(self.CORS_ORIGINS)
            default_origins.extend(env_origins)

        # suppression doublons
        return list(dict.fromkeys(default_origins))

    # ======================================================
    # NLP - patterns statiques
    # ======================================================
    @property
    def ner_phone_patterns(self) -> List[str]:
        return [
            r'\b(?:0|\+261)[-\s]?[2-9][-\s]?[0-9]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{2}\b',
            r'\b03[2-9][-\s]?[0-9]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{2}[-\s]?[0-9]{2}\b'
        ]
    
    NER_EMAIL_PATTERN: str = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    NER_PRICE_PATTERN: str = r'\b\d+[\s,.]?\d*\s*(?:Ar|MGA|€|\$|EUR|USD)\b'

    # ======================================================
    # FACEBOOK
    # ======================================================
    FACEBOOK_APP_ID: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    FACEBOOK_API_VERSION: str = "v18.0"
    FACEBOOK_WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    FACEBOOK_WEBHOOK_SECRET: Optional[str] = None
    FACEBOOK_SCOPES: str = "pages_show_list,pages_read_engagement,pages_manage_metadata,pages_manage_posts,pages_manage_engagement,public_profile,email,pages_read_user_content,business_management,pages_messaging"

    @property
    def FACEBOOK_APP_REDIRECT_URI(self) -> str:
        return f"{self.APP_URL}{self.API_V1_STR}/facebook/callback"

    @property
    def FACEBOOK_WEBHOOK_URL(self) -> str:
        return f"{self.APP_URL}{self.API_V1_STR}/facebook/webhook"

    # ======================================================
    # APPLICATION
    # ======================================================
    APP_NAME: str = "LiveCommerce"
    PROJECT_NAME: str = "Live Commerce API"

    # ======================================================
    # MÉTHODES UTILITAIRES
    # ======================================================
    def _parse_string_to_list(self, value: str) -> List[str]:
        """Parse une string (JSON ou CSV) en liste"""
        if not value:
            return []
        
        # Essayer de parser comme JSON
        if value.startswith("[") and value.endswith("]"):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # Sinon, split par virgules
        return [item.strip() for item in value.split(",") if item.strip()]

    # ======================================================
    # CONFIG PYDANTIC
    # ======================================================
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignorer les champs supplémentaires


# ======================================================
# INSTANCE
# ======================================================
settings = Settings()

# ======================================================
# POST INIT
# ======================================================
# OCR folders
for d in [settings.OCR_UPLOAD_DIR, settings.OCR_TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

# Tesseract
if settings.TESSERACT_PATH and os.path.exists(settings.TESSERACT_PATH):
    os.environ["TESSDATA_PREFIX"] = os.path.dirname(settings.TESSERACT_PATH)


# ======================================================
# TEST
# ======================================================
if __name__ == "__main__":
    print("=" * 60)
    print("✅ CONFIGURATION CHARGÉE AVEC SUCCÈS")
    print("=" * 60)
    
    print(f"📱 ENVIRONNEMENT: {settings.ENV}")
    print(f"🌐 APP_URL: {settings.APP_URL}")
    print(f"📱 FLUTTER_URL: {settings.FLUTTER_URL}")
    print(f"🖥️  FRONTEND_URL: {settings.FRONTEND_URL}")
    print(f"📦 DATABASE_URL: {'✅' if settings.DATABASE_URL else '❌'}")
    print(f"🔐 SECRET_KEY: {'✅' if settings.SECRET_KEY else '❌'}")
    print(f"📱 FACEBOOK APP ID: {'✅' if settings.FACEBOOK_APP_ID else '❌'}")
    print(f"📧 EMAIL SMTP: {'✅' if settings.SMTP_USERNAME else '❌'}")
    print(f"🤖 OCR ENGINE: {settings.OCR_ENGINE}")
    
    print(f"\n📋 PADDLE_OCR_LANGS: {settings.paddle_ocr_langs_list}")
    print(f"📋 ALLOWED_IMAGE_TYPES: {len(settings.allowed_image_types_list)} types")
    print(f"📋 CORS ORIGINS: {len(settings.backend_cors_origins)} origines")
    
    print(f"\n🔄 FACEBOOK CALLBACK: {settings.FACEBOOK_APP_REDIRECT_URI}")
    print(f"🔄 FACEBOOK WEBHOOK: {settings.FACEBOOK_WEBHOOK_URL}")
    
    print(f"\n🛡️  CORS ORIGINES ({len(settings.backend_cors_origins)}):")
    for origin in settings.backend_cors_origins[:5]:
        print(f"  ✓ {origin}")
    if len(settings.backend_cors_origins) > 5:
        print(f"  ... et {len(settings.backend_cors_origins)-5} autres")
    
    print("\n" + "=" * 60)
    
    # Vérifications
    errors = []
    if not settings.DATABASE_URL:
        errors.append("❌ DATABASE_URL manquant")
    if not settings.SECRET_KEY:
        errors.append("❌ SECRET_KEY manquant")
    
    if errors:
        print("⚠️  ERREURS DE CONFIGURATION:")
        for error in errors:
            print(f"  {error}")
    else:
        print("🎯 CONFIGURATION PRÊTE POUR LA PRODUCTION!")
        print(f"🔗 URL à utiliser: {settings.APP_URL}")
    
    print("=" * 60)