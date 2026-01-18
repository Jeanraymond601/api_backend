# app/test_ocr_complete.py
import requests
import json

def test_all_endpoints():
    """Test complet de tous les endpoints OCR"""
    base_url = "http://localhost:8000/api/v1/ocr"
    pdf_file = r"E:\document\CANEVAS-L3-M2-ENI-2023-2024.pdf"
    image_file = r"C:\Users\WINDOWS 10\Downloads\image_text.jpg"
    
    tests = [
        ("/health", "GET", None, "Vérification santé"),
        ("/image", "POST", image_file, "OCR image"),
        ("/pdf", "POST", pdf_file, "OCR PDF"),
        ("/text", "POST", {"text": "Test de texte pour NLP"}, "Traitement texte"),
    ]
    
    print("="*70)
    print("🧪 TEST COMPLET API OCR/NLP")
    print("="*70)
    
    for endpoint, method, file_or_data, description in tests:
        print(f"\n🔍 {description} ({endpoint})...")
        
        try:
            if method == "GET":
                response = requests.get(f"{base_url}{endpoint}")
            elif method == "POST":
                if isinstance(file_or_data, dict):
                    # Données JSON
                    response = requests.post(
                        f"{base_url}{endpoint}", 
                        json=file_or_data
                    )
                else:
                    # Fichier
                    with open(file_or_data, 'rb') as f:
                        files = {'file': f}
                        response = requests.post(
                            f"{base_url}{endpoint}", 
                            files=files
                        )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print(f"  ✅ Succès!")
                    
                    if 'extraction' in result:
                        ext = result['extraction']
                        print(f"     📝 Texte: {len(ext.get('text', ''))} caractères")
                        print(f"     📊 Confiance: {ext.get('confidence', 0):.3f}")
                        print(f"     🌐 Langue: {ext.get('language', 'N/A')}")
                    
                    if 'metadata' in result:
                        meta = result['metadata']
                        print(f"     📄 Type: {meta.get('document_type', 'N/A')}")
                else:
                    print(f"  ⚠️  Succès=False: {result.get('error', 'Unknown')}")
            else:
                print(f"  ❌ HTTP {response.status_code}: {response.text[:100]}...")
                
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
    
    print("\n" + "="*70)
    print("📊 TEST RÉCAPITULATIF")
    print("="*70)
    
    # Test final avec votre PDF
    print("\n🎯 TEST FINAL - Extraction PDF complète:")
    with open(pdf_file, 'rb') as f:
        response = requests.post(
            f"{base_url}/pdf",
            files={'file': f}
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('extraction', {}).get('text', '')
            confidence = result.get('extraction', {}).get('confidence', 0)
            
            print(f"  ✅ Texte extrait: {len(text)} caractères")
            print(f"  📊 Confiance: {confidence:.3f}")
            print(f"  📄 Pages: {result.get('extraction', {}).get('page_count', 0)}")
            
            # Statistiques
            words = text.split()
            lines = text.split('\n')
            print(f"\n  📈 Statistiques:")
            print(f"     📝 Mots: {len(words)}")
            print(f"     📏 Lignes: {len(lines)}")
            print(f"     🔤 Caractères: {len(text)}")
            
            # Sauvegarder le résultat
            import os
            output_file = os.path.join(
                os.path.dirname(pdf_file),
                "ocr_api_result_complet.txt"
            )
            with open(output_file, 'w', encoding='utf-8') as out:
                out.write(text)
            
            print(f"\n  💾 Résultat sauvegardé dans: {output_file}")
        else:
            print(f"  ❌ Échec: {response.status_code}")

if __name__ == "__main__":
    test_all_endpoints()