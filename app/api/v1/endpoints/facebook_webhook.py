# app/api/v1/endpoints/facebook_webhook.py - VERSION CORRIGÉE
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import hashlib
import hmac
import json
from typing import Dict, Any
import logging

from app.db import get_db
from app.core.config import settings
from app.services.facebook_messenger_service import FacebookMessengerService

router = APIRouter(prefix="/facebook/webhook", tags=["facebook-webhook"])
logger = logging.getLogger(__name__)

# Clé secrète pour vérifier les webhooks
WEBHOOK_VERIFY_TOKEN = settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN
APP_SECRET = settings.FACEBOOK_APP_SECRET

@router.get("")
async def verify_webhook(
    request: Request,
    hub_mode: str = None,
    hub_challenge: str = None,
    hub_verify_token: str = None
):
    """Endpoint de vérification du webhook Facebook"""
    if hub_mode == "subscribe" and hub_verify_token == WEBHOOK_VERIFY_TOKEN:
        return int(hub_challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification failed")

@router.post("")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    """Reçoit les événements du webhook Facebook"""
    try:
        # Vérifier la signature
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        
        if APP_SECRET:
            expected_signature = "sha256=" + hmac.new(
                APP_SECRET.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                raise HTTPException(status_code=403, detail="Invalid signature")
        
        # Parser le JSON
        data = await request.json()
        
        logger.info(f"📨 Webhook reçu: {json.dumps(data, indent=2)[:500]}...")
        
        # Vérifier le type d'événement
        if data.get("object") == "page":
            for entry in data.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    await process_messaging_event(messaging_event, db)
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_messaging_event(event: Dict[str, Any], db: Session):
    """Traite un événement Messenger"""
    try:
        sender_id = event.get("sender", {}).get("id")
        recipient_id = event.get("recipient", {}).get("id")
        
        # Message texte
        if "message" in event:
            message = event["message"]
            text = message.get("text", "")
            mid = message.get("mid")
            
            logger.info(f"💬 Message reçu de {sender_id}: {text[:100]}...")
            
            # Traiter le message
            await handle_incoming_message(
                sender_id=sender_id,
                recipient_id=recipient_id,
                text=text,
                message_id=mid,
                db=db
            )
        
        # Postback (boutons, quick replies)
        elif "postback" in event:
            postback = event["postback"]
            payload = postback.get("payload")
            title = postback.get("title", "")
            
            logger.info(f"🔘 Postback de {sender_id}: {payload} ({title})")
            
            # Traiter le postback
            await handle_postback(
                sender_id=sender_id,
                recipient_id=recipient_id,
                payload=payload,
                title=title,
                db=db
            )
        
        # Quick reply (dans message)
        elif "message" in event and "quick_reply" in event["message"]:
            quick_reply = event["message"]["quick_reply"]
            payload = quick_reply.get("payload")
            
            logger.info(f"⚡ Quick reply de {sender_id}: {payload}")
            
            # Traiter le quick reply
            await handle_quick_reply(
                sender_id=sender_id,
                recipient_id=recipient_id,
                payload=payload,
                db=db
            )
        
        # Lecture du message
        elif "read" in event:
            logger.info(f"👁️ Message lu par {sender_id}")
            
        # Livraison du message
        elif "delivery" in event:
            logger.info(f"✓ Message délivré à {sender_id}")
            
    except Exception as e:
        logger.error(f"❌ Erreur traitement événement: {e}")

async def handle_incoming_message(
    sender_id: str,
    recipient_id: str,
    text: str,
    message_id: str,
    db: Session
):
    """Traite un message entrant texte"""
    try:
        messenger_service = FacebookMessengerService(db)
        
        # Enregistrer le message reçu
        await messenger_service.save_message_history(
            message_type="customer_message",
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_content=text,
            message_id=message_id,
            status="received"
        )
        
        # Log pour debug
        logger.info(f"📝 Message sauvegardé: {sender_id} -> {text[:50]}...")
        
        # Ici tu pourrais ajouter une logique de réponse automatique
        # Pour l'instant, juste logger
        text_lower = text.lower()
        
        # Réponses automatiques simples
        auto_responses = {
            "bonjour": "👋 Bonjour ! Comment puis-je vous aider ?",
            "salut": "👋 Salut ! En quoi puis-je vous assister ?",
            "merci": "😊 Je vous en prie !",
            "adresse": "📍 Veuillez envoyer votre adresse complète pour la livraison.",
            "téléphone": "📞 Veuillez envoyer votre numéro de téléphone.",
            "commande": "📦 Pour vérifier votre commande, donnez-moi votre numéro de commande.",
            "help": "ℹ️ Je peux vous aider avec: commandes, livraison, adresse, téléphone."
        }
        
        response = None
        for keyword, reply in auto_responses.items():
            if keyword in text_lower:
                response = reply
                break
        
        if response:
            # Récupérer le token de la page
            from app.models.facebook import FacebookPage
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == recipient_id
            ).first()
            
            if page and page.page_access_token:
                await messenger_service.send_private_message(
                    recipient_id=sender_id,
                    message=response,
                    page_access_token=page.page_access_token,
                    messaging_type="RESPONSE"
                )
                logger.info(f"🤖 Réponse automatique envoyée: {response[:50]}...")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement message: {e}")

async def handle_postback(
    sender_id: str,
    recipient_id: str,
    payload: str,
    title: str,
    db: Session
):
    """Traite un postback (bouton cliqué)"""
    try:
        logger.info(f"🔄 Traitement postback: {payload}")
        
        messenger_service = FacebookMessengerService(db)
        
        # Enregistrer le postback
        await messenger_service.save_message_history(
            message_type="postback",
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_content=f"POSTBACK: {payload} - {title}",
            status="received"
        )
        
        # Réponses selon le payload
        responses = {
            "GET_STARTED": "👋 Bienvenue ! Comment puis-je vous aider aujourd'hui ?",
            "SEND_ADDRESS": "📍 Parfait ! Veuillez envoyer votre adresse complète.",
            "SEND_PHONE": "📞 Excellent ! Envoyez-moi votre numéro de téléphone.",
            "NEED_HELP": "ℹ️ Je suis là pour vous aider ! Dites-moi ce dont vous avez besoin.",
            "TAKE_PHOTO": "📸 Super ! Prenez une photo de votre adresse écrite sur papier.",
            "WRITE_ADDRESS": "✍️ Parfait ! Écrivez votre adresse dans ce chat.",
            "LATER": "⏰ D'accord, vous pouvez envoyer votre adresse plus tard.",
            "CANCEL_ORDER": "❌ Je comprends. Voulez-vous vraiment annuler votre commande ?"
        }
        
        if payload in responses:
            # Récupérer le token de la page
            from app.models.facebook import FacebookPage
            page = db.query(FacebookPage).filter(
                FacebookPage.page_id == recipient_id
            ).first()
            
            if page and page.page_access_token:
                response_text = responses[payload]
                
                await messenger_service.send_private_message(
                    recipient_id=sender_id,
                    message=response_text,
                    page_access_token=page.page_access_token,
                    messaging_type="RESPONSE"
                )
                
                logger.info(f"✅ Réponse postback envoyée: {response_text[:50]}...")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement postback: {e}")

async def handle_quick_reply(
    sender_id: str,
    recipient_id: str,
    payload: str,
    db: Session
):
    """Traite un quick reply"""
    try:
        logger.info(f"⚡ Traitement quick reply: {payload}")
        
        messenger_service = FacebookMessengerService(db)
        
        # Enregistrer le quick reply
        await messenger_service.save_message_history(
            message_type="quick_reply",
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_content=f"QUICK_REPLY: {payload}",
            status="received"
        )
        
        # Les quick replies utilisent les mêmes payloads que les postbacks
        # Donc on peut réutiliser la même logique
        await handle_postback(
            sender_id=sender_id,
            recipient_id=recipient_id,
            payload=payload,
            title="Quick Reply",
            db=db
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement quick reply: {e}")

async def handle_message_delivery(event: Dict[str, Any], db: Session):
    """Traite la confirmation de livraison d'un message"""
    try:
        sender_id = event.get("sender", {}).get("id")
        mids = event.get("delivery", {}).get("mids", [])
        
        if mids:
            messenger_service = FacebookMessengerService(db)
            
            for mid in mids:
                # Mettre à jour le statut dans l'historique
                from app.models.message_history import MessengerMessage
                
                message = db.query(MessengerMessage).filter(
                    MessengerMessage.facebook_message_id == mid
                ).first()
                
                if message:
                    message.status = "delivered"
                    message.delivered_at = datetime.utcnow()
                    db.commit()
                    
                    logger.info(f"✓ Message délivré: {mid}")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement livraison: {e}")

async def handle_message_read(event: Dict[str, Any], db: Session):
    """Traite la confirmation de lecture d'un message"""
    try:
        sender_id = event.get("sender", {}).get("id")
        watermark = event.get("read", {}).get("watermark")
        
        messenger_service = FacebookMessengerService(db)
        
        # Mettre à jour les messages lus
        from app.models.message_history import MessengerMessage
        
        messages = db.query(MessengerMessage).filter(
            MessengerMessage.recipient_id == sender_id,
            MessengerMessage.status == "delivered"
        ).all()
        
        for message in messages:
            message.status = "read"
            message.read_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"👁️ Messages marqués comme lus par {sender_id}")
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement lecture: {e}")