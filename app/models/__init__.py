# app/models/__init__.py
# Import de tous les modèles

# Models utilisateurs
from .user import User
from .seller import Seller
from .password_reset_code import PasswordResetCode  
from .facebook_reply import FacebookReplyHistory
# Models produits - basé sur ton product.py
from .product import Product  # Ton fichier a seulement Product, pas Category

# Models Facebook
from .facebook import (
    FacebookUser, FacebookPage, FacebookPost, FacebookComment,
    FacebookLiveVideo, FacebookMessage, FacebookWebhookLog,
    FacebookWebhookSubscription
)

# Models drivers
from .driver_model import Driver  # Ton driver_model.py a seulement Driver, pas DriverAvailability

# Models notifications
from .notification import Notification

# Models OCR - si existe
try:
    from .ocr_nlp import (
        OCRRequest, OCRResult, DocumentType, Language, 
        OCRResponse, DocumentMetadata, ExtractionResult,
        NLPResult, BatchOCRRequest, BatchOCRResult, BatchOCRResponse, 
        IntentType
    )
    # StandardResponse n'existe pas dans models/ocr_nlp.py, mais dans schemas/ocr_nlp.py
    # Donc on ne l'importe pas ici
except ImportError:
    OCRRequest = OCRResult = DocumentType = Language = OCRResponse = None
    DocumentMetadata = ExtractionResult = NLPResult = None
    BatchOCRRequest = BatchOCRResult = BatchOCRResponse = IntentType = None



# Liste complète de tous les modèles disponibles
__all__ = [
    # Users
    "User", "Seller", "PasswordResetCode",
    
    # Products
    "Product",
    
    # Facebook
    "FacebookUser", "FacebookPage", "FacebookPost", "FacebookComment",
    "FacebookLiveVideo", "FacebookMessage", "FacebookWebhookLog",
    "FacebookWebhookSubscription", "FacebookReplyHistory",  
    # Reports
    "Report", "ReportTemplate",
    
    # Orders
    "Order", "OrderItem", "OrderStatus", "Payment", "PaymentMethod",
    
    # OCR (sans StandardResponse car il est dans schemas/)
    "OCRRequest", "OCRResult", "DocumentType", "Language", 
    "OCRResponse", "DocumentMetadata", "ExtractionResult",
    "NLPResult", "BatchOCRRequest", "BatchOCRResult", "BatchOCRResponse",
    "IntentType",
    # Note: StandardResponse n'est pas ici car c'est un schéma, pas un modèle
]