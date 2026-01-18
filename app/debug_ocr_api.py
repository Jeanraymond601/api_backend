# app/debug_ocr_api.py
import sys
import os
import tempfile
import shutil

# Ajouter le chemin
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def debug_ocr_service():
    print("="*70)
    print("🔍 DEBUG OCR SERVICE - Simulation API")
    print("="*70)
    
    # Fichier PDF source
    pdf_source = r"E:\document\CANEVAS-L3-M2-ENI-2023-2024.pdf"
    
    # Simuler ce que fait l'API : copier dans un fichier temp
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        # Copier le fichier comme le ferait l'API
        shutil.copyfile(pdf_source, tmp.name)
        temp_path = tmp.name
    
    print(f"📄 PDF original: {pdf_source}")
    print(f"📄 Copié vers temp: {temp_path}")
    print(f"📏 Taille: {os.path.getsize(temp_path)} bytes")
    print(f"✅ Fichier existe: {os.path.exists(temp_path)}")
    
    try:
        # Importer et tester le service OCR
        from app.services import ocr_service, OCR_SERVICE_AVAILABLE
        
        print(f"\n🔧 Service OCR disponible: {OCR_SERVICE_AVAILABLE}")
        print(f"🔧 Type service: {type(ocr_service).__name__}")
        
        if OCR_SERVICE_AVAILABLE:
            print("\n🧪 Test 1: process_document (méthode API)...")
            result1 = ocr_service.process_document(temp_path)
            
            print(f"  ✅ Succès: {result1.get('success')}")
            print(f"  📊 Type fichier: {result1.get('file_type')}")
            print(f"  📊 Confiance: {result1.get('confidence', 0)}")
            print(f"  📝 Texte: {len(result1.get('text', ''))} caractères")
            
            if result1.get('error'):
                print(f"  ❌ Erreur: {result1.get('error')}")
            
            print("\n🧪 Test 2: extract_from_pdf (ancienne méthode)...")
            try:
                result2 = ocr_service.extract_from_pdf(temp_path)
                print(f"  📊 Pages: {len(result2) if result2 else 0}")
                if result2:
                    total_text = "\n".join([p[0] for p in result2])
                    print(f"  📝 Texte total: {len(total_text)} caractères")
            except Exception as e:
                print(f"  ❌ Erreur extract_from_pdf: {e}")
            
            print("\n🧪 Test 3: Preprocess + OCR manuel...")
            try:
                # Essayer manuellement comme dans votre script de test
                import fitz
                from PIL import Image
                import io
                import cv2
                import numpy as np
                
                doc = fitz.open(temp_path)
                print(f"  📑 Pages PyMuPDF: {len(doc)}")
                
                if len(doc) > 0:
                    page = doc[0]
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                    img = Image.open(io.BytesIO(pix.tobytes("ppm")))
                    
                    # Sauvegarder temporairement
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as img_tmp:
                        img.save(img_tmp.name, 'JPEG')
                        img_path = img_tmp.name
                    
                    # Tester extract_from_image
                    text, confidence, time = ocr_service.extract_from_image(img_path)
                    print(f"  📝 Texte image: {len(text)} caractères")
                    print(f"  📊 Confiance image: {confidence}")
                    
                    os.unlink(img_path)
                doc.close()
                
            except Exception as e:
                print(f"  ❌ Test manuel échoué: {e}")
        
        else:
            print("❌ Service OCR non disponible!")
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Nettoyer
        if os.path.exists(temp_path):
            os.unlink(temp_path)
            print(f"\n🗑️  Fichier temporaire nettoyé")
    
    print("\n" + "="*70)
    print("🔍 DEBUG TERMINÉ")
    print("="*70)

if __name__ == "__main__":
    debug_ocr_service()