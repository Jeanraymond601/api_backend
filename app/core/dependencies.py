# app/core/dependencies.py - VERSION SANS REPOSITORY SELLER
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Union
import jwt
import bcrypt

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from uuid import UUID

from app.db import get_db
from app.models.user import User
from app.models.seller import Seller
from app.core.config import settings

import logging
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
        
        print(f"🔍 Résolution de l'identifiant: {identifier_uuid}")
        
        # Essayer d'abord comme seller_id
        seller = db.query(Seller).filter(Seller.id == identifier_uuid).first()
        if seller:
            print(f"✅ Identifiant est un seller_id: {seller.id}")
            return seller.id
        
        # Essayer comme user_id
        seller_by_user = db.query(Seller).filter(Seller.user_id == identifier_uuid).first()
        if seller_by_user:
            print(f"✅ Identifiant est un user_id -> seller trouvé: {seller_by_user.id}")
            return seller_by_user.id
        
        # Aucun seller trouvé
        print(f"❌ Aucun seller trouvé pour l'identifiant: {identifier_uuid}")
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
# FONCTIONS EXPORTÉES
# =========================================================

def get_password_hash(password: str) -> str:
    return security_manager.get_password_hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return security_manager.verify_password(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    return security_manager.create_access_token(data)