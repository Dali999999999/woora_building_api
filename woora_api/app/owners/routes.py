
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

    # Valider les données requises minimales (image_urls et attributes)
    required_top_level_fields = ['image_urls', 'attributes']
    for field in required_top_level_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis au niveau supérieur.'}), 400

    dynamic_attributes = data.get('attributes', {})

    # Valider les champs essentiels qui sont maintenant dynamiques
    essential_dynamic_fields = ['property_type_id', 'title', 'status', 'price']
    for field in essential_dynamic_fields:
        if field not in dynamic_attributes:
            return jsonify({'message': f'L\'attribut dynamique "{field}" est requis.'}), 400

    # Vérifier l'existence de l'owner et son rôle
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent créer des biens.'}), 403

    # Extraire et valider les champs essentiels
    try:
        property_type_id = int(dynamic_attributes.get('property_type_id'))
    except (ValueError, TypeError):
        return jsonify({'message': 'property_type_id doit être un entier valide.'}), 400

    title = dynamic_attributes.get('title')
    if not isinstance(title, str) or not title:
        return jsonify({'message': 'title est requis et doit être une chaîne de caractères non vide.'}), 400

    try:
        price = float(dynamic_attributes.get('price'))
    except (ValueError, TypeError):
        return jsonify({'message': 'price doit être un nombre décimal valide.'}), 400

    status = dynamic_attributes.get('status')
    allowed_statuses = ['for_sale', 'for_rent', 'sold', 'rented']
    if status not in allowed_statuses:
        return jsonify({'message': f'status invalide. Doit être l\'une des valeurs suivantes: {", ".join(allowed_statuses)}.'}), 400

    # Gérer les champs optionnels avec des valeurs par défaut ou None
    description = dynamic_attributes.get('description')
    if description is not None and not isinstance(description, str):
        return jsonify({'message': 'description doit être une chaîne de caractères.'}), 400

    address = dynamic_attributes.get('address')
    if address is not None and not isinstance(address, str):
        return jsonify({'message': 'address doit être une chaîne de caractères.'}), 400

    city = dynamic_attributes.get('city')
    if city is not None and not isinstance(city, str):
        return jsonify({'message': 'city doit être une chaîne de caractères.'}), 400

    postal_code = dynamic_attributes.get('postal_code')
    if postal_code is not None and not isinstance(postal_code, str):
        return jsonify({'message': 'postal_code doit être une chaîne de caractères.'}), 400

    latitude = None
    if 'latitude' in dynamic_attributes and dynamic_attributes['latitude'] is not None:
        try:
            latitude = float(dynamic_attributes['latitude'])
        except (ValueError, TypeError):
            return jsonify({'message': 'latitude doit être un nombre décimal valide.'}), 400

    longitude = None
    if 'longitude' in dynamic_attributes and dynamic_attributes['longitude'] is not None:
        try:
            longitude = float(dynamic_attributes['longitude'])
        except (ValueError, TypeError):
            return jsonify({'message': 'longitude doit être un nombre décimal valide.'}), 400

    property_type = PropertyType.query.get(property_type_id)
    if not property_type:
        return jsonify({'message': 'Type de propriété invalide ou non trouvé.'}), 400

    # Créer le bien immobilier
    new_property = Property(
        owner_id=current_user_id, # Utiliser l'ID de l'utilisateur authentifié
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
        attributes=dynamic_attributes, # Stocker tous les attributs dynamiques
        is_validated=False # Par défaut, le bien n'est pas validé
    )

    db.session.add(new_property)
    db.session.flush() # Pour obtenir l'ID du bien avant de commiter

    # Enregistrer les images
    if data['image_urls']:
        for i, image_url in enumerate(data['image_urls']):
            new_image = PropertyImage(
                property_id=new_property.id,
                image_url=image_url,
                display_order=i
            )
            db.session.add(new_image)

    try:
        db.session.commit()
        return jsonify({'message': 'Bien immobilier créé avec succès.', 'property': new_property.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Erreur lors de la création du bien immobilier.', 'error': str(e)}), 500
