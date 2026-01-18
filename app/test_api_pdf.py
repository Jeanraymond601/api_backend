# app/test_api_pdf_final.py
import requests
import json

def test_final():
    url = "http://localhost:8000/api/v1/ocr/pdf"
    
    with open(r"E:\document\CANEVAS-L3-M2-ENI-2023-2024.pdf", 'rb') as f:
        files = {'file': ('test.pdf', f, 'application/pdf')}
        response = requests.post(url, files=files)
        
        print(f"Status: {response.status_code}")
        result = response.json()
        
        if result.get('success'):
            print(f"\n✅ SUCCÈS!")
            text = result.get('extraction', {}).get('text', '')
            print(f"📝 Texte extrait: {len(text)} caractères")
            
            if text:
                print(f"\n🔍 Extrait (300 caractères):")
                print("="*60)
                print(text[:300])
                print("="*60)
        else:
            print(f"\n❌ ÉCHEC: {result}")

test_final()