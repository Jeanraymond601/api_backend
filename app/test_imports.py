# test_imports.py
from services import (
    ocr_service,
    nlp_service,
    language_detector,
    order_builder,
    form_parser,
    facebook_auth_service,
    facebook_webhook_service,
    facebook_graph_service,
    OCR_SERVICE_AVAILABLE
)

print("=== IMPORT DES SERVICES ===")
print(f"OCR Service: {type(ocr_service).__name__}")
print(f"OCR disponible: {OCR_SERVICE_AVAILABLE}")
print(f"NLP Service: {type(nlp_service).__name__}")
print(f"Language Detector: {type(language_detector).__name__}")
print(f"Facebook Auth: {type(facebook_auth_service).__name__}")
print(f"Facebook Webhook: {type(facebook_webhook_service).__name__}")
print(f"Facebook Graph: {type(facebook_graph_service).__name__}")

# Test rapide OCR si disponible
if OCR_SERVICE_AVAILABLE:
    print("\n=== TEST OCR RAPIDE ===")
    try:
        # Créer une petite image de test
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (200, 100), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 40), "Test OCR Live Commerce", fill='black')
        img.save("test_ocr_small.jpg")
        
        result = ocr_service.process_document("test_ocr_small.jpg")
        print(f"OCR Result: {result.get('success', False)}")
        print(f"Confidence: {result.get('confidence', 0):.2f}")
        print(f"Text: {result.get('text', '')[:50]}...")
        
        import os
        if os.path.exists("test_ocr_small.jpg"):
            os.remove("test_ocr_small.jpg")
    except Exception as e:
        print(f"Erreur test OCR: {e}")