# app/test_pdf_final.py
import sys
import os
import tempfile
import io
import time
from PIL import Image
from datetime import datetime

os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pdf_path = r"E:\document\CANEVAS-L3-M2-ENI-2023-2024.pdf"

if not os.path.exists(pdf_path):
    print(f"❌ Fichier non trouvé: {pdf_path}")
    exit(1)

print(f"📄 Test OCR sur: {os.path.basename(pdf_path)}")

try:
    from app.services import ocr_service
    import fitz
    
    print("⏳ Ouverture PDF...")
    doc = fitz.open(pdf_path)
    print(f"📑 Pages: {len(doc)}")
    
    if len(doc) == 0:
        print("❌ PDF vide")
        doc.close()
        exit(1)
    
    # Traiter seulement 3 premières pages pour le test
    pages_to_process = min(3, len(doc))
    print(f"🔍 Traitement des {pages_to_process} premières pages...")
    
    all_text = []
    all_confidences = []
    
    for page_num in range(pages_to_process):
        print(f"  Page {page_num+1}/{pages_to_process}...")
        start_time = time.time()
        
        page = doc[page_num]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("ppm")))
        
        # Sauvegarder temporairement
        with tempfile.NamedTemporaryFile(suffix=f'_page{page_num}.jpg', delete=False) as tmp:
            tmp_path = tmp.name
        
        img.save(tmp_path, 'JPEG', quality=90)
        
        # OCR
        result = ocr_service.process_document(tmp_path)
        
        # Nettoyer
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        process_time = time.time() - start_time
        
        if result.get('success'):
            text = result.get('text', '')
            confidence = result.get('confidence', 0)
            
            all_text.append(text)
            all_confidences.append(confidence)
            
            print(f"    ✅ Confiance: {confidence:.3f}, Temps: {process_time:.2f}s")
            
            if text:
                lines = text.split('\n')
                first_line = next((l.strip() for l in lines if l.strip()), '')
                if first_line:
                    print(f"    📝 {first_line[:60]}...")
        else:
            print(f"    ❌ Échec: {result.get('error', 'Unknown')}")
            all_text.append('')
            all_confidences.append(0)
    
    doc.close()
    
    # Résumé
    print(f"\n" + "="*60)
    print("📊 RÉSUMÉ DU TEST")
    print("="*60)
    
    total_chars = sum(len(t) for t in all_text)
    total_words = sum(len(t.split()) for t in all_text)
    avg_confidence = sum(all_confidences)/len(all_confidences) if all_confidences else 0
    
    print(f"📄 Pages traitées: {pages_to_process}")
    print(f"📊 Confiance moyenne: {avg_confidence:.3f}")
    print(f"📝 Total extrait: {total_words} mots, {total_chars} caractères")
    
    # Sauvegarder
    output_dir = os.path.dirname(pdf_path)
    base_name = os.path.basename(pdf_path)[:-4]
    output_file = os.path.join(output_dir, f"ocr_test_{base_name}.txt")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== TEST OCR - {pages_to_process} PAGES ===\n")
        f.write(f"Fichier: {os.path.basename(pdf_path)}\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Confiance moyenne: {avg_confidence:.3f}\n")
        f.write("="*60 + "\n\n")
        
        for i, text in enumerate(all_text):
            if text.strip():
                f.write(f"\n{'='*30} PAGE {i+1} {'='*30}\n")
                f.write(f"Confiance: {all_confidences[i]:.3f}\n")
                f.write("-"*60 + "\n")
                f.write(text + "\n")
    
    print(f"💾 Résultat sauvegardé dans: {output_file}")
    
except Exception as e:
    print(f"❌ Erreur: {e}")
    import traceback
    traceback.print_exc()

print("\n✅ Test terminé!")