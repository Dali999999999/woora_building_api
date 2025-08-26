# /opt/render/project/src/woora_api/app/owners/routes.py

from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import Property, PropertyImage, User, PropertyType, VisitRequest,  PropertyAttributeScope, PropertyAttribute, AttributeOption
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.orm.attributes import flag_modified
from app.utils.email_utils import send_owner_acceptance_notification, send_owner_rejection_notification
from app.utils.mega_utils import get_mega_instance
from werkzeug.utils import secure_filename
import os
import uuid

UPLOAD_FOLDER = '/tmp' # Définir le dossier d'upload

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

    required_top_level_fields = ['image_urls', 'attributes']
    for field in required_top_level_fields:
        if field not in data:
            current_app.logger.warning(f"Champ de niveau supérieur manquant: {field}")
            # CORRECTION : Utilisation de guillemets doubles pour éviter le conflit avec l'apostrophe.
            return jsonify({'message': f"Le champ {field} est requis au niveau supérieur."}), 400

    dynamic_attributes = data.get('attributes', {})
    current_app.logger.debug(f"Attributs dynamiques extraits: {dynamic_attributes}")

    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        current_app.logger.warning(f"Accès non autorisé pour l'utilisateur {current_user_id} avec le rôle {owner.role if owner else 'N/A'}.")
        # CORRECTION
        return jsonify({'message': "Accès non autorisé. Seuls les propriétaires peuvent créer des biens."}), 403

    property_type_id = dynamic_attributes.get('property_type_id')
    current_app.logger.debug(f"property_type_id brut: {property_type_id}, type: {type(property_type_id)}")
    try:
        property_type_id = int(property_type_id)
        current_app.logger.debug(f"property_type_id converti: {property_type_id}, type: {type(property_type_id)}")
    except (ValueError, TypeError):
        current_app.logger.warning(f"Validation échouée: property_type_id doit être un entier valide. Reçu: {property_type_id}")
        return jsonify({'message': "property_type_id doit être un entier valide."}), 400

    title = dynamic_attributes.get('title')
    current_app.logger.debug(f"title brut: {title}, type: {type(title)}")
    if not isinstance(title, str) or not title:
        current_app.logger.warning(f"Validation échouée: title est requis et doit être une chaîne de caractères non vide. Reçu: {title}")
        # CORRECTION
        return jsonify({'message': "title est requis et doit être une chaîne de caractères non vide."}), 400

    price = dynamic_attributes.get('price')
    current_app.logger.debug(f"price brut: {price}, type: {type(price)}")
    try:
        price = float(price)
        current_app.logger.debug(f"price converti: {price}, type: {type(price)}")
    except (ValueError, TypeError):
        current_app.logger.warning(f"Validation échouée: price doit être un nombre décimal valide. Reçu: {price}")
        return jsonify({'message': "price doit être un nombre décimal valide."}), 400

    status = dynamic_attributes.get('status')
    current_app.logger.debug(f"status brut: {status}, type: {type(status)}")
    allowed_statuses = ['for_sale', 'for_rent', 'sold', 'rented']
    if status not in allowed_statuses:
        current_app.logger.warning(f"Validation échouée: status invalide. Reçu: {status}")
        # CORRECTION
        return jsonify({'message': f"status invalide. Doit être l'une des valeurs suivantes: {', '.join(allowed_statuses)}."}), 400

    description = dynamic_attributes.get('description')
    current_app.logger.debug(f"description brut: {description}, type: {type(description)}")
    if description is not None and not isinstance(description, str):
        current_app.logger.warning(f"Validation échouée: description doit être une chaîne de caractères. Reçu: {description}")
        return jsonify({'message': "description doit être une chaîne de caractères."}), 400

    address = dynamic_attributes.get('address')
    current_app.logger.debug(f"address brut: {address}, type: {type(address)}")
    if address is not None and not isinstance(address, str):
        current_app.logger.warning(f"Validation échouée: address doit être une chaîne de caractères. Reçu: {address}")
        return jsonify({'message': "address doit être une chaîne de caractères."}), 400

    city = dynamic_attributes.get('city')
    current_app.logger.debug(f"city brut: {city}, type: {type(city)}")
    if city is not None and not isinstance(city, str):
        current_app.logger.warning(f"Validation échouée: city doit être une chaîne de caractères. Reçu: {city}")
        return jsonify({'message': "city doit être une chaîne de caractères."}), 400

    postal_code = dynamic_attributes.get('postal_code')
    current_app.logger.debug(f"postal_code brut: {postal_code}, type: {type(postal_code)}")
    if postal_code is not None and not isinstance(postal_code, str):
        current_app.logger.warning(f"Validation échouée: postal_code doit être une chaîne de caractères. Reçu: {postal_code}")
        return jsonify({'message': "postal_code doit être une chaîne de caractères."}), 400

    latitude = None
    if 'latitude' in dynamic_attributes and dynamic_attributes['latitude'] is not None:
        current_app.logger.debug(f"latitude brut: {dynamic_attributes['latitude']}, type: {type(dynamic_attributes['latitude'])}")
        try:
            latitude = float(dynamic_attributes['latitude'])
            current_app.logger.debug(f"latitude converti: {latitude}, type: {type(latitude)}")
        except (ValueError, TypeError):
            current_app.logger.warning(f"Validation échouée: latitude doit être un nombre décimal valide. Reçu: {dynamic_attributes['latitude']}")
            return jsonify({'message': "latitude doit être un nombre décimal valide."}), 400

    longitude = None
    if 'longitude' in dynamic_attributes and dynamic_attributes['longitude'] is not None:
        current_app.logger.debug(f"longitude brut: {dynamic_attributes['longitude']}, type: {type(dynamic_attributes['longitude'])}")
        try:
            longitude = float(dynamic_attributes['longitude'])
            current_app.logger.debug(f"longitude converti: {longitude}, type: {type(longitude)}")
        except (ValueError, TypeError):
            current_app.logger.warning(f"Validation échouée: longitude doit être un nombre décimal valide. Reçu: {dynamic_attributes['longitude']}")
            return jsonify({'message': "longitude doit être un nombre décimal valide."}), 400

    property_type = PropertyType.query.get(property_type_id)
    if not property_type:
        current_app.logger.warning(f"Validation échouée: Type de propriété invalide ou non trouvé. ID: {property_type_id}")
        return jsonify({'message': "Type de propriété invalide ou non trouvé."}), 400

    new_property = Property(
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
        attributes=dynamic_attributes,
        is_validated=False
    )
    current_app.logger.debug(f"Nouvelle propriété créée (avant commit): {new_property}")

    db.session.add(new_property)
    db.session.flush()
    current_app.logger.debug(f"ID de la nouvelle propriété après flush: {new_property.id}")

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
        return jsonify({'message': "Bien immobilier créé avec succès.", 'property': new_property.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la création du bien immobilier (rollback): {e}", exc_info=True)
        # CORRECTION
        return jsonify({'message': "Erreur lors de la création du bien immobilier.", 'error': str(e)}), 500


@owners_bp.route('/properties', methods=['GET'])
@jwt_required()
def get_all_owner_properties(): # NOUVEAU NOM : get_ALL_owner_properties
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': "Accès non autorisé. Seuls les propriétaires peuvent voir leurs biens."}), 403

    properties = Property.query.filter_by(owner_id=current_user_id).all()
    
    properties_with_images = []
    for prop in properties:
        property_dict = prop.to_dict()
        property_dict['image_urls'] = [image.image_url for image in prop.images]
        properties_with_images.append(property_dict)

    return jsonify(properties_with_images), 200



@owners_bp.route('/properties/<int:property_id>', methods=['GET'])
@jwt_required()
def get_owner_property_details(property_id): # NOUVEAU NOM (ou gardez celui-ci s'il est unique)
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': "Accès non autorisé. Seuls les propriétaires peuvent voir les détails de leurs biens."}), 403

    property = Property.query.filter_by(id=property_id, owner_id=current_user_id).first()
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé ou vous n'êtes pas le propriétaire."}), 404

    property_dict = property.to_dict()
    # Important : Assurez-vous d'ajouter aussi les images ici pour la page de détails !
    property_dict['image_urls'] = [img.image_url for img in property.images] 
    return jsonify(property_dict), 200

@owners_bp.route('/properties/<int:property_id>', methods=['PUT'])
@jwt_required()
def update_owner_property(property_id):
    """
    Met à jour un bien immobilier existant.
    Gère à la fois les champs statiques (colonnes de la table) et les attributs dynamiques (champ JSON).
    """
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': "Accès non autorisé. Seuls les propriétaires peuvent modifier leurs biens."}), 403

    property = Property.query.filter_by(id=property_id, owner_id=current_user_id).first()
    if not property:
        return jsonify({'message': "Bien immobilier non trouvé ou vous n'êtes pas le propriétaire."}), 404

    data = request.get_json()
    if not data:
        return jsonify({'message': "Corps de la requête manquant ou invalide."}), 400
        
    current_app.logger.debug(f"Données reçues pour la mise à jour du bien {property_id}: {data}")

    attributes_data = data.get('attributes')
    if attributes_data:
        # 1. Mise à jour des champs STATIQUES (colonnes directes du modèle Property)
        # On met à jour un champ uniquement si sa clé est présente dans la requête.
        
        if 'title' in attributes_data:
            property.title = attributes_data['title']
        
        if 'price' in attributes_data:
            try:
                # Gère le cas où le prix est None
                property.price = float(attributes_data['price']) if attributes_data['price'] is not None else None
            except (ValueError, TypeError):
                return jsonify({'message': "Le prix doit être un nombre valide."}), 400
        
        if 'status' in attributes_data:
            property.status = attributes_data['status']
            
        if 'description' in attributes_data:
            property.description = attributes_data.get('description')
            
        if 'address' in attributes_data:
            property.address = attributes_data.get('address')
            
        if 'city' in attributes_data:
            property.city = attributes_data.get('city')
            
        if 'postal_code' in attributes_data:
            property.postal_code = attributes_data.get('postal_code')
            
        # Gestion robuste pour les champs numériques optionnels (latitude/longitude)
        if 'latitude' in attributes_data:
            lat_val = attributes_data.get('latitude')
            try:
                # Si la valeur est une chaîne vide, "null", ou None, on met la colonne à NULL.
                property.latitude = float(lat_val) if lat_val and str(lat_val).lower() != 'null' else None
            except (ValueError, TypeError):
                return jsonify({'message': 'latitude doit être un nombre décimal valide.'}), 400
                
        if 'longitude' in attributes_data:
            lon_val = attributes_data.get('longitude')
            try:
                property.longitude = float(lon_val) if lon_val and str(lon_val).lower() != 'null' else None
            except (ValueError, TypeError):
                return jsonify({'message': 'longitude doit être un nombre décimal valide.'}), 400

        # 2. Mise à jour du champ DYNAMIQUE (colonne JSON 'attributes')
        if property.attributes is None:
            property.attributes = {}
        
        # On fusionne les nouvelles données dans le champ JSON existant
        property.attributes.update(attributes_data)
        
        # On force SQLAlchemy à détecter que le contenu du champ JSON a été modifié
        flag_modified(property, "attributes")

    # La gestion des images reste la même, elle est correcte
    if 'image_urls' in data:
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
        
        # Utiliser la méthode to_dict() du modèle pour une réponse cohérente
        updated_property_dict = property.to_dict()
        
        return jsonify({
            'message': "Bien immobilier mis à jour avec succès.",
            'property': updated_property_dict
        }), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la mise à jour du bien immobilier (rollback): {e}", exc_info=True)
        return jsonify({'message': "Erreur lors de la mise à jour du bien immobilier.", 'error': str(e)}), 500

@owners_bp.route('/properties/<int:property_id>', methods=['DELETE'])
@jwt_required()
def delete_owner_property(property_id):
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        # CORRECTION
        return jsonify({'message': "Accès non autorisé. Seuls les propriétaires peuvent supprimer leurs biens."}), 403

    property = Property.query.filter_by(id=property_id, owner_id=current_user_id).first()
    if not property:
        # CORRECTION
        return jsonify({'message': "Bien immobilier non trouvé ou vous n'êtes pas le propriétaire."}), 404

    try:
        db.session.delete(property)
        db.session.commit()
        # CORRECTION
        return jsonify({'message': "Bien immobilier supprimé avec succès."}), 204
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la suppression du bien immobilier (rollback): {e}", exc_info=True)
        # CORRECTION
        return jsonify({'message': "Erreur lors de la suppression du bien immobilier.", 'error': str(e)}), 500

@owners_bp.route('/visit_requests', methods=['GET'])
@jwt_required()
def get_owner_visit_requests():
    """
    Récupère toutes les demandes de visite pour les biens d'un propriétaire,
    à condition que la demande ait été confirmée par un administrateur.
    """
    current_user_id = get_jwt_identity()
    
    # On fait une jointure pour ne récupérer que les demandes de visite (vr)
    # qui appartiennent à des biens (Property) dont l'owner_id est celui de l'utilisateur connecté.
    # C'est la requête la plus sûre et la plus efficace.
    visit_requests = db.session.query(VisitRequest).join(Property).filter(
        Property.owner_id == current_user_id,
        VisitRequest.status == 'confirmed' # On ne montre que celles à traiter
    ).all()

    # On construit la réponse
    result = []
    for req in visit_requests:
        # Les relations back_populates nous permettent d'accéder facilement aux objets liés
        customer = req.customer
        property_obj = req.property
        
        req_dict = {
            'id': req.id,
            'customer_name': f'{customer.first_name} {customer.last_name}' if customer else 'Client inconnu',
            'customer_email': customer.email if customer else 'Email inconnu',
            'property_title': property_obj.title if property_obj else 'Bien inconnu',
            'requested_datetime': req.requested_datetime.isoformat(),
            'status': req.status,
            'message': req.message,
            'created_at': req.created_at.isoformat()
        }
        result.append(req_dict)
        
    return jsonify(result), 200

@owners_bp.route('/visit_requests/<int:request_id>/accept', methods=['PUT'])
@jwt_required()
def accept_visit_request_by_owner(request_id):
    """
    Accepte une demande de visite.
    La logique de vérification est maintenant unifiée et robuste.
    """
    current_user_id = get_jwt_identity()

    # On fait une requête unique qui trouve la demande ET vérifie l'appartenance.
    # On cherche une VisitRequest...
    visit_request = db.session.query(VisitRequest).join(Property).filter(
        VisitRequest.id == request_id,              # ... avec le bon ID
        Property.owner_id == current_user_id      # ... ET qui appartient à un bien du propriétaire connecté.
    ).first()

    # Si la requête ne trouve rien, c'est soit que la demande n'existe pas,
    # soit qu'elle n'appartient pas au propriétaire. La réponse est la même.
    if not visit_request:
        return jsonify({'message': "Demande de visite non trouvée ou non associée à vos propriétés."}), 404

    # On vérifie que le statut est bien 'confirmed' avant d'agir
    if visit_request.status != 'confirmed':
        return jsonify({'message': f"Cette demande ne peut pas être acceptée car son statut est '{visit_request.status}'."}), 400

    visit_request.status = 'accepted'

    try:
        db.session.commit()

        # Envoyer une notification par e-mail au client
        customer = visit_request.customer
        property_obj = visit_request.property
        if customer and property_obj:
            send_owner_acceptance_notification(
                customer.email,
                property_obj.title,
                visit_request.requested_datetime.strftime('%d/%m/%Y à %Hh%M')
            )

        return jsonify({'message': 'Demande de visite acceptée avec succès. Notification envoyée au client.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de l'acceptation de la demande de visite par le propriétaire: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

@owners_bp.route('/visit_requests/<int:request_id>/reject', methods=['PUT'])
@jwt_required()
def reject_visit_request_by_owner(request_id):
    """
    Rejette une demande de visite.
    La logique de vérification est identique à celle de l'acceptation.
    """
    current_user_id = get_jwt_identity()

    # On utilise exactement la même requête de vérification que pour 'accept'
    visit_request = db.session.query(VisitRequest).join(Property).filter(
        VisitRequest.id == request_id,
        Property.owner_id == current_user_id
    ).first()

    if not visit_request:
        return jsonify({'message': "Demande de visite non trouvée ou non associée à vos propriétés."}), 404

    if visit_request.status != 'confirmed':
        return jsonify({'message': f"Cette demande ne peut pas être rejetée car son statut est '{visit_request.status}'."}), 400

    visit_request.status = 'rejected'
    
    # On récupère le message de rejet optionnel
    data = request.get_json() or {}
    message = data.get('message', 'La demande de visite a été rejetée par le propriétaire.')

    try:
        db.session.commit()

        # Envoyer une notification par e-mail au client
        customer = visit_request.customer
        property_obj = visit_request.property
        if customer and property_obj:
            send_owner_rejection_notification(
                customer.email,
                property_obj.title,
                message
            )

        return jsonify({'message': 'Demande de visite rejetée avec succès. Notification envoyée au client.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors du rejet de la demande de visite par le propriétaire: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

# --- AJOUT DE DEUX NOUVELLES ROUTES POUR LES PROPRIÉTAIRES ---

@owners_bp.route('/property_types_with_attributes', methods=['GET'])
@jwt_required()
def get_property_types_for_owner():
    # On vérifie que c'est bien un propriétaire
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': "Accès non autorisé."}), 403

    # Copie de la logique de la route admin
    pts = PropertyType.query.filter_by(is_active=True).all()
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

@owners_bp.route('/upload_image', methods=['POST'])
@jwt_required()
def upload_image_for_owner():
    current_user_id = get_jwt_identity()
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': "Accès non autorisé."}), 403

    # Copie de la logique de la route admin
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

