from fastapi import Query
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from uuid import UUID
from enum import Enum


# ==================== ENUMS ====================

class CommentStatus(str, Enum):
    NEW = "new"
    PROCESSING = "processing"
    PROCESSED = "processed"
    ERROR = "error"
    NEEDS_REVIEW = "needs_review"


class MessageDirection(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class SyncType(str, Enum):
    POSTS = "posts"
    COMMENTS = "comments"
    ALL = "all"


class MessageTemplateType(str, Enum):
    CONFIRMATION_ACHAT = "confirmation_achat"
    DEMANDE_COORDONNEES = "demande_coordonnees"
    COMMANDE_CONFIRMEE = "commande_confirmee"
    CORRECTION_MESSAGE = "correction_message"
    STOCK_INSUFFISANT = "stock_insuffisant"
    REMERCIEMENT = "remerciement"


# ==================== AUTHENTICATION ====================

class FacebookConnectRequest(BaseModel):
    state: Optional[str] = None


class FacebookConnectResponse(BaseModel):
    success: bool
    auth_url: str
    state: str


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
    fan_count: int = 0
    cover_photo_url: Optional[str] = None
    profile_pic_url: Optional[str] = None
    access_token: str = ""
    is_selected: bool = False

    class Config:
        from_attributes = True
        extra = "ignore"


class FacebookAuthResponse(BaseModel):
    success: bool
    message: str
    user_info: FacebookUserInfo
    pages: List[FacebookPageInfo]


# ==================== PAGES MANAGEMENT ====================

class FacebookPageResponse(BaseModel):
    id: UUID
    page_id: str
    name: str
    category: Optional[str] = None
    profile_pic_url: Optional[str] = None
    cover_photo_url: Optional[str] = None
    fan_count: int = 0
    is_selected: bool = False
    auto_reply_enabled: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SelectPageRequest(BaseModel):
    page_id: str
    auto_reply_enabled: bool = True 

class SelectPageResponse(BaseModel):
    success: bool
    message: str
    page: FacebookPageResponse


# ==================== SYNC ====================

class SyncRequest(BaseModel):
    page_id: str
    sync_type: SyncType = SyncType.ALL


# ==================== COMMENTS ====================

class FacebookCommentResponse(BaseModel):
    id: str
    message: Optional[str] = None
    user_name: Optional[str] = None
    post_id: Optional[str] = None
    status: Optional[str] = None
    intent: Optional[str] = None
    sentiment: Optional[str] = None
    created_at: Optional[datetime] = None
    detected_code_article: Optional[str] = None
    detected_quantity: Optional[int] = None

    class Config:
        from_attributes = True


# ==================== POSTS WITH COMMENTS ====================

class CommentDetailResponse(BaseModel):
    id: str
    message: str
    user_name: str
    post_id: str
    status: Optional[str] = None
    intent: Optional[str] = None
    sentiment: Optional[str] = None
    priority: Optional[str] = None
    detected_code_article: Optional[str] = None
    detected_quantity: Optional[int] = None
    created_at: Optional[str] = None
    facebook_created_time: Optional[str] = None
    updated_at: Optional[str] = None
    
    class Config:
        from_attributes = True


# ⭐⭐ CORRECTION PRINCIPALE ⭐⭐
class PostDetailResponse(BaseModel):
    success: bool
    post: Dict[str, Any]  # Accepte le dictionnaire complet du post
    comments_count: int
    reactions_count: int
    
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    )


# ⭐⭐ CORRECTION POUR PostListResponse ⭐⭐
class FacebookPostDetail(BaseModel):
    id: str
    facebook_post_id: str
    message: Optional[str] = None
    story: Optional[str] = None
    likes_count: int = 0
    comments_count: int = 0
    shares_count: int = 0
    post_type: str = "post"
    page_id: str  # Change de UUID à string
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    facebook_created_time: Optional[str] = None
    comments: List[CommentDetailResponse] = []
    insights: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )


class PostListResponse(BaseModel):
    success: bool = True
    count: int
    total: int
    page_id: str
    page_name: str
    posts: List[Dict[str, Any]]  # Accepte les dictionnaires
    
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )


class FacebookPostWithCommentsResponse(BaseModel):
    id: str
    facebook_post_id: str
    message: str
    story: Optional[str]
    post_type: str
    created_at: Optional[datetime]
    facebook_created_time: Optional[datetime]
    likes_count: int
    comments_count: int
    shares_count: int
    page_id: str
    comments: List[CommentDetailResponse] = []


# ==================== MESSAGES ====================

class FacebookMessageResponse(BaseModel):
    id: UUID
    customer_facebook_id: Optional[str] = None
    message_type: str
    content: str
    status: str
    direction: str
    facebook_page_id: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReplyMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


# ==================== LIVE VIDEOS ====================

class FacebookLiveVideoResponse(BaseModel):
    id: UUID
    facebook_video_id: str
    title: Optional[str] = None
    status: str
    total_comments: int = 0
    total_orders: int = 0
    total_revenue: float = 0.0
    actual_start_time: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class FacebookLiveVideoWithCommentsResponse(BaseModel):
    id: str
    facebook_video_id: str
    title: str
    description: Optional[str]
    status: str
    stream_url: Optional[str]
    permalink_url: Optional[str]
    created_at: Optional[datetime]
    actual_start_time: Optional[datetime]
    end_time: Optional[datetime]
    viewers_count: int
    duration: Optional[int]
    page_id: str
    auto_process_comments: bool
    notify_on_new_orders: bool
    comments: List[CommentDetailResponse] = []


# ⭐⭐ CORRECTION POUR LiveVideoListResponse ⭐⭐
class LiveVideoListResponse(BaseModel):
    success: bool
    count: int
    total: int
    page_id: str
    page_name: str
    live_videos: List[Dict[str, Any]]  # Accepte les dictionnaires
    
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )


# ⭐⭐ CORRECTION POUR LiveVideoDetailResponse ⭐⭐
class LiveVideoDetailResponse(BaseModel):
    success: bool
    live_video: Dict[str, Any]  # Accepte le dictionnaire complet
    comments_count: int
    viewers_count: int
    insights: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True
    )


# ==================== WEBHOOKS ====================

class FacebookWebhookChallenge(BaseModel):
    hub_mode: str = Query(..., alias="hub.mode")
    hub_challenge: str = Query(..., alias="hub.challenge")
    hub_verify_token: str = Query(..., alias="hub.verify_token")


class FacebookWebhookEvent(BaseModel):
    object: str
    entry: List[Dict[str, Any]]


class WebhookSubscriptionRequest(BaseModel):
    page_id: str
    force_resubscribe: bool = False


# ==================== NOTIFICATIONS ====================

class NotificationItem(BaseModel):
    id: str
    type: str
    message: str
    user: Optional[str] = None
    page: Optional[str] = None
    timestamp: datetime
    intent: Optional[str] = None
    sentiment: Optional[str] = None


class RecentNotificationsResponse(BaseModel):
    success: bool
    timestamp: datetime
    counts: Dict[str, int]
    comments: List[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    lives: List[Dict[str, Any]]


# ==================== BULK OPERATIONS ====================

class BulkProcessRequest(BaseModel):
    comment_ids: List[str]
    action: Literal["mark_read", "reply_all", "export", "categorize"]


class BulkProcessResponse(BaseModel):
    success: bool
    action: str
    processed: int
    results: List[Dict[str, Any]]


# ==================== EXPORT ====================

class ExportCommentsRequest(BaseModel):
    format: ExportFormat = ExportFormat.JSON
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ExportCommentsResponse(BaseModel):
    success: bool
    format: str
    count: int
    data: Optional[List[Dict[str, Any]]] = None


# ==================== MESSAGE TEMPLATES ====================

class FacebookMessageTemplateResponse(BaseModel):
    id: UUID
    template_type: str
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== LIVE ANALYTICS ====================

class LiveAnalyticsResponse(BaseModel):
    success: bool
    live_id: str
    live_title: Optional[str] = None
    status: str
    duration: Optional[float] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    analytics: Dict[str, Any]


# ==================== WEBHOOK HEALTH ====================

class WebhookHealthResponse(BaseModel):
    success: bool
    timestamp: datetime
    subscriptions: Dict[str, Any]
    recent_webhooks: List[Dict[str, Any]]
    webhook_url: Optional[str] = None


# ==================== ALIASES POUR COMPATIBILITÉ ====================

CommentResponse = FacebookCommentResponse
LiveVideoResponse = FacebookLiveVideoResponse
PostResponse = FacebookPageResponse
MessageTemplateResponse = FacebookMessageTemplateResponse
MessageResponse = FacebookMessageResponse


# ==================== EXPORT DE TOUS LES SCHÉMAS ====================

__all__ = [
    # Enums
    'CommentStatus',
    'MessageDirection',
    'MessageStatus',
    'ExportFormat',
    'SyncType',
    'MessageTemplateType',
    
    # Authentication
    'FacebookConnectRequest',
    'FacebookConnectResponse',
    'FacebookUserInfo',
    'FacebookPageInfo',
    'FacebookAuthResponse',
    
    # Pages
    'FacebookPageResponse',
    'SelectPageRequest',
    'SelectPageResponse',
    
    # Sync
    'SyncRequest',
    
    # Comments
    'FacebookCommentResponse',
    'CommentDetailResponse',
    
    # Posts
    'PostDetailResponse',
    'FacebookPostDetail',
    'PostListResponse',
    'FacebookPostWithCommentsResponse',
    
    # Messages
    'FacebookMessageResponse',
    'ReplyMessageRequest',
    
    # Live Videos
    'FacebookLiveVideoResponse',
    'FacebookLiveVideoWithCommentsResponse',
    'LiveVideoListResponse',
    'LiveVideoDetailResponse',
    
    # Webhooks
    'FacebookWebhookChallenge',
    'FacebookWebhookEvent',
    'WebhookSubscriptionRequest',
    
    # Notifications
    'NotificationItem',
    'RecentNotificationsResponse',
    
    # Bulk Operations
    'BulkProcessRequest',
    'BulkProcessResponse',
    
    # Export
    'ExportCommentsRequest',
    'ExportCommentsResponse',
    
    # Message Templates
    'FacebookMessageTemplateResponse',
    
    # Live Analytics
    'LiveAnalyticsResponse',
    
    # Webhook Health
    'WebhookHealthResponse',
    
    # Aliases
    'CommentResponse',
    'LiveVideoResponse',
    'PostResponse',
    'MessageTemplateResponse',
    'MessageResponse',
]