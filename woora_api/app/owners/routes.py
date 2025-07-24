# app/owners/routes.py
from flask import Blueprint, request, jsonify
from app import db
from app.models import Property, PropertyImage, User, PropertyType
from flask_jwt_extended import jwt_required, get_jwt_identity

owners_bp = Blueprint('owners', __name__, url_prefix='/owners')

@owners_bp.route('/properties', methods=['POST'])
@jwt_required()
def create_property():
    current_user_id = get_jwt_identity()
    data = request.get_json()

    # --- Validation structure top-level ---
    if not isinstance(data, dict):
        return jsonify({'message': 'Le corps de la requête doit être un objet JSON.'}), 400

    required_top = ['image_urls', 'attributes']
    for field in required_top:
        if field not in data:
            return jsonify({'message': f'Le champ "{field}" est requis.'}), 400

    attrs = data.get('attributes', {})
    required_attrs = ['property_type_id', 'title', 'status', 'price']
    for f in required_attrs:
        if f not in attrs:
            return jsonify({'message': f'L\'attribut "{f}" est requis dans "attributes".'}), 400

    # --- Vérification utilisateur ---
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent créer des biens.'}), 403

    # --- Conversion et validation des types ---
    try:
        property_type_id = int(attrs['property_type_id'])
    except (ValueError, TypeError):
        return jsonify({'message': 'property_type_id doit être un entier.'}), 400

    title = str(attrs['title']).strip()
    if not title:
        return jsonify({'message': 'title ne peut pas être vide.'}), 400

    try:
        price = float(attrs['price'])
    except (ValueError, TypeError):
        return jsonify({'message': 'price doit être un nombre.'}), 400

    allowed_status = {'for_sale', 'for_rent', 'sold', 'rented'}
    status = str(attrs['status']).strip()
    if status not in allowed_status:
        return jsonify({'message': f'status doit être l\'une de : {", ".join(allowed_status)}'}), 400

    # --- Champs optionnels ---
    description = str(attrs.get('description', '')).strip() or None
    address     = str(attrs.get('address', '')).strip() or None
    city        = str(attrs.get('city', '')).strip() or None
    postal_code = str(attrs.get('postal_code', '')).strip() or None
    latitude    = float(attrs['latitude']) if attrs.get('latitude') is not None else None
    longitude   = float(attrs['longitude']) if attrs.get('longitude') is not None else None

    # --- Vérification PropertyType ---
    if not PropertyType.query.get(property_type_id):
        return jsonify({'message': 'Type de propriété introuvable.'}), 400

    # --- Création ---
    new_prop = Property(
        owner_id=current_user_id,
        property_type_id=property_type_id,
        title=title,
        description=description,
        status=status,
        price=price,
        address=address,
        city=city,
        postal_code=postal_code,
        latitude=latitude,
        longitude=longitude,
        attributes=attrs,
        is_validated=False
    )
    db.session.add(new_prop)
    db.session.flush()

    # --- Images ---
    for idx, url in enumerate(data['image_urls'] or []):
        db.session.add(PropertyImage(
            property_id=new_prop.id,
            image_url=str(url),
            display_order=idx
        ))

    try:
        db.session.commit()
        return jsonify({
            'message': 'Bien créé avec succès.',
            'property': new_prop.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Erreur interne.', 'details': str(e)}), 500
