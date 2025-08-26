# app/favorites/routes.py

from flask import Blueprint, jsonify
from app import db
from app.models import User, Property, UserFavorite
from flask_jwt_extended import jwt_required, get_jwt_identity

# On crée un nouveau "blueprint" pour la logique des favoris
favorites_bp = Blueprint('favorites', __name__, url_prefix='/favorites')

@favorites_bp.route('/<int:property_id>', methods=['POST'])
@jwt_required()
def toggle_favorite(property_id):
    """
    Ajoute ou retire un bien immobilier des favoris de l'utilisateur.
    C'est une route "toggle" : si le bien est en favori, il est retiré.
    Sinon, il est ajouté.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    # Les clients et les agents peuvent avoir des favoris
    if not user or user.role not in ['customer', 'agent']:
        return jsonify({'message': "Accès non autorisé."}), 403

    property_obj = Property.query.get(property_id)
    if not property_obj:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    # Chercher si le favori existe déjà
    existing_favorite = UserFavorite.query.filter_by(
        user_id=current_user_id,
        property_id=property_id
    ).first()

    try:
        if existing_favorite:
            # Si ça existe, on le supprime
            db.session.delete(existing_favorite)
            db.session.commit()
            return jsonify({'message': "Bien retiré des favoris avec succès."}), 200
        else:
            # Sinon, on le crée
            new_favorite = UserFavorite(user_id=current_user_id, property_id=property_id)
            db.session.add(new_favorite)
            db.session.commit()
            return jsonify({'message': "Bien ajouté aux favoris avec succès."}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la gestion du favori: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500


@favorites_bp.route('/', methods=['GET'])
@jwt_required()
def get_user_favorites():
    """
    Récupère la liste de tous les biens immobiliers mis en favori
    par l'utilisateur actuellement connecté.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)

    if not user or user.role not in ['customer', 'agent']:
        return jsonify({'message': "Accès non autorisé."}), 403

    # On utilise une jointure pour récupérer directement les objets Property
    # C'est plus efficace que de récupérer les IDs puis de faire une autre requête
    favorite_properties = Property.query.join(
        UserFavorite, UserFavorite.property_id == Property.id
    ).filter(
        UserFavorite.user_id == current_user_id
    ).all()

    return jsonify([p.to_dict() for p in favorite_properties]), 200
