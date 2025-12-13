# app/schemas.py - Version complète
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# ============ USER SCHEMAS ============
class UserBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100, description="Nom complet de l'utilisateur")
    email: EmailStr = Field(..., description="Email de l'utilisateur")
    telephone: str = Field(..., min_length=8, max_length=20, description="Numéro de téléphone")
    adresse: str = Field(..., min_length=5, max_length=255, description="Adresse complète")

class UserCreate(UserBase):
    """Schéma pour créer un utilisateur"""
    password: str = Field(..., min_length=6, description="Mot de passe")
    role: str = Field(default="LIVREUR", description="Rôle: ADMIN, VENDEUR, LIVREUR, CLIENT")
    statut: str = Field(default="en_attente", description="Statut: en_attente, actif, suspendu, rejeté")
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError('Le mot de passe doit contenir au moins 6 caractères')
        return v
    
    @field_validator('telephone')
    @classmethod
    def validate_telephone(cls, v: str) -> str:
        # Enlever les espaces et caractères spéciaux pour validation
        cleaned = v.replace(' ', '').replace('-', '').replace('.', '').replace('(', '').replace(')', '')
        if not cleaned.replace('+', '').isdigit():
            raise ValueError('Numéro de téléphone invalide')
        return v

class UserUpdate(BaseModel):
    """Schéma pour mettre à jour un utilisateur"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    telephone: Optional[str] = Field(None, min_length=8, max_length=20)
    adresse: Optional[str] = Field(None, min_length=5, max_length=255)
    statut: Optional[str] = Field(None, pattern="^(en_attente|actif|suspendu|rejeté)$")
    is_active: Optional[bool] = None
    
    class Config:
        extra = "forbid"  # N'accepte pas de champs supplémentaires

class UserResponse(UserBase):
    """Schéma de réponse pour un utilisateur"""
    id: UUID
    role: str
    statut: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda dt: dt.isoformat()
        }

# ============ DRIVER SCHEMAS ============
class DriverBase(BaseModel):
    zone_livraison: Optional[str] = Field(None, max_length=255, description="Zone de livraison")
    disponibilite: bool = Field(default=True, description="Disponibilité du livreur")

class DriverCreate(DriverBase):
    """Schéma pour créer un driver (version avec user_id existant)"""
    user_id: UUID = Field(..., description="ID de l'utilisateur associé")

class DriverCreateSimple(BaseModel):
    """Schéma simplifié pour créer un livreur (tout en un)"""
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    telephone: str = Field(..., min_length=8, max_length=20)
    adresse: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6)
    role: str = Field(default="LIVREUR")
    statut: str = Field(default="en_attente")
    zone_livraison: Optional[str] = Field(None, max_length=255)
    
    @field_validator('role')
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed_roles = ["ADMIN", "VENDEUR", "LIVREUR", "CLIENT"]
        if v.upper() not in allowed_roles:
            raise ValueError(f'Rôle invalide. Doit être: {", ".join(allowed_roles)}')
        return v.upper()

class DriverUpdate(DriverBase):
    """Schéma pour mettre à jour un livreur"""
    zone_livraison: Optional[str] = Field(None, max_length=255)
    disponibilite: Optional[bool] = None
    
    class Config:
        extra = "forbid"

class DriverResponse(DriverBase):
    """Schéma de réponse pour un livreur"""
    id: UUID
    user_id: UUID
    seller_id: UUID
    created_at: datetime
    updated_at: datetime
    user: Optional[UserResponse] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda dt: dt.isoformat()
        }

# ============ DRIVER LIST & STATS SCHEMAS ============
class DriverListItem(BaseModel):
    """Schéma pour un élément de liste de livreurs"""
    id: UUID
    user_id: UUID
    seller_id: UUID
    full_name: str
    email: str
    telephone: str
    adresse: str
    role: str
    statut: str
    zone_livraison: Optional[str]
    disponibilite: bool
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda dt: dt.isoformat()
        }

class DriversListResponse(BaseModel):
    """Réponse pour la liste des livreurs"""
    count: int = Field(..., description="Nombre de livreurs dans cette page")
    total: int = Field(..., description="Nombre total de livreurs")
    active: int = Field(..., description="Nombre de livreurs actifs")
    seller: Dict[str, Any] = Field(..., description="Informations du vendeur")
    drivers: List[DriverListItem] = Field(..., description="Liste des livreurs")

# ============ AUTH SCHEMAS ============
class LoginRequest(BaseModel):
    """Schéma pour la connexion"""
    email: EmailStr = Field(..., description="Email de l'utilisateur")
    password: str = Field(..., min_length=6, description="Mot de passe")

class TokenResponse(BaseModel):
    """Réponse avec token JWT"""
    access_token: str = Field(..., description="Token JWT")
    token_type: str = Field(default="bearer", description="Type de token")
    user_id: UUID = Field(..., description="ID de l'utilisateur")
    role: str = Field(..., description="Rôle de l'utilisateur")
    full_name: str = Field(..., description="Nom complet")
    email: str = Field(..., description="Email")
    
    class Config:
        json_encoders = {
            UUID: str
        }

# ============ UTILITY SCHEMAS ============
class MessageResponse(BaseModel):
    """Réponse de message simple"""
    message: str = Field(..., description="Message de réponse")
    success: bool = Field(default=True, description="Succès de l'opération")
    timestamp: datetime = Field(default_factory=datetime.now, description="Horodatage")
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

class ErrorResponse(BaseModel):
    """Réponse d'erreur"""
    error: str = Field(..., description="Type d'erreur")
    detail: Optional[str] = Field(None, description="Détails de l'erreur")
    code: int = Field(..., description="Code d'erreur HTTP")
    timestamp: datetime = Field(default_factory=datetime.now, description="Horodatage")
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

# ============ DRIVER STATUS SCHEMAS ============
class DriverStatusUpdate(BaseModel):
    """Schéma pour changer le statut d'un livreur"""
    action: str = Field(..., pattern="^(activate|suspend|delete)$", description="Action: activate, suspend, delete")

# ============ SELLER SCHEMAS ============
class SellerBase(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100, description="Nom de l'entreprise")
    facebook_page: Optional[str] = Field(None, description="Page Facebook")
    abonnement_type: str = Field(default="gratuit", pattern="^(gratuit|premium|business)$", description="Type d'abonnement")
    abonnement_status: str = Field(default="actif", pattern="^(actif|expire|en_attente)$", description="Statut de l'abonnement")

class SellerCreate(SellerBase):
    user_id: UUID = Field(..., description="ID de l'utilisateur vendeur")

class SellerResponse(SellerBase):
    id: UUID
    user_id: UUID
    user: Optional[UserResponse] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda dt: dt.isoformat()
        }

# ============ DRIVER STATISTICS ============
class DriverStatsResponse(BaseModel):
    """Statistiques des livreurs"""
    total: int = Field(..., description="Nombre total de livreurs")
    active: int = Field(..., description="Nombre de livreurs actifs")
    available: int = Field(..., description="Nombre de livreurs disponibles")
    by_statut: Dict[str, int] = Field(..., description="Répartition par statut")
    by_disponibilite: Dict[str, int] = Field(..., description="Répartition par disponibilité")

# ============ ZONE STATISTICS ============
class ZoneStats(BaseModel):
    """Statistiques par zone"""
    zone: str = Field(..., description="Nom de la zone")
    total: int = Field(..., description="Nombre total de livreurs")
    disponibles: int = Field(..., description="Nombre de livreurs disponibles")
    indisponibles: int = Field(..., description="Nombre de livreurs indisponibles")

class ZonesResponse(BaseModel):
    """Liste des zones avec statistiques"""
    seller_id: UUID = Field(..., description="ID du vendeur")
    total_zones: int = Field(..., description="Nombre total de zones")
    zones: List[str] = Field(..., description="Liste des zones distinctes")
    zones_with_stats: List[ZoneStats] = Field(..., description="Zones avec statistiques détaillées")
    
    class Config:
        json_encoders = {
            UUID: str
        }

# Export des classes
__all__ = [
    # User
    "UserBase", "UserCreate", "UserUpdate", "UserResponse",
    
    # Driver
    "DriverBase", "DriverCreate", "DriverCreateSimple", "DriverUpdate", "DriverResponse",
    "DriverListItem", "DriversListResponse", "DriverStatusUpdate",
    
    # Auth
    "LoginRequest", "TokenResponse",
    
    # Utility
    "MessageResponse", "ErrorResponse",
    
    # Seller
    "SellerBase", "SellerCreate", "SellerResponse",
    
    # Stats
    "DriverStatsResponse", "ZoneStats", "ZonesResponse"
]