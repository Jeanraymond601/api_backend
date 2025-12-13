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