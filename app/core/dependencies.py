# app/core/dependencies.py - VERSION COMPLÈTE AVEC OCR
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Union
import jwt
import bcrypt

from fastapi import Depends, HTTPException, status, Header, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.models.user import User
from app.models.seller import Seller
from app.models import OCRRequest, DocumentType, Language
from app.core.config import settings
import logging
import tempfile
import shutil

logger = logging.getLogger(__name__)

# =========================================================
# SECURITY MANAGER
# =========================================================

class SecurityManager:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    
    def create_access_token(self, data: dict) -> str:
        current_time = datetime.now(timezone.utc)
        
        payload = {
            "sub": str(data.get("user_id") or data.get("id")),
            "user_id": str(data.get("user_id") or data.get("id")),
            "email": data.get("email", ""),
            "role": data.get("role", "user"),
            "full_name": data.get("full_name", ""),
            "exp": current_time + timedelta(minutes=self.access_token_expire_minutes),
            "iat": current_time,
            "nbf": current_time
        }
        
        if data.get("seller_id"):
            payload["seller_id"] = str(data["seller_id"])
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expiré"
            )
        except jwt.InvalidTokenError as e:
            logger.error(f"Token invalide: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide"
            )
    
    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def get_password_hash(self, password: str) -> str:
        return self.hash_password(password)

security_manager = SecurityManager()

# =========================================================
# UTILS
# =========================================================

def normalize_user_role(role: str) -> str:
    if not role or not isinstance(role, str):
        return "CLIENT"
    
    role_upper = role.upper().strip()
    
    role_mapping = {
        "VENDEUR": "VENDEUR",
        "SELLER": "VENDEUR",
        "VENDOR": "VENDEUR",
        "ADMIN": "ADMIN",
        "LIVREUR": "LIVREUR",
        "DRIVER": "LIVREUR",
        "CLIENT": "CLIENT",
        "CUSTOMER": "CLIENT"
    }
    
    return role_mapping.get(role_upper, role_upper)

def is_seller_role(role: str) -> bool:
    normalized_role = normalize_user_role(role)
    return normalized_role == "VENDEUR"

def validate_uuid(uuid_str: str, field_name: str = "ID") -> UUID:
    try:
        return UUID(uuid_str)
    except (ValueError, AttributeError):
        logger.error(f"{field_name} UUID invalide: {uuid_str}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} invalide"
        )

# =========================================================
# DEPENDENCIES PRINCIPALES
# =========================================================

security = HTTPBearer(auto_error=False)

async def get_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    if not credentials:
        logger.warning("Header Authorization manquant")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise. Header Authorization manquant."
        )
    
    token = credentials.credentials
    
    if not token:
        logger.warning("Token vide dans le header Authorization")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant dans le header Authorization"
        )
    
    return token

# =========================================================
# OCR FILE UPLOAD DEPENDENCIES
# =========================================================

async def validate_file_upload_ocr(
    file: UploadFile = File(...),
    max_size: int = settings.OCR_MAX_FILE_SIZE
) -> dict:
    """
    Validate uploaded file for OCR processing
    """
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset pointer
    
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size is {max_size // (1024*1024)}MB"
        )
    
    # Check MIME type
    allowed_types = settings.ALLOWED_IMAGE_TYPES + settings.ALLOWED_DOC_TYPES
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type {file.content_type} not supported. Allowed: {', '.join(allowed_types)}"
        )
    
    # Create temp file in OCR temp directory
    temp_dir = settings.OCR_TEMP_DIR
    os.makedirs(temp_dir, exist_ok=True)
    
    # Preserve original extension
    original_name = file.filename
    ext = os.path.splitext(original_name)[1] if '.' in original_name else '.tmp'
    
    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        dir=temp_dir,
        suffix=ext
    )
    
    # Save uploaded file
    try:
        # Read file in chunks for memory efficiency
        chunk_size = 1024 * 1024  # 1MB chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            temp_file.write(chunk)
        temp_file.flush()
    except Exception as e:
        # Clean up temp file on error
        temp_file.close()
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving file: {str(e)}"
        )
    finally:
        await file.close()
    
    logger.info(f"File uploaded: {original_name} ({file_size} bytes) -> {temp_file.name}")
    
    return {
        "temp_path": temp_file.name,
        "filename": original_name,
        "content_type": file.content_type,
        "file_size": file_size,
        "temp_file_obj": temp_file  # Keep reference for proper cleanup
    }

async def cleanup_temp_file_ocr(file_path: str):
    """
    Clean up temporary file for OCR processing
    """
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug(f"Cleaned up temp file: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup temp file {file_path}: {e}")

def get_document_type_ocr(content_type: str) -> DocumentType:
    """
    Map content type to DocumentType enum for OCR
    """
    if content_type.startswith('image/'):
        return DocumentType.IMAGE
    elif 'pdf' in content_type:
        return DocumentType.PDF
    elif 'wordprocessingml' in content_type or 'msword' in content_type:
        return DocumentType.DOCX
    elif 'spreadsheetml' in content_type or 'excel' in content_type:
        return DocumentType.EXCEL
    else:
        return DocumentType.UNKNOWN

# =========================================================
# FONCTION POUR RÉSOUDRE UN IDENTIFIANT (SANS REPOSITORY)
# =========================================================

def resolve_identifier_to_seller_id(
    identifier: Union[str, UUID],
    db: Session
) -> UUID:
    """
    Résout un identifiant (user_id ou seller_id) en seller_id valide
    Sans utiliser de repository, juste avec SQLAlchemy direct
    """
    try:
        # Convertir en UUID si c'est une chaîne
        if isinstance(identifier, str):
            try:
                identifier_uuid = UUID(identifier)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Identifiant invalide: doit être un UUID valide"
                )
        else:
            identifier_uuid = identifier
        
        logger.debug(f"🔍 Résolution de l'identifiant: {identifier_uuid}")
        
        # Essayer d'abord comme seller_id
        seller = db.query(Seller).filter(Seller.id == identifier_uuid).first()
        if seller:
            logger.debug(f"✅ Identifiant est un seller_id: {seller.id}")
            return seller.id
        
        # Essayer comme user_id
        seller_by_user = db.query(Seller).filter(Seller.user_id == identifier_uuid).first()
        if seller_by_user:
            logger.debug(f"✅ Identifiant est un user_id -> seller trouvé: {seller_by_user.id}")
            return seller_by_user.id
        
        # Aucun seller trouvé
        logger.warning(f"❌ Aucun seller trouvé pour l'identifiant: {identifier_uuid}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aucun vendeur trouvé pour cet identifiant"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur résolution identifiant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la résolution de l'identifiant: {str(e)}"
        )

# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(
    token: str = Depends(get_token),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    try:
        payload = security_manager.verify_jwt_token(token)
        
        user_id_str = payload.get("sub") or payload.get("user_id")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide: user_id manquant"
            )
        
        try:
            user_id = UUID(user_id_str)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide: user_id incorrect"
            )
        
        user = db.query(User).filter(
            User.id == user_id,
            User.is_active == True
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé ou compte désactivé"
            )
        
        user_role = normalize_user_role(user.role)
        
        # Récupérer les infos du seller si c'est un vendeur
        seller_info = None
        if user_role == "VENDEUR":
            seller = db.query(Seller).filter(Seller.user_id == user.id).first()
            if seller:
                seller_info = {
                    "seller_id": str(seller.id),
                    "company_name": seller.company_name,
                    "abonnement_type": seller.abonnement_type,
                    "abonnement_status": seller.abonnement_status
                }
        
        user_data = {
            "id": str(user.id),
            "user_id": str(user.id),
            "email": user.email,
            "role": user_role,
            "full_name": user.full_name,
            "telephone": user.telephone,
            "adresse": user.adresse,
            "is_active": user.is_active,
            "statut": user.statut,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "seller_id": payload.get("seller_id"),
        }
        
        if seller_info:
            user_data.update(seller_info)
        
        logger.info(f"✅ Utilisateur authentifié: {user.email} ({user_role})")
        return user_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur authentification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur d'authentification: {str(e)}"
        )

# =========================================================
# GET CURRENT SELLER
# =========================================================

def get_current_seller(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    try:
        user_role = current_user.get("role", "")
        
        if not is_seller_role(user_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Accès réservé aux vendeurs"
            )
        
        user_id = current_user.get("id")
        
        seller = db.query(Seller).filter(Seller.user_id == user_id).first()
        
        if not seller:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Compte seller non trouvé"
            )
        
        seller_data = {
            "seller_id": str(seller.id),
            "id": str(seller.id),
            "user_id": str(user_id),
            "email": current_user.get("email"),
            "full_name": current_user.get("full_name"),
            "role": "VENDEUR",
            "telephone": current_user.get("telephone"),
            "adresse": current_user.get("adresse"),
            "company_name": seller.company_name,
            "abonnement_type": seller.abonnement_type,
            "abonnement_status": seller.abonnement_status,
            "is_active": seller.abonnement_status == "actif",
            "created_at": seller.created_at,
            "updated_at": seller.updated_at
        }
        
        logger.info(f"✅ Seller authentifié: {seller.company_name} (seller_id: {seller.id})")
        return seller_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération seller: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du compte seller: {str(e)}"
        )

# =========================================================
# GET CURRENT USER (PUBLIC OPTIONAL)
# =========================================================

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    Optional user dependency - returns None if no token provided
    """
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        if not token:
            return None
        
        payload = security_manager.verify_jwt_token(token)
        
        user_id_str = payload.get("sub") or payload.get("user_id")
        if not user_id_str:
            return None
        
        # Return basic user info from token (without DB query)
        return {
            "id": user_id_str,
            "user_id": user_id_str,
            "email": payload.get("email", ""),
            "role": payload.get("role", "user"),
            "full_name": payload.get("full_name", ""),
            "seller_id": payload.get("seller_id")
        }
        
    except Exception as e:
        logger.debug(f"Optional auth failed: {e}")
        return None

# =========================================================
# FONCTIONS EXPORTÉES
# =========================================================

def get_password_hash(password: str) -> str:
    return security_manager.get_password_hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return security_manager.verify_password(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    return security_manager.create_access_token(data)

# =========================================================
# OCR SPECIFIC DEPENDENCIES
# =========================================================

async def ocr_file_upload_dependency(
    file: UploadFile = File(...)
) -> dict:
    """
    Dependency for OCR file uploads with automatic cleanup
    """
    return await validate_file_upload_ocr(file)

def ocr_document_type_dependency(content_type: str) -> DocumentType:
    """
    Dependency to get document type from content type
    """
    return get_document_type_ocr(content_type)

class OCRBackgroundTasks:
    """
    Helper class for OCR background task management
    """
    @staticmethod
    async def add_cleanup_task(background_tasks, file_path: str):
        """
        Add file cleanup to background tasks
        """
        if background_tasks and file_path:
            background_tasks.add_task(cleanup_temp_file_ocr, file_path)
    
    @staticmethod
    def cleanup_immediately(file_path: str):
        """
        Clean up file immediately (not in background)
        """
        cleanup_temp_file_ocr(file_path)

# =========================================================
# ROLES & PERMISSIONS FOR OCR
# =========================================================

def require_seller_or_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency that requires user to be either seller or admin
    """
    user_role = current_user.get("role", "").upper()
    
    allowed_roles = ["VENDEUR", "ADMIN", "SELLER"]
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux vendeurs et administrateurs"
        )
    
    return current_user

def require_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency that requires admin role
    """
    user_role = current_user.get("role", "").upper()
    
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs"
        )
    
    return current_user

# =========================================================
# OCR RATE LIMITING (SIMPLE VERSION)
# =========================================================

from collections import defaultdict
from datetime import datetime

class OCRRateLimiter:
    """
    Simple in-memory rate limiter for OCR endpoints
    """
    _requests = defaultdict(list)
    
    @classmethod
    def check_rate_limit(cls, user_id: str, limit: int = 100, window: int = 3600):
        """
        Check if user has exceeded rate limit
        limit: requests per window
        window: time window in seconds (default 1 hour)
        """
        current_time = datetime.now().timestamp()
        
        # Clean old requests
        cls._requests[user_id] = [
            req_time for req_time in cls._requests[user_id]
            if current_time - req_time < window
        ]
        
        # Check limit
        if len(cls._requests[user_id]) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {limit} requests per hour."
            )
        
        # Add current request
        cls._requests[user_id].append(current_time)
        
        return True

def ocr_rate_limit_dependency(
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional)
):
    """
    Rate limiting dependency for OCR endpoints
    """
    user_id = current_user.get("id") if current_user else "anonymous"
    
    # Different limits for authenticated vs anonymous users
    if current_user:
        limit = 500  # 500 requests per hour for authenticated users
    else:
        limit = 50   # 50 requests per hour for anonymous users
    
    OCRRateLimiter.check_rate_limit(user_id, limit=limit)
    return current_user