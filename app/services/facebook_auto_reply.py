import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import aiohttp

from app.models.facebook import FacebookComment, FacebookPage
from app.models.order import Order
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)

class FacebookAutoReplyService:
    """Service pour les réponses automatiques Facebook"""
    
    def __init__(self, db: Session):
        self.db = db
        self.order_service = OrderService(db)
    
    def get_comment_by_id(self, comment_id: str, seller_id: uuid.UUID) -> Optional[FacebookComment]:
        """Récupère un commentaire par ID"""
        return self.db.query(FacebookComment).filter(
            FacebookComment.id == comment_id,
            FacebookComment.seller_id == seller_id
        ).first()
    
    def get_order_by_comment_id(self, comment_id: str, seller_id: uuid.UUID) -> Optional[Order]:
        """Récupère la commande associée à un commentaire"""
        return self.db.query(Order).filter(
            Order.source_id == comment_id,
            Order.seller_id == seller_id
        ).first()
    
    async def get_facebook_token_for_seller(self, seller_id: uuid.UUID) -> Optional[str]:
        """Récupère le token Facebook pour un vendeur - VERSION CORRIGÉE"""
        try:
            # Chercher la page active/sélectionnée
            facebook_page = self.db.query(FacebookPage).filter(
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
    
    def generate_order_confirmation_reply(self, order: Order, comment: FacebookComment) -> str:
        """Génère un message de confirmation automatique"""
        
        templates = {
            "order_created": (
                "✅ Commande créée !\n\n"
                f"Merci {comment.user_name} !\n"
                f"Votre commande **{order.order_number}** a été enregistrée.\n"
                f"Total : {order.total_amount}€\n\n"
                "Nous vous contacterons en message privé pour finaliser la livraison. 📦\n\n"
                "#LiveShopping #CommandeValidée"
            ),
            "order_with_items": (
                "🎉 Commande prise en compte !\n\n"
                f"Merci {comment.user_name} pour votre commande **{order.order_number}**.\n"
                f"Montant : {order.total_amount}€\n\n"
                "Un message privé vous sera envoyé pour confirmer l'adresse de livraison.\n\n"
                "Merci pour votre confiance ! 🙏"
            ),
            "needs_confirmation": (
                "👋 Nous avons bien reçu votre demande !\n\n"
                f"{comment.user_name}, votre commande **{order.order_number}** est en attente de confirmation.\n"
                "Veuillez vérifier vos messages privés pour finaliser.\n\n"
                "Merci ! 😊"
            )
        }
        
        # Choisir le template selon le nombre d'items
        if hasattr(order, 'items') and len(order.items) > 1:
            template = "order_with_items"
        elif hasattr(order, 'customer_phone') and order.customer_phone == "À confirmer":
            template = "needs_confirmation"
        else:
            template = "order_created"
        
        return templates[template]
    
    async def send_facebook_reply(
        self, 
        comment_id: str, 
        message: str,
        page_access_token: str
    ) -> Dict[str, Any]:
        """Envoie une réponse via l'API Facebook - VERSION TESTÉE"""
        
        try:
            # URL de l'API Facebook pour répondre à un commentaire
            url = f"https://graph.facebook.com/v19.0/{comment_id}/comments"
            
            data = {
                "message": message,
                "access_token": page_access_token
            }
            
            logger.info(f"📤 Envoi réponse Facebook à {comment_id[:10]}...")
            logger.info(f"Message: {message[:50]}...")
            logger.info(f"Token: {page_access_token[:20]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.json()
                    
                    logger.info(f"📨 Réponse Facebook API: {response.status} - {result}")
                    
                    if response.status != 200:
                        error_msg = result.get('error', {}).get('message', 'Unknown error')
                        logger.error(f"❌ Erreur Facebook API: {error_msg}")
                        raise Exception(f"Facebook API error: {error_msg}")
                    
                    logger.info(f"✅ Réponse Facebook envoyée avec ID: {result.get('id')}")
                    return result
                    
        except aiohttp.ClientError as e:
            logger.error(f"❌ Erreur réseau Facebook: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Erreur envoi réponse Facebook: {e}")
            raise
    
    def save_reply_history(
        self,
        comment_id: str,
        order_id: uuid.UUID,
        message: str,
        facebook_response_id: Optional[str] = None
    ):
        """Enregistre l'historique des réponses"""
        from app.models.facebook_reply import FacebookReplyHistory
        
        reply_history = FacebookReplyHistory(
            id=uuid.uuid4(),
            comment_id=comment_id,
            order_id=order_id,
            message=message,
            facebook_response_id=facebook_response_id,
            sent_at=datetime.utcnow()
        )
        
        self.db.add(reply_history)
        self.db.commit()
        
        return reply_history
    
    def get_reply_history(self, comment_id: str, seller_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Récupère l'historique des réponses"""
        
        # Vérifier d'abord que le commentaire appartient au vendeur
        comment = self.get_comment_by_id(comment_id, seller_id)
        if not comment:
            return []
        
        from app.models.facebook_reply import FacebookReplyHistory
        
        history = self.db.query(FacebookReplyHistory).filter(
            FacebookReplyHistory.comment_id == comment_id
        ).order_by(FacebookReplyHistory.sent_at.desc()).all()
        
        return [
            {
                "id": str(item.id),
                "message": item.message,
                "sent_at": item.sent_at.isoformat() if item.sent_at else None,
                "facebook_response_id": item.facebook_response_id
            }
            for item in history
        ]
    
    async def create_order_from_comment(
        self,
        comment_id: str,
        seller_id: uuid.UUID
    ) -> Optional[Order]:
        """Crée une commande depuis un commentaire"""
        try:
            comment = self.get_comment_by_id(comment_id, seller_id)
            if not comment:
                logger.error(f"❌ Commentaire non trouvé: {comment_id}")
                return None
            
            logger.info(f"📝 Création commande depuis commentaire: {comment_id}")
            
            # Utiliser le service existant pour créer la commande
            order = self.order_service.create_order_from_facebook_comment(
                seller_id=seller_id,
                comment_id=comment_id,
                customer_name=comment.user_name,
                product_code=comment.detected_code_article,
                quantity=comment.detected_quantity or 1
            )
            
            if order:
                logger.info(f"✅ Commande créée: {order.order_number}")
            else:
                logger.error(f"❌ Échec création commande pour commentaire {comment_id}")
            
            return order
            
        except Exception as e:
            logger.error(f"❌ Erreur création commande: {e}", exc_info=True)
            return None
    
    async def auto_reply_after_order(
        self,
        comment_id: str,
        order: Order,
        seller_id: uuid.UUID,
        facebook_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Répond automatiquement après création de commande - VERSION COMPLÈTE"""
        try:
            logger.info(f"🔄 Début auto-reply pour commentaire: {comment_id}")
            
            # Récupérer le token si non fourni
            if not facebook_token:
                facebook_token = await self.get_facebook_token_for_seller(seller_id)
            
            if not facebook_token:
                error_msg = "❌ Token Facebook manquant"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            # Récupérer le commentaire
            comment = self.get_comment_by_id(comment_id, seller_id)
            if not comment:
                error_msg = f"❌ Commentaire {comment_id} non trouvé"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
            
            # Générer le message
            reply_message = self.generate_order_confirmation_reply(order, comment)
            logger.info(f"📄 Message généré: {reply_message[:100]}...")
            
            # Envoyer la réponse
            result = await self.send_facebook_reply(
                comment_id=comment_id,
                message=reply_message,
                page_access_token=facebook_token
            )
            
            # Enregistrer l'historique
            self.save_reply_history(
                comment_id=comment_id,
                order_id=order.id,
                message=reply_message,
                facebook_response_id=result.get("id")
            )
            
            logger.info(f"✅ Auto-reply terminé avec succès pour {order.order_number}")
            
            return {
                "success": True,
                "facebook_response_id": result.get("id"),
                "reply_message": reply_message,
                "order_number": order.order_number,
                "comment_id": comment_id
            }
                
        except Exception as e:
            logger.error(f"❌ Erreur auto-reply: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "comment_id": comment_id
            }
    
    async def process_comment_automatically(
        self,
        comment_id: str,
        seller_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Processus complet: crée la commande et répond automatiquement"""
        try:
            logger.info(f"🚀 Traitement automatique du commentaire: {comment_id}")
            
            # 1. Créer la commande
            order = await self.create_order_from_comment(comment_id, seller_id)
            if not order:
                return {"success": False, "error": "Échec création commande"}
            
            # 2. Récupérer le token Facebook
            facebook_token = await self.get_facebook_token_for_seller(seller_id)
            if not facebook_token:
                return {"success": False, "error": "Token Facebook manquant"}
            
            # 3. Envoyer la réponse automatique
            result = await self.auto_reply_after_order(
                comment_id=comment_id,
                order=order,
                seller_id=seller_id,
                facebook_token=facebook_token
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur traitement automatique: {e}", exc_info=True)
            return {"success": False, "error": str(e)}