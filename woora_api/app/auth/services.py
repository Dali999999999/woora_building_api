import random
import string
from datetime import datetime, timedelta

from flask import current_app
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token

from app import db, mail
from app.models import User, AppSetting

# Stockage temporaire pour les inscriptions en attente de vérification
# Clé: email, Valeur: {'data': user_data, 'code': verification_code, 'expires_at': datetime}
_pending_registrations = {}
# Stockage temporaire pour les demandes de réinitialisation
_pending_resets = {}

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(email, code):
    msg = Message('Code de Vérification Woora Immo',
                    sender=current_app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[email])
    msg.body = f'Votre code de vérification est : {code}. Ce code est valide pendant 60 secondes.'
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erreur lors de l\'envoi de l\'e-mail à {email}: {e}')
        return False

def register_user_initiate(email, password, first_name, last_name, phone_number, role):
    if User.query.filter_by(email=email).first():
        raise ValueError('Un utilisateur avec cet e-mail existe déjà.')

    # Logique spécifique pour la création d'un administrateur
    if role == 'admin':
        existing_admin = User.query.filter_by(role='admin').first()
        if existing_admin:
            raise ValueError('Un compte administrateur existe déjà. La création de plusieurs administrateurs via cette route n\'est pas autorisée.')

    hashed_password = generate_password_hash(password)
    verification_code = generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=10) # Code valide 10 minutes

    user_data = {
        'email': email,
        'password_hash': hashed_password,
        'first_name': first_name,
        'last_name': last_name,
        'phone_number': phone_number,
        'role': role
    }

    _pending_registrations[email] = {
        'data': user_data,
        'code': verification_code,
        'expires_at': expires_at
    }

    # Envoyer l\'e-mail de vérification
    if not send_verification_email(email, verification_code):
        # Gérer l\'échec de l\'envoi d\'e-mail si nécessaire
        pass

    return True # Indique que l\'initiation de l\'inscription a réussi


def resend_verification_email_service(email):
    """
    Renvoyer un code de vérification à un utilisateur en attente de validation.
    """
    if email not in _pending_registrations:
        # On vérifie si l'utilisateur existe déjà (déjà vérifié ?)
        user = User.query.filter_by(email=email).first()
        if user:
            raise ValueError("Ce compte est déjà vérifié. Veuillez vous connecter.")
        raise ValueError("Aucune inscription en attente pour cet e-mail.")

    # Générer un nouveau code
    new_code = generate_verification_code()
    new_expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Mettre à jour l'entrée existante
    _pending_registrations[email]['code'] = new_code
    _pending_registrations[email]['expires_at'] = new_expires_at

    # Renvoyer l'email
    if not send_verification_email(email, new_code):
        raise ValueError("Erreur lors de l'envoi de l'e-mail.")
    
    return True



def verify_email_and_register(email, code):
    if email not in _pending_registrations:
        raise ValueError('Aucune inscription en attente pour cet e-mail.')

    pending_reg = _pending_registrations[email]

    if pending_reg['code'] != code:
        raise ValueError('Code de vérification invalide.')

    if datetime.utcnow() > pending_reg['expires_at']:
        del _pending_registrations[email] # Supprimer l'entrée expirée
        raise ValueError('Code de vérification expiré.')

    # Créer l'utilisateur dans la base de données
    user_data = pending_reg['data']
    
    # --- Logique d'attribution des pass de visite gratuits ---
    if user_data['role'] == 'customer':
        free_passes_setting = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
        if free_passes_setting:
            user_data['visit_passes'] = int(free_passes_setting.setting_value)
        else:
            user_data['visit_passes'] = 0 # Par défaut, si le paramètre n'est pas trouvé
    # --- Fin de la logique ---

    user = User(
        email=user_data['email'],
        password_hash=user_data['password_hash'],
        first_name=user_data['first_name'],
        last_name=user_data['last_name'],
        phone_number=user_data['phone_number'],
        role=user_data['role'],
        visit_passes=user_data.get('visit_passes', 0) # Ajout du champ ici
    )

    db.session.add(user)
    db.session.commit()

    del _pending_registrations[email] # Supprimer l'entrée après inscription réussie

    return user

def authenticate_user(email, password):
    user = User.query.filter_by(email=email).first()

    if not user:
        raise ValueError('Aucun utilisateur trouvé avec cet e-mail.')

    if not check_password_hash(user.password_hash, password):
        raise ValueError('Mot de passe incorrect.')

    # Puisque l\'utilisateur n\'est enregistré qu\'après vérification, pas besoin de is_verified ici

    access_token = create_access_token(identity=str(user.id))
    return user, access_token

def send_reset_password_email(email, code):
    """Envoie un email avec le code de réinitialisation de mot de passe."""
    msg = Message('Votre Code de Réinitialisation de Mot de Passe', # Sujet différent
                    sender=current_app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[email])
    # Corps du message différent
    msg.body = f'Votre code de réinitialisation de mot de passe est : {code}. Ce code est valide pendant 10 minutes.'
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erreur lors de l\'envoi de l\'e-mail à {email}: {e}')
        return False

def send_reset_password_email(email, code):
    """Envoie un email avec le code de réinitialisation de mot de passe."""
    msg = Message('Votre Code de Réinitialisation de Mot de Passe',
                    sender=current_app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[email])
    msg.body = f'Votre code de réinitialisation est : {code}. Ce code est valide pendant 10 minutes.'
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erreur lors de l\'envoi de l\'e-mail à {email}: {e}')
        return False
