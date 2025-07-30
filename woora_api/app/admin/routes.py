from flask import Blueprint, jsonify, request, current_app
from app.models import (
    User, Property, PropertyType, PropertyAttribute, AttributeOption,
    PropertyAttributeScope, db, AppSetting, ServiceFee, VisitRequest,
    Referral, Commission, Transaction
)
from app.schemas import VisitSettingsSchema
from marshmallow import ValidationError
from app.utils.mega_utils import get_mega_instance
from werkzeug.utils import secure_filename
import os
import uuid
from app.utils.email_utils import send_admin_rejection_notification, send_admin_confirmation_to_owner

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

UPLOAD_FOLDER = '/tmp'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
def get_property_types_with_attributes():
    pts = PropertyType.query.all()
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

# ------------- UPLOAD -------------
@admin_bp.route('/upload_image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400
    filename = secure_filename(file.filename)
    tmp_path = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4()}_{filename}")
    try:
        file.save(tmp_path)
        mega = get_mega_instance()
        if not mega:
            return jsonify({'error': 'Connexion stockage impossible'}), 503
        node = mega.upload(tmp_path)
        link = mega.get_upload_link(node)
        return jsonify({'url': link}), 200
    except Exception as e:
        current_app.logger.error(f"Upload error: {e}")
        return jsonify({'error': 'Erreur interne'}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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
def mark_property_as_transacted(property_id):
    data = request.get_json()
    new_status = data.get('status')
    winning_visit_id = data.get('winning_visit_request_id')
    if new_status not in ['sold', 'rented']:
        return jsonify({'message': 'Statut invalide.'}), 400

    prop = Property.query.get_or_404(property_id)
    prop.status = new_status
    prop.winning_visit_request_id = winning_visit_id

    if winning_visit_id:
        vr = VisitRequest.query.get(winning_visit_id)
        if not vr or vr.property_id != property_id:
            return jsonify({'message': 'Demande invalide.'}), 400
        if vr.referral_id:
            ref = Referral.query.get(vr.referral_id)
            if ref and ref.agent_id:
                agent = User.query.get(ref.agent_id)
                if agent and agent.role == 'agent':
                    pct = float(AppSetting.query.filter_by(setting_key='agent_commission_percentage').first().setting_value or 5)
                    commission = (prop.price * pct) / 100
                    db.session.add(Commission(agent_id=agent.id, property_id=prop.id, amount=commission, status='paid'))
                    agent.wallet_balance += commission
                    db.session.add(Transaction(user_id=agent.id, amount=commission, type='commission_payout',
                                               description=f'Commission pour {prop.title}'))
    try:
        db.session.commit()
        return jsonify({'message': f'Bien {new_status}.', 'property': prop.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Erreur.'}), 500
