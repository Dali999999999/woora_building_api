

from flask import Blueprint, jsonify, request, current_app
from app.models import User, Property, PropertyType, PropertyAttribute, AttributeOption, PropertyAttributeScope, db
from app.utils.mega_utils import get_mega_instance
from werkzeug.utils import secure_filename
import os
import uuid

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Dossier temporaire pour les uploads
UPLOAD_FOLDER = '/tmp' # Ou un autre chemin approprié
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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

@admin_bp.route('/property_types', methods=['POST'])
def create_property_type():
    data = request.get_json()
    name = data.get('name')
    description = data.get('description')

    if not name:
        return jsonify({'message': 'Le nom du type de propriété est requis.'}), 400

    if PropertyType.query.filter_by(name=name).first():
        return jsonify({'message': 'Un type de propriété avec ce nom existe déjà.'}), 409

    new_property_type = PropertyType(
        name=name,
        description=description
    )
    db.session.add(new_property_type)
    db.session.commit()
    return jsonify({'message': 'Type de propriété créé avec succès.', 'property_type': new_property_type.to_dict()}), 201

@admin_bp.route('/property_types/<int:type_id>', methods=['PUT'])
def update_property_type(type_id):
    property_type = PropertyType.query.get_or_404(type_id)
    data = request.get_json()

    name = data.get('name')
    description = data.get('description')
    is_active = data.get('is_active')

    if name:
        # Check if name already exists for another property type
        existing_type = PropertyType.query.filter(PropertyType.name == name, PropertyType.id != type_id).first()
        if existing_type:
            return jsonify({'message': 'Un autre type de propriété avec ce nom existe déjà.'}), 409
        property_type.name = name
    if description is not None:
        property_type.description = description
    if is_active is not None:
        property_type.is_active = is_active

    db.session.commit()
    return jsonify({'message': 'Type de propriété mis à jour avec succès.', 'property_type': property_type.to_dict()})

@admin_bp.route('/property_types/<int:type_id>', methods=['DELETE'])
def delete_property_type(type_id):
    property_type = PropertyType.query.get_or_404(type_id)
    db.session.delete(property_type)
    db.session.commit()
    return jsonify({'message': 'Type de propriété supprimé avec succès.'}), 204

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

    new_attribute = PropertyAttribute(
        name=name,
        data_type=data_type,
        is_filterable=is_filterable,
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

@admin_bp.route('/property_type_scopes/<int:property_type_id>', methods=['GET'])
def get_property_type_scopes(property_type_id):
    scopes = PropertyAttributeScope.query.filter_by(property_type_id=property_type_id).all()
    return jsonify([s.attribute_id for s in scopes])

@admin_bp.route('/property_type_scopes/<int:property_type_id>', methods=['POST'])
def update_property_type_scopes(property_type_id):
    data = request.get_json()
    attribute_ids = data.get('attribute_ids', [])

    # Supprimer les scopes existants pour ce property_type_id
    PropertyAttributeScope.query.filter_by(property_type_id=property_type_id).delete()

    # Ajouter les nouveaux scopes
    for attr_id in attribute_ids:
        new_scope = PropertyAttributeScope(
            property_type_id=property_type_id,
            attribute_id=attr_id
        )
        db.session.add(new_scope)
    db.session.commit()

    return jsonify({'message': 'Scopes d\'attributs mis à jour avec succès.'}), 200

@admin_bp.route('/property_types_with_attributes', methods=['GET'])
def get_property_types_with_attributes():
    property_types = PropertyType.query.all()
    result = []
    for pt in property_types:
        pt_dict = pt.to_dict()
        # Récupérer les scopes pour ce type de propriété
        scopes = PropertyAttributeScope.query.filter_by(property_type_id=pt.id).all()
        attribute_ids = [s.attribute_id for s in scopes]
        
        # Récupérer les attributs correspondants
        attributes = PropertyAttribute.query.filter(PropertyAttribute.id.in_(attribute_ids)).all()
        
        attributes_list = []
        for attr in attributes:
            attr_dict = attr.to_dict()
            if attr.data_type == 'enum':
                options = AttributeOption.query.filter_by(attribute_id=attr.id).all()
                attr_dict['options'] = [opt.to_dict() for opt in options]
            attributes_list.append(attr_dict)
        pt_dict['attributes'] = attributes_list
        result.append(pt_dict)
    return jsonify(result)

@admin_bp.route('/upload_image', methods=['POST'])
def upload_image():
    current_app.logger.info("Requête reçue sur /upload_image")

    if 'file' not in request.files:
        current_app.logger.warning("Upload: Aucun fichier trouvé.")
        return jsonify({"error": "Aucun fichier fourni"}), 400
    file = request.files['file']
    if file.filename == '':
        current_app.logger.warning("Upload: Nom de fichier vide.")
        return jsonify({"error": "Nom de fichier vide"}), 400

    if file:
        original_filename = secure_filename(file.filename)
        temp_filename_upload = f"{uuid.uuid4()}_UPLOAD_{original_filename}"
        temp_filepath_upload = os.path.join(UPLOAD_FOLDER, temp_filename_upload)
        current_app.logger.info(f"Upload: Sauvegarde temporaire sous: '{temp_filepath_upload}'")

        try:
            file.save(temp_filepath_upload)
            file_size = os.path.getsize(temp_filepath_upload)
            current_app.logger.info(f"Upload: Fichier sauvegardé: '{temp_filepath_upload}' ({file_size} bytes)")

            m = get_mega_instance()
            if m is None:
                current_app.logger.error("Upload: Échec connexion Mega.")
                return jsonify({"error": "Échec connexion service stockage"}), 503

            current_app.logger.info(f"Upload: Téléversement '{temp_filename_upload}' sur Mega...")
            uploaded_file_node_response = m.upload(temp_filepath_upload)
            current_app.logger.info(f"Upload: Téléversement terminé.")

            public_link = None
            try:
                current_app.logger.info("Upload: Génération lien via m.get_upload_link()...")
                public_link = m.get_upload_link(uploaded_file_node_response)
                current_app.logger.info(f"Upload: Lien public généré: {public_link}")
            except Exception as e_get_link:
                current_app.logger.error(f"Upload: Erreur get_upload_link: {e_get_link}", exc_info=True)
                current_app.logger.warning("Upload: Fallback avec m.export()...")
                try:
                    file_handle = uploaded_file_node_response.get('f', [{}])[0].get('h')
                    if file_handle:
                        public_link = m.export(file_handle)
                        current_app.logger.info(f"Upload: Lien public généré (fallback): {public_link}")
                    else: raise ValueError("Handle non trouvé pour fallback.")
                except Exception as inner_e:
                    current_app.logger.error(f"Upload: Fallback export échoué: {inner_e}", exc_info=True)
                    return jsonify({"error": "Erreur interne génération lien post-upload"}), 500

            if public_link:
                return jsonify({"url": public_link}), 200
            else:
                current_app.logger.error("Upload: Lien public final est None.")
                return jsonify({"error": "Erreur interne finalisation lien public."}), 500

        except Exception as e:
            current_app.logger.error(f"Upload: Erreur majeure '{original_filename}': {e}", exc_info=True)
            return jsonify({"error": f"Erreur interne serveur ({type(e).__name__})."}), 500
        finally:
            if os.path.exists(temp_filepath_upload):
                try:
                    os.remove(temp_filepath_upload)
                    current_app.logger.info(f"Upload: Fichier temporaire supprimé: '{temp_filepath_upload}'")
                except OSError as e_remove:
                    current_app.logger.error(f"Upload: Erreur suppression temp: {e_remove}")
    else:
        return jsonify({"error": "Fichier invalide ou non traité"}), 400

