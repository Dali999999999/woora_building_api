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
