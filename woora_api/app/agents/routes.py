from flask import Blueprint, jsonify, current_app, request
from app.models import Property, User, Referral, Commission, PropertyType, PropertyAttributeScope, PropertyAttribute, AttributeOption, PropertyImage, PropertyStatus, PropertyRequest
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.helpers import generate_unique_referral_code
from app.utils.eav_utils import save_property_eav_values
from app import db
import requests
import os
from sqlalchemy import func, or_, desc, case, cast, String, Numeric
from app.models import PayoutRequest, Transaction
from datetime import datetime
import json
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import selectinload
# from app.utils.mega_utils import get_mega_instance # REMOVED
from werkzeug.utils import secure_filename
import uuid

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
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Base query for general marketplace: Validated + Not Deleted
    base_query = Property.query.options(
        selectinload(Property.images),
        selectinload(Property.property_type),
        selectinload(Property.owner)
    ).join(Property.owner).filter(
        Property.is_validated == True,
        Property.deleted_at == None,
        User.deleted_at == None
    )

    # --- 1. Filtre par Statut (Dynamique) ---
    status_param = request.args.get('status')
    if status_param and status_param != 'null' and status_param != '':
        base_query = base_query.filter(Property.status == status_param)
    else:
        # Comportement par défaut : Vente et Location
        base_query = base_query.filter(Property.status.in_(['for_sale', 'for_rent']))

    # --- 2. Filtres "Durs" (Exclusion) ---
    search_query = request.args.get('search', '').strip()
    if search_query:
        search_pattern = f"%{search_query}%"
        base_query = base_query.filter(or_(
            Property.title.ilike(search_pattern),
            Property.city.ilike(search_pattern),
            Property.address.ilike(search_pattern)
        ))

    try:
        property_type_id = request.args.get('property_type_id')
        if property_type_id:
            base_query = base_query.filter(Property.property_type_id == int(property_type_id))
    except (ValueError, TypeError):
        pass

    try:
        min_price = request.args.get('min_price')
        if min_price:
            base_query = base_query.filter(cast(Property.price, Numeric) >= float(min_price))
        
        max_price = request.args.get('max_price')
        if max_price:
            base_query = base_query.filter(cast(Property.price, Numeric) <= float(max_price))
    except (ValueError, TypeError):
        pass

    # --- 3. Filtres Dynamiques (Stricts avec EAV) ---
    filters_json = request.args.get('filters')
    if filters_json:
        try:
            dynamic_filters = json.loads(filters_json)
            if isinstance(dynamic_filters, dict) and dynamic_filters:
                from app.models import PropertyValue, PropertyAttribute
                from sqlalchemy import and_
                
                for key, value in dynamic_filters.items():
                    # Match exact basé sur le type reçu du JSON
                    if isinstance(value, bool):
                        cond = and_(
                            func.lower(PropertyAttribute.name) == key.lower().strip(),
                            PropertyValue.value_boolean == value
                        )
                    elif isinstance(value, int):
                        cond = and_(
                            func.lower(PropertyAttribute.name) == key.lower().strip(),
                            PropertyValue.value_integer == value
                        )
                    elif isinstance(value, float):
                        cond = and_(
                            func.lower(PropertyAttribute.name) == key.lower().strip(),
                            PropertyValue.value_decimal == str(value)
                        )
                    else:
                        val_str = str(value).lower().strip()
                        cond = and_(
                            func.lower(PropertyAttribute.name) == key.lower().strip(),
                            func.lower(PropertyValue.value_string) == val_str
                        )
                    
                    # On exige que CET attribut avec CETTE valeur existe pour ce bien
                    has_attr = db.session.query(PropertyValue.id).join(
                        PropertyAttribute, PropertyValue.attribute_id == PropertyAttribute.id
                    ).filter(
                        PropertyValue.property_id == Property.id,
                        cond
                    ).exists()
                    
                    base_query = base_query.filter(has_attr)

        except json.JSONDecodeError:
            pass

    # --- 4. Tri et Pagination ---
    query = base_query.order_by(Property.created_at.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    properties = pagination.items
    
    return jsonify({
        'properties': [p.to_dict() for p in properties],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    }), 200

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
    # OPTIMISATION
    property = Property.query.options(selectinload(Property.images)).get(property_id)
    
    if not property or property.deleted_at:
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
    if not property_obj or property_obj.deleted_at:
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

# --- ROUTE SIMPLE POUR LES TYPES DE PROPRIÉTÉS ---
@agents_bp.route('/property_types_with_attributes', methods=['GET'])
@jwt_required()
def get_property_types_for_agent():
    """
    Version optimisée avec selectinload pour éviter les requêtes N+1.
    """
    try:
        get_jwt_identity()
        
        # Version optimisée comme pour les propriétaires
        property_types = PropertyType.query.options(
            selectinload(PropertyType.attribute_scopes)
                .selectinload(PropertyAttributeScope.attribute)
                    .selectinload(PropertyAttribute.options)
        ).filter(PropertyType.is_active == True).order_by(PropertyType.display_order.asc()).all()

        result = []
        for pt in property_types:
            pt_dict = pt.to_dict()
            pt_dict['attributes'] = []
            
            # Sort by admin-configured sort_order
            sorted_scopes = sorted(pt.attribute_scopes, key=lambda s: s.sort_order)
            for scope in sorted_scopes:
                attribute = scope.attribute
                attr_dict = attribute.to_dict()
                pt_dict['attributes'].append(attr_dict)
                
            result.append(pt_dict)
            
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Erreur property types optimisée: {e}")
        # Fallback simple en cas d'erreur
        try:
            pts = PropertyType.query.filter_by(is_active=True).order_by(PropertyType.display_order.asc()).all()
            simple_result = [{'id': pt.id, 'name': pt.name, 'attributes': []} for pt in pts]
            return jsonify(simple_result)
        except:
            return jsonify([]), 200

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
        # ✅ VERROUILLAGE PESSIMISTE: On verrouille la ligne utilisateur pour éviter les race conditions (double dépense)
        user = User.query.with_for_update().get(current_user_id)
        
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

# ===============================================
# 3. FONCTION D'INTÉGRATION FEDAPAY PAYOUT (VERSION UNIQUE ET CORRIGÉE)
# ===============================================

def initiate_fedapay_payout(payout_request, payment_details):
    """
    Initier un versement via FedaPay API avec logging complet des réponses.
    Documentation: https://docs.fedapay.com/payments/payouts
    """
    try:
        # Déterminer si on est en mode sandbox ou production
        is_sandbox = os.getenv('FLASK_ENV', 'production') != 'production'
        
        fedapay_api_key = os.getenv('FEDAPAY_SECRET_KEY')
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
        
        # ✅ AMÉLIORATION: Logger la requête envoyée à FedaPay
        current_app.logger.info(f"=== REQUÊTE FEDAPAY PAYOUT ===")
        current_app.logger.info(f"URL: {fedapay_base_url}/payouts")
        current_app.logger.info(f"Headers: {json.dumps(headers, indent=2)}")
        current_app.logger.info(f"Payload: {json.dumps(payout_data, indent=2)}")
        current_app.logger.info(f"=== FIN REQUÊTE FEDAPAY ===")
        
        # Étape 1: Créer le virement (Payout)
        response = requests.post(
            f'{fedapay_base_url}/payouts',
            json=payout_data,
            headers=headers,
            timeout=30
        )
        
        # ✅ AMÉLIORATION: Logger la réponse complète de FedaPay (SUCCÈS)
        current_app.logger.info(f"=== RÉPONSE FEDAPAY PAYOUT ===")
        current_app.logger.info(f"Status Code: {response.status_code}")
        current_app.logger.info(f"Headers: {dict(response.headers)}")
        
        # Logger le contenu de la réponse, qu'elle soit en JSON ou en texte
        try:
            response_json = response.json()
            current_app.logger.info(f"Response Body (JSON): {json.dumps(response_json, indent=2)}")
        except ValueError:
            current_app.logger.info(f"Response Body (TEXT): {response.text}")
        
        current_app.logger.info(f"=== FIN RÉPONSE FEDAPAY ===")
        
        response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP (4xx ou 5xx)

        fedapay_response = response.json()
        payout_id = fedapay_response.get('v1/payout', {}).get('id') or fedapay_response.get('id')

        if not payout_id:
             current_app.logger.error(f"Impossible de récupérer l'ID du payout: {fedapay_response}")
             return {'success': False, 'error': "Erreur API FedaPay (ID manquant)"}

        # Étape 2: Démarrer le virement immédiatement
        current_app.logger.info(f"=== DEMARRAGE DU VIREMENT (START) POUR ID {payout_id} ===")
        start_payload = {"payouts": [{"id": payout_id, "send_now": True}]}
        
        try:
            start_response = requests.put(
                f'{fedapay_base_url}/payouts/start',
                json=start_payload,
                headers=headers,
                timeout=30
            )
            
            # Logger la réponse du Start
            current_app.logger.info(f"Start Response Code: {start_response.status_code}")
            try:
                start_json = start_response.json()
                current_app.logger.info(f"Start Response Body: {json.dumps(start_json, indent=2)}")
            except:
                current_app.logger.info(f"Start Response Text: {start_response.text}")

            start_response.raise_for_status()
            
            # Si on arrive ici, le virement est bien parti
            return {
                'success': True,
                'transaction_id': payout_id,
                'reference': fedapay_response.get('reference'),
                'status': 'processing', # On marque comme processing car envoyé
                'full_response': fedapay_response
            }

        except requests.exceptions.HTTPError as start_err:
             current_app.logger.error(f"Erreur lors du démarrage du virement: {start_err}")
             return {'success': False, 'error': f"Virement créé mais échec de l'envoi: {start_err}", 'transaction_id': payout_id}

        
        # Le code de statut 201 (Created) indique que la requête de virement a été acceptée
        return {
            'success': True,
            'transaction_id': fedapay_response.get('id'),
            'reference': fedapay_response.get('reference'),
            'status': fedapay_response.get('status'), # Sera 'pending' ou 'processing'
            'full_response': fedapay_response  # Pour un debugging complet
        }
            
    except requests.exceptions.HTTPError as e:
        # ✅ AMÉLIORATION: Logger la réponse complète de FedaPay (ERREUR)
        current_app.logger.error(f"=== ERREUR HTTP FEDAPAY PAYOUT ===")
        current_app.logger.error(f"Status Code: {e.response.status_code}")
        current_app.logger.error(f"Headers: {dict(e.response.headers)}")
        
        error_details = {}
        try:
            error_details = e.response.json()
            current_app.logger.error(f"Response Body (JSON): {json.dumps(error_details, indent=2)}")
        except ValueError:
            error_details = {'message': e.response.text}
            current_app.logger.error(f"Response Body (TEXT): {e.response.text}")
        
        current_app.logger.error(f"=== FIN ERREUR HTTP FEDAPAY ===")
        
        return {
            'success': False,
            'error': error_details.get('message', f'Erreur HTTP {e.response.status_code}'),
            'details': error_details,
            'status_code': e.response.status_code
        }
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"=== ERREUR DE CONNEXION FEDAPAY ===")
        current_app.logger.error(f"Erreur: {str(e)}")
        current_app.logger.error(f"=== FIN ERREUR DE CONNEXION ===")
        
        return {'success': False, 'error': f'Erreur de connexion FedaPay: {str(e)}'}
    except Exception as e:
        current_app.logger.error(f"=== ERREUR INTERNE PAYOUT ===")
        current_app.logger.error(f"Erreur: {str(e)}", exc_info=True)
        current_app.logger.error(f"=== FIN ERREUR INTERNE ===")
        
        return {'success': False, 'error': f'Erreur interne: {str(e)}'}

# ===============================================
# 4. WEBHOOK POUR TRAITER LES CONFIRMATIONS FEDAPAY
# ===============================================

@agents_bp.route('/webhooks/fedapay/payout', methods=['POST'])
def fedapay_payout_webhook():
    """Webhook pour traiter les notifications de versement FedaPay et mettre à jour le solde."""
    try:
        # ✅ AMÉLIORATION: Logger la requête webhook complète
        webhook_data = request.get_json()
        current_app.logger.info(f"=== WEBHOOK FEDAPAY PAYOUT REÇU ===")
        current_app.logger.info(f"Headers: {dict(request.headers)}")
        current_app.logger.info(f"Body: {json.dumps(webhook_data, indent=2)}")
        current_app.logger.info(f"=== FIN WEBHOOK REÇU ===")
        
        data = webhook_data.get('data', {}) # Le payload est souvent dans une clé "data"
        event = webhook_data.get('event') # ex: 'payout.approved'

        if not data or not event:
             # Si la structure n'est pas celle attendue, on prend le JSON racine
             data = webhook_data
             event = data.get('name') # FedaPay utilise 'name' pour l'événement et 'data' pour le payload

        transaction_id = data.get('id')
        status = data.get('status') # approved, declined, etc.
        
        current_app.logger.info(f"Webhook traité - Event: {event}, Transaction ID: {transaction_id}, Status: {status}")
        
        if not transaction_id:
            return jsonify({'error': 'ID de transaction manquant dans le webhook'}), 400
        
        payout_request = PayoutRequest.query.filter_by(fedapay_transaction_id=str(transaction_id)).first()
        
        if not payout_request:
            current_app.logger.warning(f"Demande de versement non trouvée pour transaction_id: {transaction_id}")
            return jsonify({'error': 'Demande de versement non trouvée'}), 404
        
        # Éviter de traiter plusieurs fois le même webhook
        if payout_request.status == 'completed' or payout_request.status == 'failed':
            current_app.logger.info(f"Webhook déjà traité pour payout_request {payout_request.id}")
            return jsonify({'message': 'Webhook déjà traité'}), 200

        if status == 'approved':
            # ✅ CORRECTION LOGIQUE : Mettre à jour le solde du portefeuille
            agent = User.query.get(payout_request.agent_id)
            if agent:
                current_balance = float(agent.wallet_balance or 0.0)
                payout_amount = float(payout_request.requested_amount)
                agent.wallet_balance = current_balance - payout_amount
                
                current_app.logger.info(f"Solde agent {agent.id} mis à jour: {current_balance} -> {agent.wallet_balance}")
            
            payout_request.status = 'completed'
            payout_request.completed_at = datetime.utcnow()
            payout_request.actual_amount = payout_request.requested_amount # On suppose que le montant versé est celui demandé
            
            # Marquer toutes les commissions 'pending' comme 'paid'
            updated_commissions = Commission.query.filter(
                Commission.agent_id == payout_request.agent_id,
                Commission.status == 'pending'
            ).update({'status': 'paid'})
            
            current_app.logger.info(f"{updated_commissions} commissions marquées comme payées pour l'agent {payout_request.agent_id}")
            
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
            
            current_app.logger.error(f"Payout {payout_request.id} échoué: {payout_request.error_message}")
        
        db.session.commit()
        
        current_app.logger.info(f"Webhook FedaPay traité avec succès pour payout_request {payout_request.id}")
        return jsonify({'message': 'Webhook traité avec succès'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"=== ERREUR WEBHOOK FEDAPAY ===")
        current_app.logger.error(f"Erreur: {str(e)}", exc_info=True)
        current_app.logger.error(f"=== FIN ERREUR WEBHOOK ===")
        
        return jsonify({'error': 'Erreur interne lors du traitement du webhook'}), 500

# ===============================================
# 5. ROUTE POUR L'HISTORIQUE DES VERSEMENTS
# ===============================================

@agents_bp.route('/commissions/payout_history', methods=['GET'])
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

@agents_bp.route('/request-withdrawal', methods=['POST'])
@jwt_required()
def request_withdrawal():
    """
    Initie une demande de virement (Payout) pour l'agent connecté.
    """
    current_user_id = get_jwt_identity()
    # ✅ VERROUILLAGE PESSIMISTE
    agent = User.query.with_for_update().get(current_user_id)
    
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé."}), 403

    data = request.get_json()
    if not data:
        return jsonify({'message': "Données manquantes."}), 400

    amount = data.get('amount')
    mode = data.get('mode')
    phone_number = data.get('phone_number')
    country_code = data.get('country_code')

    # Valider les entrées
    if not all([amount, mode, phone_number, country_code]):
        return jsonify({'message': "Tous les champs sont requis."}), 400

    try:
        amount_int = int(amount)
        if amount_int < 1000:
            return jsonify({'message': "Le montant minimum pour un virement est de 1000 FCFA."}), 400
        if amount_int > agent.wallet_balance:
            return jsonify({'message': "Solde insuffisant pour effectuer ce virement."}), 400
    except (ValueError, TypeError):
        return jsonify({'message': "Le montant doit être un nombre entier valide."}), 400
        
    # --- DÉBUT DE L'INTERACTION AVEC FEDAPAY ---
    
    FEDAPAY_API_KEY = os.environ.get('FEDAPAY_SECRET_KEY')
    FEDAPAY_API_URL = "https://sandbox-api.fedapay.com/v1/payouts"

    headers = {
        'Authorization': f'Bearer {FEDAPAY_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    payout_data = {
        "amount": amount_int,
        "currency": {"iso": "XOF"},
        "mode": mode,
        "customer": {
            "firstname": agent.first_name,
            "lastname": agent.last_name,
            "email": agent.email,
            "phone_number": {
                "number": phone_number,
                "country": country_code
            }
        }
    }

    try:
        # Étape 1 : Créer le Payout
        response_create = requests.post(FEDAPAY_API_URL, headers=headers, json=payout_data)
        response_create.raise_for_status() # Lève une exception pour les erreurs HTTP (4xx ou 5xx)
        payout_response_data = response_create.json()
        payout_id = payout_response_data['v1/payout']['id']

        # Étape 2 : Lancer le Payout immédiatement
        start_url = f"{FEDAPAY_API_URL}/start"
        start_data = { "payouts": [{ "id": payout_id }] }
        response_start = requests.put(start_url, headers=headers, json=start_data)
        response_start.raise_for_status()

        # Étape 3 : Enregistrer la transaction dans notre BDD
        # L'argent est maintenant "bloqué" en attendant la confirmation de FedaPay
        # On ne décrémente le solde que lorsque le webhook confirme le statut 'sent'
        new_transaction = Transaction(
            user_id=agent.id,
            amount=Decimal(str(amount_int)), # On stocke en Decimal
            type='withdrawal',
            description=f"Demande de virement vers {phone_number} via {mode}.",
            # On pourrait ajouter une colonne 'status' et 'external_id' à la table Transaction
            # status='pending', 
            # external_transaction_id=payout_id 
        )
        db.session.add(new_transaction)
        db.session.commit()

        return jsonify({'message': f"Votre demande de virement de {amount_int} XOF a été initiée."}), 200

    except requests.exceptions.RequestException as e:
        # Erreurs de communication avec FedaPay
        current_app.logger.error(f"Erreur FedaPay: {e.response.text if e.response else e}")
        return jsonify({'message': "Une erreur est survenue lors de la communication avec le service de paiement."}), 503
    except Exception as e:
        # Autres erreurs (ex: base de données)
        db.session.rollback()
        current_app.logger.error(f"Erreur interne lors de la demande de virement: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

# ==============================================================================
# NOUVELLES ROUTES POUR PERMETTRE AUX AGENTS D'AJOUTER DES BIENS IMMOBILIERS
# ==============================================================================

UPLOAD_FOLDER = '/tmp' # Définir le dossier d'upload

@agents_bp.route('/properties', methods=['POST'])
@jwt_required()
def create_property_for_agent():
    """
    Permet à un agent immobilier de créer un bien immobilier pour lui-même.
    Identique au système des propriétaires mais pour les agents.
    """
    current_app.logger.debug("Requête POST /agents/properties reçue.")
    current_user_id = get_jwt_identity()
    current_app.logger.debug(f"Agent authentifié ID: {current_user_id}")

    data = request.get_json()
    import logging
    logging.getLogger().setLevel(logging.DEBUG)
    current_app.logger.debug("🔍 Payload reçu : %s", data)

    # ... (code existant de create_property_for_agent non montré complètement dans le snippet précédent,
    # mais je vais ajouter les nouvelles routes APRES, à la fin du fichier, ce qui est plus sûr)
    # ATTENTION: Le snippet précédent s'arrêtait à la ligne 800. Je vais utiliser "write_to_file" en append
    # ou "replace_file_content" ciblant la fin, mais je ne connais pas la dernière ligne exacte.
    # Strategie: Je vais remplacer le bloc 786-800 et AJOUTER les nouvelles routes juste AVANT ce bloc
    # car je connais le contenu exact de ce bloc.
    # Non, mauvaise idée. Le fichier fait 1225 lignes.
    # Je vais plutot faire un `view_file` de la fin du fichier pour être sûr de l'endroit où ajouter.

    current_app.logger.debug(f"JSON brut reçu: {data}")

    required_top_level_fields = ['image_urls', 'attributes']
    for field in required_top_level_fields:
        if field not in data:
            current_app.logger.warning(f"Champ de niveau supérieur manquant: {field}")
            return jsonify({'message': f"Le champ {field} est requis au niveau supérieur."}), 400

    dynamic_attributes = data.get('attributes', {})
    current_app.logger.debug(f"Attributs dynamiques extraits: {dynamic_attributes}")

    agent = User.query.get(current_user_id)
    if not agent or agent.role != 'agent':
        current_app.logger.warning(f"Accès non autorisé pour l'utilisateur {current_user_id} avec le rôle {agent.role if agent else 'N/A'}.")
        return jsonify({'message': "Accès non autorisé. Seuls les agents peuvent créer des biens."}), 403

    property_type_id = dynamic_attributes.get('property_type_id')
    current_app.logger.debug(f"property_type_id brut: {property_type_id}, type: {type(property_type_id)}")
    try:
        property_type_id = int(property_type_id)
        current_app.logger.debug(f"property_type_id converti: {property_type_id}, type: {type(property_type_id)}")
    except (ValueError, TypeError):
        current_app.logger.warning(f"Validation échouée: property_type_id doit être un entier valide. Reçu: {property_type_id}")
        return jsonify({'message': "property_type_id doit être un entier valide."}), 400

    title = dynamic_attributes.get('title')
    current_app.logger.debug(f"title brut: {title}, type: {type(title)}")
    if not isinstance(title, str) or not title:
        current_app.logger.warning(f"Validation échouée: title est requis et doit être une chaîne de caractères non vide. Reçu: {title}")
        return jsonify({'message': "title est requis et doit être une chaîne de caractères non vide."}), 400

    price = dynamic_attributes.get('price')
    current_app.logger.debug(f"price brut: {price}, type: {type(price)}")
    try:
        price = float(price)
        current_app.logger.debug(f"price converti: {price}, type: {type(price)}")
    except (ValueError, TypeError):
        current_app.logger.warning(f"Validation échouée: price doit être un nombre décimal valide. Reçu: {price}")
        return jsonify({'message': "price doit être un nombre décimal valide."}), 400

    description = dynamic_attributes.get('description')
    current_app.logger.debug(f"description brut: {description}, type: {type(description)}")
    if description is not None and not isinstance(description, str):
        current_app.logger.warning(f"Validation échouée: description doit être une chaîne de caractères. Reçu: {description}")
        return jsonify({'message': "description doit être une chaîne de caractères."}), 400

    # Extraction intelligente pour la ville (support du français)
    city = dynamic_attributes.get('city') or dynamic_attributes.get('Ville') or dynamic_attributes.get('ville')
    current_app.logger.debug(f"city extrait: {city}, type: {type(city)}")
    if city is not None and not isinstance(city, str):
        current_app.logger.warning(f"Validation échouée: city doit être une chaîne de caractères. Reçu: {city}")
        return jsonify({'message': "city doit être une chaîne de caractères."}), 400

    # Extraction intelligente pour l'adresse/quartier (support du français)
    address = dynamic_attributes.get('address') or dynamic_attributes.get('Adresse') or dynamic_attributes.get('adresse') or dynamic_attributes.get('Quartier') or dynamic_attributes.get('quartier')
    current_app.logger.debug(f"address extrait: {address}, type: {type(address)}")
    if address is not None and not isinstance(address, str):
        current_app.logger.warning(f"Validation échouée: address doit être une chaîne de caractères. Reçu: {address}")
        return jsonify({'message': "address doit être une chaîne de caractères."}), 400

    postal_code = dynamic_attributes.get('postal_code')
    current_app.logger.debug(f"postal_code brut: {postal_code}, type: {type(postal_code)}")
    if postal_code is not None and not isinstance(postal_code, str):
        current_app.logger.warning(f"Validation échouée: postal_code doit être une chaîne de caractères. Reçu: {postal_code}")
        return jsonify({'message': "postal_code doit être une chaîne de caractères."}), 400

    latitude = None
    if 'latitude' in dynamic_attributes and dynamic_attributes['latitude'] is not None:
        current_app.logger.debug(f"latitude brut: {dynamic_attributes['latitude']}, type: {type(dynamic_attributes['latitude'])}")
        try:
            latitude = float(dynamic_attributes['latitude'])
            current_app.logger.debug(f"latitude converti: {latitude}, type: {type(latitude)}")
        except (ValueError, TypeError):
            current_app.logger.warning(f"Validation échouée: latitude doit être un nombre décimal valide. Reçu: {dynamic_attributes['latitude']}")
            return jsonify({'message': "latitude doit être un nombre décimal valide."}), 400

    longitude = None
    if 'longitude' in dynamic_attributes and dynamic_attributes['longitude'] is not None:
        current_app.logger.debug(f"longitude brut: {dynamic_attributes['longitude']}, type: {type(dynamic_attributes['longitude'])}")
        try:
            longitude = float(dynamic_attributes['longitude'])
            current_app.logger.debug(f"longitude converti: {longitude}, type: {type(longitude)}")
        except (ValueError, TypeError):
            current_app.logger.warning(f"Validation échouée: longitude doit être un nombre décimal valide. Reçu: {dynamic_attributes['longitude']}")
            return jsonify({'message': "longitude doit être un nombre décimal valide."}), 400

    property_type = PropertyType.query.get(property_type_id)
    if not property_type:
        current_app.logger.warning(f"Validation échouée: Type de propriété invalide ou non trouvé. ID: {property_type_id}")
        return jsonify({'message': "Type de propriété invalide ou non trouvé."}), 400

    status_input = dynamic_attributes.get('status') or data.get('status')
    current_app.logger.debug(f"status brut (ID ou Slug attendu): {status_input}, type: {type(status_input)}")
    
    status_obj = None
    
    # Tentative de récupération stricte par ID prioritairement
    try:
        if isinstance(status_input, int) or (isinstance(status_input, str) and status_input.isdigit()):
            status_id = int(status_input)
            status_obj = PropertyStatus.query.get(status_id)
    except (ValueError, TypeError):
        pass

    # Si ce n'est pas un ID valide ou qu'on n'a rien trouvé, c'est une erreur de validation
    if not status_obj:
        current_app.logger.warning(f"Validation échouée: ID de statut ou code statut invalide ou non trouvé. Reçu: {status_input}")
        return jsonify({'message': "Statut de propriété invalide ou non trouvé. Veuillez fournir un ID de statut valide défini par un entier."}), 400

    # Fallback pour le champ legacy 'status' de type ENUM
    name_to_slug_legacy = {
        'à vendre': 'for_sale',
        'a vendre': 'for_sale',
        'à louer': 'for_rent',
        'a louer': 'for_rent',
        'vefa': 'vefa',
        'bailler': 'bailler',
        'location-vente': 'location_vente',
        'vendu': 'sold',
        'loué': 'rented'
    }
    legacy_status_slug = name_to_slug_legacy.get(status_obj.name.strip().lower(), 'for_sale')

    # L'agent crée un bien pour lui-même, donc owner_id = agent_id = current_user_id
    new_property = Property(
        owner_id=current_user_id,  # L'agent est le propriétaire
        agent_id=current_user_id,  # L'agent est aussi celui qui a créé le bien
        property_type_id=property_type_id,
        title=title,
        description=description,
        status=legacy_status_slug,
        status_id=status_obj.id, # Lier strictement l'ID du statut
        price=price,
        address=address,
        city=city,
        postal_code=postal_code,
        latitude=latitude,
        longitude=longitude,
        attributes=dynamic_attributes
    )
    try:
        current_app.logger.debug(f"Nouvelle propriété créée (avant commit): {new_property}")
        db.session.add(new_property)
        db.session.flush()
        current_app.logger.debug(f"ID de la nouvelle propriété après flush: {new_property.id}")

        image_urls = data.get('image_urls', [])
        current_app.logger.debug(f"URLs d'images à enregistrer: {image_urls}")
        if image_urls:
            for i, image_url in enumerate(image_urls):
                new_image = PropertyImage(
                    property_id=new_property.id,
                    image_url=image_url,
                    display_order=i
                )
                db.session.add(new_image)
                current_app.logger.debug(f"Image ajoutée: {image_url}")

        db.session.commit()
        current_app.logger.info("Bien immobilier créé avec succès et commité.")

        # NOTE: Le matching engine (alertes) n'est plus déclenché ici.
        # Il sera déclenché uniquement lors de la VALIDATION par l'admin.

        return jsonify({'message': "Bien immobilier créé avec succès.", 'property': new_property.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création du bien immobilier (rollback): {e}", exc_info=True)
        return jsonify({'message': "Erreur lors de la création du bien immobilier.", 'error': str(e)}), 500

@agents_bp.route('/my-properties', methods=['GET'])
@jwt_required()
def get_agent_created_properties():
    """
    Récupère tous les biens immobiliers créés par cet agent.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    if not agent:
        return jsonify({'message': "Utilisateur non trouvé."}), 404
    
    if str(agent.role) != 'agent':
        return jsonify({'message': f"Accès non autorisé. Votre rôle est '{agent.role}', mais 'agent' est requis."}), 403

    # Récupérer toutes les propriétés créées par cet agent
    properties = Property.query.options(selectinload(Property.images), selectinload(Property.owner)).filter_by(agent_id=current_user_id).filter(Property.deleted_at == None).all()
    
    properties_with_details = []
    for prop in properties:
        property_dict = prop.to_dict()
        property_dict['image_urls'] = [image.image_url for image in prop.images]
        
        # Ajouter les informations sur le propriétaire
        if prop.owner:
            property_dict['owner_info'] = {
                'owner_id': prop.owner.id,
                'owner_name': f"{prop.owner.first_name} {prop.owner.last_name}",
                'owner_email': prop.owner.email
            }
        
        properties_with_details.append(property_dict)

    # Retourner directement la liste pour être cohérent avec les autres routes
    return jsonify(properties_with_details), 200


@agents_bp.route('/upload_image', methods=['POST'])
@jwt_required()
def upload_image_for_agent():
    """
    Permet aux agents d'uploader des images pour les biens immobiliers.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé."}), 403

    # Même logique que pour les propriétaires et admin
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400

    from app.utils.cloudinary_utils import upload_image # Tardif
    
    try:
        secure_url = upload_image(file, folder="woora_properties") # Dossier properties
        
        if secure_url:
            return jsonify({'url': secure_url}), 200
        else:
             return jsonify({'error': 'Erreur interne Cloudinary'}), 500

    except Exception as e:
        current_app.logger.error(f"Upload error: {e}")
        return jsonify({'error': 'Erreur interne'}), 500

@agents_bp.route('/properties/<int:property_id>', methods=['PUT'])
@jwt_required()
def update_agent_created_property(property_id):
    """
    Permet à un agent de modifier un bien immobilier qu'il a créé.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé. Seuls les agents peuvent modifier leurs biens créés."}), 403

    # Vérifier que le bien existe et a été créé par cet agent
    property = Property.query.filter_by(id=property_id, agent_id=current_user_id).first()
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé ou vous n'êtes pas l'agent créateur."}), 404

    data = request.get_json()
    if not data:
        return jsonify({'message': "Corps de la requête manquant ou invalide."}), 400
        
    current_app.logger.debug(f"Données reçues pour la mise à jour du bien {property_id} par l'agent: {data}")

    attributes_data = data.get('attributes')
    if attributes_data:
        # Mise à jour des champs statiques (même logique que pour les propriétaires)
        if 'title' in attributes_data:
            property.title = attributes_data['title']
        
        if 'price' in attributes_data:
            try:
                property.price = float(attributes_data['price']) if attributes_data['price'] is not None else None
            except (ValueError, TypeError):
                return jsonify({'message': "Le prix doit être un nombre valide."}), 400
        
        if 'status' in attributes_data:
            raw_status = attributes_data['status']
            if isinstance(raw_status, int) or (isinstance(raw_status, str) and raw_status.isdigit()):
                status_obj = PropertyStatus.query.get(int(raw_status))
                if status_obj:
                    property.status_id = status_obj.id
                    # Fallback pour la colonne legacy `status`
                    name_to_slug = {'à vendre': 'for_sale', 'a vendre': 'for_sale', 'à louer': 'for_rent', 'a louer': 'for_rent', 'vefa': 'vefa', 'bailler': 'bailler', 'location-vente': 'location_vente', 'vendu': 'sold', 'loué': 'rented'}
                    property.status = name_to_slug.get(status_obj.name.strip().lower(), 'for_sale')
                else:
                    return jsonify({'message': 'Statut de propriété invalide ou non trouvé. Veuillez fournir un ID de statut valide défini par un entier.'}), 400
            else:
                 return jsonify({'message': "Statut de propriété invalide. L'usage d'identifiants (IDs) est désormais strictement requis pour le statut."}), 400
            
        if 'description' in attributes_data:
            property.description = attributes_data.get('description')
            
        if 'address' in attributes_data:
            property.address = attributes_data.get('address')
            
        if 'city' in attributes_data:
            property.city = attributes_data.get('city')
            
        if 'postal_code' in attributes_data:
            property.postal_code = attributes_data.get('postal_code')
            
        # Gestion des coordonnées GPS
        if 'latitude' in attributes_data:
            lat_val = attributes_data.get('latitude')
            try:
                property.latitude = float(lat_val) if lat_val and str(lat_val).lower() != 'null' else None
            except (ValueError, TypeError):
                return jsonify({'message': 'latitude doit être un nombre décimal valide.'}), 400
                
        if 'longitude' in attributes_data:
            lon_val = attributes_data.get('longitude')
            try:
                property.longitude = float(lon_val) if lon_val and str(lon_val).lower() != 'null' else None
            except (ValueError, TypeError):
                return jsonify({'message': 'longitude doit être un nombre décimal valide.'}), 400

        # Mise à jour du champ JSON attributes pour rétro-compatibilité temporaire
        if property.attributes is None:
            property.attributes = {}
        
        property.attributes.update(attributes_data)
        flag_modified(property, "attributes")

        # --- NEW EAV MIGRATION LOGIC ---
        # Sauvegarde robuste des caractéristiques dans la nouvelle table PropertyValues
        try:
            save_property_eav_values(property.id, attributes_data)
        except Exception as e:
            current_app.logger.error(f"EAV Saving failed: {e}")
            raise e
        # -------------------------------

    # Gestion des images (même logique que pour les propriétaires)
    if 'image_urls' in data:
        PropertyImage.query.filter_by(property_id=property.id).delete()
        db.session.flush()

        image_urls = data.get('image_urls', [])
        for i, image_url in enumerate(image_urls):
            new_image = PropertyImage(
                property_id=property.id,
                image_url=image_url,
                display_order=i
            )
            db.session.add(new_image)

    try:
        db.session.commit()
        
        updated_property_dict = property.to_dict()
        
        return jsonify({
            'message': "Bien immobilier mis à jour avec succès par l'agent.",
            'property': updated_property_dict
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la mise à jour du bien immobilier par l'agent (rollback): {e}", exc_info=True)
        return jsonify({'message': "Erreur lors de la mise à jour du bien immobilier.", 'error': str(e)}), 500

@agents_bp.route('/properties/<int:property_id>', methods=['DELETE'])
@jwt_required()
def delete_agent_created_property(property_id):
    """
    Permet à un agent de supprimer un bien immobilier qu'il a créé.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé. Seuls les agents peuvent supprimer leurs biens créés."}), 403

    # Vérifier que le bien existe et a été créé par cet agent
    property = Property.query.filter_by(id=property_id, agent_id=current_user_id).first()
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé ou vous n'êtes pas l'agent créateur."}), 404

    try:
        db.session.delete(property)
        db.session.commit()
        return jsonify({'message': "Bien immobilier supprimé avec succès par l'agent."}), 204
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la suppression du bien immobilier par l'agent (rollback): {e}", exc_info=True)
        return jsonify({'message': "Erreur lors de la suppression du bien immobilier.", 'error': str(e)}), 500

@agents_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_agent_created_property_details(property_id):
    """
    Récupère les détails d'un bien immobilier créé par l'agent.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)
    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès non autorisé. Seuls les agents peuvent voir les détails de leurs biens créés."}), 403

    # Vérifier que le bien existe et a été créé par cet agent
    property = Property.query.filter_by(id=property_id, agent_id=current_user_id).first()
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé ou vous n'êtes pas l'agent créateur."}), 404

    property_dict = property.to_dict()
    property_dict['image_urls'] = [img.image_url for img in property.images] 
    return jsonify(property_dict), 200

# ==============================================================================
# GESTION DES REQUÊTES / ALERTES PROPRIÉTÉS POUR AGENTS
# ==============================================================================

@agents_bp.route('/property-requests', methods=['POST'])
@jwt_required()
def create_agent_property_request():
    """
    Permet à un AGENT de soumettre une alerte / demande de bien.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)

    if not agent or agent.role != 'agent':
        return jsonify({'message': "Accès refusé. Seuls les agents peuvent créer des alertes ici."}), 403

    data = request.get_json()
    if not data:
        return jsonify({'message': "Données manquantes."}), 400

    # 1. On récupère la chaîne de caractères JSON
    request_details_str = data.get('request_details', '{}')
    try:
        # 2. On la décode pour la transformer en dictionnaire Python
        request_values = json.loads(request_details_str)
    except json.JSONDecodeError:
        return jsonify({'message': "Le format des détails de la requête est invalide."}), 400

    # 3. On extrait les valeurs pour les colonnes structurées
    city = request_values.get('city')
    min_price = request_values.get('min_price')
    max_price = request_values.get('max_price')

    # --- NOUVEAU : Validation 50% Remplissage ---
    # base_fields : city, min_price (ou max_price)
    # plus les attributs additionnels dans request_values
    
    total_fields = 2 # Ville, Prix (on compte la fourchette comme 1 champ sémantique)
    filled_fields = 0
    
    if city: filled_fields += 1
    if min_price or max_price: filled_fields += 1
    
    # On évalue les autres attributs dynamiques (ex: chambres, salles de bain)
    for key, val in request_values.items():
        if key not in ['city', 'min_price', 'max_price']:
            total_fields += 1
            # Si val est renseigné (non null, non string vide)
            if val is not None and str(val).strip() != '':
                 filled_fields += 1
                 
    completion_ratio = filled_fields / max(1, total_fields)
    
    if completion_ratio < 0.5:
        return jsonify({'message': "Veuillez renseigner au moins 50% des critères pour valider cette alerte."}), 400
    # --- FIN VALIDATION ---

    # 4. On crée l'objet PropertyRequest
    # On réutilise la colonne customer_id pour l'ID de l'agent (car User table unifiée)
    new_request = PropertyRequest(
        customer_id=current_user_id,
        property_type_id=data.get('property_type_id'),
        
        city=city,
        min_price=min_price,
        max_price=max_price,
        
        request_details=request_details_str, 
        
        status='new'
    )

    try:
        db.session.add(new_request)
        db.session.commit()
        return jsonify({'message': "Alerte agent enregistrée avec succès."}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur création alerte agent: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500

@agents_bp.route('/property-requests', methods=['GET'])
@jwt_required()
def get_agent_property_requests():
    """
    Récupère l'historique des alertes pour l'agent connecté.
    """
    current_user_id = get_jwt_identity()
    agent = User.query.get(current_user_id)

    if not agent or agent.role != 'agent':
        return jsonify({'message': 'Accès refusé.'}), 403

    # On récupère TOUTES les demandes de l'agent (historique complet), les plus récentes en premier
    requests = PropertyRequest.query.filter_by(customer_id=current_user_id).order_by(PropertyRequest.created_at.desc()).all()
    
    return jsonify([req.to_dict() for req in requests]), 200

@agents_bp.route('/property-requests/<int:request_id>', methods=['DELETE'])
@jwt_required()
def delete_agent_property_request(request_id):
    """
    Permet à un AGENT de supprimer (fermer) une de ses alertes.
    """
    current_user_id = get_jwt_identity()
    
    # On cherche la requête (vérification que c'est bien celle de l'agent connecté)
    req = PropertyRequest.query.filter_by(id=request_id, customer_id=current_user_id).first()
    
    if not req:
        return jsonify({'message': "Alerte non trouvée ou accès refusé."}), 404
        
    try:
        # Fermeture (Soft Delete / Status Update)
        req.status = 'closed'
        req.archived_at = datetime.utcnow()
        req.archived_by = current_user_id
        
        db.session.commit()
        return jsonify({'message': "Alerte agent supprimée avec succès."}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur suppression alerte agent: {e}")
        return jsonify({'message': "Erreur serveur."}), 500
