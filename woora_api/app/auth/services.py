import random
import string
from datetime import datetime, timedelta

from flask import current_app
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token

from app import db, mail
from app.models import User

# Stockage temporaire pour les inscriptions en attente de vérification
# Clé: email, Valeur: {'data': user_data, 'code': verification_code, 'expires_at': datetime}
_pending_registrations = {}

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(email, code):
    msg = Message('Code de Vérification Woora Immo',
                    sender=current_app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[email])
    msg.body = f'Votre code de vérification est : {code}. Ce code est valide pendant 10 minutes.'
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erreur lors de l\'envoi de l\'e-mail à {email}: {e}')
        return False

def register_user_initiate(email, password, first_name, last_name, phone_number, role):
    if User.query.filter_by(email=email).first():
        raise ValueError('Un utilisateur avec cet e-mail existe déjà.')

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

def verify_email_and_register(email, code):
    if email not in _pending_registrations:
        raise ValueError('Aucune inscription en attente pour cet e-mail.')

    pending_reg = _pending_registrations[email]

    if pending_reg['code'] != code:
        raise ValueError('Code de vérification invalide.')

    if datetime.utcnow() > pending_reg['expires_at']:
        del _pending_registrations[email] # Supprimer l\'entrée expirée
        raise ValueError('Code de vérification expiré.')

    # Créer l\'utilisateur dans la base de données
    user_data = pending_reg['data']
    user = User(
        email=user_data['email'],
        password_hash=user_data['password_hash'],
        first_name=user_data['first_name'],
        last_name=user_data['last_name'],
        phone_number=user_data['phone_number'],
        role=user_data['role']
    )

    db.session.add(user)
    db.session.commit()

    del _pending_registrations[email] # Supprimer l\'entrée après inscription réussie

    return user

def authenticate_user(email, password):
    user = User.query.filter_by(email=email).first()

    if not user:
        raise ValueError('Aucun utilisateur trouvé avec cet e-mail.')

    if not check_password_hash(user.password_hash, password):
        raise ValueError('Mot de passe incorrect.')

    # Puisque l\'utilisateur n\'est enregistré qu\'après vérification, pas besoin de is_verified ici

    access_token = create_access_token(identity={'id': user.id, 'role': user.role})
    return user, access_token
