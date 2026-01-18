# test_ocr_fixed.py
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np

print("=== PaddleOCR 3.3.2 - Extraction correcte ===")

# Initialisation
ocr = PaddleOCR(lang='fr')

# Charger image
img = np.array(Image.open("C:/Users/WINDOWS 10/Downloads/image_text.jpg"))

# Faire l'OCR
result = ocr.predict(img)

# IMPORTANT: result est une liste contenant un OCRResult
if result and len(result) > 0:
    ocr_result = result[0]  # C'est un OCRResult (dictionnaire)
    
    # Extraire les textes et scores
    if 'rec_texts' in ocr_result and 'rec_scores' in ocr_result:
        texts = ocr_result['rec_texts']
        scores = ocr_result['rec_scores']
        
        print(f"✅ {len(texts)} textes détectés:")
        print("-" * 50)
        
        for i, (text, score) in enumerate(zip(texts, scores)):
            print(f"{i+1:2d}. [{score:.3f}] {text}")
        
        # Combiner le texte complet
        full_text = "\n".join(texts)
        
        print("\n" + "=" * 50)
        print("📋 TEXTE COMPLET:")
        print("=" * 50)
        print(full_text)
        print("=" * 50)
        
        # Calculer la confiance moyenne
        avg_confidence = np.mean(scores) if scores else 0.0
        print(f"\n📊 Statistiques:")
        print(f"• Textes détectés: {len(texts)}")
        print(f"• Confiance moyenne: {avg_confidence:.3f}")
        print(f"• Confiance min: {min(scores):.3f}")
        print(f"• Confiance max: {max(scores):.3f}")
        
        # Sauvegarder
        with open("resultat_ocr_final.txt", "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"\n💾 Résultat sauvegardé dans 'resultat_ocr_final.txt'")
    else:
        print("❌ Clés 'rec_texts' ou 'rec_scores' non trouvées")
        print("Clés disponibles:", list(ocr_result.keys()))
else:
    print("❌ Aucun résultat")