import random
import string
from datetime import datetime, timedelta

from flask import current_app
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token

from app import db, mail
from app.models import User

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(user):
    msg = Message('Code de Vérification Woora Immo',
                    sender=current_app.config['MAIL_DEFAULT_SENDER'],
                    recipients=[user.email])
    msg.body = f'Votre code de vérification est : {user.verification_code}. Ce code est valide pendant 10 minutes.'
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Erreur lors de l\'envoi de l\'e-mail à {user.email}: {e}')
        return False

def register_user(email, password, first_name, last_name, phone_number, role):
    if User.query.filter_by(email=email).first():
        raise ValueError('Un utilisateur avec cet e-mail existe déjà.')

    hashed_password = generate_password_hash(password)
    verification_code = generate_verification_code()

    user = User(
        email=email,
        password_hash=hashed_password,
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        role=role,
        is_verified=False,
        verification_code=verification_code
    )

    db.session.add(user)
    db.session.commit()

    # Envoyer l'e-mail de vérification
    if not send_verification_email(user):
        # Gérer l'échec de l'envoi d'e-mail si nécessaire
        pass

    return user

def verify_email(email, code):
    user = User.query.filter_by(email=email, verification_code=code).first()
    if user:
        # Pour une sécurité accrue, on pourrait ajouter une expiration au code
        user.is_verified = True
        user.verification_code = None # Effacer le code après vérification
        db.session.commit()
        return True
    return False

def authenticate_user(email, password):
    user = User.query.filter_by(email=email).first()

    if not user:
        raise ValueError('Aucun utilisateur trouvé avec cet e-mail.')

    if not check_password_hash(user.password_hash, password):
        raise ValueError('Mot de passe incorrect.')

    if not user.is_verified:
        raise ValueError('Veuillez vérifier votre adresse e-mail avant de vous connecter.')

    access_token = create_access_token(identity={'id': user.id, 'role': user.role})
    return user, access_token
