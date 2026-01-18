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
    auto_reply_template = Column(Text, nullable=True) 
    auto_process_comments = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FacebookPost(Base):
    __tablename__ = "facebook_posts"

    # ID
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    
    # Post Info - CORRESPOND À LA TABLE SQL
    facebook_post_id = Column(String(100), unique=True, nullable=False, index=True)
    message = Column(Text, nullable=True)
    post_type = Column(String(50), nullable=True)  # ⭐ CHANGER 'type' en 'post_type'
    story = Column(Text, nullable=True)  # ⭐ AJOUTER ce champ
    
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
    __tablename__ = "live_streams"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    facebook_video_id = Column(String(100), unique=True, nullable=False, index=True)
    page_id = Column(String(100), nullable=False)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default='scheduled')
    scheduled_start_time = Column(DateTime(timezone=False), nullable=True)
    actual_start_time = Column(DateTime(timezone=False), nullable=True)
    end_time = Column(DateTime(timezone=False), nullable=True)
    total_comments = Column(Integer, default=0)
    total_orders = Column(Integer, default=0)
    total_revenue = Column(Numeric(10, 2), default=0.0)
    nlp_processed_comments = Column(Integer, default=0)
    ambiguous_comments = Column(Integer, default=0)
    auto_process_comments = Column(Boolean, default=True)
    notify_on_new_orders = Column(Boolean, default=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    created_at = Column(DateTime(timezone=False), server_default=func.now())
    updated_at = Column(DateTime(timezone=False), onupdate=func.now())


class FacebookComment(Base):
    __tablename__ = "facebook_comments"
    
    id = Column(String(100), primary_key=True)
    seller_id = Column(UUID(as_uuid=True), nullable=False)
    post_id = Column(String(100), nullable=True)
    user_id = Column(String(100), nullable=True)
    message = Column(Text, nullable=False)
    user_name = Column(String(255), nullable=True)
    facebook_created_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default='new')
    detected_code_article = Column(String(100), nullable=True)
    detected_product_name = Column(String(255), nullable=True)
    detected_quantity = Column(Integer, default=1)
    response_text = Column(Text, nullable=True)
    action_taken = Column(String(50), nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    extracted_data = Column(JSON, nullable=True)
    validation_data = Column(JSON, nullable=True)
    order_id = Column(String(50), nullable=True)
    confidence_score = Column(Numeric(3, 2), nullable=True)
    page_id = Column(UUID(as_uuid=True), nullable=True)
    intent = Column(String(50), nullable=True)
    sentiment = Column(String(50), nullable=True)
    entities = Column(JSON, nullable=True)
    priority = Column(String(20), nullable=True)


class FacebookMessage(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    customer_facebook_id = Column(String(100), nullable=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    message_type = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), default='pending')
    direction = Column(String(20), default='outgoing')
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ⭐ AJOUT: Champs pour l'intégration Facebook
    facebook_page_id = Column(String(100), nullable=True)
    message_id = Column(String(100), nullable=True)
    sender_id = Column(String(100), nullable=True)
    recipient_id = Column(String(100), nullable=True)
    message_metadata = Column(JSON, nullable=True)


class NLPProcessingLog(Base):
    __tablename__ = "nlp_processing_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    comment_id = Column(String(100), nullable=False)
    processor_version = Column(String(50), default='1.0.0')
    processing_time_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    detected_intent = Column(String(100), nullable=True)
    confidence_score = Column(Numeric(5, 2), nullable=True)
    is_ambiguous = Column(Boolean, nullable=True)
    requires_human_review = Column(Boolean, nullable=True)
    detected_products = Column(JSON, nullable=True)
    detected_quantities = Column(JSON, nullable=True)
    detected_colors = Column(JSON, nullable=True)
    detected_sizes = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    stack_trace = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())


class FacebookWebhookLog(Base):
    __tablename__ = "facebook_webhook_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    object_type = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    entry_id = Column(String(100), nullable=True)
    payload = Column(JSON, nullable=False)
    signature = Column(String(500), nullable=True)
    processed = Column(Boolean, default=False)
    processing_error = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    page_id = Column(String(100), nullable=True)
    http_method = Column(String(10), default='POST')
    status_code = Column(Integer, nullable=True)


class FacebookWebhookSubscription(Base):
    __tablename__ = "facebook_webhook_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    page_id = Column(String(100), nullable=False)
    subscription_type = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    last_received = Column(DateTime(timezone=True), nullable=True)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("sellers.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class FacebookMessageTemplate(Base):
    __tablename__ = "message_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    template_type = Column(String(50), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())