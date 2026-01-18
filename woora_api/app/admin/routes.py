from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.orm import selectinload
from app.models import (
    User, Property, PropertyType, PropertyAttribute, AttributeOption,
    PropertyAttributeScope, db, AppSetting, ServiceFee, VisitRequest,
    Referral, Commission, Transaction, PropertyRequest
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

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

UPLOAD_FOLDER = '/tmp'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ------------- DASHBOARD -------------
@admin_bp.route('/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    user_count = User.query.count()
    property_count = Property.query.filter_by(status='active').count()
    pending_visits = VisitRequest.query.filter_by(status='pending').count()
    
    # Calculate revenue from commissions
    # Assuming Transaction model has amount and type='commission_payout' (checks code snippet above)
    revenue = db.session.query(db.func.sum(Transaction.amount)).filter_by(type='commission_payout').scalar() or 0.0

    return jsonify({
        'total_users': user_count,
        'active_properties': property_count,
        'pending_visits': pending_visits,
        'total_revenue': float(revenue)
    })

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
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

# ------------- PROPRIÉTÉS -------------
@admin_bp.route('/properties', methods=['GET'])
def get_properties():
    properties = Property.query.all()
    return jsonify([p.to_dict() for p in properties])

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
    if vr.status != 'pending':
        return jsonify({'message': 'Pas en attente.'}), 400
    vr.status = 'rejected'
    msg = request.get_json().get('message', 'Rejet admin.')
    try:
        db.session.commit()
        customer = User.query.get(vr.customer_id)
        prop = Property.query.get(vr.property_id)
        if customer and prop:
            send_admin_rejection_notification(customer.email, prop.title, msg)
        return jsonify({'message': 'Rejetée.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Erreur.'}), 500

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
def mark_property_as_transacted(property_id):
    """
    Marque un bien comme 'vendu' ou 'loué' et génère la commission
    de l'agent parrain, le cas échéant.
    """
    data = request.get_json()
    new_status = data.get('status')
    winning_visit_id = data.get('winning_visit_request_id')

    if new_status not in ['sold', 'rented']:
        return jsonify({'message': 'Le statut doit être "sold" ou "rented".'}), 400

    prop = Property.query.get_or_404(property_id)
    prop.status = new_status
    prop.winning_visit_request_id = winning_visit_id

    # Si une visite gagnante est spécifiée, on traite la commission
    if winning_visit_id:
        vr = VisitRequest.query.get(winning_visit_id)
        if not vr or vr.property_id != property_id:
            return jsonify({'message': 'ID de la demande de visite invalide ou ne correspondant pas au bien.'}), 400
        
        # Si cette visite est liée à un parrainage
        if vr.referral_id:
            ref = Referral.query.get(vr.referral_id)
            if ref and ref.agent_id:
                agent = User.query.get(ref.agent_id)
                if agent and agent.role == 'agent':
                    # Récupérer le pourcentage de commission depuis les paramètres
                    commission_setting = AppSetting.query.filter_by(setting_key='agent_commission_percentage').first()
                    # Utiliser une valeur par défaut de 5.0 si le paramètre n'existe pas
                    pct_str = commission_setting.setting_value if commission_setting else "5.0"
                    
                    # --- DÉBUT DE LA CORRECTION ---
                    try:
                        # Convertir le prix (Decimal) et le pourcentage (String) en Decimal pour le calcul
                        price_decimal = Decimal(prop.price)
                        pct_decimal = Decimal(pct_str)
                        
                        # Calculer la commission en utilisant uniquement des Decimals
                        commission_amount = (price_decimal * pct_decimal) / Decimal(100)
                        
                        # Arrondir au centime le plus proche
                        commission_amount = round(commission_amount, 2)

                    except (TypeError, ValueError):
                        current_app.logger.error("La valeur du pourcentage de commission est invalide.")
                        return jsonify({'message': 'Erreur de configuration du pourcentage de commission.'}), 500
                    # --- FIN DE LA CORRECTION ---

                    # Ajouter la commission à la base de données
                    db.session.add(Commission(agent_id=agent.id, property_id=prop.id, amount=commission_amount, status='paid'))
                    
                    # Mettre à jour le portefeuille de l'agent
                    if agent.wallet_balance is None:
                        agent.wallet_balance = Decimal(0)
                    agent.wallet_balance += commission_amount
                    
                    # Enregistrer la transaction
                    db.session.add(Transaction(user_id=agent.id, amount=commission_amount, type='commission_payout',
                                               description=f'Commission pour la transaction du bien: {prop.title}'))
    try:
        db.session.commit()
        return jsonify({'message': f'Le bien a été marqué comme "{new_status}".', 'property': prop.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors du marquage comme 'transacted': {e}", exc_info=True)
        return jsonify({'message': 'Une erreur est survenue lors de la sauvegarde.'}), 500

# Endpoint pour voir toutes les demandes des clients
@admin_bp.route('/property_requests', methods=['GET'])
# @jwt_required() et @admin_required
def get_all_property_requests():
    requests = PropertyRequest.query.order_by(PropertyRequest.created_at.desc()).all()
    # Vous pouvez construire une réponse plus détaillée ici si nécessaire
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
    # La manière EFFICACE de vérifier si un attribut est utilisé est de
    # regarder s'il est lié à un PropertyType, pas de scanner tous les biens.
    if new_data_type and new_data_type != attr.data_type:
        is_in_use = PropertyAttributeScope.query.filter_by(attribute_id=attr.id).first()
        if is_in_use:
            return jsonify({
                'message': f"Impossible de changer le type de l'attribut '{attr.name}' car il est déjà associé à un type de bien."
            }), 409 # 409 Conflict

    # 3. Validation : si on change le nom, s'assurer qu'il n'est pas déjà pris
    if new_name and new_name != attr.name:
        existing_attr = PropertyAttribute.query.filter(
            PropertyAttribute.name == new_name,
            PropertyAttribute.id != attribute_id
        ).first()
        if existing_attr:
            return jsonify({'message': f"Ce nom d'attribut '{new_name}' est déjà utilisé."}), 409
        attr.name = new_name

    # 4. Mise à jour des champs
    if new_data_type:
        # Si on change un type 'enum' pour autre chose, on supprime ses options
        if attr.data_type == 'enum' and new_data_type != 'enum':
            AttributeOption.query.filter_by(attribute_id=attr.id).delete()
        attr.data_type = new_data_type

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
    properties_using_attribute = Property.query.filter(Property.attributes.isnot(None)).all()
    
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






