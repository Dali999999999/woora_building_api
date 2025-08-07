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
    """Demander un versement de commissions"""
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'agent':
            return jsonify({'error': 'Accès refusé. Seuls les agents peuvent effectuer cette action'}), 403
        
        data = request.get_json()
        phone_number = data.get('phone_number')
        payment_method = data.get('payment_method', 'mobile_money')
        
        if not phone_number:
            return jsonify({'error': 'Numéro de téléphone requis pour Mobile Money'}), 400
        
        # Calculer le montant disponible
        total_pending = db.session.query(func.sum(Commission.amount)).filter(
            Commission.agent_id == current_user_id,
            Commission.status == 'pending'
        ).scalar() or 0
        
        min_amount = 1000  # Minimum 1000 FCFA
        if float(total_pending) < min_amount:
            return jsonify({
                'error': f'Montant insuffisant. Minimum requis: {min_amount} FCFA',
                'available_amount': float(total_pending)
            }), 400
        
        # Vérifier s'il n'y a pas déjà une demande en cours
        existing_request = PayoutRequest.query.filter(
            PayoutRequest.agent_id == current_user_id,
            PayoutRequest.status.in_(['pending', 'processing'])
        ).first()
        
        if existing_request:
            return jsonify({
                'error': 'Une demande de versement est déjà en cours',
                'existing_request': existing_request.to_dict()
            }), 400
        
        # Créer la demande de versement
        payout_request = PayoutRequest(
            agent_id=current_user_id,
            requested_amount=total_pending,
            payment_method=payment_method,
            phone_number=phone_number,
            status='pending'
        )
        
        db.session.add(payout_request)
        db.session.commit()
        
        # Initier le paiement avec FedaPay (asynchrone recommandé)
        try:
            fedapay_result = initiate_fedapay_payout(payout_request)
            
            if fedapay_result.get('success'):
                payout_request.status = 'processing'
                payout_request.fedapay_transaction_id = fedapay_result.get('transaction_id')
                payout_request.processed_at = datetime.utcnow()
            else:
                payout_request.status = 'failed'
                payout_request.error_message = fedapay_result.get('error', 'Erreur FedaPay inconnue')
            
            db.session.commit()
            
        except Exception as fedapay_error:
            payout_request.status = 'failed'
            payout_request.error_message = f'Erreur FedaPay: {str(fedapay_error)}'
            db.session.commit()
        
        return jsonify({
            'message': 'Demande de versement créée avec succès',
            'payout_request': payout_request.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ===============================================
# 3. FONCTION D'INTÉGRATION FEDAPAY PAYOUT
# ===============================================

def initiate_fedapay_payout(payout_request):
    """
    Initier un versement via FedaPay API
    Documentation: https://docs.fedapay.com/payments/payouts
    """
    try:
        fedapay_api_key = os.getenv('FEDAPAY_SECRET_KEY')  # Clé API FedaPay
        fedapay_base_url = os.getenv('FEDAPAY_BASE_URL', 'https://sandbox-api.fedapay.com/v1')
        
        if not fedapay_api_key:
            raise Exception('Clé API FedaPay manquante')
        
        # Préparer les données pour FedaPay
        payout_data = {
            "amount": int(float(payout_request.requested_amount)),  # Montant en centimes/kobo
            "currency": "XOF",  # Franc CFA
            "description": f"Versement commission agent #{payout_request.agent_id}",
            "customer": {
                "firstname": payout_request.agent.first_name or "Agent",
                "lastname": payout_request.agent.last_name or f"#{payout_request.agent_id}",
                "email": payout_request.agent.email,
                "phone_number": payout_request.phone_number
            },
            "method": payout_request.payment_method,
            "phone_number": payout_request.phone_number,
            "callback_url": f"{os.getenv('API_BASE_URL')}/webhooks/fedapay/payout"
        }
        
        # Headers pour l'API FedaPay
        headers = {
            'Authorization': f'Bearer {fedapay_api_key}',
            'Content-Type': 'application/json'
        }
        
        # Faire la requête à FedaPay
        response = requests.post(
            f'{fedapay_base_url}/payouts',
            json=payout_data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 201:
            fedapay_response = response.json()
            return {
                'success': True,
                'transaction_id': fedapay_response.get('id'),
                'reference': fedapay_response.get('reference'),
                'status': fedapay_response.get('status')
            }
        else:
            error_data = response.json() if response.content else {}
            return {
                'success': False,
                'error': error_data.get('message', f'Erreur HTTP {response.status_code}'),
                'details': error_data
            }
            
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Erreur de connexion FedaPay: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Erreur interne: {str(e)}'
        }

# ===============================================
# 4. WEBHOOK POUR TRAITER LES CONFIRMATIONS FEDAPAY
# ===============================================

@agents_bp.route('/webhooks/fedapay/payout', methods=['POST'])
def fedapay_payout_webhook():
    """Webhook pour traiter les notifications de versement FedaPay"""
    try:
        data = request.get_json()
        
        transaction_id = data.get('id')
        status = data.get('status')
        
        if not transaction_id:
            return jsonify({'error': 'Transaction ID manquant'}), 400
        
        # Trouver la demande de versement correspondante
        payout_request = PayoutRequest.query.filter_by(
            fedapay_transaction_id=str(transaction_id)
        ).first()
        
        if not payout_request:
            return jsonify({'error': 'Demande de versement non trouvée'}), 404
        
        # Traiter selon le statut
        if status == 'approved':
            # Versement réussi
            payout_request.status = 'completed'
            payout_request.completed_at = datetime.utcnow()
            payout_request.actual_amount = payout_request.requested_amount
            
            # Marquer les commissions comme payées
            Commission.query.filter(
                Commission.agent_id == payout_request.agent_id,
                Commission.status == 'pending'
            ).update({'status': 'paid'})
            
            # Créer une transaction de versement
            transaction = Transaction(
                user_id=payout_request.agent_id,
                amount=payout_request.actual_amount,
                type='commission_payout',
                description=f'Versement de commissions (Payout #{payout_request.id})',
                related_entity_id=str(payout_request.id)
            )
            db.session.add(transaction)
            
        elif status in ['declined', 'failed']:
            # Versement échoué
            payout_request.status = 'failed'
            payout_request.error_message = data.get('reason', 'Versement échoué')
            
        elif status == 'pending':
            # Versement en cours
            payout_request.status = 'processing'
        
        db.session.commit()
        
        return jsonify({'message': 'Webhook traité avec succès'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

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





