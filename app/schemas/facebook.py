# app/schemas/facebook.py
from fastapi import Query
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from uuid import UUID
from enum import Enum  # ⭐ IMPORTANT: Utilise le Enum de Python, pas SQLAlchemy

# ==================== REQUEST SCHEMAS ====================

class FacebookConnectRequest(BaseModel):
    state: Optional[str] = None


class FacebookCallbackRequest(BaseModel):
    code: str
    state: Optional[str] = None


class SelectPageRequest(BaseModel):
    page_id: str
    page_name: Optional[str] = None
    page_access_token: Optional[str] = None


# ==================== RESPONSE SCHEMAS ====================

class FacebookUserInfo(BaseModel):
    facebook_user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_pic_url: Optional[str] = None


class FacebookPageInfo(BaseModel):
    page_id: str
    name: str
    category: Optional[str] = None
    category_list: Optional[List[Dict]] = None
    picture: Optional[Dict] = None
    cover: Optional[Dict] = None
    fan_count: int = 0
    about: Optional[str] = None
    description: Optional[str] = None
    access_token: str
    is_selected: bool = False
    
    class Config:
        from_attributes = True


class FacebookPageResponse(BaseModel):
    id: UUID
    page_id: str
    name: str
    category: Optional[str] = None
    profile_pic_url: Optional[str] = None
    cover_photo_url: Optional[str] = None
    fan_count: int = 0
    is_selected: bool = False
    auto_reply_enabled: bool = False
    
    class Config:
        from_attributes = True


class FacebookTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    facebook_user_id: str


class FacebookAuthResponse(BaseModel):
    success: bool
    message: str
    user_info: Optional[FacebookUserInfo] = None
    pages: Optional[List[FacebookPageInfo]] = None


class FacebookConnectResponse(BaseModel):
    success: bool
    auth_url: str
    state: Optional[str] = None


class SelectPageResponse(BaseModel):
    success: bool
    message: str
    page_id: str
    page_name: str


# ==================== DATABASE SCHEMAS ====================

class FacebookUserCreate(BaseModel):
    facebook_user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    profile_pic_url: Optional[str] = None
    long_lived_token: str
    token_expires_at: datetime
    seller_id: UUID


class FacebookUserUpdate(BaseModel):
    is_active: Optional[bool] = None
    last_sync: Optional[datetime] = None


class FacebookPageCreate(BaseModel):
    page_id: str
    name: str
    category: Optional[str] = None
    about: Optional[str] = None
    cover_photo_url: Optional[str] = None
    profile_pic_url: Optional[str] = None
    fan_count: int = 0
    page_access_token: str
    token_expires_at: datetime
    facebook_user_id: UUID
    seller_id: UUID


class FacebookPageUpdate(BaseModel):
    is_selected: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    auto_process_comments: Optional[bool] = None
    auto_reply_message: Optional[str] = None


# ==================== WEBHOOK SCHEMAS ====================

class FacebookWebhookChallenge(BaseModel):
    hub_mode: str = Query(..., alias="hub.mode")
    hub_challenge: str = Query(..., alias="hub.challenge")
    hub_verify_token: str = Query(..., alias="hub.verify_token")


class FacebookWebhookEvent(BaseModel):
    object: str
    entry: List[Dict[str, Any]]


# ⭐ CORRECTION : Utilise Enum de Python, pas SQLAlchemy
class CommentStatus(str, Enum):
    NEW = "new"
    PROCESSED = "processed"
    IGNORED = "ignored"
    ERROR = "error"


class FacebookCommentCreate(BaseModel):
    comment_id: str
    message: str
    post_id: str
    user_id: str
    user_name: str
    created_time: datetime


class LiveEvent(BaseModel):
    live_id: str
    status: str  # live, scheduled, archived
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class SyncRequest(BaseModel):
    page_id: str
    sync_type: Literal["posts", "comments", "lives", "all"] = "all"  # ⭐ Correction : Literal pour validation
    days_back: Optional[int] = Field(7, ge=1, le=30)


# ==================== NOUVEAUX SCHÉMAS (pour les endpoints manquants) ====================

class FacebookPostRequest(BaseModel):
    message: str
    link: Optional[str] = None
    image_url: Optional[str] = None


class FacebookPostResponse(BaseModel):
    success: bool
    message: str
    post_id: Optional[str] = None
    post_url: Optional[str] = None


class FacebookLiveVideoResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str  # live, scheduled, archived
    creation_time: Optional[datetime] = None
    scheduled_start_time: Optional[datetime] = None
    live_views: int = 0
    permalink_url: Optional[str] = None
    embed_html: Optional[str] = None
    video_url: Optional[str] = None


class FacebookCommentResponse(BaseModel):
    id: str
    message: str
    created_time: datetime
    from_user: Dict[str, Any]
    comment_count: int = 0
    like_count: int = 0


# ==================== SCHÉMAS POUR FILTRES ====================

class CommentFilter(BaseModel):
    status: Optional[CommentStatus] = None
    page_id: Optional[str] = None
    post_id: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class PostFilter(BaseModel):
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
    include_comments: bool = False


class LiveVideoFilter(BaseModel):
    status: Optional[Literal["live", "scheduled", "archived"]] = None
    limit: int = Field(10, ge=1, le=50)
    offset: int = Field(0, ge=0)
    
    
# ==================== MESSAGE TEMPLATE SCHEMAS ====================

class MessageTemplateType(str, Enum):
    CONFIRMATION_ACHAT = "confirmation_achat"
    DEMANDE_COORDONNEES = "demande_coordonnees"
    COMMANDE_CONFIRMEE = "commande_confirmee"
    CORRECTION_MESSAGE = "correction_message"
    STOCK_INSUFFISANT = "stock_insuffisant"
    REMERCIEMENT = "remerciement"


class FacebookMessageTemplateBase(BaseModel):
    template_type: MessageTemplateType
    content: str


class FacebookMessageTemplateCreate(FacebookMessageTemplateBase):
    pass


class FacebookMessageTemplateUpdate(BaseModel):
    content: Optional[str] = None


class FacebookMessageTemplateResponse(FacebookMessageTemplateBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        
        
        
# ==================== MESSAGE SCHEMAS ====================

class FacebookMessageBase(BaseModel):
    customer_facebook_id: Optional[str] = None
    message_type: str
    content: str
    facebook_page_id: Optional[str] = None
    order_id: Optional[UUID] = None


class FacebookMessageCreate(FacebookMessageBase):
    seller_id: UUID


class FacebookMessageResponse(FacebookMessageBase):
    id: UUID
    seller_id: UUID
    status: str
    direction: str
    sent_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
        

# ==================== SCHÉMAS MANQUANTS POUR LES IMPORTS ====================

class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageResponse(BaseModel):
    """Réponse après l'envoi d'un message"""
    success: bool
    message_id: Optional[str] = None
    recipient_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    
    class Config:
        from_attributes = True


# Aliases pour les schémas existants
LiveVideoResponse = FacebookLiveVideoResponse
PostResponse = FacebookPostResponse


class WebhookSubscriptionRequest(BaseModel):
    page_id: str
    force_resubscribe: bool = False
    fields: Optional[List[str]] = Field(
        default=None,
        description="Liste des champs à souscrire. Par défaut: tous les champs disponibles."
    )


class WebhookSubscriptionResponse(BaseModel):
    """Réponse pour une subscription webhook"""
    success: bool
    message: str
    subscription_id: Optional[str] = None
    fields: Optional[List[str]] = None
    webhook_url: Optional[str] = None


class WebhookHealthResponse(BaseModel):
    """Réponse pour la santé des webhooks"""
    success: bool
    timestamp: datetime
    subscriptions: Dict[str, Any]
    recent_webhooks: List[Dict[str, Any]]
    webhook_url: Optional[str] = None


class BulkProcessRequest(BaseModel):
    """Requête pour le traitement en masse"""
    comment_ids: List[str]
    action: Literal["mark_read", "reply_all", "export", "categorize"]
    reply_text: Optional[str] = Field(
        None, 
        description="Texte de réponse (requis pour l'action 'reply_all')"
    )


class BulkProcessResponse(BaseModel):
    """Réponse pour le traitement en masse"""
    success: bool
    action: str
    processed: int
    results: List[Dict[str, Any]]
    errors: Optional[List[str]] = None


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class ExportCommentsRequest(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_metadata: bool = True


class ExportCommentsResponse(BaseModel):
    """Réponse pour l'export de commentaires"""
    success: bool
    format: str
    count: int
    data: Optional[List[Dict[str, Any]]] = None
    download_url: Optional[str] = None
    filename: Optional[str] = None


class LiveAnalyticsResponse(BaseModel):
    """Réponse pour les analytics de live"""
    success: bool
    live_id: str
    live_title: Optional[str] = None
    status: str
    duration: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    analytics: Dict[str, Any]


class NotificationItem(BaseModel):
    """Élément de notification"""
    id: str
    type: str
    message: str
    user: Optional[str] = None
    page: Optional[str] = None
    timestamp: datetime
    intent: Optional[str] = None
    sentiment: Optional[str] = None
    priority: Optional[str] = None


class RecentNotificationsResponse(BaseModel):
    """Réponse pour les notifications récentes"""
    success: bool
    timestamp: datetime
    counts: Dict[str, int]
    comments: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    lives: List[Dict[str, Any]]


class ReplyMessageRequest(BaseModel):
    """Requête pour répondre à un message"""
    text: str = Field(..., min_length=1, max_length=2000)
    quick_replies: Optional[List[Dict[str, str]]] = None
    template_name: Optional[str] = None


class StreamEvent(BaseModel):
    """Événement pour le stream SSE"""
    id: int
    type: str
    object: str
    timestamp: Optional[datetime] = None
    data: Dict[str, Any]


# ==================== SCHÉMAS POUR LA PAGINATION ====================

class PaginatedResponse(BaseModel):
    """Réponse paginée générique"""
    success: bool
    data: List[Dict[str, Any]]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_previous: bool


class PaginatedCommentsResponse(PaginatedResponse):
    """Réponse paginée pour les commentaires"""
    data: List[Dict[str, Any]]


class PaginatedMessagesResponse(PaginatedResponse):
    """Réponse paginée pour les messages"""
    data: List[Dict[str, Any]]


class PaginatedPostsResponse(PaginatedResponse):
    """Réponse paginée pour les posts"""
    data: List[Dict[str, Any]]


# ==================== SCHÉMAS POUR LES STATISTIQUES ====================

class FacebookStatsResponse(BaseModel):
    """Statistiques Facebook"""
    success: bool
    period: str
    total_posts: int = 0
    total_comments: int = 0
    total_messages: int = 0
    total_lives: int = 0
    active_lives: int = 0
    engagement_rate: float = 0.0
    avg_response_time_minutes: Optional[float] = None
    top_pages: List[Dict[str, Any]]
    recent_activity: List[Dict[str, Any]]


class CommentStatsResponse(BaseModel):
    """Statistiques sur les commentaires"""
    total: int
    processed: int
    pending: int
    by_intent: Dict[str, int]
    by_sentiment: Dict[str, int]
    by_hour: Dict[str, int]
    avg_processing_time_ms: Optional[float] = None


# ==================== SCHÉMAS POUR LA CONFIGURATION ====================

class AutoReplyConfig(BaseModel):
    """Configuration de l'auto-réponse"""
    enabled: bool = True
    greeting_message: Optional[str] = None
    away_message: Optional[str] = None
    response_delay_seconds: int = Field(30, ge=0, le=3600)
    working_hours_start: Optional[str] = None  # Format: "09:00"
    working_hours_end: Optional[str] = None    # Format: "18:00"
    exclude_intents: List[str] = []


class NLPConfig(BaseModel):
    """Configuration NLP"""
    model_config = {"protected_namespaces": ()}  # ⭐ AJOUTE CETTE LIGNE
    
    version: str = "1.0.0"  # ⭐ CHANGE: model_version → version
    confidence_threshold: float = Field(0.7, ge=0.1, le=1.0)
    auto_categorize: bool = True
    extract_entities: bool = True
    languages: List[str] = ["fr", "en"]


class FacebookConfigResponse(BaseModel):
    """Configuration Facebook complète"""
    success: bool
    page_id: str
    page_name: str
    auto_reply: AutoReplyConfig
    nlp: NLPConfig
    webhook_subscribed: bool
    last_sync: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class UpdateConfigRequest(BaseModel):
    """Requête de mise à jour de configuration"""
    auto_reply: Optional[AutoReplyConfig] = None
    nlp: Optional[NLPConfig] = None
    

CommentResponse = FacebookCommentResponse
LiveVideoResponse = FacebookLiveVideoResponse  
PostResponse = FacebookPostResponse
MessageTemplateResponse = FacebookMessageTemplateResponse
MessageResponse = FacebookMessageResponse



__all__ = [
    # Request schemas
    'FacebookConnectRequest',
    'FacebookCallbackRequest',
    'SelectPageRequest',
    'WebhookSubscriptionRequest',
    'SyncRequest',
    'BulkProcessRequest',
    'ExportCommentsRequest',
    'ReplyMessageRequest',
    'UpdateConfigRequest',
    
    # Response schemas  
    'FacebookConnectResponse',
    'FacebookAuthResponse',
    'FacebookPageResponse',
    'SelectPageResponse',
    'FacebookPostResponse',
    'FacebookLiveVideoResponse',
    'FacebookCommentResponse',
    'FacebookMessageTemplateResponse',
    'FacebookMessageResponse',
    'MessageResponse',
    'WebhookSubscriptionResponse',
    'WebhookHealthResponse',
    'BulkProcessResponse',
    'ExportCommentsResponse',
    'LiveAnalyticsResponse',
    'RecentNotificationsResponse',
    
    # Webhook schemas
    'FacebookWebhookChallenge',
    'FacebookWebhookEvent',
    
    # Database schemas
    'FacebookUserCreate',
    'FacebookUserUpdate',
    'FacebookPageCreate',
    'FacebookPageUpdate',
    'FacebookMessageTemplateCreate',
    'FacebookMessageTemplateUpdate',
    'FacebookMessageCreate',
    'FacebookMessageUpdate',
    
    # Filter schemas
    'CommentFilter',
    'PostFilter',
    'LiveVideoFilter',
    
    # Stats & Config schemas
    'FacebookStatsResponse',
    'FacebookConfigResponse',
    
    # Aliases (pour compatibilité)
    'CommentResponse',
    'LiveVideoResponse',
    'PostResponse',
    
    # Enums
    'CommentStatus',
    'MessageTemplateType',
    'MessageDirection',
    'MessageStatus',
    'ExportFormat',
]