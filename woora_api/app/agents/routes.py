from flask import Blueprint, jsonify, current_app
from app.models import Property, User
from flask_jwt_extended import jwt_required, get_jwt_identity

# On crée un nouveau "blueprint" spécifiquement pour les agents
agents_bp = Blueprint('agents', __name__, url_prefix='/agents')

@agents_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_agent():
    """
    Endpoint pour les agents.
    Récupère tous les biens immobiliers publiés par les propriétaires.
    À l'avenir, on pourrait ajouter un filtre, par exemple, pour ne montrer que les biens validés.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    
    # Étape de sécurité : on vérifie que l'utilisateur est bien un agent
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé. Seuleument les agents peuvent accéder à cette ressource."}), 403

    # On récupère tous les biens.
    # Pour une application en production, on filtrerait sûrement par `is_validated=True`
    properties = Property.query.all()
    
    # On utilise la méthode to_dict() qui est déjà complète et cohérente
    return jsonify([p.to_dict() for p in properties]), 200
