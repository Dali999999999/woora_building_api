# app/seekers/routes.py

from flask import Blueprint, request, jsonify, current_app
from app.models import Property, User, VisitRequest, Referral, PropertyRequest, UserFavorite, AgentReview
from app import db # Assurez-vous que l'import de 'db' est correct
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from app.models import ServiceFee

# Assurez-vous que le chemin vers vos utilitaires d'email est correct
try:
    from app.utils.email_utils import send_new_visit_request_notification, send_referral_used_notification, send_visit_request_confirmation_to_customer
except ImportError:
    # Crée des fonctions factices si le fichier n'existe pas encore pour éviter une erreur d'import
    def send_new_visit_request_notification(*args, **kwargs): pass
    def send_referral_used_notification(*args, **kwargs): pass
    def send_visit_request_confirmation_to_customer(*args, **kwargs): pass


seekers_bp = Blueprint('seekers', __name__, url_prefix='/seekers')

from sqlalchemy import or_, desc, case, func, cast, String, Numeric
from sqlalchemy.orm import selectinload # Optimization N+1
import json

@seekers_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_properties_for_seeker():
    """
    Endpoint pour les chercheurs.
    Récupère les biens 'à vendre' ou 'à louer' avec filtrage avancé (SQL pur).
    Utilise un système de Scoring pour les filtres secondaires (attributs) et la pagination SQL.
    """
    
    # --- 1. Base Query ---
    # On commence par définir les colonnes de base et les relations à charger
    base_query = Property.query.options(
        selectinload(Property.images),
        selectinload(Property.property_type),
        selectinload(Property.owner)
    ).join(Property.owner).filter(
        Property.is_validated == True,
        Property.deleted_at == None,
        User.deleted_at == None
    )

    # --- 1.1 Filtre par Statut (Dynamique) ---
    status_param = request.args.get('status')
    if status_param and status_param != 'null' and status_param != '':
        base_query = base_query.filter(Property.status == status_param)
    else:
        # Comportement par défaut : Vente et Location
        base_query = base_query.filter(Property.status.in_(['for_sale', 'for_rent']))

    # --- 2. Filtres "Durs" (Exclusion) ---
    # Ces filtres éliminent les résultats qui ne correspondent PAS.
    
    # Recherche Textuelle
    search_query = request.args.get('search', '').strip()
    if search_query:
        search_pattern = f"%{search_query}%"
        base_query = base_query.filter(or_(
            Property.title.ilike(search_pattern),
            Property.city.ilike(search_pattern),
            Property.address.ilike(search_pattern)
        ))

    # Type de Bien
    try:
        property_type_id = request.args.get('property_type_id')
        if property_type_id:
            base_query = base_query.filter(Property.property_type_id == int(property_type_id))
    except (ValueError, TypeError):
        pass

    # Prix Min / Max
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
    # Pour chaque filtre dynamique reçu, on exige que la propriété possède cet attribut ET cette valeur.
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
                            PropertyValue.value_decimal == str(value) # value_decimal is string/numeric in DB
                        )
                    else:
                        # String et fallback
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
    # Tri par date classique
    query = base_query.order_by(Property.created_at.desc())

    # Pagination DB stricte
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # La méthode .paginate() fait un COUNT(*) optimisé puis un LIMIT/OFFSET
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    properties = pagination.items

    return jsonify({
        'properties': [p.to_dict() for p in properties],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    }), 200

@seekers_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_property_details_for_seeker(property_id):
    """
    Récupère les détails d'un bien immobilier pour un SEEKER.
    PRIVACY: Exclut les informations sensibles (agent, owner).
    """
    user_id = get_jwt_identity()
    
    property_obj = Property.query.options(
        selectinload(Property.images),
        selectinload(Property.property_type)
    ).get(property_id)
    
    if not property_obj:
        return jsonify({'message': "Bien immobilier non trouvé."}), 404
    
    # Récupérer les données du bien
    property_dict = property_obj.to_dict()
    
    # SÉCURITÉ CRITIQUE: Supprimer toutes les informations sensibles
    property_dict.pop('created_by_agent', None)
    property_dict.pop('owner_details', None)
    property_dict.pop('owner_id', None)
    property_dict.pop('created_by', None)
    
    # --- CHECK FIRST VISIT REQUEST ---
    # Vérifie si l'utilisateur a DÉJÀ fait une demande pour ce bien (status 'pending', 'confirmed', 'accepted', 'rejected', etc.)
    previous_requests_count = VisitRequest.query.filter_by(
        customer_id=user_id,
        property_id=property_id
    ).count()
    
    # Si count == 0, c'est sa toute première demande -> Eligible au parrainage
    property_dict['is_first_visit_request'] = (previous_requests_count == 0)
    
    return jsonify(property_dict), 200

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

    # --- NOUVEAU : Validation 50% Remplissage ---
    total_fields = 2 # Ville, Prix (on compte la fourchette comme 1 champ logique)
    filled_fields = 0
    
    if city: filled_fields += 1
    if min_price or max_price: filled_fields += 1
    
    for key, val in request_values.items():
        if key not in ['city', 'min_price', 'max_price']:
            total_fields += 1
            if val is not None and str(val).strip() != '':
                 filled_fields += 1
                 
    completion_ratio = filled_fields / max(1, total_fields)
    
    if completion_ratio < 0.5:
        return jsonify({'message': "Veuillez renseigner au moins 50% des critères pour valider cette alerte."}), 400
    # --- FIN VALIDATION ---

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

    # On récupère TOUTES les demandes du client (historique complet), les plus récentes en premier
    requests = PropertyRequest.query.filter_by(customer_id=current_user_id).order_by(PropertyRequest.created_at.desc()).all()
    
    return jsonify([req.to_dict() for req in requests]), 200

@seekers_bp.route('/property-requests/<int:request_id>', methods=['DELETE'])
@jwt_required()
def delete_property_request(request_id):
    """
    Permet à un client ou agent de supprimer (fermer) une alerte.
    """
    current_user_id = get_jwt_identity()
    
    # On cherche la requête
    req = PropertyRequest.query.filter_by(id=request_id, customer_id=current_user_id).first()
    
    if not req:
        return jsonify({'message': "Alerte non trouvée ou accès refusé."}), 404
        
    try:
        # Option 1: Suppression définitive (Hard Delete)
        # db.session.delete(req)
        
        # Option 2: Fermeture (Soft Delete / Status Update) - Préférable pour l'historique
        req.status = 'closed'
        req.archived_at = datetime.utcnow()
        req.archived_by = current_user_id
        
        db.session.commit()
        return jsonify({'message': "Alerte supprimée avec succès."}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur suppression alerte: {e}")
        return jsonify({'message': "Erreur serveur."}), 500

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


# ===================================================================
# DEMANDES DE VISITE - SEEKER
# ===================================================================

@seekers_bp.route('/properties/<int:property_id>/visit-requests', methods=['POST'])
@jwt_required()
def submit_visit_request(property_id):
    """
    Permet à un seeker de soumettre une demande de visite pour un bien.
    """
    try:
        user_id = get_jwt_identity()
        
        # VALIDATION: Seuls les customers peuvent demander des visites
        user = User.query.get(user_id)
        if not user or user.role != 'customer':
            return jsonify({"error": "Seuls les clients peuvent demander des visites."}), 403
        
        data = request.get_json()
        
        # Validation des données requises
        if not data or 'requested_datetime' not in data:
            return jsonify({"error": "La date et l'heure sont requises."}), 400
        
        # Vérifier que la propriété existe et est validée
        property_obj = Property.query.get(property_id)
        if not property_obj:
            return jsonify({'error': 'Propriété non trouvée.'}), 404
        
        if not property_obj.is_validated:
            return jsonify({'error': 'Cette propriété n\'est pas encore validée.'}), 400
        
        # Vérifier que la propriété est disponible
        if property_obj.status not in ['for_sale', 'for_rent', 'vefa', 'bailler', 'location_vente']:
            return jsonify({'error': 'Cette propriété n\'est plus disponible.'}), 400
        
        # Parser la date/heure
        try:
            requested_dt = datetime.fromisoformat(data['requested_datetime'].replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return jsonify({'error': 'Format de date invalide.'}), 400
        
        # Vérifier que la date est dans le futur
        if requested_dt <= datetime.utcnow():
            return jsonify({'error': 'La date doit être dans le futur.'}), 400
        
        # Vérifier s'il y a déjà une demande en cours (PENDING, CONFIRMED, ou ACCEPTED)
        active_request = VisitRequest.query.filter(
            VisitRequest.customer_id == user_id,
            VisitRequest.property_id == property_id,
            VisitRequest.status.in_(['pending', 'confirmed', 'accepted'])
        ).first()

        if active_request:
            return jsonify({'error': 'Vous avez déjà une demande en cours pour ce bien.'}), 400

        # Vérifier si c'est la TOUTE PREMIÈRE demande de visite pour ce bien
        # On cherche s'il existe N'IMPORTE QUELLE demande précédente (même rejetée, annulée, ou completed)
        previous_requests_count = VisitRequest.query.filter_by(
            customer_id=user_id,
            property_id=property_id
        ).count()

        is_first_request = (previous_requests_count == 0)

        # Vérification du solde de pass de visite
        if user.visit_passes <= 0:
            return jsonify({'error': "Vous n'avez pas assez de pass de visite. Veuillez en acheter."}), 400

        referral_id = None
        # Gestion du code de parrainage - UNIQUEMENT SI C'EST LA PREMIÈRE DEMANDE
        if is_first_request:
            if data.get('referral_code'):
                referral_code_input = data['referral_code'].strip()
                referral = Referral.query.filter_by(referral_code=referral_code_input).first()
                
                if not referral:
                     # Code invalide : on retourne une erreur explicite
                     return jsonify({'error': 'Code de parrainage invalide.', 'message': 'Code de parrainage invalide.'}), 400

                # VÉRIFICATION USAGE UNIQUE (Globale)
                # On vérifie si ce code a DÉJÀ été utilisé par n'importe qui
                usage_count = VisitRequest.query.filter_by(referral_id=referral.id).count()
                if usage_count > 0:
                     return jsonify({'error': 'Ce code de parrainage a déjà été utilisé.', 'message': 'Ce code de parrainage a déjà été utilisé.'}), 400

                # Si valide et non utilisé, on l'associe
                referral_id = referral.id
                
                # Notification à l'agent parrain
                try:
                    send_referral_used_notification(
                        referral.agent.email,
                        f"{user.first_name} {user.last_name}",
                        property_obj.title
                    )
                except Exception as e:
                    current_app.logger.warning(f"Échec envoi email parrainage: {e}")
        else:
            # Si ce n'est pas la première demande, on ignore le code pour éviter les erreurs bloquantes
            pass
        
        # Créer la demande de visite
        visit_request = VisitRequest(
            customer_id=user_id,
            property_id=property_id,
            requested_datetime=requested_dt,
            message=data.get('message'),
            referral_id=referral_id,
            status='pending'
        )
        
        # Déduction du pass de visite
        user.visit_passes -= 1

        db.session.add(visit_request)
        db.session.commit()
        
        # Notification au propriétaire
        try:
            send_new_visit_request_notification(visit_request)
        except Exception as e:
            current_app.logger.warning(f"Échec envoi email notification: {e}")
        
        current_app.logger.info(f"Demande de visite créée: {visit_request.id} pour propriété {property_id} par user {user_id}")
        
        return jsonify({
            'message': 'Demande de visite envoyée avec succès.',
            'visit_request_id': visit_request.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création de la demande de visite: {e}", exc_info=True)
        return jsonify({'error': 'Erreur interne du serveur.'}), 500


@seekers_bp.route('/visit_requests', methods=['GET'])
@jwt_required()
def get_my_visit_requests():
    """
    Récupère toutes les demandes de visite du seeker connecté.
    """
    try:
        user_id = get_jwt_identity()
        
        # Récupérer toutes les demandes de l'utilisateur
        visit_requests = VisitRequest.query\
            .filter_by(customer_id=user_id)\
            .order_by(VisitRequest.created_at.desc())\
            .all()
        
        result = []
        for vr in visit_requests:
            result.append({
                'id': vr.id,
                'property_id': vr.property_id,
                'property_title': vr.property.title if vr.property else 'Titre indisponible',
                'property_address': vr.property.address if vr.property else None,
                'property_city': vr.property.city if vr.property else None,
                'requested_datetime': vr.requested_datetime.isoformat() if vr.requested_datetime else None,
                'status': vr.status,
                'message': vr.message,
                'created_at': vr.created_at.isoformat() if vr.created_at else None
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des demandes de visite: {e}", exc_info=True)
        return jsonify({'error': 'Erreur interne du serveur.'}), 500
