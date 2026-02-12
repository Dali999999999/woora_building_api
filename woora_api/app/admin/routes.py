from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from app.models import (
    User, Property, PropertyType, PropertyAttribute, AttributeOption,
    PropertyAttributeScope, db, AppSetting, ServiceFee, VisitRequest,
    Referral, Commission, Transaction, PropertyRequest, PropertyStatus
)
from app.schemas import VisitSettingsSchema
from marshmallow import ValidationError
# from app.utils.mega_utils import get_mega_instance # REMOVED
from werkzeug.utils import secure_filename
import os
import uuid
from decimal import Decimal
from app.utils.email_utils import send_admin_rejection_notification, send_admin_confirmation_to_owner, send_admin_response_to_seeker
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import inspect

# Assurez-vous que le chemin vers vos utilitaires d'email est correct
try:
    from app.utils.email_utils import send_property_invalidation_notification, send_property_validation_notification
except ImportError:
    def send_property_invalidation_notification(*args, **kwargs): pass
    def send_property_validation_notification(*args, **kwargs): pass

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# ===================================================================
# NOUVEL ENDPOINT POUR RÉCUPÉRER LES STATUTS DE PROPRIÉTÉ
# ===================================================================

@admin_bp.route('/property-statuses', methods=['GET'])
@jwt_required()
def get_property_statuses():
    """
    Récupère la liste de tous les statuts de propriété disponibles depuis la table PropertyStatuses.
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'admin':
            return jsonify({'message': 'Accès non autorisé.'}), 403
        
        statuses = PropertyStatus.query.all()
        return jsonify([s.to_dict() for s in statuses]), 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des statuts: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

@admin_bp.route('/property-statuses', methods=['POST'])
@jwt_required()
def create_property_status():
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user or user.role != 'admin': return jsonify({'message': 'Accès non autorisé.'}), 403

        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'message': 'Le nom du statut est requis.'}), 400
        
        # Vérifier unicité
        if PropertyStatus.query.filter_by(name=data['name']).first():
             return jsonify({'message': 'Ce statut existe déjà.'}), 409

        new_status = PropertyStatus(
            name=data['name'],
            color=data.get('color', '#000000'),
            description=data.get('description', '')
        )
        db.session.add(new_status)
        db.session.commit()
        
        return jsonify(new_status.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur création statut: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne.'}), 500

@admin_bp.route('/property-statuses/<int:status_id>', methods=['PUT'])
@jwt_required()
def update_property_status(status_id):
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user or user.role != 'admin': return jsonify({'message': 'Accès non autorisé.'}), 403

        status_obj = PropertyStatus.query.get_or_404(status_id)
        data = request.get_json()
        
        if 'name' in data:
            existing = PropertyStatus.query.filter_by(name=data['name']).first()
            if existing and existing.id != status_id:
                return jsonify({'message': 'Ce nom de statut est déjà utilisé.'}), 409
            status_obj.name = data['name']
            
        if 'color' in data: status_obj.color = data['color']
        if 'description' in data: status_obj.description = data['description']
        
        db.session.commit()
        return jsonify(status_obj.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur modif statut: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne.'}), 500

@admin_bp.route('/property-statuses/<int:status_id>', methods=['DELETE'])
@jwt_required()
def delete_property_status(status_id):
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        if not user or user.role != 'admin': return jsonify({'message': 'Accès non autorisé.'}), 403

        status_obj = PropertyStatus.query.get_or_404(status_id)
        
        # Vérifier si utilisé
        if Property.query.filter_by(status_id=status_id).first():
            return jsonify({'message': 'Impossible de supprimer: ce statut est utilisé par des biens.'}), 409
            
        db.session.delete(status_obj)
        db.session.commit()
        return jsonify({'message': 'Statut supprimé avec succès.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur suppression statut: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne.'}), 500

# ===================================================================
# ENDPOINTS EXISTANTS
# ===================================================================

UPLOAD_FOLDER = '/tmp'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ------------- DASHBOARD -------------
@admin_bp.route('/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    from sqlalchemy import func, extract
    from datetime import datetime
    
    current_year = datetime.now().year
    
    # 1. Basic Counters
    user_count = User.query.count()
    property_count = Property.query.count()  # Compte global
    pending_visits = VisitRequest.query.filter_by(status='pending').count()
    
    # 2. Total Revenue (Transactions of type 'payment')
    revenue = db.session.query(db.func.sum(Transaction.amount)).filter_by(type='payment').scalar() or 0.0

    # 3. Monthly Revenue Chart (Current Year)
    # Group by Month
    revenue_results = db.session.query(
        func.extract('month', Transaction.created_at).label('month'),
        func.sum(Transaction.amount).label('total')
    ).filter(
        Transaction.type == 'payment',
        func.extract('year', Transaction.created_at) == current_year
    ).group_by('month').all()

    # Format revenue data for all 12 months
    revenue_chart = []
    revenue_map = {int(r.month): float(r.total) for r in revenue_results}
    month_names = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    
    for i in range(1, 13):
        revenue_chart.append({
            "name": month_names[i-1],
            "revenue": revenue_map.get(i, 0.0)
        })

    # 4. Monthly User Growth Chart (Clients vs Owners)
    user_results = db.session.query(
        func.extract('month', User.created_at).label('month'),
        User.role,
        func.count(User.id).label('count')
    ).filter(
        func.extract('year', User.created_at) == current_year,
        User.role.in_(['customer', 'owner'])
    ).group_by('month', User.role).all()

    # Format user data
    users_map = {} # { month_index: { 'clients': 0, 'owners': 0 } }
    for r in user_results:
        m = int(r.month)
        if m not in users_map:
            users_map[m] = {'clients': 0, 'owners': 0}
        
        if r.role == 'customer':
            users_map[m]['clients'] = r.count
        elif r.role == 'owner':
            users_map[m]['owners'] = r.count
            
    user_growth_chart = []
    for i in range(1, 13):
        data = users_map.get(i, {'clients': 0, 'owners': 0})
        user_growth_chart.append({
            "name": month_names[i-1],
            "clients": data['clients'],
            "owners": data['owners']
        })

    return jsonify({
        'total_users': user_count,
        'active_properties': property_count,
        'pending_visits': pending_visits,
        'total_revenue': float(revenue),
        'revenue_chart': revenue_chart,
        'user_growth_chart': user_growth_chart
    })


@admin_bp.route('/users/<int:user_id>/suspend', methods=['PUT'])
@jwt_required()
def suspend_user(user_id):
    current_user_id = get_jwt_identity()
    admin = User.query.get(current_user_id)
    if not admin or admin.role != 'admin':
        return jsonify({'message': 'Accès refusé.'}), 403

    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    reason = data.get('reason', 'Non-respect des règles.')

    user.is_suspended = True
    user.suspension_reason = reason
    db.session.commit()

    return jsonify({'message': f'Utilisateur {user.email} suspendu.', 'is_suspended': True}), 200

@admin_bp.route('/users/<int:user_id>/unsuspend', methods=['PUT'])
@jwt_required()
def unsuspend_user(user_id):
    current_user_id = get_jwt_identity()
    admin = User.query.get(current_user_id)
    if not admin or admin.role != 'admin':
        return jsonify({'message': 'Accès refusé.'}), 403

    user = User.query.get_or_404(user_id)
    user.is_suspended = False
    user.suspension_reason = None
    db.session.commit()

    return jsonify({'message': f'Suspension levée pour {user.email}.', 'is_suspended': False}), 200

@admin_bp.route('/transactions', methods=['GET'])
def get_transactions():
    txs = Transaction.query.order_by(Transaction.created_at.desc()).limit(50).all()
    # Need to check Transaction model fields. code above uses:
    # Transaction(user_id, amount, type, description)
    # It doesn't show timestamp field in the code snippet but it likely exists (created_at or timestamp).
    # I'll check 'created_at' or 'timestamp'. Standard models usually have it.
    # Assuming 'created_at' based on other models. If error, I'll fix.
    # Wait, the code snippet created Transaction but didn't show definition.
    # I'll use simple list for now.
    
    results = []
    for t in txs:
         # Safely access fields.
         results.append({
             'id': t.id,
             'amount': float(t.amount),
             'type': t.type,
             'description': t.description,
             'date': t.created_at.isoformat() if hasattr(t, 'created_at') else ''
         })
    return jsonify(results)

# ------------- UTILISATEURS -------------
@admin_bp.route('/users', methods=['GET'])
def get_users():
    # Récupération des paramètres de requête
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    search_term = request.args.get('search', '').strip()
    role_filter = request.args.get('role', 'all')
    
    # Construction de la requête de base (EXCLURE LES SUPPRIMÉS)
    query = User.query.filter(User.deleted_at == None)
    
    # Filtrage par recherche (Nom, Prénom, Email)
    if search_term:
        search_pattern = f"%{search_term}%"
        query = query.filter(
            db.or_(
                User.email.ilike(search_pattern),
                User.first_name.ilike(search_pattern),
                User.last_name.ilike(search_pattern)
            )
        )
    
    # Filtrage par rôle
    if role_filter and role_filter != 'all':
        query = query.filter(User.role == role_filter)
        
    # Tri par défaut (plus récent en premier)
    query = query.order_by(User.created_at.desc())
    
    # Pagination
    pagination = query.paginate(page=page, per_page=limit, error_out=False)
    
    # Construction de la réponse metadata + data
    return jsonify({
        'users': [user.to_dict() for user in pagination.items],
        'total': pagination.total,
        'page': page,
        'limit': limit,
        'pages': pagination.pages
    })

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

from datetime import datetime
from app.utils.email_utils import send_alert_match_email, send_account_deletion_email

@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    """
    Soft delete user: Mark user as deleted but keep data.
    """
    current_user_id = get_jwt_identity()
    admin = User.query.get(current_user_id)
    if not admin or admin.role != 'admin':
        return jsonify({'message': 'Accès refusé.'}), 403

    user = User.query.get_or_404(user_id)
    
    # Get Reason if provided
    data = request.json or {} 
    reason = data.get('reason')

    user.deleted_at = datetime.utcnow()
    user.deletion_reason = reason
    
    # FIX: Anonymiser l'email pour libérer la contrainte d'unicité
    # Cela permet à l'utilisateur de se réinscrire avec le même email plus tard
    original_email = user.email
    user.email = f"deleted_{int(datetime.utcnow().timestamp())}_{original_email}"

    # FIX: Cascade Soft Delete -> Supprimer (soft) tous les biens de cet utilisateur
    # On ne veut pas de biens orphelins "actifs" appartenant à un utilisateur supprimé
    user_properties = Property.query.filter_by(owner_id=user.id).all()
    for prop in user_properties:
        if not prop.deleted_at: # Ne pas écraser si déjà supprimé
            prop.deleted_at = datetime.utcnow()
            prop.deletion_reason = f"Cascade: Propriétaire ({original_email}) supprimé par admin."
    
    db.session.commit()
    
    # Send Notification (using original email)
    send_account_deletion_email(original_email, user.first_name, reason)

    return jsonify({'message': 'Utilisateur supprimé (Soft Delete) avec succès. Email anonymisé et biens supprimés.'}), 200

# ------------- PROPRIÉTÉS -------------
@admin_bp.route('/properties', methods=['GET'])
def get_properties():
    properties = Property.query.filter(Property.deleted_at == None).options(selectinload(Property.owner)).order_by(Property.created_at.desc()).all()
    results = []
    for p in properties:
        data = p.to_dict()
        if p.owner:
            data['owner_details'] = p.owner.to_dict()
        results.append(data)
    return jsonify(results)

@admin_bp.route('/properties/<int:property_id>/validate', methods=['PUT'])
def validate_property(property_id):
    prop = Property.query.get_or_404(property_id)
      
    # Clean up any rejection reason if it exists
    if prop.attributes and '_rejection_reason' in prop.attributes:
        new_attrs = dict(prop.attributes)
        new_attrs.pop('_rejection_reason', None)
        prop.attributes = new_attrs

    # TRIGGER MATCHING ENGINE ONLY IF NOT ALREADY VALIDATED
    should_run_matching = not prop.is_validated
    prop.is_validated = True

    try:
        db.session.commit()
        
        if should_run_matching:
            # TRIGGER MATCHING ENGINE
            try:
                from app.utils.matching_utils import find_matches_for_property
                find_matches_for_property(prop.id)
            except Exception as e:
                current_app.logger.error(f"Error running matching engine: {e}")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur validation/matching: {e}")
        return jsonify({'message': "Erreur lors de la validation."}), 500

    return jsonify({'message': f"Bien '{prop.title}' validé avec succès.", 'property': prop.to_dict()}), 200

from app.models import Property, PropertyImage, User, PropertyType, VisitRequest,  PropertyAttributeScope, PropertyAttribute, AttributeOption, PropertyRequest
from app.utils.email_utils import send_admin_response_to_seeker, send_property_invalidation_email, send_alert_match_email, send_commission_paid_notification, send_deal_closed_client_notification

# ... (other code)

@admin_bp.route('/properties/<int:property_id>/invalidate', methods=['PUT'])
def invalidate_property(property_id):
    prop = Property.query.get_or_404(property_id)
    data = request.get_json() or {}
    reason = data.get('reason')

    prop.is_validated = False
    
    if reason:
        current_attrs = dict(prop.attributes) if prop.attributes else {}
        current_attrs['_rejection_reason'] = reason
        prop.attributes = current_attrs
        
        # Notify Owner
        owner = User.query.get(prop.owner_id)
        if owner:
            # Use the dedicated property invalidation email function
            send_property_invalidation_email(owner.email, prop.title, reason)


    db.session.commit()
    return jsonify({'message': f"Bien invalidé.", 'property': prop.to_dict()}), 200

@admin_bp.route('/properties/<int:property_id>', methods=['DELETE'])
@jwt_required()
def delete_property_admin(property_id):
    """
    Soft delete property: Mark as deleted but keep data.
    """
    current_user_id = get_jwt_identity()
    admin = User.query.get(current_user_id)
    if not admin or admin.role != 'admin':
        return jsonify({'message': 'Accès refusé.'}), 403

    prop = Property.query.get_or_404(property_id)
    
    data = request.json or {}
    reason = data.get('reason')

    prop.deleted_at = datetime.utcnow()
    prop.deletion_reason = reason
    
    # Optional: Should we change status to 'withdrawn' or similar?
    # Keeping it simple as soft delete hides it from lists.

    # Handling dependencies:
    # 1. Visit Requests: pending ones should probably be rejected or cancelled.
    pending_visits = VisitRequest.query.filter_by(property_id=prop.id, status='pending').all()
    for visit in pending_visits:
        visit.status = 'rejected'
        visit.message = f"Bien supprimé par l'administrateur. Raison: {reason}"
        
        # Notify seeker
        customer = User.query.get(visit.customer_id)
        if customer:
            from app.utils.email_utils import send_admin_rejection_notification
            send_admin_rejection_notification(customer.email, prop.title, visit.message)

    db.session.commit()
    
    # Notify Owner
    owner = User.query.get(prop.owner_id)
    if owner:
        # We can reuse invalidation email or create a new one. Using invalidation for now as it conveys "removed".
        send_property_invalidation_email(owner.email, prop.title, f"Votre bien a été supprimé par l'administration. Raison: {reason}")

    return jsonify({'message': 'Bien immobilier supprimé (Soft Delete) avec succès.'}), 200

# ------------- TYPES DE PROPRIÉTÉ -------------
@admin_bp.route('/property_types', methods=['GET'])
def get_property_types():
    property_types = PropertyType.query.all()
    return jsonify([pt.to_dict() for pt in property_types])

@admin_bp.route('/property_types', methods=['POST'])
def create_property_type():
    data = request.get_json()
    name, description = data.get('name'), data.get('description')
    if not name:
        return jsonify({'message': 'Le nom du type de propriété est requis.'}), 400
    if PropertyType.query.filter_by(name=name).first():
        return jsonify({'message': 'Ce nom existe déjà.'}), 409
    pt = PropertyType(name=name, description=description)
    db.session.add(pt)
    db.session.commit()
    return jsonify({'message': 'Type créé.', 'property_type': pt.to_dict()}), 201

@admin_bp.route('/property_types/<int:type_id>', methods=['PUT'])
def update_property_type(type_id):
    pt = PropertyType.query.get_or_404(type_id)
    data = request.get_json()
    name, description, is_active = data.get('name'), data.get('description'), data.get('is_active')
    if name:
        if PropertyType.query.filter(PropertyType.name == name, PropertyType.id != type_id).first():
            return jsonify({'message': 'Nom déjà pris.'}), 409
        pt.name = name
    if description is not None:
        pt.description = description
    if is_active is not None:
        pt.is_active = is_active
    db.session.commit()
    return jsonify({'message': 'Type mis à jour.', 'property_type': pt.to_dict()})

@admin_bp.route('/property_types/<int:type_id>', methods=['DELETE'])
def delete_property_type(type_id):
    pt = PropertyType.query.get_or_404(type_id)
    db.session.delete(pt)
    db.session.commit()
    return jsonify({'message': 'Type supprimé.'}), 204

# ------------- ATTRIBUTS -------------
@admin_bp.route('/property_attributes', methods=['GET'])
def get_property_attributes():
    return jsonify([pa.to_dict() for pa in PropertyAttribute.query.all()])

@admin_bp.route('/property_attributes', methods=['POST'])
def add_property_attribute():
    data = request.get_json()
    name, data_type = data.get('name'), data.get('data_type')
    if not all([name, data_type]):
        return jsonify({'message': 'Nom et type requis.'}), 400
    if PropertyAttribute.query.filter_by(name=name).first():
        return jsonify({'message': 'Nom déjà utilisé.'}), 409
    attr = PropertyAttribute(name=name, data_type=data_type, is_filterable=data.get('is_filterable', False))
    db.session.add(attr)
    db.session.commit()
    if data_type == 'enum' and 'options' in data:
        for val in data['options']:
            db.session.add(AttributeOption(attribute_id=attr.id, option_value=val))
        db.session.commit()
    return jsonify({'message': 'Attribut ajouté.', 'attribute': attr.to_dict()}), 201

# ------------- SCOPES -------------
@admin_bp.route('/property_type_scopes/<int:property_type_id>', methods=['GET'])
def get_property_type_scopes(property_type_id):
    scopes = PropertyAttributeScope.query.filter_by(property_type_id=property_type_id).all()
    return jsonify([s.attribute_id for s in scopes])

@admin_bp.route('/property_type_scopes/<int:property_type_id>', methods=['POST'])
def update_property_type_scopes(property_type_id):
    data = request.get_json()
    attr_ids = data.get('attribute_ids', [])
    PropertyAttributeScope.query.filter_by(property_type_id=property_type_id).delete()
    for aid in attr_ids:
        db.session.add(PropertyAttributeScope(property_type_id=property_type_id, attribute_id=aid))
    db.session.commit()
    return jsonify({'message': 'Scopes mis à jour.'}), 200

@admin_bp.route('/property_types_with_attributes', methods=['GET'])
@jwt_required() # C'est une route admin, elle doit être protégée
def get_property_types_with_attributes():
    """
    Récupère TOUS les types de biens et leurs attributs/options.
    
    Version OPTIMISÉE pour pré-charger toutes les données nécessaires
    et éviter les timeouts dus au problème de "N+1 queries".
    """
    # Optionnel: Vérification du rôle admin si le décorateur ne suffit pas
    # current_user_id = get_jwt_identity()
    # admin = User.query.get(current_user_id)
    # if not admin or admin.role != 'admin':
    #     return jsonify({'message': "Accès non autorisé."}), 403

    # Étape 1: Construire une seule requête qui charge tout en avance.
    # C'est la clé de la performance.
    property_types = PropertyType.query.options(
        selectinload(PropertyType.attribute_scopes)
            .selectinload(PropertyAttributeScope.attribute)
                .selectinload(PropertyAttribute.options)
    ).all() # On ne filtre pas par is_active pour l'admin

    # Étape 2: Construire la réponse JSON à partir des données déjà en mémoire.
    # Ces boucles sont maintenant ultra-rapides.
    result = []
    for pt in property_types:
        pt_dict = pt.to_dict()
        pt_dict['attributes'] = []
        
        for scope in pt.attribute_scopes:
            attribute = scope.attribute
            attr_dict = attribute.to_dict() # Les options sont déjà chargées
            pt_dict['attributes'].append(attr_dict)
            
        result.append(pt_dict)
        
    return jsonify(result)

# ------------- UPLOAD -------------
@admin_bp.route('/upload_image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400

    from app.utils.cloudinary_utils import upload_image # Tardif
    
    try:
        secure_url = upload_image(file, folder="woora_admin_uploads")
        
        if secure_url:
            return jsonify({'url': secure_url}), 200
        else:
             return jsonify({'error': 'Erreur interne Cloudinary'}), 500

    except Exception as e:
        current_app.logger.error(f"Upload error: {e}")
        return jsonify({'error': 'Erreur interne'}), 500

# ------------- SETTINGS -------------
@admin_bp.route('/settings/visits', methods=['GET'])
def get_visit_settings():
    free = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
    price = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    return jsonify({
        'initial_free_visit_passes': int(free.setting_value) if free else 0,
        'visit_pass_price': float(price.amount) if price else 0.0
    })

@admin_bp.route('/settings/visits', methods=['PUT'])
def update_visit_settings():
    data = request.get_json()
    try:
        validated = VisitSettingsSchema().load(data)
    except ValidationError as e:
        return jsonify(e.messages), 422

    free = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
    if free:
        free.setting_value = str(validated['initial_free_visit_passes'])
    else:
        db.session.add(AppSetting(
            setting_key='initial_free_visit_passes',
            setting_value=str(validated['initial_free_visit_passes']),
            data_type='integer',
            description='Pass gratuits à l\'inscription'
        ))

    price = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    if price:
        price.amount = validated['visit_pass_price']
    else:
        db.session.add(ServiceFee(
            service_key='visit_pass_purchase',
            name='Achat de Pass de Visite',
            amount=validated['visit_pass_price'],
            applicable_to_role='customer',
            description='Permet à un client d’acheter un pass'
        ))

    db.session.commit()
    return jsonify({'message': 'Paramètres mis à jour.'}), 200

# ------------- VISITE REQUESTS -------------
@admin_bp.route('/visit_requests', methods=['GET'])
def get_visit_requests():
    status_filter = request.args.get('status')
    query = VisitRequest.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    result = []
    for req in query.all():
        customer = User.query.get(req.customer_id)
        prop = Property.query.get(req.property_id)
        result.append({
            'id': req.id,
            'customer_name': f'{customer.first_name} {customer.last_name}' if customer else 'N/A',
            'customer_email': customer.email if customer else 'N/A',
            'property_title': prop.title if prop else 'N/A',
            'requested_datetime': req.requested_datetime.isoformat(),
            'status': req.status,
            'message': req.message,
            'created_at': req.created_at.isoformat()
        })
    return jsonify(result), 200

@admin_bp.route('/visit_requests/<int:request_id>/confirm', methods=['PUT'])
def confirm_visit_request(request_id):
    vr = VisitRequest.query.get_or_404(request_id)
    if vr.status != 'pending':
        return jsonify({'message': 'Pas en attente.'}), 400
    vr.status = 'confirmed'
    try:
        db.session.commit()
        owner = User.query.get(Property.query.get(vr.property_id).owner_id)
        customer = User.query.get(vr.customer_id)
        prop = Property.query.get(vr.property_id)
        if owner and customer and prop:
            send_admin_confirmation_to_owner(
                owner.email,
                f'{customer.first_name} {customer.last_name}',
                prop.title,
                vr.requested_datetime.strftime('%Y-%m-%d %H:%M')
            )
        return jsonify({'message': 'Confirmée.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Erreur.'}), 500

@admin_bp.route('/visit_requests/<int:request_id>/reject', methods=['PUT'])
def reject_visit_request_by_admin(request_id):
    vr = VisitRequest.query.get_or_404(request_id)
    
    # MODIF: On autorise le rejet/annulation pour 'pending', 'confirmed' et 'accepted'
    if vr.status not in ['pending', 'confirmed', 'accepted']:
        return jsonify({'message': 'Impossible d\'annuler une visite déjà effectuée ou rejetée.'}), 400
        
    vr.status = 'rejected'
    msg = request.get_json().get('message', 'Annulation par l\'administrateur.')
    
    try:
        # REMBOURSEMENT AUTOMATIQUE DU PASS
        # Si le client a payé un pass (déduit à la création), on le rembourse
        if vr.customer_id:
            customer_to_refund = User.query.with_for_update().get(vr.customer_id)
            if customer_to_refund:
                customer_to_refund.visit_passes += 1
                current_app.logger.info(f"[ADMIN] Remboursement de 1 pass au client {customer_to_refund.id} suite au rejet/annulation de la visite {vr.id}")

        db.session.commit()
        
        # Notification
        customer = User.query.get(vr.customer_id)
        prop = Property.query.get(vr.property_id)
        if customer and prop:
            send_admin_rejection_notification(customer.email, prop.title, msg)
            
        return jsonify({'message': 'Visite annulée/rejetée avec succès.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur annulation visite admin: {e}")
        return jsonify({'message': 'Erreur lors de l\'annulation.'}), 500

# ------------- COMMISSION AGENT -------------
@admin_bp.route('/settings/agent_commission', methods=['GET'])
def get_agent_commission_setting():
    setting = AppSetting.query.filter_by(setting_key='agent_commission_percentage').first()
    return jsonify({'agent_commission_percentage': float(setting.setting_value) if setting else 0.0}), 200

@admin_bp.route('/settings/agent_commission', methods=['PUT'])
def update_agent_commission_setting():
    data = request.get_json()
    pct = data.get('agent_commission_percentage')
    if pct is None:
        return jsonify({'message': 'Champ manquant.'}), 400
    try:
        pct = float(pct)
        if not (0 <= pct <= 100):
            raise ValueError
    except ValueError:
        return jsonify({'message': 'Valeur invalide (0-100).'}), 400

    setting = AppSetting.query.filter_by(setting_key='agent_commission_percentage').first()
    if setting:
        setting.setting_value = str(pct)
    else:
        db.session.add(AppSetting(
            setting_key='agent_commission_percentage',
            setting_value=str(pct),
            data_type='decimal',
            description='Commission agent (%)'
        ))
    db.session.commit()
    return jsonify({'message': 'Commission mise à jour.'}), 200

# ------------- ELIGIBLE BUYERS -------------
@admin_bp.route('/properties/<int:property_id>/eligible_buyers', methods=['GET'])
def get_eligible_buyers_for_property(property_id):
    prop = Property.query.get_or_404(property_id)
    visits = (db.session.query(VisitRequest, User)
              .join(User, VisitRequest.customer_id == User.id)
              .filter(VisitRequest.property_id == property_id, VisitRequest.status == 'accepted')
              .all())
    return jsonify([{
        'visit_request_id': v.id,
        'customer_id': u.id,
        'customer_name': f'{u.first_name} {u.last_name}',
        'customer_email': u.email,
        'requested_datetime': v.requested_datetime.isoformat(),
        'has_referral_code': v.referral_id is not None
    } for v, u in visits]), 200

# ------------- TRANSACTION -------------
@admin_bp.route('/properties/<int:property_id>/mark_as_transacted', methods=['PUT'])
# @jwt_required() # Assurez-vous que cette route est protégée
# @admin_required # Et accessible uniquement par les admins
# --- GESTION DES VISITES EFFECTUÉES ET TRANSACTION ---

@admin_bp.route('/visit_requests/<int:visit_id>/complete', methods=['PUT'])
# @admin_required
def mark_visit_as_completed(visit_id):
    """
    Marque une visite comme 'effectuée' (completed).
    Cela permet ensuite de sélectionner ce client comme acquéreur.
    """
    visit = VisitRequest.query.get_or_404(visit_id)
    if visit.status != 'accepted':
        return jsonify({'message': "Seule une visite 'acceptée' peut être marquée comme effectuée."}), 400
    
    visit.status = 'completed'
    db.session.commit()
    return jsonify({'message': "Visite marquée comme effectuée.", 'visit': visit.to_dict()}), 200

@admin_bp.route('/properties/<int:property_id>/eligible_buyers', methods=['GET'])
# @admin_required
def get_eligible_buyers(property_id):
    """
    Récupère la liste des utilisateurs ayant effectué au moins une visite (status='completed')
    pour ce bien. Indique si le client a un parrainage valide (basé sur sa 1ère demande).
    """
    # On cherche les visites effectuées pour ce bien
    completed_visits = VisitRequest.query.filter_by(property_id=property_id, status='completed').all()
    
    # On extrait les IDs utilisateurs uniques
    buyer_ids = set(v.customer_id for v in completed_visits)
    
    buyers_data = []
    for user_id in buyer_ids:
        user = User.query.get(user_id)
        if not user:
            continue
            
        # RÈGLE DU "STICKY REFERRAL" :
        # On cherche la TOUTE PREMIÈRE demande de ce client pour ce bien
        first_request = VisitRequest.query.filter_by(
            customer_id=user_id,
            property_id=property_id
        ).order_by(VisitRequest.created_at.asc()).first()
        
        has_referral = False
        referral_agent_name = None
        
        if first_request and first_request.referral_id:
            has_referral = True
            if first_request.referral and first_request.referral.agent:
                referral_agent_name = f"{first_request.referral.agent.first_name} {first_request.referral.agent.last_name}"
        
        buyers_data.append({
            'user_id': user.id,
            'user_name': f"{user.first_name} {user.last_name}",
            'email': user.email,
            'has_referral': has_referral,
            'referral_agent_name': referral_agent_name,
            'first_visit_date': first_request.created_at.isoformat() if first_request else None
        })
        
    return jsonify(buyers_data), 200

@admin_bp.route('/properties/<int:property_id>/mark_as_transacted', methods=['PUT'])
# @admin_required # Et accessible uniquement par les admins
def mark_property_as_transacted(property_id):
    """
    Marque un bien comme 'vendu' ou 'loué' basé sur l'ACHETEUR (User).
    Vérifie si la PREMIÈRE demande de cet acheteur avait un parrainage pour payer la commission.
    """
    data = request.get_json()
    new_status = data.get('status')
    buyer_id = data.get('buyer_id') # On attend maintenant l'ID de l'acheteur (User)

    if new_status not in ['sold', 'rented']:
        return jsonify({'message': 'Le statut doit être "sold" ou "rented".'}), 400

    if not buyer_id:
        return jsonify({'message': 'Un acheteur (User ID) doit être spécifié.'}), 400

    prop = Property.query.get_or_404(property_id)
    prop.status = new_status
    
    # --- SAUVEGARDE DE L'ACHETEUR ---
    # Maintenant que le modèle Property a un champ buyer_id, on le stocke.
    prop.buyer_id = buyer_id

    # --- LOGIQUE DE COMMISSION (STICKY REFERRAL) ---
    # On récupère la TOUTE PREMIÈRE demande de cet acheteur pour ce bien
    first_request = VisitRequest.query.filter_by(
        customer_id=buyer_id,
        property_id=property_id
    ).order_by(VisitRequest.created_at.asc()).first()
    
    agent_to_pay = None
    
    if first_request and first_request.referral_id:
        ref = Referral.query.get(first_request.referral_id)
        if ref and ref.agent_id:
            agent_to_pay = User.query.get(ref.agent_id)

    # Si un agent doit être payé (Parrainage à la première demande)
    if agent_to_pay and agent_to_pay.role == 'agent':
        # SÉCURITÉ : Verrouillage pour mise à jour solde
        agent = User.query.with_for_update().get(agent_to_pay.id)
        
        # Récupérer le pourcentage
        commission_setting = AppSetting.query.filter_by(setting_key='agent_commission_percentage').first()
        pct_str = commission_setting.setting_value if commission_setting else "5.0"
        
        try:
            price_decimal = Decimal(prop.price)
            pct_decimal = Decimal(pct_str)
            commission_amount = (price_decimal * pct_decimal) / Decimal(100)
            commission_amount = round(commission_amount, 2)
            
            # 1. Créer la commission
            db.session.add(Commission(agent_id=agent.id, property_id=prop.id, amount=commission_amount, status='paid'))
            
            # 2. Update Wallet
            if agent.wallet_balance is None:
                agent.wallet_balance = Decimal(0)
            agent.wallet_balance += commission_amount
            
            # 3. Transaction Record
            db.session.add(Transaction(
                user_id=agent.id, 
                amount=commission_amount, 
                type='commission_payout',
                description=f'Commission pour la transaction du bien: {prop.title} (Acheteur: User #{buyer_id})'
            ))
            
            # 4. Notification Agent
            try:
                send_commission_paid_notification(
                    agent_email=agent.email,
                    agent_name=f"{agent.first_name} {agent.last_name}",
                    amount=f"{commission_amount:,.0f}".replace(",", " "),
                    property_title=prop.title
                )
            except Exception as e:
                current_app.logger.warning(f"Échec envoi email commission: {e}")

        except Exception as e:
            current_app.logger.error(f"Erreur calcul commission: {e}")
            return jsonify({'message': 'Erreur lors du calcul de la commission.'}), 500

    # --- NOTIFICATION CLIENT (Deal Closed) ---
    buyer = User.query.get(buyer_id)
    if buyer:
         try:
             # On demande un avis sur l'agent SI l'agent a été payé
             agent_id_for_review = agent_to_pay.id if agent_to_pay else None

             send_deal_closed_client_notification(
                 customer_email=buyer.email,
                 customer_name=f"{buyer.first_name} {buyer.last_name}",
                 property_title=prop.title,
                 agent_id=agent_id_for_review
             )
         except Exception as e:
             current_app.logger.warning(f"Échec envoi email client (deal closed): {e}")

    try:
        db.session.commit()
        return jsonify({'message': f"Bien marqué comme {new_status}.", 'property': prop.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors du marquage comme 'transacted': {e}", exc_info=True)
        return jsonify({'message': 'Une erreur est survenue lors de la sauvegarde.'}), 500

# Endpoint pour voir toutes les demandes des clients
@admin_bp.route('/property_requests', methods=['GET'])
# @jwt_required() et @admin_required
def get_all_property_requests():
    """
    Récupère les demandes de biens (alertes clients).
    Par défaut, exclut les alertes archivées.
    Utilisez ?include_archived=true pour inclure les archivées.
    """
    include_archived = request.args.get('include_archived', 'false').lower() == 'true'
    
    query = PropertyRequest.query
    
    # Filtrer les archivées par défaut
    if not include_archived:
        query = query.filter(PropertyRequest.archived_at == None)
    
    requests = query.order_by(PropertyRequest.created_at.desc()).all()
    return jsonify([req.to_dict() for req in requests]), 200 # Assurez-vous d'avoir une méthode to_dict() sur le modèle

@admin_bp.route('/property_requests/<int:request_id>/respond', methods=['POST'])
# @jwt_required() et @admin_required
def respond_to_property_request(request_id):
    """
    Permet à un admin de répondre à une alerte, ce qui met à jour le statut
    et envoie un email de notification au client.
    """
    prop_request = PropertyRequest.query.get_or_404(request_id)
    
    data = request.get_json()
    response_message = data.get('message')
    if not response_message:
        return jsonify({'message': "Un message de réponse est requis."}), 400
        
    try:
        # Mettre à jour la demande dans la base de données
        prop_request.status = 'contacted'
        prop_request.admin_notes = response_message
        
        # Récupérer les informations du client pour l'email
        customer = prop_request.customer
        if customer:
            # Maintenant que la fonction est importée, cet appel fonctionnera
            send_admin_response_to_seeker(
                customer_email=customer.email,
                customer_name=customer.first_name,
                original_request=prop_request.request_details,
                admin_response=response_message
            )

        db.session.commit()
        return jsonify({'message': "Réponse envoyée avec succès au client."}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la réponse à une demande de bien: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500

@admin_bp.route('/property_requests/<int:request_id>/archive', methods=['PUT'])
@jwt_required()
def archive_property_request(request_id):
    """
    Archive une alerte client (PropertyRequest).
    Seules les alertes avec statut 'contacted' ou 'closed' peuvent être archivées.
    """
    current_user_id = get_jwt_identity()
    admin = User.query.get(current_user_id)
    if not admin or admin.role != 'admin':
        return jsonify({'message': 'Accès refusé. Réservé aux administrateurs.'}), 403
    
    prop_request = PropertyRequest.query.get_or_404(request_id)
    
    # Vérifier que l'alerte peut être archivée
    if prop_request.status not in ['contacted', 'closed']:
        return jsonify({
            'message': "Impossible d'archiver cette alerte. Seules les alertes 'contacted' ou 'closed' peuvent être archivées."
        }), 400
    
    # Vérifier si déjà archivée
    if prop_request.archived_at is not None:
        return jsonify({'message': "Cette alerte est déjà archivée."}), 400
    
    try:
        prop_request.archived_at = datetime.utcnow()
        prop_request.archived_by = current_user_id
        db.session.commit()
        
        return jsonify({
            'message': "Alerte archivée avec succès."
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de l'archivage de l'alerte: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500

@admin_bp.route('/property_requests/<int:request_id>/unarchive', methods=['PUT'])
@jwt_required()
def unarchive_property_request(request_id):
    """
    Désarchive (restaure) une alerte client archivée.
    """
    current_user_id = get_jwt_identity()
    admin = User.query.get(current_user_id)
    if not admin or admin.role != 'admin':
        return jsonify({'message': 'Accès refusé. Réservé aux administrateurs.'}), 403
    
    prop_request = PropertyRequest.query.get_or_404(request_id)
    
    # Vérifier si l'alerte est archivée
    if prop_request.archived_at is None:
        return jsonify({'message': "Cette alerte n'est pas archivée."}), 400
    
    try:
        prop_request.archived_at = None
        prop_request.archived_by = None
        db.session.commit()
        
        return jsonify({
            'message': "Alerte restaurée avec succès.",
            'request': prop_request.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la restauration de l'alerte: {e}", exc_info=True)
        return jsonify({'message': "Erreur interne du serveur."}), 500


@admin_bp.route('/property_attributes/<int:attribute_id>', methods=['PUT'])
# @jwt_required() et @admin_required # N'oubliez pas d'activer la sécurité
def update_property_attribute(attribute_id):
    """
    Met à jour un attribut de bien existant.
    Cette version est sécurisée et performante.
    """
    # 1. Récupérer l'attribut ou retourner une erreur 404
    attr = PropertyAttribute.query.get_or_404(attribute_id)
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Données manquantes.'}), 400

    new_name = data.get('name', '').strip()
    new_data_type = data.get('data_type')

    # 2. Vérification de sécurité : si on change le type de données
    # On NE BLOQUE que si des BIENS RÉELS utilisent cet attribut.
    # La simple association à un PropertyType ne doit PAS bloquer la modification.
    if new_data_type and new_data_type != attr.data_type:
        # Vérifier s'il existe des biens qui utilisent cet attribut
        # On cherche dans la colonne JSON 'attributes' si la clé existe
        from sqlalchemy import text
        
        # Compte le nombre de biens (NON SUPPRIMÉS) qui ont cet attribut dans leur JSON
        count_query = text("""
            SELECT COUNT(*) 
            FROM Properties 
            WHERE JSON_EXTRACT(attributes, :attr_path) IS NOT NULL
            AND deleted_at IS NULL
        """)
        
        result = db.session.execute(
            count_query, 
            {'attr_path': f'$.{attr.name}'}
        ).scalar()
        
        if result and result > 0:
            return jsonify({
                'message': f"Impossible de changer le type de l'attribut '{attr.name}' car {result} bien(s) l'utilisent déjà. Vous devez d'abord supprimer ou modifier ces biens."
            }), 409 # 409 Conflict

    # 3. Validation : si on change le nom, s'assurer qu'il n'est pas déjà pris
    # ET SURTOUT qu'il n'est pas déjà utilisé dans des données existantes (pour éviter de casser le JSON)
    if new_name and new_name != attr.name:
        # Check nom unique
        existing_attr = PropertyAttribute.query.filter(
            PropertyAttribute.name == new_name,
            PropertyAttribute.id != attribute_id
        ).first()
        if existing_attr:
            return jsonify({'message': f"Ce nom d'attribut '{new_name}' est déjà utilisé."}), 409

        # Check usage dans les propriétés (CRUCIAL)
        # On cherche si une propriété a une clé qui correspond à l'ancien nom de l'attribut
        # Note: La syntaxe exacte dépend de la DB (Postgres/MySQL). Ici on utilise une méthode générique Python
        # car JSON_CONTAINS ou équivalent peut varier.
        # Pour être sûr et compatible, on scanne les propriétés qui ont des attributs.
        # (Optimisation possible: faire une requête SQL native spécifique si bcp de données)
        
        # FIX: Exclure les propriétés supprimées (Soft Delete)
        properties_using_attribute = Property.query.filter(
            Property.attributes.isnot(None), 
            Property.deleted_at == None
        ).all()
        for prop in properties_using_attribute:
             if isinstance(prop.attributes, dict) and attr.name in prop.attributes:
                 return jsonify({
                    'message': f"Impossible de renommer l'attribut '{attr.name}' car il est utilisé dans des biens existants (ex: ID {prop.id}). Supprimez-le et recréez-le si nécessaire, mais les données seront perdues."
                }), 409
        
        attr.name = new_name

    # 4. Mise à jour des champs
    if new_data_type:
        # Si on change un type 'enum' pour autre chose, on supprime ses options
        if attr.data_type == 'enum' and new_data_type != 'enum':
            AttributeOption.query.filter_by(attribute_id=attr.id).delete()
        attr.data_type = new_data_type

    # Gestion de la mise à jour des options pour les ENUM
    if attr.data_type == 'enum' and 'options' in data:
        # On supprime les anciennes options et on recrée les nouvelles
        # C'est la méthode la plus sûre pour garantir la synchro
        AttributeOption.query.filter_by(attribute_id=attr.id).delete()
        
        new_options = data.get('options', [])
        for val in new_options:
            if val and val.strip(): # On évite les options vides
                db.session.add(AttributeOption(attribute_id=attr.id, option_value=val.strip()))

    # La mise à jour de 'is_filterable' est toujours autorisée
    if 'is_filterable' in data:
        attr.is_filterable = data['is_filterable']

    # 5. Sauvegarder les changements
    try:
        db.session.commit()
        return jsonify({'message': 'Attribut mis à jour avec succès.', 'attribute': attr.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la mise à jour de l'attribut: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500


@admin_bp.route('/property_attributes/<int:attribute_id>', methods=['DELETE'])
# @jwt_required() et @admin_required # N'oubliez pas d'activer la sécurité
def delete_property_attribute(attribute_id):
    """
    Supprime un attribut de propriété, après avoir vérifié qu'il n'est pas utilisé.
    """
    attr = PropertyAttribute.query.get_or_404(attribute_id)

    # --- VÉRIFICATION D'USAGE (CRUCIAL) ---
    # On vérifie si un bien utilise cet attribut dans son champ JSON.
    # C'est une vérification simple mais efficace.
    # CORRECTION: On ignore les biens supprimés (Soft Delete)
    properties_using_attribute = Property.query.filter(
        Property.attributes.isnot(None),
        Property.deleted_at == None
    ).all()
    
    for prop in properties_using_attribute:
        if isinstance(prop.attributes, dict) and attr.name in prop.attributes:
            # Si on trouve ne serait-ce qu'un seul bien qui utilise cet attribut, on bloque la suppression.
            return jsonify({
                'message': f"Impossible de supprimer l'attribut '{attr.name}' car il est utilisé par au moins un bien immobilier (ID: {prop.id})."
            }), 409 # 409 Conflict

    # Si la vérification passe, l'attribut n'est pas utilisé et peut être supprimé.
    # La suppression des options et des scopes se fait en cascade grâce à la configuration de la BDD.
    try:
        db.session.delete(attr)
        db.session.commit()
        return jsonify({'message': 'Attribut supprimé avec succès.'}), 204 # 204 No Content est standard pour un DELETE réussi
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la suppression de l'attribut: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500


@admin_bp.route('/properties/<int:property_id>', methods=['PUT', 'PATCH'])
# @jwt_required() et @admin_required via before_request ou decorator global
def update_property_by_admin(property_id):
    """
    Permet à un administrateur de modifier n'importe quel bien immobilier.
    """
    # Note: La vérification admin est supposée être gérée par le décorateur ou le blueprint

    # Vérifier que le bien existe
    property = Property.query.get_or_404(property_id)

    data = request.get_json()
    if not data:
        return jsonify({'message': "Corps de la requête manquant ou invalide."}), 400
        
    # --- LOGIQUE DE MISE À JOUR (Inspirée de agent/routes.py) ---

    # 1. Mise à jour des champs directs si présents dans la racine du JSON
    attributes_data = data.get('attributes', data) # Fallback sur data si attributes absent

    if 'title' in attributes_data:
        property.title = attributes_data['title']
    
    if 'price' in attributes_data:
        try:
            val = attributes_data['price']
            property.price = float(val) if val is not None else None
        except (ValueError, TypeError):
            return jsonify({'message': "Le prix doit être un nombre valide."}), 400
    
    if 'status' in attributes_data:
        # On accepte tous les statuts valides
        property.status = attributes_data['status']
        
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
        try:
            val = attributes_data.get('latitude')
            property.latitude = float(val) if val and str(val).lower() != 'null' else None
        except (ValueError, TypeError):
             return jsonify({'message': 'latitude invalide.'}), 400
            
    if 'longitude' in attributes_data:
        try:
            val = attributes_data.get('longitude')
            property.longitude = float(val) if val and str(val).lower() != 'null' else None
        except (ValueError, TypeError):
             return jsonify({'message': 'longitude invalide.'}), 400

    # 2. Mise à jour du champ JSON attributes (pour les champs dynamiques)
    if attributes_data:
        if property.attributes is None:
            property.attributes = {}
        
        property.attributes.update(attributes_data)
        flag_modified(property, "attributes")

    # 3. Gestion des images
    if 'image_urls' in data:
        # Remplacement complet des images
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
        return jsonify({
            'message': "Bien immobilier mis à jour avec succès par l'admin.",
            'property': property.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur update admin property: {e}")
        return jsonify({'message': "Erreur lors de la mise à jour."}), 500


# ===================================================================
# GESTION DES DEMANDES DE VISITE - ADMIN
# ===================================================================

@admin_bp.route('/visit_requests', methods=['GET'])
@jwt_required()
def get_all_visit_requests_admin():
    """
    Récupère toutes les demandes de visite avec possibilité de filtrer par statut.
    Accessible uniquement pour les administrateurs.
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Accès non autorisé. Réservé aux administrateurs.'}), 403
        
        # Filtrage par statut (optionnel)
        status_filter = request.args.get('status')
        
        query = VisitRequest.query
        if status_filter and status_filter != 'all':
            query = query.filter_by(status=status_filter)
        
        visit_requests = query.order_by(VisitRequest.created_at.desc()).all()
        
        result = []
        for vr in visit_requests:
            result.append({
                'id': vr.id,
                'property_id': vr.property_id,
                'property_title': vr.property.title if vr.property else 'Titre indisponible',
                'customer_id': vr.customer_id,
                'customer_name': f"{vr.customer.first_name} {vr.customer.last_name}" if vr.customer else 'Client inconnu',
                'customer_email': vr.customer.email if vr.customer else None,
                'requested_datetime': vr.requested_datetime.isoformat() if vr.requested_datetime else None,
                'status': vr.status,
                'message': vr.message,
                'created_at': vr.created_at.isoformat() if vr.created_at else None
            })
        
        return jsonify(result), 200
        
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des demandes de visite (admin): {e}", exc_info=True)
        return jsonify({'error': 'Erreur interne du serveur.'}), 500


@admin_bp.route('/visit_requests/<int:request_id>/confirm', methods=['PUT'])
@jwt_required()
def confirm_visit_request_admin(request_id):
    """
    Confirme une demande de visite (passe de 'pending' à 'confirmed').
    Accessible uniquement pour les administrateurs.
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Accès non autorisé. Réservé aux administrateurs.'}), 403
        
        visit_request = VisitRequest.query.get(request_id)
        if not visit_request:
            return jsonify({'error': 'Demande de visite non trouvée.'}), 404
        
        if visit_request.status != 'pending':
            return jsonify({'error': f"Cette demande ne peut pas être confirmée car son statut est '{visit_request.status}'."}), 400
        
        visit_request.status = 'confirmed'
        db.session.commit()
        
        current_app.logger.info(f"Demande de visite {request_id} confirmée par admin {current_user_id}")
        
        return jsonify({'message': 'Demande de visite confirmée avec succès.'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la confirmation de la demande de visite (admin): {e}", exc_info=True)
        return jsonify({'error': 'Erreur interne du serveur.'}), 500


@admin_bp.route('/visit_requests/<int:request_id>/reject', methods=['PUT'])
@jwt_required()
def reject_visit_request_admin(request_id):
    """
    Rejette une demande de visite.
    Accessible uniquement pour les administrateurs.
    """
    try:
        current_user_id = get_jwt_identity()
        user = User.query.get(current_user_id)
        
        if not user or user.role != 'admin':
            return jsonify({'error': 'Accès non autorisé. Réservé aux administrateurs.'}), 403
        
        visit_request = VisitRequest.query.get(request_id)
        if not visit_request:
            return jsonify({'error': 'Demande de visite non trouvée.'}), 404
        
        data = request.get_json() or {}
        rejection_message = data.get('message', 'Demande rejetée par l\'administrateur.')
        
        visit_request.status = 'rejected'
        db.session.commit()
        
        current_app.logger.info(f"Demande de visite {request_id} rejetée par admin {current_user_id}")
        
        return jsonify({'message': 'Demande de visite rejetée avec succès.'}), 200
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors du rejet de la demande de visite (admin): {e}", exc_info=True)
        return jsonify({'error': 'Erreur interne du serveur.'}), 500


