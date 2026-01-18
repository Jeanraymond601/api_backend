from langdetect import detect, detect_langs, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException
from typing import List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class LanguageDetectorService:
    def __init__(self, config):
        self.config = config
        self.supported_languages = config.get("PADDLE_OCR_LANGS", ["fr", "en", "mg"])
        DetectorFactory.seed = 0
        
        # Language code mapping
        self.lang_code_map = {
            'fr': 'français',
            'en': 'english',
            'mg': 'malagasy',
            'es': 'spanish',
            'de': 'german'
        }
        
        # Language-specific characteristics
        self.lang_characteristics = {
            'fr': ['le', 'la', 'les', 'un', 'une', 'des', 'et', 'est'],
            'en': ['the', 'a', 'an', 'is', 'are', 'and', 'of'],
            'mg': ['ny', 'an\'ny', 'ho', 'dia', 'ary', 'fa']
        }
        
        logger.info(f"Language detector initialized for: {self.supported_languages}")
    
    def detect_with_confidence(self, text: str) -> Tuple[str, float]:
        """Detect language with confidence score"""
        try:
            if not text or len(text.strip()) < 5:
                return 'unknown', 0.0
            
            # Get language probabilities
            languages = detect_langs(text)
            
            if not languages:
                return 'unknown', 0.0
            
            # Get the most probable language
            best_lang = str(languages[0])
            lang_code = best_lang.split(':')[0]
            confidence = float(best_lang.split(':')[1])
            
            # Map to supported languages
            if lang_code not in self.supported_languages:
                # Try to find closest supported language
                for supported_lang in self.supported_languages:
                    if self._are_languages_similar(lang_code, supported_lang):
                        lang_code = supported_lang
                        confidence *= 0.8  # Reduce confidence for mapping
                        break
            
            return lang_code, confidence
            
        except LangDetectException:
            return self.detect_with_fallback(text)
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return 'unknown', 0.0
    
    def detect_with_fallback(self, text: str) -> Tuple[str, float]:
        """Fallback language detection using simple heuristics"""
        if not text:
            return 'unknown', 0.0
        
        text_lower = text.lower()
        scores = {}
        
        # Score based on common words
        for lang, words in self.lang_characteristics.items():
            if lang not in self.supported_languages:
                continue
            
            score = 0
            for word in words:
                score += text_lower.count(word)
            
            if score > 0:
                scores[lang] = score
        
        if scores:
            best_lang = max(scores, key=scores.get)
            total_words = len(text_lower.split())
            confidence = min(scores[best_lang] / max(total_words, 1), 1.0)
            return best_lang, confidence
        
        # Check for Malagasy specific patterns
        malagasy_patterns = ['ny', 'an\'ny', 'ho anao', 'misaotra']
        mg_score = sum(1 for pattern in malagasy_patterns if pattern in text_lower)
        if mg_score > 0:
            total_words = len(text_lower.split())
            confidence = min(mg_score / max(total_words, 1), 1.0)
            return 'mg', confidence
        
        return 'unknown', 0.0
    
    def _are_languages_similar(self, lang1: str, lang2: str) -> bool:
        """Check if two languages are similar/dialects"""
        similar_groups = [
            ['fr', 'fr-ca', 'fr-fr'],  # French variants
            ['en', 'en-us', 'en-gb'],  # English variants
            ['pt', 'pt-br', 'pt-pt']   # Portuguese variants
        ]
        
        for group in similar_groups:
            if lang1 in group and lang2 in group:
                return True
        
        return False
    
    def detect_multilingual(self, text: str) -> List[Dict[str, Any]]:
        """Detect multiple languages in text (for mixed language documents)"""
        try:
            if not text or len(text.strip()) < 20:
                return []
            
            # Split text into segments (by paragraphs or sentences)
            segments = self._segment_text(text)
            
            detected_languages = []
            for segment in segments:
                lang, confidence = self.detect_with_confidence(segment)
                if lang != 'unknown' and confidence > 0.5:
                    detected_languages.append({
                        'language': lang,
                        'confidence': confidence,
                        'text_segment': segment[:100] + '...' if len(segment) > 100 else segment,
                        'percentage': len(segment) / len(text)
                    })
            
            # Group and summarize
            if detected_languages:
                return self._summarize_language_distribution(detected_languages)
            
            return []
            
        except Exception as e:
            logger.error(f"Multilingual detection failed: {e}")
            return []
    
    def _segment_text(self, text: str) -> List[str]:
        """Segment text into meaningful parts"""
        # Split by paragraphs
        paragraphs = text.split('\n\n')
        
        # If paragraphs are too long, split by sentences
        segments = []
        for para in paragraphs:
            if len(para) > 200:
                # Simple sentence splitting
                sentences = para.replace('!', '.').replace('?', '.').split('.')
                segments.extend([s.strip() for s in sentences if s.strip()])
            else:
                segments.append(para.strip())
        
        return [s for s in segments if s]
    
    def _summarize_language_distribution(self, detections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize language distribution"""
        summary = {}
        
        for detection in detections:
            lang = detection['language']
            if lang not in summary:
                summary[lang] = {
                    'language': lang,
                    'confidence_sum': 0,
                    'percentage_sum': 0,
                    'count': 0
                }
            
            summary[lang]['confidence_sum'] += detection['confidence']
            summary[lang]['percentage_sum'] += detection['percentage']
            summary[lang]['count'] += 1
        
        # Calculate averages
        result = []
        for lang, data in summary.items():
            result.append({
                'language': lang,
                'full_name': self.lang_code_map.get(lang, lang),
                'average_confidence': data['confidence_sum'] / data['count'],
                'percentage': data['percentage_sum'],
                'segment_count': data['count']
            })
        
        # Sort by percentage
        return sorted(result, key=lambda x: x['percentage'], reverse=True)
    
    def validate_language_support(self, language: str) -> bool:
        """Validate if language is supported"""
        return language in self.supported_languages or language == 'unknown'
    
    def get_language_name(self, code: str) -> str:
        """Get full language name from code"""
        return self.lang_code_map.get(code, code)