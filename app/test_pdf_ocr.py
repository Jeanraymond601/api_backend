# app/test_pdf_ocr.py
import sys
import os
import time

# Configuration pour éviter les logs verbeux
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'

# Ajouter le chemin
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

print("="*70)
print("TEST OCR EXTRACTION PDF")
print("="*70)

# Chemin du fichier PDF à tester
pdf_path = r"E:\document\CANEVAS-L3-M2-ENI-2023-2024.pdf"

# Vérifier si le fichier existe
if not os.path.exists(pdf_path):
    print(f"❌ Fichier PDF introuvable: {pdf_path}")
    print("\n📁 Recherche dans le répertoire...")
    pdf_dir = r"E:\document"
    if os.path.exists(pdf_dir):
        print(f"Fichiers disponibles dans {pdf_dir}:")
        for f in os.listdir(pdf_dir)[:10]:  # Affiche les 10 premiers
            if f.lower().endswith('.pdf'):
                print(f"  - {f}")
    exit(1)

print(f"📄 Fichier PDF: {pdf_path}")
print(f"📏 Taille: {os.path.getsize(pdf_path) / 1024 / 1024:.2f} MB")

try:
    # Importer le service OCR
    from app.services import ocr_service, OCR_SERVICE_AVAILABLE
    
    print("\n" + "="*70)
    print("INITIALISATION OCR")
    print("="*70)
    
    if not OCR_SERVICE_AVAILABLE:
        print("❌ Service OCR non disponible")
        exit(1)
    
    print(f"✅ Service OCR disponible: {type(ocr_service).__name__}")
    print(f"✅ OCR Engine: {ocr_service.ocr_engine.__class__.__name__ if hasattr(ocr_service, 'ocr_engine') else 'N/A'}")
    
    # Vérifier les méthodes disponibles
    if not hasattr(ocr_service, 'process_document'):
        print("❌ Méthode process_document non disponible")
        print("Méthodes disponibles:", [m for m in dir(ocr_service) if not m.startswith('_')])
        exit(1)
    
    print("\n" + "="*70)
    print("EXTRACTION OCR DU PDF")
    print("="*70)
    
    start_time = time.time()
    
    print("⏳ Démarrage de l'extraction OCR...")
    print("⚠️ Cette opération peut prendre plusieurs minutes selon la taille du PDF")
    print("📊 Pages seront converties en images puis traitées par OCR...")
    
    try:
        # Extraire le texte du PDF
        result = ocr_service.process_document(pdf_path)
        
        processing_time = time.time() - start_time
        
        print("\n" + "="*70)
        print("RÉSULTATS DE L'EXTRACTION")
        print("="*70)
        
        print(f"✅ Succès: {result.get('success', False)}")
        print(f"📄 Type de fichier: {result.get('file_type', 'N/A')}")
        print(f"📊 Confiance moyenne: {result.get('confidence', 0):.3f}")
        print(f"⏱️  Temps de traitement: {processing_time:.2f} secondes")
        
        if 'error' in result and result['error']:
            print(f"❌ Erreur: {result['error']}")
        
        # Afficher les pages
        pages = result.get('pages', [])
        print(f"\n📑 Pages extraites: {len(pages)}")
        
        for i, (page_text, page_confidence) in enumerate(pages[:3]):  # Afficher 3 premières pages max
            print(f"\n--- PAGE {i+1} (confiance: {page_confidence:.3f}) ---")
            if page_text:
                # Afficher les premières lignes de chaque page
                lines = page_text.split('\n')
                for j, line in enumerate(lines[:5]):  # 5 premières lignes par page
                    if line.strip():
                        print(f"  {line[:100]}{'...' if len(line) > 100 else ''}")
                if len(lines) > 5:
                    print(f"  ... et {len(lines)-5} lignes supplémentaires")
            else:
                print("  (aucun texte)")
        
        # Texte complet (premier extrait)
        full_text = result.get('text', '')
        if full_text:
            print(f"\n📝 Texte total extrait: {len(full_text)} caractères")
            print("\n" + "="*70)
            print("EXTRAIT DU TEXTE (500 premiers caractères)")
            print("="*70)
            print(full_text[:500] + "..." if len(full_text) > 500 else full_text)
            
            # Sauvegarder le résultat dans un fichier
            output_file = os.path.join(os.path.dirname(pdf_path), f"ocr_result_{os.path.basename(pdf_path)}.txt")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"=== OCR EXTRACTION RESULT ===\n")
                f.write(f"Fichier: {pdf_path}\n")
                f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Confiance: {result.get('confidence', 0):.3f}\n")
                f.write(f"Temps: {processing_time:.2f}s\n")
                f.write(f"Pages: {len(pages)}\n")
                f.write("="*50 + "\n\n")
                
                for i, (page_text, page_confidence) in enumerate(pages):
                    f.write(f"\n{'='*30} PAGE {i+1} {'='*30}\n")
                    f.write(f"Confiance: {page_confidence:.3f}\n")
                    f.write("-"*70 + "\n")
                    f.write(page_text + "\n")
            
            print(f"\n💾 Résultat sauvegardé dans: {output_file}")
        else:
            print("❌ Aucun texte extrait du PDF")
            
        # Statistiques
        print("\n" + "="*70)
        print("STATISTIQUES")
        print("="*70)
        
        if pages:
            avg_page_confidence = sum(p[1] for p in pages) / len(pages)
            avg_page_length = sum(len(p[0]) for p in pages) / len(pages)
            
            print(f"📈 Confiance moyenne par page: {avg_page_confidence:.3f}")
            print(f"📏 Longueur moyenne par page: {avg_page_confidence:.0f} caractères")
            print(f"📄 Pages avec texte: {sum(1 for p in pages if p[0].strip())}/{len(pages)}")
        
    except Exception as e:
        print(f"\n❌ Erreur lors de l'extraction: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    print("\nEssayer d'importer directement depuis le module...")
    
    try:
        # Import direct
        import importlib.util
        spec = importlib.util.spec_from_file_location("ocr_service", 
                                                      os.path.join(current_dir, "services", "ocr_service.py"))
        ocr_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ocr_module)
        
        # Créer une instance
        OCR_CONFIG = {
            "OCR_ENGINE": "paddleocr",
            "preprocess_image": True,
            "MAX_CONCURRENT_OCR": 2,
            "OCR_TIMEOUT": 60
        }
        
        ocr_service = ocr_module.OCRService(OCR_CONFIG)
        print("✅ OCR service importé directement")
        
        # Tester
        print("⏳ Test OCR direct...")
        result = ocr_service.process_document(pdf_path)
        print(f"Résultat: {result.get('success', False)}")
        
    except Exception as e2:
        print(f"❌ Échec import direct: {e2}")

except Exception as e:
    print(f"❌ Erreur générale: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("TEST TERMINÉ")
print("="*70)