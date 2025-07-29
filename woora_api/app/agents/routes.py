from flask import Blueprint, jsonify, current_app
from app.models import Property, User, Referral # On ajoute Referral ici
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.helpers import generate_unique_referral_code 
from app import db

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

@agents_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_property_details_for_agent(property_id):
    """
    Endpoint pour les agents.
    Récupère les détails d'un bien immobilier spécifique par son ID.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    
    # Sécurité : Vérifier que l'utilisateur est bien un agent
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé."}), 403

    # On récupère le bien par son ID, sans vérifier le propriétaire
    property = Property.query.get(property_id)
    
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    # On utilise la méthode to_dict() pour une réponse cohérente
    return jsonify(property.to_dict()), 200

@agents_bp.route('/properties/<int:property_id>/referrals', methods=['POST'])
@jwt_required()
def create_or_get_referral_code(property_id):
    """
    Crée un code de parrainage pour un agent et un bien, ou le récupère s'il existe déjà.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé. Seuls les agents peuvent créer des codes."}), 403

    # Vérifier que le bien existe
    property_obj = Property.query.get(property_id)
    if not property_obj:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    # Vérifier si un code existe déjà pour cet agent et ce bien
    existing_referral = Referral.query.filter_by(
        agent_id=current_user_id,
        property_id=property_id
    ).first()

    if existing_referral:
        # Si le code existe, on le renvoie simplement
        return jsonify({
            'message': "Code de parrainage existant récupéré.",
            'referral_code': existing_referral.referral_code
        }), 200

    # Si aucun code n'existe, on en crée un nouveau
    new_code = generate_unique_referral_code()
    
    new_referral = Referral(
        agent_id=current_user_id,
        property_id=property_id,
        referral_code=new_code
    )

    try:
        db.session.add(new_referral)
        db.session.commit()
        return jsonify({
            'message': "Code de parrainage créé avec succès.",
            'referral_code': new_code
        }), 201 # 201 Created
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création du code de parrainage: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500

@agents_bp.route('/referrals', methods=['GET'])
@jwt_required()
def get_agent_referrals_with_details():
    """
    Récupère tous les codes de parrainage de l'agent connecté, avec les détails
    du bien associé et la liste des clients ayant utilisé chaque code.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé."}), 403

    # On récupère tous les parrainages de l'agent
    referrals = Referral.query.filter_by(agent_id=current_user_id).all()
    
    response_data = []
    for referral in referrals:
        # Pour chaque parrainage, on construit un dictionnaire détaillé
        
        # On récupère les clients qui ont utilisé ce code
        customers_who_used_code = []
        for visit in referral.visit_requests: # Grâce à la relation ajoutée dans le modèle
            customer = visit.customer
            if customer:
                customers_who_used_code.append({
                    'full_name': f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                })

        response_data.append({
            'id': referral.id,
            'referral_code': referral.referral_code,
            'property_id': referral.property_id,
            'property_title': referral.property.title if referral.property else "Bien supprimé",
            'customers': customers_who_used_code
        })

    return jsonify(response_data), 200
