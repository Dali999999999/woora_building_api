import random
import string
from datetime import datetime, timedelta

from flask import current_app
from flask_mail import Message
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token

from app import db, mail
from app.models import User, AppSetting



def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(email, code):
    msg = Message('Code de Vérification Woora Building',
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
    user = User.query.filter_by(email=email).first()
    
    # 1. GESTION DU SOFT DELETE : Libérer l'email si l'utilisateur est supprimé
    if user and user.deleted_at is not None:
        import time
        timestamp = int(time.time())
        # On anonymise l'ancien compte pour permettre la réinscription
        # On garde une trace pour l'admin
        anonymized_email = f"{user.email}.del.{timestamp}"
        
        # S'assurer que ça ne dépasse pas 191 chars
        if len(anonymized_email) > 190:
            anonymized_email = f"del.{timestamp}.{user.id}@woora.deleted"

        current_app.logger.info(f"Anonymisation du compte supprimé {user.id} ({user.email}) -> {anonymized_email}")
        user.email = anonymized_email
        
        # On libère aussi le numéro de téléphone au cas où (pour éviter confusion)
        if user.phone_number:
             user.phone_number = f"{user.phone_number}_del_{timestamp}"

        db.session.commit()
        
        # On considère maintenant que l'utilisateur n'existe plus pour la suite de la logique
        user = None

    if user and user.is_verified:
        raise ValueError('Un utilisateur avec cet e-mail existe déjà.')

    # Logique spécifique pour la création d'un administrateur
    if role == 'admin':
        existing_admin = User.query.filter_by(role='admin').first()
        if existing_admin:
            raise ValueError('Un compte administrateur existe déjà.')

    hashed_password = generate_password_hash(password)
    verification_code = generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Si l'utilisateur existe mais n'est pas vérifié, on met à jour ses infos
    if user and not user.is_verified:
        user.password_hash = hashed_password
        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone_number
        user.role = role
        # On ne touche pas à visit_passes ici, on le fait à la vérification ou création
    else:
        # Création du nouvel utilisateur (non vérifié par défaut)
        user = User(
            email=email,
            password_hash=hashed_password,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            role=role,
            is_verified=False
        )
        db.session.add(user)

    # On stocke le code en BASE DE DONNÉES (Support multi-workers)
    user.verification_code = verification_code
    user.verification_code_expires = expires_at

    db.session.commit()

    # Envoyer l'e-mail de vérification

    # Envoyer l'e-mail de vérification
    if not send_verification_email(email, verification_code):
        pass

    return True

def resend_verification_email_service(email):
    """
    Renvoyer un code de vérification à un utilisateur en attente de validation.
    """
    user = User.query.filter_by(email=email).first()
    
    # Cas 1: Utilisateur déjà vérifié
    if user and user.is_verified:
        raise ValueError("Ce compte est déjà vérifié. Veuillez vous connecter.")
    
    # Cas 2: Utilisateur non trouvé du tout
    if not user:
        raise ValueError("Aucune inscription en attente pour cet e-mail.")

    # Cas 3: Utilisateur existe et !is_verified (Inscription en cours)
    # On génère un nouveau code
    new_code = generate_verification_code()
    new_expires_at = datetime.utcnow() + timedelta(minutes=10)

    # On met à jour la DB
    user.verification_code = new_code
    user.verification_code_expires = new_expires_at
    db.session.commit()

    # Renvoyer l'email
    if not send_verification_email(email, new_code):
        raise ValueError("Erreur lors de l'envoi de l'e-mail.")
    
    return True

def verify_email_and_register(email, code):
    # Récupération de l'utilisateur en base
    user = User.query.filter_by(email=email).first()
    
    if not user:
        raise ValueError('Utilisateur introuvable. Veuillez vous inscrire.')

    if user.is_verified:
        return user # Déjà fait

    # Vérification du code en DB
    if not user.verification_code or not user.verification_code_expires:
         raise ValueError('Aucun code de vérification en attente. Veuillez en demander un nouveau.')

    if user.verification_code != code:
        raise ValueError('Code de vérification invalide.')

    if datetime.utcnow() > user.verification_code_expires:
        raise ValueError('Code de vérification expiré.')

    # Récupération de l'utilisateur en base
    user = User.query.filter_by(email=email).first()
    if not user:
        # Cas théoriquement impossible si register_user_initiate a bien commit
        raise ValueError("Erreur critique: Utilisateur introuvable.")

    if user.is_verified:
        return user # Déjà fait

    # Validation finale
    user.is_verified = True
    
    # --- Logique d'attribution des pass de visite gratuits ---
    if user.role == 'customer':
        free_passes_setting = AppSetting.query.filter_by(setting_key='initial_free_visit_passes').first()
        if free_passes_setting:
            user.visit_passes = int(free_passes_setting.setting_value)
    # --- Fin de la logique ---

    db.session.commit()

    # Nettoyage
    user.verification_code = None
    user.verification_code_expires = None
    db.session.commit()

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
