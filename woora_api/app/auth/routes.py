from flask import Blueprint, request, jsonify, make_response
from app.auth import services as auth_services
from flask import current_app # Import added for logging
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, create_refresh_token, set_access_cookies, set_refresh_cookies, unset_jwt_cookies
from app import limiter  # Import limiter for rate limiting
from app.models import User
import random
import string
from datetime import datetime, timedelta
from app import db
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
# from app.utils.mega_utils import get_mega_instance # REMOVED
import os
import uuid

UPLOAD_FOLDER = '/tmp'

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
@limiter.limit("3 per minute")  # Security: Prevent spam registration
def register():
    data = request.get_json()
    current_app.logger.debug(f'Données reçues pour l\'inscription: {data}')
    email = data.get('email')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    phone_number = data.get('phone_number')
    role = data.get('role')

    if not all([email, password, first_name, last_name, phone_number, role]):
        return jsonify({'message': 'Tous les champs sont requis.'}), 400

    try:
        auth_services.register_user_initiate(email, password, first_name, last_name, phone_number, role)
        return jsonify({'message': 'Inscription initiée. Un code de vérification a été envoyé à votre adresse e-mail.'}), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 409 # Conflict
    except Exception as e:
        current_app.logger.error(f'Erreur lors de l\'initiation de l\'inscription: {e}', exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

@auth_bp.route('/verify_email', methods=['POST'])
def verify_email():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')

    if not all([email, code]):
        return jsonify({'message': 'L\'e-mail et le code de vérification sont requis.'}), 400

    try:
        user = auth_services.verify_email_and_register(email, code)
        return jsonify({'message': 'Adresse e-mail vérifiée avec succès. Compte créé.', 'user_id': user.id}), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f'Erreur lors de la vérification de l\'e-mail: {e}', exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

@auth_bp.route('/resend-verification-code', methods=['POST'])
def resend_verification_code():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'message': 'L\'e-mail est requis.'}), 400

    try:
        auth_services.resend_verification_email_service(email)
        return jsonify({'message': 'Un nouveau code de vérification a été envoyé.'}), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        current_app.logger.error(f'Erreur lors du renvoi du code: {e}', exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # Security: Prevent brute-force attacks
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({'message': 'L\'e-mail et le mot de passe sont requis.'}), 400

    try:
        user, access_token = auth_services.authenticate_user(email, password)
        
        if user.deleted_at:
             reason = user.deletion_reason or "Compte supprimé par l'administrateur."
             return jsonify({'message': f'Ce compte a été supprimé. Motif : {reason}'}), 403

        # Check suspension
        if user.is_suspended:
            reason = user.suspension_reason or "Compte suspendu pour non-respect des règles."
            return jsonify({'message': f'Compte suspendu. Raison : {reason}'}), 403

        # Create refresh token
        refresh_token = create_refresh_token(identity=str(user.id))

        response = jsonify({
            'message': 'Connexion réussie.',
            'access_token': access_token, # Keep for mobile compatibility
            'refresh_token': refresh_token, # Keep for mobile compatibility
            'user_role': user.role,
            'user_id': user.id
        })
        
        # Set cookies for web
        set_access_cookies(response, access_token)
        set_refresh_cookies(response, refresh_token)

        return response, 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 401 # Unauthorized
    except Exception as e:
        current_app.logger.error(f'Erreur lors de la connexion: {e}', exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """
    Renouvelle le token d'accès en utilisant le refresh token (envoyé via cookie ou header).
    """
    try:
        current_user_id = get_jwt_identity()
        new_access_token = create_access_token(identity=current_user_id)
        
        response = jsonify({'access_token': new_access_token})
        set_access_cookies(response, new_access_token)
        return response, 200
    except Exception as e:
        current_app.logger.error(f"Erreur lors du refresh: {e}")
        return jsonify({'message': 'Impossible de rafraîchir le token.'}), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    response = jsonify({'message': 'Déconnexion réussie.'})
    unset_jwt_cookies(response)
    # Nuclear option: Force delete potential legacy cookies with specific paths
    response.set_cookie('refresh_token_cookie', '', expires=0, max_age=0, path='/auth/refresh')
    response.set_cookie('access_token_cookie', '', expires=0, max_age=0, path='/auth/refresh')
    return response, 200

# --- AJOUTEZ CETTE NOUVELLE FONCTION ---
@auth_bp.route('/profile', methods=['GET'])
@jwt_required()
def get_user_profile():
    """
    Récupère les informations du profil de l'utilisateur actuellement connecté.
    """
    # Récupère l'ID de l'utilisateur depuis le token JWT
    current_user_id = get_jwt_identity()
    
    # Cherche l'utilisateur dans la base de données
    user = User.query.get(current_user_id)
    
    if not user:
        return jsonify({"message": "Utilisateur non trouvé."}), 404
        
    # Utilise la méthode to_dict() que nous avons déjà sur le modèle User
    return jsonify(user.to_dict()), 200

@auth_bp.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")  # Security: Prevent password reset spam
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    
    user = User.query.filter_by(email=email).first()
    if not user:
        # On ne révèle pas si l'email existe pour des raisons de sécurité
        return jsonify({"message": "Si un compte est associé à cet email, un code a été envoyé."}), 200

    # On utilise la logique du service d'authentification
    verification_code = auth_services.generate_verification_code()
    expiration_time = datetime.utcnow() + timedelta(seconds=600) # 10 minutes

    # On stocke en BASE DE DONNÉES
    user.reset_password_token = verification_code
    user.reset_password_expires = expiration_time
    db.session.commit()

    # On envoie l'email via le service
    auth_services.send_reset_password_email(email, verification_code)
    current_app.logger.info(f"Code de réinitialisation pour {email}: {verification_code}")
    
    return jsonify({"message": "Un code de réinitialisation a été envoyé à votre email."}), 200


@auth_bp.route('/verify-reset-code', methods=['POST'])
def verify_reset_code():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.reset_password_token:
         return jsonify({"message": "Aucune demande de réinitialisation en cours."}), 400

    if user.reset_password_token != code:
        return jsonify({"message": "Code invalide."}), 400
        
    if datetime.utcnow() > user.reset_password_expires:
        return jsonify({"message": "Code expiré."}), 400
        
    # Le code est valide, on crée un token temporaire
    reset_token = create_access_token(identity=email, expires_delta=timedelta(minutes=15))
    
    # On supprime le token pour empêcher la réutilisation
    user.reset_password_token = None
    user.reset_password_expires = None
    db.session.commit()
    
    return jsonify({"reset_token": reset_token}), 200


@auth_bp.route('/reset-password', methods=['POST'])
@jwt_required()
def reset_password():
    user_email = get_jwt_identity()
    user = User.query.filter_by(email=user_email).first()
    
    if not user:
        return jsonify({"message": "Utilisateur invalide."}), 400
        
    data = request.get_json()
    new_password = data.get('new_password')
    
    if not new_password or len(new_password) < 6:
        return jsonify({"message": "Le mot de passe doit contenir au moins 6 caractères."}), 400
    
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    # On connecte l'utilisateur
    access_token = create_access_token(identity=str(user.id))
    
    return jsonify({
        "message": "Mot de passe réinitialisé avec succès.",
        "access_token": access_token,
        "user_role": user.role
    }), 200

@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_user_profile():
    """
    Permet à l'utilisateur connecté de mettre à jour ses propres informations de profil.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)
    
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Données manquantes.'}), 400

    # Mettre à jour les champs s'ils sont fournis dans la requête
    if 'first_name' in data: user.first_name = data['first_name']
    if 'last_name' in data: user.last_name = data['last_name']
    if 'phone_number' in data: user.phone_number = data['phone_number']
    if 'profession' in data: user.profession = data['profession']
    if 'address' in data: user.address = data['address']
    if 'city' in data: user.city = data['city']
    if 'country' in data: user.country = data['country']
    if 'bio' in data: user.bio = data['bio']
    if 'profile_picture_url' in data: user.profile_picture_url = data['profile_picture_url']
    
    try:
        db.session.commit()
        return jsonify(user.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur lors de la mise à jour du profil: {e}")
        return jsonify({'message': 'Erreur interne du serveur.'}), 500

@auth_bp.route('/profile/upload-picture', methods=['POST'])
@jwt_required()
def upload_profile_picture():
    """
    Permet à l'utilisateur connecté de téléverser une nouvelle photo de profil.
    """
    current_user_id = get_jwt_identity()
    user = User.query.get_or_404(current_user_id)

    # --- CLOUDINARY UPLOAD ---
    # Pas besoin de sauvegarder temporairement le fichier
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Nom de fichier vide'}), 400

    from app.utils.cloudinary_utils import upload_image # Import tardif
    
    try:
        secure_url = upload_image(file, folder="woora_profiles") # Dossier spécifique profils
        
        if not secure_url:
            return jsonify({'error': 'Échec de l\'upload vers Cloudinary'}), 500

        # Mettre à jour l'URL de la photo de profil de l'utilisateur
        user.profile_picture_url = secure_url
        db.session.commit()
        
        return jsonify({'message': 'Photo de profil mise à jour.', 'profile_picture_url': secure_url}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur d'upload de la photo de profil: {e}")
        return jsonify({'error': 'Erreur interne du serveur.'}), 500

from app.models import VisitRequest, PropertyRequestMatch, PropertyRequest, Property, Referral, Commission

@auth_bp.route('/notifications/summary', methods=['GET'])
@jwt_required()
def get_notifications_summary():
    """
    Récupère le résumé des notifications (badges) pour l'utilisateur connecté.
    Retourne:
    - pending_visits_count: Nombre de visites en attente (pour Agent/Owner).
    - unread_alerts_count: Nombre de nouveaux biens correspondants (pour Seeker/Agent).
    """
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user:
        return jsonify({'message': 'Utilisateur non trouvé.'}), 404
        
    response_data = {
        'pending_visits_count': 0,
        'unread_alerts_count': 0,
        'seeker_unread_visits_count': 0,
        'agent_unread_commissions_count': 0
    }
    
    try:
        # 1. BADGE VISITES (Pour Owners et Agents)
        # Logique : Compter les demandes avec statut 'pending'
        
        if user.role == 'owner':
            # Pour un Owner : toutes les demandes sur SES propriétés
            pending_count = VisitRequest.query.join(Property).filter(
                Property.owner_id == user.id,
                VisitRequest.status == 'pending'
            ).count()
            response_data['pending_visits_count'] = pending_count
            
        elif user.role == 'agent':
            # Pour un Agent : 
            # A. Demandes sur ses propres propriétés (si agent est aussi "owner" technique de certains biens)
            # B. Demandes via son code de parrainage (Referrals)
            
            # Approche A+B combinée via requête OR ou deux requêtes
            # 1. Directement liées à l'agent via Referral
            referral_pending = VisitRequest.query.join(Referral).filter(
                Referral.agent_id == user.id,
                VisitRequest.status == 'pending'
            ).count()
            
            # 2. Liées à des propriétés créées par l'agent (agent_id sur Property)
            direct_property_pending = VisitRequest.query.join(Property).filter(
                Property.agent_id == user.id,
                VisitRequest.status == 'pending'
            ).count()
            
            # Note: Si un agent parraine sa propre propriété, éviter de compter double ?
            # Simplification : On additionne pour l'instant, ou on fait une union si nécessaire.
            # Pour l'instant, Woora distingue bien les deux flux.
            response_data['pending_visits_count'] = referral_pending + direct_property_pending

        # 2. BADGE ALERTES (Pour Seekers et Agents)
        # Logique : Compter les matches non lus (is_read=False)
        
        if user.role in ['customer', 'agent']:
            # Récupérer les ID des PropertyRequest de l'utilisateur
            user_request_ids = [req.id for req in user.property_requests]
            
            if user_request_ids:
                unread_count = PropertyRequestMatch.query.filter(
                    PropertyRequestMatch.property_request_id.in_(user_request_ids),
                    PropertyRequestMatch.is_read == False
                ).count()
                response_data['unread_alerts_count'] = unread_count
                
        # 3. NOUVEAU BADGE VISITES CLIENT (Pour Seekers)
        if user.role == 'customer':
            seeker_visits_unread = VisitRequest.query.filter_by(
                customer_id=user.id,
                customer_has_unread_update=True
            ).count()
            response_data['seeker_unread_visits_count'] = seeker_visits_unread
            
        # 4. NOUVEAU BADGE GAINS (Pour Agents)
        if user.role == 'agent':
            agent_commissions_unread = Commission.query.filter_by(
                agent_id=user.id,
                is_read=False
            ).count()
            response_data['agent_unread_commissions_count'] = agent_commissions_unread
        
        return jsonify(response_data), 200
        
    except Exception as e:
        current_app.logger.error(f"Erreur lors du calcul des notifications: {e}", exc_info=True)
        return jsonify({'message': 'Erreur interne lors du calcul des notifications.'}), 500

@auth_bp.route('/notifications/read_visits', methods=['POST'])
@jwt_required()
def mark_visits_as_read():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user or user.role != 'customer':
        return jsonify({'message': 'Non autorisé.'}), 403
        
    try:
        VisitRequest.query.filter_by(
            customer_id=user.id, 
            customer_has_unread_update=True
        ).update({'customer_has_unread_update': False})
        db.session.commit()
        return jsonify({'message': 'Visites marquées comme lues.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur mark_visits_as_read: {e}")
        return jsonify({'message': 'Erreur interne'}), 500

@auth_bp.route('/notifications/read_commissions', methods=['POST'])
@jwt_required()
def mark_commissions_as_read():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    if not user or user.role != 'agent':
        return jsonify({'message': 'Non autorisé.'}), 403
        
    try:
        Commission.query.filter_by(
            agent_id=user.id, 
            is_read=False
        ).update({'is_read': True})
        db.session.commit()
        return jsonify({'message': 'Commissions marquées comme lues.'}), 200
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Erreur mark_commissions_as_read: {e}")
        return jsonify({'message': 'Erreur interne'}), 500
