# app/api/v1/endpoints/facebook.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
import httpx
from sqlalchemy.orm import Session, joinedload
from typing import Dict, List, Optional, Any, AsyncGenerator
import logging
import json
import hashlib
import hmac
from uuid import UUID
import asyncio

from app.db import get_db
from app.services.facebook_auth import facebook_auth_service
from app.services.facebook_webhook import FacebookWebhookService
from app.services.facebook_graph_api import FacebookGraphAPIService
from app.schemas.facebook import (
    FacebookConnectRequest,
    FacebookConnectResponse,
    FacebookAuthResponse,
    FacebookPageResponse,
    FacebookWebhookChallenge,
    FacebookWebhookEvent,
    SelectPageRequest,
    SelectPageResponse,
    SyncRequest,
    
    FacebookCommentResponse as CommentResponse,      # Alias local
    MessageResponse,
    FacebookLiveVideoResponse as LiveVideoResponse,  # Alias local  
    FacebookPostResponse as PostResponse,            # Alias local
    WebhookSubscriptionRequest,
)
from app.models.facebook import (
    FacebookComment, FacebookLiveVideo, FacebookMessage, 
    FacebookPost, FacebookUser, FacebookPage, FacebookWebhookLog,
    FacebookMessageTemplate, FacebookWebhookSubscription
)
from app.core.security import get_current_seller
from app.core.config import settings
from app.services.nlp_service import NLPService

router = APIRouter()
logger = logging.getLogger(__name__)

# ⭐ Services
facebook_webhook_service = FacebookWebhookService()
facebook_graph_service = FacebookGraphAPIService()
nlp_service = NLPService()
CommentResponse = CommentResponse
MessageResponse = MessageResponse
# ==================== AUTHENTICATION & CONNECTION ====================

@router.get("/login", response_model=FacebookConnectResponse)
async def facebook_login(
    request: Request,
    fb_request: FacebookConnectRequest = Depends(),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Génère l'URL OAuth pour la connexion Facebook
    """
    try:
        # Vérifier si l'utilisateur a déjà un compte Facebook connecté
        existing_user = db.query(FacebookUser).filter(
            FacebookUser.seller_id == current_seller.id,
            FacebookUser.is_active == True
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Un compte Facebook est déjà connecté. Déconnectez-vous d'abord."
            )
        
        # Générer l'URL OAuth avec les permissions étendues
        state = fb_request.state or str(current_seller.id)
        permissions = [
            "pages_show_list",
            "pages_read_engagement",  # Pour les posts, commentaires
            "pages_manage_posts",     # Pour publier
            "pages_messaging",        # Pour les messages
            "pages_read_user_content", # Pour lire le contenu utilisateur
            "pages_manage_metadata",  # Pour gérer les métadonnées
            "business_management"     # Pour la gestion business
        ]
        
        auth_url = facebook_auth_service.get_oauth_url(state, permissions)
        
        return FacebookConnectResponse(
            success=True,
            auth_url=auth_url,
            state=state
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'URL OAuth: {e}")
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de la connexion à Facebook"
        )

# [Les autres endpoints d'authentification restent similaires...]

# ==================== WEBHOOK MANAGEMENT ====================

@router.post("/webhook/subscribe")
async def subscribe_to_webhooks(
    request: WebhookSubscriptionRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Souscrit aux webhooks Facebook pour une page
    """
    try:
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == request.page_id,
            FacebookPage.seller_id == current_seller.id,
            FacebookPage.is_selected == True
        ).first()
        
        if not page:
            raise HTTPException(status_code=404, detail="Page non trouvée ou non sélectionnée")
        
        # Vérifier si déjà souscrit
        existing_sub = db.query(FacebookWebhookSubscription).filter(
            FacebookWebhookSubscription.page_id == page.id
        ).first()
        
        if existing_sub and not request.force_resubscribe:
            return {
                "success": True,
                "message": "Déjà souscrit aux webhooks",
                "subscription_id": existing_sub.id
            }
        
        # Souscrire aux webhooks via Graph API
        subscription_fields = [
            "feed",           # Posts, likes, comments
            "conversations",  # Messages
            "messages",       # Messages Messenger
            "messaging_postbacks",  # Actions messages
            "messaging_optins",     # Opt-ins
            "messaging_referrals",  # Références
            "message_deliveries",   # Livraison messages
            "message_reads",        # Messages lus
            "messaging_handovers",  # Transferts
            "messaging_policy_enforcement",  # Politique
            "live_videos",    # Lives
            "video_publishing",  # Publications vidéos
            "ratings",        # Évaluations
            "mention",        # Mentions
            "standby"         # Mode veille
        ]
        
        # Créer l'URL du webhook
        webhook_url = f"{settings.APP_URL}/api/v1/facebook/webhook"
        
        async with httpx.AsyncClient() as client:
            # Souscrire aux webhooks
            response = await client.post(
                f"https://graph.facebook.com/v18.0/{page.page_id}/subscribed_apps",
                params={
                    "subscribed_fields": ",".join(subscription_fields),
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Erreur subscription: {response.text}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Erreur Facebook: {response.json().get('error', {}).get('message', 'Unknown')}"
                )
            
            result = response.json()
            
            # Enregistrer la subscription en base
            if existing_sub:
                subscription = existing_sub
                subscription.subscribed_fields = json.dumps(subscription_fields)
                subscription.webhook_url = webhook_url
                subscription.is_active = True
                subscription.last_sync = datetime.utcnow()
            else:
                subscription = FacebookWebhookSubscription(
                    page_id=page.id,
                    subscription_id=result.get("id"),
                    subscribed_fields=json.dumps(subscription_fields),
                    webhook_url=webhook_url,
                    is_active=True,
                    last_sync=datetime.utcnow()
                )
                db.add(subscription)
            
            db.commit()
            
            return {
                "success": True,
                "message": "Webhooks souscrits avec succès",
                "subscription_id": subscription.id,
                "fields": subscription_fields,
                "webhook_url": webhook_url
            }
            
    except Exception as e:
        logger.error(f"Erreur subscription webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/webhook")
async def facebook_webhook_challenge(
    challenge: FacebookWebhookChallenge = Depends()
):
    """
    Validation du webhook Facebook (GET)
    """
    if challenge.hub_mode == "subscribe" and challenge.hub_verify_token == settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN:
        logger.info(f"✅ Webhook Facebook validé avec succès. Challenge: {challenge.hub_challenge}")
        return int(challenge.hub_challenge)
    
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("/webhook")
async def facebook_webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Reçoit et traite les événements webhook de Facebook
    """
    try:
        # Lire le corps brut pour vérifier la signature
        raw_body = await request.body()
        body_json = json.loads(raw_body.decode('utf-8'))
        
        # Vérifier la signature X-Hub-Signature
        signature = request.headers.get("x-hub-signature")
        if signature and not facebook_webhook_service.verify_signature(raw_body, signature):
            logger.error("❌ Signature webhook invalide")
            raise HTTPException(status_code=403, detail="Invalid signature")
        
        # Journaliser l'événement brut
        webhook_log = FacebookWebhookLog(
            object_type=body_json.get("object", "unknown"),
            event_type="webhook_received",
            entry_id=body_json.get("entry", [{}])[0].get("id") if body_json.get("entry") else None,
            payload=body_json,
            signature=signature,
            received_at=datetime.utcnow()
        )
        db.add(webhook_log)
        db.commit()
        
        # Traiter dans une tâche de fond pour répondre rapidement à Facebook
        background_tasks.add_task(
            process_webhook_async,
            webhook_log.id,
            body_json,
            db
        )
        
        logger.info(f"📥 Webhook reçu: {body_json.get('object')}. Traitement en background.")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def process_webhook_async(webhook_log_id: int, body_json: dict, db: Session):
    """Traite le webhook de manière asynchrone"""
    try:
        # Récupérer le log
        webhook_log = db.query(FacebookWebhookLog).get(webhook_log_id)
        if not webhook_log:
            logger.error(f"Log webhook {webhook_log_id} non trouvé")
            return
        
        object_type = body_json.get("object")
        entries = body_json.get("entry", [])
        
        for entry in entries:
            # Identifier la page
            page_id = entry.get("id")
            page = db.query(FacebookPage).filter(FacebookPage.page_id == page_id).first()
            
            if not page:
                logger.warning(f"Page {page_id} non trouvée en base")
                continue
            
            # Traiter les changements
            changes = entry.get("changes", [])
            for change in changes:
                await process_webhook_change(change, page, db)
            
            # Traiter les messages Messenger
            messaging = entry.get("messaging", [])
            for message_event in messaging:
                await process_messaging_event(message_event, page, db)
            
            # Traiter les standbys (mode veille)
            standby = entry.get("standby", [])
            for standby_event in standby:
                await process_standby_event(standby_event, page, db)
        
        # Marquer comme traité
        webhook_log.processed = True
        webhook_log.processed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"✅ Webhook {webhook_log_id} traité avec succès")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement webhook async: {e}", exc_info=True)
        db.rollback()

async def process_webhook_change(change: dict, page: FacebookPage, db: Session):
    """Traite un changement de webhook"""
    field = change.get("field")
    value = change.get("value")
    
    logger.info(f"🔄 Changement détecté: {field} pour page {page.page_id}")
    
    if field == "feed":
        await process_feed_change(value, page, db)
    elif field == "conversations":
        await process_conversations_change(value, page, db)
    elif field == "live_videos":
        await process_live_videos_change(value, page, db)
    elif field == "ratings":
        await process_ratings_change(value, page, db)
    elif field == "mention":
        await process_mention_change(value, page, db)

async def process_feed_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de feed (posts, commentaires)"""
    item = value.get("item")
    verb = value.get("verb")
    post_id = value.get("post_id")
    comment_id = value.get("comment_id")
    parent_id = value.get("parent_id")  # Pour les réponses aux commentaires
    
    if item == "post" and verb == "add":
        # Nouveau post
        await fetch_and_save_post(post_id, page, db)
        
    elif item == "comment" and verb == "add":
        # Nouveau commentaire
        await fetch_and_save_comment(comment_id, page, db)
        
        # Analyser l'intention avec NLP
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id
        ).first()
        
        if comment:
            # Analyser l'intention
            intent = nlp_service.analyze_comment_intent(comment.message)
            comment.intent = intent.get("intent")
            comment.sentiment = intent.get("sentiment")
            comment.entities = json.dumps(intent.get("entities", []))
            
            # Marquer comme prioritaire si nécessaire
            if intent.get("priority", False):
                comment.priority = "high"
            
            db.commit()
            
            # Notifier en temps réel si configuré
            await notify_real_time_comment(comment, page)
    
    elif item == "comment" and verb == "edit":
        # Commentaire modifié
        await update_comment(comment_id, page, db)
    
    elif item == "comment" and verb == "remove":
        # Commentaire supprimé
        await mark_comment_deleted(comment_id, db)

async def process_messaging_event(event: dict, page: FacebookPage, db: Session):
    """Traite les événements Messenger"""
    sender = event.get("sender", {}).get("id")
    recipient = event.get("recipient", {}).get("id")
    timestamp = event.get("timestamp")
    
    # Message texte
    if "message" in event:
        message_data = event["message"]
        message_id = message_data.get("mid")
        text = message_data.get("text", "")
        
        # Sauvegarder le message
        message = FacebookMessage(
            message_id=message_id,
            sender_id=sender,
            recipient_id=recipient,
            page_id=page.page_id,
            message_type="text",
            content=text,
            direction="incoming",
            status="received",
            metadata=json.dumps({
                "quick_reply": message_data.get("quick_reply"),
                "attachments": message_data.get("attachments"),
                "is_echo": message_data.get("is_echo", False)
            })
        )
        db.add(message)
        db.commit()
        
        # Analyser avec NLP
        intent = nlp_service.analyze_message_intent(text)
        message.intent = intent.get("intent")
        message.sentiment = intent.get("sentiment")
        db.commit()
        
        # Réponse automatique si configurée
        await handle_auto_reply(message, page, db)
    
    # Postback (boutons)
    elif "postback" in event:
        postback = event["postback"]
        payload = postback.get("payload")
        
        message = FacebookMessage(
            message_id=f"postback_{timestamp}",
            sender_id=sender,
            recipient_id=recipient,
            page_id=page.page_id,
            message_type="postback",
            content=payload,
            direction="incoming",
            status="received",
            metadata=json.dumps(postback)
        )
        db.add(message)
        db.commit()
        
        await handle_postback(payload, sender, page, db)
    
    # Livraison message
    elif "delivery" in event:
        mids = event["delivery"].get("mids", [])
        for mid in mids:
            message = db.query(FacebookMessage).filter(
                FacebookMessage.message_id == mid
            ).first()
            if message:
                message.status = "delivered"
    
    # Lecture message
    elif "read" in event:
        watermark = event["read"].get("watermark")
        # Marquer les messages comme lus

async def process_live_videos_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de lives vidéos"""
    video_id = value.get("video_id")
    status = value.get("status")
    
    if not video_id:
        return
    
    # Récupérer les infos du live
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://graph.facebook.com/v18.0/{video_id}",
            params={
                "fields": "id,title,description,status,creation_time,"
                         "scheduled_start_time,live_views,end_time,"
                         "permalink_url,from",
                "access_token": page.page_access_token
            }
        )
        
        if response.status_code == 200:
            video_data = response.json()
            
            # Chercher ou créer le live
            live = db.query(FacebookLiveVideo).filter(
                FacebookLiveVideo.facebook_video_id == video_id
            ).first()
            
            if live:
                # Mettre à jour
                live.status = video_data.get("status")
                live.live_views = video_data.get("live_views")
                if status == "live":
                    live.actual_start_time = datetime.utcnow()
                elif status == "archived":
                    live.end_time = datetime.utcnow()
                    live.duration = (datetime.utcnow() - live.actual_start_time).total_seconds() if live.actual_start_time else 0
            else:
                # Créer
                live = FacebookLiveVideo(
                    facebook_video_id=video_id,
                    page_id=page.page_id,
                    title=video_data.get("title"),
                    description=video_data.get("description"),
                    status=video_data.get("status"),
                    scheduled_start_time=datetime.fromisoformat(
                        video_data.get("scheduled_start_time").replace("Z", "+00:00")
                    ) if video_data.get("scheduled_start_time") else None,
                    actual_start_time=datetime.fromisoformat(
                        video_data.get("creation_time").replace("Z", "+00:00")
                    ) if video_data.get("creation_time") else None,
                    seller_id=page.seller_id
                )
                db.add(live)
            
            db.commit()
            logger.info(f"🎥 Live {video_id} mis à jour: {status}")

async def fetch_and_save_post(post_id: str, page: FacebookPage, db: Session):
    """Récupère et sauvegarde un post Facebook"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{post_id}",
                params={
                    "fields": "id,message,created_time,updated_time,full_picture,"
                             "permalink_url,likes.summary(true),comments.summary(true),"
                             "shares,attachments,type,is_hidden,is_published,"
                             "is_expired,is_instagram_eligible,is_popular",
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code == 200:
                post_data = response.json()
                
                # Vérifier si existe déjà
                existing = db.query(FacebookPost).filter(
                    FacebookPost.post_id == post_id
                ).first()
                
                if not existing:
                    post = FacebookPost(
                        post_id=post_id,
                        message=post_data.get("message"),
                        type=post_data.get("type"),
                        picture_url=post_data.get("full_picture"),
                        link=post_data.get("attachments", {}).get("data", [{}])[0].get("url") 
                             if post_data.get("attachments") else None,
                        likes_count=post_data.get("likes", {}).get("summary", {}).get("total_count", 0),
                        comments_count=post_data.get("comments", {}).get("summary", {}).get("total_count", 0),
                        shares_count=post_data.get("shares", {}).get("count", 0) 
                                if post_data.get("shares") else 0,
                        page_id=page.id,
                        seller_id=page.seller_id,
                        facebook_created_time=datetime.fromisoformat(
                            post_data.get("created_time").replace("Z", "+00:00")
                        ),
                        is_live_commerce=False,
                        metadata=json.dumps({
                            "is_hidden": post_data.get("is_hidden"),
                            "is_published": post_data.get("is_published"),
                            "is_popular": post_data.get("is_popular"),
                            "permalink": post_data.get("permalink_url")
                        })
                    )
                    db.add(post)
                    db.commit()
                    
                    # Analyser si c'est du live commerce
                    if post.message:
                        analysis = nlp_service.analyze_post_for_live_commerce(post.message)
                        if analysis.get("is_live_commerce"):
                            post.is_live_commerce = True
                            post.live_commerce_score = analysis.get("score")
                            db.commit()
                    
                    logger.info(f"📝 Nouveau post sauvegardé: {post_id}")
                    
    except Exception as e:
        logger.error(f"❌ Erreur fetch post {post_id}: {e}")

async def fetch_and_save_comment(comment_id: str, page: FacebookPage, db: Session):
    """Récupère et sauvegarde un commentaire"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{comment_id}",
                params={
                    "fields": "id,message,created_time,from{id,name},"
                             "like_count,comment_count,parent,attachment",
                    "access_token": page.page_access_token
                }
            )
            
            if response.status_code == 200:
                comment_data = response.json()
                
                # Vérifier si existe déjà
                existing = db.query(FacebookComment).filter(
                    FacebookComment.id == comment_id
                ).first()
                
                if not existing:
                    comment = FacebookComment(
                        id=comment_id,
                        message=comment_data.get("message"),
                        user_id=comment_data.get("from", {}).get("id"),
                        user_name=comment_data.get("from", {}).get("name"),
                        post_id=comment_data.get("parent", {}).get("id") 
                               if comment_data.get("parent") else None,
                        seller_id=page.seller_id,
                        page_id=page.id,
                        status="new",
                        facebook_created_time=datetime.fromisoformat(
                            comment_data.get("created_time").replace("Z", "+00:00")
                        ),
                        metadata=json.dumps({
                            "like_count": comment_data.get("like_count"),
                            "comment_count": comment_data.get("comment_count"),
                            "attachment": comment_data.get("attachment")
                        })
                    )
                    db.add(comment)
                    db.commit()
                    logger.info(f"💬 Nouveau commentaire sauvegardé: {comment_id}")
                    
    except Exception as e:
        logger.error(f"❌ Erreur fetch comment {comment_id}: {e}")

# ==================== REAL-TIME NOTIFICATIONS ====================

@router.get("/webhook/stream")
async def webhook_stream(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Stream SSE (Server-Sent Events) pour les notifications en temps réel
    """
    async def event_generator():
        """Générateur d'événements SSE"""
        last_id = None
        
        while True:
            # Récupérer les nouveaux événements
            query = db.query(FacebookWebhookLog).filter(
                FacebookWebhookLog.processed == True
            ).order_by(FacebookWebhookLog.processed_at.desc()).limit(10)
            
            if last_id:
                query = query.filter(FacebookWebhookLog.id > last_id)
            
            events = query.all()
            
            for event in events:
                last_id = event.id
                
                # Formater l'événement pour le SSE
                event_data = {
                    "id": event.id,
                    "type": event.event_type,
                    "object": event.object_type,
                    "timestamp": event.processed_at.isoformat() if event.processed_at else None,
                    "data": {
                        "entry_id": event.entry_id,
                        "seller_id": current_seller.id
                    }
                }
                
                yield f"data: {json.dumps(event_data)}\n\n"
            
            await asyncio.sleep(2)  # Poll toutes les 2 secondes
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Pour Nginx
        }
    )

@router.get("/notifications/recent")
async def get_recent_notifications(
    limit: int = Query(20, ge=1, le=100),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les notifications récentes
    """
    # Récupérer les pages du vendeur
    pages = db.query(FacebookPage).filter(
        FacebookPage.seller_id == current_seller.id
    ).all()
    
    page_ids = [page.id for page in pages]
    
    # Commentaires récents
    recent_comments = db.query(FacebookComment).filter(
        FacebookComment.page_id.in_(page_ids),
        FacebookComment.status == "new"
    ).order_by(FacebookComment.created_at.desc()).limit(limit).all()
    
    # Messages récents
    recent_messages = db.query(FacebookMessage).filter(
        FacebookMessage.page_id.in_([p.page_id for p in pages]),
        FacebookMessage.direction == "incoming",
        FacebookMessage.status == "received"
    ).order_by(FacebookMessage.created_at.desc()).limit(limit).all()
    
    # Lives actifs
    active_lives = db.query(FacebookLiveVideo).filter(
        FacebookLiveVideo.page_id.in_([p.page_id for p in pages]),
        FacebookLiveVideo.status == "live"
    ).order_by(FacebookLiveVideo.actual_start_time.desc()).all()
    
    return {
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
        "counts": {
            "new_comments": len(recent_comments),
            "new_messages": len(recent_messages),
            "active_lives": len(active_lives)
        },
        "comments": recent_comments,
        "messages": recent_messages,
        "lives": active_lives
    }

# ==================== MESSAGE MANAGEMENT ====================

@router.post("/messages/{message_id}/reply")
async def reply_to_message(
    message_id: str,
    reply_data: dict,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Répond à un message Messenger
    """
    try:
        # Récupérer le message original
        message = db.query(FacebookMessage).filter(
            FacebookMessage.message_id == message_id,
            FacebookMessage.page_id.in_(
                db.query(FacebookPage.page_id).filter(
                    FacebookPage.seller_id == current_seller.id
                )
            )
        ).first()
        
        if not message:
            raise HTTPException(status_code=404, detail="Message non trouvé")
        
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == message.page_id
        ).first()
        
        if not page:
            raise HTTPException(status_code=404, detail="Page non trouvée")
        
        # Envoyer la réponse via Graph API
        response = await facebook_graph_service.send_message(
            page_id=page.page_id,
            recipient_id=message.sender_id,
            message_text=reply_data.get("text"),
            access_token=page.page_access_token
        )
        
        if response.get("message_id"):
            # Sauvegarder la réponse envoyée
            reply_message = FacebookMessage(
                message_id=response["message_id"],
                sender_id=page.page_id,
                recipient_id=message.sender_id,
                page_id=page.page_id,
                message_type="text",
                content=reply_data.get("text"),
                direction="outgoing",
                status="sent",
                parent_message_id=message_id
            )
            db.add(reply_message)
            db.commit()
            
            # Marquer le message original comme répondu
            message.status = "replied"
            message.replied_at = datetime.utcnow()
            db.commit()
            
            return {
                "success": True,
                "message_id": response["message_id"],
                "recipient_id": message.sender_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Erreur Facebook: {response.get('error', 'Unknown')}"
            )
            
    except Exception as e:
        logger.error(f"❌ Erreur reply message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def handle_auto_reply(message: FacebookMessage, page: FacebookPage, db: Session):
    """Gère les réponses automatiques"""
    # Vérifier si l'auto-réponse est activée pour cette page
    if not page.auto_reply_enabled:
        return
    
    # Analyser l'intention pour une réponse appropriée
    intent = message.intent
    
    # Chercher un template de réponse
    template = db.query(FacebookMessageTemplate).filter(
        FacebookMessageTemplate.intent == intent,
        FacebookMessageTemplate.page_id == page.id,
        FacebookMessageTemplate.is_active == True
    ).first()
    
    if template:
        # Envoyer la réponse automatique
        await facebook_graph_service.send_message(
            page_id=page.page_id,
            recipient_id=message.sender_id,
            message_text=template.response_text,
            access_token=page.page_access_token
        )
        
        # Marquer comme répondu automatiquement
        message.status = "auto_replied"
        message.auto_reply_template_id = template.id
        db.commit()

# ==================== LIVE COMMERCE MANAGEMENT ====================

@router.get("/live/{live_id}/analytics")
async def get_live_analytics(
    live_id: str,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Récupère les analytics d'un live
    """
    live = db.query(FacebookLiveVideo).filter(
        FacebookLiveVideo.facebook_video_id == live_id,
        FacebookLiveVideo.seller_id == current_seller.id
    ).first()
    
    if not live:
        raise HTTPException(status_code=404, detail="Live non trouvé")
    
    # Récupérer les commentaires du live
    comments = db.query(FacebookComment).filter(
        FacebookComment.post_id == live_id,
        FacebookComment.seller_id == current_seller.id
    ).all()
    
    # Analyser les commentaires
    comment_analysis = {
        "total": len(comments),
        "by_intent": {},
        "by_sentiment": {},
        "top_keywords": []
    }
    
    for comment in comments:
        # Compter par intention
        intent = comment.intent or "unknown"
        comment_analysis["by_intent"][intent] = comment_analysis["by_intent"].get(intent, 0) + 1
        
        # Compter par sentiment
        sentiment = comment.sentiment or "neutral"
        comment_analysis["by_sentiment"][sentiment] = comment_analysis["by_sentiment"].get(sentiment, 0) + 1
    
    # Récupérer les metrics du live depuis Facebook
    async with httpx.AsyncClient() as client:
        # Récupérer la page pour le token
        page = db.query(FacebookPage).filter(
            FacebookPage.page_id == live.page_id
        ).first()
        
        if page:
            response = await client.get(
                f"https://graph.facebook.com/v18.0/{live_id}/video_insights",
                params={
                    "metric": "total_video_views,total_video_complete_views,"
                             "total_video_retention_graph,"
                             "total_video_avg_time_watched,"
                             "total_video_impressions,"
                             "total_video_engagement",
                    "access_token": page.page_access_token
                }
            )
            
            facebook_metrics = response.json().get("data", []) if response.status_code == 200 else []
    
    return {
        "success": True,
        "live_id": live_id,
        "live_title": live.title,
        "status": live.status,
        "duration": live.duration,
        "start_time": live.actual_start_time.isoformat() if live.actual_start_time else None,
        "end_time": live.end_time.isoformat() if live.end_time else None,
        "analytics": {
            "comments": comment_analysis,
            "facebook_metrics": facebook_metrics,
            "engagement_rate": len(comments) / max(live.live_views or 1, 1) * 100
        }
    }

# ==================== BULK OPERATIONS ====================

@router.post("/comments/bulk-process")
async def bulk_process_comments(
    comment_ids: List[str],
    action: str = Query(..., pattern="^(mark_read|reply_all|export|categorize)$"),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Traitement en masse des commentaires
    """
    try:
        # Récupérer les commentaires
        comments = db.query(FacebookComment).filter(
            FacebookComment.id.in_(comment_ids),
            FacebookComment.seller_id == current_seller.id
        ).all()
        
        if not comments:
            raise HTTPException(status_code=404, detail="Aucun commentaire trouvé")
        
        results = []
        
        if action == "mark_read":
            for comment in comments:
                comment.status = "processed"
                results.append({"id": comment.id, "status": "processed"})
            
            db.commit()
            
        elif action == "reply_all":
            # Récupérer la page
            page_id = comments[0].page_id if comments else None
            page = db.query(FacebookPage).filter(FacebookPage.id == page_id).first()
            
            if page:
                # Template de réponse
                reply_text = "Merci pour votre commentaire ! Nous reviendrons vers vous rapidement."
                
                for comment in comments:
                    try:
                        # Envoyer la réponse via Graph API
                        response = await facebook_graph_service.send_comment_reply(
                            comment_id=comment.id,
                            message_text=reply_text,
                            access_token=page.page_access_token
                        )
                        
                        if response.get("id"):
                            comment.status = "replied"
                            comment.replied_at = datetime.utcnow()
                            results.append({"id": comment.id, "reply_id": response["id"]})
                    except Exception as e:
                        results.append({"id": comment.id, "error": str(e)})
                
                db.commit()
        
        return {
            "success": True,
            "action": action,
            "processed": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur bulk process: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== EXPORT ====================

@router.get("/export/comments")
async def export_comments(
    format: str = Query("json", pattern="^(json|csv)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Exporte les commentaires
    """
    query = db.query(FacebookComment).filter(
        FacebookComment.seller_id == current_seller.id
    )
    
    if start_date:
        query = query.filter(FacebookComment.created_at >= start_date)
    if end_date:
        query = query.filter(FacebookComment.created_at <= end_date)
    
    comments = query.order_by(FacebookComment.created_at.desc()).all()
    
    if format == "json":
        return {
            "success": True,
            "format": "json",
            "count": len(comments),
            "data": [comment.to_dict() for comment in comments]
        }
    elif format == "csv":
        # Générer CSV
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # En-têtes
        writer.writerow([
            "ID", "Message", "User", "Post ID", "Status",
            "Intent", "Sentiment", "Created At", "Page"
        ])
        
        # Données
        for comment in comments:
            writer.writerow([
                comment.id,
                comment.message,
                comment.user_name,
                comment.post_id or "",
                comment.status,
                comment.intent or "",
                comment.sentiment or "",
                comment.created_at.isoformat() if comment.created_at else "",
                comment.page.name if comment.page else ""
            ])
        
        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=comments_{datetime.utcnow().date()}.csv"
            }
        )

# ==================== HEALTH & MONITORING ====================

@router.get("/webhook/health")
async def webhook_health(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """
    Vérifie l'état des webhooks
    """
    # Récupérer les subscriptions actives
    pages = db.query(FacebookPage).filter(
        FacebookPage.seller_id == current_seller.id,
        FacebookPage.is_selected == True
    ).all()
    
    subscriptions = []
    for page in pages:
        sub = db.query(FacebookWebhookSubscription).filter(
            FacebookWebhookSubscription.page_id == page.id,
            FacebookWebhookSubscription.is_active == True
        ).first()
        
        if sub:
            subscriptions.append({
                "page_id": page.page_id,
                "page_name": page.name,
                "subscription_id": sub.subscription_id,
                "last_sync": sub.last_sync.isoformat() if sub.last_sync else None,
                "fields": json.loads(sub.subscribed_fields) if sub.subscribed_fields else []
            })
    
    # Derniers webhooks reçus
    recent_webhooks = db.query(FacebookWebhookLog).order_by(
        FacebookWebhookLog.received_at.desc()
    ).limit(10).all()
    
    return {
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
        "subscriptions": {
            "count": len(subscriptions),
            "active": subscriptions
        },
        "recent_webhooks": [
            {
                "id": wh.id,
                "object": wh.object_type,
                "received_at": wh.received_at.isoformat() if wh.received_at else None,
                "processed": wh.processed
            }
            for wh in recent_webhooks
        ],
        "webhook_url": f"{settings.APP_URL}/api/v1/facebook/webhook"
    }

# ==================== UTILITY FUNCTIONS ====================

async def notify_real_time_comment(comment: FacebookComment, page: FacebookPage):
    """Notifie en temps réel un nouveau commentaire"""
    # Ici, vous pouvez intégrer avec:
    # - WebSockets
    # - Server-Sent Events (SSE)
    # - Webhooks externes
    # - Notifications push
    
    notification_data = {
        "type": "new_comment",
        "comment_id": comment.id,
        "message": comment.message[:100],  # Premier 100 caractères
        "user": comment.user_name,
        "page": page.name,
        "timestamp": datetime.utcnow().isoformat(),
        "intent": comment.intent,
        "sentiment": comment.sentiment,
        "priority": comment.priority
    }
    
    # Exemple: Envoyer à un WebSocket
    # await websocket_manager.broadcast(f"page_{page.id}", notification_data)
    
    logger.info(f"📢 Notification commentaire: {comment.id}")

async def handle_postback(payload: str, sender_id: str, page: FacebookPage, db: Session):
    """Gère les postbacks Messenger"""
    # Exemple de payload: "GET_STARTED", "VIEW_PRODUCTS", "CONTACT_SUPPORT"
    
    if payload == "GET_STARTED":
        # Message de bienvenue
        welcome_message = "Bienvenue sur notre page ! Comment puis-je vous aider ?"
        
        await facebook_graph_service.send_message(
            page_id=page.page_id,
            recipient_id=sender_id,
            message_text=welcome_message,
            access_token=page.page_access_token
        )
    
    # Sauvegarder l'interaction
    interaction = FacebookMessage(
        message_id=f"postback_{int(datetime.utcnow().timestamp())}",
        sender_id=sender_id,
        recipient_id=page.page_id,
        page_id=page.page_id,
        message_type="postback",
        content=payload,
        direction="incoming",
        status="processed",
        metadata=json.dumps({"handler": "postback"})
    )
    db.add(interaction)
    db.commit()

# Helper functions à compléter selon votre implémentation
async def process_conversations_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de conversations"""
    pass

async def process_ratings_change(value: dict, page: FacebookPage, db: Session):
    """Traite les changements de ratings"""
    pass

async def process_mention_change(value: dict, page: FacebookPage, db: Session):
    """Traite les mentions"""
    pass

async def process_standby_event(event: dict, page: FacebookPage, db: Session):
    """Traite les événements standby"""
    pass

async def update_comment(comment_id: str, page: FacebookPage, db: Session):
    """Met à jour un commentaire"""
    pass

async def mark_comment_deleted(comment_id: str, db: Session):
    """Marque un commentaire comme supprimé"""
    pass