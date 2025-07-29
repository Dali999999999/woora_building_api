
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
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer or customer.role != 'customer':
        return jsonify({'message': "Accès refusé. Seuls les clients peuvent faire des demandes de visite."}), 403

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

    # Vérification du code de parrainage
    referral_id = None
    if referral_code:
        referral = Referral.query.filter_by(referral_code=referral_code).first()
        if not referral:
            return jsonify({'message': "Code de parrainage invalide."}), 400 # Rejeter si code invalide
        referral_id = referral.id

    # Vérification des pass de visite
    if customer.visit_passes <= 0:
        return jsonify({'message': "Vous n'avez plus de pass de visite disponibles. Veuillez en acheter pour continuer."}), 402 # 402 Payment Required

    # Décrémenter le pass de visite
    customer.visit_passes -= 1
    db.session.add(customer)

    # Créer la nouvelle demande de visite
    new_visit_request = VisitRequest(
        customer_id=current_user_id,
        property_id=property_id,
        requested_datetime=requested_datetime,
        message=message,
        referral_id=referral_id # Ajout du referral_id
    )

    try:
        db.session.add(new_visit_request)
        db.session.commit()

        # Envoyer la notification à l'administrateur
        admin_users = User.query.filter_by(role='admin').all()
        if admin_users:
            # Pour l'exemple, on envoie au premier admin trouvé. En production, gérer plusieurs admins.
            admin_email = admin_users[0].email 
            property_obj = Property.query.get(property_id)
            send_new_visit_request_notification(
                admin_email,
                f'{customer.first_name} {customer.last_name}',
                property_obj.title,
                requested_datetime.strftime('%Y-%m-%d %H:%M'),
                message
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
