# Import TOUT depuis app/schemas/ocr_nlp.py
from .ocr_nlp import (
    FileUploadRequest,
    HealthCheckResponse,
    SystemMetrics,
    OCRProcessingOptions,
    ImageProcessingOptions,
    OrderCreationRequest,
    IntegrationResponse,
    ProcessingStats,
    StandardResponse,
    ErrorResponse,  # Celui de ocr_nlp.py, pas de schemas.py
    # Ajoute les autres si nécessaire
    LanguageStats,
    IntentStats,
    ValidationError,
    ValidationErrorResponse,
    WebhookPayload,
    WebhookConfig,
    CacheItem
)

# Si tu as besoin de l'ErrorResponse de schemas.py aussi, tu peux l'importer avec un alias
from .schemas import ErrorResponse as MainErrorResponse

# Définir quel ErrorResponse utiliser
# Je recommande d'utiliser celui de ocr_nlp.py pour la compatibilité OCR
# Mais si d'autres modules utilisent celui de schemas.py, on peut faire :

__all__ = [
    # OCR/NLP schemas
    "StandardResponse",
    "ErrorResponse",  # Celui de ocr_nlp.py
    "FileUploadRequest",
    "HealthCheckResponse",
    "SystemMetrics",
    "OCRProcessingOptions",
    "ImageProcessingOptions",
    "OrderCreationRequest",
    "IntegrationResponse",
    "ProcessingStats",
    "LanguageStats",
    "IntentStats",
    "ValidationError",
    "ValidationErrorResponse",
    "WebhookPayload",
    "WebhookConfig",
    "CacheItem",
    
    # Pour compatibilité avec d'autres modules qui utilisent MainErrorResponse
    "MainErrorResponse"
]