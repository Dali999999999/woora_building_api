# app/seekers/routes.py

from flask import Blueprint, request, jsonify, current_app
from app.models import Property, User, VisitRequest, Referral, PropertyRequest
from app import db # Assurez-vous que l'import de 'db' est correct
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.models import ServiceFee

# Assurez-vous que le chemin vers vos utilitaires d'email est correct
try:
    from app.utils.email_utils import send_new_visit_request_notification, send_referral_used_notification
except ImportError:
    # Crée des fonctions factices si le fichier n'existe pas encore pour éviter une erreur d'import
    def send_new_visit_request_notification(*args, **kwargs): pass
    def send_referral_used_notification(*args, **kwargs): pass


seekers_bp = Blueprint('seekers', __name__, url_prefix='/seekers')

@seekers_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_seeker():
    """
    Endpoint pour les chercheurs.
    Récupère TOUS les biens immobiliers qui sont actuellement 'à vendre' ou 'à louer'.
    """
    # Pas besoin de vérifier le rôle ici
    
    # --- DÉBUT DE LA CORRECTION ---
    # On applique exactement le même filtre que pour les agents.
    properties = Property.query.filter(
        Property.status.in_(['for_sale', 'for_rent'])
    ).all()
    # --- FIN DE LA CORRECTION ---

    return jsonify([p.to_dict() for p in properties]), 200

@seekers_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_property_details_for_seeker(property_id):
    """
    Récupère les détails d'un bien immobilier spécifique.
    """
    property_obj = Property.query.get(property_id)
    if not property_obj:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404
    return jsonify(property_obj.to_dict()), 200

@seekers_bp.route('/properties/<int:property_id>/visit-requests', methods=['POST'])
@jwt_required()
def create_visit_request(property_id):
    """
    Permet à un client de soumettre une demande de visite.
    Décrémente toujours un pass de visite.
    Vérifie qu'un code de parrainage n'a pas déjà été utilisé pour ce bien par ce client.
    Si un code est utilisé, il lie la demande à l'agent et le notifie.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer:
        return jsonify({'message': "Utilisateur non trouvé."}), 404
        
    if customer.role != 'customer':
        return jsonify({'message': "Accès refusé. Seuls les clients peuvent faire des demandes de visite."}), 403

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

    if customer.visit_passes <= 0:
        return jsonify({'message': "Vous n'avez plus de pass de visite disponibles. Veuillez en acheter pour continuer."}), 402

    referral_id = None
    agent_to_notify = None
    if referral_code:
        referral = Referral.query.filter_by(
            referral_code=referral_code,
            property_id=property_id
        ).first()
        
        if not referral:
            return jsonify({'message': "Code de parrainage invalide ou non applicable pour ce bien."}), 400
        
        # --- DÉBUT DE LA VÉRIFICATION DE RÉUTILISATION ---
        existing_referred_visit = VisitRequest.query.filter(
            VisitRequest.customer_id == current_user_id,
            VisitRequest.property_id == property_id,
            VisitRequest.referral_id.isnot(None)
        ).first()

        if existing_referred_visit:
            return jsonify({'message': "Vous avez déjà utilisé un code de parrainage pour une visite de ce bien."}), 400
        # --- FIN DE LA VÉRIFICATION DE RÉUTILISATION ---
        
        referral_id = referral.id
        agent_to_notify = referral.agent

    customer.visit_passes -= 1

    new_visit_request = VisitRequest(
        customer_id=current_user_id,
        property_id=property_id,
        requested_datetime=requested_datetime,
        message=message,
        referral_id=referral_id
    )

    try:
        db.session.add(customer)
        db.session.add(new_visit_request)
        db.session.commit()

        # Notifications
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
    """
    Récupère l'historique des demandes de visite pour le client connecté.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer or customer.role != 'customer':
        return jsonify({'message': 'Accès refusé. Seuls les clients peuvent voir leurs demandes de visite.'}), 403

    status_filter = request.args.get('status')
    query = VisitRequest.query.filter_by(customer_id=current_user_id)

    if status_filter:
        query = query.filter_by(status=status_filter)
    
    visit_requests = query.order_by(VisitRequest.created_at.desc()).all()
    result = []
    for req in visit_requests:
        property_obj = req.property
        req_dict = {
            'id': req.id,
            'property_id': req.property_id,
            'property_title': property_obj.title if property_obj else 'Bien supprimé ou introuvable',
            'requested_datetime': req.requested_datetime.isoformat(),
            'status': req.status,
            'message': req.message,
            'created_at': req.created_at.isoformat()
        }
        result.append(req_dict)
    return jsonify(result), 200

# --- NOUVEL ENDPOINT POUR OBTENIR LE PRIX D'UN PASS ---
@seekers_bp.route('/visit-pass-price', methods=['GET'])
@jwt_required()
def get_visit_pass_price():
    """
    Retourne le prix unitaire d'un pass de visite.
    """
    # On cherche le service correspondant dans la base de données
    price_entry = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    
    if not price_entry:
        return jsonify({'message': "Le prix des pass de visite n'est pas configuré."}), 404
        
    return jsonify({'price': float(price_entry.amount)}), 200

# --- ENDPOINT DE VÉRIFICATION ENTIÈREMENT CORRIGÉ ---
@seekers_bp.route('/purchase-visit-passes', methods=['POST'])
@jwt_required()
def purchase_visit_passes():
    """
    Vérifie une transaction Fedapay et crédite le compte de l'utilisateur.
    Valide le montant payé en fonction de la quantité.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)
    if not customer:
        return jsonify({'message': "Utilisateur non trouvé."}), 404

    data = request.get_json()
    transaction_id = data.get('transaction_id')
    quantity = data.get('quantity')

    if not transaction_id or not quantity:
        return jsonify({'message': "ID de transaction et quantité manquants."}), 400
        
    try:
        quantity = int(quantity)
        if quantity <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({'message': "La quantité doit être un nombre entier positif."}), 400

    try:
        # 1. Récupérer le prix unitaire depuis la base de données (source de vérité)
        price_entry = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
        if not price_entry:
            return jsonify({'message': "Service d'achat de pass non configuré."}), 500
        
        price_per_pass = price_entry.amount # C'est un Decimal
        
        # 2. Vérifier la transaction auprès de Fedapay
        transaction = feda.Transaction.retrieve(transaction_id)
        
        if transaction.status != 'approved':
            return jsonify({'message': "Le paiement n'a pas été approuvé."}), 400

        # 3. Étape de sécurité CRUCIALE : Valider le montant
        expected_amount = int(price_per_pass * quantity) # FedaPay utilise des entiers (centimes/plus petite unité)
        
        if transaction.amount != expected_amount:
            current_app.logger.warning(f"Alerte de sécurité: Montant invalide pour user {customer.id}. Attendu: {expected_amount}, Reçu: {transaction.amount}")
            return jsonify({'message': "Montant de la transaction invalide."}), 400

        # 4. Créditer le compte de l'utilisateur
        customer.visit_passes += quantity
        db.session.commit()
        
        return jsonify({
            'message': f"{quantity} pass de visite ajoutés avec succès.",
            'new_visit_passes_balance': customer.visit_passes
        }), 200

    except Exception as e:
        current_app.logger.error(f"Erreur lors de la vérification de la transaction Fedapay: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur lors de la vérification du paiement."}), 500

@seekers_bp.route('/property-requests', methods=['POST'])
@jwt_required()
def create_property_request():
    """
    Permet à un client de soumettre une alerte / demande de bien.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer or customer.role != 'customer':
        return jsonify({'message': "Accès refusé."}), 403

    data = request.get_json()
    if not data:
        return jsonify({'message': "Données manquantes."}), 400

    new_request = PropertyRequest(
        customer_id=current_user_id,
        request_details=data.get('request_details'),
        city=data.get('city'),
        property_type_id=data.get('property_type_id'),
        min_price=data.get('min_price'),
        max_price=data.get('max_price'),
        status='new' # Le statut par défaut
    )

    try:
        db.session.add(new_request)
        db.session.commit()
        # On pourrait notifier l'admin ici, mais c'est optionnel
        return jsonify({'message': "Votre alerte a bien été enregistrée. Nous vous contacterons bientôt."}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création de la demande de bien: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500

@seekers_bp.route('/property-requests', methods=['GET'])
@jwt_required()
def get_seeker_property_requests():
    """
    Récupère l'historique des alertes de recherche pour le client connecté.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer or customer.role != 'customer':
        return jsonify({'message': 'Accès refusé.'}), 403

    # On récupère toutes les demandes du client, les plus récentes en premier
    requests = PropertyRequest.query.filter_by(customer_id=current_user_id).order_by(PropertyRequest.created_at.desc()).all()
    
    return jsonify([req.to_dict() for req in requests]), 200
