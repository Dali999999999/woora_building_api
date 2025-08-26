# app/search/routes.py

from flask import Blueprint, jsonify
from app.models import Property

# On crée un nouveau "blueprint" pour les recherches publiques
search_bp = Blueprint('search', __name__, url_prefix='/search')

@search_bp.route('/property-by-id/<int:property_id>', methods=['GET'])
def get_property_by_id(property_id):
    """
    Recherche un bien immobilier par son ID numérique.
    Ne retourne que les biens qui sont visibles publiquement ('for_sale' ou 'for_rent').
    """
    # On cherche le bien par sa clé primaire, c'est très rapide.
    property_obj = Property.query.get(property_id)

    # Vérification 1: Le bien existe-t-il ?
    if not property_obj:
        return jsonify({'message': "Aucun bien immobilier ne correspond à cet identifiant."}), 404

    # Vérification 2: Le bien est-il accessible au public ?
    # On ne veut pas que les gens trouvent des biens déjà vendus ou loués via cette recherche.
    if property_obj.status not in ['for_sale', 'for_rent']:
        return jsonify({'message': "Ce bien n'est plus disponible à la vente ou à la location."}), 404
        
    # Si tout est bon, on retourne les données du bien
    return jsonify(property_obj.to_dict()), 200
