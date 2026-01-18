# app/test_api_word.py
import requests
import json
import os
import time

def test_word_extraction():
    """Test l'API OCR avec un document Word"""
    
    # Configuration
    api_url = "http://localhost:8000/api/v1/ocr/docx"
    word_file = r"E:\document\ARCHITECTURE COMPLÈTE.docx"
    
    # Vérifier si le fichier existe
    if not os.path.exists(word_file):
        print(f"❌ Fichier Word introuvable: {word_file}")
        print(f"\n📁 Recherche de fichiers Word dans E:\\document\\")
        doc_dir = r"E:\document"
        if os.path.exists(doc_dir):
            word_files = [f for f in os.listdir(doc_dir) if f.lower().endswith(('.docx', '.doc'))]
            if word_files:
                print(f"Fichiers Word disponibles:")
                for f in word_files[:5]:  # Afficher les 5 premiers
                    print(f"  - {f}")
                if len(word_files) > 5:
                    print(f"  ... et {len(word_files)-5} autres")
            else:
                print("Aucun fichier Word trouvé")
        return
    
    print("="*70)
    print("📄 TEST EXTRACTION DOCUMENT WORD")
    print("="*70)
    
    print(f"🔍 Fichier: {os.path.basename(word_file)}")
    print(f"📏 Taille: {os.path.getsize(word_file) / 1024:.1f} KB")
    print(f"🌐 URL API: {api_url}")
    
    # Tester d'abord la connexion à l'API
    print("\n🔌 Test de connexion à l'API...")
    try:
        health_response = requests.get("http://localhost:8000/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ API en ligne et fonctionnelle")
        else:
            print(f"⚠️  API répond mais avec code {health_response.status_code}")
    except Exception as e:
        print(f"❌ Impossible de se connecter à l'API: {e}")
        print("\n💡 Vérifiez que l'API est en cours d'exécution:")
        print("  python -m app.main")
        return
    
    # Envoyer le fichier Word
    print(f"\n📤 Envoi du document Word à l'API...")
    start_time = time.time()
    
    try:
        with open(word_file, 'rb') as f:
            files = {'file': (os.path.basename(word_file), f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
            
            response = requests.post(api_url, files=files, timeout=30)
            processing_time = time.time() - start_time
        
        print(f"⏱️  Temps total: {processing_time:.2f}s")
        print(f"📡 Code HTTP: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ RÉSULTAT DE L'EXTRACTION")
            print("="*70)
            
            # Informations de base
            print(f"📊 Succès: {result.get('success', False)}")
            
            metadata = result.get('metadata', {})
            print(f"📄 Type document: {metadata.get('document_type', 'N/A')}")
            print(f"📄 MIME Type: {metadata.get('mime_type', 'N/A')}")
            print(f"📄 Nom fichier: {metadata.get('filename', 'N/A')}")
            print(f"📄 Taille: {metadata.get('file_size', 0) / 1024:.1f} KB")
            
            extraction = result.get('extraction', {})
            print(f"\n📝 Extraction OCR:")
            print(f"  🌐 Langue: {extraction.get('language', 'N/A')}")
            print(f"  📊 Confiance: {extraction.get('confidence', 0):.3f}")
            print(f"  ⏱️  Temps traitement: {extraction.get('processing_time', 0):.2f}s")
            
            text = extraction.get('text', '')
            text_length = len(text)
            print(f"  📏 Longueur texte: {text_length} caractères")
            
            if text:
                # Afficher un extrait
                print(f"\n🔍 EXTRACTION TEXTE (500 premiers caractères):")
                print("-" * 70)
                print(text[:500] + "..." if text_length > 500 else text)
                print("-" * 70)
                
                # Statistiques
                words = text.split()
                lines = text.split('\n')
                non_empty_lines = [line for line in lines if line.strip()]
                
                print(f"\n📈 STATISTIQUES:")
                print(f"  📝 Mots: {len(words)}")
                print(f"  📏 Lignes (total): {len(lines)}")
                print(f"  📏 Lignes (non vides): {len(non_empty_lines)}")
                print(f"  🔤 Caractères: {text_length}")
                
                # Recherche de mots-clés (pour voir la pertinence)
                keywords = ['architecture', 'système', 'client', 'serveur', 'base de données', 
                           'api', 'docker', 'microservices', 'cloud', 'sécurité']
                
                found_keywords = []
                text_lower = text.lower()
                for keyword in keywords:
                    if keyword in text_lower:
                        found_keywords.append(keyword)
                
                if found_keywords:
                    print(f"\n🔑 MOTS-CLÉS DÉTECTÉS:")
                    print(f"  {', '.join(found_keywords)}")
                
                # Résultats NLP si disponibles
                nlp_result = result.get('nlp_result')
                if nlp_result:
                    print(f"\n🤖 ANALYSE NLP:")
                    print(f"  🎯 Intention: {nlp_result.get('intent', 'N/A')}")
                    print(f"  📊 Confiance intention: {nlp_result.get('intent_confidence', 0):.3f}")
                    
                    client = nlp_result.get('client', {})
                    if client.get('first_name') or client.get('last_name'):
                        print(f"  👤 Client: {client.get('first_name', '')} {client.get('last_name', '')}")
                    
                    phones = nlp_result.get('client', {}).get('phone', [])
                    if phones:
                        print(f"  📱 Téléphones: {', '.join(phones)}")
                
                # Sauvegarder le résultat complet
                output_dir = os.path.dirname(word_file)
                base_name = os.path.basename(word_file).replace('.docx', '').replace('.doc', '')
                output_file = os.path.join(output_dir, f"ocr_result_{base_name}.txt")
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"=== EXTRACTION OCR DOCUMENT WORD ===\n")
                    f.write(f"Fichier: {os.path.basename(word_file)}\n")
                    f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Confiance: {extraction.get('confidence', 0):.3f}\n")
                    f.write(f"Caractères: {text_length}\n")
                    f.write("="*70 + "\n\n")
                    f.write(text)
                
                print(f"\n💾 Résultat sauvegardé dans: {output_file}")
                
                # Sauvegarder aussi la réponse JSON complète
                json_file = os.path.join(output_dir, f"api_response_{base_name}.json")
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                
                print(f"📊 Réponse API sauvegardée dans: {json_file}")
                
            else:
                print(f"\n❌ AUCUN TEXTE EXTRACTION")
                print(f"🔍 Réponse API complète pour debug:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
        elif response.status_code == 415:
            print(f"\n❌ ERREUR 415 - Type de fichier non supporté")
            print(f"💡 Vérifiez que votre endpoint accepte les fichiers Word (.docx)")
            print(f"📄 Réponse: {response.text}")
            
        elif response.status_code == 422:
            print(f"\n❌ ERREUR 422 - Validation échouée")
            print(f"📄 Réponse: {response.text}")
            
        else:
            print(f"\n❌ ERREUR HTTP: {response.status_code}")
            print(f"📄 Réponse: {response.text[:500]}...")
            
    except requests.exceptions.Timeout:
        print(f"\n❌ TIMEOUT - L'API n'a pas répondu dans les 30 secondes")
        print(f"💡 Le traitement Word peut prendre du temps pour les gros fichiers")
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ ERREUR CONNEXION - Impossible de se connecter à l'API")
        print(f"💡 Vérifiez que l'API est toujours en cours d'exécution")
        
    except Exception as e:
        print(f"\n❌ ERREUR INATTENDUE: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("✅ TEST TERMINÉ")
    print("="*70)

def test_word_fallback():
    """Test de secours si l'endpoint /docx n'existe pas"""
    print("\n" + "="*70)
    print("🔄 TEST DE SECOURS - Utilisation de l'endpoint générique")
    print("="*70)
    
    word_file = r"E:\document\ARCHITECTURE COMPLÈTE.docx"
    
    # Essayer l'endpoint /auto qui détecte automatiquement le type
    api_url = "http://localhost:8000/api/v1/ocr/auto"
    
    if os.path.exists(word_file):
        print(f"📤 Envoi à l'endpoint auto-détection...")
        
        try:
            with open(word_file, 'rb') as f:
                files = {'file': f}
                response = requests.post(api_url, files=files, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Réponse reçue")
                
                extraction = result.get('extraction', {})
                text = extraction.get('text', '')
                
                if text:
                    print(f"📝 Texte extrait: {len(text)} caractères")
                    print(f"\n🔍 Extrait (300 caractères):")
                    print("-" * 50)
                    print(text[:300] + "..." if len(text) > 300 else text)
                    print("-" * 50)
                else:
                    print(f"❌ Aucun texte extrait")
                    
                    # Essayer avec python-docx directement
                    print(f"\n🔄 Test direct avec python-docx...")
                    try:
                        from docx import Document
                        doc = Document(word_file)
                        direct_text = []
                        for para in doc.paragraphs:
                            direct_text.append(para.text)
                        
                        full_text = "\n".join(direct_text)
                        print(f"✅ Extraction directe: {len(full_text)} caractères")
                        print(f"🔍 Extrait: {full_text[:200]}...")
                        
                    except ImportError:
                        print(f"❌ python-docx non installé. Installez-le avec:")
                        print(f"   pip install python-docx")
                        
        except Exception as e:
            print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    # Test principal
    test_word_extraction()
    
    # Si le fichier n'existe pas, proposer des alternatives
    word_file = r"E:\document\ARCHITECTURE COMPLÈTE.docx"
    if not os.path.exists(word_file):
        print(f"\n⚠️  Fichier spécifique non trouvé, test avec d'autres fichiers...")
        test_word_fallback()