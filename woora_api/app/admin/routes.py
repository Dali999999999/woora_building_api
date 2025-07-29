from flask import Blueprint, jsonify, request, current_app
from app.models import (
    User, Property, PropertyType, PropertyAttribute, AttributeOption,
    PropertyAttributeScope, db, AppSetting, ServiceFee, VisitRequest
)
from app.schemas import VisitSettingsSchema
from marshmallow import ValidationError
from app.utils.mega_utils import get_mega_instance
from werkzeug.utils import secure_filename
import os
import uuid
from app.utils.email_utils import send_admin_rejection_notification, send_admin_confirmation_to_owner

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Dossier temporaire pour les uploads
UPLOAD_FOLDER = '/tmp'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ---------------------------------
# USERS
# ---------------------------------
@admin_bp.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

# ---------------------------------
# PROPERTIES
# ---------------------------------
@admin_bp.route('/properties', methods=['GET'])
def get_properties():
    properties = Property.query.all()
    return jsonify([p.to_dict() for p in properties])

# ---------------------------------
# PROPERTY TYPES
# ---------------------------------
@admin_bp.route('/property_types', methods=['GET'])
def get_property_types():
    property_types = PropertyType.query.all()
    return jsonify([pt.to_dict() for pt in property_types])

@admin_bp.route('/property_types', methods=['POST'])
def create_property_type():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description')

    if not name:
        return jsonify({'message': 'Le nom du type de propriété est requis.'}), 400

    if PropertyType.query.filter_by(name=name).first():
        return jsonify({'message': 'Un type de propriété avec ce nom existe déjà.'}), 409

    new_property_type = PropertyType(name=name, description=description)
    db.session.add(new_property_type)
    db.session.commit()
    return jsonify({
        'message': 'Type de propriété créé avec succès.',
        'property_type': new_property_type.to_dict()
    }), 201

@admin_bp.route('/property_types/<int:type_id>', methods=['PUT'])
def update_property_type(type_id):
    property_type = PropertyType.query.get_or_404(type_id)
    data = request.get_json()

    name = data.get('name')
    description = data.get('description')
    is_active = data.get('is_active')

    if name:
        existing = PropertyType.query.filter(
            PropertyType.name == name,
            PropertyType.id != type_id
        ).first()
        if existing:
            return jsonify({'message': 'Un autre type avec ce nom existe déjà.'}), 409
        property_type.name = name
    if description is not None:
        property_type.description = description
    if is_active is not None:
        property_type.is_active = is_active

    db.session.commit()
    return jsonify({
        'message': 'Type de propriété mis à jour avec succès.',
        'property_type': property_type.to_dict()
    })

@admin_bp.route('/property_types/<int:type_id>', methods=['DELETE'])
def delete_property_type(type_id):
    property_type = PropertyType.query.get_or_404(type_id)
    db.session.delete(property_type)
    db.session.commit()
    return jsonify({'message': 'Type de propriété supprimé avec succès.'}), 204

# ---------------------------------
# PROPERTY ATTRIBUTES
# ---------------------------------
@admin_bp.route('/property_attributes', methods=['POST'])
def add_property_attribute():
    data = request.get_json()
    name = data.get('name')
    data_type = data.get('data_type')
    is_filterable = data.get('is_filterable', False)

    if not all([name, data_type]):
        return jsonify({'message': 'Nom et type de données sont requis.'}), 400

    if PropertyAttribute.query.filter_by(name=name).first():
        return jsonify({'message': 'Un attribut avec ce nom existe déjà.'}), 409

    new_attr = PropertyAttribute(
        name=name,
        data_type=data_type,
        is_filterable=is_filterable,
    )
    db.session.add(new_attr)
    db.session.commit()

    if data_type == 'enum' and 'options' in data:
        for val in data['options']:
            db.session.add(AttributeOption(attribute_id=new_attr.id, option_value=val))
        db.session.commit()

    return jsonify({'message': 'Attribut ajouté.', 'attribute': new_attr.to_dict()}), 201

@admin_bp.route('/property_attributes', methods=['GET'])
def get_property_attributes():
    attrs = PropertyAttribute.query.all()
    return jsonify([pa.to_dict() for pa in attrs])

# ---------------------------------
# SCOPES
# ---------------------------------
@admin_bp.route('/property_type_scopes/<int:property_type_id>', methods=['GET'])
def get_property_type_scopes(property_type_id):
    scopes = PropertyAttributeScope.query.filter_by(property_type_id=property_type_id).all()
    return jsonify([s.attribute_id for s in scopes])

@admin_bp.route('/property_type_scopes/<int:property_type_id>', methods=['POST'])
def update_property_type_scopes(property_type_id):
    data = request.get_json()
    attribute_ids = data.get('attribute_ids', [])

    PropertyAttributeScope.query.filter_by(property_type_id=property_type_id).delete()
    for attr_id in attribute_ids:
        db.session.add(PropertyAttributeScope(
            property_type_id=property_type_id,
            attribute_id=attr_id
        ))
    db.session.commit()
    return jsonify({'message': 'Scopes mis à jour.'}), 200

@admin_bp.route('/property_types_with_attributes', methods=['GET'])
def get_property_types_with_attributes():
    property_types = PropertyType.query.all()
    result = []
    for pt in property_types:
        pt_dict = pt.to_dict()
        scopes = PropertyAttributeScope.query.filter_by(property_type_id=pt.id).all()
        attrs = PropertyAttribute.query.filter(
            PropertyAttribute.id.in_([s.attribute_id for s in scopes])
        ).all()
        attrs_list = []
        for attr in attrs:
            d = attr.to_dict()
            if attr.data_type == 'enum':
                d['options'] = [o.to_dict() for o in AttributeOption.query.filter_by(attribute_id=attr.id)]
            attrs_list.append(d)
        pt_dict['attributes'] = attrs_list
        result.append(pt_dict)
    return jsonify(result)

# ---------------------------------
# IMAGE UPLOAD
# ---------------------------------
@admin_bp.route('/upload_image', methods=['POST'])
def upload_image():
    current_app.logger.info("Requête reçue sur /upload_image")
    if 'file' not in request.files:
        return jsonify({"error": "Aucun fichier fourni"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Nom de fichier vide"}), 400

    original_filename = secure_filename(file.filename)
    temp_filename = f"{uuid.uuid4()}_UPLOAD_{original_filename}"
    temp_path = os.path.join(UPLOAD_FOLDER, temp_filename)

    try:
        file.save(temp_path)
        m = get_mega_instance()
        if not m:
            return jsonify({"error": "Connexion stockage impossible"}), 503

        uploaded = m.upload(temp_path)
        public_link = m.get_upload_link(uploaded)
        return jsonify({"url": public_link}), 200
    except Exception as e:
        current_app.logger.error(f"Upload erreur : {e}", exc_info=True)
        return jsonify({"error": "Erreur serveur"}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# ---------------------------------
# VISIT SETTINGS
# ---------------------------------
@admin_bp.route('/settings/visits', methods=['GET'])
def get_visit_settings():
    free = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
    price = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
    settings = {
        'initial_free_visit_passes': int(free.setting_value) if free else 0,
        'visit_pass_price': float(price.amount) if price else 0.0
    }
    return jsonify(VisitSettingsSchema().dump(settings)), 200

@admin_bp.route('/settings/visits', methods=['PUT'])
def update_visit_settings():
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Données JSON non fournies."}), 400

    try:
        data = VisitSettingsSchema().load(json_data)
    except ValidationError as err:
        return jsonify(err.messages), 422

    try:
        free = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
        if free:
            free.setting_value = str(data['initial_free_visit_passes'])
        else:
            free = AppSetting(
                setting_key='initial_free_visit_passes',
                setting_value=str(data['initial_free_visit_passes']),
                data_type='integer',
                description='Nombre de pass gratuits offerts à l\'inscription.'
            )
            db.session.add(free)

        price = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
        if price:
            price.amount = data['visit_pass_price']
        else:
            price = ServiceFee(
                service_key='visit_pass_purchase',
                name='Achat de Pass de Visite',
                amount=data['visit_pass_price'],
                applicable_to_role='customer',
                description='Permet à un client d\'acheter un pass pour visiter.'
            )
            db.session.add(price)

        db.session.commit()
        return jsonify({"message": "Paramètres de visite mis à jour."}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur update visit settings: {e}", exc_info=True)
        return jsonify({"message": "Erreur interne."}), 500

# ---------------------------------
# VISIT REQUESTS
# ---------------------------------
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
        return jsonify({'message': 'La demande n\'est pas en attente.'}), 400

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
        return jsonify({'message': 'Demande confirmée, propriétaire notifié.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur confirmation: {e}")
        return jsonify({'message': 'Erreur interne.'}), 500

@admin_bp.route('/visit_requests/<int:request_id>/reject', methods=['PUT'])
def reject_visit_request_by_admin(request_id):
    vr = VisitRequest.query.get_or_404(request_id)
    if vr.status != 'pending':
        return jsonify({'message': 'La demande n\'est pas en attente.'}), 400

    vr.status = 'rejected'
    message = request.get_json().get('message', 'Demande rejetée par l\'administrateur.')

    try:
        db.session.commit()
        customer = User.query.get(vr.customer_id)
        prop = Property.query.get(vr.property_id)
        if customer and prop:
            send_admin_rejection_notification(customer.email, prop.title, message)
        return jsonify({'message': 'Demande rejetée, client notifié.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur rejet: {e}")
        return jsonify({'message': 'Erreur interne.'}), 500
