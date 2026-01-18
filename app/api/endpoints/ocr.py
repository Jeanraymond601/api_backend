from datetime import datetime
import re
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional, List, Dict, Any, Tuple
import uuid
import time
import logging
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import json
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import asyncio

from pydantic import BaseModel

from app.models.ocr_nlp import (
    DocumentType, Language, IntentType,
    DocumentMetadata, ExtractionResult, NLPResult, GeoCoordinates,
    OCRResponse, BatchOCRResponse
)
from ...schemas import (
    StandardResponse, ErrorResponse,
    HealthCheckResponse, SystemMetrics
)

# Initialiser le logger
logger = logging.getLogger(__name__)

# Import conditionnel des services OCR
try:
    from ...services import (
        ocr_service,
        nlp_service,
        form_parser,
        language_detector,
        order_builder,
        OCR_SERVICE_AVAILABLE
    )
    _OCR_SERVICES_AVAILABLE = True
    logger.info("✅ Tous les services OCR importés")
except ImportError as e:
    logger.warning(f"Erreur import services OCR: {e}")
    ocr_service = nlp_service = form_parser = language_detector = order_builder = None
    _OCR_SERVICES_AVAILABLE = False
    OCR_SERVICE_AVAILABLE = False

from app.core.dependencies import (
    validate_file_upload_ocr as validate_file_upload,
    cleanup_temp_file_ocr as cleanup_temp_file,
    get_document_type_ocr as get_document_type,
    require_seller_or_admin
)
from app.core.config import settings

router = APIRouter(
    prefix=getattr(settings, 'OCR_SERVICE_PREFIX', '/ocr'),
    tags=["ocr"],
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    }
)

# ==============================================
# FONCTIONS MANQUANTES À AJOUTER
# ==============================================

def detect_language_safe(text: str, fallback: str = "fr") -> str:
    """
    Détecter la langue du texte avec fallback sécurisé
    """
    if not text or len(text.strip()) < 10:
        return fallback
    
    try:
        if language_detector:
            detected = language_detector.detect(text)
            return detected if detected else fallback
        
        # Fallback simple basé sur les caractères
        french_chars = set('àâäçéèêëîïôöùûüÿæœÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸÆŒ')
        text_chars = set(text)
        
        if len(french_chars.intersection(text_chars)) > 3:
            return "fr"
        elif re.search(r'\bthe\b|\band\b|\bto\b', text, re.IGNORECASE):
            return "en"
        else:
            return fallback
            
    except Exception as e:
        logger.warning(f"Erreur détection langue: {e}")
        return fallback

def require_ocr_service():
    """
    Dépendance pour vérifier la disponibilité du service OCR
    """
    if not _OCR_SERVICES_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service OCR indisponible"
        )
    
    if not ocr_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service OCR non initialisé"
        )
    
    return True

async def generate_simple_map_png(lat: float, lon: float, title: str) -> str:
    """
    Génère une carte PNG simple pour une localisation
    """
    try:
        img_width = 600
        img_height = 400
        
        img = Image.new('RGB', (img_width, img_height), color=(240, 248, 255))
        draw = ImageDraw.Draw(img)
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 20)
            font_coords = ImageFont.truetype("arial.ttf", 14)
        except:
            font_title = ImageFont.load_default()
            font_coords = ImageFont.load_default()
        
        # Titre
        draw.text((img_width//2, 20), f"📍 {title[:40]}", 
                 fill=(25, 35, 45), font=font_title, anchor="mm")
        
        # Carte simplifiée
        center_x = img_width // 2
        center_y = img_height // 2
        
        # Cercle de la carte
        draw.ellipse([center_x-150, center_y-100, center_x+150, center_y+100],
                    fill=(173, 216, 230), outline=(70, 130, 180), width=2)
        
        # Marqueur
        draw.ellipse([center_x-10, center_y-10, center_x+10, center_y+10],
                    fill=(220, 20, 60), outline=(178, 34, 34), width=2)
        
        # Coordonnées
        coords_text = f"Lat: {lat:.6f}\nLon: {lon:.6f}"
        draw.text((img_width//2, img_height - 60), coords_text,
                 fill=(25, 35, 45), font=font_coords, anchor="mm", align="center")
        
        output_path = tempfile.NamedTemporaryFile(suffix="_simple_map.png", delete=False).name
        img.save(output_path, "PNG")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erreur génération carte simple: {e}")
        return ""

async def generate_bulk_geocode_report(results: List[Dict]) -> str:
    """
    Génère un rapport PNG pour le géocodage par lot
    """
    try:
        img_width = 1000
        img_height = 200 + (len(results) * 30)
        
        img = Image.new('RGB', (img_width, img_height), color=(245, 247, 250))
        draw = ImageDraw.Draw(img)
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 28)
            font_data = ImageFont.truetype("arial.ttf", 14)
        except:
            font_title = font_data = ImageFont.load_default()
        
        y = 30
        
        # Titre
        draw.text((img_width//2, y), "🌍 RAPPORT DE GÉOCODAGE PAR LOT", 
                 fill=(25, 35, 45), font=font_title, anchor="mm")
        y += 70
        
        # Statistiques
        successful = len([r for r in results if r.get('success', False)])
        draw.text((50, y), f"• Total adresses: {len(results)}", fill=(52, 152, 219), font=font_data)
        draw.text((50, y+25), f"• Succès: {successful}", fill=(46, 204, 113), font=font_data)
        draw.text((50, y+50), f"• Taux succès: {(successful/len(results))*100:.1f}%", 
                 fill=(155, 89, 182), font=font_data)
        
        y += 100
        
        # Résultats
        for i, result in enumerate(results):
            color = (46, 204, 113) if result.get('success') else (231, 76, 60)
            status = "✅" if result.get('success') else "❌"
            
            address_text = result['original_address'][:50] + ("..." if len(result['original_address']) > 50 else "")
            draw.text((50, y + (i*30)), f"{status} {address_text}", fill=color, font=font_data)
        
        output_path = tempfile.NamedTemporaryFile(suffix="_bulk_geocode.png", delete=False).name
        img.save(output_path, "PNG")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erreur rapport bulk géocoding: {e}")
        return None

# ==============================================
# SERVICES DE GÉOLOCALISATION
# ==============================================

class GeolocationService:
    """Service de géolocalisation des adresses"""
    
    def __init__(self):
        self.geolocator = Nominatim(user_agent="ocr_coordinates_extractor")
        self.cache = {}
        self.cache_file = "geolocation_cache.json"
        self.load_cache()
    
    def load_cache(self):
        """Charger le cache depuis le fichier"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                logger.info(f"✅ Cache géolocalisation chargé: {len(self.cache)} entrées")
        except Exception as e:
            logger.warning(f"Erreur chargement cache: {e}")
            self.cache = {}
    
    def save_cache(self):
        """Sauvegarder le cache dans un fichier"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Erreur sauvegarde cache: {e}")
    
    async def geocode_address(self, address: str) -> Optional[Dict]:
        """
        Géocoder une adresse en coordonnées GPS
        Retourne: {"latitude": float, "longitude": float, "address": str}
        """
        if not address or len(address) < 5:
            return None
        
        # Vérifier le cache
        address_key = address.lower().strip()
        if address_key in self.cache:
            logger.info(f"📌 Adresse trouvée dans le cache: {address}")
            return self.cache[address_key]
        
        try:
            # Essayer avec Nominatim
            location = await asyncio.to_thread(
                self.geolocator.geocode,
                address,
                timeout=10,
                language='fr'
            )
            
            if location:
                result = {
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "address": location.address,
                    "confidence": 0.9,
                    "source": "nominatim"
                }
                
                # Mettre en cache
                self.cache[address_key] = result
                self.save_cache()
                
                logger.info(f"📍 Adresse géocodée: {address} -> {location.latitude}, {location.longitude}")
                return result
                
        except (GeocoderTimedOut, GeocoderServiceError) as e:
            logger.warning(f"⚠️ Erreur Nominatim pour {address}: {e}")
            
            # Fallback: Essayer avec OpenStreetMap API
            try:
                result = await self._geocode_osm_fallback(address)
                if result:
                    self.cache[address_key] = result
                    self.save_cache()
                    return result
            except Exception as fallback_error:
                logger.warning(f"⚠️ Fallback OSM échoué: {fallback_error}")
        
        except Exception as e:
            logger.error(f"❌ Erreur géocodage {address}: {e}")
        
        return None
    
    async def _geocode_osm_fallback(self, address: str) -> Optional[Dict]:
        """Fallback avec OpenStreetMap API"""
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1,
                'accept-language': 'fr'
            }
            
            headers = {
                'User-Agent': 'OCR-Coordinates-Extractor/1.0'
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data:
                    result = {
                        "latitude": float(data[0]['lat']),
                        "longitude": float(data[0]['lon']),
                        "address": data[0]['display_name'],
                        "confidence": 0.7,
                        "source": "osm_api"
                    }
                    return result
        except Exception as e:
            logger.warning(f"Erreur API OSM: {e}")
        
        return None
    
    async def reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """Reverse géocoding: coordonnées -> adresse"""
        try:
            location = await asyncio.to_thread(
                self.geolocator.reverse,
                f"{lat}, {lon}",
                timeout=10,
                language='fr'
            )
            return location.address if location else None
        except Exception as e:
            logger.warning(f"Erreur reverse géocoding: {e}")
            return None
    
    async def extract_and_geocode(self, text: str, language: str = "fr") -> Dict:
        """
        Extraire les adresses du texte et les géocoder
        """
        result = {
            "addresses": [],
            "coordinates": [],
            "geocoded_count": 0,
            "total_addresses": 0
        }
        
        if not text:
            return result
        
        try:
            # Extraire les adresses avec NLP si disponible
            nlp_data = {}
            if nlp_service:
                nlp_data = nlp_service.extract_all(text, language)
            
            addresses = []
            
            # Collecter les adresses depuis différentes sources
            client_info = nlp_data.get('client', {}) if nlp_data else {}
            if client_info.get('address'):
                addresses.append(client_info['address'])
            
            # Extraire les adresses du texte avec regex
            address_patterns = [
                r'\d+\s+[A-Za-zÀ-ÿ\s]+,\s*\d{5}\s+[A-Za-zÀ-ÿ\s]+',  # Adresse française
                r'\d+\s+[A-Za-zÀ-ÿ\s]+\s+(rue|avenue|boulevard|place)\s+[A-Za-zÀ-ÿ\s]+',
                r'[A-Za-zÀ-ÿ\s]+\s+\d{5}\s+[A-Za-zÀ-ÿ\s]+'  # Ville + CP
            ]
            
            for pattern in address_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                addresses.extend(matches)
            
            # Nettoyer et dédupliquer
            addresses = list(set([addr.strip() for addr in addresses if len(addr) > 10]))
            
            result["total_addresses"] = len(addresses)
            
            # Géocoder chaque adresse
            for address in addresses:
                geo_data = await self.geocode_address(address)
                
                address_info = {
                    "original_address": address,
                    "geocoded": geo_data is not None
                }
                
                if geo_data:
                    address_info.update({
                        "latitude": geo_data["latitude"],
                        "longitude": geo_data["longitude"],
                        "formatted_address": geo_data["address"],
                        "confidence": geo_data["confidence"],
                        "source": geo_data["source"]
                    })
                    
                    result["coordinates"].append({
                        "latitude": geo_data["latitude"],
                        "longitude": geo_data["longitude"],
                        "address": address,
                        "formatted_address": geo_data["address"]
                    })
                    
                    result["geocoded_count"] += 1
                
                result["addresses"].append(address_info)
            
            logger.info(f"📍 {result['geocoded_count']}/{result['total_addresses']} adresses géocodées")
            
        except Exception as e:
            logger.error(f"❌ Erreur extraction+géocodage: {e}")
        
        return result

# Initialiser le service de géolocalisation
geolocation_service = GeolocationService()

# ==============================================
# ENDPOINTS AMÉLIORÉS AVEC GÉOLOCALISATION
# ==============================================

@router.post("/image/geolocated", response_model=StandardResponse)
async def process_image_with_geolocation(
    file: UploadFile = File(...),
    language_hint: str = Query("fr", description="Langue pour l'OCR"),
    geocode_addresses: bool = Query(True, description="Activer la géolocalisation"),
    generate_map: bool = Query(False, description="Générer une carte PNG"),
    background_tasks: BackgroundTasks = None,
    _: Any = Depends(require_ocr_service)
):
    """
    Traitement d'image avec extraction de coordonnées et géolocalisation GPS
    """
    start_time = time.time()
    document_id = str(uuid.uuid4())[:8]
    
    try:
        # 1. VALIDATION ET CAPTURE
        file_info = await validate_file_upload(file)
        temp_path = file_info["temp_path"]
        
        if background_tasks:
            background_tasks.add_task(cleanup_temp_file, temp_path)
        
        # 2. EXTRACTION OCR
        logger.info(f"🔍 Début OCR pour {file.filename}")
        
        # Vérifier que le service OCR est disponible
        if not ocr_service:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service OCR non disponible"
            )
        
        text, confidence, ocr_time = ocr_service.extract_from_image(temp_path, language_hint)
        
        if not text:
            return StandardResponse(
                success=False,
                message="Aucun texte détecté dans l'image",
                processing_time=time.time() - start_time
            )
        
        # 3. DÉTECTION LANGUE
        language = detect_language_safe(text, language_hint)
        
        # 4. EXTRACTION INTELLIGENTE DES COORDONNÉES
        nlp_data = {}
        coordinates_data = {}
        
        if nlp_service:
            nlp_data = nlp_service.extract_all(text, language)
            
            # Structure les coordonnées
            coordinates_data = {
                "client_info": nlp_data.get('client', {}),
                "contact_info": {
                    "phones": re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text),
                    "emails": re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text),
                    "urls": re.findall(r'https?://[^\s]+', text)
                },
                "raw_text_preview": text[:500] + ("..." if len(text) > 500 else "")
            }
        else:
            # Fallback si nlp_service n'est pas disponible
            coordinates_data = {
                "client_info": {},
                "contact_info": {
                    "phones": re.findall(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]', text),
                    "emails": re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text),
                    "urls": re.findall(r'https?://[^\s]+', text)
                },
                "raw_text_preview": text[:500] + ("..." if len(text) > 500 else "")
            }
        
        # 5. GÉOLOCALISATION DES ADRESSES
        geolocation_results = {}
        map_image_path = None
        
        if geocode_addresses and coordinates_data.get("client_info", {}).get("address"):
            address = coordinates_data["client_info"]["address"]
            
            # Géocoder l'adresse principale
            geo_data = await geolocation_service.geocode_address(address)
            
            if geo_data:
                coordinates_data["client_info"]["geolocation"] = {
                    "latitude": geo_data["latitude"],
                    "longitude": geo_data["longitude"],
                    "formatted_address": geo_data["address"],
                    "confidence": geo_data["confidence"],
                    "source": geo_data["source"]
                }
                
                # Générer une carte si demandé
                if generate_map:
                    map_image_path = await generate_location_map(
                        geo_data["latitude"], 
                        geo_data["longitude"],
                        coordinates_data["client_info"].get("name", "Client"),
                        document_id
                    )
            
            # Extraire et géocoder toutes les adresses du texte
            geolocation_results = await geolocation_service.extract_and_geocode(text, language)
        
        # 6. GÉNÉRATION RAPPORT VISUEL
        report_image_path = await generate_coordinates_report_png(
            coordinates_data, 
            geolocation_results,
            document_id,
            file_info["filename"]
        )
        
        total_time = time.time() - start_time
        
        # 7. PRÉPARATION RÉPONSE
        response_data = {
            "document_id": document_id,
            "filename": file_info["filename"],
            "ocr_confidence": confidence,
            "language": language,
            "coordinates_extracted": coordinates_data,
            "geolocation": geolocation_results,
            "processing_time": total_time,
            "report_available": report_image_path is not None,
            "map_available": map_image_path is not None
        }
        
        # 8. RETOUR AVEC OPTIONS DE TÉLÉCHARGEMENT
        if generate_map and map_image_path:
            return FileResponse(
                path=map_image_path,
                media_type="image/png",
                filename=f"carte_localisation_{document_id}.png",
                background=BackgroundTasks(cleanup_temp_file, map_image_path)
            )
        
        return StandardResponse(
            success=True,
            message=f"Coordonnées extraites et géolocalisées ({geolocation_results.get('geocoded_count', 0)} adresses)",
            data=response_data,
            processing_time=total_time
        )
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement avec géolocalisation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur traitement: {str(e)}"
        )

@router.post("/batch/geolocated", response_model=StandardResponse)
async def process_batch_with_geolocation(
    files: List[UploadFile] = File(...),
    language_hint: str = "fr",
    geocode_addresses: bool = True,
    background_tasks: BackgroundTasks = None,
    _: Any = Depends(require_ocr_service)
):
    """
    Traitement par lot avec géolocalisation
    """
    start_time = time.time()
    batch_id = str(uuid.uuid4())[:8]
    
    results = []
    total_geocoded = 0
    
    for file in files:
        try:
            # Traiter chaque fichier
            file_info = await validate_file_upload(file)
            temp_path = file_info["temp_path"]
            
            if background_tasks:
                background_tasks.add_task(cleanup_temp_file, temp_path)
            
            # OCR
            text, confidence, _ = ocr_service.extract_from_image(temp_path, language_hint)
            
            if text:
                # Extraction coordonnées
                language = detect_language_safe(text, language_hint)
                nlp_data = nlp_service.extract_all(text, language) if nlp_service else {}
                
                # Géolocalisation
                geolocation_data = {}
                if geocode_addresses and nlp_data.get('client', {}).get('address'):
                    address = nlp_data['client']['address']
                    geo_data = await geolocation_service.geocode_address(address)
                    
                    if geo_data:
                        geolocation_data = {
                            "address": address,
                            "latitude": geo_data["latitude"],
                            "longitude": geo_data["longitude"],
                            "confidence": geo_data["confidence"]
                        }
                        total_geocoded += 1
                
                results.append({
                    "filename": file.filename,
                    "client_name": nlp_data.get('client', {}).get('name', 'Non détecté'),
                    "address": nlp_data.get('client', {}).get('address', 'Non détectée'),
                    "geolocation": geolocation_data,
                    "ocr_confidence": confidence,
                    "success": True
                })
            else:
                results.append({
                    "filename": file.filename,
                    "success": False,
                    "error": "Aucun texte détecté"
                })
                
        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })
    
    total_time = time.time() - start_time
    
    # Générer un rapport consolidé
    report_path = await generate_batch_report_png(results, batch_id, total_geocoded)
    
    return StandardResponse(
        success=True,
        message=f"Traitement par lot terminé: {len([r for r in results if r['success']])}/{len(files)} succès, {total_geocoded} géocodés",
        data={
            "batch_id": batch_id,
            "total_files": len(files),
            "successful": len([r for r in results if r['success']]),
            "total_geocoded": total_geocoded,
            "results": results,
            "report_available": report_path is not None
        },
        processing_time=total_time
    )

@router.get("/geocode/address")
async def geocode_single_address(
    address: str = Query(..., description="Adresse à géocoder"),
    language: str = Query("fr", description="Langue pour la réponse")
):
    """
    Géocoder une adresse spécifique
    """
    try:
        geo_data = await geolocation_service.geocode_address(address)
        
        if geo_data:
            # Obtenir des informations supplémentaires
            location_info = {
                "query": address,
                "latitude": geo_data["latitude"],
                "longitude": geo_data["longitude"],
                "formatted_address": geo_data["address"],
                "confidence": geo_data["confidence"],
                "source": geo_data["source"]
            }
            
            # Générer une carte de localisation
            map_image = await generate_simple_map_png(
                geo_data["latitude"],
                geo_data["longitude"],
                address
            )
            
            return StandardResponse(
                success=True,
                message="Adresse géocodée avec succès",
                data={
                    **location_info,
                    "map_preview": map_image[:500] + "..." if len(map_image) > 500 else map_image,
                    "google_maps_url": f"https://www.google.com/maps?q={geo_data['latitude']},{geo_data['longitude']}",
                    "openstreetmap_url": f"https://www.openstreetmap.org/?mlat={geo_data['latitude']}&mlon={geo_data['longitude']}"
                }
            )
        else:
            return StandardResponse(
                success=False,
                message="Adresse non trouvée",
                data={"query": address}
            )
            
    except Exception as e:
        logger.error(f"❌ Erreur géocodage manuel: {e}")
        return StandardResponse(
            success=False,
            message=f"Erreur géocodage: {str(e)}"
        )

@router.get("/geocode/reverse")
async def reverse_geocode_coordinates(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    language: str = Query("fr", description="Langue pour la réponse")
):
    """
    Reverse géocoding: coordonnées → adresse
    """
    try:
        address = await geolocation_service.reverse_geocode(lat, lon)
        
        if address:
            return StandardResponse(
                success=True,
                message="Reverse géocoding réussi",
                data={
                    "coordinates": {"latitude": lat, "longitude": lon},
                    "address": address,
                    "google_maps_url": f"https://www.google.com/maps?q={lat},{lon}",
                    "what3words_url": f"https://what3words.com///{lat},{lon}"
                }
            )
        else:
            return StandardResponse(
                success=False,
                message="Aucune adresse trouvée pour ces coordonnées"
            )
            
    except Exception as e:
        logger.error(f"❌ Erreur reverse géocoding: {e}")
        return StandardResponse(
            success=False,
            message=f"Erreur reverse géocoding: {str(e)}"
        )

# ==============================================
# FONCTIONS DE GÉNÉRATION D'IMAGES AVEC CARTES
# ==============================================

async def generate_location_map(lat: float, lon: float, title: str, document_id: str) -> str:
    """
    Génère une carte PNG avec un marqueur à la position GPS
    """
    try:
        # Créer une image de carte simple
        img_width = 800
        img_height = 600
        
        # Créer l'image
        img = Image.new('RGB', (img_width, img_height), color=(240, 248, 255))
        draw = ImageDraw.Draw(img)
        
        # Charger une police
        try:
            font_title = ImageFont.truetype("arial.ttf", 28)
            font_coords = ImageFont.truetype("arial.ttf", 18)
        except:
            font_title = ImageFont.load_default()
            font_coords = ImageFont.load_default()
        
        # Titre
        draw.text((img_width//2, 30), f"📍 Localisation: {title}", 
                 fill=(25, 35, 45), font=font_title, anchor="mm")
        
        # Dessiner une carte simplifiée
        map_center_x = img_width // 2
        map_center_y = img_height // 2 + 50
        map_radius = 200
        
        # Cercle représentant la carte
        draw.ellipse([map_center_x-map_radius, map_center_y-map_radius,
                     map_center_x+map_radius, map_center_y+map_radius],
                    fill=(173, 216, 230), outline=(70, 130, 180), width=3)
        
        # Marqueur GPS
        marker_x = map_center_x
        marker_y = map_center_y
        
        # Dessiner le marqueur
        draw.ellipse([marker_x-15, marker_y-15, marker_x+15, marker_y+15],
                    fill=(220, 20, 60), outline=(178, 34, 34), width=2)
        
        # Ligne pointant vers le marqueur
        draw.line([marker_x, marker_y-30, marker_x, marker_y-15], 
                 fill=(220, 20, 60), width=3)
        
        # Coordonnées GPS
        coords_text = f"Lat: {lat:.6f} | Lon: {lon:.6f}"
        draw.text((img_width//2, img_height - 100), coords_text,
                 fill=(25, 35, 45), font=font_coords, anchor="mm")
        
        # Liens
        links_text = f"Google Maps: https://maps.google.com/?q={lat},{lon}"
        draw.text((20, img_height - 50), links_text,
                 fill=(52, 152, 219), font=font_coords)
        
        # Sauvegarder
        output_path = tempfile.NamedTemporaryFile(
            suffix=f"_map_{document_id}.png", 
            delete=False
        ).name
        img.save(output_path, "PNG")
        
        logger.info(f"🗺️ Carte générée: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Erreur génération carte: {e}")
        return None

async def generate_coordinates_report_png(
    coordinates_data: dict, 
    geolocation_data: dict,
    document_id: str,
    filename: str
) -> str:
    """
    Génère un rapport complet PNG avec coordonnées et géolocalisation
    """
    try:
        img_width = 1000
        img_height = 1200
        
        # Couleurs professionnelles
        bg_color = (245, 247, 250)
        header_color = (25, 35, 45)
        section_color = (52, 152, 219)
        text_color = (44, 62, 80)
        success_color = (46, 204, 113)
        warning_color = (241, 196, 15)
        
        # Créer l'image
        img = Image.new('RGB', (img_width, img_height), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Polices
        try:
            font_large = ImageFont.truetype("arial.ttf", 32)
            font_medium = ImageFont.truetype("arial.ttf", 24)
            font_small = ImageFont.truetype("arial.ttf", 18)
            font_xsmall = ImageFont.truetype("arial.ttf", 14)
        except:
            font_large = font_medium = font_small = font_xsmall = ImageFont.load_default()
        
        y_position = 30
        
        # En-tête
        draw.rectangle([0, 0, img_width, 80], fill=header_color)
        draw.text((img_width//2, 40), "📊 RAPPORT D'EXTRACTION INTELLIGENTE", 
                 fill=(255, 255, 255), font=font_large, anchor="mm")
        
        y_position = 100
        
        # Informations du document
        draw.text((50, y_position), f"📄 Document: {filename}", 
                 fill=text_color, font=font_medium)
        draw.text((50, y_position + 40), f"🆔 ID: {document_id}", 
                 fill=text_color, font=font_small)
        draw.text((50, y_position + 70), f"📅 Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 
                 fill=text_color, font=font_small)
        
        y_position += 120
        
        # Section: Coordonnées client
        draw.rectangle([30, y_position-10, 400, y_position+40], fill=section_color, outline=section_color)
        draw.text((50, y_position+15), "👤 COORDONNÉES CLIENT", 
                 fill=(255, 255, 255), font=font_medium)
        
        y_position += 60
        
        client_info = coordinates_data.get("client_info", {})
        
        info_lines = []
        if client_info.get("name"):
            info_lines.append(f"• Nom: {client_info['name']}")
        if client_info.get("address"):
            info_lines.append(f"• Adresse: {client_info['address']}")
        
        # Ajouter géolocalisation si disponible
        if client_info.get("geolocation"):
            geo = client_info["geolocation"]
            info_lines.append(f"• 📍 GPS: {geo['latitude']:.6f}, {geo['longitude']:.6f}")
            info_lines.append(f"• Confiance: {geo['confidence']:.0%}")
            info_lines.append(f"• Source: {geo['source'].upper()}")
        
        # Afficher les lignes
        for i, line in enumerate(info_lines):
            draw.text((60, y_position + (i*30)), line, 
                     fill=text_color, font=font_small)
        
        y_position += len(info_lines) * 30 + 40
        
        # Section: Contacts
        draw.rectangle([30, y_position-10, 400, y_position+40], fill=section_color, outline=section_color)
        draw.text((50, y_position+15), "📞 CONTACTS", 
                 fill=(255, 255, 255), font=font_medium)
        
        y_position += 60
        
        contact_info = coordinates_data.get("contact_info", {})
        
        if contact_info.get("phones"):
            draw.text((60, y_position), f"• Téléphones: {', '.join(contact_info['phones'][:3])}", 
                     fill=text_color, font=font_small)
            y_position += 30
        
        if contact_info.get("emails"):
            draw.text((60, y_position), f"• Emails: {', '.join(contact_info['emails'][:3])}", 
                     fill=text_color, font=font_small)
            y_position += 30
        
        y_position += 40
        
        # Section: Géolocalisation
        if geolocation_data:
            draw.rectangle([30, y_position-10, 400, y_position+40], fill=success_color, outline=success_color)
            draw.text((50, y_position+15), "🗺️ GÉOLOCALISATION", 
                     fill=(255, 255, 255), font=font_medium)
            
            y_position += 60
            
            stats_text = [
                f"• Adresses trouvées: {geolocation_data.get('total_addresses', 0)}",
                f"• Géocodées: {geolocation_data.get('geocoded_count', 0)}",
                f"• Taux succès: {(geolocation_data.get('geocoded_count', 0)/max(geolocation_data.get('total_addresses', 1), 1))*100:.1f}%"
            ]
            
            for i, text in enumerate(stats_text):
                draw.text((60, y_position + (i*30)), text, 
                         fill=text_color, font=font_small)
            
            y_position += len(stats_text) * 30 + 30
            
            # Afficher les coordonnées géocodées
            coordinates = geolocation_data.get('coordinates', [])[:3]
            if coordinates:
                draw.text((60, y_position), "📍 Coordonnées GPS:", 
                         fill=text_color, font=font_small)
                y_position += 30
                
                for i, coord in enumerate(coordinates):
                    coord_text = f"  {i+1}. {coord['latitude']:.4f}, {coord['longitude']:.4f}"
                    draw.text((80, y_position + (i*25)), coord_text, 
                             fill=text_color, font=font_xsmall)
        
        # QR Code pour Google Maps (optionnel)
        if client_info.get("geolocation"):
            y_position = img_height - 150
            draw.text((img_width//2, y_position), "📱 Scanner pour Google Maps", 
                     fill=section_color, font=font_small, anchor="mm")
            
            # Générer un QR code simple (texte)
            maps_url = f"https://maps.google.com/?q={client_info['geolocation']['latitude']},{client_info['geolocation']['longitude']}"
            draw.text((img_width//2, y_position + 30), maps_url[:50] + "...", 
                     fill=(52, 152, 219), font=font_xsmall, anchor="mm")
        
        # Pied de page
        draw.rectangle([0, img_height-40, img_width, img_height], fill=header_color)
        draw.text((img_width//2, img_height-20), "Système d'Extraction Intelligente de Coordonnées © 2024", 
                 fill=(255, 255, 255), font=font_xsmall, anchor="mm")
        
        # Sauvegarder
        output_path = tempfile.NamedTemporaryFile(
            suffix=f"_report_{document_id}.png", 
            delete=False
        ).name
        img.save(output_path, "PNG", quality=95)
        
        logger.info(f"📋 Rapport généré: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Erreur génération rapport: {e}")
        return None

async def generate_batch_report_png(results: List[Dict], batch_id: str, total_geocoded: int) -> str:
    """
    Génère un rapport PNG pour le traitement par lot
    """
    try:
        img_width = 1200
        img_height = 800 + (len(results) * 40)
        
        # Créer l'image
        img = Image.new('RGB', (img_width, img_height), color=(245, 247, 250))
        draw = ImageDraw.Draw(img)
        
        # Polices
        try:
            font_title = ImageFont.truetype("arial.ttf", 36)
            font_header = ImageFont.truetype("arial.ttf", 24)
            font_data = ImageFont.truetype("arial.ttf", 16)
        except:
            font_title = font_header = font_data = ImageFont.load_default()
        
        y = 30
        
        # Titre
        draw.text((img_width//2, y), "📦 RAPPORT DE TRAITEMENT PAR LOT", 
                 fill=(25, 35, 45), font=font_title, anchor="mm")
        y += 60
        
        # Résumé
        successful = len([r for r in results if r.get('success', False)])
        draw.text((50, y), f"• Fichiers traités: {len(results)}", 
                 fill=(52, 152, 219), font=font_header)
        draw.text((50, y+40), f"• Succès: {successful}", 
                 fill=(46, 204, 113), font=font_header)
        draw.text((50, y+80), f"• Géolocalisés: {total_geocoded}", 
                 fill=(155, 89, 182), font=font_header)
        
        y += 140
        
        # Tableau des résultats
        headers = ["Fichier", "Client", "Adresse", "GPS", "Statut"]
        col_widths = [300, 250, 350, 150, 150]
        
        # En-tête du tableau
        x = 50
        for i, header in enumerate(headers):
            draw.rectangle([x, y, x+col_widths[i], y+50], fill=(25, 35, 45))
            draw.text((x+10, y+25), header, fill=(255, 255, 255), font=font_header)
            x += col_widths[i]
        
        y += 60
        
        # Données
        for result in results:
            x = 50
            
            # Fichier
            draw.text((x+10, y+20), result['filename'][:30], 
                     fill=(44, 62, 80), font=font_data)
            x += col_widths[0]
            
            # Client
            draw.text((x+10, y+20), result.get('client_name', 'N/A')[:20], 
                     fill=(44, 62, 80), font=font_data)
            x += col_widths[1]
            
            # Adresse
            draw.text((x+10, y+20), result.get('address', 'N/A')[:25], 
                     fill=(44, 62, 80), font=font_data)
            x += col_widths[2]
            
            # GPS
            if result.get('geolocation'):
                gps_text = f"{result['geolocation']['latitude']:.4f}, {result['geolocation']['longitude']:.4f}"
                draw.text((x+10, y+20), gps_text, 
                         fill=(46, 204, 113), font=font_data)
            else:
                draw.text((x+10, y+20), "Non géocodé", 
                         fill=(231, 76, 60), font=font_data)
            x += col_widths[3]
            
            # Statut
            status_color = (46, 204, 113) if result.get('success') else (231, 76, 60)
            status_text = "✅ Succès" if result.get('success') else "❌ Échec"
            draw.text((x+10, y+20), status_text, 
                     fill=status_color, font=font_data)
            
            y += 40
        
        # Sauvegarder
        output_path = tempfile.NamedTemporaryFile(
            suffix=f"_batch_{batch_id}.png", 
            delete=False
        ).name
        img.save(output_path, "PNG")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Erreur rapport batch: {e}")
        return None

# ==============================================
# AUTRES ENDPOINTS AMÉLIORÉS
# ==============================================

@router.post("/image")
async def process_image_enhanced(
    file: UploadFile = File(...),
    language_hint: str = "fr",
    geocode: bool = True,
    generate_report: bool = True,
    background_tasks: BackgroundTasks = None,
    _: Any = Depends(require_ocr_service)
):
    """
    Version améliorée avec géolocalisation optionnelle
    """
    # Appelle la fonction principale avec géolocalisation
    return await process_image_with_geolocation(
        file=file,
        language_hint=language_hint,
        geocode_addresses=geocode,
        generate_map=False,
        background_tasks=background_tasks,
        _=True  # Pass the dependency result
    )

@router.get("/stats/geolocation")
async def get_geolocation_stats():
    """
    Statistiques de géolocalisation
    """
    return StandardResponse(
        success=True,
        message="Statistiques de géolocalisation",
        data={
            "cache_size": len(geolocation_service.cache),
            "service": "Nominatim/OpenStreetMap",
            "cache_file": geolocation_service.cache_file,
            "user_agent": "ocr_coordinates_extractor"
        }
    )

@router.post("/addresses/bulk-geocode")
async def bulk_geocode_addresses(
    addresses: List[str],
    background_tasks: BackgroundTasks = None
):
    """
    Géocoder plusieurs adresses en une seule requête
    """
    start_time = time.time()
    
    results = []
    successful = 0
    
    for address in addresses:
        try:
            geo_data = await geolocation_service.geocode_address(address)
            
            if geo_data:
                results.append({
                    "original_address": address,
                    "latitude": geo_data["latitude"],
                    "longitude": geo_data["longitude"],
                    "formatted_address": geo_data["address"],
                    "confidence": geo_data["confidence"],
                    "success": True
                })
                successful += 1
            else:
                results.append({
                    "original_address": address,
                    "success": False,
                    "error": "Adresse non trouvée"
                })
                
        except Exception as e:
            results.append({
                "original_address": address,
                "success": False,
                "error": str(e)
            })
    
    # Générer un rapport
    report_path = await generate_bulk_geocode_report(results)
    
    total_time = time.time() - start_time
    
    return StandardResponse(
        success=True,
        message=f"Géocodage par lot: {successful}/{len(addresses)} succès",
        data={
            "total_addresses": len(addresses),
            "successful_geocodes": successful,
            "success_rate": f"{(successful/len(addresses))*100:.1f}%",
            "results": results,
            "report_available": report_path is not None
        },
        processing_time=total_time
    )

# ==============================================
# FONCTION DE NETTOYAGE AMÉLIORÉE
# ==============================================

async def cleanup_geolocation_files(file_path: str):
    """
    Nettoyer les fichiers temporaires de géolocalisation
    """
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug(f"🧹 Fichier nettoyé: {file_path}")
    except Exception as e:
        logger.warning(f"⚠️ Erreur nettoyage {file_path}: {e}")

# ==============================================
# MIDDLEWARE POUR LOGS DE GÉOLOCALISATION
# ==============================================

@router.middleware("http")
async def log_geolocation_requests(request, call_next):
    """
    Middleware pour logger les requêtes de géolocalisation
    """
    if "geocode" in request.url.path:
        logger.info(f"🌍 Requête géolocalisation: {request.method} {request.url.path}")
    
    response = await call_next(request)
    return response