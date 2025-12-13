# app/schemas/notification.py
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
import json

# Schéma de base
class NotificationBase(BaseModel):
    type: str = Field(..., max_length=50, description="Type de notification")
    title: str = Field(..., max_length=200, description="Titre de la notification")
    message: str = Field(..., description="Message de la notification")
    data: Dict[str, Any] = Field(default_factory=dict, description="Données supplémentaires")

# Schéma pour la création
class NotificationCreate(NotificationBase):
    seller_id: int = Field(..., description="ID du vendeur")

# Schéma pour la réponse
class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    message: str
    data: Dict[str, Any]
    read: bool
    created_at: datetime
    read_at: Optional[datetime] = None
    
    @validator('data', pre=True)
    def parse_json_data(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v or {}
    
    class Config:
        from_attributes = True

# Schéma pour la liste
class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    unread_count: int
    current_page: int
    total_pages: int
    
    class Config:
        from_attributes = True

# Schéma pour les statistiques
class NotificationStatsResponse(BaseModel):
    total: int
    unread: int
    by_type: Dict[str, int]
    today_count: int
    read_rate: float = Field(..., ge=0, le=100, description="Pourcentage de notifications lues")
    
    class Config:
        from_attributes = True

# Schéma pour marquer comme lu
class MarkReadRequest(BaseModel):
    notification_ids: Optional[List[int]] = Field(
        None, 
        description="Liste d'IDs de notifications. Si vide, marque toutes les notifications comme lues"
    )
    all_unread: bool = Field(
        False, 
        description="Si True, marque toutes les notifications non lues comme lues"
    )

# Schéma pour les paramètres
class NotificationSettings(BaseModel):
    # Types de notifications
    email_enabled: bool = Field(True, description="Activer les notifications par email")
    push_enabled: bool = Field(True, description="Activer les notifications push")
    
    # Sources de notifications
    facebook_comments: bool = Field(True, description="Notifications des commentaires Facebook")
    facebook_messages: bool = Field(True, description="Notifications des messages Facebook")
    facebook_lives: bool = Field(True, description="Notifications des lives Facebook")
    
    # Alertes produits
    low_stock_alerts: bool = Field(True, description="Alertes stock bas")
    out_of_stock_alerts: bool = Field(True, description="Alertes rupture de stock")
    price_change_alerts: bool = Field(False, description="Alertes changement de prix")
    
    # Résumés
    daily_summary: bool = Field(True, description="Résumé quotidien")
    weekly_summary: bool = Field(False, description="Résumé hebdomadaire")
    
    # Heures silencieuses
    quiet_hours_enabled: bool = Field(False, description="Activer les heures silencieuses")
    quiet_hours_start: Optional[str] = Field(
        None, 
        regex="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$",
        description="Heure de début (HH:MM)"
    )
    quiet_hours_end: Optional[str] = Field(
        None,
        regex="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$",
        description="Heure de fin (HH:MM)"
    )
    
    # Seuils
    low_stock_threshold: int = Field(10, ge=1, description="Seuil d'alerte stock bas")
    
    @validator('quiet_hours_end')
    def validate_quiet_hours(cls, v, values):
        if values.get('quiet_hours_enabled') and values.get('quiet_hours_start'):
            if not v:
                raise ValueError("Heure de fin requise quand les heures silencieuses sont activées")
        return v

# Schéma pour les métadonnées de notification
class NotificationMeta(BaseModel):
    source: str = Field(..., description="Source de la notification")
    entity_id: Optional[int] = None
    entity_type: Optional[str] = None
    priority: str = Field("normal", regex="^(low|normal|high|urgent)$")
    actions: List[Dict[str, Any]] = Field(default_factory=list)

# Schéma pour les réponses d'action
class ActionResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    deleted_count: Optional[int] = None

# Schéma pour les éléments Facebook non lus
class FacebookUnreadResponse(BaseModel):
    facebook_unread: Dict[str, int]
    timestamp: datetime
    
    class Config:
        from_attributes = True