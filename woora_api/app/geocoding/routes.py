"""
Routes pour le géocodage et l'autocomplétion d'adresses.
"""
from flask import Blueprint, request, jsonify
from . import services as geocoding_services

geocoding_bp = Blueprint('geocoding', __name__, url_prefix='/geocoding')


@geocoding_bp.route('/autocomplete', methods=['GET'])
def autocomplete_address():
    """
    Autocomplétion d'adresse.
    
    Query params:
        - q: Terme de recherche (requis)
        - country: Code pays (optionnel, défaut: BJ)
        - limit: Nombre de résultats (optionnel, défaut: 5)
        
    Returns:
        JSON: Liste de suggestions
    """
    query = request.args.get('q', '').strip()
    country_code = request.args.get('country', 'BJ').upper()
    limit = request.args.get('limit', 5, type=int)
    
    if not query:
        return jsonify({'message': 'Le paramètre "q" est requis.'}), 400
    
    if limit > 10:
        limit = 10  # Limite max pour éviter l'abus
    
    try:
        results = geocoding_services.autocomplete_address(
            query=query,
            country_code=country_code,
            limit=limit
        )
        
        return jsonify({
            'results': results,
            'count': len(results)
        }), 200
        
    except Exception as e:
        return jsonify({
            'message': 'Erreur lors de la recherche d\'adresse.',
            'error': str(e)
        }), 500


@geocoding_bp.route('/reverse', methods=['GET'])
def reverse_geocode():
    """
    Géocodage inversé (coordonnées → adresse).
    
    Query params:
        - lat: Latitude (requis)
        - lon: Longitude (requis)
        
    Returns:
        JSON: Informations d'adresse
    """
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
    except (ValueError, TypeError):
        return jsonify({
            'message': 'Les paramètres "lat" et "lon" doivent être des nombres.'
        }), 400
    
    if lat is None or lon is None:
        return jsonify({
            'message': 'Les paramètres "lat" et "lon" sont requis.'
        }), 400
    
    # Validation basique des coordonnées
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return jsonify({
            'message': 'Coordonnées invalides.'
        }), 400
    
    try:
        result = geocoding_services.reverse_geocode(latitude=lat, longitude=lon)
        
        if result is None:
            return jsonify({
                'message': 'Aucune adresse trouvée pour ces coordonnées.'
            }), 404
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({
            'message': 'Erreur lors du géocodage inversé.',
            'error': str(e)
        }), 500
