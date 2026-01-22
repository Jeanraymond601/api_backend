# app/schemas.py - VERSION AMÉLIORÉE POUR EXTRACTION INTELLIGENTE
from pydantic import BaseModel, Field, HttpUrl, model_validator, validator, root_validator
from typing import List, Optional, Dict, Any, Union, Literal
from datetime import datetime, date
from enum import Enum
import uuid
import re

# ==============================================
# ENUMS ET CONSTANTES
# ==============================================

class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    MAINTENANCE = "maintenance"

class UploadSource(str, Enum):
    DIRECT_UPLOAD = "direct_upload"
    MESSENGER = "messenger"
    LIVE_COMMERCE = "live_commerce"
    EMAIL = "email"
    SCANNER = "scanner"
    MOBILE_APP = "mobile_app"
    WEB_FORM = "web_form"
    API = "api"
    FTP = "ftp"
    CLOUD_STORAGE = "cloud_storage"
    OTHER = "other"

class ProcessingPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    REALTIME = "realtime"

class ExtractionLevel(str, Enum):
    BASIC = "basic"  # OCR seulement
    STANDARD = "standard"  # OCR + NLP de base
    ADVANCED = "advanced"  # OCR + NLP complet + géolocalisation
    ENTERPRISE = "enterprise"  # Tout + validation + enrichissement

class OCRProvider(str, Enum):
    PADDLEOCR = "paddleocr"
    TESSERACT = "tesseract"
    GOOGLE_VISION = "google_vision"
    AZURE_COMPUTER_VISION = "azure_cv"
    AWS_TEXTRACT = "aws_textract"
    EASYOCR = "easyocr"
    HYBRID = "hybrid"

# ==============================================
# SCHÉMAS DE REQUÊTE
# ==============================================

class ImageProcessingOptions(BaseModel):
    """Options de prétraitement d'image"""
    deskew: bool = Field(True, description="Correction inclinaison")
    denoise: bool = Field(True, description="Réduction bruit")
    contrast_enhancement: bool = Field(True, description="Amélioration contraste")
    binarize: bool = Field(False, description="Binarisation noir/blanc")
    sharpen: bool = Field(False, description="Accentuation contours")
    remove_background: bool = Field(False, description="Suppression fond")
    dpi: int = Field(300, ge=72, le=1200, description="Résolution cible DPI")
    color_mode: str = Field("auto", description="auto, grayscale, color, bw")
    rotation_correction: bool = Field(True, description="Correction rotation auto")
    border_removal: bool = Field(True, description="Suppression bordures")
    
    @validator('color_mode')
    def validate_color_mode(cls, v):
        allowed = ['auto', 'grayscale', 'color', 'bw', 'inverted']
        if v not in allowed:
            raise ValueError(f'Color mode must be one of {allowed}')
        return v

class NLPExtractionOptions(BaseModel):
    """Options d'extraction NLP/IA"""
    extract_entities: bool = Field(True, description="Extraire entités nommées")
    extract_relations: bool = Field(False, description="Extraire relations")
    classify_intent: bool = Field(True, description="Classifier l'intention")
    extract_form_fields: bool = Field(True, description="Extraire champs formulaire")
    validate_data: bool = Field(True, description="Valider données extraites")
    enrich_data: bool = Field(True, description="Enrichir données (géocodage, etc.)")
    detect_language: bool = Field(True, description="Détection automatique langue")
    confidence_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Seuil confiance")
    deduplicate: bool = Field(True, description="Dédoublonner données")
    
class GeolocationOptions(BaseModel):
    """Options de géolocalisation"""
    enabled: bool = Field(True, description="Activer géolocalisation")
    provider: str = Field("nominatim", description="nominatim, google, bing, mapbox")
    cache_results: bool = Field(True, description="Mettre en cache résultats")
    fallback_providers: List[str] = Field(["openstreetmap"], description="Fallbacks")
    timeout: int = Field(10, ge=1, le=60, description="Timeout en secondes")
    language: str = Field("fr", description="Langue résultats")
    include_map_image: bool = Field(False, description="Générer image carte")
    include_reverse_geocode: bool = Field(False, description="Reverse géocoding")
    
    @validator('provider')
    def validate_provider(cls, v):
        allowed = ['nominatim', 'google', 'bing', 'mapbox', 'here', 'opencage']
        if v not in allowed:
            raise ValueError(f'Provider must be one of {allowed}')
        return v

class FileUploadRequest(BaseModel):
    """Requête d'upload de fichier"""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    file_base64: Optional[str] = Field(None, description="Fichier en base64")
    file_url: Optional[str] = Field(None, description="URL du fichier")
    filename: str
    content_type: str
    source: UploadSource = Field(UploadSource.DIRECT_UPLOAD)
    session_id: Optional[str] = Field(None, description="ID session utilisateur")
    user_id: Optional[str] = Field(None, description="ID utilisateur")
    device_info: Optional[Dict[str, str]] = Field(None, description="Infos device")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Métadonnées custom")
    callback_url: Optional[HttpUrl] = Field(None, description="URL callback")
    webhook_url: Optional[HttpUrl] = Field(None, description="URL webhook")
    priority: ProcessingPriority = Field(ProcessingPriority.NORMAL)
    extraction_level: ExtractionLevel = Field(ExtractionLevel.STANDARD)
    
    @validator('content_type')
    def validate_content_type(cls, v):
        """Valider le type MIME"""
        allowed_types = [
            'image/jpeg', 'image/jpg', 'image/png', 'image/webp',
            'image/tiff', 'image/bmp', 'image/gif',
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-excel',
            'text/plain', 'text/csv'
        ]
        
        if v not in allowed_types:
            raise ValueError(f'Content type {v} not supported')
        
        return v
    
    @model_validator(mode='after')
    def validate_file_source(self):
        """Valider qu'au moins une source de fichier est fournie"""
        if not self.file_base64 and not self.file_url:
            raise ValueError('Either file_base64 or file_url must be provided')
        
        if self.file_base64 and self.file_url:
            raise ValueError('Only one of file_base64 or file_url should be provided')
        
        return self

class OCRProcessingRequest(BaseModel):
    """Requête de traitement OCR complet"""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    upload: FileUploadRequest
    language_hint: Optional[str] = Field(None, description="fr, en, mg, etc.")
    ocr_provider: OCRProvider = Field(OCRProvider.PADDLEOCR)
    image_processing: ImageProcessingOptions = Field(default_factory=ImageProcessingOptions)
    nlp_options: NLPExtractionOptions = Field(default_factory=NLPExtractionOptions)
    geolocation_options: GeolocationOptions = Field(default_factory=GeolocationOptions)
    timeout: int = Field(60, ge=10, le=300, description="Timeout total secondes")
    store_results: bool = Field(True, description="Stocker résultats DB")
    generate_report: bool = Field(False, description="Générer rapport PDF")
    return_format: str = Field("json", description="json, xml, csv, pdf")
    validation_rules: Optional[Dict[str, Any]] = Field(None, description="Règles validation")
    enrichment_apis: Optional[List[str]] = Field(None, description="APIs d'enrichissement")
    
    @validator('return_format')
    def validate_return_format(cls, v):
        allowed = ['json', 'xml', 'csv', 'pdf', 'html', 'png']
        if v not in allowed:
            raise ValueError(f'Return format must be one of {allowed}')
        return v

class BatchOCRRequest(BaseModel):
    """Requête de traitement par lot"""
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    requests: List[OCRProcessingRequest]
    name: Optional[str] = Field(None, description="Nom du batch")
    description: Optional[str] = Field(None, description="Description")
    priority: ProcessingPriority = Field(ProcessingPriority.NORMAL)
    concurrent_workers: int = Field(4, ge=1, le=20, description="Workers parallèles")
    notify_completion: bool = Field(True, description="Notification fin traitement")
    result_aggregation: bool = Field(True, description="Agréger résultats")
    deduplicate_across_batch: bool = Field(False, description="Dédoublonner entre documents")
    output_format: str = Field("json", description="Format sortie")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Métadonnées batch")

# ==============================================
# SCHÉMAS DE RÉPONSE
# ==============================================

class StandardResponse(BaseModel):
    """Réponse API standard"""
    request_id: str = Field(..., description="ID de la requête")
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = Field(None, description="Données résultat")
    warnings: List[str] = Field(default_factory=list, description="Avertissements")
    errors: List[str] = Field(default_factory=list, description="Erreurs")
    processing_time: float = Field(..., ge=0.0, description="Temps traitement secondes")
    api_version: str = Field("2.0.0", description="Version API")
    timestamp: datetime = Field(default_factory=datetime.now)
    pagination: Optional[Dict[str, Any]] = Field(None, description="Info pagination")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ErrorResponse(BaseModel):
    """Réponse d'erreur structurée"""
    request_id: Optional[str] = Field(None, description="ID de la requête")
    error: str = Field(..., description="Type d'erreur")
    detail: str = Field(..., description="Détail erreur")
    code: str = Field(..., description="Code erreur")
    timestamp: datetime = Field(default_factory=datetime.now)
    trace_id: Optional[str] = Field(None, description="ID trace pour debugging")
    suggested_action: Optional[str] = Field(None, description="Action suggérée")
    documentation_url: Optional[HttpUrl] = Field(None, description="URL documentation")
    
    @validator('code')
    def validate_error_code(cls, v):
        """Format des codes d'erreur"""
        pattern = r'^[A-Z_]+_[0-9]{3}$'
        if not re.match(pattern, v):
            raise ValueError('Error code must be in format: PREFIX_001')
        return v

class ValidationErrorDetail(BaseModel):
    """Détail erreur validation"""
    field: str = Field(..., description="Champ en erreur")
    message: str = Field(..., description="Message erreur")
    value: Optional[Any] = Field(None, description="Valeur problématique")
    location: Optional[str] = Field(None, description="body, query, path, header")
    type: Optional[str] = Field(None, description="Type erreur: required, invalid, etc.")
    
class ValidationErrorResponse(BaseModel):
    """Réponse erreur validation"""
    request_id: Optional[str] = Field(None, description="ID de la requête")
    errors: List[ValidationErrorDetail] = Field(..., description="Liste erreurs")
    timestamp: datetime = Field(default_factory=datetime.now)
    message: str = Field("Validation failed", description="Message général")

# ==============================================
# SCHÉMAS DE SANTÉ ET MÉTRIQUES
# ==============================================

class ComponentStatus(BaseModel):
    """Statut d'un composant système"""
    name: str = Field(..., description="Nom composant")
    status: ServiceStatus = Field(..., description="Statut")
    message: Optional[str] = Field(None, description="Message détaillé")
    last_check: datetime = Field(default_factory=datetime.now)
    response_time: Optional[float] = Field(None, ge=0.0, description="Temps réponse ms")
    version: Optional[str] = Field(None, description="Version composant")
    dependencies: Optional[List[str]] = Field(None, description="Dépendances")
    
class DatabaseStatus(BaseModel):
    """Statut base de données"""
    connected: bool
    latency_ms: float
    active_connections: int
    total_connections: int
    database_size_mb: float
    last_backup: Optional[datetime]
    replication_status: Optional[str]

class CacheStatus(BaseModel):
    """Statut cache"""
    connected: bool
    hit_rate: float = Field(..., ge=0.0, le=1.0)
    total_keys: int
    memory_used_mb: float
    evictions: int
    latency_ms: float

class HealthCheckResponse(BaseModel):
    """Réponse health check complète"""
    status: ServiceStatus
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str
    environment: str = Field("production", description="production, staging, development")
    uptime_seconds: float
    components: List[ComponentStatus]
    database: Optional[DatabaseStatus] = None
    cache: Optional[CacheStatus] = None
    ocr_engine: str
    ocr_version: str
    supported_languages: List[str]
    system_info: Dict[str, Any] = Field(default_factory=dict)
    checks: Dict[str, bool] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class SystemMetrics(BaseModel):
    """Métriques système détaillées"""
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # CPU
    cpu_percent: float = Field(..., ge=0.0, le=100.0)
    cpu_count: int
    cpu_load_1min: float
    cpu_load_5min: float
    cpu_load_15min: float
    
    # Mémoire
    memory_percent: float = Field(..., ge=0.0, le=100.0)
    memory_total_gb: float
    memory_used_gb: float
    memory_available_gb: float
    
    # Disque
    disk_usage_percent: float = Field(..., ge=0.0, le=100.0)
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    
    # Réseau
    network_bytes_sent_mb: float
    network_bytes_recv_mb: float
    network_packets_sent: int
    network_packets_recv: int
    
    # Application
    active_ocr_jobs: int = Field(0, ge=0)
    queue_size: int = Field(0, ge=0)
    average_processing_time: float = Field(0.0, ge=0.0)
    active_connections: int = Field(0, ge=0)
    thread_count: int = Field(0, ge=0)
    
    # Cache
    cache_hit_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    cache_size_mb: Optional[float] = Field(None, ge=0.0)
    
    # Business
    documents_processed_today: int = Field(0, ge=0)
    successful_extractions_today: int = Field(0, ge=0)
    failed_extractions_today: int = Field(0, ge=0)
    average_confidence_today: float = Field(0.0, ge=0.0, le=1.0)

# ==============================================
# SCHÉMAS WEBHOOK ET NOTIFICATIONS
# ==============================================

class WebhookEventType(str, Enum):
    OCR_STARTED = "ocr_started"
    OCR_COMPLETED = "ocr_completed"
    OCR_FAILED = "ocr_failed"
    ORDER_EXTRACTED = "order_extracted"
    COORDINATES_EXTRACTED = "coordinates_extracted"
    GEOLOCATION_COMPLETED = "geolocation_completed"
    VALIDATION_COMPLETED = "validation_completed"
    BATCH_COMPLETED = "batch_completed"
    SYSTEM_ALERT = "system_alert"

class WebhookPayload(BaseModel):
    """Payload webhook"""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: WebhookEventType
    request_id: str
    document_id: Optional[str] = None
    batch_id: Optional[str] = None
    status: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    signature: Optional[str] = Field(None, description="Signature HMAC")
    attempts: int = Field(1, ge=1, description="Tentatives d'envoi")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class WebhookConfig(BaseModel):
    """Configuration webhook"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    url: HttpUrl
    secret: Optional[str] = Field(None, description="Clé secrète signature")
    events: List[WebhookEventType] = Field(default_factory=list)
    enabled: bool = Field(True)
    timeout: int = Field(30, ge=1, le=120, description="Timeout secondes")
    retry_attempts: int = Field(3, ge=0, le=10)
    retry_delay: int = Field(5, ge=1, description="Délai entre tentatives secondes")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers additionnels")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @validator('events')
    def validate_events(cls, v):
        if not v:
            raise ValueError('At least one event type must be specified')
        return v

class NotificationPayload(BaseModel):
    """Payload notification"""
    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = Field(..., description="email, sms, push, webhook")
    recipient: str = Field(..., description="Destinataire")
    subject: Optional[str] = Field(None, description="Sujet")
    message: str = Field(..., description="Message")
    data: Optional[Dict[str, Any]] = Field(None, description="Données additionnelles")
    priority: str = Field("normal", description="low, normal, high, urgent")
    scheduled_for: Optional[datetime] = Field(None, description="Planification")
    created_at: datetime = Field(default_factory=datetime.now)

# ==============================================
# SCHÉMAS D'INTÉGRATION
# ==============================================

class IntegrationType(str, Enum):
    CRM = "crm"
    ERP = "erp"
    ECOMMERCE = "ecommerce"
    ACCOUNTING = "accounting"
    MARKETING = "marketing"
    CUSTOM = "custom"

class IntegrationConfig(BaseModel):
    """Configuration intégration"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: IntegrationType
    name: str
    enabled: bool = Field(True)
    api_key: Optional[str] = Field(None, description="Clé API")
    api_secret: Optional[str] = Field(None, description="Secret API")
    base_url: HttpUrl
    endpoints: Dict[str, str] = Field(default_factory=dict)
    timeout: int = Field(30, ge=1, le=120)
    retry_policy: Dict[str, Any] = Field(default_factory=dict)
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    webhook_url: Optional[HttpUrl] = Field(None, description="URL webhook intégration")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class OrderCreationRequest(BaseModel):
    """Requête création commande depuis extraction"""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    integration_id: str = Field(..., description="ID intégration cible")
    client_data: Dict[str, Any]
    items: List[Dict[str, Any]]
    total_amount: Optional[float] = Field(None, ge=0.0)
    delivery_info: Optional[Dict[str, Any]] = None
    payment_info: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    source: str = Field("ocr_extraction", description="Source données")
    ocr_document_id: Optional[str] = Field(None, description="ID document OCR source")
    validation_required: bool = Field(True, description="Valider avant création")
    async_processing: bool = Field(False, description="Traitement asynchrone")
    
    @validator('items')
    def validate_items(cls, v):
        if not v:
            raise ValueError('At least one item is required')
        return v

class IntegrationResponse(BaseModel):
    """Réponse intégration"""
    request_id: str
    integration_id: str
    success: bool
    external_id: Optional[str] = Field(None, description="ID externe créé")
    message: str
    data: Optional[Dict[str, Any]] = None
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    processing_time: float = Field(..., ge=0.0)
    timestamp: datetime = Field(default_factory=datetime.now)

# ==============================================
# SCHÉMAS CACHE ET PERFORMANCE
# ==============================================

class CacheItem(BaseModel):
    """Item cache"""
    key: str
    value: Any
    ttl: int = Field(3600, ge=1, description="Time to live en secondes")
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    hits: int = Field(0, ge=0, description="Nombre d'accès")
    last_accessed: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list, description="Tags pour invalidation")
    
    @model_validator(mode='after')
    def calculate_expires_at(self):
        """Calculer la date d'expiration"""
        if self.created_at and self.ttl:
            from datetime import timedelta
            self.expires_at = self.created_at + timedelta(seconds=self.ttl)
        
        return self

class CacheStats(BaseModel):
    """Statistiques cache"""
    total_items: int
    memory_usage_mb: float
    hit_rate: float = Field(..., ge=0.0, le=1.0)
    miss_rate: float = Field(..., ge=0.0, le=1.0)
    evictions: int
    average_ttl: float
    oldest_item_age: float
    newest_item_age: float
    timestamp: datetime = Field(default_factory=datetime.now)

# ==============================================
# SCHÉMAS ANALYTIQUES ET REPORTING
# ==============================================

class ProcessingStats(BaseModel):
    """Statistiques de traitement"""
    period_start: datetime
    period_end: datetime = Field(default_factory=datetime.now)
    total_documents: int = Field(0, ge=0)
    successful_extractions: int = Field(0, ge=0)
    failed_extractions: int = Field(0, ge=0)
    average_confidence: float = Field(0.0, ge=0.0, le=1.0)
    most_common_language: Optional[str] = None
    average_processing_time: float = Field(0.0, ge=0.0)
    documents_by_type: Dict[str, int] = Field(default_factory=dict)
    documents_by_source: Dict[str, int] = Field(default_factory=dict)
    peak_processing_time: Optional[datetime] = None
    busiest_hour: Optional[int] = Field(None, ge=0, le=23)
    
    @property
    def success_rate(self) -> float:
        if self.total_documents == 0:
            return 0.0
        return self.successful_extractions / self.total_documents

class LanguageStats(BaseModel):
    """Statistiques par langue"""
    language: str
    count: int = Field(0, ge=0)
    average_confidence: float = Field(0.0, ge=0.0, le=1.0)
    average_processing_time: float = Field(0.0, ge=0.0)
    success_rate: float = Field(0.0, ge=0.0, le=1.0)
    documents_by_type: Dict[str, int] = Field(default_factory=dict)

class IntentStats(BaseModel):
    """Statistiques par intention"""
    intent: str
    count: int = Field(0, ge=0)
    average_confidence: float = Field(0.0, ge=0.0, le=1.0)
    average_items_per_order: Optional[float] = Field(None, ge=0.0)
    average_order_value: Optional[float] = Field(None, ge=0.0)
    most_common_language: Optional[str] = None
    conversion_rate: Optional[float] = Field(None, ge=0.0, le=1.0)

class GeolocationStats(BaseModel):
    """Statistiques géolocalisation"""
    period_start: datetime
    period_end: datetime
    total_addresses_found: int = Field(0, ge=0)
    addresses_geocoded: int = Field(0, ge=0)
    geocoding_success_rate: float = Field(0.0, ge=0.0, le=1.0)
    average_accuracy: float = Field(0.0, ge=0.0, le=1.0)
    cache_hit_rate: float = Field(0.0, ge=0.0, le=1.0)
    most_common_city: Optional[str] = None
    most_common_country: Optional[str] = None
    addresses_by_source: Dict[str, int] = Field(default_factory=dict)

class SystemPerformanceReport(BaseModel):
    """Rapport performance système"""
    report_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    period: str = Field(..., description="daily, weekly, monthly, custom")
    period_start: datetime
    period_end: datetime
    processing_stats: ProcessingStats
    language_stats: List[LanguageStats]
    intent_stats: List[IntentStats]
    geolocation_stats: Optional[GeolocationStats] = None
    system_metrics: List[SystemMetrics]
    recommendations: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)

# ==============================================
# SCHÉMAS DE CONFIGURATION
# ==============================================

class OCRConfiguration(BaseModel):
    """Configuration OCR globale"""
    default_language: str = Field("fr", description="Langue par défaut")
    default_provider: OCRProvider = Field(OCRProvider.PADDLEOCR)
    fallback_providers: List[OCRProvider] = Field(default_factory=list)
    timeout_seconds: int = Field(60, ge=10, le=300)
    max_file_size_mb: int = Field(50, ge=1, le=500)
    supported_formats: List[str] = Field(default_factory=list)
    image_preprocessing_enabled: bool = Field(True)
    nlp_extraction_enabled: bool = Field(True)
    geolocation_enabled: bool = Field(True)
    validation_enabled: bool = Field(True)
    caching_enabled: bool = Field(True)
    logging_level: str = Field("INFO", description="DEBUG, INFO, WARNING, ERROR")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @validator('logging_level')
    def validate_logging_level(cls, v):
        allowed = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v not in allowed:
            raise ValueError(f'Logging level must be one of {allowed}')
        return v

class APIConfiguration(BaseModel):
    """Configuration API"""
    version: str = Field("2.0.0")
    rate_limit_requests: int = Field(100, ge=1, description="Requêtes par minute")
    rate_limit_period: int = Field(60, ge=1, description="Période en secondes")
    cors_origins: List[str] = Field(["*"], description="Origines CORS autorisées")
    auth_required: bool = Field(False, description="Authentification requise?")
    api_key_required: bool = Field(True, description="Clé API requise?")
    max_batch_size: int = Field(100, ge=1, description="Taille max batch")
    webhook_timeout: int = Field(30, ge=1, description="Timeout webhook secondes")
    enable_swagger: bool = Field(True, description="Activer documentation API")
    enable_metrics: bool = Field(True, description="Activer endpoints métriques")
    maintenance_mode: bool = Field(False, description="Mode maintenance")

# ==============================================
# UTILITAIRES
# ==============================================

def generate_sample_request() -> OCRProcessingRequest:
    """Générer une requête d'exemple"""
    return OCRProcessingRequest(
        upload=FileUploadRequest(
            file_base64="base64_encoded_string_here",
            filename="carte_visite.jpg",
            content_type="image/jpeg",
            source=UploadSource.DIRECT_UPLOAD
        ),
        language_hint="fr",
        ocr_provider=OCRProvider.PADDLEOCR,
        timeout=60
    )

def generate_sample_response() -> StandardResponse:
    """Générer une réponse d'exemple"""
    return StandardResponse(
        request_id="req_123456",
        success=True,
        message="Extraction terminée avec succès",
        data={
            "document_id": "doc_789",
            "confidence": 0.92,
            "processing_time": 2.5
        },
        processing_time=2.5,
        api_version="2.0.0"
    )

# ==============================================
# EXPORTS
# ==============================================

__all__ = [
    # Enums
    'ServiceStatus', 'UploadSource', 'ProcessingPriority', 'ExtractionLevel',
    'OCRProvider', 'WebhookEventType', 'IntegrationType',
    
    # Requêtes
    'ImageProcessingOptions', 'NLPExtractionOptions', 'GeolocationOptions',
    'FileUploadRequest', 'OCRProcessingRequest', 'BatchOCRRequest',
    
    # Réponses
    'StandardResponse', 'ErrorResponse', 'ValidationErrorResponse',
    'ValidationErrorDetail',
    
    # Santé et métriques
    'ComponentStatus', 'DatabaseStatus', 'CacheStatus',
    'HealthCheckResponse', 'SystemMetrics',
    
    # Webhooks et notifications
    'WebhookPayload', 'WebhookConfig', 'NotificationPayload',
    
    # Intégrations
    'IntegrationConfig', 'OrderCreationRequest', 'IntegrationResponse',
    
    # Cache
    'CacheItem', 'CacheStats',
    
    # Analytiques
    'ProcessingStats', 'LanguageStats', 'IntentStats', 'GeolocationStats',
    'SystemPerformanceReport',
    
    # Configuration
    'OCRConfiguration', 'APIConfiguration',
    
    # Utilitaires
    'generate_sample_request', 'generate_sample_response'
]