import re
import time
from typing import List, Optional, Dict, Any, Tuple
import logging
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

logger = logging.getLogger(__name__)

class NLPService:
    def __init__(self, config):
        self.config = config
        self.phone_patterns = config.get("NER_PHONE_PATTERNS", [])
        self.email_pattern = config.get("NER_EMAIL_PATTERN")
        self.price_pattern = config.get("NER_PRICE_PATTERN")
        
        # Compile regex patterns
        self.compiled_phone_patterns = [re.compile(pattern) for pattern in self.phone_patterns]
        self.compiled_email_pattern = re.compile(self.email_pattern) if self.email_pattern else None
        self.compiled_price_pattern = re.compile(self.price_pattern) if self.price_pattern else None
        
        # Initialize language detector
        DetectorFactory.seed = 0
        
        # Malagasy specific patterns
        self.malagasy_cities = [
            "antananarivo", "tana", "antsirabe", "toamasina", "mahajanga",
            "fianarantsoa", "toliara", "antsiranana", "moramanga", "ambositra"
        ]
        
        logger.info("NLP Service initialized")
    
    def detect_language(self, text: str) -> str:
        """Detect language of text"""
        try:
            if not text or len(text.strip()) < 10:
                return "unknown"
            
            lang = detect(text)
            return lang
            
        except LangDetectException:
            return "unknown"
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return "unknown"
    
    def extract_phone_numbers(self, text: str) -> List[str]:
        """Extract phone numbers from text"""
        phones = []
        
        for pattern in self.compiled_phone_patterns:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]  # Get first group if tuple
                phones.append(match)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_phones = []
        for phone in phones:
            if phone not in seen:
                seen.add(phone)
                unique_phones.append(phone)
        
        return unique_phones
    
    def extract_emails(self, text: str) -> List[str]:
        """Extract email addresses from text"""
        if not self.compiled_email_pattern:
            return []
        
        emails = self.compiled_email_pattern.findall(text)
        return list(set(emails))  # Remove duplicates
    
    def extract_names(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract first and last names from text"""
        # Simple pattern matching for Malagasy/French names
        name_patterns = [
            r'(?:Je suis|Je m\'appelle|Nom|Prénom|Name)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'([A-Z][a-z]+)\s+([A-Z][a-z]+)',  # First Last pattern
            r'([A-Z][a-z]+),\s*([A-Z][a-z]+)'  # Last, First pattern
        ]
        
        for pattern in name_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                if isinstance(matches[0], tuple):
                    # Two groups found (first and last)
                    return matches[0][0], matches[0][1]
                else:
                    # Single group found
                    names = matches[0].split()
                    if len(names) >= 2:
                        return names[0], " ".join(names[1:])
                    else:
                        return names[0], None
        
        return None, None
    
    def extract_address(self, text: str) -> Dict[str, str]:
        """Extract address information from text"""
        address_info = {}
        
        # Extract Malagasy cities
        text_lower = text.lower()
        for city in self.malagasy_cities:
            if city in text_lower:
                address_info['city'] = city.title()
                break
        
        # Look for address indicators
        address_patterns = {
            'street': r'(?:adresse|adress|address)[:\s]+([^\n,]+)',
            'district': r'(?:quartier|district)[:\s]+([^\n,]+)',
            'postal_code': r'(?:code postal|postal code)[:\s]+(\d{5})'
        }
        
        for key, pattern in address_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                address_info[key] = match.group(1).strip()
        
        return address_info
    
    def extract_order_items(self, text: str) -> List[Dict[str, Any]]:
        """Extract order items from text"""
        items = []
        
        # Patterns for order extraction
        patterns = [
            # Pattern: "2 sacs noirs" or "2x sac noir"
            r'(\d+)(?:x|\s+)?\s*([^,\n.]+?)(?:\s*,\s*|\n|$)',
            # Pattern: "Je prends 2 sacs"
            r'(?:prends|commande|je veux|je voudrais)\s+(\d+)\s+([^,\n.]+)',
            # Pattern: "sacs: 2"
            r'([^:\n]+?)[:\s]+(\d+)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                quantity, product = match
                try:
                    quantity = int(quantity)
                    product = product.strip()
                    
                    # Clean up product name
                    product = re.sub(r'^\s*-\s*', '', product)  # Remove leading dash
                    product = re.sub(r'\s+', ' ', product)  # Normalize spaces
                    
                    items.append({
                        'product': product,
                        'quantity': quantity,
                        'confidence': 0.7
                    })
                except ValueError:
                    continue
        
        return items
    
    def extract_prices(self, text: str) -> List[Dict[str, Any]]:
        """Extract prices from text"""
        if not self.compiled_price_pattern:
            return []
        
        prices = []
        matches = self.compiled_price_pattern.findall(text)
        
        for match in matches:
            # Extract numeric value
            value_match = re.search(r'(\d+[\s,.]?\d*)', match)
            if value_match:
                value_str = value_match.group(1).replace(',', '.').replace(' ', '')
                try:
                    value = float(value_str)
                    prices.append({
                        'value': value,
                        'currency': self._extract_currency(match),
                        'text': match
                    })
                except ValueError:
                    continue
        
        return prices
    
    def _extract_currency(self, text: str) -> str:
        """Extract currency from price text"""
        if 'Ar' in text or 'MGA' in text:
            return 'MGA'
        elif '€' in text or 'EUR' in text:
            return 'EUR'
        elif '$' in text or 'USD' in text:
            return 'USD'
        else:
            return 'unknown'
    
    def detect_intent(self, text: str) -> Tuple[str, float]:
        """Detect user intent from text"""
        text_lower = text.lower()
        
        # Order intent patterns
        order_keywords = [
            'je prends', 'je commande', 'commande', 'je veux', 'je voudrais',
            'livraison', 'livrez', 'expédiez', 'acheter', 'achat',
            'quantité', 'combien', 'prix', 'coût'
        ]
        
        # Contact intent patterns
        contact_keywords = [
            'contact', 'contacter', 'appeler', 'téléphoner', 'appel',
            'email', 'courriel', 'écrire', 'message', 'whatsapp'
        ]
        
        # Information intent patterns
        info_keywords = [
            'information', 'renseignement', 'détails', 'caractéristique',
            'disponible', 'stock', 'catalogue', 'brochure', 'fiche'
        ]
        
        # Calculate scores
        order_score = sum(1 for keyword in order_keywords if keyword in text_lower)
        contact_score = sum(1 for keyword in contact_keywords if keyword in text_lower)
        info_score = sum(1 for keyword in info_keywords if keyword in text_lower)
        
        scores = {
            'ORDER': order_score,
            'CONTACT': contact_score,
            'INFORMATION': info_score
        }
        
        # Get intent with highest score
        max_intent = max(scores, key=scores.get)
        max_score = scores[max_intent]
        
        # Calculate confidence (normalize between 0 and 1)
        total_keywords = len(text_lower.split())
        confidence = min(max_score / max(total_keywords, 1), 1.0)
        
        # If no clear intent, mark as unprocessable
        if confidence < 0.3:
            return 'UNPROCESSABLE', confidence
        
        return max_intent, confidence
    
    def extract_all(self, text: str, language: str = None) -> Dict[str, Any]:
        """Extract all information from text"""
        start_time = time.time()
        
        # Detect language if not provided
        if not language:
            language = self.detect_language(text)
        
        # Detect intent
        intent, intent_confidence = self.detect_intent(text)
        
        # Extract information
        result = {
            'text': text,
            'language': language,
            'intent': intent,
            'intent_confidence': intent_confidence,
            'phone_numbers': self.extract_phone_numbers(text),
            'emails': self.extract_emails(text),
            'first_name': None,
            'last_name': None,
            'address': self.extract_address(text),
            'order_items': self.extract_order_items(text),
            'prices': self.extract_prices(text),
            'processing_time': time.time() - start_time
        }
        
        # Extract names
        first_name, last_name = self.extract_names(text)
        result['first_name'] = first_name
        result['last_name'] = last_name
        
        # Calculate total amount if prices found
        if result['prices']:
            result['total_amount'] = sum(price['value'] for price in result['prices'])
        
        logger.info(f"NLP extraction completed in {result['processing_time']:.2f}s")
        return result