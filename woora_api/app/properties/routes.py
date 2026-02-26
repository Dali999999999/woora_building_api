from flask import Blueprint, jsonify, current_app
from sqlalchemy import inspect
from app.models import Property, PropertyStatus
from app import db

properties_bp = Blueprint('properties', __name__, url_prefix='/properties')

# ===================================================================
# PUBLIC ENDPOINT POUR RÉCUPÉRER LES STATUTS DE PROPRIÉTÉ (MOBILE)
# ===================================================================

@properties_bp.route('/statuses', methods=['GET'])
def get_property_statuses():
    """
    Récupère la liste de tous les statuts de propriété disponibles.
    Endpoint public accessible par les apps mobiles.
    """
    try:
        statuses = PropertyStatus.query.all()
        return jsonify([s.to_dict() for s in statuses]), 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des statuts: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

@properties_bp.route('/share/<string:share_uid>', methods=['GET'])
def resolve_share_link(share_uid):
    """
    Endpoint public permettant aux App Links (Android/iOS) ou au Web
    de retrouver l'ID interne réel du bien immobilier à partir de son UUID public (share_uid).
    """
    try:
        property_obj = db.session.query(Property.id).filter_by(share_uid=share_uid).first()
        if not property_obj:
            return jsonify({'message': 'Lien de partage introuvable ou invalide.'}), 404
            
        return jsonify({'property_id': property_obj.id}), 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la résolution du share_uid {share_uid}: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

