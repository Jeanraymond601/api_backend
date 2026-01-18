import cv2
import numpy as np
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class FormParserService:
    def __init__(self, config):
        self.config = config
        self.form_templates = self._load_form_templates()
        
    def _load_form_templates(self) -> Dict[str, Any]:
        """Load predefined form templates"""
        # Common form field labels in multiple languages
        return {
            'customer_form': {
                'labels': {
                    'fr': ['nom', 'prénom', 'téléphone', 'email', 'adresse', 'ville'],
                    'en': ['name', 'first name', 'phone', 'email', 'address', 'city'],
                    'mg': ['anarana', 'fanampiny', 'finday', 'mailaka', 'adiresy', 'tanàna']
                },
                'field_types': {
                    'nom': 'text', 'name': 'text', 'anarana': 'text',
                    'téléphone': 'phone', 'phone': 'phone', 'finday': 'phone',
                    'email': 'email', 'mailaka': 'email',
                    'adresse': 'address', 'address': 'address', 'adiresy': 'address'
                }
            },
            'order_form': {
                'labels': {
                    'fr': ['produit', 'quantité', 'prix', 'total', 'livraison', 'paiement'],
                    'en': ['product', 'quantity', 'price', 'total', 'delivery', 'payment'],
                    'mg': ['vokatra', 'isany', 'vidiny', 'totaly', 'fanaterana', 'fandoavam-bola']
                }
            }
        }
    
    def detect_form_type(self, text: str, language: str) -> str:
        """Detect type of form based on content"""
        text_lower = text.lower()
        
        # Check for form indicators
        form_indicators = {
            'customer_form': ['formulaire', 'fiche', 'client', 'information'],
            'order_form': ['commande', 'bon', 'order', 'purchase']
        }
        
        for form_type, indicators in form_indicators.items():
            if any(indicator in text_lower for indicator in indicators):
                return form_type
        
        # Check for field labels
        for form_type, template in self.form_templates.items():
            labels = template['labels'].get(language, [])
            if any(label in text_lower for label in labels):
                return form_type
        
        return 'unknown'
    
    def parse_form_fields(self, text: str, language: str = 'fr') -> List[Dict[str, Any]]:
        """Parse form fields from OCR text"""
        fields = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check if line contains a label-value separator
            separators = [':', '=', '-', '>']
            for sep in separators:
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2:
                        label = parts[0].strip().lower()
                        value = parts[1].strip()
                        
                        # Identify field type
                        field_type = self._identify_field_type(label, language)
                        
                        fields.append({
                            'label': label,
                            'value': value,
                            'type': field_type,
                            'confidence': 0.8,
                            'line_number': i
                        })
                        break
            
            # Check for label in next line pattern
            if i < len(lines) - 1:
                current_line = line.lower()
                next_line = lines[i + 1].strip()
                
                # Check if current line looks like a label and next line looks like a value
                if (self._looks_like_label(current_line, language) and 
                    next_line and not self._looks_like_label(next_line.lower(), language)):
                    
                    field_type = self._identify_field_type(current_line, language)
                    
                    fields.append({
                        'label': current_line,
                        'value': next_line,
                        'type': field_type,
                        'confidence': 0.7,
                        'line_number': i
                    })
        
        return fields
    
    def _looks_like_label(self, text: str, language: str) -> bool:
        """Check if text looks like a form field label"""
        # Check against known labels
        for template in self.form_templates.values():
            labels = template['labels'].get(language, [])
            if any(label in text for label in labels):
                return True
        
        # Check for label patterns (short, ends with colon-like, common words)
        if len(text) < 30:  # Labels are usually short
            label_indicators = ['nom', 'name', 'phone', 'tel', 'email', 'adresse', 'address']
            if any(indicator in text for indicator in label_indicators):
                return True
        
        return False
    
    def _identify_field_type(self, label: str, language: str) -> str:
        """Identify field type based on label"""
        label_lower = label.lower()
        
        # Check templates for field type mapping
        for template in self.form_templates.values():
            if 'field_types' in template:
                field_types = template['field_types']
                if label_lower in field_types:
                    return field_types[label_lower]
        
        # Default mapping based on common patterns
        type_mapping = {
            'fr': {
                'nom': 'text', 'prénom': 'text', 'téléphone': 'phone', 'tel': 'phone',
                'email': 'email', 'mail': 'email', 'adresse': 'address',
                'ville': 'text', 'code postal': 'text', 'produit': 'text',
                'quantité': 'number', 'prix': 'price', 'total': 'price'
            },
            'en': {
                'name': 'text', 'first name': 'text', 'phone': 'phone',
                'email': 'email', 'address': 'address', 'city': 'text',
                'product': 'text', 'quantity': 'number', 'price': 'price',
                'total': 'price'
            },
            'mg': {
                'anarana': 'text', 'fanampiny': 'text', 'finday': 'phone',
                'mailaka': 'email', 'adiresy': 'address', 'tanàna': 'text',
                'vokatra': 'text', 'isany': 'number', 'vidiny': 'price'
            }
        }
        
        # Check for exact matches first
        if language in type_mapping:
            for key, value in type_mapping[language].items():
                if key in label_lower:
                    return value
        
        # Check for partial matches
        if language in type_mapping:
            for key, value in type_mapping[language].items():
                if any(word in label_lower for word in key.split()):
                    return value
        
        return 'text'  # Default type
    
    def detect_handwriting(self, image_path: str) -> bool:
        """Detect if form contains handwriting"""
        try:
            # Load image
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                return False
            
            # Calculate variance of Laplacian (focus measure)
            laplacian = cv2.Laplacian(img, cv2.CV_64F)
            variance = laplacian.var()
            
            # Handwritten text typically has higher variance
            return variance > 100  # Threshold may need adjustment
            
        except Exception as e:
            logger.error(f"Handwriting detection failed: {e}")
            return False
    
    def calculate_form_completeness(self, fields: List[Dict[str, Any]], form_type: str) -> float:
        """Calculate completeness score for form"""
        if form_type not in self.form_templates:
            return 0.0
        
        template = self.form_templates[form_type]
        required_fields = list(template.get('field_types', {}).keys())
        
        if not required_fields:
            return 0.0
        
        # Count how many required fields are present
        present_fields = 0
        for field in fields:
            if field['label'] in required_fields:
                present_fields += 1
        
        return present_fields / len(required_fields)