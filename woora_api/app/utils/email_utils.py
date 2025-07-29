
from flask_mail import Message
from flask import current_app
from app import mail

def send_new_visit_request_notification(admin_email, customer_name, property_title, requested_datetime, message):
    msg = Message(
        f'Nouvelle Demande de Visite pour {property_title}',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[admin_email]
    )
    msg.body = (
        f'Bonjour Administrateur,\n\n'
        f'Une nouvelle demande de visite a été soumise.\n\n'
        f'Détails de la demande:\n'
        f'  Client: {customer_name}\n'
        f'  Bien: {property_title}\n'
        f'  Date et Heure Souhaitées: {requested_datetime}\n'
        f'  Message du client: {message if message else "Aucun"}\n\n'
        f'Veuillez vous connecter au panel d\'administration pour confirmer ou rejeter cette demande.\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de notification de nouvelle demande de visite envoyé à {admin_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l\'envoi de l\'email de notification à l\'admin: {e}", exc_info=True)
        return False

def send_admin_rejection_notification(customer_email, property_title, message):
    msg = Message(
        f'Votre Demande de Visite pour {property_title} a été Rejetée',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email]
    )
    msg.body = (
        f'Bonjour,\n\n'
        f'Nous avons le regret de vous informer que votre demande de visite pour le bien "{property_title}" a été rejetée par l\'administrateur.\n\n'
        f'Raison: {message if message else "Aucune raison spécifique fournie."}\n\n'
        f'N\'hésitez pas à soumettre une nouvelle demande ou à nous contacter pour plus d\'informations.\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de rejet admin envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l\'envoi de l\'email de rejet admin: {e}", exc_info=True)
        return False

def send_admin_confirmation_to_owner(owner_email, customer_name, property_title, requested_datetime):
    msg = Message(
        f'Demande de Visite Confirmée pour {property_title}',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[owner_email]
    )
    msg.body = (
        f'Bonjour Propriétaire,\n\n'
        f'Une demande de visite pour votre bien "{property_title}" a été confirmée par l\'administrateur.\n\n'
        f'Détails de la demande:\n'
        f'  Client: {customer_name}\n'
        f'  Date et Heure Souhaitées: {requested_datetime}\n\n'
        f'Veuillez vous connecter à votre interface pour accepter ou refuser cette demande.\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de confirmation admin envoyé au propriétaire {owner_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l\'envoi de l\'email de confirmation admin au propriétaire: {e}", exc_info=True)
        return False

def send_owner_acceptance_notification(customer_email, property_title, requested_datetime):
    msg = Message(
        f'Votre Demande de Visite pour {property_title} a été Acceptée!',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email]
    )
    msg.body = (
        f'Félicitations!\n\n'
        f'Votre demande de visite pour le bien "{property_title}" a été acceptée par le propriétaire.\n\n'
        f'La visite est prévue pour le {requested_datetime}.\n\n'
        f'Nous vous souhaitons une excellente visite!\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        current_app.logger.info(f"Email d\'acceptation propriétaire envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l\'envoi de l\'email d\'acceptation propriétaire: {e}", exc_info=True)
        return False

def send_owner_rejection_notification(customer_email, property_title, message):
    msg = Message(
        f'Votre Demande de Visite pour {property_title} a été Rejetée',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email]
    )
    msg.body = (
        f'Bonjour,\n\n'
        f'Nous avons le regret de vous informer que votre demande de visite pour le bien "{property_title}" a été rejetée par le propriétaire.\n\n'
        f'Raison: {message if message else "Aucune raison spécifique fournie."}\n\n'
        f'N\'hésitez pas à soumettre une nouvelle demande ou à nous contacter pour plus d\'informations.\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de rejet propriétaire envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l\'envoi de l\'email de rejet propriétaire: {e}", exc_info=True)
        return False
