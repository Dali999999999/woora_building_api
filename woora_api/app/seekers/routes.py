# app/seekers/routes.py

from flask import Blueprint, request, jsonify, current_app
from app.models import Property, User, VisitRequest, Referral, PropertyRequest, UserFavorite, AgentReview
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

from sqlalchemy import or_
import json

@seekers_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_seeker():
    """
    Endpoint pour les chercheurs.
    Récupère les biens 'à vendre' ou 'à louer' avec filtrage avancé.
    Paramètres GET supportés :
    - search (text): Recherche dans titre, ville, adresse.
    - min_price (number)
    - max_price (number)
    - property_type_id (int)
    - filters (json string): Filtres dynamiques pour les attributs (ex: {"Piscine": "Oui"})
    """
    
    # 1. Base Query : Statut Actif ET Validé par l'admin
    query = Property.query.filter(
        Property.status.in_(['for_sale', 'for_rent']),
        Property.is_validated == True
    )

    # 2. Recherche Textuelle (Titre, Ville, Adresse)
    search_query = request.args.get('search', '').strip()
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(or_(
            Property.title.ilike(search_pattern),
            Property.city.ilike(search_pattern),
            Property.address.ilike(search_pattern)
        ))

    # 3. Filtre par Type de Bien
    try:
        property_type_id = request.args.get('property_type_id')
        if property_type_id:
            query = query.filter(Property.property_type_id == int(property_type_id))
    except (ValueError, TypeError):
        pass # Ignorer si l'ID n'est pas un entier valide

    # 4. Filtre par Prix (Min / Max)
    try:
        min_price = request.args.get('min_price')
        if min_price:
            query = query.filter(Property.price >= float(min_price))
        
        max_price = request.args.get('max_price')
        if max_price:
            query = query.filter(Property.price <= float(max_price))
    except (ValueError, TypeError):
        pass

    # 5. Récupération des candidats pour filtrage "Fuzzy" (Attributs)
    # On récupère tous les candidats qui correspondent aux critères stricts (Prix, Ville, Type)
    # pour appliquer la logique "au moins 3 correspondances" en Python.
    candidate_properties = query.order_by(Property.created_at.desc()).all()
    
    final_properties = []
    
    filters_json = request.args.get('filters')
    if filters_json:
        try:
            dynamic_filters = json.loads(filters_json)
            if isinstance(dynamic_filters, dict) and dynamic_filters:
                # Logique Fuzzy Matching
                target_match_count = min(3, len(dynamic_filters))
                
                for prop in candidate_properties:
                    match_count = 0
                    prop_attrs = prop.attributes or {}
                    
                    for key, value in dynamic_filters.items():
                        # Comparaison souple (String vs Int etc.)
                        if key in prop_attrs and str(prop_attrs[key]) == str(value):
                            match_count += 1
                            
                    if match_count >= target_match_count:
                        final_properties.append(prop)
                        
            else:
                final_properties = candidate_properties
        except json.JSONDecodeError:
             final_properties = candidate_properties
    else:
        final_properties = candidate_properties

    # 6. Pagination Manuelle
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    total = len(final_properties)
    start = (page - 1) * per_page
    end = start + per_page
    
    sliced_properties = final_properties[start:end]
    total_pages = (total + per_page - 1) // per_page

    return jsonify({
        'properties': [p.to_dict() for p in sliced_properties],
        'total': total,
        'pages': total_pages,
        'current_page': page
    }), 200

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
    Cette version décode le JSON 'request_details' pour remplir les colonnes
    structurées de la base de données.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)

    if not customer or customer.role != 'customer':
        return jsonify({'message': "Accès refusé."}), 403

    data = request.get_json()
    if not data:
        return jsonify({'message': "Données manquantes."}), 400

    # --- DÉBUT DE LA LOGIQUE CORRIGÉE ---

    # 1. On récupère la chaîne de caractères JSON envoyée par Flutter
    request_details_str = data.get('request_details', '{}')
    try:
        # 2. On la décode pour la transformer en dictionnaire Python
        request_values = json.loads(request_details_str)
    except json.JSONDecodeError:
        return jsonify({'message': "Le format des détails de la requête est invalide."}), 400

    # 3. On extrait les valeurs pour les colonnes structurées
    # On utilise .get() pour récupérer les valeurs sans causer d'erreur si elles sont absentes
    city = request_values.get('city')
    min_price = request_values.get('min_price')
    max_price = request_values.get('max_price')

    # 4. On crée l'objet PropertyRequest en assignant chaque valeur à la bonne colonne
    new_request = PropertyRequest(
        customer_id=current_user_id,
        property_type_id=data.get('property_type_id'), # Vient du niveau supérieur du JSON
        
        city=city,
        min_price=min_price,
        max_price=max_price,
        
        # On sauvegarde la chaîne JSON complète pour référence et pour les attributs dynamiques
        request_details=request_details_str, 
        
        status='new'
    )

    # --- FIN DE LA LOGIQUE CORRIGÉE ---

    try:
        db.session.add(new_request)
        db.session.commit()
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

# ===================================================================
# GESTION DES FAVORIS
# ===================================================================

@seekers_bp.route('/favorites/<int:property_id>', methods=['POST'])
@jwt_required()
def toggle_favorite(property_id):
    """
    Ajoute ou retire un bien des favoris de l'utilisateur connecté.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    # Vérifier l'existence du bien
    property_obj = Property.query.get(property_id)
    if not property_obj:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404

    # Vérifier si déjà en favori
    existing_fav = UserFavorite.query.filter_by(user_id=current_user_id, property_id=property_id).first()

    try:
        if existing_fav:
            db.session.delete(existing_fav)
            db.session.commit()
            return jsonify({'message': "Bien retiré des favoris.", 'is_favorite': False}), 200
        else:
            new_fav = UserFavorite(user_id=current_user_id, property_id=property_id)
            db.session.add(new_fav)
            db.session.commit()
            return jsonify({'message': "Bien ajouté aux favoris.", 'is_favorite': True}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur favoris: {e}")
        return jsonify({'message': "Erreur lors de la mise à jour des favoris."}), 500

@seekers_bp.route('/favorites', methods=['GET'])
@jwt_required()
def get_favorite_properties():
    """
    Récupère la liste des biens favoris de l'utilisateur.
    """
    current_user_id = get_jwt_identity()
    
    # Jointure pour récupérer les propriétés favorites
    favorites = db.session.query(Property).join(UserFavorite).filter(UserFavorite.user_id == current_user_id).all()
    
    return jsonify([p.to_dict() for p in favorites]), 200

# ===================================================================
# GESTION DES AVIS AGENTS
# ===================================================================

@seekers_bp.route('/agents/<int:agent_id>/reviews', methods=['POST'])
@jwt_required()
def add_agent_review(agent_id):
    """
    Permet à un client de laisser un avis sur un agent.
    """
    current_user_id = get_jwt_identity()
    customer = User.query.get(current_user_id)
    agent = User.query.get(agent_id)

    if not agent or agent.role != 'agent':
        return jsonify({'message': "Agent non trouvé."}), 404

    data = request.get_json()
    rating = data.get('rating')
    comment = data.get('comment')

    if not rating or not isinstance(rating, int) or not (1 <= rating <= 5):
        return jsonify({'message': "La note doit être un entier entre 1 et 5."}), 400

    # Optionnel : Vérifier si le client a déjà noté cet agent
    existing_review = AgentReview.query.filter_by(agent_id=agent_id, customer_id=current_user_id).first()
    if existing_review:
        # Mise à jour de l'avis existant ou rejet ?
        # Pour l'instant, rejetons la création de multiples avis
        return jsonify({'message': "Vous avez déjà donné votre avis sur cet agent."}), 400

    new_review = AgentReview(
        agent_id=agent_id,
        customer_id=current_user_id,
        rating=rating,
        comment=comment
    )

    try:
        db.session.add(new_review)
        db.session.commit()
        return jsonify({'message': "Avis enregistré avec succès."}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur avis agent: {e}")
        return jsonify({'message': "Erreur interne."}), 500

@seekers_bp.route('/agents/<int:agent_id>/reviews', methods=['GET'])
@jwt_required()
def get_agent_reviews_list(agent_id):
    """
    Récupère les avis d'un agent.
    """
    reviews = AgentReview.query.filter_by(agent_id=agent_id).order_by(AgentReview.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reviews]), 200
