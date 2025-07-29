
# app/seekers/routes.py

from flask import Blueprint, request, jsonify, current_app
from app.models import Property, User, VisitRequest, Referral, db
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.utils.email_utils import send_new_visit_request_notification

seekers_bp = Blueprint('seekers', __name__, url_prefix='/seekers')

@seekers_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_seeker():
    properties = Property.query.all()
    return jsonify([p.to_dict() for p in properties]), 200

@seekers_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_property_details_for_seeker(property_id):
    property = Property.query.get(property_id)
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404
    return jsonify(property.to_dict()), 200

@seekers_bp.route('/properties/<int:property_id>/visit-requests', methods=['POST'])
@jwt_required()
def create_visit_request(property_id):
    """
    Permet à un client de soumettre une demande de visite.
    Décrémente toujours un pass de visite.
    Si un code de parrainage est utilisé, il lie la demande à l'agent et le notifie.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    # Note: Votre modèle User utilise 'customer', assurez-vous que c'est bien le rôle des chercheurs.
    # Si c'est 'seeker', changez la condition ici.
    if not customer or customer.role != 'customer':
        return jsonify({'message': "Accès refusé. Seuls les clients peuvent faire des demandes de visite."}), 403

    # Vérification que le bien existe
    property_obj = Property.query.get(property_id)
    if not property_obj:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    data = request.get_json()
    if not data:
        return jsonify({'message': "Données manquantes."}), 400

    requested_datetime_str = data.get('requested_datetime')
    referral_code = data.get('referral_code')
    message = data.get('message')

    if not requested_datetime_str:
        return jsonify({'message': "La date et l'heure de la visite sont requises."}), 400

    try:
        requested_datetime = datetime.fromisoformat(requested_datetime_str)
    except ValueError:
        return jsonify({'message': "Format de date invalide. Utilisez le format ISO 8601."}), 400

    # Étape 1 : Vérification OBLIGATOIRE des pass de visite
    if customer.visit_passes <= 0:
        return jsonify({'message': "Vous n'avez plus de pass de visite disponibles. Veuillez en acheter pour continuer."}), 402 # 402 Payment Required

    # Étape 2 : Vérification du code de parrainage (si fourni)
    referral_id = None
    agent_to_notify = None
    if referral_code:
        # On vérifie que le code est valide POUR CE BIEN PRÉCIS
        referral = Referral.query.filter_by(
            referral_code=referral_code,
            property_id=property_id
        ).first()
        
        if not referral:
            return jsonify({'message': "Code de parrainage invalide ou non applicable pour ce bien."}), 400
        
        referral_id = referral.id
        agent_to_notify = referral.agent # On récupère l'objet agent pour la notification

    # Étape 3 : Création de la demande et décrémentation du pass
    
    # Décrémenter le pass de visite
    customer.visit_passes -= 1

    # Créer la nouvelle demande de visite
    new_visit_request = VisitRequest(
        customer_id=current_user_id,
        property_id=property_id,
        requested_datetime=requested_datetime,
        message=message,
        referral_id=referral_id # Ajout du referral_id (sera None s'il n'y a pas de code)
    )

    try:
        db.session.add(customer) # Ajoute la modification du nombre de pass
        db.session.add(new_visit_request)
        db.session.commit()

        # Étape 4 : Notifications
        
        # 4.1 Notifier l'administrateur (logique existante)
        admin_users = User.query.filter_by(role='admin').all()
        if admin_users:
            admin_email = admin_users[0].email 
            send_new_visit_request_notification(
                admin_email,
                f'{customer.first_name} {customer.last_name}',
                property_obj.title,
                requested_datetime.strftime('%d/%m/%Y à %Hh%M'),
                message
            )

        # 4.2 Notifier l'agent si son code a été utilisé
        if agent_to_notify:
            send_referral_used_notification(
                agent_email=agent_to_notify.email,
                customer_name=f'{customer.first_name} {customer.last_name}',
                property_title=property_obj.title
            )

        return jsonify({'message': "Votre demande de visite a été envoyée avec succès et un pass a été utilisé."}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création de la demande de visite: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500

@seekers_bp.route('/visit_requests', methods=['GET'])
@jwt_required()
def get_customer_visit_requests():
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer or customer.role != 'customer':
        return jsonify({'message': 'Accès refusé. Seuls les clients peuvent voir leurs demandes de visite.'}), 403

    status_filter = request.args.get('status')
    query = VisitRequest.query.filter_by(customer_id=current_user_id)

    if status_filter:
        query = query.filter_by(status=status_filter)
    
    visit_requests = query.all()
    result = []
    for req in visit_requests:
        property_obj = Property.query.get(req.property_id)
        req_dict = {
            'id': req.id,
            'property_id': req.property_id,
            'property_title': property_obj.title if property_obj else 'N/A',
            'requested_datetime': req.requested_datetime.isoformat(),
            'status': req.status,
            'message': req.message,
            'created_at': req.created_at.isoformat()
        }
        result.append(req_dict)
    return jsonify(result), 200
