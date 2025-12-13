# test_geocodage_amelioré.py
import requests
import json
from datetime import datetime

def test_geocoding_improvement():
    """
    Test spécifique pour comparer l'ancien et le nouveau géocodage
    """
    BASE_URL = "http://localhost:8000"
    TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZmMxMjZhODItNDFjNi00ZjQ4LWE1MGMtYzEzZTBiM2M4YjE5IiwiZW1haWwiOiJ0ZWFtc29yYTQwQGdtYWlsLmNvbSIsInJvbGUiOiJWZW5kZXVyIiwiZnVsbF9uYW1lIjoiSmVhbiBSYXltb25kIiwiZXhwIjoxNzY0NzU3NDQ5LCJpYXQiOjE3NjQ3NTM4NDksIm5iZiI6MTc2NDc1Mzg0OX0.kzTMykXtdTGr0SajHN8ySB2WcISzYbUS3J_15Hxgkzo"
    
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Adresses complexes pour tester le géocodage amélioré
    complex_addresses = [
        ("Fokontany Antanimena, Antsirabe", "Antsirabe"),
        ("Commune rurale d'Andasibe, Moramanga", "Moramanga"),
        ("Lotissement Amboniloha, près stade Mahamasina, Antananarivo", "Antananarivo"),
        ("RN7, PK 12, Ambatolampy", "Ambatolampy"),
        ("Zone industrielle, Ivato Airport, Antananarivo", "Antananarivo"),
        ("Plage d'Ambondrona, Nosy Be", "Nosy Be"),
        ("Marché d'Analakely, Antananarivo", "Antananarivo"),
        ("Campus universitaire, Ankatso, Antananarivo", "Antananarivo"),
        ("Port de pêche, Mahavelona, Foulpointe", "Foulpointe"),
        ("Station service Total, Ambohidrapeto, Antananarivo", "Antananarivo")
    ]
    
    print("🧪 TEST GÉOCODAGE AMÉLIORÉ - ADRESSES COMPLEXES")
    print("=" * 80)
    
    results = []
    
    for address, expected_zone in complex_addresses:
        driver_data = {
            "full_name": f"Test {expected_zone}",
            "email": f"test.{expected_zone.lower()}.{int(datetime.now().timestamp())}@mg.mg",
            "telephone": f"034{int(datetime.now().timestamp()) % 10000000:07d}",
            "adresse": address,
            "password": "Test123!",
            "statut": "actif"
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/v1/drivers/",
                headers=headers,
                json=driver_data
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                actual_zone = result.get("zone_livraison", "Non détectée")
                correct = expected_zone.lower() in actual_zone.lower()
                
                status = "✅" if correct else "❌"
                results.append({
                    "address": address,
                    "expected": expected_zone,
                    "actual": actual_zone,
                    "correct": correct
                })
                
                print(f"\n{status} {address[:50]}...")
                print(f"   Attendu: {expected_zone}")
                print(f"   Obtenu: {actual_zone}")
                
                # Tester la mise à jour de géolocalisation
                driver_id = result.get("driver_id")
                if driver_id:
                    # Récupérer la zone initiale
                    get_response = requests.get(
                        f"{BASE_URL}/api/v1/drivers/{driver_id}",
                        headers=headers
                    )
                    
                    if get_response.status_code == 200:
                        initial_zone = get_response.json().get("zone_livraison", "")
                        
                        # Tester la mise à jour
                        update_response = requests.post(
                            f"{BASE_URL}/api/v1/drivers/{driver_id}/update-geolocation",
                            headers=headers
                        )
                        
                        if update_response.status_code == 200:
                            updated_data = update_response.json()
                            new_zone = updated_data.get("new_zone", "")
                            
                            if initial_zone == new_zone:
                                print(f"   🔄 Géocodage cohérent (pas de changement)")
                            else:
                                print(f"   🔄 Géocodage mis à jour: {new_zone}")
            else:
                print(f"\n❌ Erreur création: {response.status_code} - {response.text[:100]}")
                
        except Exception as e:
            print(f"\n❌ Exception: {str(e)}")
    
    # Analyse des résultats
    print("\n" + "="*80)
    print("📊 ANALYSE DES RÉSULTATS:")
    
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accuracy = (correct / total * 100) if total > 0 else 0
    
    print(f"   • Total tests: {total}")
    print(f"   • Corrects: {correct}")
    print(f"   • Précision: {accuracy:.1f}%")
    
    if accuracy < 90:
        print(f"\n⚠️  RECOMMANDATION:")
        print("   Implémenter GeocodingServiceMadagascar pour améliorer la précision")
    
    # Sauvegarder les résultats
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total,
        "correct": correct,
        "accuracy": f"{accuracy:.1f}%",
        "results": results
    }
    
    with open("test_geocodage_complexe.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Rapport sauvegardé: test_geocodage_complexe.json")

if __name__ == "__main__":
    test_geocoding_improvement()