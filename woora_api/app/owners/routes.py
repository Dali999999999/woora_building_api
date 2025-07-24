# app/owners/routes.py
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import Property, PropertyImage, User, PropertyType
from flask_jwt_extended import jwt_required, get_jwt_identity

owners_bp = Blueprint('owners', __name__, url_prefix='/owners')

@owners_bp.route('/properties', methods=['POST'])
@jwt_required()
def create_property():
    # --- logging très explicite ---
    current_app.logger.info("POST /owners/properties reçu")
    current_user_id = get_jwt_identity()
    data = request.get_json()

    # 1) on renvoie toujours le payload dans la 422
    if not isinstance(data, dict):
        return jsonify({'message': 'Body JSON attendu', 'received': data}), 422

    # 2) champ racine
    for k in ('image_urls', 'attributes'):
        if k not in data:
            return jsonify({'message': f'{k} manquant', 'received': data}), 422

    attrs = data['attributes']

    # 3) champs obligatoires dans attributes
    required_attrs = {
        'property_type_id': int,
        'title': str,
        'price': (int, float),
        'status': str
    }
    for key, types in required_attrs.items():
        if key not in attrs:
            return jsonify({'message': f'{key} manquant dans attributes', 'received': attrs}), 422
        try:
            if key == 'property_type_id':
                attrs[key] = int(attrs[key])
            elif key == 'price':
                attrs[key] = float(attrs[key])
            elif key == 'title':
                attrs[key] = str(attrs[key]).strip()
            elif key == 'status':
                attrs[key] = str(attrs[key]).strip()
        except (ValueError, TypeError):
            return jsonify({'message': f'{key} invalide', 'received': attrs}), 422

    # 4) vérification valeurs autorisées
    allowed_status = {'for_sale', 'for_rent', 'sold', 'rented'}
    if attrs['status'] not in allowed_status:
        return jsonify({'message': 'status doit être for_sale, for_rent, sold ou rented', 'received': attrs}), 422

    # 5) vérification PropertyType
    if not PropertyType.query.get(attrs['property_type_id']):
        return jsonify({'message': 'property_type_id inconnu', 'received': attrs}), 422

    # 6) rôle utilisateur
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès refusé : rôle owner requis'}), 403

    # 7) création Property
    prop = Property(
        owner_id=current_user_id,
        property_type_id=attrs['property_type_id'],
        title=attrs['title'],
        status=attrs['status'],
        price=attrs['price'],
        description=str(attrs.get('description', '')) or None,
        attributes=attrs,
        is_validated=False
    )
    db.session.add(prop)
    db.session.flush()

    # 8) images
    for idx, url in enumerate(data.get('image_urls') or []):
        db.session.add(PropertyImage(
            property_id=prop.id,
            image_url=str(url),
            display_order=idx
        ))

    try:
        db.session.commit()
        return jsonify({'message': 'Bien créé', 'property': prop.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': str(e)}), 500
