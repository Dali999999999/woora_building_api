"""
Service de géocodage utilisant Nominatim (OpenStreetMap)
pour l'autocomplétion d'adresses et le géocodage inversé.
"""
import requests
from flask import current_app

NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
USER_AGENT = "WooraBuilding/1.0"


def autocomplete_address(query, country_code='SN', limit=10):
    """
    Autocomplète une adresse via l'API Nominatim OpenStreetMap.
    
    Args:
        query (str): Texte de recherche
        country_code (str): Code pays ISO (SN pour Sénégal)
        limit (int): Nombre maximum de résultats
        
    Returns:
        list: Liste de suggestions avec nom, lat, lon, type
    """
    if not query or len(query) < 2:
        return []

    try:
        params = {
            'q': query,
            'countrycodes': country_code, # Réactivé pour restreindre la recherche au pays spécifié
            'format': 'json',
            'addressdetails': 1,
            'limit': limit,
            'accept-language': 'fr',  # Résultats en français
        }
        
        headers = {'User-Agent': USER_AGENT}
        
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/search",
            params=params,
            headers=headers,
            timeout=5
        )
        
        if response.status_code != 200:
            current_app.logger.error(f"Nominatim API error: {response.status_code}")
            return []
        
        data = response.json()
        
        # Formater les résultats
        results = []
        for item in data:
            address = item.get('address', {})
            
            # Construire un nom lisible et court
            # Ex: "Mermoz, Dakar" ou "Porto-Novo, Ouémé"
            parts = []
            
            # 1. Le lieu précis (route, quartier, etc.)
            road = address.get('road') or address.get('pedestrian')
            suburb = address.get('suburb') or address.get('neighbourhood') or address.get('district')
            
            if road: parts.append(road)
            if suburb: parts.append(suburb)
            
            # 2. La ville ou localité importante
            city = address.get('city') or address.get('town') or address.get('village') or address.get('county')
            if city and city not in parts:
                parts.append(city)
                
            # 3. La région/état (sauf si c'est déjà la ville, ex: Dakar)
            state = address.get('state')
            if state and state != city and state not in parts:
                parts.append(state)
            
            # Note: On NE met PAS le pays car il est déjà sélectionné par l'utilisateur
            
            # Fallback si vide
            clean_display_name = ", ".join(parts)
            if not clean_display_name:
                clean_display_name = item.get('display_name', '')

            results.append({
                'display_name': clean_display_name,
                'raw_display_name': item.get('display_name', ''), # Garder l'original au cas où
                'city': city,
                'suburb': suburb,
                'state': state,
                'country': country,
                'latitude': float(item['lat']),
                'longitude': float(item['lon']),
                'type': place_type,
                'osm_id': item.get('osm_id'),
            })
        
        return results
        
    except requests.RequestException as e:
        current_app.logger.error(f"Nominatim request failed: {e}")
        return []
    except Exception as e:
        current_app.logger.error(f"Geocoding error: {e}")
        return []


def reverse_geocode(latitude, longitude):
    """
    Géocodage inversé : coordonnées → adresse.
    
    Args:
        latitude (float): Latitude
        longitude (float): Longitude
        
    Returns:
        dict: Informations d'adresse ou None si erreur
    """
    try:
        params = {
            'lat': latitude,
            'lon': longitude,
            'format': 'json',
            'addressdetails': 1,
            'accept-language': 'fr',
        }
        
        headers = {'User-Agent': USER_AGENT}
        
        response = requests.get(
            f"{NOMINATIM_BASE_URL}/reverse",
            params=params,
            headers=headers,
            timeout=5
        )
        
        if response.status_code != 200:
            current_app.logger.error(f"Reverse geocode error: {response.status_code}")
            return None
        
        data = response.json()
        address = data.get('address', {})
        
        return {
            'display_name': data.get('display_name', ''),
            'city': address.get('city') or address.get('town') or address.get('village'),
            'suburb': address.get('suburb') or address.get('neighbourhood'),
            'state': address.get('state'),
            'country': address.get('country'),
            'postcode': address.get('postcode'),
            'road': address.get('road'),
            'latitude': latitude,
            'longitude': longitude,
        }
        
    except requests.RequestException as e:
        current_app.logger.error(f"Reverse geocode request failed: {e}")
        return None
    except Exception as e:
        current_app.logger.error(f"Reverse geocode error: {e}")
        return None
