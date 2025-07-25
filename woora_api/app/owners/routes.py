
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import Property, PropertyImage, User, PropertyType
from flask_jwt_extended import jwt_required, get_jwt_identity

owners_bp = Blueprint('owners', __name__, url_prefix='/owners')

@owners_bp.route('/properties', methods=['POST'])
@jwt_required()
def create_property():
    current_app.logger.debug("Requête POST /owners/properties reçue.")
    current_user_id = get_jwt_identity()
    current_app.logger.debug(f"Utilisateur authentifié ID: {current_user_id}")

    data = request.get_json()
    import logging
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("🔍 Payload reçu : %s", data)
    current_app.logger.debug(f"JSON brut reçu: {data}")

    # Valider les données requises minimales (image_urls et attributes)
    required_top_level_fields = ['image_urls', 'attributes']
    for field in required_top_level_fields:
        if field not in data:
            current_app.logger.warning(f"Champ de niveau supérieur manquant: {field}")
            return jsonify({'message': f'Le champ {field} est requis au niveau supérieur.'}), 400

    dynamic_attributes = data.get('attributes', {})
    current_app.logger.debug(f"Attributs dynamiques extraits: {dynamic_attributes}")

    # Vérifier l'existence de l'owner et son rôle
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        current_app.logger.warning(f"Accès non autorisé pour l'utilisateur {current_user_id} avec le rôle {owner.role if owner else 'N/A'}.")
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent créer des biens.'}), 403

    # Extraire et valider les champs essentiels
    property_type_id = dynamic_attributes.get('property_type_id')
    current_app.logger.debug(f"property_type_id brut: {property_type_id}, type: {type(property_type_id)}")
    try:
        property_type_id = int(property_type_id)
        current_app.logger.debug(f"property_type_id converti: {property_type_id}, type: {type(property_type_id)}")
    except (ValueError, TypeError):
        current_app.logger.warning(f"Validation échouée: property_type_id doit être un entier valide. Reçu: {property_type_id}")
        return jsonify({'message': 'property_type_id doit être un entier valide.'}), 400

    title = dynamic_attributes.get('title')
    current_app.logger.debug(f"title brut: {title}, type: {type(title)}")
    if not isinstance(title, str) or not title:
        current_app.logger.warning(f"Validation échouée: title est requis et doit être une chaîne de caractères non vide. Reçu: {title}")
        return jsonify({'message': 'title est requis et doit être une chaîne de caractères non vide.'}), 400

    price = dynamic_attributes.get('price')
    current_app.logger.debug(f"price brut: {price}, type: {type(price)}")
    try:
        price = float(price)
        current_app.logger.debug(f"price converti: {price}, type: {type(price)}")
    except (ValueError, TypeError):
        current_app.logger.warning(f"Validation échouée: price doit être un nombre décimal valide. Reçu: {price}")
        return jsonify({'message': 'price doit être un nombre décimal valide.'}), 400

    status = dynamic_attributes.get('status')
    current_app.logger.debug(f"status brut: {status}, type: {type(status)}")
    allowed_statuses = ['for_sale', 'for_rent', 'sold', 'rented']
    if status not in allowed_statuses:
        current_app.logger.warning(f"Validation échouée: status invalide. Reçu: {status}")
        return jsonify({'message': f'status invalide. Doit être l\'une des valeurs suivantes: {", ".join(allowed_statuses)}.'}), 400

    # Gérer les champs optionnels avec des valeurs par défaut ou None
    description = dynamic_attributes.get('description')
    current_app.logger.debug(f"description brut: {description}, type: {type(description)}")
    if description is not None and not isinstance(description, str):
        current_app.logger.warning(f"Validation échouée: description doit être une chaîne de caractères. Reçu: {description}")
        return jsonify({'message': 'description doit être une chaîne de caractères.'}), 400

    address = dynamic_attributes.get('address')
    current_app.logger.debug(f"address brut: {address}, type: {type(address)}")
    if address is not None and not isinstance(address, str):
        current_app.logger.warning(f"Validation échouée: address doit être une chaîne de caractères. Reçu: {address}")
        return jsonify({'message': 'address doit être une chaîne de caractères.'}), 400

    city = dynamic_attributes.get('city')
    current_app.logger.debug(f"city brut: {city}, type: {type(city)}")
    if city is not None and not isinstance(city, str):
        current_app.logger.warning(f"Validation échouée: city doit être une chaîne de caractères. Reçu: {city}")
        return jsonify({'message': 'city doit être une chaîne de caractères.'}), 400

    postal_code = dynamic_attributes.get('postal_code')
    current_app.logger.debug(f"postal_code brut: {postal_code}, type: {type(postal_code)}")
    if postal_code is not None and not isinstance(postal_code, str):
        current_app.logger.warning(f"Validation échouée: postal_code doit être une chaîne de caractères. Reçu: {postal_code}")
        return jsonify({'message': 'postal_code doit être une chaîne de caractères.'}), 400

    latitude = None
    if 'latitude' in dynamic_attributes and dynamic_attributes['latitude'] is not None:
        current_app.logger.debug(f"latitude brut: {dynamic_attributes['latitude']}, type: {type(dynamic_attributes['latitude'])}")
        try:
            latitude = float(dynamic_attributes['latitude'])
            current_app.logger.debug(f"latitude converti: {latitude}, type: {type(latitude)}")
        except (ValueError, TypeError):
            current_app.logger.warning(f"Validation échouée: latitude doit être un nombre décimal valide. Reçu: {dynamic_attributes['latitude']}")
            return jsonify({'message': 'latitude doit être un nombre décimal valide.'}), 400

    longitude = None
    if 'longitude' in dynamic_attributes and dynamic_attributes['longitude'] is not None:
        current_app.logger.debug(f"longitude brut: {dynamic_attributes['longitude']}, type: {type(dynamic_attributes['longitude'])}")
        try:
            longitude = float(dynamic_attributes['longitude'])
            current_app.logger.debug(f"longitude converti: {longitude}, type: {type(longitude)}")
        except (ValueError, TypeError):
            current_app.logger.warning(f"Validation échouée: longitude doit être un nombre décimal valide. Reçu: {dynamic_attributes['longitude']}")
            return jsonify({'message': 'longitude doit être un nombre décimal valide.'}), 400

    property_type = PropertyType.query.get(property_type_id)
    if not property_type:
        current_app.logger.warning(f"Validation échouée: Type de propriété invalide ou non trouvé. ID: {property_type_id}")
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
    current_app.logger.debug(f"Nouvelle propriété créée (avant commit): {new_property}")

    db.session.add(new_property)
    db.session.flush() # Pour obtenir l'ID du bien avant de commiter
    current_app.logger.debug(f"ID de la nouvelle propriété après flush: {new_property.id}")

    # Enregistrer les images
    image_urls = data.get('image_urls', [])
    current_app.logger.debug(f"URLs d'images à enregistrer: {image_urls}")
    if image_urls:
        for i, image_url in enumerate(image_urls):
            new_image = PropertyImage(
                property_id=new_property.id,
                image_url=image_url,
                display_order=i
            )
            db.session.add(new_image)
            current_app.logger.debug(f"Image ajoutée: {image_url}")

    try:
        db.session.commit()
        current_app.logger.info("Bien immobilier créé avec succès et commité.")
        return jsonify({'message': 'Bien immobilier créé avec succès.', 'property': new_property.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création du bien immobilier (rollback): {e}", exc_info=True)
        return jsonify({'message': 'Erreur lors de la création du bien immobilier.', 'error': str(e)}), 500

@owners_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_owner_properties():
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent voir leurs biens.'}), 403

    properties = Property.query.filter_by(owner_id=current_user_id).all()
    return jsonify([p.to_dict() for p in properties]), 200

@owners_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_owner_property_details(property_id):
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent voir les détails de leurs biens.'}), 403

    property = Property.query.filter_by(id=property_id, owner_id=current_user_id).first()
    if not property:
        return jsonify({'message': 'Bien immobilier non trouvé ou vous n'êtes pas le propriétaire.'}), 404

    property_dict = property.to_dict()
    property_dict['images'] = [img.image_url for img in property.images]
    return jsonify(property_dict), 200

@owners_bp.route('/properties/<int:property_id>', methods=['PUT'])
@jwt_required()
def update_owner_property(property_id):
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent modifier leurs biens.'}), 403

    property = Property.query.filter_by(id=property_id, owner_id=current_user_id).first()
    if not property:
        return jsonify({'message': 'Bien immobilier non trouvé ou vous n'êtes pas le propriétaire.'}), 404

    data = request.get_json()
    current_app.logger.debug(f"Données reçues pour la mise à jour du bien {property_id}: {data}")

    # Update fixed fields
    if 'attributes' in data:
        dynamic_attributes = data.get('attributes', {})
        if 'property_type_id' in dynamic_attributes:
            try:
                property_type_id = int(dynamic_attributes['property_type_id'])
                property_type = PropertyType.query.get(property_type_id)
                if not property_type:
                    return jsonify({'message': 'Type de propriété invalide ou non trouvé.'}), 400
                property.property_type_id = property_type_id
            except (ValueError, TypeError):
                return jsonify({'message': 'property_type_id doit être un entier valide.'}), 400
        if 'title' in dynamic_attributes:
            if not isinstance(dynamic_attributes['title'], str) or not dynamic_attributes['title']:
                return jsonify({'message': 'title est requis et doit être une chaîne de caractères non vide.'}), 400
            property.title = dynamic_attributes['title']
        if 'price' in dynamic_attributes:
            try:
                property.price = float(dynamic_attributes['price'])
            except (ValueError, TypeError):
                return jsonify({'message': 'price doit être un nombre décimal valide.'}), 400
        if 'status' in dynamic_attributes:
            allowed_statuses = ['for_sale', 'for_rent', 'sold', 'rented']
            if dynamic_attributes['status'] not in allowed_statuses:
                return jsonify({'message': f'status invalide. Doit être l'une des valeurs suivantes: {", ".join(allowed_statuses)}.'}), 400
            property.status = dynamic_attributes['status']
        if 'description' in dynamic_attributes:
            if dynamic_attributes['description'] is not None and not isinstance(dynamic_attributes['description'], str):
                return jsonify({'message': 'description doit être une chaîne de caractères.'}), 400
            property.description = dynamic_attributes['description']
        if 'address' in dynamic_attributes:
            if dynamic_attributes['address'] is not None and not isinstance(dynamic_attributes['address'], str):
                return jsonify({'message': 'address doit être une chaîne de caractères.'}), 400
            property.address = dynamic_attributes['address']
        if 'city' in dynamic_attributes:
            if dynamic_attributes['city'] is not None and not isinstance(dynamic_attributes['city'], str):
                return jsonify({'message': 'city doit être une chaîne de caractères.'}), 400
            property.city = dynamic_attributes['city']
        if 'postal_code' in dynamic_attributes:
            if dynamic_attributes['postal_code'] is not None and not isinstance(dynamic_attributes['postal_code'], str):
                return jsonify({'message': 'postal_code doit être une chaîne de caractères.'}), 400
            property.postal_code = dynamic_attributes['postal_code']
        if 'latitude' in dynamic_attributes:
            try:
                property.latitude = float(dynamic_attributes['latitude']) if dynamic_attributes['latitude'] is not None else None
            except (ValueError, TypeError):
                return jsonify({'message': 'latitude doit être un nombre décimal valide.'}), 400
        if 'longitude' in dynamic_attributes:
            try:
                property.longitude = float(dynamic_attributes['longitude']) if dynamic_attributes['longitude'] is not None else None
            except (ValueError, TypeError):
                return jsonify({'message': 'longitude doit être un nombre décimal valide.'}), 400

        # Update dynamic attributes (JSONB field)
        property.attributes.update(dynamic_attributes)

    # Handle images
    if 'image_urls' in data:
        # Delete existing images for this property
        PropertyImage.query.filter_by(property_id=property.id).delete()
        db.session.flush() # Ensure deletion before adding new ones

        # Add new images
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
        return jsonify({'message': 'Bien immobilier mis à jour avec succès.', 'property': property.to_dict()}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la mise à jour du bien immobilier (rollback): {e}", exc_info=True)
        return jsonify({'message': 'Erreur lors de la mise à jour du bien immobilier.', 'error': str(e)}), 500

@owners_bp.route('/properties/<int:property_id>', methods=['DELETE'])
@jwt_required()
def delete_owner_property(property_id):
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent supprimer leurs biens.'}), 403

    property = Property.query.filter_by(id=property_id, owner_id=current_user_id).first()
    if not property:
        return jsonify({'message': 'Bien immobilier non trouvé ou vous n'êtes pas le propriétaire.'}), 404

    try:
        db.session.delete(property)
        db.session.commit()
        return jsonify({'message': 'Bien immobilier supprimé avec succès.'}), 204
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la suppression du bien immobilier (rollback): {e}", exc_info=True)
        return jsonify({'message': 'Erreur lors de la suppression du bien immobilier.', 'error': str(e)}), 500
