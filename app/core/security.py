import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import jwt  # type: ignore
import bcrypt

# ✅ IMPORTS FASTAPI
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

# ✅ IMPORTS DE VOS MODULES
try:
    from app.db import get_db
    from app.models.user import User
    from app.models.seller import Seller  # IMPORTANT
    from app.core.config import settings
except ImportError:
    # Fallback pour le test
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
    
    class Settings:
        SECRET_KEY = os.getenv("SECRET_KEY")
        ALGORITHM = os.getenv("ALGORITHM", "HS256")
        ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    
    settings = Settings()
    
    # Fallback pour get_db (pour les tests)
    def get_db():
        yield None


class SecurityManager:
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    
    # ========== VERSION CORRIGÉE AVEC seller_id ==========
    def create_jwt_token(self, user_id: str, email: str, role: str, full_name: str, seller_id: Optional[str] = None) -> str:
        """Crée un token JWT avec les informations utilisateur"""
        current_time = datetime.now(timezone.utc)
        
        payload = {
            "user_id": user_id,
            "email": email,
            "role": role,
            "full_name": full_name,
            "exp": current_time + timedelta(minutes=self.access_token_expire_minutes),
            "iat": current_time,
            "nbf": current_time
        }
        
        # ⭐ AJOUT du seller_id SI DISPONIBLE
        if seller_id:
            payload["seller_id"] = seller_id
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token
    
    def verify_jwt_token(self, token: str) -> Dict[str, Any]:
        """Vérifie et décode un token JWT"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expiré")
        except jwt.InvalidTokenError:
            raise ValueError("Token invalide")
    
    def hash_password(self, password: str) -> str:
        """Hash un mot de passe en utilisant bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe contre son hash"""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    
    def get_user_from_token(self, token: str) -> Dict[str, Any]:
        """Extrait les infos utilisateur du token"""
        payload = self.verify_jwt_token(token)
        return {
            "user_id": payload.get("user_id"),
            "email": payload.get("email"),
            "role": payload.get("role"),
            "full_name": payload.get("full_name"),
            "seller_id": payload.get("seller_id")  # ⭐ AJOUTÉ
        }
    
    # ✅ FONCTION POUR CRÉER UN TOKEN AVEC SELLER_ID
    def create_access_token_with_seller(self, user_id: str, email: str, role: str, full_name: str, seller_id: str) -> str:
        """Crée un token d'accès avec seller_id"""
        return self.create_jwt_token(user_id, email, role, full_name, seller_id)
    
    def create_access_token(self, data: dict) -> str:
        """Crée un token d'accès (alias pour compatibilité)"""
        user_id = data.get("sub") or data.get("user_id")
        email = data.get("email")
        role = data.get("role", "user")
        full_name = data.get("full_name", "")
        seller_id = data.get("seller_id")  # ⭐ Récupère seller_id si présent
        
        return self.create_jwt_token(str(user_id), email, role, full_name, seller_id)
    
    def get_password_hash(self, password: str) -> str:
        """Alias pour hash_password (compatibilité)"""
        return self.hash_password(password)


# ✅ SECURITY BEARER POUR L'AUTHENTIFICATION
security = HTTPBearer()


# ========== FONCTIONS DE DÉPENDANCE ==========

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Dependency to get current authenticated user from JWT token
    """
    try:
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials missing",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = credentials.credentials
        security_manager = SecurityManager()  # Créer une instance
        payload = security_manager.verify_jwt_token(token)
        
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Inactive user",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # ⭐ RETOURNE AUSSI seller_id DU TOKEN SI PRÉSENT
        return {
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "seller_id": payload.get("seller_id")  # ⭐ AJOUTÉ
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ========== ⭐ FONCTION get_current_seller CORRIGÉE ==========

def get_current_seller(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    """
    Récupère le vendeur actuel à partir du token JWT
    """
    try:
        # 1. Obtenir l'utilisateur courant
        current_user = get_current_user(credentials, db)
        
        user_id = current_user.get("user_id")
        
        # 2. Chercher le Seller correspondant dans la base
        seller = db.query(Seller).filter(
            Seller.user_id == user_id
        ).first()
        
        if not seller:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profil vendeur non trouvé pour cet utilisateur",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return seller
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération du vendeur: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ========== FONCTIONS UTILITAIRES ==========

def get_password_hash(password: str) -> str:
    """Fonction exportée pour compatibilité"""
    security_manager = SecurityManager()
    return security_manager.get_password_hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Fonction exportée pour compatibilité"""
    security_manager = SecurityManager()
    return security_manager.verify_password(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """Fonction exportée pour compatibilité"""
    security_manager = SecurityManager()
    return security_manager.create_access_token(data)


# ========== FONCTION POUR GÉNÉRER UN TOKEN AVEC SELLER_ID ==========

def create_seller_token(user_id: str, email: str, role: str, full_name: str, seller_id: str) -> str:
    """
    Crée un token JWT avec l'ID du vendeur inclus
    """
    security_manager = SecurityManager()
    return security_manager.create_access_token_with_seller(
        user_id=user_id,
        email=email,
        role=role,
        full_name=full_name,
        seller_id=seller_id
    )


# ========== TEST DU MODULE ==========

if __name__ == "__main__":
    print("✅ Module security.py chargé avec succès!")
    print(f"   - get_current_user: {'✓' if 'get_current_user' in globals() else '✗'}")
    print(f"   - get_current_seller: {'✓' if 'get_current_seller' in globals() else '✗'}")
    print(f"   - SecurityManager: {'✓' if 'SecurityManager' in globals() else '✗'}")
    
    # Test de création de token
    security_manager = SecurityManager()
    test_token = security_manager.create_jwt_token(
        user_id="test-user-123",
        email="test@example.com",
        role="VENDEUR",
        full_name="Test User",
        seller_id="test-seller-456"
    )
    
    print(f"\n🔐 Test token avec seller_id:")
    print(f"   Token généré: {test_token[:50]}...")
    
    # Décoder pour vérifier
    try:
        payload = security_manager.verify_jwt_token(test_token)
        print(f"   ✅ Token valide")
        print(f"   Contient seller_id: {'✓' if 'seller_id' in payload else '✗'}")
        if 'seller_id' in payload:
            print(f"   seller_id: {payload['seller_id']}")
    except Exception as e:
        print(f"   ❌ Erreur: {e}")