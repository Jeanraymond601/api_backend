# app/test_word_direct.py
import sys
import os
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_word_direct():
    """Test direct de l'extraction Word"""
    word_file = r"E:\document\ARCHITECTURE COMPLÈTE.docx"
    
    if not os.path.exists(word_file):
        print(f"❌ Fichier non trouvé: {word_file}")
        return
    
    print(f"🔍 Test direct extraction Word: {os.path.basename(word_file)}")
    print(f"📏 Taille: {os.path.getsize(word_file) / 1024:.1f} KB")
    
    # Test 1: Essayer avec python-docx directement
    print("\n🧪 Test 1: python-docx direct...")
    try:
        from docx import Document
        
        start = time.time()
        doc = Document(word_file)
        
        # Extraire les paragraphes
        paragraphs = []
        for i, para in enumerate(doc.paragraphs[:10]):  # 10 premiers seulement
            if para.text.strip():
                paragraphs.append(para.text)
                print(f"  ¶{i+1}: {para.text[:80]}..." if len(para.text) > 80 else f"  ¶{i+1}: {para.text}")
        
        text = "\n".join(paragraphs)
        elapsed = time.time() - start
        
        print(f"\n✅ python-docx fonctionne!")
        print(f"📝 Paragraphes trouvés: {len(paragraphs)}")
        print(f"📝 Texte total: {len(text)} caractères")
        print(f"⏱️  Temps: {elapsed:.3f}s")
        
        # Afficher plus de texte si nécessaire
        if text:
            print(f"\n📄 Extrait complet (500 caractères):")
            print("-" * 60)
            print(text[:500] + "..." if len(text) > 500 else text)
            print("-" * 60)
            
    except ImportError as e:
        print(f"❌ python-docx non installé: {e}")
        print("💡 Installez avec: pip install python-docx")
        
    except Exception as e:
        print(f"❌ Erreur avec python-docx: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Tester avec votre service OCR
    print("\n🧪 Test 2: Service OCR complet...")
    try:
        from app.services.ocr_service import OCRService
        
        config = {
            "OCR_ENGINE": "paddleocr",
            "preprocess_image": True
        }
        
        service = OCRService(config)
        
        start = time.time()
        result = service.process_document(word_file)
        elapsed = time.time() - start
        
        print(f"✅ Service OCR initialisé")
        print(f"📊 Type détecté: {result.get('file_type')}")
        print(f"📊 Succès: {result.get('success')}")
        print(f"📊 Confiance: {result.get('confidence', 0)}")
        
        text = result.get('text', '')
        if text:
            print(f"📝 Texte extrait: {len(text)} caractères")
            print(f"\n🔍 Extrait (300 caractères):")
            print("-" * 60)
            print(text[:300])
            print("-" * 60)
        else:
            print(f"❌ Texte vide")
            print(f"❌ Erreur: {result.get('error', 'Aucune erreur rapportée')}")
            
        print(f"⏱️  Temps total: {elapsed:.3f}s")
        
    except Exception as e:
        print(f"❌ Erreur service OCR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Fallback avec zipfile
    print("\n🧪 Test 3: Fallback avec zipfile...")
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        
        start = time.time()
        
        with zipfile.ZipFile(word_file, 'r') as docx:
            # Lister les fichiers dans l'archive
            print(f"  📁 Fichiers dans le DOCX:")
            for file_info in docx.infolist()[:5]:  # 5 premiers
                print(f"    - {file_info.filename}")
            
            # Lire le document principal
            xml_content = docx.read('word/document.xml')
            root = ET.fromstring(xml_content)
            
            # Extraire le texte
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text_elements = root.findall('.//w:t', ns)
            
            print(f"\n  🔤 Éléments texte trouvés: {len(text_elements)}")
            
            # Afficher les premiers éléments
            for i, elem in enumerate(text_elements[:5]):
                if elem.text:
                    print(f"    Text[{i}]: {elem.text[:60]}..." if len(elem.text) > 60 else f"    Text[{i}]: {elem.text}")
            
            # Combiner tout le texte
            all_text = [elem.text for elem in text_elements if elem.text]
            combined = ' '.join(all_text)
            
            elapsed = time.time() - start
            
            if combined:
                print(f"\n✅ Fallback réussi!")
                print(f"📝 Texte extrait: {len(combined)} caractères")
                print(f"🔤 Mots: {len(combined.split())}")
                print(f"⏱️  Temps: {elapsed:.3f}s")
            else:
                print(f"❌ Aucun texte extrait avec fallback")
                
    except Exception as e:
        print(f"❌ Erreur fallback: {e}")

if __name__ == "__main__":
    print("="*70)
    print("🔍 TEST DIRECT EXTRACTION WORD")
    print("="*70)
    test_word_direct()
    print("\n" + "="*70)
    print("✅ TEST TERMINÉ")
    print("="*70)