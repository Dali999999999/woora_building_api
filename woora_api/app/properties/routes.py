from flask import Blueprint, jsonify, current_app
from sqlalchemy import inspect
from app.models import Property
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
        # Récupérer les valeurs ENUM depuis la colonne status
        inspector = inspect(db.engine)
        columns = inspector.get_columns('properties')
        status_column = next((col for col in columns if col['name'] == 'status'), None)
        
        if status_column and hasattr(status_column['type'], 'enums'):
            enum_values = status_column['type'].enums
        else:
            # Fallback
            enum_values = ['for_sale', 'for_rent', 'sold', 'rented', 'vefa', 'bailler', 'location_vente']
        
        # Mapper les valeurs avec leurs labels français
        status_mapping = {
            'for_sale': 'À Vendre',
            'for_rent': 'À Louer',
            'vefa': 'VEFA',
            'bailler': 'Bailler',
            'location_vente': 'Location-vente',
            'sold': 'Vendu',
            'rented': 'Loué'
        }
        
        statuses = [
            {'value': value, 'label': status_mapping.get(value, value.capitalize())}
            for value in enum_values
        ]
        
        return jsonify(statuses), 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des statuts: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500
