from flask import Blueprint, request, jsonify
from app.auth import services as auth_services
from flask import current_app # Import added for logging
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User
import random
import string
from datetime import datetime, timedelta
from flask_jwt_extended import create_access_token
from app import db
from werkzeug.security import generate_password_hash

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['POST'])
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

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not all([email, password]):
        return jsonify({'message': 'L\'e-mail et le mot de passe sont requis.'}), 400

    try:
        user, access_token = auth_services.authenticate_user(email, password)
        return jsonify({
            'message': 'Connexion réussie.',
            'access_token': access_token,
            'user_role': user.role,
            'user_id': user.id
        }), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 401 # Unauthorized
    except Exception as e:
        current_app.logger.error(f'Erreur lors de la connexion: {e}', exc_info=True)
        return jsonify({'message': 'Erreur interne du serveur.', 'error': str(e)}), 500

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
def forgot_password():
    data = request.get_json()
    email = data.get('email')
    
    user = User.query.filter_by(email=email).first()
    if not user:
        # On ne révèle pas si l'email existe pour des raisons de sécurité
        return jsonify({"message": "Si un compte est associé à cet email, un code a été envoyé."}), 200

    # On utilise la logique du service d'authentification
    verification_code = auth_services.generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # On stocke en mémoire
    auth_services._pending_resets[email] = {
        'code': verification_code,
        'expires_at': expires_at
    }

    # On envoie l'email via le service
    auth_services.send_reset_password_email(email, verification_code)
    current_app.logger.info(f"Code de réinitialisation pour {email}: {verification_code}")
    
    return jsonify({"message": "Un code de réinitialisation a été envoyé à votre email."}), 200


@auth_bp.route('/verify-reset-code', methods=['POST'])
def verify_reset_code():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    # On vérifie dans le dictionnaire en mémoire
    pending_reset = auth_services._pending_resets.get(email)
    
    if not pending_reset or pending_reset['code'] != code or datetime.utcnow() > pending_reset['expires_at']:
        return jsonify({"message": "Code invalide ou expiré."}), 400
        
    # Le code est valide, on crée un token temporaire
    reset_token = create_access_token(identity=email, expires_delta=timedelta(minutes=15))
    
    # On supprime l'entrée du dictionnaire
    del auth_services._pending_resets[email]
    
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
