# app/seekers/routes.py

from flask import Blueprint, jsonify
from app.models import Property, User
from flask_jwt_extended import jwt_required, get_jwt_identity

# On crée un nouveau "blueprint" pour les chercheurs de biens
seekers_bp = Blueprint('seekers', __name__, url_prefix='/seekers')

@seekers_bp.route('/properties', methods=['GET'])
@jwt_required() # On s'assure que l'utilisateur est connecté, peu importe son rôle
def get_all_properties_for_seeker():
    """
    Endpoint pour les chercheurs.
    Récupère tous les biens immobiliers.
    Accessible par n'importe quel utilisateur authentifié.
    """
    # Pas besoin de vérifier le rôle ici, car tout utilisateur connecté peut rechercher.
    
    properties = Property.query.all()
    
    # On utilise la méthode to_dict() qui est déjà complète et cohérente
    return jsonify([p.to_dict() for p in properties]), 200


@seekers_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required() # On s'assure que l'utilisateur est connecté
def get_property_details_for_seeker(property_id):
    """
    Endpoint pour les chercheurs.
    Récupère les détails d'un bien immobilier spécifique.
    """
    property = Property.query.get(property_id)
    
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    return jsonify(property.to_dict()), 200
