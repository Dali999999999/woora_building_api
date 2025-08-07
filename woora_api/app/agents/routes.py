from flask import Blueprint, jsonify, current_app, request
from app.models import Property, User, Referral, Commission, PropertyType, PropertyAttributeScope, PropertyAttribute, AttributeOption
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.helpers import generate_unique_referral_code
from app import db
import requests
import os
from sqlalchemy import func
from app.models import PayoutRequest

# On crée un nouveau "blueprint" spécifiquement pour les agents
agents_bp = Blueprint('agents', __name__, url_prefix='/agents')

@agents_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_agent():
    """
    Endpoint pour les agents.
    Récupère TOUS les biens immobiliers qui sont actuellement 'à vendre' ou 'à louer'.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé. Seuleument les agents peuvent accéder à cette ressource."}), 403

    # --- DÉBUT DE LA CORRECTION ---
    # On filtre les biens pour ne garder que ceux avec le statut 'for_sale' ou 'for_rent'.
    # On utilise .in_() pour vérifier si le statut est dans la liste des statuts valides.
    properties = Property.query.filter(
        Property.status.in_(['for_sale', 'for_rent'])
    ).all()
    # --- FIN DE LA CORRECTION ---
    
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

@agents_bp.route('/commissions', methods=['GET'])
@jwt_required()
def get_agent_commissions():
    """
    Récupère le solde du portefeuille de l'agent et la liste détaillée de ses commissions.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé."}), 403

    # Récupérer toutes les commissions pour cet agent, triées par date (la plus récente en premier)
    commissions = Commission.query.filter_by(agent_id=current_user_id).order_by(Commission.created_at.desc()).all()
    
    # Formater la liste des commissions
    commission_list = []
    for comm in commissions:
        commission_list.append({
            'id': comm.id,
            'amount': float(comm.amount) if comm.amount is not None else 0.0,
            'status': comm.status,
            'created_at': comm.created_at.isoformat(),
            'property_title': comm.property.title if comm.property else "Bien supprimé"
        })

    # Construire la réponse finale
    response_data = {
        'wallet_balance': float(agent.wallet_balance) if agent.wallet_balance is not None else 0.0,
        'commissions': commission_list
    }

    return jsonify(response_data), 200

# --- AJOUT D'UNE NOUVELLE ROUTE POUR LES AGENTS ET CLIENTS ---
@agents_bp.route('/property_types_with_attributes', methods=['GET'])
@jwt_required()
def get_property_types_for_agent():
    # On vérifie juste que l'utilisateur est connecté (agent ou client)
    # Pas besoin de vérifier le rôle si les clients peuvent aussi y accéder.
    get_jwt_identity()

    # Copie de la logique de la route admin
    pts = PropertyType.query.filter_by(is_active=True).all()
    result = []
    for pt in pts:
        d = pt.to_dict()
        aids = [s.attribute_id for s in PropertyAttributeScope.query.filter_by(property_type_id=pt.id).all()]
        attrs = PropertyAttribute.query.filter(PropertyAttribute.id.in_(aids)).all()
        d['attributes'] = []
        for a in attrs:
            ad = a.to_dict()
            if a.data_type == 'enum':
                ad['options'] = [o.to_dict() for o in AttributeOption.query.filter_by(attribute_id=a.id)]
            d['attributes'].append(ad)
        result.append(d)
    return jsonify(result)

# ===============================================
# 2. ROUTES FLASK POUR LES VERSEMENTS
# ===============================================

@agents_bp.route('/commissions/summary', methods=['GET'])
@jwt_required()
def get_commission_summary():
    """Récupérer le résumé des commissions de l'agent"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'agent':
            return jsonify({'error': 'Accès refusé. Seuls les agents peuvent accéder à cette ressource'}), 403
        
        # Calculer les totaux des commissions
        total_commissions = db.session.query(func.sum(Commission.amount)).filter(
            Commission.agent_id == current_user_id,
            Commission.status == 'pending'
        ).scalar() or 0
        
        paid_commissions = db.session.query(func.sum(Commission.amount)).filter(
            Commission.agent_id == current_user_id,
            Commission.status == 'paid'
        ).scalar() or 0
        
        # Dernière demande de versement
        last_payout = PayoutRequest.query.filter_by(
            agent_id=current_user_id
        ).order_by(PayoutRequest.requested_at.desc()).first()
        
        # Vérifier si un versement est éligible
        min_payout_amount = 1000  # 1000 FCFA minimum
        can_request_payout = float(total_commissions) >= min_payout_amount
        
        return jsonify({
            'total_pending_commissions': float(total_commissions),
            'total_paid_commissions': float(paid_commissions),
            'can_request_payout': can_request_payout,
            'minimum_payout_amount': min_payout_amount,
            'last_payout_request': last_payout.to_dict() if last_payout else None,
            'commissions': [commission.to_dict() for commission in user.commissions_earned]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@agents_bp.route('/commissions/request_payout', methods=['POST'])
@jwt_required()
def request_commission_payout():
    """Demander un versement de commissions en se basant sur le solde du portefeuille."""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'agent':
            return jsonify({'error': 'Accès refusé.'}), 403
        
        data = request.get_json()
        payment_details = {
            "phone_number": data.get('phone_number'),
            "mode": data.get('mode'),
            "country_iso": data.get('country_iso')
        }
        
        if not all(payment_details.values()):
            return jsonify({'error': 'Données de paiement manquantes.'}), 400
        
        # ✅ CORRECTION LOGIQUE : On vérifie le solde directement depuis le portefeuille de l'utilisateur.
        # C'est la source de vérité pour l'argent disponible.
        available_balance = float(user.wallet_balance or 0.0)
        
        min_amount = 1000  # Minimum 1000 FCFA
        if available_balance < min_amount:
            return jsonify({
                'error': f'Montant insuffisant. Minimum requis: {min_amount} FCFA',
                'available_amount': available_balance
            }), 400
            
        # On vérifie s'il y a déjà une demande en cours pour éviter les doublons.
        existing_request = PayoutRequest.query.filter(
            PayoutRequest.agent_id == current_user_id,
            PayoutRequest.status.in_(['pending', 'processing'])
        ).first()
        
        if existing_request:
            return jsonify({
                'error': 'Une demande de versement est déjà en cours.',
                'existing_request': existing_request.to_dict()
            }), 409

        # Le montant à verser est la totalité du solde disponible.
        amount_to_payout = available_balance

        # Créer la demande de versement
        payout_request = PayoutRequest(
            agent_id=current_user_id,
            requested_amount=amount_to_payout,
            payment_method=payment_details['mode'],
            phone_number=payment_details['phone_number'],
            status='pending'
        )
        
        db.session.add(payout_request)
        db.session.commit()
        
        # Initier le paiement avec FedaPay
        fedapay_result = initiate_fedapay_payout(payout_request, payment_details)
        
        if fedapay_result.get('success'):
            payout_request.status = 'processing'
            payout_request.fedapay_transaction_id = fedapay_result.get('transaction_id')
            payout_request.processed_at = datetime.utcnow()
        else:
            payout_request.status = 'failed'
            payout_request.error_message = fedapay_result.get('error', 'Erreur FedaPay inconnue')
        
        db.session.commit()
        
        return jsonify({
            'message': 'Demande de virement transmise avec succès à FedaPay.',
            'payout_request': payout_request.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la demande de virement: {e}", exc_info=True)
        return jsonify({'error': 'Une erreur interne est survenue.'}), 500

# Assurez-vous que la fonction initiate_fedapay_payout est aussi présente dans ce fichier ou importée correctement
# Je la remets ici pour être sûr qu'elle soit complète.

def initiate_fedapay_payout(payout_request, payment_details):
    """
    Initier un versement via FedaPay API en utilisant la structure de payload correcte.
    """
    try:
        is_sandbox = os.getenv('FLASK_ENV', 'production') != 'production'
        
        fedapay_api_key = os.getenv('FEDAPAY_SECRET_KEY_SANDBOX' if is_sandbox else 'FEDAPAY_SECRET_KEY')
        fedapay_base_url = "https://sandbox-api.fedapay.com/v1" if is_sandbox else "https://api.fedapay.com/v1"
        
        if not fedapay_api_key:
            raise Exception('Clé API FedaPay manquante pour l\'environnement actuel.')

        phone_number = payment_details.get('phone_number')
        mode = payment_details.get('mode')
        country_iso = payment_details.get('country_iso')

        payout_data = {
            "amount": int(float(payout_request.requested_amount)),
            "currency": {"iso": "XOF"},
            "mode": mode,
            "description": f"Versement commission Woora agent #{payout_request.agent_id}",
            "customer": {
                "firstname": payout_request.agent.first_name or "Agent",
                "lastname": payout_request.agent.last_name or f"#{payout_request.agent_id}",
                "email": payout_request.agent.email,
                "phone_number": {
                    "number": phone_number,
                    "country": country_iso.lower()
                }
            },
            # Le webhook doit pointer vers l'URL publique de votre API
            "callback_url": f"{os.getenv('API_BASE_URL')}/webhooks/fedapay/payout"
        }
        
        headers = {
            'Authorization': f'Bearer {fedapay_api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            f'{fedapay_base_url}/payouts',
            json=payout_data,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status()
        fedapay_response = response.json()
        
        return {
            'success': True,
            'transaction_id': fedapay_response.get('id'),
            'reference': fedapay_response.get('reference'),
            'status': fedapay_response.get('status')
        }
            
    except requests.exceptions.HTTPError as e:
        error_details = e.response.json() if e.response.content else {}
        return {'success': False, 'error': error_details.get('message', f'Erreur FedaPay: {e.response.status_code}'), 'details': error_details}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'Erreur de connexion FedaPay: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'Erreur interne: {str(e)}'}

# ===============================================
# 3. FONCTION D'INTÉGRATION FEDAPAY PAYOUT
# ===============================================

def initiate_fedapay_payout(payout_request, payment_details):
    """
    Initier un versement via FedaPay API en utilisant la structure de payload correcte.
    Documentation: https://docs.fedapay.com/payments/payouts
    """
    try:
        # Déterminer si on est en mode sandbox ou production
        # Idéalement, à mettre dans la configuration de l'app Flask
        is_sandbox = os.getenv('FLASK_ENV', 'production') != 'production'
        
        fedapay_api_key = os.getenv('FEDAPAY_SECRET_KEY_SANDBOX' if is_sandbox else 'FEDAPAY_SECRET_KEY')
        fedapay_base_url = "https://sandbox-api.fedapay.com/v1" if is_sandbox else "https://api.fedapay.com/v1"
        
        if not fedapay_api_key:
            raise Exception('Clé API FedaPay manquante pour l\'environnement actuel.')

        # Récupérer les détails du paiement depuis le dictionnaire
        phone_number = payment_details.get('phone_number')
        mode = payment_details.get('mode') # ex: 'mtn_open'
        country_iso = payment_details.get('country_iso') # ex: 'bj'

        if not all([phone_number, mode, country_iso]):
            raise Exception("Les détails de paiement (numéro, mode, pays) sont incomplets.")

        # Préparer le payload pour FedaPay avec la structure exacte
        payout_data = {
            "amount": int(float(payout_request.requested_amount)),
            "currency": {"iso": "XOF"},  # Structure objet correcte
            "mode": mode,
            "description": f"Versement commission Woora agent #{payout_request.agent_id}",
            "customer": {
                "firstname": payout_request.agent.first_name or "Agent",
                "lastname": payout_request.agent.last_name or f"#{payout_request.agent_id}",
                "email": payout_request.agent.email,
                "phone_number": {
                    "number": phone_number,    # Numéro au format international
                    "country": country_iso.lower() # Code pays en minuscules
                }
            },
            "callback_url": f"{os.getenv('API_BASE_URL')}/webhooks/fedapay/payout"
        }
        
        headers = {
            'Authorization': f'Bearer {fedapay_api_key}',
            'Content-Type': 'application/json'
        }
        
        # Étape 1: Créer le virement (Payout)
        # La documentation FedaPay indique que la création et l'envoi peuvent être faits en une seule étape
        # via l'endpoint /payouts. Il n'est pas toujours nécessaire d'appeler /start séparément.
        # Nous allons suivre le modèle de création direct.
        response = requests.post(
            f'{fedapay_base_url}/payouts',
            json=payout_data,
            headers=headers,
            timeout=30
        )
        
        response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP (4xx ou 5xx)

        fedapay_response = response.json()
        
        # Le code de statut 201 (Created) indique que la requête de virement a été acceptée
        return {
            'success': True,
            'transaction_id': fedapay_response.get('id'),
            'reference': fedapay_response.get('reference'),
            'status': fedapay_response.get('status') # Sera 'pending' ou 'processing'
        }
            
    except requests.exceptions.HTTPError as e:
        error_details = e.response.json() if e.response.content else {}
        return {
            'success': False,
            'error': error_details.get('message', f'Erreur FedaPay: {e.response.status_code}'),
            'details': error_details
        }
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'Erreur de connexion FedaPay: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'Erreur interne: {str(e)}'}

# ===============================================
# 4. WEBHOOK POUR TRAITER LES CONFIRMATIONS FEDAPAY
# ===============================================

@agents_bp.route('/webhooks/fedapay/payout', methods=['POST'])
def fedapay_payout_webhook():
    """Webhook pour traiter les notifications de versement FedaPay et mettre à jour le solde."""
    try:
        data = request.get_json().get('data', {}) # Le payload est souvent dans une clé "data"
        event = request.get_json().get('event') # ex: 'payout.approved'

        if not data or not event:
             # Si la structure n'est pas celle attendue, on prend le JSON racine
             data = request.get_json()
             event = data.get('name') # FedaPay utilise 'name' pour l'événement et 'data' pour le payload

        transaction_id = data.get('id')
        status = data.get('status') # approved, declined, etc.
        
        if not transaction_id:
            return jsonify({'error': 'ID de transaction manquant dans le webhook'}), 400
        
        payout_request = PayoutRequest.query.filter_by(fedapay_transaction_id=str(transaction_id)).first()
        
        if not payout_request:
            return jsonify({'error': 'Demande de versement non trouvée'}), 404
        
        # Éviter de traiter plusieurs fois le même webhook
        if payout_request.status == 'completed' or payout_request.status == 'failed':
            return jsonify({'message': 'Webhook déjà traité'}), 200

        if status == 'approved':
            # ✅ CORRECTION LOGIQUE : Mettre à jour le solde du portefeuille
            agent = User.query.get(payout_request.agent_id)
            if agent:
                current_balance = float(agent.wallet_balance or 0.0)
                payout_amount = float(payout_request.requested_amount)
                agent.wallet_balance = current_balance - payout_amount
            
            payout_request.status = 'completed'
            payout_request.completed_at = datetime.utcnow()
            payout_request.actual_amount = payout_request.requested_amount # On suppose que le montant versé est celui demandé
            
            # Marquer toutes les commissions 'pending' comme 'paid'
            Commission.query.filter(
                Commission.agent_id == payout_request.agent_id,
                Commission.status == 'pending'
            ).update({'status': 'paid'})
            
            # Créer une transaction de type 'commission_payout'
            transaction = Transaction(
                user_id=payout_request.agent_id,
                amount=-payout_request.actual_amount, # Montant négatif car c'est un retrait
                type='commission_payout',
                description=f'Virement FedaPay (Payout #{payout_request.id})',
                related_entity_id=str(payout_request.id)
            )
            db.session.add(transaction)
            
        elif status in ['declined', 'failed']:
            payout_request.status = 'failed'
            payout_request.error_message = data.get('last_error_message', 'Versement échoué par FedaPay')
        
        db.session.commit()
        return jsonify({'message': 'Webhook traité avec succès'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur Webhook FedaPay: {e}", exc_info=True)
        return jsonify({'error': 'Erreur interne lors du traitement du webhook'}), 500

# ===============================================
# 5. ROUTE POUR L'HISTORIQUE DES VERSEMENTS
# ===============================================

@agents_bp.route('/agents/commissions/payout_history', methods=['GET'])
@jwt_required()
def get_payout_history():
    """Récupérer l'historique des demandes de versement"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'agent':
            return jsonify({'error': 'Accès refusé'}), 403
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        payouts = PayoutRequest.query.filter_by(
            agent_id=current_user_id
        ).order_by(PayoutRequest.requested_at.desc()).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'payouts': [payout.to_dict() for payout in payouts.items],
            'pagination': {
                'current_page': payouts.page,
                'pages': payouts.pages,
                'per_page': payouts.per_page,
                'total': payouts.total,
                'has_next': payouts.has_next,
                'has_prev': payouts.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500









