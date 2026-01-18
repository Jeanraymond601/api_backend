# app/test_ocr_service.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ocr_service import OCRService

def test_service():
    print("Testing OCR Service...")
    
    config = {
        "OCR_ENGINE": "paddleocr",
        "preprocess_image": True,
        "MAX_CONCURRENT_OCR": 3,
        "OCR_TIMEOUT": 30
    }
    
    try:
        service = OCRService(config)
        print("✅ OCR Service initialized")
        
        result = service.process_document("C:/Users/WINDOWS 10/Downloads/image_text.jpg")
        
        print(f"\nSuccess: {result['success']}")
        print(f"File type: {result['file_type']}")
        print(f"Confidence: {result['confidence']:.3f}")
        print(f"Processing time: {result['processing_time']:.2f}s")
        
        if result['error']:
            print(f"Error: {result['error']}")
        
        print("\n" + "="*60)
        print("EXTRACTED TEXT:")
        print("="*60)
        print(result['text'])
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_service()