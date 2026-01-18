# app/test_paddleocr_direct.py
import sys
import os
from PIL import Image
import numpy as np

def test_direct():
    print("Testing PaddleOCR directly...")
    
    # Import PaddleOCR
    from paddleocr import PaddleOCR
    
    # Initialiser avec configuration minimale
    try:
        ocr = PaddleOCR(lang='fr')
        print("✅ PaddleOCR initialized")
    except Exception as e:
        print(f"❌ Error initializing PaddleOCR: {e}")
        return
    
    # Charger l'image
    image_path = "C:/Users/WINDOWS 10/Downloads/image_text.jpg"
    try:
        img = np.array(Image.open(image_path))
        print(f"✅ Image loaded: {img.shape}")
    except Exception as e:
        print(f"❌ Error loading image: {e}")
        return
    
    # Faire l'OCR
    try:
        print("Performing OCR...")
        result = ocr.predict(img)
        
        if result and len(result) > 0:
            ocr_result = result[0]
            
            if isinstance(ocr_result, dict) and 'rec_texts' in ocr_result:
                texts = ocr_result['rec_texts']
                scores = ocr_result.get('rec_scores', [])
                
                print(f"\n✅ Found {len(texts)} text elements:")
                print("-" * 50)
                
                for i, (text, score) in enumerate(zip(texts, scores)):
                    conf = score if i < len(scores) else 0.0
                    print(f"{i+1:2d}. [{conf:.3f}] {text}")
                
                # Texte complet
                full_text = "\n".join(texts)
                avg_conf = np.mean(scores) if scores else 0.0
                
                print("\n" + "=" * 50)
                print("FULL TEXT:")
                print("=" * 50)
                print(full_text)
                print("=" * 50)
                print(f"\nAverage confidence: {avg_conf:.3f}")
            else:
                print("❌ Unexpected result format")
                print(f"Result type: {type(ocr_result)}")
                print(f"Keys: {ocr_result.keys() if isinstance(ocr_result, dict) else 'N/A'}")
        else:
            print("❌ No result returned")
            
    except Exception as e:
        print(f"❌ Error during OCR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_direct()