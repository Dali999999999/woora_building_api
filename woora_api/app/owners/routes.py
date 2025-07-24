
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

    # Valider les données requises
    required_fields = ['property_type_id', 'title', 'description', 'status', 'price', 'address', 'city', 'postal_code', 'image_urls']
    for field in required_fields:
        if field not in data:
            return jsonify({'message': f'Le champ {field} est requis.'}), 400

    # Vérifier l'existence de l'owner et son rôle
    owner = User.query.get(current_user_id)
    if not owner or owner.role != 'owner':
        return jsonify({'message': 'Accès non autorisé. Seuls les propriétaires peuvent créer des biens.'}), 403

    property_type = PropertyType.query.get(data['property_type_id'])
    if not property_type:
        return jsonify({'message': 'Type de propriété invalide ou non trouvé.'}), 400

    # Créer le bien immobilier
    new_property = Property(
        owner_id=current_user_id, # Utiliser l'ID de l'utilisateur authentifié
        property_type_id=data['property_type_id'],
        title=data['title'],
        description=data['description'],
        status=data['status'],
        price=data['price'],
        address=data['address'],
        city=data['city'],
        postal_code=data['postal_code'],
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        attributes=data.get('attributes', {}), # Attributs dynamiques
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
