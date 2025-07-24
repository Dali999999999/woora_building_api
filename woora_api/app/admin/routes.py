
from flask import Blueprint, jsonify, request
from app.models import User, Property, PropertyType, PropertyAttribute, AttributeOption, PropertyAttributeScope, db

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/users', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users])

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify(user.to_dict())

@admin_bp.route('/properties', methods=['GET'])
def get_properties():
    properties = Property.query.all()
    return jsonify([p.to_dict() for p in properties])

@admin_bp.route('/property_types', methods=['GET'])
def get_property_types():
    property_types = PropertyType.query.all()
    return jsonify([pt.to_dict() for pt in property_types])

@admin_bp.route('/property_attributes', methods=['POST'])
def add_property_attribute():
    data = request.get_json()
    name = data.get('name')
    data_type = data.get('data_type')
    is_filterable = data.get('is_filterable', False)
    # created_by = data.get('created_by') # Assuming admin user for now

    if not all([name, data_type]):
        return jsonify({'message': 'Nom et type de données sont requis.'}), 400

    if PropertyAttribute.query.filter_by(name=name).first():
        return jsonify({'message': 'Un attribut avec ce nom existe déjà.'}), 409

    new_attribute = PropertyAttribute(
        name=name,
        data_type=data_type,
        is_filterable=is_filterable,
        # created_by=created_by
    )
    db.session.add(new_attribute)
    db.session.commit()

    if data_type == 'enum' and 'options' in data:
        for option_value in data['options']:
            new_option = AttributeOption(
                attribute_id=new_attribute.id,
                option_value=option_value
            )
            db.session.add(new_option)
        db.session.commit()

    return jsonify({'message': 'Attribut ajouté avec succès.', 'attribute': new_attribute.to_dict()}), 201

@admin_bp.route('/property_attributes', methods=['GET'])
def get_property_attributes():
    property_attributes = PropertyAttribute.query.all()
    return jsonify([pa.to_dict() for pa in property_attributes])
