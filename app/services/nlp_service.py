# app/services/nlp_service.py
import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import numpy as np
from collections import Counter
import spacy
from textblob import TextBlob
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import string
from dataclasses import dataclass
from enum import Enum

# Télécharger les ressources NLTK si besoin
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('stopwords')
    nltk.download('wordnet')
    nltk.download('averaged_perceptron_tagger')

logger = logging.getLogger(__name__)

class IntentType(Enum):
    """Types d'intentions détectées"""
    QUESTION = "question"
    COMPLAINT = "complaint"
    COMPLIMENT = "compliment"
    ORDER = "order"
    INQUIRY = "inquiry"
    SUPPORT = "support"
    PRICE = "price"
    AVAILABILITY = "availability"
    DELIVERY = "delivery"
    REFUND = "refund"
    OTHER = "other"

class SentimentType(Enum):
    """Types de sentiment"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"

class PriorityLevel(Enum):
    """Niveaux de priorité"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

@dataclass
class NLPResult:
    """Résultat d'analyse NLP"""
    text: str
    intent: IntentType
    sentiment: SentimentType
    confidence: float
    entities: List[Dict[str, Any]]
    keywords: List[str]
    priority: PriorityLevel
    categories: List[str]
    language: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertit en dictionnaire"""
        return {
            "text": self.text,
            "intent": self.intent.value,
            "sentiment": self.sentiment.value,
            "confidence": round(self.confidence, 3),
            "entities": self.entities,
            "keywords": self.keywords,
            "priority": self.priority.value,
            "categories": self.categories,
            "language": self.language
        }

class NLPService:
    """
    Service NLP pour analyser les commentaires et messages Facebook
    """
    
    def __init__(self, model_name: str = "fr_core_news_sm"):
        """
        Initialise le service NLP
        """
        self.logger = logging.getLogger(__name__)
        
        # Charger le modèle spaCy
        try:
            self.nlp = spacy.load(model_name)
            self.logger.info(f"✅ Modèle spaCy chargé: {model_name}")
        except OSError:
            self.logger.warning(f"Modèle {model_name} non trouvé, téléchargement...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", model_name])
            self.nlp = spacy.load(model_name)
        
        # Initialiser NLTK
        self.stop_words = set(stopwords.words('french') + stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        
        # Dictionnaires personnalisés
        self.keyword_patterns = self._load_keyword_patterns()
        self.entity_patterns = self._load_entity_patterns()
        
        # Configuration
        self.min_confidence = 0.5
        self.max_keywords = 10
        
        self.logger.info("✅ Service NLP initialisé")
    
    def _load_keyword_patterns(self) -> Dict[str, List[str]]:
        """
        Charge les patterns de mots-clés par catégorie
        """
        return {
            "question": [
                "combien", "prix", "coûte", "coût", "quel", "quelle", "quand",
                "comment", "où", "pourquoi", "est-ce que", "?", "how much",
                "price", "cost", "when", "how", "where", "why"
            ],
            "complaint": [
                "problème", "bug", "erreur", "cassé", "ne marche pas",
                "défaut", "mauvais", "nul", "horrible", "déçu", "déception",
                "fâché", "colère", "insatisfait", "réclamation",
                "problem", "broken", "not working", "defect", "bad",
                "terrible", "disappointed", "angry", "complaint"
            ],
            "compliment": [
                "super", "génial", "excellent", "parfait", "bravo", "félicitations",
                "merci", "thanks", "thank you", "awesome", "great", "perfect",
                "good", "nice", "love", "amazing", "fantastic", "wonderful"
            ],
            "order": [
                "commander", "achat", "acheter", "commande", "panier", "ajouter",
                "order", "buy", "purchase", "cart", "add to cart", "checkout"
            ],
            "inquiry": [
                "information", "renseignement", "détail", "spécification",
                "caractéristique", "info", "details", "information", "specs"
            ],
            "support": [
                "aide", "support", "assistance", "service client", "sav",
                "help", "customer service", "assistance", "support"
            ],
            "price": [
                "prix", "tarif", "coût", "montant", "€", "$", "euro", "dollar",
                "price", "cost", "amount", "discount", "réduction", "promotion",
                "solde", "sale", "offre", "offer"
            ],
            "availability": [
                "disponible", "stock", "rupture", "livraison", "délai",
                "available", "in stock", "out of stock", "delivery", "shipping"
            ],
            "delivery": [
                "livraison", "expédition", "colis", "livrer", "recevoir",
                "delivery", "shipping", "package", "ship", "receive"
            ],
            "refund": [
                "remboursement", "retour", "échanger", "garantie", "règlement",
                "refund", "return", "exchange", "warranty", "guarantee"
            ]
        }
    
    def _load_entity_patterns(self) -> Dict[str, List[Tuple[str, str]]]:
        """
        Charge les patterns d'entités pour la reconnaissance
        """
        return {
            "PRODUCT": [
                (r'\b(iphone|samsung|xiaomi|huawei)\b', 'MARQUE'),
                (r'\b(\d+)\s*(go|gb|mo)\b', 'STOCKAGE'),
                (r'\b(noir|blanc|rouge|bleu|vert|or|argent)\b', 'COULEUR'),
                (r'\b(\d+)\s*(inch|pouces|")\b', 'TAILLE_ECRAN'),
                (r'\b(\d+)\s*(mp|mégapixels)\b', 'APPAREIL_PHOTO'),
            ],
            "PRICE": [
                (r'\b(\d+[,.]?\d*)\s*[€$]\b', 'MONTANT'),
                (r'\b(gratuit|free)\b', 'GRATUIT'),
                (r'\b(promo|promotion|solde|discount|offre)\b', 'PROMOTION'),
            ],
            "DATE": [
                (r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', 'DATE'),
                (r'\b(aujourd\'hui|demain|hier|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b', 'JOUR'),
                (r'\b(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\b', 'MOIS'),
            ],
            "LOCATION": [
                (r'\b(paris|lyon|marseille|toulouse|nice|nantes|strasbourg|montpellier|bordeaux|lille)\b', 'VILLE_FR'),
                (r'\b(france|belgique|suisse|canada|espagne|italie|allemagne|portugal)\b', 'PAYS'),
            ]
        }
    
    def detect_language(self, text: str) -> str:
        """
        Détecte la langue du texte
        """
        # Simple detection basée sur les mots communs
        french_words = ['le', 'la', 'les', 'un', 'une', 'des', 'et', 'est']
        english_words = ['the', 'a', 'an', 'and', 'is', 'are', 'you', 'i']
        
        french_count = sum(1 for word in text.lower().split() if word in french_words)
        english_count = sum(1 for word in text.lower().split() if word in english_words)
        
        if french_count > english_count:
            return 'fr'
        elif english_count > french_count:
            return 'en'
        else:
            # Analyser avec TextBlob pour plus de précision
            try:
                blob = TextBlob(text)
                return blob.detect_language()
            except:
                return 'unknown'
    
    def preprocess_text(self, text: str, language: str = 'fr') -> str:
        """
        Prétraite le texte pour l'analyse
        """
        # Convertir en minuscules
        text = text.lower()
        
        # Supprimer la ponctuation
        text = text.translate(str.maketrans('', '', string.punctuation))
        
        # Tokenization
        tokens = word_tokenize(text, language='french' if language == 'fr' else 'english')
        
        # Supprimer les stop words
        tokens = [word for word in tokens if word not in self.stop_words]
        
        # Lemmatization
        tokens = [self.lemmatizer.lemmatize(word) for word in tokens]
        
        return ' '.join(tokens)
    
    def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """
        Extrait les mots-clés du texte
        """
        # Tokenization
        tokens = word_tokenize(text.lower())
        
        # Supprimer les stop words et ponctuation
        tokens = [word for word in tokens 
                 if word not in self.stop_words 
                 and word not in string.punctuation]
        
        # Calculer la fréquence
        word_freq = Counter(tokens)
        
        # Récupérer les mots les plus fréquents
        keywords = [word for word, freq in word_freq.most_common(max_keywords)]
        
        return keywords
    
    def detect_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Détecte les entités nommées dans le texte
        """
        entities = []
        
        # Utiliser spaCy pour les entités standard
        doc = self.nlp(text)
        for ent in doc.ents:
            entities.append({
                "text": ent.text,
                "label": ent.label_,
                "start": ent.start_char,
                "end": ent.end_char,
                "confidence": 0.8  # Estimation
            })
        
        # Ajouter les entités personnalisées via regex
        for entity_type, patterns in self.entity_patterns.items():
            for pattern, label in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    entities.append({
                        "text": match.group(),
                        "label": label,
                        "start": match.start(),
                        "end": match.end(),
                        "entity_type": entity_type,
                        "confidence": 0.7
                    })
        
        return entities
    
    def analyze_sentiment(self, text: str) -> Tuple[SentimentType, float]:
        """
        Analyse le sentiment du texte
        """
        try:
            # Utiliser TextBlob pour l'analyse de sentiment
            blob = TextBlob(text)
            
            # Score de polarité (-1 à 1)
            polarity = blob.sentiment.polarity
            
            # Déterminer le type de sentiment
            if polarity > 0.2:
                sentiment = SentimentType.POSITIVE
            elif polarity < -0.2:
                sentiment = SentimentType.NEGATIVE
            else:
                sentiment = SentimentType.NEUTRAL
            
            # Confidence basée sur la magnitude
            confidence = abs(polarity)
            
            return sentiment, confidence
            
        except Exception as e:
            self.logger.warning(f"Erreur analyse sentiment: {e}")
            return SentimentType.NEUTRAL, 0.0
    
    def detect_intent(self, text: str) -> Tuple[IntentType, float]:
        """
        Détecte l'intention principale du texte
        """
        text_lower = text.lower()
        scores = {}
        
        # Calculer les scores pour chaque intention
        for intent_type, keywords in self.keyword_patterns.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            
            # Normaliser le score
            normalized_score = score / len(keywords) if keywords else 0
            scores[intent_type] = normalized_score
        
        # Trouver l'intention avec le score le plus élevé
        if scores:
            best_intent = max(scores, key=scores.get)
            best_score = scores[best_intent]
            
            # Convertir en IntentType
            try:
                intent_type = IntentType(best_intent)
            except ValueError:
                intent_type = IntentType.OTHER
                best_score = max(best_score, self.min_confidence)
            
            # Vérifier le seuil de confiance
            if best_score >= self.min_confidence:
                return intent_type, best_score
        
        # Par défaut
        return IntentType.OTHER, 0.5
    
    def determine_priority(
        self, 
        intent: IntentType, 
        sentiment: SentimentType,
        has_urgent_keywords: bool = False
    ) -> PriorityLevel:
        """
        Détermine le niveau de priorité
        """
        # Règles de priorité
        if has_urgent_keywords:
            return PriorityLevel.URGENT
        
        if intent == IntentType.COMPLAINT and sentiment == SentimentType.NEGATIVE:
            return PriorityLevel.HIGH
        
        if intent == IntentType.QUESTION and sentiment == SentimentType.NEGATIVE:
            return PriorityLevel.HIGH
        
        if intent == IntentType.SUPPORT or intent == IntentType.REFUND:
            return PriorityLevel.MEDIUM
        
        if intent == IntentType.ORDER or intent == IntentType.PRICE:
            return PriorityLevel.MEDIUM
        
        return PriorityLevel.LOW
    
    def extract_categories(self, text: str, entities: List[Dict]) -> List[str]:
        """
        Extrait les catégories du texte
        """
        categories = set()
        
        # Catégories basées sur les entités
        for entity in entities:
            if entity.get("entity_type") == "PRODUCT":
                categories.add("produit")
            elif entity.get("entity_type") == "PRICE":
                categories.add("prix")
            elif entity.get("entity_type") == "DELIVERY":
                categories.add("livraison")
        
        # Catégories basées sur les mots-clés
        text_lower = text.lower()
        
        category_keywords = {
            "technique": ["bug", "erreur", "problème", "ne marche pas", "planté"],
            "commercial": ["commande", "achat", "panier", "paiement"],
            "logistique": ["livraison", "expédition", "colis", "transport"],
            "service": ["sav", "support", "assistance", "service client"],
            "produit": ["caractéristique", "spécification", "fonctionnalité"],
            "promotion": ["promo", "réduction", "solde", "offre"]
        }
        
        for category, keywords in category_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    categories.add(category)
                    break
        
        return list(categories)
    
    def analyze_comment(self, text: str) -> NLPResult:
        """
        Analyse complète d'un commentaire
        """
        # Détection de la langue
        language = self.detect_language(text)
        
        # Prétraitement
        cleaned_text = self.preprocess_text(text, language)
        
        # Analyse de sentiment
        sentiment, sentiment_confidence = self.analyze_sentiment(text)
        
        # Détection d'intention
        intent, intent_confidence = self.detect_intent(text)
        
        # Confiance globale
        confidence = (sentiment_confidence + intent_confidence) / 2
        
        # Extraction d'entités
        entities = self.detect_entities(text)
        
        # Extraction de mots-clés
        keywords = self.extract_keywords(cleaned_text, self.max_keywords)
        
        # Détection de mots urgents
        urgent_keywords = ["urgent", "immédiat", "important", "asap", "vite", "rapide"]
        has_urgent = any(keyword in text.lower() for keyword in urgent_keywords)
        
        # Détermination de priorité
        priority = self.determine_priority(intent, sentiment, has_urgent)
        
        # Extraction de catégories
        categories = self.extract_categories(text, entities)
        
        # Créer le résultat
        result = NLPResult(
            text=text[:200],  # Tronquer pour l'affichage
            intent=intent,
            sentiment=sentiment,
            confidence=confidence,
            entities=entities,
            keywords=keywords,
            priority=priority,
            categories=categories,
            language=language
        )
        
        return result
    
    def analyze_comment_intent(self, text: str) -> Dict[str, Any]:
        """
        Analyse rapide d'un commentaire pour l'intention (pour webhook)
        """
        try:
            result = self.analyze_comment(text)
            
            # Déterminer si c'est prioritaire
            priority = result.priority in [PriorityLevel.HIGH, PriorityLevel.URGENT]
            
            return {
                "intent": result.intent.value,
                "sentiment": result.sentiment.value,
                "confidence": result.confidence,
                "priority": priority,
                "entities": result.entities,
                "categories": result.categories,
                "language": result.language
            }
            
        except Exception as e:
            self.logger.error(f"Erreur analyse commentaire: {e}")
            return {
                "intent": IntentType.OTHER.value,
                "sentiment": SentimentType.NEUTRAL.value,
                "confidence": 0.0,
                "priority": False,
                "entities": [],
                "categories": [],
                "language": "unknown"
            }
    
    def analyze_message_intent(self, text: str) -> Dict[str, Any]:
        """
        Analyse d'un message Messenger
        """
        # Similar à analyse_comment_intent mais avec focus sur conversation
        result = self.analyze_comment_intent(text)
        
        # Ajouter des métriques spécifiques aux messages
        text_lower = text.lower()
        
        # Détection de questions
        is_question = any(q in text_lower for q in ['?', 'comment', 'pourquoi', 'quand', 'où'])
        
        # Détection de demande de contact
        wants_contact = any(word in text_lower for word in 
                           ['appeler', 'téléphoner', 'contact', 'appel', 'phone', 'tel'])
        
        result.update({
            "is_question": is_question,
            "wants_contact": wants_contact,
            "response_needed": is_question or result["priority"]
        })
        
        return result
    
    def analyze_post_for_live_commerce(self, text: str) -> Dict[str, Any]:
        """
        Analyse un post pour détecter si c'est du live commerce
        """
        text_lower = text.lower()
        
        # Mots-clés liés au live commerce
        live_keywords = [
            "live", "direct", "en direct", "streaming", "vidéo live",
            "shopping live", "live shopping", "vente en direct",
            "émission", "diffusion", "en ce moment", "maintenant"
        ]
        
        commerce_keywords = [
            "promo", "réduction", "offre", "solde", "prix", "coût",
            "achat", "commande", "acheter", "vendre", "produit",
            "article", "item", "disponible", "stock", "livraison"
        ]
        
        # Calcul des scores
        live_score = sum(1 for keyword in live_keywords if keyword in text_lower)
        commerce_score = sum(1 for keyword in commerce_keywords if keyword in text_lower)
        
        # Normalisation
        total_score = (live_score / len(live_keywords) + commerce_score / len(commerce_keywords)) / 2
        
        # Détection d'heure (souvent indiquée dans les lives)
        time_pattern = r'\b(\d{1,2})[hH](\d{0,2})?\b'
        has_time = bool(re.search(time_pattern, text))
        
        # Détection de date
        date_pattern = r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b'
        has_date = bool(re.search(date_pattern, text))
        
        return {
            "is_live_commerce": total_score > 0.3,  # Seuil
            "score": round(total_score, 3),
            "live_keywords_found": live_score,
            "commerce_keywords_found": commerce_score,
            "has_time": has_time,
            "has_date": has_date,
            "timestamp_detected": has_time or has_date
        }
    
    def extract_product_info(self, text: str) -> Dict[str, Any]:
        """
        Extrait les informations produit d'un texte
        """
        entities = self.detect_entities(text)
        
        product_info = {
            "brand": None,
            "model": None,
            "color": None,
            "size": None,
            "price": None,
            "quantity": None,
            "features": []
        }
        
        for entity in entities:
            if entity.get("entity_type") == "PRODUCT":
                if entity.get("label") == "MARQUE":
                    product_info["brand"] = entity["text"]
                elif entity.get("label") == "COULEUR":
                    product_info["color"] = entity["text"]
                elif entity.get("label") == "TAILLE_ECRAN":
                    product_info["size"] = entity["text"]
            
            elif entity.get("entity_type") == "PRICE":
                if entity.get("label") == "MONTANT":
                    product_info["price"] = entity["text"]
        
        # Détection de quantité
        quantity_pattern = r'\b(\d+)\s*(pcs|pièces|unités|unité|items?)\b'
        match = re.search(quantity_pattern, text.lower())
        if match:
            product_info["quantity"] = match.group(1)
        
        return product_info
    
    def generate_auto_response(
        self, 
        intent: str, 
        sentiment: str,
        language: str = 'fr'
    ) -> str:
        """
        Génère une réponse automatique basée sur l'intention et le sentiment
        """
        responses = {
            'fr': {
                'question': {
                    'positive': "Merci pour votre question ! Nous y répondrons rapidement.",
                    'neutral': "Bonjour, nous traitons votre question et reviendrons vers vous bientôt.",
                    'negative': "Nous sommes désolés pour ce désagrément. Notre équipe va examiner votre question."
                },
                'complaint': {
                    'positive': "Merci de nous avoir signalé ce problème. Nous le corrigeons.",
                    'neutral': "Nous prenons en compte votre réclamation et allons la traiter.",
                    'negative': "Nous nous excusons sincèrement. Notre service client va vous contacter."
                },
                'compliment': {
                    'positive': "Merci beaucoup pour votre compliment ! Cela nous encourage.",
                    'neutral': "Merci pour votre retour positif.",
                    'negative': "Merci pour votre commentaire."
                },
                'order': {
                    'positive': "Merci pour votre intérêt ! Nos conseillers sont disponibles pour vous aider.",
                    'neutral': "Pour toute commande, notre équipe commerciale est à votre disposition.",
                    'negative': "Nous comprenons vos préoccupations. Parlons-en pour trouver une solution."
                }
            },
            'en': {
                'question': {
                    'positive': "Thanks for your question! We'll answer it quickly.",
                    'neutral': "Hello, we're processing your question and will get back to you soon.",
                    'negative': "We're sorry for the inconvenience. Our team will review your question."
                },
                'complaint': {
                    'positive': "Thanks for reporting this issue. We're fixing it.",
                    'neutral': "We've noted your complaint and will handle it.",
                    'negative': "We sincerely apologize. Our customer service will contact you."
                },
                'compliment': {
                    'positive': "Thank you so much for your compliment! It encourages us.",
                    'neutral': "Thanks for your positive feedback.",
                    'negative': "Thank you for your comment."
                },
                'order': {
                    'positive': "Thanks for your interest! Our advisors are available to help you.",
                    'neutral': "For any order, our sales team is at your disposal.",
                    'negative': "We understand your concerns. Let's talk to find a solution."
                }
            }
        }
        
        # Récupérer la réponse appropriée
        lang_responses = responses.get(language, responses['fr'])
        intent_responses = lang_responses.get(intent, lang_responses['question'])
        response = intent_responses.get(sentiment, intent_responses['neutral'])
        
        return response
    
    def batch_analyze(self, texts: List[str]) -> List[NLPResult]:
        """
        Analyse un lot de textes
        """
        results = []
        for text in texts:
            try:
                result = self.analyze_comment(text)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Erreur analyse batch: {e}")
                # Ajouter un résultat par défaut
                results.append(NLPResult(
                    text=text[:200],
                    intent=IntentType.OTHER,
                    sentiment=SentimentType.NEUTRAL,
                    confidence=0.0,
                    entities=[],
                    keywords=[],
                    priority=PriorityLevel.LOW,
                    categories=[],
                    language="unknown"
                ))
        
        return results
    
    def get_statistics(self, results: List[NLPResult]) -> Dict[str, Any]:
        """
        Génère des statistiques à partir d'une liste de résultats
        """
        if not results:
            return {}
        
        stats = {
            "total": len(results),
            "by_intent": {},
            "by_sentiment": {},
            "by_priority": {},
            "average_confidence": 0,
            "common_categories": [],
            "common_keywords": []
        }
        
        # Compter les intentions
        for result in results:
            intent = result.intent.value
            stats["by_intent"][intent] = stats["by_intent"].get(intent, 0) + 1
            
            sentiment = result.sentiment.value
            stats["by_sentiment"][sentiment] = stats["by_sentiment"].get(sentiment, 0) + 1
            
            priority = result.priority.value
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
        
        # Calculer la confiance moyenne
        confidences = [r.confidence for r in results]
        stats["average_confidence"] = round(sum(confidences) / len(confidences), 3)
        
        # Trouver les catégories communes
        all_categories = []
        for result in results:
            all_categories.extend(result.categories)
        
        category_counter = Counter(all_categories)
        stats["common_categories"] = category_counter.most_common(5)
        
        # Trouver les mots-clés communs
        all_keywords = []
        for result in results:
            all_keywords.extend(result.keywords)
        
        keyword_counter = Counter(all_keywords)
        stats["common_keywords"] = keyword_counter.most_common(10)
        
        return stats