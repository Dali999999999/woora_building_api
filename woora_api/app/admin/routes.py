

from flask import Blueprint, jsonify, request, current_app
from app.models import User, Property, PropertyType, PropertyAttribute, AttributeOption, PropertyAttributeScope, db, AppSetting, ServiceFee, VisitRequest
from app.schemas import VisitSettingsSchema
from marshmallow import ValidationError
from app.utils.mega_utils import get_mega_instance
from werkzeug.utils import secure_filename
import os
import uuid
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.email_utils import send_admin_rejection_notification, send_admin_confirmation_to_owner

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

@admin_bp.route('/settings/visits', methods=['GET'])
def get_visit_settings():
    """Récupère la configuration actuelle des visites."""
    try:
        free_passes_setting = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
        pass_price_setting = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()

        settings = {
            'initial_free_visit_passes': int(free_passes_setting.setting_value) if free_passes_setting else 0,
            'visit_pass_price': float(pass_price_setting.amount) if pass_price_setting else 0.0
        }
        
        return jsonify(VisitSettingsSchema().dump(settings)), 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la récupération des paramètres de visite: {e}", exc_info=True)
        return jsonify({"message": "Erreur interne du serveur."}), 500


@admin_bp.route('/settings/visits', methods=['PUT'])
def update_visit_settings():
    """Met à jour la configuration des visites."""
    json_data = request.get_json()
    if not json_data:
        return jsonify({"message": "Données JSON non fournies."}), 400

    try:
        # Validation des données
        data = VisitSettingsSchema().load(json_data)
    except ValidationError as err:
        return jsonify(err.messages), 422

    try:
        # Mise à jour du nombre de pass gratuits
        free_passes_setting = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
        if free_passes_setting:
            free_passes_setting.setting_value = str(data['initial_free_visit_passes'])
        else:
            free_passes_setting = AppSetting(
                setting_key='initial_free_visit_passes',
                setting_value=str(data['initial_free_visit_passes']),
                data_type='integer',
                description='Nombre de pass de visite gratuits offerts à l\'inscription.'
            )
            db.session.add(free_passes_setting)

        # Mise à jour du prix du pass
        pass_price_setting = ServiceFee.query.filter_by(service_key='visit_pass_purchase').first()
        if pass_price_setting:
            pass_price_setting.amount = data['visit_pass_price']
        else:
            pass_price_setting = ServiceFee(
                service_key='visit_pass_purchase',
                name='Achat de Pass de Visite',
                amount=data['visit_pass_price'],
                applicable_to_role='customer',
                description='Permet à un client d\'acheter un pass pour effectuer une demande de visite.'
            )
            db.session.add(pass_price_setting)
        
        db.session.commit()
        
        return jsonify({"message": "Paramètres de visite mis à jour avec succès."}), 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la mise à jour des paramètres de visite: {e}", exc_info=True)
        return jsonify({"message": "Erreur interne du serveur."}), 500

@admin_bp.route('/visit_requests', methods=['GET'])
def get_visit_requests():
    current_user_id = get_jwt_identity()
    admin_user = User.query.get(current_user_id)

    if not admin_user or admin_user.role != 'admin':
        return jsonify({'message': 'Accès refusé. Seuls les administrateurs peuvent voir les demandes de visite.'}), 403

    status_filter = request.args.get('status')
    query = VisitRequest.query

    if status_filter:
        query = query.filter_by(status=status_filter)
    
    visit_requests = query.all()
    result = []
    for req in visit_requests:
        customer = User.query.get(req.customer_id)
        property_obj = Property.query.get(req.property_id)
        req_dict = {
            'id': req.id,
            'customer_name': f'{customer.first_name} {customer.last_name}' if customer else 'N/A',
            'customer_email': customer.email if customer else 'N/A',
            'property_title': property_obj.title if property_obj else 'N/A',
            'requested_datetime': req.requested_datetime.isoformat(),
            'status': req.status,
            'message': req.message,
            'created_at': req.created_at.isoformat()
        }
        result.append(req_dict)
    return jsonify(result), 200

@admin_bp.route('/visit_requests/<int:request_id>/confirm', methods=['PUT'])
def confirm_visit_request(request_id):
    current_user_id = get_jwt_identity()
    admin_user = User.query.get(current_user_id)

    if not admin_user or admin_user.role != 'admin':
        return jsonify({'message': 'Accès refusé. Seuls les administrateurs peuvent confirmer les demandes de visite.'}), 403

    visit_request = VisitRequest.query.get(request_id)
    if not visit_request:
        return jsonify({'message': 'Demande de visite non trouvée.'}), 404

    if visit_request.status != 'pending':
        return jsonify({'message': 'La demande de visite n\'est pas en attente de confirmation.'}), 400

    visit_request.status = 'confirmed'
    
    try:
        db.session.commit()

        # Envoyer un e-mail au propriétaire
        owner = User.query.get(Property.query.get(visit_request.property_id).owner_id)
        customer = User.query.get(visit_request.customer_id)
        property_obj = Property.query.get(visit_request.property_id)

        if owner and customer and property_obj:
            send_admin_confirmation_to_owner(
                owner.email,
                f'{customer.first_name} {customer.last_name}',
                property_obj.title,
                visit_request.requested_datetime.strftime('%Y-%m-%d %H:%M')
            )

        return jsonify({'message': 'Demande de visite confirmée avec succès. Notification envoyée au propriétaire.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la confirmation de la demande de visite: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

@admin_bp.route('/visit_requests/<int:request_id>/reject', methods=['PUT'])
def reject_visit_request_by_admin(request_id):
    current_user_id = get_jwt_identity()
    admin_user = User.query.get(current_user_id)

    if not admin_user or admin_user.role != 'admin':
        return jsonify({'message': 'Accès refusé. Seuls les administrateurs peuvent rejeter les demandes de visite.'}), 403

    visit_request = VisitRequest.query.get(request_id)
    if not visit_request:
        return jsonify({'message': 'Demande de visite non trouvée.'}), 404

    if visit_request.status != 'pending':
        return jsonify({'message': 'La demande de visite n\'est pas en attente de rejet.'}), 400

    visit_request.status = 'rejected'
    message = request.get_json().get('message', 'Demande rejetée par l\'administrateur.')

    try:
        db.session.commit()

        # Envoyer un e-mail au client
        customer = User.query.get(visit_request.customer_id)
        property_obj = Property.query.get(visit_request.property_id)

        if customer and property_obj:
            send_admin_rejection_notification(
                customer.email,
                property_obj.title,
                message
            )

        return jsonify({'message': 'Demande de visite rejetée avec succès. Notification envoyée au client.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors du rejet de la demande de visite par l\'admin: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

