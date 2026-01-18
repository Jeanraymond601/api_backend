# app/api/v1/endpoints/facebook_auto_reply.py - VERSION RÉELLE AVEC AUTO-REPLY
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel
import uuid
from datetime import datetime
import logging
import aiohttp
import asyncio

from app.db import get_db
from app.core.dependencies import get_current_seller

router = APIRouter(prefix="/facebook/auto-reply", tags=["facebook-auto-reply"])
logger = logging.getLogger(__name__)

# ================================
# MODÈLES PYDANTIC
# ================================

class AutoReplySettings(BaseModel):
    enabled: bool = True
    custom_message: Optional[str] = None
    template_name: Optional[str] = None

class TestAutoReplyRequest(BaseModel):
    comment_text: str
    customer_name: str = "Client Test"
    order_number: str = "SHO-20250116-9999"
    total_amount: float = 24.99

# ================================
# FONCTIONS UTILITAIRES
# ================================

def get_seller_id(seller):
    """Extrait le seller_id que seller soit un dict ou un objet"""
    if isinstance(seller, dict):
        return seller.get('seller_id')
    elif hasattr(seller, 'seller_id'):
        return seller.seller_id
    elif hasattr(seller, 'id'):
        return seller.id
    else:
        raise ValueError("Impossible de déterminer le seller_id")

def get_facebook_page_for_seller(db: Session, seller_id: uuid.UUID):
    """Récupère la page Facebook active du vendeur"""
    from app.models.facebook import FacebookPage
    return db.query(FacebookPage).filter(
        FacebookPage.seller_id == seller_id,
        FacebookPage.is_selected == True
    ).first()

async def get_facebook_token(db: Session, seller_id: uuid.UUID) -> Optional[str]:
    """Récupère le token Facebook pour un vendeur"""
    try:
        from app.models.facebook import FacebookPage
        
        # Chercher la page active/sélectionnée
        facebook_page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.page_access_token.isnot(None)
        ).order_by(
            FacebookPage.is_selected.desc(),
            FacebookPage.updated_at.desc()
        ).first()
        
        if facebook_page and facebook_page.page_access_token:
            logger.info(f"✅ Token Facebook trouvé pour vendeur {seller_id}: {facebook_page.page_access_token[:30]}...")
            return facebook_page.page_access_token
        
        logger.warning(f"❌ Pas de token Facebook trouvé pour le vendeur {seller_id}")
        return None
        
    except Exception as e:
        logger.error(f"Erreur récupération token Facebook: {e}", exc_info=True)
        return None

async def send_real_facebook_reply(
    comment_id: str,
    message: str,
    page_access_token: str
) -> Dict[str, Any]:
    """Envoie une VRAIE réponse via l'API Facebook"""
    
    try:
        # URL de l'API Facebook pour répondre à un commentaire
        url = f"https://graph.facebook.com/v19.0/{comment_id}/comments"
        
        data = {
            "message": message,
            "access_token": page_access_token
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; FacebookAutoReply/1.0)",
            "Accept": "application/json"
        }
        
        logger.info(f"📤 Envoi VRAIE réponse Facebook à {comment_id}")
        logger.info(f"Message: {message[:100]}...")
        logger.info(f"Token: {page_access_token[:30]}...")
        
        # Timeout de 30 secondes
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.post(url, data=data) as response:
                result_text = await response.text()
                logger.info(f"📨 Réponse Facebook API - Status: {response.status}")
                
                try:
                    result = await response.json()
                except:
                    result = {"raw_response": result_text}
                
                if response.status != 200:
                    error_msg = result.get('error', {}).get('message', 'Unknown error')
                    error_code = result.get('error', {}).get('code', 'UNKNOWN')
                    
                    logger.error(f"❌ Erreur Facebook API: {error_code} - {error_msg}")
                    logger.error(f"Détails: {result.get('error', {})}")
                    
                    raise Exception(f"Facebook API error {error_code}: {error_msg}")
                
                logger.info(f"✅ Réponse Facebook envoyée avec ID: {result.get('id')}")
                return result
                
    except aiohttp.ClientError as e:
        logger.error(f"❌ Erreur réseau Facebook: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Erreur envoi réponse Facebook: {e}")
        raise

# ================================
# TEMPLATES D'AUTO-REPLY
# ================================

AUTO_REPLY_TEMPLATES = {
    "order_confirmation": """✅ Commande {order_number} créée !

Merci {customer_name} pour votre commande !
• Produit : {product_name}
• Quantité : {quantity}
• Montant total : {total_amount}€

Nous vous contacterons par message privé pour finaliser la livraison. 📦

Merci pour votre confiance ! 🙏""",
    
    "simple_confirmation": """✅ Commande {order_number} enregistrée !

Merci {customer_name} ! 
Montant : {total_amount}€

Nous vous contactons en MP. 📦""",
    
    "address_request": """📍 Adresse de livraison

Bonjour {customer_name},

Pour livrer votre commande {order_number}, nous avons besoin de votre adresse complète.

Veuillez répondre à ce message avec :
• Votre adresse complète
• Code postal
• Ville
• Téléphone

Ou cliquez sur "Envoyer l'adresse" ci-dessous.

Merci ! 🚚""",
    
    "thank_you": """🙏 Merci {customer_name} !

Votre commande {order_number} a été créée avec succès.
Montant : {total_amount}€

Nous sommes heureux de vous servir ! 😊"""
}

def generate_auto_reply_message(
    template_name: str,
    customer_name: str,
    order_number: str,
    total_amount: float,
    product_name: str = "le produit",
    quantity: int = 1
) -> str:
    """Génère un message d'auto-reply à partir d'un template"""
    template = AUTO_REPLY_TEMPLATES.get(template_name, AUTO_REPLY_TEMPLATES["simple_confirmation"])
    
    return template.format(
        customer_name=customer_name,
        order_number=order_number,
        total_amount=total_amount,
        product_name=product_name,
        quantity=quantity
    )

# ================================
# ENDPOINTS AUTO-REPLY
# ================================

@router.get("/test")
async def test_endpoint():
    return {"status": "ok", "message": "Facebook Auto Reply API fonctionnel"}

@router.post("/enable")
async def enable_auto_reply(
    settings: AutoReplySettings,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Active/désactive l'auto-reply Facebook"""
    try:
        seller_id = get_seller_id(current_seller)
        
        from app.models.facebook import FacebookPage
        
        # Récupère la page active
        page = get_facebook_page_for_seller(db, seller_id)
        
        if not page:
            return {
                "success": False,
                "error": "Aucune page Facebook active",
                "solution": "Sélectionnez d'abord une page dans /facebook/pages/select"
            }
        
        # Active/désactive l'auto-reply
        page.auto_reply_enabled = settings.enabled
        
        # Gestion du template
        if settings.custom_message:
            page.auto_reply_template = settings.custom_message
            template_source = "custom"
        elif settings.template_name:
            template = AUTO_REPLY_TEMPLATES.get(settings.template_name)
            if template:
                page.auto_reply_template = template
                template_source = f"template: {settings.template_name}"
            else:
                page.auto_reply_template = AUTO_REPLY_TEMPLATES["simple_confirmation"]
                template_source = "default (template non trouvé)"
        elif not page.auto_reply_template or page.auto_reply_template == "":
            # Template par défaut si aucun
            page.auto_reply_template = AUTO_REPLY_TEMPLATES["simple_confirmation"]
            template_source = "default"
        else:
            template_source = "existing"
        
        page.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": f"Auto-reply {'ACTIVÉ' if settings.enabled else 'DÉSACTIVÉ'} avec succès",
            "enabled": page.auto_reply_enabled,
            "page_name": page.name,
            "template_source": template_source,
            "template_preview": page.auto_reply_template[:150] + "..." if page.auto_reply_template and len(page.auto_reply_template) > 150 else page.auto_reply_template,
            "next_step": "Testez avec POST /facebook/auto-reply/test-message"
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Erreur activation auto-reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_auto_reply_status(
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Récupère le statut de l'auto-reply"""
    try:
        seller_id = get_seller_id(current_seller)
        
        from app.models.facebook import FacebookPage
        
        page = get_facebook_page_for_seller(db, seller_id)
        
        if not page:
            return {
                "success": True,
                "enabled": False,
                "message": "Aucune page active",
                "status": "NOT_CONFIGURED"
            }
        
        return {
            "success": True,
            "enabled": page.auto_reply_enabled,
            "page_name": page.name,
            "page_id": page.page_id,
            "template_preview": page.auto_reply_template[:200] + "..." if page.auto_reply_template and len(page.auto_reply_template) > 200 else page.auto_reply_template,
            "template_length": len(page.auto_reply_template) if page.auto_reply_template else 0,
            "last_updated": page.updated_at.isoformat() if page.updated_at else None,
            "status": "ACTIVE" if page.auto_reply_enabled else "INACTIVE",
            "templates_available": list(AUTO_REPLY_TEMPLATES.keys())
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur statut auto-reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test-message")
async def test_auto_reply_message(
    request: TestAutoReplyRequest,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Teste la génération d'un message d'auto-reply (sans envoyer)"""
    try:
        seller_id = get_seller_id(current_seller)
        
        from app.models.facebook import FacebookPage
        
        page = get_facebook_page_for_seller(db, seller_id)
        
        if not page:
            return {
                "success": False,
                "error": "Aucune page active",
                "solution": "Activez d'abord une page Facebook"
            }
        
        # Générer le message
        if page.auto_reply_template:
            # Utiliser le template personnalisé de la page
            message = page.auto_reply_template.format(
                customer_name=request.customer_name,
                order_number=request.order_number,
                total_amount=request.total_amount,
                product_name="Produit test",
                quantity=1
            )
            template_source = "page_template"
        else:
            # Utiliser le template par défaut
            message = generate_auto_reply_message(
                template_name="simple_confirmation",
                customer_name=request.customer_name,
                order_number=request.order_number,
                total_amount=request.total_amount
            )
            template_source = "default_template"
        
        return {
            "success": True,
            "message": "Message d'auto-reply généré avec succès",
            "auto_reply_enabled": page.auto_reply_enabled,
            "generated_message": message,
            "message_length": len(message),
            "template_source": template_source,
            "test_data": {
                "comment_text": request.comment_text,
                "customer_name": request.customer_name,
                "order_number": request.order_number,
                "total_amount": request.total_amount
            },
            "note": "Ceci est un test. Le message n'a pas été envoyé sur Facebook."
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur test message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/trigger-auto-reply/{comment_id}")
async def trigger_auto_reply_for_comment(
    comment_id: str,
    background_tasks: BackgroundTasks,
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Déclenche l'auto-reply pour un commentaire spécifique"""
    try:
        seller_id = get_seller_id(current_seller)
        
        from app.models.facebook import FacebookComment
        from app.models.order import Order
        
        # Récupérer le commentaire
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id,
            FacebookComment.seller_id == seller_id
        ).first()
        
        if not comment:
            raise HTTPException(status_code=404, detail={
                "error": "Commentaire non trouvé",
                "comment_id": comment_id
            })
        
        # Récupérer la commande associée
        order = db.query(Order).filter(
            Order.source_id == comment_id,
            Order.seller_id == seller_id
        ).first()
        
        if not order:
            return {
                "success": False,
                "error": "Aucune commande associée à ce commentaire",
                "comment_id": comment_id,
                "solution": "Créez d'abord une commande avec POST /facebook/comments/{comment_id}/create-order"
            }
        
        # Récupérer la page
        from app.models.facebook import FacebookPage
        page = get_facebook_page_for_seller(db, seller_id)
        
        if not page or not page.auto_reply_enabled:
            return {
                "success": False,
                "error": "Auto-reply non activé",
                "solution": "Activez d'abord l'auto-reply avec POST /facebook/auto-reply/enable",
                "page_has_auto_reply": page.auto_reply_enabled if page else False
            }
        
        # Générer le message d'auto-reply
        if page.auto_reply_template:
            message = page.auto_reply_template.format(
                customer_name=order.customer_name,
                order_number=order.order_number,
                total_amount=order.total_amount,
                product_name=comment.detected_code_article or "votre produit",
                quantity=comment.detected_quantity or 1
            )
        else:
            message = generate_auto_reply_message(
                template_name="simple_confirmation",
                customer_name=order.customer_name,
                order_number=order.order_number,
                total_amount=float(order.total_amount)
            )
        
        # Lancer l'envoi en arrière-plan
        background_tasks.add_task(
            send_auto_reply_background,
            comment_id=comment_id,
            message=message,
            seller_id=seller_id,
            order_id=order.id
        )
        
        return {
            "success": True,
            "message": "Auto-reply déclenché avec succès",
            "comment_id": comment_id,
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "generated_message_preview": message[:150] + "..." if len(message) > 150 else message,
            "auto_reply_status": "QUEUED",
            "note": "L'auto-reply sera envoyé dans quelques secondes"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur déclenchement auto-reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def send_auto_reply_background(
    comment_id: str,
    message: str,
    seller_id: uuid.UUID,
    order_id: uuid.UUID
):
    """Envoie l'auto-reply en arrière-plan"""
    try:
        db = SessionLocal()
        try:
            # Récupérer le token
            token = await get_facebook_token(db, seller_id)
            if not token:
                logger.error(f"❌ Token non trouvé pour seller {seller_id}")
                return
            
            # Envoyer la réponse
            result = await send_real_facebook_reply(
                comment_id=comment_id,
                message=message,
                page_access_token=token
            )
            
            # Enregistrer dans l'historique
            from app.models.facebook_reply import FacebookReplyHistory
            reply_history = FacebookReplyHistory(
                id=uuid.uuid4(),
                comment_id=comment_id,
                order_id=order_id,
                message=message,
                facebook_response_id=result.get('id'),
                sent_at=datetime.utcnow(),
                is_auto_reply=True
            )
            db.add(reply_history)
            
            # Mettre à jour le commentaire
            from app.models.facebook import FacebookComment
            comment = db.query(FacebookComment).filter(
                FacebookComment.id == comment_id
            ).first()
            if comment:
                comment.auto_replied = True
                comment.auto_reply_sent_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"✅ Auto-reply envoyé pour commentaire {comment_id}")
            
        except Exception as e:
            logger.error(f"❌ Erreur auto-reply background: {e}")
            db.rollback()
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Erreur grave auto-reply background: {e}")

@router.post("/{comment_id}/reply")
async def real_facebook_auto_reply(
    comment_id: str,
    db: Session = Depends(get_db),
    seller = Depends(get_current_seller)
):
    """ENVOIE UNE VRAIE RÉPONSE SUR FACEBOOK (avec vérification auto-reply)"""
    try:
        seller_id = get_seller_id(seller)
        
        logger.info(f"🚀 DÉBUT RÉPONSE FACEBOOK pour {comment_id}")
        
        from app.models.facebook import FacebookComment
        from app.models.order import Order
        
        # 1. Récupérer le commentaire
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id,
            FacebookComment.seller_id == seller_id
        ).first()
        
        if not comment:
            raise HTTPException(status_code=404, detail={
                "error": "Commentaire non trouvé",
                "comment_id": comment_id,
                "seller_id": str(seller_id)
            })
        
        logger.info(f"✅ Commentaire trouvé: {comment.user_name} - {comment.message}")
        
        # 2. Récupérer ou créer la commande
        order = db.query(Order).filter(
            Order.source_id == comment_id,
            Order.seller_id == seller_id
        ).first()
        
        order_created = False
        if not order:
            logger.info("📝 Création d'une nouvelle commande...")
            try:
                from app.services.order_service import OrderService
                order_service = OrderService(db)
                
                order = order_service.create_order_from_facebook_comment(
                    seller_id=seller_id,
                    comment_id=comment_id,
                    customer_name=comment.user_name,
                    product_code=comment.detected_code_article,
                    quantity=comment.detected_quantity or 1
                )
                
                if order:
                    order_created = True
                    logger.info(f"✅ Nouvelle commande créée: {order.order_number}")
                else:
                    raise Exception("Échec création commande")
                    
            except Exception as e:
                logger.error(f"❌ Erreur création commande: {e}")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": f"Impossible de créer la commande: {str(e)}",
                        "comment_id": comment_id,
                        "product": comment.detected_code_article
                    }
                )
        else:
            logger.info(f"✅ Commande existante trouvée: {order.order_number}")
        
        # 3. Vérifier si l'auto-reply est activé
        from app.models.facebook import FacebookPage
        page = get_facebook_page_for_seller(db, seller_id)
        
        use_auto_reply = False
        reply_message = ""
        
        if page and page.auto_reply_enabled and page.auto_reply_template:
            # Utiliser l'auto-reply
            use_auto_reply = True
            reply_message = page.auto_reply_template.format(
                customer_name=order.customer_name,
                order_number=order.order_number,
                total_amount=order.total_amount,
                product_name=comment.detected_code_article or "votre produit",
                quantity=comment.detected_quantity or 1
            )
            logger.info(f"🤖 Utilisation auto-reply (template: {len(page.auto_reply_template)} caractères)")
        else:
            # Message standard
            reply_message = (
                f"✅ Commande {order.order_number} créée !\n\n"
                f"Merci {comment.user_name} pour votre commande !\n"
                f"Montant total : {order.total_amount}€\n\n"
                "Nous vous contacterons en message privé pour finaliser la livraison. 📦\n\n"
                "Merci pour votre confiance ! 🙏"
            )
            logger.info("📄 Utilisation message standard")
        
        logger.info(f"📄 Message généré ({len(reply_message)} caractères)")
        
        # 4. Récupérer le token Facebook
        facebook_token = await get_facebook_token(db, seller_id)
        if not facebook_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Token Facebook non disponible",
                    "solution": "Vérifiez que la page Facebook est bien configurée",
                    "seller_id": str(seller_id),
                    "comment_id": comment_id
                }
            )
        
        logger.info(f"✅ Token Facebook récupéré: {facebook_token[:30]}...")
        
        # 5. ENVOYER LA RÉPONSE FACEBOOK
        logger.info(f"📤 ENVOI vers Facebook API...")
        
        try:
            facebook_result = await send_real_facebook_reply(
                comment_id=comment_id,
                message=reply_message,
                page_access_token=facebook_token
            )
            
            facebook_response_id = facebook_result.get('id')
            
            logger.info(f"✅✅✅ SUCCÈS ! Réponse Facebook publiée !")
            logger.info(f"✅ ID de la réponse: {facebook_response_id}")
            
            # 6. Enregistrer dans l'historique
            try:
                from app.models.facebook_reply import FacebookReplyHistory
                
                reply_history = FacebookReplyHistory(
                    id=uuid.uuid4(),
                    comment_id=comment_id,
                    order_id=order.id,
                    message=reply_message,
                    facebook_response_id=facebook_response_id,
                    sent_at=datetime.utcnow(),
                    is_auto_reply=use_auto_reply
                )
                db.add(reply_history)
                db.commit()
                logger.info(f"📝 Historique enregistré: {reply_history.id}")
            except Exception as history_error:
                logger.warning(f"⚠️ Erreur historique: {history_error}")
            
            # 7. Mettre à jour le commentaire
            try:
                comment.response_text = reply_message
                comment.action_taken = "order_created"
                comment.auto_replied = use_auto_reply
                comment.processed_at = datetime.utcnow()
                if use_auto_reply:
                    comment.auto_reply_sent_at = datetime.utcnow()
                db.commit()
                logger.info(f"📝 Commentaire mis à jour")
            except Exception as update_error:
                logger.warning(f"⚠️ Erreur mise à jour commentaire: {update_error}")
            
            return {
                "success": True,
                "message": "✅ Réponse Facebook envoyée avec succès !",
                "comment_id": comment_id,
                "order_number": order.order_number,
                "customer_name": order.customer_name,
                "reply_message": reply_message,
                "facebook_response_id": facebook_response_id,
                "facebook_url": f"https://facebook.com/{facebook_response_id}" if facebook_response_id else None,
                "order_created": order_created,
                "auto_reply_used": use_auto_reply,
                "timestamp": datetime.utcnow().isoformat(),
                "mode": "real",
                "note": "Cette réponse a été publiée sur Facebook",
                "debug": {
                    "token_preview": facebook_token[:20] + "...",
                    "comment_user": comment.user_name,
                    "product": comment.detected_code_article,
                    "message_length": len(reply_message),
                    "auto_reply_enabled": page.auto_reply_enabled if page else False
                }
            }
            
        except aiohttp.ClientError as e:
            logger.error(f"❌ Erreur réseau: {e}")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": f"Erreur de connexion à Facebook: {str(e)}",
                    "comment_id": comment_id,
                    "solution": "Vérifiez votre connexion internet"
                }
            )
        except asyncio.TimeoutError:
            logger.error("❌ Timeout Facebook API")
            raise HTTPException(
                status_code=504,
                detail={
                    "error": "Timeout de connexion à Facebook (30 secondes)",
                    "comment_id": comment_id,
                    "solution": "Réessayez ou vérifiez l'API Facebook"
                }
            )
        except Exception as e:
            logger.error(f"❌ Erreur Facebook API: {e}", exc_info=True)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Erreur Facebook: {str(e)}",
                    "comment_id": comment_id,
                    "solution": "Vérifiez votre token Facebook"
                }
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erreur globale: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"Erreur interne: {str(e)}",
                "comment_id": comment_id
            }
        )

@router.post("/{comment_id}/preview")
async def preview_facebook_reply(
    comment_id: str,
    db: Session = Depends(get_db),
    seller = Depends(get_current_seller)
):
    """Prévisualise la réponse sans l'envoyer"""
    try:
        seller_id = get_seller_id(seller)
        
        from app.models.facebook import FacebookComment
        from app.models.order import Order
        
        # Récupérer commentaire
        comment = db.query(FacebookComment).filter(
            FacebookComment.id == comment_id,
            FacebookComment.seller_id == seller_id
        ).first()
        
        if not comment:
            raise HTTPException(status_code=404, detail="Commentaire non trouvé")
        
        # Vérifier auto-reply
        from app.models.facebook import FacebookPage
        page = get_facebook_page_for_seller(db, seller_id)
        
        use_auto_reply = False
        reply_message = ""
        
        if page and page.auto_reply_enabled and page.auto_reply_template:
            use_auto_reply = True
            # Simuler une commande pour le preview
            reply_message = page.auto_reply_template.format(
                customer_name=comment.user_name or "Client",
                order_number=f"SHO-{datetime.now().strftime('%Y%m%d')}-XXXX",
                total_amount=24.99,
                product_name=comment.detected_code_article or "Produit",
                quantity=comment.detected_quantity or 1
            )
        else:
            # Message standard
            reply_message = (
                f"✅ Commande SHO-{datetime.now().strftime('%Y%m%d')}-XXXX créée !\n\n"
                f"Merci {comment.user_name} pour votre commande !\n"
                f"Montant total : 24.99€\n\n"
                "Nous vous contacterons en message privé pour finaliser la livraison. 📦\n\n"
                "Merci pour votre confiance ! 🙏"
            )
        
        # Vérifier le token
        facebook_token = await get_facebook_token(db, seller_id)
        
        return {
            "success": True,
            "mode": "preview",
            "comment_id": comment_id,
            "customer_name": comment.user_name,
            "reply_message": reply_message,
            "message_length": len(reply_message),
            "auto_reply_used": use_auto_reply,
            "auto_reply_enabled": page.auto_reply_enabled if page else False,
            "token_available": bool(facebook_token),
            "token_preview": facebook_token[:30] + "..." if facebook_token else None,
            "note": "Ceci est une prévisualisation. La réponse n'a pas été envoyée.",
            "action_required": "Utilisez POST /{comment_id}/reply pour envoyer réellement"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{comment_id}/custom")
async def custom_reply(
    comment_id: str,
    message_data: Dict[str, Any],
    current_seller = Depends(get_current_seller),
    db: Session = Depends(get_db)
):
    """Réponse personnalisée VRAIE"""
    try:
        seller_id = get_seller_id(current_seller)
        
        message = message_data.get("message")
        if not message:
            raise HTTPException(status_code=400, detail="Message requis")
        
        # Récupérer le token
        facebook_token = await get_facebook_token(db, seller_id)
        if not facebook_token:
            raise HTTPException(status_code=400, detail="Token Facebook non disponible")
        
        # Chercher la commande associée
        from app.models.order import Order
        order = db.query(Order).filter(
            Order.source_id == comment_id,
            Order.seller_id == seller_id
        ).first()
        
        # Envoyer la réponse réelle
        facebook_result = await send_real_facebook_reply(
            comment_id=comment_id,
            message=message,
            page_access_token=facebook_token
        )
        
        facebook_response_id = facebook_result.get('id')
        
        # Enregistrer dans l'historique
        try:
            from app.models.facebook_reply import FacebookReplyHistory
            
            reply_history = FacebookReplyHistory(
                id=uuid.uuid4(),
                comment_id=comment_id,
                order_id=order.id if order else None,
                message=message,
                facebook_response_id=facebook_response_id,
                sent_at=datetime.utcnow(),
                is_auto_reply=False
            )
            db.add(reply_history)
            db.commit()
            logger.info(f"[CUSTOM-REPLY] Historique enregistré pour {comment_id}")
        except Exception as e:
            logger.warning(f"[CUSTOM-REPLY] Pas d'historique: {e}")
        
        return {
            "success": True,
            "message": "Réponse personnalisée envoyée sur Facebook",
            "comment_id": comment_id,
            "order_id": str(order.id) if order else None,
            "reply_message": message,
            "facebook_response_id": facebook_response_id,
            "facebook_url": f"https://facebook.com/{facebook_response_id}",
            "timestamp": datetime.utcnow().isoformat(),
            "mode": "real"
        }
        
    except Exception as e:
        logger.error(f"❌ Erreur custom reply: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/check-token")
async def check_facebook_token_status(
    db: Session = Depends(get_db),
    seller = Depends(get_current_seller)
):
    """Vérifie l'état du token Facebook"""
    try:
        seller_id = get_seller_id(seller)
        
        from app.models.facebook import FacebookPage
        
        # Récupérer la page
        page = db.query(FacebookPage).filter(
            FacebookPage.seller_id == seller_id,
            FacebookPage.is_selected == True
        ).first()
        
        token = await get_facebook_token(db, seller_id)
        
        return {
            "success": True,
            "has_token": bool(token),
            "token_preview": token[:30] + "..." if token else None,
            "token_length": len(token) if token else 0,
            "page": {
                "name": page.name if page else None,
                "page_id": page.page_id if page else None,
                "is_selected": page.is_selected if page else None,
                "auto_reply_enabled": page.auto_reply_enabled if page else None,
                "auto_reply_template_length": len(page.auto_reply_template) if page and page.auto_reply_template else 0
            } if page else None,
            "seller_id": str(seller_id),
            "status": "READY" if token else "NOT_CONFIGURED"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "seller_id": str(seller_id) if 'seller_id' in locals() else None
        }

@router.get("/debug-seller")
async def debug_seller(seller = Depends(get_current_seller)):
    """Debug: voir la structure du seller"""
    return {
        "seller_type": type(seller).__name__,
        "seller_attrs": dir(seller) if hasattr(seller, '__dir__') else "N/A",
        "seller_dict": dict(seller) if isinstance(seller, dict) else (
            seller.__dict__ if hasattr(seller, '__dict__') else "N/A"
        ),
        "has_seller_id": hasattr(seller, 'seller_id') if not isinstance(seller, dict) else 'seller_id' in seller,
        "has_id": hasattr(seller, 'id') if not isinstance(seller, dict) else 'id' in seller,
        "seller_id_value": get_seller_id(seller) if 'seller_id' in locals() else "N/A"
    }

# Ajoute cette fonction si SessionLocal n'est pas importé
try:
    from app.db import SessionLocal
except ImportError:
    from app.db import SessionLocal