# app/nlp.py
"""
Module NLP pour l'analyse des intentions et l'extraction d'informations
"""
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class IntentResult:
    """Résultat de l'analyse d'intention"""
    def __init__(self):
        self.intent_type = 'unknown'
        self.confidence = 0.0
        self.sentiment = 'neutral'
        self.extracted_products = []
        self.entities = {}

class IntentDetector:
    """Détecteur d'intentions pour les commentaires et messages"""
    
    def __init__(self):
        self.purchase_keywords = [
            'je veux', 'je voudrais', 'commander', 'acheter', 'prendre',
            'donnez-moi', 'donne moi', 'prix', 'jp', 'je prends', 'je prens',
            'je vais prendre', 'je vais acheter', 'commande', 'achète',
            'je désire', 'je souhaite', 'je souhaiterais', 'je réserve',
            'stp', 'svp', 's\'il vous plaît', 's\'il te plaît'
        ]
        self.question_keywords = ['comment', 'quand', 'où', 'pourquoi', 'quel', 'quelle', '?']
        self.complaint_keywords = ['problème', 'erreur', 'faux', 'mauvais', 'pas content', 'réclamation', 'marchandise']
    
    async def analyze_comment(self, text: str) -> IntentResult:
        """Analyse un commentaire pour détecter l'intention"""
        result = IntentResult()
        text_lower = text.lower() if text else ""
        
        # Détection d'intention
        purchase_score = sum(1 for kw in self.purchase_keywords if kw in text_lower)
        question_score = sum(1 for kw in self.question_keywords if kw in text_lower)
        complaint_score = sum(1 for kw in self.complaint_keywords if kw in text_lower)
        
        scores = {
            'purchase': purchase_score,
            'question': question_score,
            'complaint': complaint_score
        }
        
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]
        
        if max_score > 0:
            result.intent_type = max_intent
            result.confidence = min(max_score / 3, 1.0)
        else:
            result.intent_type = 'unknown'
            result.confidence = 0.0
        
        # Détection de sentiment
        positive_words = ['super', 'excellent', 'génial', 'parfait', 'merci', 'bravo', 'top']
        negative_words = ['nul', 'horrible', 'déçu', 'déception', 'mauvais', 'pas bien']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            result.sentiment = 'positive'
        elif negative_count > positive_count:
            result.sentiment = 'negative'
        else:
            result.sentiment = 'neutral'
        
        # Extraction de produits
        result.extracted_products = self._extract_products(text)
        
        # Extraction d'entités
        result.entities = self._extract_entities(text)
        
        logger.info(f"Analyse commentaire: intent={result.intent_type}, confidence={result.confidence}")
        return result
    
    def _extract_products(self, text: str) -> List[Dict[str, Any]]:
        """Extrait les produits mentionnés"""
        products = []
        
        # 1. Codes produits avec quantités : "2 APL-IP15P"
        code_pattern = r'(\d+)\s*(?:x\s*)?([A-Z]{2,4}-[A-Z0-9]{2,6})'
        code_matches = re.finditer(code_pattern, text, re.IGNORECASE)
        
        for match in code_matches:
            try:
                quantity = int(match.group(1))
                product_code = match.group(2).upper()
                
                products.append({
                    'name': product_code,
                    'quantity': quantity,
                    'code': product_code,
                    'price': None,
                    'confidence': 0.9
                })
            except:
                continue
        
        # 2. Codes produits sans quantités : "APL-IP15P"
        simple_codes = re.findall(r'\b([A-Z]{2,4}-[A-Z0-9]{2,6})\b', text)
        for code in simple_codes:
            code_upper = code.upper()
            if not any(p['code'] == code_upper for p in products):
                products.append({
                    'name': code_upper,
                    'quantity': 1,
                    'code': code_upper,
                    'price': None,
                    'confidence': 0.7
                })
        
        # 3. Produits génériques
        generic_patterns = [
            r'(\d+)\s*([\w\s]+?)(?:s|$)',  # "2 pizzas"
            r'([\w\s]+?)\s*x\s*(\d+)',     # "pizza x 2"
        ]
        
        for pattern in generic_patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                try:
                    quantity = int(match.group(1)) if match.group(1).isdigit() else 1
                    product_name = match.group(2).strip()
                    
                    if len(product_name) > 2 and product_name not in ['de', 'la', 'le', 'et', 'un', 'une', 'des']:
                        products.append({
                            'name': product_name,
                            'quantity': quantity,
                            'code': product_name[:3].upper().replace(' ', ''),
                            'price': None,
                            'confidence': 0.6
                        })
                except:
                    continue
        
        return products
    
    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """Extrait les entités du texte"""
        return {
            'prices': re.findall(r'(\d+)\s*(?:€|euro|euros|mg|ar|mga)', text.lower()),
            'quantities': re.findall(r'\b(\d+)\b', text),
            'product_codes': re.findall(r'\b[A-Z]{2,4}-[A-Z0-9]{2,6}\b', text),
            'phone_numbers': re.findall(r'(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}', text),
            'emails': re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        }

# Instance globale
intent_detector = IntentDetector()