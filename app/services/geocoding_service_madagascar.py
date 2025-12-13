# app/services/geocoding_service_madagascar.py

import re
import time
import requests
import logging
from typing import Optional, Dict, List, Tuple, Set
from functools import lru_cache
from datetime import datetime, timedelta
import hashlib
import json

logger = logging.getLogger(__name__)


class CacheEntry:
    """Entrée de cache avec expiration"""
    
    def __init__(self, value: str, ttl_seconds: int = 3600):
        self.value = value
        self.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
    
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at
    
    def __repr__(self) -> str:
        return f"CacheEntry(value={self.value[:20]}..., expires={self.expires_at})"


class GeocodingServiceMadagascar:
   
    # Dictionnaire complet des villes de Madagascar
    # Mise à jour: Décembre 2025
    VILLES_MADAGASCAR = {
        # ---------------------------------------------------------------------
        # ANTANANARIVO ET ENVIRONS (Analamanga)
        # ---------------------------------------------------------------------
        "antananarivo": "Antananarivo",
        "tana": "Antananarivo",           # Nom commun
        "ananarivo": "Antananarivo",      # Variante orthographique
        "ivato": "Antananarivo",          # Aéroport
        "ambohidratrimo": "Antananarivo", # Commune urbaine
        
        # ---------------------------------------------------------------------
        # PROVINCES ET GRANDES VILLES
        # ---------------------------------------------------------------------
        # Province de Toamasina
        "toamasina": "Toamasina",
        "tamatave": "Toamasina",          # Ancien nom
        "mahavelona": "Foulpointe",       # Station balnéaire
        "foulpointe": "Foulpointe",
        "mahanoro": "Mahanoro",
        "vatomandry": "Vatomandry",
        
        # Province de Mahajanga
        "mahajanga": "Mahajanga",
        "majunga": "Mahajanga",           # Ancien nom
        "marovoay": "Marovoay",
        "soalala": "Soalala",
        "ambato-boeny": "Ambato-Boeny",
        
        # Province de Toliara
        "toliara": "Toliara",
        "tuléar": "Toliara",              # Ancien nom
        "tuléar": "Toliara",
        "morondava": "Morondava",
        "manja": "Manja",
        "belo sur tsiribihina": "Belo-sur-Tsiribihina",
        
        # Province d'Antsiranana
        "antsiranana": "Antsiranana",
        "diégo": "Antsiranana",           # Nom commun
        "diego": "Antsiranana",
        "ambilobe": "Ambilobe",
        "antsiranana": "Antsiranana",
        
        # Province de Fianarantsoa
        "fianarantsoa": "Fianarantsoa",
        "antsirabe": "Antsirabe",
        "ambositra": "Ambositra",
        "mananjary": "Mananjary",
        "manakara": "Manakara",
        "ihosy": "Ihosy",
        
        # Province d'Antananarivo (autres)
        "moramanga": "Moramanga",
        "ambatolampy": "Ambatolampy",
        "ambalavao": "Ambalavao",
        
        # ---------------------------------------------------------------------
        # VILLES IMPORTANTES
        # ---------------------------------------------------------------------
        "antalaha": "Antalaha",
        "sambava": "Sambava",
        "maroantsetra": "Maroantsetra",
        "taolagnaro": "Taolagnaro",
        "fort dauphin": "Taolagnaro",     # Ancien nom
        "andapa": "Andapa",
        "bekily": "Bekily",
        "betioky": "Betioky",
        "farafangana": "Farafangana",
        "miandrivazo": "Miandrivazo",
        "tsiroanomandidy": "Tsiroanomandidy",
        "vangaindrano": "Vangaindrano",
        "vohipeno": "Vohipeno",
        
        # ---------------------------------------------------------------------
        # ÎLES ET STATIONS BALNÉAIRES
        # ---------------------------------------------------------------------
        "nosy be": "Nosy Be",
        "nosy boraha": "Sainte-Marie",
        "sainte-marie": "Sainte-Marie",
        "nosy komba": "Nosy Komba",
        "nosy tanikely": "Nosy Tanikely",
        "ifaty": "Ifaty",
        "ankao": "Ankao",
        "mangily": "Mangily",
        "ankilibe": "Ankilibe",
        
        # ---------------------------------------------------------------------
        # COMMUNES ET DISTRICTS IMPORTANTS
        # ---------------------------------------------------------------------
        "ambanja": "Ambanja",
        "antsalova": "Antsalova",
        "beloha": "Beloha",
        "maintirano": "Maintirano",
        "mananara": "Mananara",
        "marolambo": "Marolambo",
        "soanierana ivongo": "Soanierana Ivongo",
        "vohémar": "Vohémar",
        "vondrozo": "Vondrozo",
    }
    
    # Quartiers par ville - Base de connaissances géographiques
    QUARTIERS_PAR_VILLE = {
        "Antananarivo": [
            # Centre-ville et quartiers historiques
            "Analakely", "Isotry", "Andohalo", "Ampasampito", "Ambodivona",
            "Anosy", "Tsaralalana", "Faravohitra", "Ambohimanarina",
            "Ambohidratrimo", "Ampandrana", "Andavamamba", "Ankadifotsy",
            "Ankadivato", "Ankorondrano", "Ivandry", "Ambatonakanga",
            "Mahamasina", "Antaninarenina", "Ankaditapaka", "Ambohijatovo",
            
            # Quartiers résidentiels
            "Ambohibao", "Amboditsiry", "Ambatobe", "Anjanahary",
            "Besarety", "Manjakaray", "Soixante sept hectares",
            "Anosibe", "Andraharo", "Ambohimiadana", "Ankazomanga",
            
            # Zones industrielles et commerciales
            "Ankadindramamy", "Andranomanalina", "Ambatomitsangana",
            "Ambatomirahavavy", "Ambohimiandra", "Androhibe",
            
            # Lotissements
            "Lotissement Amboniloha", "Lotissement Ivandry",
            "Lotissement Ambohidempona", "Lotissement Ankorahotra",
        ],
        
        "Toamasina": [
            # Centre-ville et quartiers centraux
            "Centre-ville", "Tanambao", "Morarano", "Ankirihiry", "Ampasimadinika",
            "Ambodimanga", "Analakininina", "Ambalavontaka", "Ampasina",
            "Ambohibe", "Ampasimpotsy", "Ambodiampana", "Ankirikiriky",
            
            # Zones portuaires et commerciales
            "Bazarikely", "Bazarybe", "Farafaty", "Analamalotra",
            "Ampasina-Manantsatrana", "Ampasimazava", "Ankirihitra",
            
            # Quartiers résidentiels
            "Ambodilafatra", "Amborovy", "Ampasina-Tsitongaina",
            "Ankofafa", "Antsiravina", "Betsimitatatra",
        ],
        
        "Mahajanga": [
            # Centre-ville
            "Centre-ville", "Mangarivotra", "Ambondrona", "Marolaka",
            "Antsahavola", "Ankazomiriotra", "Manga", "Befarafara",
            "Miarinarivo", "Ambohidronono", "Ankorikely", "Andranomamy",
            
            # Zones côtières
            "Antanimalandy", "Marovoay", "Ankoba", "Antsahabe",
            "Betsako", "Mahabibo", "Miarinavaratra",
            
            # Quartiers périphériques
            "Amborovy", "Ankaraobato", "Antsanitia", "Betsiakoho",
        ],
        
        "Antsirabe": [
            # Centre-ville et quartiers thermaux
            "Centre-ville", "Andranomanelatra", "Antanambao", "Ambohimasina",
            "Soaindrana", "Manandona", "Ivohitra", "Antsahalava",
            "Manarintsoa", "Antanimena", "Sabotsy", "Ambohibary",
            
            # Zones industrielles
            "Antsahafiry", "Fivarotanana", "Manodidina", "Tsiroanomandidy",
            
            # Quartiers résidentiels
            "Ambohitsimanova", "Andranomafana", "Antsirakely", "Soavina",
        ],
        
        "Fianarantsoa": [
            # Ville haute et basse
            "Haute-ville", "Basse-ville", "Tsianolondroa", "Ambohimena",
            "Ambatomena", "Ambohijanahary", "Ambohimalaza", "Isoraka",
            "Andrainjato", "Ambohimahamasina", "Ankofafa", "Andoharanomaitso",
            
            # Quartiers universitaires
            "Ankofafa Sud", "Andoharano", "Ambalamidera", "Imito",
            
            # Zones périphériques
            "Ambohimahasoa", "Ambatofitorahana", "Anjoma", "Soatanana",
        ],
        
        "Toliara": [
            # Centre-ville côtier
            "Centre-ville", "Ankilibe", "Andaboly", "Ambohibe", "Anketa",
            "Betsinjake", "Ankililoaka", "Ankoba", "Amboronampela",
            "Ankadimanga", "Ambohimena", "Ankoronga", "Ankasina",
            
            # Zones portuaires
            "Ambohitrandriana", "Andranovory", "Bevala", "Mangarivotra",
            
            # Quartiers résidentiels
            "Ambondro", "Ankiliabo", "Befasy", "Mikoboke",
        ],
        
        "Nosy Be": [
            # Villages et stations balnéaires
            "Hell-Ville", "Ambatozavavy", "Ambondrona", "Ampasipohy",
            "Andilana", "Madirokely", "Mitsinjo", "Tanikely",
        ],
        
        "Sainte-Marie": [
            # Villages de l'île
            "Ambodifotatra", "Anafiafy", "Ampanihy", "Manompana",
            "Sainte-Marie Centre", "Voloina", "Ankirihiry",
        ]
    }
    
    # Mapping des codes postaux malgaches
    # Format: {code_postal: "Zone de livraison"}
    CODES_POSTAUX = {
        # ---------------------------------------------------------------------
        # ANTANANARIVO (101-105)
        # ---------------------------------------------------------------------
        "101": "Antananarivo Centre",
        "102": "Antananarivo Avaradrano",
        "103": "Antananarivo Atsimondrano",
        "104": "Antananarivo Renivohitra",
        "105": "Antananarivo",
        
        # ---------------------------------------------------------------------
        # ANTSIRANANA (201-210)
        # ---------------------------------------------------------------------
        "201": "Antsiranana I",
        "202": "Antsiranana II",
        "203": "Antsiranana",
        "205": "Ambilobe",
        "206": "Nosy Be",
        "207": "Antalaha",
        "208": "Sambava",
        "209": "Vohemar",
        "210": "Andapa",
        
        # ---------------------------------------------------------------------
        # FIANARANTSOA (301-315)
        # ---------------------------------------------------------------------
        "301": "Fianarantsoa I",
        "302": "Fianarantsoa II",
        "303": "Mananjary",
        "304": "Manakara",
        "305": "Farafangana",
        "306": "Ambositra",
        "307": "Ambositra",
        "308": "Ihosy",
        "309": "Vangaindrano",
        "310": "Vondrozo",
        
        # ---------------------------------------------------------------------
        # MAHAJANGA (401-415)
        # ---------------------------------------------------------------------
        "401": "Mahajanga I",
        "402": "Mahajanga II",
        "403": "Mahajanga",
        "404": "Marovoay",
        "405": "Soalala",
        "406": "Maintirano",
        "407": "Antsalova",
        "408": "Besalampy",
        "409": "Ambato-Boeny",
        
        # ---------------------------------------------------------------------
        # TOAMASINA (501-515)
        # ---------------------------------------------------------------------
        "501": "Toamasina I",
        "502": "Toamasina II",
        "503": "Mahanoro",
        "504": "Vatomandry",
        "505": "Foulpointe",
        "506": "Brickaville",
        "507": "Vohibinany",
        "508": "Marolambo",
        "509": "Mananara",
        "510": "Soanierana Ivongo",
        "514": "Sainte-Marie",
        "515": "Sainte-Marie",
        
        # ---------------------------------------------------------------------
        # TOLIARA (601-620)
        # ---------------------------------------------------------------------
        "601": "Toliara I",
        "602": "Toliara II",
        "603": "Toliara",
        "604": "Tuléar I",
        "605": "Tuléar II",
        "606": "Morombe",
        "607": "Tsimanampetsotsa",
        "608": "Betioky",
        "609": "Ampanihy",
        "610": "Beloha",
        "611": "Tsihombe",
        "612": "Ambovombe",
        "613": "Tolanaro",
        "614": "Amboasary",
        "615": "Taolagnaro",
        "616": "Fort-Dauphin",
        "617": "Manantenina",
        "618": "Manambaro",
        "619": "Morondava",
        "620": "Morondava",
        
        # ---------------------------------------------------------------------
        # AUTRES VILLES IMPORTANTES
        # ---------------------------------------------------------------------
        "110": "Antsirabe I",
        "111": "Antsirabe II",
        "112": "Betafo",
        "113": "Mandoto",
        "114": "Miandrivazo",
        "115": "Miarinarivo",
        "116": "Soavinandriana",
        "117": "Arivonimamo",
        "118": "Anjozorobe",
        "119": "Manjakandriana",
        
        "120": "Moramanga",
        "121": "Anosibe An'ala",
        "122": "Andilamena",
        "123": "Ambatondrazaka",
        "124": "Ambatondrazaka",
        
        "130": "Ambatolampy",
        "131": "Antanifotsy",
        "132": "Faratsiho",
        "133": "Antsirabe"
    }
    
    # Mots-clés géographiques spécifiques à Madagascar
    INDICATEURS_GEOGRAPHIQUES = {
        "fokontany": "Fokontany",
        "commune": "Commune",
        "commune rurale": "Commune Rurale",
        "commune urbaine": "Commune Urbaine",
        "district": "District",
        "region": "Région",
        "faritra": "Faritra",
        "tanàna": "Tanàna",
        "tanàna": "Tanàna",
        "vohitra": "Vohitra",
        "village": "Village",
    }
    
    # Mots à ignorer lors de l'extraction des mots significatifs
    STOP_WORDS = {
        "de", "la", "du", "des", "et", "à", "au", "aux", "d", "l",
        "lalana", "avenue", "boulevard", "place", "allée", "chemin",
        "lot", "quartier", "commune", "district", "region", "tanàna",
        "fokontany", "faritra", "voie", "route", "rn", "nationale",
        "près", "proche", "face", "à côté", "madagascar", "mg", "rue",
        "street", "road", "avenue", "boulevard", "place", "square",
        "numéro", "n°", "numero", "no", "n", "#", "bis", "ter",
        "madagasikara", "mg", "repoblikan'i", "repoblikan'i madagasikara"
    }
    
    def __init__(self, use_api_fallback: bool = False, cache_ttl: int = 3600):
        """
        Initialise le service de géocodage
        
        Args:
            use_api_fallback: Activer le fallback à OpenStreetMap API
            cache_ttl: Durée de vie du cache en secondes (défaut: 1 heure)
        """
        self.use_api_fallback = use_api_fallback
        self.cache_ttl = cache_ttl
        self.cache: Dict[str, CacheEntry] = {}
        self.cache_hits = 0
        self.cache_misses = 0
        
        # Configuration API externe
        self.nominatim_url = "https://nominatim.openstreetmap.org/search"
        self.headers = {'User-Agent': 'LiveCommerceDelivery/2.0 (contact@livecommerce.mg)'}
        self.last_request_time = 0
        self.min_request_interval = 1  # seconde entre les requêtes API
        
        # Métriques de performance
        self.metrics = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'postal_detections': 0,
            'city_detections': 0,
            'quarter_detections': 0,
            'geographic_detections': 0,
            'api_fallbacks': 0,
            'intelligent_fallbacks': 0,
            'avg_response_time': 0.0,
        }
        
        logger.info(f"GeocodingServiceMadagascar initialisé (cache_ttl={cache_ttl}s)")
    
    def _get_cache_key(self, address: str) -> str:
        """Génère une clé de cache normalisée pour une adresse"""
        # Normalisation: minuscules, suppression des espaces multiples, ponctuation
        normalized = re.sub(r'\s+', ' ', address.lower().strip())
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    def _get_from_cache(self, address: str) -> Optional[str]:
        """Récupère une valeur du cache avec vérification d'expiration"""
        cache_key = self._get_cache_key(address)
        
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if not entry.is_expired():
                self.cache_hits += 1
                self.metrics['cache_hits'] += 1
                logger.debug(f"Cache hit pour: {address[:50]}...")
                return entry.value
            else:
                # Supprimer l'entrée expirée
                del self.cache[cache_key]
        
        self.cache_misses += 1
        self.metrics['cache_misses'] += 1
        return None
    
    def _save_to_cache(self, address: str, value: str) -> None:
        """Sauvegarde une valeur dans le cache"""
        cache_key = self._get_cache_key(address)
        self.cache[cache_key] = CacheEntry(value, self.cache_ttl)
        
        # Limiter la taille du cache à 5000 entrées
        if len(self.cache) > 5000:
            # Supprimer les 20% les plus anciennes
            keys_to_remove = list(self.cache.keys())[:1000]
            for key in keys_to_remove:
                del self.cache[key]
            logger.debug(f"Cache nettoyé: {len(keys_to_remove)} entrées supprimées")
    
    def clear_cache(self) -> None:
        """Vide complètement le cache"""
        self.cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        logger.info("Cache vidé")
    
    def get_cache_stats(self) -> Dict:
        """Retourne les statistiques du cache"""
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total * 100) if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'hits': self.cache_hits,
            'misses': self.cache_misses,
            'hit_rate': f"{hit_rate:.1f}%",
            'ttl_seconds': self.cache_ttl,
        }
    
    def get_metrics(self) -> Dict:
        """Retourne les métriques de performance"""
        total_time = self.metrics['total_requests']
        avg_time = self.metrics['avg_response_time'] / total_time if total_time > 0 else 0
        
        return {
            **self.metrics,
            'cache_stats': self.get_cache_stats(),
            'avg_response_time_ms': f"{avg_time*1000:.2f}ms",
            'total_cities': len(self.VILLES_MADAGASCAR),
            'total_quarters': sum(len(q) for q in self.QUARTIERS_PAR_VILLE.values()),
            'total_postal_codes': len(self.CODES_POSTAUX),
        }
    
    def reset_metrics(self) -> None:
        """Réinitialise toutes les métriques"""
        self.metrics = {k: 0 for k in self.metrics}
        self.metrics['avg_response_time'] = 0.0
        logger.info("Métriques réinitialisées")
    
    @lru_cache(maxsize=1000)
    def extract_zone_from_address(self, address: str) -> str:
        start_time = time.time()
        self.metrics['total_requests'] += 1
        
        try:
            # Validation de l'entrée
            if not address or not isinstance(address, str):
                raise ValueError("Adresse invalide ou vide")
            
            address_lower = address.lower().strip()
            
            # 1. Vérification du cache
            cached_result = self._get_from_cache(address)
            if cached_result:
                return cached_result
            
            logger.info(f"Géocodage nouvelle adresse: {address[:100]}...")
            
            # 2. Détection par code postal
            postal_zone = self._detect_by_postal_code(address)
            if postal_zone:
                self.metrics['postal_detections'] += 1
                self._save_to_cache(address, postal_zone)
                return postal_zone
            
            # 3. Détection par ville dans le dictionnaire
            city_zone = self._detect_by_city(address_lower)
            if city_zone:
                # 4. Détection du quartier
                quarter = self._detect_quarter(address_lower, city_zone)
                if quarter:
                    final_zone = f"{city_zone} - {quarter}"
                    self.metrics['quarter_detections'] += 1
                else:
                    final_zone = city_zone
                    self.metrics['city_detections'] += 1
                
                self._save_to_cache(address, final_zone)
                return final_zone
            
            # 5. Détection par indicateurs géographiques
            geo_zone = self._detect_by_geographic_indicators(address_lower)
            if geo_zone:
                self.metrics['geographic_detections'] += 1
                self._save_to_cache(address, geo_zone)
                return geo_zone
            
            # 6. Fallback API externe (optionnel)
            if self.use_api_fallback:
                api_zone = self._fallback_to_api(address)
                if api_zone:
                    self.metrics['api_fallbacks'] += 1
                    self._save_to_cache(address, api_zone)
                    return api_zone
            
            # 7. Fallback intelligent final
            final_zone = self._intelligent_fallback(address)
            self.metrics['intelligent_fallbacks'] += 1
            self._save_to_cache(address, final_zone)
            return final_zone
            
        except Exception as e:
            logger.error(f"Erreur géocodage pour '{address[:50]}...': {e}")
            return "Zone Madagascar"
        
        finally:
            # Calcul du temps de réponse
            response_time = time.time() - start_time
            self.metrics['avg_response_time'] += response_time
            logger.debug(f"Géocodage terminé en {response_time*1000:.2f}ms")
    
    def _detect_by_postal_code(self, address: str) -> Optional[str]:
        """Détecte la zone par code postal malgache"""
        # Recherche des codes postaux format 3 chiffres (101-999)
        cp_match = re.search(r'\b(10[1-9]|11[0-9]|12[0-9]|13[0-9]|20[1-9]|30[1-9]|40[1-9]|50[1-9]|60[1-9]|70[1-9]|80[1-9]|90[1-9])\b', address)
        
        if cp_match:
            cp = cp_match.group()
            zone = self.CODES_POSTAUX.get(cp)
            if zone:
                logger.debug(f"Détection code postal {cp} → {zone}")
                return zone
            else:
                logger.debug(f"Code postal {cp} non mappé")
                return f"Zone {cp}"
        
        return None
    
    def _detect_by_city(self, address_lower: str) -> Optional[str]:
        """Détecte la ville dans l'adresse"""
        # Chercher les noms complets de ville (limites de mot)
        for ville_key, ville_name in self.VILLES_MADAGASCAR.items():
            pattern = r'(?:^|\W)' + re.escape(ville_key) + r'(?:$|\W)'
            if re.search(pattern, address_lower):
                logger.debug(f"Détection ville exacte: {ville_key} → {ville_name}")
                return ville_name
        
        # Chercher des parties de noms de ville (pour les noms composés)
        for ville_key, ville_name in self.VILLES_MADAGASCAR.items():
            if ville_key in address_lower:
                # Vérifier que ce n'est pas dans un autre mot
                words = address_lower.split()
                for word in words:
                    if ville_key in word and len(word) <= len(ville_key) + 3:
                        logger.debug(f"Détection ville partielle: {ville_key} → {ville_name}")
                        return ville_name
        
        return None
    
    def _detect_quarter(self, address_lower: str, city: str) -> Optional[str]:
        """Détecte le quartier dans l'adresse pour une ville donnée"""
        if city in self.QUARTIERS_PAR_VILLE:
            quarters = self.QUARTIERS_PAR_VILLE[city]
            
            # Chercher les quartiers exacts
            for quarter in quarters:
                quarter_lower = quarter.lower()
                pattern = r'(?:^|\W)' + re.escape(quarter_lower) + r'(?:$|\W)'
                if re.search(pattern, address_lower):
                    logger.debug(f"Détection quartier {quarter} pour {city}")
                    return quarter
            
            # Chercher les mots-clés de quartier génériques
            quarter_keywords = {
                "lotissement": "Lotissement",
                "quartier": "Quartier",
                "cite": "Cité",
                "zone": "Zone",
                "camp": "Camp",
                "village": "Village",
            }
            
            for keyword, prefix in quarter_keywords.items():
                if keyword in address_lower:
                    # Extraire le nom après le mot-clé
                    pattern = fr'{keyword}\s+(\w+(?:\s+\w+)*)'
                    match = re.search(pattern, address_lower)
                    if match:
                        quarter_name = match.group(1).title()
                        logger.debug(f"Détection {keyword}: {quarter_name}")
                        return f"{prefix} {quarter_name}"
        
        return None
    
    def _detect_by_geographic_indicators(self, address_lower: str) -> Optional[str]:
        """Détecte par indicateurs géographiques spécifiques à Madagascar"""
        for indicator_key, indicator_name in self.INDICATEURS_GEOGRAPHIQUES.items():
            if indicator_key in address_lower:
                # Extraire le nom spécifique après l'indicateur
                pattern = fr'{indicator_key}\s+(\w+(?:\s+\w+)*)'
                match = re.search(pattern, address_lower)
                if match:
                    specific_name = match.group(1).title()
                    logger.debug(f"Détection {indicator_key}: {specific_name}")
                    return f"{indicator_name} {specific_name}"
                else:
                    return indicator_name
        
        return None
    
    def _wait_for_rate_limit(self):
        """Attend pour respecter les limites de taux de l'API externe"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            time.sleep(wait_time)
        
        self.last_request_time = time.time()
    
    def _fallback_to_api(self, address: str) -> Optional[str]:
        """Utilise l'API OpenStreetMap comme fallback"""
        try:
            self._wait_for_rate_limit()
            
            params = {
                'q': f"{address}, Madagascar",
                'format': 'json',
                'addressdetails': 1,
                'limit': 1,
                'countrycodes': 'mg',
                'accept-language': 'fr',
                'namedetails': 1
            }
            
            response = requests.get(
                self.nominatim_url, 
                params=params, 
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    result = data[0]
                    
                    # Priorité des champs pour Madagascar
                    priority_fields = [
                        ('city', 10),
                        ('town', 9),
                        ('village', 8),
                        ('municipality', 7),
                        ('suburb', 6),
                        ('county', 5),
                        ('state', 4),
                        ('region', 3),
                        ('display_name', 1)
                    ]
                    
                    for field, priority in priority_fields:
                        if field in result.get('address', {}):
                            zone = result['address'][field]
                            if zone and str(zone).strip():
                                logger.info(f"API détection: {field} → {zone}")
                                return str(zone)
                    
                    # Fallback sur display_name
                    if 'display_name' in result:
                        display_name = result['display_name']
                        # Extraire la partie la plus pertinente
                        parts = display_name.split(',')
                        if len(parts) > 1:
                            zone = parts[1].strip()
                            logger.info(f"API fallback display_name: {zone}")
                            return zone
        
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout API OpenStreetMap pour: {address[:50]}...")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Erreur connexion API OpenStreetMap")
        except Exception as e:
            logger.debug(f"API OpenStreetMap échouée: {e}")
        
        return None
    
    def _intelligent_fallback(self, address: str) -> str:
        """Fallback intelligent basé sur l'extraction de mots significatifs"""
        # Nettoyer l'adresse
        clean_address = re.sub(r'[^\w\s]', ' ', address)
        words = clean_address.split()
        
        # Filtrer les mots significatifs
        significant_words = []
        for word in words:
            word_lower = word.lower()
            
            # Critères d'exclusion
            if (len(word) > 2 and 
                word_lower not in self.STOP_WORDS and
                not word.isdigit() and
                not re.match(r'^[a-z]$', word_lower) and
                not re.match(r'^\d+[a-z]?$', word_lower)):
                
                significant_words.append(word.capitalize())
                if len(significant_words) >= 3:
                    break
        
        if significant_words:
            result = " ".join(significant_words)
            logger.debug(f"Fallback intelligent: {result}")
            return result
        elif words:
            # Prendre les 2 premiers mots significatifs
            first_words = [w.capitalize() for w in words[:2] if len(w) > 2]
            if first_words:
                result = " ".join(first_words)
                logger.debug(f"Fallback 2 premiers mots: {result}")
                return result
        
        logger.debug("Fallback par défaut: Zone Madagascar")
        return "Zone Madagascar"
    
    def get_delivery_zones_for_driver(self, driver_address: str, max_zones: int = 10) -> List[str]:
        """
        Retourne les zones de livraison pour un livreur
        
        Cette méthode détermine la zone principale basée sur l'adresse du livreur,
        puis ajoute des zones similaires/géographiquement proches.
        
        Args:
            driver_address: Adresse complète du livreur
            max_zones: Nombre maximum de zones à retourner (1-20)
        
        Returns:
            List[str]: Zones où le livreur peut livrer, triées par pertinence
        
        Examples:
            >>> service.get_delivery_zones_for_driver("Analakely, Antananarivo 101")
            [
                "Antananarivo Centre",
                "Antananarivo - Analakely",
                "Antananarivo - Isotry",
                "Antananarivo - Andohalo",
                "Antananarivo Avaradrano"
            ]
        """
        # Validation des paramètres
        max_zones = max(1, min(20, max_zones))
        
        # Zone principale
        main_zone = self.extract_zone_from_address(driver_address)
        zones = [main_zone]
        
        # Extraire la ville de la zone principale
        if " - " in main_zone:
            city = main_zone.split(" - ")[0]
        else:
            city = main_zone
        
        # Ajouter des zones similaires basées sur la ville
        if city in self.QUARTIERS_PAR_VILLE:
            quarters = self.QUARTIERS_PAR_VILLE[city]
            
            # Filtrer les quartiers qui ne sont pas déjà dans la zone principale
            for quarter in quarters:
                if quarter not in main_zone and f"{city} - {quarter}" not in zones:
                    zones.append(f"{city} - {quarter}")
                    if len(zones) >= max_zones:
                        break
        
        # Si nous avons encore de la place, ajouter des villes voisines
        if len(zones) < max_zones and city in self._get_neighbor_cities():
            neighbors = self._get_neighbor_cities()[city]
            for neighbor in neighbors[:max_zones - len(zones)]:
                if neighbor not in zones:
                    zones.append(neighbor)
        
        return zones[:max_zones]
    
    def _get_neighbor_cities(self) -> Dict[str, List[str]]:
        """Retourne les villes géographiquement proches"""
        return {
            "Antananarivo": ["Antsirabe", "Ambatolampy", "Moramanga", "Arivonimamo"],
            "Toamasina": ["Foulpointe", "Mahanoro", "Vatomandry", "Brickaville"],
            "Mahajanga": ["Marovoay", "Soalala", "Ambato-Boeny", "Mitsinjo"],
            "Toliara": ["Morombe", "Betioky", "Ampanihy", "Ankilibe"],
            "Antsiranana": ["Ambilobe", "Nosy Be", "Antalaha", "Sambava"],
            "Fianarantsoa": ["Ambositra", "Ihosy", "Manakara", "Mananjary"],
            "Antsirabe": ["Betafo", "Ambositra", "Antananarivo", "Faratsiho"],
            "Morondava": ["Belon'i Tsiribihina", "Manja", "Mahabo", "Malandiandafitra"],
            "Ambositra": ["Fandriana", "Antsirabe", "Fianarantsoa", "Ambatofinandrahana"],
            "Sainte-Marie": ["Soanierana Ivongo", "Fenoarivo Atsinanana", "Mananara"],
        }
    
    def get_all_supported_zones(self) -> List[str]:
        """Retourne toutes les zones supportées par le système"""
        zones = set()
        
        # Ajouter toutes les villes
        zones.update(set(self.VILLES_MADAGASCAR.values()))
        
        # Ajouter les quartiers formatés
        for city, quarters in self.QUARTIERS_PAR_VILLE.items():
            for quarter in quarters:
                zones.add(f"{city} - {quarter}")
        
        # Ajouter les codes postaux
        zones.update(set(self.CODES_POSTAUX.values()))
        
        # Ajouter les indicateurs géographiques
        zones.update(set(self.INDICATEURS_GEOGRAPHIQUES.values()))
        
        return sorted(zones)
    
    def search_zones(self, query: str, limit: int = 10) -> List[str]:
        """
        Recherche des zones correspondant à une requête
        
        Args:
            query: Terme de recherche
            limit: Nombre maximum de résultats
        
        Returns:
            List[str]: Zones correspondantes triées par pertinence
        """
        query_lower = query.lower().strip()
        results = []
        
        # Recherche dans les zones supportées
        all_zones = self.get_all_supported_zones()
        
        for zone in all_zones:
            zone_lower = zone.lower()
            
            # Score de pertinence
            score = 0
            
            # Correspondance exacte
            if zone_lower == query_lower:
                score += 100
            
            # Commence par la requête
            elif zone_lower.startswith(query_lower):
                score += 50
            
            # Contient la requête
            elif query_lower in zone_lower:
                score += 30
            
            # Mots en commun
            query_words = set(query_lower.split())
            zone_words = set(zone_lower.split())
            common_words = query_words.intersection(zone_words)
            if common_words:
                score += len(common_words) * 10
            
            if score > 0:
                results.append((score, zone))
        
        # Trier par score décroissant
        results.sort(key=lambda x: x[0], reverse=True)
        
        return [zone for _, zone in results[:limit]]
    
    def validate_address(self, address: str) -> Dict:
        """
        Valide une adresse et retourne des informations détaillées
        
        Args:
            address: Adresse à valider
        
        Returns:
            Dict: Informations de validation
        """
        zone = self.extract_zone_from_address(address)
        
        # Analyse de l'adresse
        components = {
            'postal_code': None,
            'city': None,
            'quarter': None,
            'geographic_indicator': None,
        }
        
        # Détection code postal
        cp_match = re.search(r'\b(10[1-9]|11[0-9]|12[0-9]|13[0-9]|20[1-9]|30[1-9]|40[1-9]|50[1-9]|60[1-9])\b', address)
        if cp_match:
            components['postal_code'] = cp_match.group()
        
        # Détection ville
        for ville_key, ville_name in self.VILLES_MADAGASCAR.items():
            if ville_key in address.lower():
                components['city'] = ville_name
                break
        
        # Détection indicateur géographique
        for indicator in self.INDICATEURS_GEOGRAPHIQUES:
            if indicator in address.lower():
                components['geographic_indicator'] = indicator
                break
        
        return {
            'address': address,
            'zone': zone,
            'components': components,
            'is_valid': zone != "Zone Madagascar",
            'confidence': 'high' if components['city'] or components['postal_code'] else 'medium',
            'timestamp': datetime.now().isoformat(),
        }
    
    def save_cache_to_file(self, filepath: str = "geocoding_cache.json") -> bool:
        """Sauvegarde le cache sur disque"""
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'entries': [
                    {
                        'address_hash': key,
                        'value': entry.value,
                        'expires_at': entry.expires_at.isoformat()
                    }
                    for key, entry in self.cache.items()
                    if not entry.is_expired()
                ]
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Cache sauvegardé: {len(cache_data['entries'])} entrées -> {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde cache: {e}")
            return False
    
    def load_cache_from_file(self, filepath: str = "geocoding_cache.json") -> bool:
        """Charge le cache depuis le disque"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            loaded_count = 0
            for entry_data in cache_data.get('entries', []):
                expires_at = datetime.fromisoformat(entry_data['expires_at'])
                if expires_at > datetime.now():
                    self.cache[entry_data['address_hash']] = CacheEntry(
                        entry_data['value'],
                        int((expires_at - datetime.now()).total_seconds())
                    )
                    loaded_count += 1
            
            logger.info(f"Cache chargé: {loaded_count} entrées valides depuis {filepath}")
            return loaded_count > 0
            
        except FileNotFoundError:
            logger.debug(f"Fichier cache non trouvé: {filepath}")
            return False
        except Exception as e:
            logger.error(f"Erreur chargement cache: {e}")
            return False


# =============================================================================
# INSTANCE GLOBALE POUR L'APPLICATION
# =============================================================================

# Instance configurable via variables d'environnement
import os

# Configuration via variables d'environnement
CACHE_TTL = int(os.getenv('GEOCODING_CACHE_TTL', '3600'))  # 1 heure par défaut
USE_API_FALLBACK = os.getenv('GEOCODING_USE_API_FALLBACK', 'false').lower() == 'true'

# Création de l'instance globale
geocoding_service_mg = GeocodingServiceMadagascar(
    use_api_fallback=USE_API_FALLBACK,
    cache_ttl=CACHE_TTL
)

# Optionnel: Charger le cache depuis le disque au démarrage
if os.getenv('GEOCODING_LOAD_CACHE', 'false').lower() == 'true':
    geocoding_service_mg.load_cache_from_file()

if __name__ == "__main__":
    # Mode démo/test
    service = GeocodingServiceMadagascar()
    
    print("🧪 DÉMONSTRATION GÉOCODAGE MADAGASCAR")
    print("=" * 80)
    
    test_addresses = [
        "Analakely, Antananarivo 101",
        "Port de Toamasina, Rue Commerce 501",
        "Boulevard de la Mer, Mahajanga 401",
        "Fokontany Antanimena, Antsirabe 110",
        "RN7, PK 12, Ambatolampy",
        "Lotissement Amboniloha, Antananarivo",
    ]
    
    for addr in test_addresses:
        zone = service.extract_zone_from_address(addr)
        print(f"📍 {addr}")
        print(f"   → {zone}")
        print()
    
    # Afficher les statistiques
    print("📊 STATISTIQUES:")
    stats = service.get_cache_stats()
    metrics = service.get_metrics()
    print(f"   Cache: {stats['size']} entrées, Hit rate: {stats['hit_rate']}")
    print(f"   Performance: {metrics['avg_response_time_ms']} par requête")
    print(f"   Détections: {metrics['city_detections']} villes, {metrics['quarter_detections']} quartiers")