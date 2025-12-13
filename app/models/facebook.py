# app/models/facebook.py
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class FacebookUser(Base):
    __tablename__ = "facebook_users"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Facebook Info
    facebook_user_id = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    name = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    profile_pic_url = Column(Text, nullable=True)
    
    # Tokens
    short_lived_token = Column(Text, nullable=True)
    long_lived_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Permissions
    granted_permissions = Column(JSON, default=list)
    
    # App User Relation
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    last_sync = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FacebookPage(Base):
    __tablename__ = "facebook_pages"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Page Info
    page_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(255), nullable=True)
    about = Column(Text, nullable=True)
    cover_photo_url = Column(Text, nullable=True)
    profile_pic_url = Column(Text, nullable=True)
    fan_count = Column(Integer, default=0)
    
    # Access Token
    page_access_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Foreign Keys
    facebook_user_id = Column(UUID(as_uuid=True), ForeignKey("facebook_users.id"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    
    # Settings
    is_selected = Column(Boolean, default=False)
    auto_reply_enabled = Column(Boolean, default=False)
    auto_process_comments = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ⭐ SIMPLIFIE : Enlève la relation comments ici (gérée par backref dans FacebookComment)
    # comments = relationship(...)  # ← ENLÈVE CETTE LIGNE
    
    # Relation avec FacebookUser
    facebook_user = relationship("FacebookUser")  # ← Sans back_populates
    
    # Relation avec Seller
    seller = relationship("Seller")  # ← Sans back_populates


class FacebookPost(Base):
    __tablename__ = "facebook_posts"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Post Info
    post_id = Column(String(100), unique=True, nullable=False, index=True)
    message = Column(Text, nullable=True)
    type = Column(String(50), nullable=True)
    
    # Media
    picture_url = Column(Text, nullable=True)
    full_picture_url = Column(Text, nullable=True)
    link = Column(Text, nullable=True)
    
    # Stats
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    shares_count = Column(Integer, default=0)
    
    # Foreign Keys
    page_id = Column(UUID(as_uuid=True), ForeignKey("facebook_pages.id"), nullable=False)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    
    # Facebook Metadata
    facebook_created_time = Column(DateTime(timezone=True), nullable=False)
    updated_time = Column(DateTime(timezone=True), nullable=True)
    is_hidden = Column(Boolean, default=False)
    
    # Live Commerce
    is_live_commerce = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FacebookLiveVideo(Base):
    __tablename__ = "live_streams"  # Utilise votre table existante

    # ID (déjà dans votre schéma)
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Facebook Video Info
    facebook_video_id = Column(String(100), unique=True, nullable=False, index=True)
    page_id = Column(String(100), nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    
    # Status (utilise votre enum existant)
    status = Column(String(50), default='scheduled')
    
    # Timing
    scheduled_start_time = Column(DateTime(timezone=True), nullable=True)  # ⭐ CORRIGÉ: timezone=True
    actual_start_time = Column(DateTime(timezone=True), nullable=True)     # ⭐ CORRIGÉ: timezone=True
    end_time = Column(DateTime(timezone=True), nullable=True)             # ⭐ CORRIGÉ: timezone=True
    
    # Stats
    total_comments = Column(Integer, default=0)
    total_orders = Column(Integer, default=0)
    total_revenue = Column(Numeric(10, 2), default=0.0)
    nlp_processed_comments = Column(Integer, default=0)
    ambiguous_comments = Column(Integer, default=0)
    
    # Settings
    auto_process_comments = Column(Boolean, default=True)
    notify_on_new_orders = Column(Boolean, default=True)
    
    # Foreign Keys
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())   # ⭐ CORRIGÉ: timezone=True
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())         # ⭐ CORRIGÉ: timezone=True


class FacebookComment(Base):
    __tablename__ = "facebook_comments"

    # ID
    id = Column(String(100), primary_key=True)
    
    # Comment Info
    message = Column(Text, nullable=False)
    user_id = Column(String(100), nullable=True)
    user_name = Column(String(255), nullable=True)
    
    # ⭐ CORRECT : UN SEUL page_id (UUID)
    page_id = Column(UUID(as_uuid=True), ForeignKey('facebook_pages.id'), nullable=True)
    
    # ⭐ COLONNES NLP
    intent = Column(String(50), nullable=True)
    sentiment = Column(String(50), nullable=True)
    entities = Column(JSON, nullable=True)
    priority = Column(String(20), nullable=True)
    
    # Foreign Keys
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    post_id = Column(String(100), nullable=True)
    
    # Status
    status = Column(String(20), default='new')
    
    # NLP Processing
    detected_code_article = Column(String(100), nullable=True)
    detected_product_name = Column(String(255), nullable=True)
    detected_quantity = Column(Integer, default=1)
    confidence_score = Column(Numeric(3, 2), nullable=True)
    
    # Response
    response_text = Column(Text, nullable=True)
    action_taken = Column(String(50), nullable=True)
    
    # Extracted Data
    extracted_data = Column(JSON, nullable=True)
    validation_data = Column(JSON, nullable=True)
    
    # Order Link
    order_id = Column(String(50), nullable=True)
    
    # Facebook Metadata
    facebook_created_time = Column(DateTime(timezone=True), nullable=True)
    
    # Processing Info
    processing_time_ms = Column(Integer, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ⭐ SIMPLIFIE : Utilise backref OU rien
    page = relationship("FacebookPage", backref="comments")  # ← backref au lieu de back_populates
    
    # Relation avec Seller
    seller = relationship("Seller")  # ← Simple, sans back_populates

class FacebookMessage(Base):
    __tablename__ = "messages"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Message Info
    customer_facebook_id = Column(String(100), nullable=True)
    message_type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    
    # Status & Direction
    status = Column(String(20), default='pending')
    direction = Column(String(20), default='outgoing')
    
    # ⭐ AJOUT: Champ pour Facebook Page
    facebook_page_id = Column(String(100), nullable=True)
    
    # Foreign Keys
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    
    # Timestamps
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NLPProcessingLog(Base):
    __tablename__ = "nlp_processing_logs"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Comment Reference
    comment_id = Column(String(100), nullable=False)
    
    # Processing Info
    processor_version = Column(String(50), default='1.0.0')
    processing_time_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    
    # NLP Results
    detected_intent = Column(String(100), nullable=True)
    confidence_score = Column(Numeric(5, 2), nullable=True)  # ⭐ CORRIGÉ: Numeric au lieu de Integer
    is_ambiguous = Column(Boolean, nullable=True)
    requires_human_review = Column(Boolean, nullable=True)
    
    # Extracted Entities
    detected_products = Column(JSON, nullable=True)
    detected_quantities = Column(JSON, nullable=True)
    detected_colors = Column(JSON, nullable=True)
    detected_sizes = Column(JSON, nullable=True)
    
    # Error Handling
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    stack_trace = Column(Text, nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # ⭐ CORRIGÉ: timezone=True


class FacebookWebhookLog(Base):
    __tablename__ = "facebook_webhook_logs"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Webhook Info
    object_type = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    entry_id = Column(String(100), nullable=True)
    
    # ⭐ AJOUT: Page ID pour le filtrage
    page_id = Column(String(100), nullable=True)
    
    # Payload
    payload = Column(JSON, nullable=False)
    signature = Column(String(500), nullable=True)
    
    # ⭐ AJOUT: HTTP method et status code
    http_method = Column(String(10), default='POST')
    status_code = Column(Integer, nullable=True)
    
    # Processing
    processed = Column(Boolean, default=False)
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ⭐ NOUVEAU MODÈLE: Pour les subscriptions webhook
class FacebookWebhookSubscription(Base):
    __tablename__ = "facebook_webhook_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    page_id = Column(String(100), nullable=False)
    subscription_type = Column(String(50), nullable=False)  # feed, live_videos, conversations
    is_active = Column(Boolean, default=True)
    last_received = Column(DateTime(timezone=True), nullable=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
# ⭐ AJOUT: Modèle pour les templates de messages
class FacebookMessageTemplate(Base):
    __tablename__ = "message_templates"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Template Info
    template_type = Column(String(50), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<FacebookMessageTemplate(type='{self.template_type}')>"