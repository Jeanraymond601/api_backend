# app/services/nlp/intent_detector.py
import logging
from typing import Dict, Any, List
import re

logger = logging.getLogger(__name__)

class IntentResult:
    def __init__(self):
        self.intent_type = 'unknown'
        self.confidence = 0.0
        self.sentiment = 'neutral'
        self.extracted_products = []
        self.entities = {}
        self.keywords = []

class IntentDetector:
    def __init__(self, model_path: str = None):
        self.purchase_keywords = [
            'je veux', 'je voudrais', 'je souhaite', 'commander', 'acheter',
            'prendre', 'donnez-moi', 'je prends', 'je commande', 'réservation',
            'livraison', 'combien', 'prix', 'tarif', 'disponible', 'stock',
            'envoyer', 'expédier', 'payer', 'paiement', 'facture'
        ]
        
        self.question_keywords = [
            'comment', 'quand', 'où', 'pourquoi', 'quel', 'quelle', 'quels', 'quelles',
            'est-ce que', 'comment faire', 'comment ça marche'
        ]
        
        self.complaint_keywords = [
            'problème', 'erreur', 'faux', 'incorrect', 'mauvais', 'pas content',
            'insatisfait', 'réclamation', 'plainte', 'bug', 'ne marche pas',
            'défectueux', 'cassé', 'abîmé', 'retard', 'perdu'
        ]
        
        # Patterns pour extraire des produits
        self.product_patterns = [
            r'(\d+)\s*([\w\s]+?)(?:s|$)',  # "2 pizzas"
            r'([\w\s]+?)\s*x\s*(\d+)',     # "pizza x 2"
            r'(\d+)\s*x\s*([\w\s]+)',      # "2 x pizza"
        ]

    async def analyze_comment(self, text: str) -> IntentResult:
        """Analyse un commentaire pour détecter l'intention"""
        result = IntentResult()
        text_lower = text.lower().strip()
        
        # Détection d'intention basée sur les mots-clés
        purchase_score = sum(1 for keyword in self.purchase_keywords if keyword in text_lower)
        question_score = sum(1 for keyword in self.question_keywords if keyword in text_lower)
        complaint_score = sum(1 for keyword in self.complaint_keywords if keyword in text_lower)
        
        # Détection de sentiment basique
        positive_words = ['super', 'excellent', 'génial', 'parfait', 'merci', 'bravo', 'félicitations']
        negative_words = ['nul', 'horrible', 'déçu', 'déception', 'pas bien', 'mauvais']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            result.sentiment = 'positive'
        elif negative_count > positive_count:
            result.sentiment = 'negative'
        else:
            result.sentiment = 'neutral'
        
        # Déterminer l'intention principale
        scores = {
            'purchase': purchase_score,
            'question': question_score,
            'complaint': complaint_score
        }
        
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]
        
        if max_score > 0:
            result.intent_type = max_intent
            result.confidence = min(max_score / 5, 1.0)  # Normaliser à 0-1
        else:
            result.intent_type = 'unknown'
            result.confidence = 0.0
        
        # Extraire les produits
        result.extracted_products = self._extract_products(text_lower)
        
        # Extraire des entités (prix, quantités)
        result.entities = self._extract_entities(text_lower)
        
        logger.info(f"Analyse commentaire: intent={result.intent_type}, confidence={result.confidence}, products={len(result.extracted_products)}")
        
        return result
    
    def _extract_products(self, text: str) -> List[Dict[str, Any]]:
        """Extrait les produits mentionnés dans le texte"""
        products = []
        
        for pattern in self.product_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                quantity = int(match.group(1)) if match.group(1).isdigit() else 1
                product_name = match.group(2).strip()
                
                # Nettoyer le nom du produit
                product_name = re.sub(r'\s+', ' ', product_name)
                
                # Ajouter seulement si le nom n'est pas trop court
                if len(product_name) > 2:
                    products.append({
                        'name': product_name,
                        'quantity': quantity,
                        'code': self._generate_product_code(product_name),
                        'confidence': 0.7
                    })
        
        # Si pas de pattern trouvé, chercher des mots-clés de produits communs
        if not products:
            common_products = ['pizza', 'burger', 'boisson', 'menu', 'dessert', 'salade', 'sandwich']
            for product in common_products:
                if product in text:
                    # Essayer de deviner la quantité
                    quantity = 1
                    quantity_match = re.search(rf'(\d+)\s*{product}', text)
                    if quantity_match:
                        quantity = int(quantity_match.group(1))
                    
                    products.append({
                        'name': product,
                        'quantity': quantity,
                        'code': product.upper()[:3],
                        'confidence': 0.5
                    })
        
        return products
    
    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Extrait des entités du texte"""
        entities = {
            'prices': [],
            'quantities': [],
            'locations': [],
            'dates': []
        }
        
        # Extraire les prix
        price_patterns = [
            r'(\d+)\s*(?:€|euro|euros|mg|ar|mga)',
            r'(?:€|euro|euros|mg|ar|mga)\s*(\d+)'
        ]
        
        for pattern in price_patterns:
            prices = re.findall(pattern, text)
            entities['prices'].extend([int(p) for p in prices if p.isdigit()])
        
        # Extraire les quantités
        quantity_matches = re.findall(r'\b(\d+)\b', text)
        entities['quantities'] = [int(q) for q in quantity_matches if q.isdigit()]
        
        return entities
    
    def _generate_product_code(self, product_name: str) -> str:
        """Génère un code produit basé sur le nom"""
        # Prendre les 3 premières lettres (sans espaces)
        clean_name = re.sub(r'[^a-zA-Z]', '', product_name)
        if len(clean_name) >= 3:
            return clean_name[:3].upper()
        else:
            return clean_name.upper().ljust(3, 'X')