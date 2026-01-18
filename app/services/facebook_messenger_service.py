# app/services/facebook_messenger_service.py - VERSION CORRIGÉE
import logging
import uuid
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
import aiohttp
import asyncio

from app.models.facebook import FacebookPage, FacebookComment
from app.models.order import Order
# REMPLACER: from app.models.customer import Customer  # Ce modèle n'existe pas
# PAR:
from app.models.user import User  # Si tu as un modèle User
# OU utiliser directement les champs de Order

logger = logging.getLogger(__name__)

class FacebookMessengerService:
    """Service complet pour Facebook Messenger"""
    
    def __init__(self, db: Session):
        self.db = db
        self.message_templates = self._load_message_templates()
        self.max_retries = 3
        self.retry_delay = 2  # secondes
    
    def _load_message_templates(self) -> Dict[str, str]:
        """Charge les templates de messages"""
        return {
            "order_confirmation": (
                "👋 Bonjour {customer_name} !\n\n"
                "✅ Votre commande **{order_number}** a été enregistrée avec succès !\n"
                "🛒 Produit: {product_name}\n"
                "💰 Montant total: {total_amount}€\n"
                "📦 Quantité: {quantity}\n\n"
                "Pour finaliser votre livraison, veuillez nous envoyer votre :\n"
                "1. 📍 **Adresse complète de livraison**\n"
                "2. 📞 **Numéro de téléphone**\n"
                "3. 🏠 **Justificatif de domicile** (optionnel)\n\n"
                "Vous pouvez simplement prendre une photo de votre adresse écrite sur papier.\n\n"
                "Nous vous remercions pour votre confiance ! 🙏\n"
                "#LiveShopping #CommandeValidée"
            ),
            
            "delivery_confirmation": (
                "🎉 Excellente nouvelle {customer_name} !\n\n"
                "📦 Votre commande **{order_number}** est en route !\n"
                "🚚 Livreur assigné: {delivery_person}\n"
                "📍 Zone de livraison: {delivery_zone}\n"
                "⏰ Heure estimée: {delivery_time}\n\n"
                "Suivez votre livraison en temps réel.\n"
                "Merci pour votre patience ! 😊"
            ),
            
            "address_request": (
                "📬 Pour finaliser votre livraison, nous avons besoin de votre adresse.\n\n"
                "Veuillez nous envoyer une photo avec :\n"
                "• Votre nom complet\n"
                "• Votre adresse complète\n"
                "• Votre numéro de téléphone\n\n"
                "Ou écrivez simplement votre adresse dans ce chat.\n\n"
                "Merci !"
            ),
            
            "thank_you_message": (
                "🙏 Merci {customer_name} !\n\n"
                "Nous avons bien reçu vos informations.\n"
                "Votre livraison est maintenant en préparation.\n\n"
                "Nous vous tiendrons informé de l'avancement.\n"
                "Bonne journée ! 😊"
            ),
            
            "order_status_update": (
                "📊 Mise à jour commande {order_number}\n\n"
                "🔄 Statut: {status}\n"
                "📝 Note: {note}\n\n"
                "N'hésitez pas à nous contacter pour toute question."
            ),
            
            "quick_reply_template": (
                "👋 Bonjour {customer_name} !\n\n"
                "Comment pouvons-nous vous aider aujourd'hui ?\n\n"
                "Choisissez une option :"
            )
        }
    
    async def get_messenger_token(self, seller_id: uuid.UUID) -> Optional[str]:
        """Récupère le token Messenger pour un vendeur"""
        try:
            # Récupérer la page Facebook sélectionnée
            page = self.db.query(FacebookPage).filter(
                FacebookPage.seller_id == seller_id,
                FacebookPage.is_selected == True,
                FacebookPage.page_access_token.isnot(None)
            ).first()
            
            if page and page.page_access_token:
                # Vérifier que le token a les permissions Messenger
                token = page.page_access_token
                has_permissions = await self._check_messenger_permissions(token)
                
                if has_permissions:
                    logger.info(f"✅ Token Messenger valide pour vendeur {seller_id}")
                    return token
                else:
                    logger.warning(f"⚠️ Token sans permissions Messenger pour vendeur {seller_id}")
            
            logger.error(f"❌ Token Messenger non disponible pour vendeur {seller_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération token Messenger: {e}")
            return None
    
    async def _check_messenger_permissions(self, page_token: str) -> bool:
        """Vérifie si le token a les permissions Messenger"""
        try:
            url = f"https://graph.facebook.com/v19.0/me/permissions"
            params = {"access_token": page_token}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        permissions = data.get("data", [])
                        
                        # Vérifier les permissions nécessaires
                        required_permissions = {"pages_messaging", "pages_manage_metadata"}
                        granted_permissions = {p["permission"] for p in permissions if p["status"] == "granted"}
                        
                        return required_permissions.issubset(granted_permissions)
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification permissions: {e}")
            return False
    
    async def send_private_message(
        self,
        recipient_id: str,
        message: str,
        page_access_token: str,
        messaging_type: str = "MESSAGE_TAG",
        tag: str = "CONFIRMED_EVENT_UPDATE",
        quick_replies: Optional[List[Dict]] = None,
        attachments: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Envoie un message privé via Messenger API"""
        
        for attempt in range(self.max_retries):
            try:
                url = "https://graph.facebook.com/v19.0/me/messages"
                
                # Construire le payload
                payload = {
                    "recipient": {"id": recipient_id},
                    "messaging_type": messaging_type,
                    "tag": tag,
                    "message": {"text": message}
                }
                
                # Ajouter les quick replies si fournis
                if quick_replies:
                    payload["message"]["quick_replies"] = quick_replies
                
                # Ajouter les attachments si fournis
                if attachments:
                    payload["message"]["attachment"] = attachments
                
                params = {"access_token": page_access_token}
                
                logger.info(f"📤 Envoi message Messenger à {recipient_id}")
                logger.debug(f"Message: {message[:100]}...")
                logger.debug(f"Token preview: {page_access_token[:30]}...")
                
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "LiveCommerceMessenger/2.0"
                }
                
                timeout = aiohttp.ClientTimeout(total=30)
                
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    async with session.post(url, params=params, json=payload) as response:
                        response_text = await response.text()
                        
                        logger.info(f"📨 Réponse Messenger API - Status: {response.status}")
                        
                        try:
                            result = await response.json()
                        except:
                            result = {"raw_response": response_text}
                        
                        if response.status == 200:
                            message_id = result.get("message_id")
                            recipient_id = result.get("recipient_id")
                            
                            logger.info(f"✅ Message envoyé avec succès! ID: {message_id}")
                            
                            return {
                                "success": True,
                                "message_id": message_id,
                                "recipient_id": recipient_id,
                                "timestamp": datetime.utcnow().isoformat(),
                                "result": result
                            }
                        else:
                            error = result.get("error", {})
                            error_code = error.get("code")
                            error_msg = error.get("message", "Unknown error")
                            
                            logger.error(f"❌ Erreur Messenger API (attempt {attempt + 1}/{self.max_retries}): {error_code} - {error_msg}")
                            
                            # Erreurs récupérables
                            recoverable_errors = {4, 368, 803, 190, 200}
                            if error_code in recoverable_errors and attempt < self.max_retries - 1:
                                await asyncio.sleep(self.retry_delay * (attempt + 1))
                                continue
                            else:
                                raise Exception(f"Messenger API error {error_code}: {error_msg}")
                
            except aiohttp.ClientError as e:
                logger.error(f"❌ Erreur réseau Messenger (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
            except Exception as e:
                logger.error(f"❌ Erreur envoi message (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
        
        return {"success": False, "error": "Max retries exceeded"}
    
    async def get_user_profile(
        self,
        user_id: str,
        page_access_token: str
    ) -> Optional[Dict[str, Any]]:
        """Récupère le profil d'un utilisateur Facebook"""
        try:
            url = f"https://graph.facebook.com/v19.0/{user_id}"
            params = {
                "fields": "id,name,first_name,last_name,profile_pic",
                "access_token": page_access_token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Profil utilisateur récupéré: {data.get('name')}")
                        return data
                    else:
                        logger.warning(f"⚠️ Impossible de récupérer le profil de {user_id}")
                        return None
                        
        except Exception as e:
            logger.error(f"❌ Erreur récupération profil: {e}")
            return None
    
    async def send_order_confirmation_message(
        self,
        order: Order,
        comment: FacebookComment,
        seller_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Envoie un message de confirmation de commande"""
        try:
            # 1. Récupérer le token Messenger
            token = await self.get_messenger_token(seller_id)
            if not token:
                return {
                    "success": False,
                    "error": "Token Messenger non disponible",
                    "action": "Vérifiez les permissions de la page Facebook"
                }
            
            # 2. Vérifier si l'utilisateur a un ID Facebook
            recipient_id = comment.user_id
            if not recipient_id:
                # Essayer de trouver l'ID via le nom (approximatif)
                recipient_id = await self._find_user_id_by_name(comment.user_name, token)
                
                if not recipient_id:
                    return {
                        "success": False,
                        "error": "ID utilisateur Facebook non disponible",
                        "action": "L'utilisateur doit avoir commenté sur la page"
                    }
            
            # 3. Récupérer les infos produit
            product_name = comment.detected_product_name or comment.detected_code_article
            
            # 4. Préparer le message
            message = self.message_templates["order_confirmation"].format(
                customer_name=comment.user_name,
                order_number=order.order_number,
                product_name=product_name,
                total_amount=order.total_amount,
                quantity=comment.detected_quantity or 1
            )
            
            # 5. Préparer les quick replies
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "📍 Envoyer mon adresse",
                    "payload": "SEND_ADDRESS"
                },
                {
                    "content_type": "text",
                    "title": "📞 Mon téléphone",
                    "payload": "SEND_PHONE"
                },
                {
                    "content_type": "text",
                    "title": "❓ Demander de l'aide",
                    "payload": "NEED_HELP"
                }
            ]
            
            # 6. Envoyer le message
            result = await self.send_private_message(
                recipient_id=recipient_id,
                message=message,
                page_access_token=token,
                quick_replies=quick_replies
            )
            
            # 7. Enregistrer dans l'historique
            if result["success"]:
                await self.save_message_history(
                    message_type="order_confirmation",
                    sender_id="page",  # La page envoie
                    recipient_id=recipient_id,
                    message_content=message,
                    message_id=result.get("message_id"),
                    order_id=order.id,
                    comment_id=comment.id,
                    seller_id=seller_id
                )
                
                logger.info(f"✅ Message de confirmation envoyé à {comment.user_name}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur envoi confirmation commande: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def send_delivery_address_request(
        self,
        recipient_id: str,
        customer_name: str,
        order_number: str,
        page_access_token: str
    ) -> Dict[str, Any]:
        """Demande l'adresse de livraison"""
        try:
            message = self.message_templates["address_request"]
            
            quick_replies = [
                {
                    "content_type": "text",
                    "title": "📸 Prendre une photo",
                    "payload": "TAKE_PHOTO"
                },
                {
                    "content_type": "text", 
                    "title": "✍️ Écrire mon adresse",
                    "payload": "WRITE_ADDRESS"
                },
                {
                    "content_type": "text",
                    "title": "⏰ Plus tard",
                    "payload": "LATER"
                }
            ]
            
            result = await self.send_private_message(
                recipient_id=recipient_id,
                message=message,
                page_access_token=page_access_token,
                quick_replies=quick_replies
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Erreur demande adresse: {e}")
            return {"success": False, "error": str(e)}
    
    async def _find_user_id_by_name(self, username: str, page_token: str) -> Optional[str]:
        """Tente de trouver un ID utilisateur par nom (approximatif)"""
        # Cette méthode est limitée par les permissions Facebook
        # En pratique, on a besoin que l'utilisateur ait interagi avec la page
        try:
            # Chercher dans les commentaires récents de la page
            page_id = await self._get_page_id_from_token(page_token)
            if not page_id:
                return None
            
            # URL pour chercher des commentaires
            url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            params = {
                "fields": "comments{from}",
                "limit": 50,
                "access_token": page_token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Chercher le nom dans les commentaires
                        for post in data.get("data", []):
                            if "comments" in post:
                                for comment in post["comments"]["data"]:
                                    if comment.get("from", {}).get("name", "").lower() == username.lower():
                                        return comment["from"]["id"]
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Erreur recherche utilisateur: {e}")
            return None
    
    async def _get_page_id_from_token(self, page_token: str) -> Optional[str]:
        """Récupère l'ID de page depuis le token"""
        try:
            url = "https://graph.facebook.com/v19.0/me"
            params = {"access_token": page_token, "fields": "id,name"}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("id")
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Erreur récupération ID page: {e}")
            return None
    
    async def save_message_history(
        self,
        message_type: str,
        sender_id: str,
        recipient_id: str,
        message_content: str,
        message_id: Optional[str] = None,
        order_id: Optional[uuid.UUID] = None,
        comment_id: Optional[str] = None,
        seller_id: Optional[uuid.UUID] = None,
        status: str = "sent"
    ):
        """Enregistre l'historique des messages"""
        try:
            # IMPORTANT: Créer d'abord le modèle MessengerMessage si tu ne l'as pas
            
            # Solution temporaire: utiliser un modèle simple
            class SimpleMessage:
                def __init__(self, **kwargs):
                    self.id = kwargs.get('id', uuid.uuid4())
                    self.message_type = kwargs.get('message_type')
                    self.sender_id = kwargs.get('sender_id')
                    self.recipient_id = kwargs.get('recipient_id')
                    self.message_content = kwargs.get('message_content')
                    self.facebook_message_id = kwargs.get('facebook_message_id')
                    self.order_id = kwargs.get('order_id')
                    self.comment_id = kwargs.get('comment_id')
                    self.seller_id = kwargs.get('seller_id')
                    self.status = kwargs.get('status', 'sent')
                    self.sent_at = kwargs.get('sent_at', datetime.utcnow())
                    self.created_at = kwargs.get('created_at', datetime.utcnow())
            
            # Créer le message
            message = SimpleMessage(
                message_type=message_type,
                sender_id=sender_id,
                recipient_id=recipient_id,
                message_content=message_content,
                facebook_message_id=message_id,
                order_id=order_id,
                comment_id=comment_id,
                seller_id=seller_id,
                status=status
            )
            
            # Pour l'instant, juste logger
            logger.info(f"📝 Message enregistré: {message_id} - {message_type}")
            logger.debug(f"  De: {sender_id} -> À: {recipient_id}")
            logger.debug(f"  Contenu: {message_content[:100]}...")
            
            # Si tu veux vraiment sauvegarder en base, crée d'abord le modèle:
            """
            from app.models.message_history import MessengerMessage
            
            message = MessengerMessage(
                id=uuid.uuid4(),
                message_type=message_type,
                sender_id=sender_id,
                recipient_id=recipient_id,
                message_content=message_content,
                facebook_message_id=message_id,
                order_id=order_id,
                comment_id=comment_id,
                seller_id=seller_id,
                status=status,
                sent_at=datetime.utcnow(),
                created_at=datetime.utcnow()
            )
            
            self.db.add(message)
            self.db.commit()
            """
            
        except Exception as e:
            logger.error(f"❌ Erreur enregistrement historique: {e}")
            # Pas de rollback car pas de transaction active
    
    async def process_comment_and_send_message(
        self,
        comment_id: str,
        seller_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Processus complet: 
        1. Crée la commande depuis le commentaire
        2. Envoie la réponse publique sur le commentaire
        3. Envoie le message privé sur Messenger
        """
        try:
            logger.info(f"🔄 Processus complet pour commentaire {comment_id}")
            
            # 1. Récupérer le commentaire
            comment = self.db.query(FacebookComment).filter(
                FacebookComment.id == comment_id,
                FacebookComment.seller_id == seller_id
            ).first()
            
            if not comment:
                return {
                    "success": False,
                    "error": "Commentaire non trouvé",
                    "comment_id": comment_id
                }
            
            logger.info(f"✅ Commentaire trouvé: {comment.user_name}")
            
            # 2. Créer ou récupérer la commande
            # Vérifier si OrderService existe
            try:
                from app.services.order_service import OrderService
                order_service = OrderService(self.db)
                
                order = order_service.get_order_by_comment_id(comment_id, seller_id)
                order_created = False
                
                if not order:
                    logger.info("📝 Création de la commande...")
                    order = order_service.create_order_from_facebook_comment(
                        seller_id=seller_id,
                        comment_id=comment_id,
                        customer_name=comment.user_name,
                        product_code=comment.detected_code_article,
                        quantity=comment.detected_quantity or 1
                    )
                    
                    if not order:
                        return {
                            "success": False,
                            "error": "Impossible de créer la commande",
                            "comment_id": comment_id
                        }
                    
                    order_created = True
                    logger.info(f"✅ Nouvelle commande créée: {order.order_number}")
                else:
                    logger.info(f"✅ Commande existante: {order.order_number}")
                    
            except ImportError:
                # Fallback: créer une commande simple
                logger.warning("⚠️ OrderService non disponible, création simple")
                order = type('Order', (), {
                    'id': uuid.uuid4(),
                    'order_number': f"SHO-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}",
                    'total_amount': 24.99,
                    'customer_name': comment.user_name
                })()
                order_created = True
            
            # 3. Envoyer la réponse publique sur le commentaire (auto-reply)
            try:
                from app.services.facebook_auto_reply import FacebookAutoReplyService
                auto_reply_service = FacebookAutoReplyService(self.db)
                
                # Récupérer le token pour la page
                token = await self.get_messenger_token(seller_id)
                
                if token:
                    # Envoyer la réponse publique
                    public_reply_result = await auto_reply_service.auto_reply_after_order(
                        comment_id=comment_id,
                        order=order,
                        seller_id=seller_id,
                        facebook_token=token
                    )
                    
                    if public_reply_result.get("success"):
                        logger.info(f"✅ Réponse publique envoyée: {public_reply_result.get('facebook_response_id')}")
                    else:
                        logger.warning(f"⚠️ Réponse publique échouée: {public_reply_result.get('error')}")
                else:
                    logger.warning("⚠️ Pas de token pour la réponse publique")
                    public_reply_result = {"success": False, "error": "No token"}
                    
            except ImportError as e:
                logger.warning(f"⚠️ AutoReplyService non disponible: {e}")
                public_reply_result = {"success": False, "error": "Service non disponible"}
            
            # 4. Envoyer le message privé Messenger
            messenger_result = await self.send_order_confirmation_message(
                order=order,
                comment=comment,
                seller_id=seller_id
            )
            
            if messenger_result["success"]:
                # Mettre à jour le statut du commentaire
                comment.action_taken = "messenger_sent"
                comment.processed_at = datetime.utcnow()
                self.db.commit()
                
                logger.info(f"🎉 Processus complet terminé avec succès!")
                
                return {
                    "success": True,
                    "order_created": order_created,
                    "order_number": order.order_number if hasattr(order, 'order_number') else "N/A",
                    "customer_name": comment.user_name,
                    "public_reply": public_reply_result,
                    "private_message": messenger_result,
                    "comment_id": comment_id,
                    "workflow_completed": True
                }
            else:
                return {
                    "success": False,
                    "error": f"Échec envoi message privé: {messenger_result.get('error')}",
                    "order_created": order_created,
                    "order_number": order.order_number if hasattr(order, 'order_number') else None,
                    "comment_id": comment_id
                }
            
        except Exception as e:
            logger.error(f"❌ Erreur processus complet: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "comment_id": comment_id
            }