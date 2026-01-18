from .email_service import EmailService, email_service
from .geocoding_service_madagascar import geocoding_service_mg as geocoding_service

# app/services/__init__.py
import logging

logger = logging.getLogger(__name__)

# Import des services existants
from .facebook_auth import FacebookAuthService
from .facebook_webhook import FacebookWebhookService
from .facebook_graph_api import FacebookGraphAPIService
from .nlp_service import NLPService

# Configuration commune
DEFAULT_NLP_CONFIG = {
    "NER_PHONE_PATTERNS": [
        r'\b(?:034|032|033|038|020|021)\s?\d{2}\s?\d{3}\s?\d{2}\b',
        r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{3}[-.\s]?\d{2}\b'
    ],
    "NER_EMAIL_PATTERN": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "NER_PRICE_PATTERN": r'(?:(?:\d{1,3}(?:[.,]\d{3})*|\d+)(?:[.,]\d{2})?)\s*(?:Ar|MGA|€|EUR|\$|USD)'
}

# Configuration OCR (si disponible)
OCR_CONFIG = {
    "temp_dir": "./temp_ocr",
    "max_file_size": 10 * 1024 * 1024,  # 10MB
    "supported_formats": ["image/jpeg", "image/png", "application/pdf"],
    "OCR_ENGINE": "paddleocr",
    "PADDLE_OCR_LANGS": ["fr", "en", "mg"],
    "MAX_CONCURRENT_OCR": 4,
    "OCR_TIMEOUT": 30,
    "preprocess_image": True  # Ajouté pour activer le prétraitement
}

# ==============================================
# SERVICE OCR - CORRECTION PRINCIPALE
# ==============================================
OCRServiceClass = None  # Initialiser à None
try:
    from .ocr_service import OCRService as OCRServiceClass
    OCR_SERVICE_AVAILABLE = True
    # ⭐ CORRECTION : Créer une INSTANCE, pas assigner la classe
    ocr_service_instance = OCRServiceClass(config=OCR_CONFIG)  # INSTANCE
    logger.info("✅ Service OCR disponible et initialisé")
except ImportError as e:
    OCR_SERVICE_AVAILABLE = False
    logger.warning(f"⚠️ Service OCR non disponible: {e}")
    # Créer un service factice COMPLET
    class OCRServiceDummy:
        def __init__(self, config=None):
            self.available = False
            self.name = "OCRService (Dummy)"
            self.config = config or {}
            self.ocr_engine = None
        
        # ⭐ CORRECTION : Ajouter TOUTES les méthodes nécessaires
        def extract_from_image(self, image_path: str, language: str = None):
            raise ImportError("OCRService non disponible. Installer paddleocr.")
        
        def extract_from_pdf(self, pdf_path: str, language: str = None):
            raise ImportError("OCRService non disponible.")
        
        def extract_from_docx(self, docx_path: str):
            raise ImportError("OCRService non disponible.")
        
        def extract_from_excel(self, excel_path: str):
            raise ImportError("OCRService non disponible.")
        
        def process_document(self, file_path: str, language: str = None):
            return {
                'success': False,
                'file_type': 'unknown',
                'text': "",
                'confidence': 0.0,
                'pages': [],
                'processing_time': 0.0,
                'error': 'OCRService non disponible. Installer paddleocr.'
            }
        
        def detect_file_type(self, file_path: str):
            return "unknown"
        
        # Ancienne méthode (pour compatibilité)
        def extract_text(self, *args, **kwargs):
            raise ImportError("OCRService non disponible.")
        
        def __call__(self, *args, **kwargs):
            raise ImportError("OCRService non disponible.")
    
    # Définir OCRServiceClass pour l'export
    OCRServiceClass = OCRServiceDummy
    ocr_service_instance = OCRServiceDummy(config=OCR_CONFIG)  # INSTANCE

# ⭐ CORRECTION : Exporter l'instance avec le nom attendu
ocr_service = ocr_service_instance

# ==============================================
# AUTRES SERVICES OCR (optionnels)
# ==============================================
FormParserServiceClass = None
try:
    from .form_parser import FormParserService as FormParserServiceClass
    FORM_PARSER_AVAILABLE = True
    # Créer une instance
    form_parser_instance = FormParserServiceClass(config=DEFAULT_NLP_CONFIG)
    logger.info("✅ FormParserService disponible")
except ImportError as e:
    FORM_PARSER_AVAILABLE = False
    logger.warning(f"⚠️ FormParserService non disponible: {e}")
    class FormParserServiceDummy:
        def __init__(self, config=None):
            self.available = False
            self.config = config or {}
        
        def extract_form_fields(self, *args, **kwargs):
            raise ImportError("FormParserService non disponible.")
        
        def parse_form_fields(self, text, language):
            return {}
        
        def detect_form_type(self, text, language):
            return "unknown"
        
        def calculate_form_completeness(self, fields, form_type):
            return 0
        
        def detect_handwriting(self, image_path):
            return False
        
        def __call__(self, *args, **kwargs):
            raise ImportError("FormParserService non disponible.")
    
    FormParserServiceClass = FormParserServiceDummy
    form_parser_instance = FormParserServiceDummy(config=DEFAULT_NLP_CONFIG)

# Exporter l'instance
form_parser = form_parser_instance

LanguageDetectorServiceClass = None
try:
    from .language_detector import LanguageDetectorService as LanguageDetectorServiceClass
    LANGUAGE_DETECTOR_AVAILABLE = True
    # Créer une instance
    try:
        language_detector_instance = LanguageDetectorServiceClass(config=DEFAULT_NLP_CONFIG)
    except TypeError:
        # Si la classe n'accepte pas config
        language_detector_instance = LanguageDetectorServiceClass()
    logger.info("✅ LanguageDetectorService disponible")
except ImportError as e:
    LANGUAGE_DETECTOR_AVAILABLE = False
    logger.warning(f"⚠️ LanguageDetectorService non disponible: {e}")
    class LanguageDetectorServiceDummy:
        def __init__(self, config=None):
            self.available = False
            self.config = config or {}
        
        def detect(self, text):
            return "fr"  # Français par défaut
        
        def detect_with_confidence(self, text):
            return ("fr", 1.0)  # Pour compatibilité
        
        def detect_multiple(self, texts):
            return ["fr"] * len(texts) if texts else []
        
        def detect_language(self, text):
            return "fr"
    
    LanguageDetectorServiceClass = LanguageDetectorServiceDummy
    language_detector_instance = LanguageDetectorServiceDummy(config=DEFAULT_NLP_CONFIG)

# Exporter l'instance
language_detector = language_detector_instance

OrderBuilderServiceClass = None
try:
    from .order_builder import OrderBuilderService as OrderBuilderServiceClass
    ORDER_BUILDER_AVAILABLE = True
    # Créer une instance
    try:
        order_builder_instance = OrderBuilderServiceClass(config=DEFAULT_NLP_CONFIG)
    except TypeError:
        order_builder_instance = OrderBuilderServiceClass()
    logger.info("✅ OrderBuilderService disponible")
except ImportError as e:
    ORDER_BUILDER_AVAILABLE = False
    logger.warning(f"⚠️ OrderBuilderService non disponible: {e}")
    class OrderBuilderServiceDummy:
        def __init__(self, config=None):
            self.available = False
            self.config = config or {}
        
        def build_order_from_text(self, *args, **kwargs):
            raise ImportError("OrderBuilderService non disponible.")
        
        def build_order_structure(self, nlp_data, form_fields=None):
            return {}
        
        def prepare_for_order_service(self, order_structure):
            return {}
    
    OrderBuilderServiceClass = OrderBuilderServiceDummy
    order_builder_instance = OrderBuilderServiceDummy(config=DEFAULT_NLP_CONFIG)

# Exporter l'instance
order_builder = order_builder_instance

# ==============================================
# SERVICES FACEBOOK
# ==============================================
facebook_auth_service = FacebookAuthService()
facebook_webhook_service = FacebookWebhookService()
facebook_graph_service = FacebookGraphAPIService()

# ==============================================
# SERVICE NLP
# ==============================================
NLPServiceClass = None
try:
    from .nlp_service import NLPService as NLPServiceClass
    nlp_service_instance = NLPServiceClass(config=DEFAULT_NLP_CONFIG)
    logger.info("✅ Service NLP initialisé avec succès")
except Exception as e:
    logger.error(f"❌ Erreur initialisation NLP Service: {e}")
    class NLPServiceDummy:
        def __init__(self, config=None):
            self.available = False
            self.config = config or {}
        
        def extract_entities(self, *args, **kwargs):
            return []
        
        def extract_all(self, text, language="fr"):
            return {
                "text": text,
                "language": language,
                "intent": "OTHER",
                "intent_confidence": 0.0,
                "phone_numbers": [],
                "emails": [],
                "first_name": "",
                "last_name": "",
                "address": {},
                "order_items": [],
                "prices": [],
                "processing_time": 0.0
            }
        
        def analyze_sentiment(self, *args, **kwargs):
            return "neutral"
    
    NLPServiceClass = NLPServiceDummy
    nlp_service_instance = NLPServiceDummy(config=DEFAULT_NLP_CONFIG)
    logger.warning("⚠️ NLP Service factice créé")

# Exporter l'instance
nlp_service = nlp_service_instance

# ==============================================
# EXPORT FINAL - CORRIGÉ
# ==============================================
__all__ = [
    # Services Facebook
    'FacebookAuthService',
    'FacebookWebhookService', 
    'FacebookGraphAPIService',
    
    # Services OCR/NLP - INSTANCES
    'ocr_service',           # ⭐ Instance du service OCR
    'form_parser',           # ⭐ Instance du form parser  
    'language_detector',     # ⭐ Instance du détecteur de langue
    'order_builder',         # ⭐ Instance du constructeur de commandes
    'nlp_service',           # ⭐ Instance du service NLP
    
    # Services Facebook - instances
    'facebook_auth_service',
    'facebook_webhook_service',
    'facebook_graph_service',
    
    # Autres services
    'EmailService', 
    'email_service',
    'geocoding_service',
    
    # ⭐ CORRECTION : N'exporte les classes que si elles existent
    'OCRServiceClass' if OCRServiceClass else None,
    'FormParserServiceClass' if FormParserServiceClass else None,
    'LanguageDetectorServiceClass' if LanguageDetectorServiceClass else None,
    'OrderBuilderServiceClass' if OrderBuilderServiceClass else None,
    'NLPServiceClass' if NLPServiceClass else None,
    
    # ⭐ ALTERNATIVE : Export conditionnel (plus propre)
    'OCR_SERVICE_AVAILABLE',
    'FORM_PARSER_AVAILABLE',
    'LANGUAGE_DETECTOR_AVAILABLE',
    'ORDER_BUILDER_AVAILABLE'
]

# ⭐ NETTOYAGE : Supprimer les None de la liste d'export
__all__ = [item for item in __all__ if item is not None]