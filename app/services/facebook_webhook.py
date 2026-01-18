import hashlib
import hmac
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

class FacebookWebhookService:
    """
    Service de gestion des webhooks Facebook - Version Production
    Validation sécurisée et parsing robuste des événements
    """
    
    def __init__(self):
        # 🔥 Validation critique de la configuration
        self.app_secret = settings.FACEBOOK_APP_SECRET or ""
        self.verify_token = settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN or ""
        
        if not self.app_secret:
            logger.critical("❌ FACEBOOK_APP_SECRET non configuré pour les webhooks")
        if not self.verify_token:
            logger.critical("❌ FACEBOOK_WEBHOOK_VERIFY_TOKEN non configuré")
        
        self.supported_events = [
            "feed",              # Posts, commentaires
            "conversations",     # Conversations
            "messages",          # Messages Messenger
            "messaging_postbacks",
            "messaging_optins",
            "messaging_referrals",
            "message_deliveries",
            "message_reads",
            "messaging_handovers",
            "messaging_policy_enforcement",
            "live_videos",       # Lives
            "video_publishing",
            "ratings",           # Évaluations
            "mention",           # Mentions
            "standby",           # Mode standby
        ]
        
        logger.info("🚀 FacebookWebhookService initialisé")
    
    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        🔥 CORRIGÉ: Vérifie la signature HMAC SHA1 de Facebook
        Retourne False si la signature est invalide ou si app_secret manque
        """
        if not self.app_secret:
            logger.error("❌ App secret manquant pour vérification signature")
            return False
        
        if not signature or not signature.startswith("sha1="):
            logger.warning("⚠️ Signature webhook invalide ou malformée")
            return False
        
        try:
            # Nettoyer la signature
            signature_hash = signature[5:]  # Retirer "sha1="
            
            # Générer la signature attendue
            expected_signature = hmac.new(
                self.app_secret.encode('utf-8'),
                payload,
                hashlib.sha1
            ).hexdigest()
            
            # Comparaison sécurisée contre les attaques timing
            is_valid = hmac.compare_digest(signature_hash, expected_signature)
            
            if not is_valid:
                logger.warning(f"⚠️ Signature invalide: reçu {signature_hash[:8]}..., attendu {expected_signature[:8]}...")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ Erreur vérification signature: {e}")
            return False
    
    def verify_challenge(self, hub_mode: str, hub_verify_token: str, hub_challenge: str) -> Optional[str]:
        """
        🔥 CORRIGÉ: Valide le challenge d'abonnement webhook
        Retourne le challenge si valide, None sinon
        """
        if hub_mode != "subscribe":
            logger.warning(f"⚠️ Mode webhook invalide: {hub_mode}")
            return None
        
        if hub_verify_token != self.verify_token:
            logger.warning(f"⚠️ Token de vérification invalide: reçu {hub_verify_token[:10]}...")
            return None
        
        try:
            # S'assurer que le challenge est un nombre
            challenge = str(int(hub_challenge))
            logger.info(f"✅ Challenge webhook validé: {challenge}")
            return challenge
        except (ValueError, TypeError):
            logger.warning(f"⚠️ Challenge invalide: {hub_challenge}")
            return None
    
    def parse_webhook_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔥 CORRIGÉ: Parse et valide un événement webhook Facebook
        Structure standardisée pour le traitement ultérieur
        """
        parsed = {
            "success": False,
            "object_type": "unknown",
            "event_type": "unknown",
            "page_id": None,
            "timestamp": datetime.utcnow().isoformat(),
            "entries": [],
            "raw_data": event_data
        }
        
        try:
            # Validation basique
            if not isinstance(event_data, dict):
                logger.error("❌ Données webhook invalides: pas un dictionnaire")
                return parsed
            
            object_type = event_data.get("object")
            if not object_type:
                logger.warning("⚠️ Type d'objet webhook manquant")
                return parsed
            
            parsed["object_type"] = object_type
            entries = event_data.get("entry", [])
            
            if not entries:
                logger.warning("⚠️ Aucune entrée dans l'événement webhook")
                parsed["success"] = True  # Facebook envoie parfois des pings vides
                return parsed
            
            # Parser chaque entrée
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                
                parsed_entry = self._parse_webhook_entry(entry, object_type)
                if parsed_entry:
                    parsed["entries"].append(parsed_entry)
                    # Prendre le premier page_id valide
                    if not parsed["page_id"] and parsed_entry.get("page_id"):
                        parsed["page_id"] = parsed_entry["page_id"]
            
            parsed["success"] = len(parsed["entries"]) > 0
            
            if parsed["success"]:
                logger.info(f"✅ Webhook parsé: {object_type} - {len(parsed['entries'])} entrées")
            else:
                logger.warning(f"⚠️ Webhook parsé mais aucune donnée valide: {object_type}")
            
        except Exception as e:
            logger.error(f"❌ Erreur parsing webhook: {e}", exc_info=True)
            parsed["error"] = str(e)
        
        return parsed
    
    def _parse_webhook_entry(self, entry: Dict[str, Any], object_type: str) -> Optional[Dict[str, Any]]:
        """
        🔥 CORRIGÉ: Parse une entrée webhook individuelle
        """
        try:
            parsed_entry = {
                "page_id": entry.get("id"),
                "time": entry.get("time"),
                "changes": [],
                "messaging": [],
                "standby": []
            }
            
            # Traiter les changements
            for change in entry.get("changes", []):
                parsed_change = self._parse_webhook_change(change, object_type)
                if parsed_change:
                    parsed_entry["changes"].append(parsed_change)
            
            # Traiter les messages Messenger
            for messaging in entry.get("messaging", []):
                parsed_message = self._parse_messaging_event(messaging)
                if parsed_message:
                    parsed_entry["messaging"].append(parsed_message)
            
            # Traiter le mode standby
            for standby in entry.get("standby", []):
                parsed_standby = self._parse_standby_event(standby)
                if parsed_standby:
                    parsed_entry["standby"].append(parsed_standby)
            
            # Retourner seulement si on a des données
            if (parsed_entry["changes"] or parsed_entry["messaging"] or parsed_entry["standby"]):
                return parsed_entry
            
        except Exception as e:
            logger.error(f"❌ Erreur parsing entrée webhook: {e}")
        
        return None
    
    def _parse_webhook_change(self, change: Dict[str, Any], object_type: str) -> Optional[Dict[str, Any]]:
        """
        🔥 CORRIGÉ: Parse un changement webhook
        """
        try:
            field = change.get("field")
            value = change.get("value", {})
            
            if not field:
                return None
            
            parsed_change = {
                "field": field,
                "value": value,
                "event_type": "change",
                "details": {}
            }
            
            # 🔥 PARSER LES DIFFÉRENTS TYPES DE CHANGEMENTS
            
            # FEED - Posts et commentaires
            if field == "feed":
                item = value.get("item")
                verb = value.get("verb")
                
                if item == "post" and verb == "add":
                    parsed_change["event_type"] = "post_added"
                    parsed_change["details"] = {
                        "post_id": value.get("post_id"),
                        "sender_id": value.get("sender_id"),
                        "sender_name": value.get("sender_name"),
                        "message": value.get("message"),
                        "link": value.get("link")
                    }
                
                elif item == "comment":
                    parsed_change["event_type"] = f"comment_{verb}"  # comment_add, comment_edit, comment_remove
                    parsed_change["details"] = {
                        "comment_id": value.get("comment_id"),
                        "post_id": value.get("post_id"),
                        "parent_id": value.get("parent_id"),
                        "sender_id": value.get("sender_id"),
                        "sender_name": value.get("sender_name"),
                        "message": value.get("message")
                    }
            
            # LIVE VIDEOS
            elif field == "live_videos":
                parsed_change["event_type"] = "live_video_update"
                parsed_change["details"] = {
                    "video_id": value.get("video_id"),
                    "status": value.get("status"),
                    "broadcast_id": value.get("broadcast_id")
                }
            
            # CONVERSATIONS
            elif field == "conversations":
                parsed_change["event_type"] = "conversation_update"
                parsed_change["details"] = value
            
            # RATINGS
            elif field == "ratings":
                parsed_change["event_type"] = "rating_added"
                parsed_change["details"] = {
                    "review_id": value.get("review_id"),
                    "rating": value.get("rating"),
                    "review_text": value.get("review_text"),
                    "reviewer": value.get("reviewer")
                }
            
            # MENTIONS
            elif field == "mention":
                parsed_change["event_type"] = "mention_added"
                parsed_change["details"] = value
            
            # AUTRES CHAMPS
            else:
                parsed_change["event_type"] = f"{field}_update"
                parsed_change["details"] = value
            
            return parsed_change
            
        except Exception as e:
            logger.error(f"❌ Erreur parsing changement: {e}")
            return None
    
    def _parse_messaging_event(self, messaging: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        🔥 CORRIGÉ: Parse un événement Messenger
        """
        try:
            sender = messaging.get("sender", {}).get("id")
            recipient = messaging.get("recipient", {}).get("id")
            timestamp = messaging.get("timestamp")
            
            if not sender or not recipient:
                return None
            
            parsed_event = {
                "sender_id": sender,
                "recipient_id": recipient,
                "timestamp": timestamp,
                "event_type": "unknown",
                "message_data": {}
            }
            
            # 🔥 DÉTECTION DU TYPE D'ÉVÉNEMENT
            
            # Message texte
            if "message" in messaging:
                message = messaging["message"]
                parsed_event["event_type"] = "message_received"
                parsed_event["message_data"] = {
                    "mid": message.get("mid"),
                    "text": message.get("text", ""),
                    "quick_reply": message.get("quick_reply"),
                    "attachments": message.get("attachments", []),
                    "is_echo": message.get("is_echo", False)
                }
            
            # Postback (boutons)
            elif "postback" in messaging:
                postback = messaging["postback"]
                parsed_event["event_type"] = "postback_received"
                parsed_event["message_data"] = {
                    "payload": postback.get("payload"),
                    "title": postback.get("title"),
                    "referral": postback.get("referral")
                }
            
            # Livraison
            elif "delivery" in messaging:
                delivery = messaging["delivery"]
                parsed_event["event_type"] = "message_delivered"
                parsed_event["message_data"] = {
                    "mids": delivery.get("mids", []),
                    "watermark": delivery.get("watermark")
                }
            
            # Lecture
            elif "read" in messaging:
                read = messaging["read"]
                parsed_event["event_type"] = "message_read"
                parsed_event["message_data"] = {
                    "watermark": read.get("watermark")
                }
            
            # Opt-in
            elif "optin" in messaging:
                optin = messaging["optin"]
                parsed_event["event_type"] = "optin_received"
                parsed_event["message_data"] = {
                    "ref": optin.get("ref"),
                    "user_ref": optin.get("user_ref")
                }
            
            # Referral
            elif "referral" in messaging:
                referral = messaging["referral"]
                parsed_event["event_type"] = "referral_received"
                parsed_event["message_data"] = {
                    "ref": referral.get("ref"),
                    "source": referral.get("source"),
                    "type": referral.get("type")
                }
            
            else:
                # Événement non reconnu
                return None
            
            return parsed_event
            
        except Exception as e:
            logger.error(f"❌ Erreur parsing messaging: {e}")
            return None
    
    def _parse_standby_event(self, standby: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        🔥 CORRIGÉ: Parse un événement standby
        """
        try:
            # Le mode standby a la même structure que messaging
            return self._parse_messaging_event(standby)
        except Exception as e:
            logger.error(f"❌ Erreur parsing standby: {e}")
            return None
    
    def should_process_event(self, parsed_event: Dict[str, Any]) -> bool:
        """
        🔥 NOUVEAU: Détermine si un événement doit être traité
        Filtrage par type d'événement et validation
        """
        try:
            # Vérifier le succès du parsing
            if not parsed_event.get("success", False):
                logger.debug("⚠️ Événement non traité: parsing échoué")
                return False
            
            # Vérifier le type d'objet
            object_type = parsed_event.get("object_type")
            if object_type not in ["page", "instagram", "whatsapp_business_account"]:
                logger.debug(f"⚠️ Type d'objet non supporté: {object_type}")
                return False
            
            # Vérifier qu'il y a des entrées
            entries = parsed_event.get("entries", [])
            if not entries:
                logger.debug("ℹ️ Aucune entrée à traiter")
                return False
            
            # 🔥 FILTRES SPÉCIFIQUES POUR LIVE COMMERCE
            
            for entry in entries:
                # Ignorer les événements de livraison/lecture si non critiques
                for messaging in entry.get("messaging", []):
                    event_type = messaging.get("event_type", "")
                    if event_type in ["message_delivered", "message_read"]:
                        logger.debug(f"ℹ️ Événement {event_type} ignoré (non critique)")
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur décision traitement: {e}")
            return False
    
    def extract_critical_data(self, parsed_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        🔥 NOUVEAU: Extrait les données critiques pour le Live Commerce
        """
        critical_data = {
            "page_id": parsed_event.get("page_id"),
            "timestamp": datetime.utcnow().isoformat(),
            "events": []
        }
        
        try:
            for entry in parsed_event.get("entries", []):
                page_id = entry.get("page_id")
                
                # Commentaires (CRITIQUE pour Live Commerce)
                for change in entry.get("changes", []):
                    if change.get("field") == "feed":
                        value = change.get("value", {})
                        if value.get("item") == "comment":
                            event_data = {
                                "type": "comment",
                                "comment_id": value.get("comment_id"),
                                "post_id": value.get("post_id"),
                                "sender_id": value.get("sender_id"),
                                "sender_name": value.get("sender_name", "Utilisateur inconnu"),
                                "message": value.get("message", ""),
                                "verb": value.get("verb"),
                                "page_id": page_id
                            }
                            critical_data["events"].append(event_data)
                
                # Messages Messenger (CRITIQUE pour support)
                for messaging in entry.get("messaging", []):
                    if messaging.get("event_type") == "message_received":
                        event_data = {
                            "type": "message",
                            "sender_id": messaging.get("sender_id"),
                            "message_id": messaging.get("message_data", {}).get("mid"),
                            "text": messaging.get("message_data", {}).get("text", ""),
                            "page_id": page_id
                        }
                        critical_data["events"].append(event_data)
                
                # Lives vidéos (CRITIQUE pour Live Commerce)
                for change in entry.get("changes", []):
                    if change.get("field") == "live_videos":
                        event_data = {
                            "type": "live_video",
                            "video_id": change.get("value", {}).get("video_id"),
                            "status": change.get("value", {}).get("status"),
                            "page_id": page_id
                        }
                        critical_data["events"].append(event_data)
        
        except Exception as e:
            logger.error(f"❌ Erreur extraction données critiques: {e}")
        
        return critical_data
    
    def generate_response(self, status: str = "processed") -> Dict[str, Any]:
        """
        🔥 NOUVEAU: Génère une réponse standard pour Facebook
        """
        responses = {
            "processed": {"status": "success", "message": "Webhook traité avec succès"},
            "ignored": {"status": "ignored", "message": "Événement non critique ignoré"},
            "error": {"status": "error", "message": "Erreur de traitement"},
            "invalid": {"status": "invalid", "message": "Signature ou données invalides"}
        }
        
        response = responses.get(status, responses["error"])
        response["timestamp"] = datetime.utcnow().isoformat()
        
        return response


# 🔥 Instance singleton avec validation
try:
    facebook_webhook_service = FacebookWebhookService()
    logger.info("✅ FacebookWebhookService initialisé avec succès")
except Exception as e:
    logger.critical(f"💥 Échec initialisation FacebookWebhookService: {e}")
    
    # Service dégradé
    class DegradedWebhookService:
        def __init__(self):
            self.app_secret = ""
            self.verify_token = ""
        
        def verify_signature(self, *args, **kwargs):
            return False
        
        def verify_challenge(self, *args, **kwargs):
            return None
        
        def parse_webhook_event(self, event_data):
            return {"success": False, "error": "Service non configuré"}
    
    facebook_webhook_service = DegradedWebhookService()