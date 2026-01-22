# app/schemas/__init__.py - CORRIGÉ

# Import TOUT depuis app/schemas.py (où les classes sont réellement définies)
from .ocr_nlp import (
    FileUploadRequest,
    HealthCheckResponse,
    SystemMetrics,
    ImageProcessingOptions,
    OrderCreationRequest,
    IntegrationResponse,
    ProcessingStats,
    StandardResponse,
    ErrorResponse,  # Celui de schemas.py
    LanguageStats,
    IntentStats,
    ValidationErrorDetail,  # Note: C'est ValidationErrorDetail, pas ValidationError
    ValidationErrorResponse,
    WebhookPayload,
    WebhookConfig,
    CacheItem,
    # Ajoute toutes les autres classes dont tu as besoin
)

# Crée un alias pour compatibilité
OCRProcessingOptions = ImageProcessingOptions

# Crée un alias si ValidationError est utilisé au lieu de ValidationErrorDetail
ValidationError = ValidationErrorDetail

__all__ = [
    # OCR/NLP schemas
    "StandardResponse",
    "ErrorResponse",
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
    "ValidationError",  # L'alias
    "ValidationErrorResponse",
    "WebhookPayload",
    "WebhookConfig",
    "CacheItem",
]