from typing import Dict, Any, List, Optional, Tuple
import logging
import uuid
import re
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
from functools import lru_cache
import phonenumbers
from email_validator import validate_email, EmailNotValidError

logger = logging.getLogger(__name__)

class DeliveryMode(str, Enum):
    HOME_DELIVERY = "home_delivery"
    EXPRESS_DELIVERY = "express_delivery"
    PICKUP = "pickup"
    STORE_DELIVERY = "store_delivery"
    UNKNOWN = "unknown"

class PaymentMode(str, Enum):
    CASH = "cash"
    MOBILE_MONEY = "mobile_money"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    UNKNOWN = "unknown"

class IntentType(str, Enum):
    ORDER = "ORDER"
    INQUIRY = "INQUIRY"
    COMPLAINT = "COMPLAINT"
    UNPROCESSABLE = "UNPROCESSABLE"

@dataclass
class OrderItem:
    product: str
    quantity: int
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    extraction_confidence: float = 0.5
    currency: str = "MGA"
    product_code: Optional[str] = None
    price_match_confidence: Optional[float] = None

@dataclass
class ClientInfo:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_numbers: List[str] = None
    emails: List[str] = None
    address: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.phone_numbers is None:
            self.phone_numbers = []
        if self.emails is None:
            self.emails = []
        if self.address is None:
            self.address = {}

class OrderBuilderService:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.product_database = config.get('product_database', {})
        self.stock_service = config.get('stock_service')
        self.price_matching_threshold = config.get('price_matching_threshold', 60)
        
        # Compilation des regex pour performances
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile les patterns regex pour de meilleures performances"""
        self.delivery_patterns = {
            DeliveryMode.HOME_DELIVERY: [
                re.compile(r'(livraison|livrez|apportez|amenez)\s+(à|au)\s+(domicile|maison|chez moi)', re.IGNORECASE),
                re.compile(r'(domicile|maison|adresse)\s+(de\s+)?livraison', re.IGNORECASE),
                re.compile(r'(envoyez|envoyez-moi|envoie)\s+(à|au)', re.IGNORECASE)
            ],
            DeliveryMode.EXPRESS_DELIVERY: [
                re.compile(r'(express|rapide|urgent|urgence)\s+(livraison|envoi)', re.IGNORECASE),
                re.compile(r'(livraison|envoi)\s+(express|rapide|urgent)', re.IGNORECASE)
            ],
            DeliveryMode.PICKUP: [
                re.compile(r'(retrait|pick.?up|récupérer|venir chercher)', re.IGNORECASE),
                re.compile(r'(sur place|en magasin|au bureau)', re.IGNORECASE),
                re.compile(r'(je passe|je viens)\s+(chercher|prendre)', re.IGNORECASE)
            ],
            DeliveryMode.STORE_DELIVERY: [
                re.compile(r'(point\s+relais|relais colis|dépôt)', re.IGNORECASE),
                re.compile(r'(bureau\s+de\s+poste|poste)', re.IGNORECASE)
            ]
        }
        
        self.payment_patterns = {
            PaymentMode.CASH: [
                re.compile(r'espèces|cash|liquide', re.IGNORECASE)
            ],
            PaymentMode.MOBILE_MONEY: [
                re.compile(r'mobile money|orange money|mvola|airtel money', re.IGNORECASE)
            ],
            PaymentMode.CARD: [
                re.compile(r'carte|card|visa|mastercard', re.IGNORECASE)
            ],
            PaymentMode.BANK_TRANSFER: [
                re.compile(r'virement|transfert|bank', re.IGNORECASE)
            ]
        }
        
        self.promotion_patterns = [
            re.compile(r'(réduction|promo|offre|rabais)\s+de\s+(\d+)(?:%\s+sur|\s+sur)?', re.IGNORECASE),
            re.compile(r'(\d+)%\s+(de\s+)?(réduction|rabais|promo)', re.IGNORECASE),
            re.compile(r'(gratuit|offer[t|ts]|cadeau)\s+(avec|pour)', re.IGNORECASE),
            re.compile(r'(code\s+promo|bon\s+de\s+réduction):?\s*([A-Z0-9]+)', re.IGNORECASE)
        ]
    
    def build_order_structure(self, nlp_result: Dict[str, Any], 
                             form_fields: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Build structured order from NLP extraction"""
        try:
            order_id = self._generate_order_id()
            timestamp = datetime.now().isoformat()
            
            # Build client information with validation
            client = self._build_client_info(nlp_result, form_fields)
            
            # Build order items with price matching
            items = self._build_order_items(nlp_result)
            
            # Check stock availability
            stock_info = self._validate_stock_availability(items)
            
            # Build delivery information with improved detection
            delivery = self._build_delivery_info(nlp_result)
            
            # Build payment information
            payment = self._build_payment_info(nlp_result)
            
            # Extract promotions
            promotions = self._extract_promotions(nlp_result.get('text', ''))
            
            # Calculate total with promotions
            total_amount = self._calculate_total(items, nlp_result, promotions)
            
            # Calculate confidence with improved scoring
            confidence = self._calculate_overall_confidence(nlp_result, form_fields, items)
            
            # Build the complete order structure
            order = {
                'order_id': order_id,
                'timestamp': timestamp,
                'intent': nlp_result.get('intent', IntentType.UNPROCESSABLE),
                'intent_confidence': nlp_result.get('intent_confidence', 0.0),
                'source': 'ocr_nlp_extraction',
                'client': client.__dict__,
                'items': [item.__dict__ for item in items],
                'delivery': delivery,
                'payment': payment,
                'promotions': promotions,
                'stock_info': stock_info,
                'total_amount': total_amount,
                'total_with_discount': self._apply_promotions(total_amount, promotions),
                'metadata': {
                    'language': nlp_result.get('language', 'unknown'),
                    'processing_time': nlp_result.get('processing_time', 0),
                    'extraction_confidence': confidence,
                    'has_form_data': form_fields is not None and len(form_fields) > 0,
                    'stock_available': stock_info['available'],
                    'items_count': len(items),
                    'client_info_completeness': self._calculate_client_completeness(client)
                }
            }
            
            # Add form fields if available
            if form_fields:
                order['form_fields'] = form_fields
            
            logger.info(f"✅ Order structure built: {order_id} (confidence: {confidence:.2f})")
            return order
            
        except Exception as e:
            logger.error(f"❌ Error building order structure: {e}", exc_info=True)
            return self._build_fallback_order(nlp_result, str(e))
    
    def _generate_order_id(self) -> str:
        """Generate a unique order ID with timestamp"""
        timestamp = datetime.now().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4())[:6].upper()
        return f"ORD-{timestamp}-{unique_id}"
    
    def _build_client_info(self, nlp_result: Dict[str, Any], 
                          form_fields: Optional[List[Dict[str, Any]]]) -> ClientInfo:
        """Build validated client information from extracted data"""
        client = ClientInfo(
            first_name=nlp_result.get('first_name'),
            last_name=nlp_result.get('last_name'),
            phone_numbers=self._validate_phones(nlp_result.get('phone_numbers', [])),
            emails=self._validate_emails(nlp_result.get('emails', [])),
            address=nlp_result.get('address', {})
        )
        
        # Enhance with form fields if available
        if form_fields:
            for field in form_fields:
                self._process_form_field(client, field)
        
        # Standardize phone numbers
        client.phone_numbers = self._standardize_phone_numbers(client.phone_numbers)
        
        return client
    
    def _validate_phones(self, phones: List[str]) -> List[str]:
        """Validate and clean phone numbers"""
        valid_phones = []
        for phone in phones:
            try:
                parsed = phonenumbers.parse(phone, "MG")  
                if phonenumbers.is_valid_number(parsed):
                    valid_phones.append(phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.E164
                    ))
            except:
                # Try to extract digits
                digits = re.sub(r'\D', '', phone)
                if len(digits) >= 9:
                    valid_phones.append(f"+261{digits[-9:]}")
        return valid_phones
    
    def _validate_emails(self, emails: List[str]) -> List[str]:
        """Validate email addresses"""
        valid_emails = []
        for email in emails:
            try:
                valid = validate_email(email, check_deliverability=False)
                valid_emails.append(valid.email)
            except EmailNotValidError:
                continue
        return valid_emails
    
    def _process_form_field(self, client: ClientInfo, field: Dict[str, Any]):
        """Process a single form field"""
        field_type = field.get('type', '')
        value = field.get('value', '').strip()
        label = field.get('label', '').lower()
        
        if not value:
            return
        
        if field_type == 'phone':
            validated = self._validate_phones([value])
            if validated and validated[0] not in client.phone_numbers:
                client.phone_numbers.append(validated[0])
        
        elif field_type == 'email':
            validated = self._validate_emails([value])
            if validated and validated[0] not in client.emails:
                client.emails.append(validated[0])
        
        elif 'nom' in label or 'name' in label:
            if not client.last_name:
                client.last_name = value.title()
        
        elif 'prénom' in label or 'first' in label:
            if not client.first_name:
                client.first_name = value.title()
        
        elif 'adresse' in label or 'address' in label:
            if not client.address.get('street'):
                client.address['street'] = value
    
    def _standardize_phone_numbers(self, phones: List[str]) -> List[str]:
        """Standardize phone numbers to E164 format"""
        standardized = []
        for phone in phones:
            if phone.startswith('+261'):
                standardized.append(phone)
            elif phone.startswith('0'):
                standardized.append(f"+261{phone[1:]}")
            elif len(phone) == 9:
                standardized.append(f"+261{phone}")
        return list(set(standardized))
    
    def _build_order_items(self, nlp_result: Dict[str, Any]) -> List[OrderItem]:
        """Build order items with intelligent price matching"""
        items = []
        
        for item_data in nlp_result.get('order_items', []):
            item = OrderItem(
                product=item_data.get('product', '').strip(),
                quantity=max(1, int(item_data.get('quantity', 1))),
                extraction_confidence=item_data.get('confidence', 0.5),
                product_code=self._extract_product_code(item_data.get('product', ''))
            )
            items.append(item)
        
        # Intelligent price matching
        prices = nlp_result.get('prices', [])
        if prices and items:
            self._intelligent_price_matching(items, prices, nlp_result.get('text', ''))
        
        return items
    
    def _intelligent_price_matching(self, items: List[OrderItem], prices: List[Dict[str, Any]], text: str):
        """Intelligent price matching using fuzzy logic and context"""
        from fuzzywuzzy import fuzz
        
        for item in items:
            product_name = item.product.lower()
            best_match = None
            best_score = 0
            
            for price_data in prices:
                price_text = price_data.get('text', '').lower()
                
                # Multiple matching strategies
                strategies = [
                    fuzz.partial_ratio(product_name, price_text),
                    fuzz.token_set_ratio(product_name, price_text),
                    fuzz.token_sort_ratio(product_name, price_text)
                ]
                
                score = max(strategies)
                
                # Bonus for proximity in text
                product_pos = text.lower().find(product_name)
                price_pos = text.lower().find(price_text)
                if product_pos != -1 and price_pos != -1:
                    distance = abs(product_pos - price_pos)
                    if distance < 100:  # Within 100 characters
                        score += (100 - distance) / 100 * 20  # Up to 20 points bonus
                
                if score > best_score and score > self.price_matching_threshold:
                    best_score = score
                    best_match = price_data
            
            if best_match:
                item.unit_price = best_match['value']
                item.total_price = item.unit_price * item.quantity
                item.currency = best_match.get('currency', 'MGA')
                item.price_match_confidence = best_score / 100
                
                # Try to extract product code from price context
                if not item.product_code and best_match.get('text'):
                    item.product_code = self._extract_product_code(best_match['text'])
    
    def _extract_product_code(self, text: str) -> Optional[str]:
        """Extract product code from text"""
        patterns = [
            r'code[:\s]*([A-Z0-9-]+)',
            r'réf[:\s]*([A-Z0-9-]+)',
            r'ref[:\s]*([A-Z0-9-]+)',
            r'article[:\s]*([A-Z0-9-]+)',
            r'([A-Z]{2,3}-\d{2,4})',  # Format: ABC-123
            r'([A-Z]{2,3}\d{2,4})',   # Format: ABC123
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _validate_stock_availability(self, items: List[OrderItem]) -> Dict[str, Any]:
        """Check stock availability for items"""
        if not self.stock_service:
            return {'available': True, 'issues': []}
        
        issues = []
        for item in items:
            product_code = item.product_code or self._find_product_code_by_name(item.product)
            
            if product_code and self.product_database:
                available = self.stock_service.check_availability(
                    product_code=product_code,
                    quantity=item.quantity
                )
                
                if not available.get('in_stock', True):
                    issues.append({
                        'product': item.product,
                        'product_code': product_code,
                        'requested': item.quantity,
                        'available': available.get('quantity', 0),
                        'suggestion': available.get('alternative')
                    })
        
        return {
            'available': len(issues) == 0,
            'issues': issues,
            'can_partially_fulfill': len(issues) < len(items)
        }
    
    @lru_cache(maxsize=100)
    def _find_product_code_by_name(self, product_name: str) -> Optional[str]:
        """Find product code by name using fuzzy matching"""
        if not self.product_database:
            return None
        
        from fuzzywuzzy import process
        
        matches = process.extractOne(
            product_name.lower(),
            [p.lower() for p in self.product_database.keys()]
        )
        
        if matches and matches[1] > 70:  # 70% confidence threshold
            matched_name = matches[0]
            return self.product_database[matched_name].get('code')
        
        return None
    
    def _build_delivery_info(self, nlp_result: Dict[str, Any]) -> Dict[str, Any]:
        """Build delivery information with improved detection"""
        text = nlp_result.get('text', '').lower()
        
        detected_modes = []
        for mode, patterns in self.delivery_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    detected_modes.append(mode)
                    break
        
        # Priority order
        priority = [
            DeliveryMode.EXPRESS_DELIVERY,
            DeliveryMode.HOME_DELIVERY,
            DeliveryMode.STORE_DELIVERY,
            DeliveryMode.PICKUP
        ]
        
        selected_mode = DeliveryMode.UNKNOWN
        for mode in priority:
            if mode in detected_modes:
                selected_mode = mode
                break
        
        return {
            'mode': selected_mode.value,
            'detected_modes': [m.value for m in detected_modes],
            'address': nlp_result.get('address', {}),
            'notes': self._extract_delivery_notes(text),
            'urgency': 'high' if 'urgent' in text or 'rapide' in text else 'normal'
        }
    
    def _extract_delivery_notes(self, text: str) -> str:
        """Extract delivery-specific notes from text"""
        notes_patterns = [
            r'(avant|avant\s+)\s*(\d{1,2})h',
            r'(après|après\s+)\s*(\d{1,2})h',
            r'(matin|soir|midi)',
            r'(demain|aujourd\'hui|ce soir)'
        ]
        
        notes = []
        for pattern in notes_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    notes.append(' '.join(match))
                else:
                    notes.append(match)
        
        return '; '.join(notes) if notes else ''
    
    def _build_payment_info(self, nlp_result: Dict[str, Any]) -> Dict[str, Any]:
        """Build payment information with improved detection"""
        text = nlp_result.get('text', '').lower()
        
        detected_modes = []
        for mode, patterns in self.payment_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    detected_modes.append(mode)
        
        selected_mode = PaymentMode.UNKNOWN
        if detected_modes:
            # Prioritize mobile money for Madagascar
            if PaymentMode.MOBILE_MONEY in detected_modes:
                selected_mode = PaymentMode.MOBILE_MONEY
            else:
                selected_mode = detected_modes[0]
        
        return {
            'mode': selected_mode.value,
            'detected_modes': [m.value for m in detected_modes],
            'amount': nlp_result.get('total_amount'),
            'currency': 'MGA',
            'prepaid': 'avance' in text or 'acompte' in text
        }
    
    def _extract_promotions(self, text: str) -> List[Dict[str, Any]]:
        """Extract promotion information from text"""
        promotions = []
        
        for pattern in self.promotion_patterns:
            matches = pattern.findall(text)
            for match in matches:
                promotion = self._parse_promotion_match(match, pattern.pattern)
                if promotion:
                    promotions.append(promotion)
        
        return promotions
    
    def _parse_promotion_match(self, match: Any, pattern: str) -> Optional[Dict[str, Any]]:
        """Parse a promotion regex match"""
        if isinstance(match, tuple):
            match = list(match)
        
        if 'code' in pattern.lower():
            code = match[1] if len(match) > 1 else match[0]
            return {
                'type': 'promo_code',
                'value': code,
                'code': code,
                'description': f"Code promo: {code}"
            }
        
        elif '%' in str(match[0]) or '%' in pattern:
            percentage = None
            for item in match:
                if isinstance(item, str):
                    num_match = re.search(r'\d+', item)
                    if num_match:
                        percentage = int(num_match.group())
                        break
            
            if percentage:
                return {
                    'type': 'percentage_discount',
                    'value': percentage,
                    'description': f"{percentage}% de réduction"
                }
        
        return None
    
    def _calculate_total(self, items: List[OrderItem], nlp_result: Dict[str, Any], 
                        promotions: List[Dict[str, Any]]) -> Optional[float]:
        """Calculate total order amount with promotions"""
        # Try to get total from prices first
        if nlp_result.get('total_amount'):
            total = nlp_result['total_amount']
        else:
            # Calculate from items
            total = 0
            has_prices = False
            
            for item in items:
                if item.total_price:
                    total += item.total_price
                    has_prices = True
            
            if not has_prices:
                return None
        
        return total
    
    def _apply_promotions(self, total: Optional[float], promotions: List[Dict[str, Any]]) -> Optional[float]:
        """Apply promotions to total amount"""
        if total is None:
            return None
        
        discounted = total
        for promo in promotions:
            if promo['type'] == 'percentage_discount':
                discounted -= total * (promo['value'] / 100)
            elif promo['type'] == 'fixed_discount':
                discounted -= promo['value']
        
        return max(discounted, 0)
    
    def _calculate_overall_confidence(self, nlp_result: Dict[str, Any], 
                                    form_fields: Optional[List[Dict[str, Any]]],
                                    items: List[OrderItem]) -> float:
        """Calculate overall extraction confidence with improved scoring"""
        weights = {
            'intent': 0.15,
            'client_info': 0.25,
            'order_items': 0.30,
            'price_matching': 0.20,
            'form_fields': 0.10
        }
        
        scores = []
        
        # Intent confidence
        scores.append(nlp_result.get('intent_confidence', 0.0) * weights['intent'])
        
        # Client information score (more granular)
        client_score = self._calculate_client_score(nlp_result)
        scores.append(client_score * weights['client_info'])
        
        # Order items score
        items_score = self._calculate_items_score(items)
        scores.append(items_score * weights['order_items'])
        
        # Price matching score
        price_score = self._calculate_price_matching_score(items)
        scores.append(price_score * weights['price_matching'])
        
        # Form fields score
        form_score = self._calculate_form_score(form_fields)
        scores.append(form_score * weights['form_fields'])
        
        total_score = sum(scores)
        
        # Apply quality multipliers
        multipliers = self._calculate_quality_multipliers(nlp_result, items)
        final_score = total_score * multipliers
        
        return min(final_score, 1.0)
    
    def _calculate_client_score(self, nlp_result: Dict[str, Any]) -> float:
        """Calculate client information completeness score"""
        score = 0
        
        # Phone is most important
        if nlp_result.get('phone_numbers'):
            score += 0.4
        
        # Name
        if nlp_result.get('first_name') and nlp_result.get('last_name'):
            score += 0.3
        elif nlp_result.get('first_name') or nlp_result.get('last_name'):
            score += 0.15
        
        # Address
        address = nlp_result.get('address', {})
        if address.get('street'):
            score += 0.2
        if address.get('city'):
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_items_score(self, items: List[OrderItem]) -> float:
        """Calculate order items quality score"""
        if not items:
            return 0.0
        
        # Base score based on number of items
        count_score = min(len(items) / 5, 1.0) * 0.3
        
        # Confidence score
        confidences = [item.extraction_confidence for item in items]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        confidence_score = avg_confidence * 0.4
        
        # Price completeness score
        priced_items = [item for item in items if item.unit_price is not None]
        price_score = (len(priced_items) / len(items)) * 0.3 if items else 0
        
        return count_score + confidence_score + price_score
    
    def _calculate_price_matching_score(self, items: List[OrderItem]) -> float:
        """Calculate price matching quality score"""
        if not items:
            return 0.0
        
        priced_items = [item for item in items if item.unit_price is not None]
        if not priced_items:
            return 0.0
        
        # Average price match confidence
        confidences = [item.price_match_confidence for item in priced_items if item.price_match_confidence]
        if not confidences:
            return 0.5  # Default score if no confidence data
        
        avg_confidence = sum(confidences) / len(confidences)
        
        # Adjust based on percentage of items with prices
        coverage = len(priced_items) / len(items)
        
        return avg_confidence * coverage
    
    def _calculate_form_score(self, form_fields: Optional[List[Dict[str, Any]]]) -> float:
        """Calculate form fields quality score"""
        if not form_fields:
            return 0.1  # Small base score
        
        # Score based on number and type of fields
        score = min(len(form_fields) / 10, 1.0) * 0.6
        
        # Bonus for critical fields
        critical_fields = ['phone', 'email', 'name']
        for field in form_fields:
            if field.get('type') in critical_fields and field.get('value'):
                score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_quality_multipliers(self, nlp_result: Dict[str, Any], items: List[OrderItem]) -> float:
        """Calculate quality multipliers for confidence score"""
        multiplier = 1.0
        
        # Penalty for low intent confidence
        intent_conf = nlp_result.get('intent_confidence', 0.0)
        if intent_conf < 0.5:
            multiplier *= 0.8
        
        # Bonus for complete addresses
        address = nlp_result.get('address', {})
        if address.get('street') and address.get('city'):
            multiplier *= 1.1
        
        # Penalty for items without prices
        priced_items = [item for item in items if item.unit_price is not None]
        if items and len(priced_items) == 0:
            multiplier *= 0.7
        
        return multiplier
    
    def _calculate_client_completeness(self, client: ClientInfo) -> float:
        """Calculate client information completeness percentage"""
        criteria = [
            1 if client.first_name else 0,
            1 if client.last_name else 0,
            1 if client.phone_numbers else 0,
            1 if client.emails else 0,
            1 if client.address.get('street') else 0,
        ]
        
        return sum(criteria) / len(criteria)
    
    def prepare_for_order_service(self, order_structure: Dict[str, Any],
                                service_type: str = 'default') -> Dict[str, Any]:
        """Prepare order structure for external order service with configurable mappings"""
        
        # Service-specific mappings
        service_mappings = {
            'shopify': self._map_to_shopify_format,
            'woocommerce': self._map_to_woocommerce_format,
            'magento': self._map_to_magento_format,
            'default': self._map_to_default_format
        }
        
        mapper = service_mappings.get(service_type, self._map_to_default_format)
        return mapper(order_structure)
    
    def _map_to_default_format(self, order_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Default mapping format"""
        client = order_structure['client']
        
        return {
            'external_reference': order_structure['order_id'],
            'customer': {
                'first_name': client.get('first_name'),
                'last_name': client.get('last_name'),
                'phone': client.get('phone_numbers', [''])[0] if client.get('phone_numbers') else None,
                'email': client.get('emails', [''])[0] if client.get('emails') else None,
                'address': client.get('address', {})
            },
            'order_details': [
                {
                    'product_name': item['product'],
                    'product_code': item.get('product_code'),
                    'quantity': item['quantity'],
                    'unit_price': item.get('unit_price'),
                    'total_price': item.get('total_price'),
                    'currency': item.get('currency', 'MGA')
                }
                for item in order_structure['items']
            ],
            'delivery_method': order_structure['delivery'].get('mode'),
            'payment_method': order_structure['payment'].get('mode'),
            'total_amount': order_structure['total_amount'],
            'total_with_discount': order_structure.get('total_with_discount'),
            'promotions': order_structure.get('promotions', []),
            'stock_info': order_structure.get('stock_info'),
            'metadata': order_structure['metadata'],
            'source': 'ocr_automated_extraction'
        }
    
    def _map_to_shopify_format(self, order_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Map to Shopify API format"""
        client = order_structure['client']
        address = client.get('address', {})
        
        return {
            'order': {
                'email': client.get('emails', [''])[0] if client.get('emails') else None,
                'phone': client.get('phone_numbers', [''])[0] if client.get('phone_numbers') else None,
                'first_name': client.get('first_name'),
                'last_name': client.get('last_name'),
                'billing_address': {
                    'address1': address.get('street'),
                    'city': address.get('city'),
                    'zip': address.get('postal_code'),
                    'country': address.get('country', 'Madagascar')
                },
                'shipping_address': {
                    'address1': address.get('street'),
                    'city': address.get('city'),
                    'zip': address.get('postal_code'),
                    'country': address.get('country', 'Madagascar')
                },
                'line_items': [
                    {
                        'title': item['product'],
                        'sku': item.get('product_code'),
                        'quantity': item['quantity'],
                        'price': item.get('unit_price')
                    }
                    for item in order_structure['items']
                ],
                'total_price': order_structure['total_amount'],
                'currency': 'MGA',
                'source_name': 'facebook_ocr'
            }
        }
    
    def _map_to_woocommerce_format(self, order_structure: Dict[str, Any]) -> Dict[str, Any]:
        """Map to WooCommerce API format"""
        client = order_structure['client']
        
        return {
            'payment_method': order_structure['payment'].get('mode'),
            'payment_method_title': self._get_payment_method_title(order_structure['payment'].get('mode')),
            'billing': {
                'first_name': client.get('first_name'),
                'last_name': client.get('last_name'),
                'phone': client.get('phone_numbers', [''])[0] if client.get('phone_numbers') else None,
                'email': client.get('emails', [''])[0] if client.get('emails') else None,
                'address_1': client.get('address', {}).get('street'),
                'city': client.get('address', {}).get('city'),
                'postcode': client.get('address', {}).get('postal_code'),
                'country': 'MG'
            },
            'line_items': [
                {
                    'product_id': self._get_product_id(item.get('product_code')),
                    'name': item['product'],
                    'quantity': item['quantity'],
                    'price': item.get('unit_price')
                }
                for item in order_structure['items']
            ],
            'shipping_lines': [
                {
                    'method_id': 'flat_rate',
                    'method_title': self._get_shipping_method_title(order_structure['delivery'].get('mode')),
                    'total': '0'
                }
            ]
        }
    
    def _get_payment_method_title(self, method: str) -> str:
        """Get payment method display title"""
        titles = {
            'cash': 'Espèces',
            'mobile_money': 'Mobile Money',
            'card': 'Carte Bancaire',
            'bank_transfer': 'Virement Bancaire',
            'unknown': 'Non spécifié'
        }
        return titles.get(method, method)
    
    def _get_shipping_method_title(self, method: str) -> str:
        """Get shipping method display title"""
        titles = {
            'home_delivery': 'Livraison à domicile',
            'express_delivery': 'Livraison express',
            'pickup': 'Retrait en magasin',
            'store_delivery': 'Point relais',
            'unknown': 'Non spécifié'
        }
        return titles.get(method, method)
    
    def _get_product_id(self, product_code: Optional[str]) -> int:
        """Get product ID from product code"""
        if not product_code or not self.product_database:
            return 0
        
        for product_data in self.product_database.values():
            if product_data.get('code') == product_code:
                return product_data.get('woocommerce_id', 0)
        
        return 0
    
    def _build_fallback_order(self, nlp_result: Dict[str, Any], error: str) -> Dict[str, Any]:
        """Build a fallback order structure when main processing fails"""
        return {
            'order_id': f"ERR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'timestamp': datetime.now().isoformat(),
            'intent': 'ERROR',
            'intent_confidence': 0.0,
            'source': 'ocr_nlp_extraction',
            'client': {},
            'items': [],
            'delivery': {'mode': 'unknown'},
            'payment': {'mode': 'unknown'},
            'total_amount': None,
            'metadata': {
                'language': 'unknown',
                'processing_time': 0,
                'extraction_confidence': 0.0,
                'has_form_data': False,
                'error': error,
                'error_timestamp': datetime.now().isoformat()
            }
        }