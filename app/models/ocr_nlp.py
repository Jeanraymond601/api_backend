# app/models.py - VERSION AMÉLIORÉE AVEC GÉOLOCALISATION
from pydantic import BaseModel, Field, model_validator, validator
from typing import List, Optional, Dict, Any, Union, Tuple
from enum import Enum
from datetime import datetime, date
import re
import uuid
from decimal import Decimal

class DocumentType(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    DOCX = "docx"
    EXCEL = "excel"
    TXT = "txt"
    UNKNOWN = "unknown"

class FileFormat(str, Enum):
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    BMP = "bmp"
    GIF = "gif"
    TIFF = "tiff"
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    XLS = "xls"
    XLSX = "xlsx"
    CSV = "csv"
    TXT = "txt"

class Language(str, Enum):
    FR = "fr"
    EN = "en"
    MG = "mg"
    DE = "de"
    ES = "es"
    IT = "it"
    UNKNOWN = "unknown"

class IntentType(str, Enum):
    ORDER = "ORDER"
    INVOICE = "INVOICE"
    QUOTATION = "QUOTATION"
    CONTACT = "CONTACT"
    IDENTITY = "IDENTITY"
    FORM = "FORM"
    OTHER = "OTHER"

class ExtractionSource(str, Enum):
    OCR = "ocr"
    NLP = "nlp"
    FORM_PARSER = "form_parser"
    REGEX = "regex"
    MANUAL = "manual"

class GeoCoordinates(BaseModel):
    """Coordonnées GPS avec validation"""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude entre -90 et 90")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude entre -180 et 180")
    altitude: Optional[float] = Field(None, description="Altitude en mètres")
    accuracy: Optional[float] = Field(None, ge=0.0, description="Précision en mètres")
    source: ExtractionSource = Field(ExtractionSource.OCR, description="Source des coordonnées")
    confidence: float = Field(0.9, ge=0.0, le=1.0, description="Confiance de la géolocalisation")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    @validator('latitude', 'longitude')
    def round_coordinates(cls, v):
        """Arrondir les coordonnées à 6 décimales"""
        return round(v, 6)
    
    @property
    def google_maps_url(self) -> str:
        """URL Google Maps"""
        return f"https://www.google.com/maps?q={self.latitude},{self.longitude}"
    
    @property
    def openstreetmap_url(self) -> str:
        """URL OpenStreetMap"""
        return f"https://www.openstreetmap.org/?mlat={self.latitude}&mlon={self.longitude}"

class Address(BaseModel):
    """Adresse complète avec géolocalisation"""
    street: Optional[str] = Field(None, description="Rue et numéro")
    complement: Optional[str] = Field(None, description="Complément d'adresse")
    city: Optional[str] = Field(None, description="Ville")
    district: Optional[str] = Field(None, description="Arrondissement/Quartier")
    region: Optional[str] = Field(None, description="Région/Département")
    postal_code: Optional[str] = Field(None, description="Code postal")
    country: Optional[str] = Field("France", description="Pays")
    formatted_address: Optional[str] = Field(None, description="Adresse formatée complète")
    coordinates: Optional[GeoCoordinates] = Field(None, description="Coordonnées GPS")
    is_commercial: Optional[bool] = Field(None, description="Adresse commerciale?")
    is_residential: Optional[bool] = Field(None, description="Adresse résidentielle?")
    
    @validator('city', 'district', 'region', 'country')
    def capitalize_names(cls, v):
        if v:
            return v.title()
        return v
    
    @validator('postal_code')
    def validate_postal_code(cls, v):
        if v:
            # Nettoyer le code postal
            v = re.sub(r'[^\d]', '', v)
            # Validation basique
            if len(v) not in [4, 5, 6]:
                raise ValueError('Invalid postal code length')
        return v
    
    @property
    def full_address(self) -> str:
        """Adresse formatée complète"""
        if self.formatted_address:
            return self.formatted_address
        
        parts = []
        if self.street:
            parts.append(self.street)
        if self.complement:
            parts.append(self.complement)
        if self.postal_code:
            parts.append(self.postal_code)
        if self.city:
            if self.postal_code:
                parts[-1] = f"{self.postal_code} {self.city}"
            else:
                parts.append(self.city)
        if self.country and self.country != "France":
            parts.append(self.country)
        
        return ", ".join(filter(None, parts))

class ContactPoint(BaseModel):
    """Point de contact"""
    type: str = Field(..., description="phone, email, fax, mobile, etc.")
    value: str = Field(..., description="Valeur du contact")
    is_primary: bool = Field(False, description="Contact principal?")
    country_code: Optional[str] = Field(None, description="Code pays")
    label: Optional[str] = Field(None, description="Label personnalisé")
    source: ExtractionSource = Field(ExtractionSource.OCR, description="Source d'extraction")
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    
    @validator('type')
    def validate_type(cls, v):
        allowed = ['phone', 'mobile', 'email', 'fax', 'website', 'social', 'other']
        if v not in allowed:
            raise ValueError(f'Type must be one of {allowed}')
        return v
    
    @validator('value')
    def normalize_value(cls, v, values):
        if 'type' in values:
            if values['type'] in ['phone', 'mobile', 'fax']:
                # Normalisation téléphone
                v = re.sub(r'[^\d+]', '', v)
                if v.startswith('0'):
                    v = '+33' + v[1:]  # France par défaut
                elif v.startswith('261'):
                    v = '+' + v  # Madagascar
            elif values['type'] == 'email':
                v = v.lower().strip()
            elif values['type'] == 'website':
                if not v.startswith(('http://', 'https://')):
                    v = 'https://' + v
        return v

class CompanyInfo(BaseModel):
    """Informations entreprise"""
    name: Optional[str] = Field(None, description="Nom de l'entreprise")
    legal_name: Optional[str] = Field(None, description="Nom légal")
    siret: Optional[str] = Field(None, description="SIRET")
    siren: Optional[str] = Field(None, description="SIREN")
    vat_number: Optional[str] = Field(None, description="Numéro TVA")
    activity_code: Optional[str] = Field(None, description="Code APE/NAF")
    legal_form: Optional[str] = Field(None, description="Forme juridique")
    capital: Optional[float] = Field(None, description="Capital social")
    registration_date: Optional[date] = Field(None, description="Date d'immatriculation")
    
    @validator('siret', 'siren')
    def validate_siret_siren(cls, v):
        if v:
            v = re.sub(r'[^\d]', '', v)
            if len(v) not in [9, 14]:
                raise ValueError('Invalid SIREN/SIRET length')
        return v

class ClientInfo(BaseModel):
    """Informations client enrichies"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    first_name: Optional[str] = Field(None, description="Prénom")
    last_name: Optional[str] = Field(None, description="Nom")
    full_name: Optional[str] = Field(None, description="Nom complet")
    title: Optional[str] = Field(None, description="Civilité (M., Mme, Mlle)")
    job_title: Optional[str] = Field(None, description="Fonction")
    company: Optional[CompanyInfo] = Field(None, description="Informations entreprise")
    contacts: List[ContactPoint] = Field(default_factory=list, description="Liste des contacts")
    addresses: List[Address] = Field(default_factory=list, description="Liste des adresses")
    birth_date: Optional[date] = Field(None, description="Date de naissance")
    customer_since: Optional[date] = Field(None, description="Client depuis")
    customer_id: Optional[str] = Field(None, description="Numéro client")
    segmentation: Optional[str] = Field(None, description="Segment client")
    notes: Optional[str] = Field(None, description="Notes supplémentaires")
    extraction_confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confiance d'extraction")
    last_updated: datetime = Field(default_factory=datetime.now)
    
    @validator('first_name', 'last_name', 'full_name')
    def capitalize_name(cls, v):
        if v:
            return v.title()
        return v
    
    @validator('contacts')
    def deduplicate_contacts(cls, v):
        """Dédoublonner les contacts"""
        seen = set()
        deduped = []
        for contact in v:
            key = (contact.type, contact.value)
            if key not in seen:
                seen.add(key)
                deduped.append(contact)
        return deduped
    
    @property
    def primary_email(self) -> Optional[str]:
        """Email principal"""
        for contact in self.contacts:
            if contact.type == 'email' and contact.is_primary:
                return contact.value
        for contact in self.contacts:
            if contact.type == 'email':
                return contact.value
        return None
    
    @property
    def primary_phone(self) -> Optional[str]:
        """Téléphone principal"""
        for contact in self.contacts:
            if contact.type in ['phone', 'mobile'] and contact.is_primary:
                return contact.value
        for contact in self.contacts:
            if contact.type in ['phone', 'mobile']:
                return contact.value
        return None
    
    @property
    def primary_address(self) -> Optional[Address]:
        """Adresse principale"""
        return self.addresses[0] if self.addresses else None

class OrderItem(BaseModel):
    """Article de commande"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    product_code: Optional[str] = Field(None, description="Code produit")
    product: str = Field(..., description="Nom du produit")
    description: Optional[str] = Field(None, description="Description détaillée")
    category: Optional[str] = Field(None, description="Catégorie produit")
    brand: Optional[str] = Field(None, description="Marque")
    quantity: float = Field(1.0, ge=0.0, description="Quantité (peut être décimal)")
    unit: Optional[str] = Field("unit", description="Unité (kg, L, unité, etc.)")
    unit_price: Optional[float] = Field(None, ge=0.0, description="Prix unitaire")
    discount_rate: Optional[float] = Field(0.0, ge=0.0, le=1.0, description="Taux remise")
    tax_rate: Optional[float] = Field(0.0, ge=0.0, le=1.0, description="Taux TVA")
    total_before_tax: Optional[float] = Field(None, ge=0.0, description="Total HT")
    total_tax: Optional[float] = Field(None, ge=0.0, description="Montant TVA")
    total_price: Optional[float] = Field(None, ge=0.0, description="Total TTC")
    stock_reference: Optional[str] = Field(None, description="Référence stock")
    weight: Optional[float] = Field(None, ge=0.0, description="Poids en kg")
    dimensions: Optional[Dict[str, float]] = Field(None, description="Dimensions")
    notes: Optional[str] = Field(None, description="Notes sur l'article")
    
    @validator('quantity', pre=True)
    def parse_quantity(cls, v):
        """Parser la quantité depuis différents formats"""
        if v is None:
            return 1.0
        
        if isinstance(v, str):
            # Supprimer les espaces
            v = v.strip()
            # Remplacer les virgules par des points
            v = v.replace(',', '.')
            # Extraire les nombres
            numbers = re.findall(r'[\d.]+', v)
            if numbers:
                try:
                    return float(numbers[0])
                except:
                    return 1.0
            return 1.0
        
        try:
            return float(v)
        except (ValueError, TypeError):
            return 1.0
    
    @model_validator(mode='after')
    def calculate_totals(self):
        if self.order_items:
            subtotal = sum(item.total_before_tax or 0 for item in self.order_items)
            total_tax = sum(item.total_tax or 0 for item in self.order_items)
            total_amount = sum(item.total_price or 0 for item in self.order_items)
        
            self.subtotal = round(subtotal, 2)
            self.total_tax = round(total_tax, 2)
            self.total_amount = round(total_amount, 2)
    
        return self

class DeliveryInfo(BaseModel):
    """Informations livraison"""
    mode: Optional[str] = Field(None, description="home, pickup, express, etc.")
    carrier: Optional[str] = Field(None, description="Transporteur")
    tracking_number: Optional[str] = Field(None, description="Numéro de suivi")
    estimated_date: Optional[date] = Field(None, description="Date estimée")
    confirmed_date: Optional[date] = Field(None, description="Date confirmée")
    delivered_date: Optional[date] = Field(None, description="Date livraison")
    cost: Optional[float] = Field(None, ge=0.0, description="Coût livraison")
    weight: Optional[float] = Field(None, ge=0.0, description="Poids total")
    dimensions: Optional[Dict[str, float]] = Field(None, description="Dimensions colis")
    insurance: Optional[bool] = Field(False, description="Assuré?")
    address: Optional[Address] = Field(None, description="Adresse livraison")
    instructions: Optional[str] = Field(None, description="Instructions spéciales")
    
    @validator('mode')
    def validate_mode(cls, v):
        if v and v not in ['home', 'pickup', 'express', 'standard', 'urgent', 'other']:
            raise ValueError('Invalid delivery mode')
        return v

class PaymentInfo(BaseModel):
    """Informations paiement"""
    mode: Optional[str] = Field(None, description="cash, card, transfer, mobile, check")
    status: Optional[str] = Field(None, description="pending, paid, partial, cancelled")
    amount: Optional[float] = Field(None, ge=0.0, description="Montant payé")
    due_date: Optional[date] = Field(None, description="Date échéance")
    paid_date: Optional[date] = Field(None, description="Date paiement")
    reference: Optional[str] = Field(None, description="Référence paiement")
    bank_details: Optional[Dict[str, str]] = Field(None, description="Coordonnées bancaires")
    terms: Optional[str] = Field(None, description="Conditions paiement")
    
    @validator('mode')
    def validate_mode(cls, v):
        if v and v not in ['cash', 'card', 'transfer', 'mobile', 'check', 'paypal', 'other']:
            raise ValueError('Invalid payment mode')
        return v
    
    @validator('status')
    def validate_status(cls, v):
        if v and v not in ['pending', 'paid', 'partial', 'cancelled', 'refunded']:
            raise ValueError('Invalid payment status')
        return v

class DocumentMetadata(BaseModel):
    """Métadonnées document"""
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    filename: str
    original_filename: Optional[str] = None
    file_size: int = Field(..., ge=0, description="Taille en octets")
    mime_type: str
    document_type: DocumentType
    file_format: Optional[FileFormat] = None
    pages: Optional[int] = Field(None, ge=1, description="Nombre de pages")
    dimensions: Optional[Dict[str, int]] = Field(None, description="Dimensions (px, mm)")
    resolution: Optional[Dict[str, int]] = Field(None, description="Résolution DPI")
    color_mode: Optional[str] = Field(None, description="RGB, Grayscale, BW")
    created_date: Optional[datetime] = Field(None, description="Date création fichier")
    modified_date: Optional[datetime] = Field(None, description="Date modification")
    upload_date: datetime = Field(default_factory=datetime.now)
    upload_source: Optional[str] = Field(None, description="Web, Mobile, Email, Scanner")
    checksum: Optional[str] = Field(None, description="Hash MD5/SHA du fichier")
    storage_path: Optional[str] = Field(None, description="Chemin stockage")
    
    @validator('file_size')
    def validate_file_size(cls, v):
        max_size = 100 * 1024 * 1024  # 100 MB
        if v > max_size:
            raise ValueError(f'File size exceeds maximum {max_size} bytes')
        return v

class ExtractionResult(BaseModel):
    """Résultat extraction OCR"""
    text: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    language: Language
    raw_text: Optional[str] = None
    page_count: int = Field(1, ge=1)
    page_details: List[Dict[str, Any]] = Field(default_factory=list)
    processing_time: float = Field(..., ge=0.0)
    ocr_engine: Optional[str] = Field(None, description="Tesseract, PaddleOCR, etc.")
    engine_version: Optional[str] = None
    preprocessing_applied: List[str] = Field(default_factory=list)
    text_blocks: Optional[List[Dict[str, Any]]] = Field(None, description="Blocs texte positionnés")
    
    @validator('confidence')
    def round_confidence(cls, v):
        return round(v, 3)

class NLPResult(BaseModel):
    """Résultat extraction NLP/IA"""
    intent: IntentType
    intent_confidence: float = Field(..., ge=0.0, le=1.0)
    document_category: Optional[str] = Field(None, description="Facture, Devis, Contrat, etc.")
    document_number: Optional[str] = Field(None, description="Numéro document")
    document_date: Optional[date] = Field(None, description="Date document")
    due_date: Optional[date] = Field(None, description="Date échéance")
    client: Optional[ClientInfo] = None
    seller: Optional[ClientInfo] = Field(None, description="Informations vendeur")
    order_items: List[OrderItem] = Field(default_factory=list)
    delivery: Optional[DeliveryInfo] = None
    payment: Optional[PaymentInfo] = None
    subtotal: Optional[float] = Field(None, ge=0.0, description="Sous-total HT")
    total_tax: Optional[float] = Field(None, ge=0.0, description="Total TVA")
    total_amount: Optional[float] = Field(None, ge=0.0, description="Total TTC")
    currency: Optional[str] = Field("EUR", description="Devise")
    terms_conditions: Optional[str] = Field(None, description="Conditions générales")
    notes: Optional[str] = Field(None, description="Notes générales")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    extraction_sources: Dict[str, ExtractionSource] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    
    @model_validator(mode='after')
    def calculate_totals(self):
        """Calculer les totaux automatiquement depuis les articles"""
        if self.order_items:
            subtotal = sum(item.total_before_tax or 0 for item in self.order_items)
            total_tax = sum(item.total_tax or 0 for item in self.order_items)
            total_amount = sum(item.total_price or 0 for item in self.order_items)
            
            self.subtotal = round(subtotal, 2)
            self.total_tax = round(total_tax, 2)
            self.total_amount = round(total_amount, 2)
        
        return self
    
    @property
    def item_count(self) -> int:
        """Nombre total d'articles"""
        return len(self.order_items)
    
    @property
    def total_quantity(self) -> float:
        """Quantité totale d'articles"""
        return sum(item.quantity for item in self.order_items)

class FormField(BaseModel):
    """Champ de formulaire"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    label: str
    value: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    field_type: Optional[str] = Field(None, description="text, number, date, checkbox, etc.")
    is_required: bool = Field(False)
    is_filled: bool = Field(True)
    validation_pattern: Optional[str] = Field(None, description="Regex validation")
    bounding_box: Optional[List[float]] = Field(None, description="[x1, y1, x2, y2]")
    page: Optional[int] = Field(1, ge=1)
    source: ExtractionSource = Field(ExtractionSource.FORM_PARSER)

class FormExtractionResult(BaseModel):
    """Résultat extraction formulaire"""
    template_id: Optional[str] = Field(None, description="ID template reconnu")
    template_name: Optional[str] = Field(None, description="Nom template")
    fields: List[FormField] = Field(default_factory=list)
    is_handwritten: bool = Field(False)
    handwriting_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    completeness_score: float = Field(0.0, ge=0.0, le=1.0)
    validation_score: float = Field(0.0, ge=0.0, le=1.0)
    field_mapping: Dict[str, str] = Field(default_factory=dict)
    
    @property
    def filled_fields_count(self) -> int:
        return sum(1 for field in self.fields if field.is_filled)
    
    @property
    def total_fields_count(self) -> int:
        return len(self.fields)

class GeolocationResult(BaseModel):
    """Résultat géolocalisation"""
    addresses_found: int = Field(0, ge=0)
    addresses_geocoded: int = Field(0, ge=0)
    coordinates: List[GeoCoordinates] = Field(default_factory=list)
    bounding_box: Optional[Dict[str, float]] = Field(None, description="Bounding box globale")
    center_point: Optional[GeoCoordinates] = Field(None, description="Point central")
    accuracy_score: float = Field(0.0, ge=0.0, le=1.0)
    source: str = Field("nominatim", description="Source géocodage")
    cache_hit: bool = Field(False, description="Résultat depuis cache?")
    processing_time: float = Field(0.0, ge=0.0)
    
    @property
    def success_rate(self) -> float:
        if self.addresses_found == 0:
            return 0.0
        return self.addresses_geocoded / self.addresses_found

class OCRResponse(BaseModel):
    """Réponse API OCR complète"""
    success: bool
    document_id: str
    metadata: DocumentMetadata
    extraction: ExtractionResult
    nlp_result: Optional[NLPResult] = None
    form_result: Optional[FormExtractionResult] = None
    geolocation_result: Optional[GeolocationResult] = None
    form_fields: Optional[Dict[str, str]] = Field(None, deprecated=True)  # Ancien format
    processing_time: float
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    api_version: str = Field("2.0.0")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: lambda v: float(v)
        }

class BatchOCRRequest(BaseModel):
    """Requête traitement par lot"""
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    documents: List[Dict[str, Any]]  # Liste de OCRRequest simplifiées
    priority: str = Field("normal", description="low, normal, high, urgent")
    callback_url: Optional[str] = Field(None, description="URL pour callback")
    notify_email: Optional[str] = Field(None, description="Email notification")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('priority')
    def validate_priority(cls, v):
        if v not in ['low', 'normal', 'high', 'urgent']:
            raise ValueError('Invalid priority level')
        return v

class BatchOCRResponse(BaseModel):
    """Réponse traitement par lot"""
    batch_id: str
    status: str = Field("processing", description="processing, completed, failed")
    total_documents: int
    processed_documents: int
    successful_documents: int
    failed_documents: int
    results: List[OCRResponse]
    total_processing_time: float
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    summary: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def success_rate(self) -> float:
        if self.total_documents == 0:
            return 0.0
        return self.successful_documents / self.total_documents

class HealthMetrics(BaseModel):
    """Métriques santé système"""
    cpu_percent: float = Field(..., ge=0.0, le=100.0)
    memory_percent: float = Field(..., ge=0.0, le=100.0)
    disk_percent: float = Field(..., ge=0.0, le=100.0)
    active_ocr_jobs: int = Field(0, ge=0)
    queue_size: int = Field(0, ge=0)
    average_processing_time: float = Field(0.0, ge=0.0)
    cache_hit_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    uptime_hours: float = Field(0.0, ge=0.0)
    last_error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class APIMetrics(BaseModel):
    """Métriques API"""
    total_requests: int = Field(0, ge=0)
    successful_requests: int = Field(0, ge=0)
    failed_requests: int = Field(0, ge=0)
    average_response_time: float = Field(0.0, ge=0.0)
    endpoints: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    peak_concurrent_users: int = Field(0, ge=0)
    data_processed_mb: float = Field(0.0, ge=0.0)
    period_start: datetime
    period_end: datetime = Field(default_factory=datetime.now)

# ==============================================
# MODÈLES POUR LA GÉOLOCALISATION AVANCÉE
# ==============================================

class LocationCluster(BaseModel):
    """Cluster de localisations"""
    center: GeoCoordinates
    addresses: List[Address]
    radius_km: float = Field(..., ge=0.0)
    density: float = Field(..., ge=0.0)
    confidence: float = Field(..., ge=0.0, le=1.0)

class RouteInfo(BaseModel):
    """Informations d'itinéraire"""
    start: GeoCoordinates
    end: GeoCoordinates
    distance_km: float = Field(..., ge=0.0)
    duration_minutes: float = Field(..., ge=0.0)
    polyline: Optional[str] = Field(None, description="Polyline encodée")
    waypoints: List[GeoCoordinates] = Field(default_factory=list)
    mode: str = Field("driving", description="driving, walking, cycling")

class CoverageArea(BaseModel):
    """Zone de couverture"""
    polygon: List[GeoCoordinates] = Field(..., min_items=3)
    center: GeoCoordinates
    area_sqkm: float = Field(..., ge=0.0)
    address_count: int = Field(0, ge=0)
    is_urban: Optional[bool] = None
    population_density: Optional[float] = Field(None, ge=0.0)

# ==============================================
# UTILITAIRES
# ==============================================

def generate_sample_ocr_response() -> OCRResponse:
    """Générer une réponse OCR d'exemple"""
    return OCRResponse(
        success=True,
        document_id="sample_123",
        metadata=DocumentMetadata(
            filename="carte_visite.jpg",
            file_size=245678,
            mime_type="image/jpeg",
            document_type=DocumentType.IMAGE
        ),
        extraction=ExtractionResult(
            text="Dupont Consulting\n12 Rue de la Paix\n75001 Paris\n01 23 45 67 89",
            confidence=0.95,
            language=Language.FR,
            processing_time=1.2
        ),
        nlp_result=NLPResult(
            intent=IntentType.CONTACT,
            intent_confidence=0.92,
            client=ClientInfo(
                first_name="Jean",
                last_name="Dupont",
                full_name="Jean Dupont",
                contacts=[
                    ContactPoint(
                        type="phone",
                        value="+33123456789",
                        is_primary=True
                    ),
                    ContactPoint(
                        type="email",
                        value="contact@dupont.com",
                        is_primary=False
                    )
                ],
                addresses=[
                    Address(
                        street="12 Rue de la Paix",
                        city="Paris",
                        postal_code="75001",
                        country="France",
                        coordinates=GeoCoordinates(
                            latitude=48.868678,
                            longitude=2.330987,
                            confidence=0.9
                        )
                    )
                ]
            )
        ),
        processing_time=2.5
    )