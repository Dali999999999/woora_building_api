
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

@seekers_bp.route('/properties/<int:property_id>/visit-requests', methods=['POST'])
@jwt_required()
def create_visit_request(property_id):
    """
    Permet à un utilisateur authentifié (seeker) de soumettre une demande de visite
    pour une propriété spécifique.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    # On pourrait vérifier le rôle, mais logiquement, n'importe qui peut demander une visite.
    if not user:
        return jsonify({'message': "Utilisateur non trouvé."}), 404

    data = request.get_json()
    if not data:
        return jsonify({'message': "Données manquantes."}), 400

    requested_datetime_str = data.get('requested_datetime')
    referral_code = data.get('referral_code') # Optionnel
    message = data.get('message') # Optionnel

    if not requested_datetime_str:
        return jsonify({'message': "La date et l'heure de la visite sont requises."}), 400

    try:
        # Convertir la chaîne de caractères ISO 8601 en objet datetime
        requested_datetime = datetime.fromisoformat(requested_datetime_str)
    except ValueError:
        return jsonify({'message': "Format de date invalide. Utilisez le format ISO 8601."}), 400

    # Créer la nouvelle demande de visite
    new_visit_request = VisitRequest(
        customer_id=current_user_id,
        property_id=property_id,
        requested_datetime=requested_datetime,
        message=message
        # Le statut est 'pending' par défaut dans le modèle
    )
    
    # On pourrait ajouter ici la logique de validation du code de parrainage plus tard
    
    try:
        db.session.add(new_visit_request)
        db.session.commit()
        return jsonify({'message': "Votre demande de visite a été envoyée avec succès."}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création de la demande de visite: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500
