
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

def send_property_invalidation_email(owner_email, property_title, reason):
    msg = Message(
        f'Mise à jour pour votre bien : {property_title}',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[owner_email]
    )
    msg.body = (
        f'Bonjour,\n\n'
        f'Nous souhaitons vous informer d\'une mise à jour concernant votre bien "{property_title}".\n\n'
        f'Après examen par notre équipe, ce bien ne peut pas être publié en l\'état et a été mis en statut "Non Validé".\n\n'
        f'Motif indiqué par l\'administrateur :\n'
        f'"{reason if reason else "Non spécifié"}"\n\n'
        f'Vous pouvez modifier votre annonce depuis votre application pour corriger ces points et la soumettre à nouveau.\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        current_app.logger.info(f"Email d'invalidation de bien envoyé à {owner_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email d'invalidation: {e}", exc_info=True)
        return False

def send_alert_match_email(customer_email, customer_name, property_title, property_id):
    msg = Message(
        f'Nouveau bien correspondant à votre recherche ! 🏠',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email]
    )
    msg.body = (
        f'Bonjour {customer_name},\n\n'
        f'Bonne nouvelle ! Un nouveau bien vient d\'être publié et correspond à vos critères de recherche.\n\n'
        f'"{property_title}"\n\n'
        f'Ouvrez vite l\'application Woora Building pour le consulter avant tout le monde !\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur email alerte: {e}")
        return False

def send_account_deletion_email(user_email, user_name, reason):
    msg = Message(
        f'Suppression de votre compte Woora Immo',
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[user_email]
    )
    msg.body = (
        f'Bonjour {user_name},\n\n'
        f'Nous vous informons que votre compte Woora Immo a été supprimé par l\'administrateur.\n\n'
        f'Motif : {reason if reason else "Aucun motif spécifique."}\n\n'
        f'Vos données et vos annonces ne sont plus accessibles.\n'
        f'Si vous pensez qu\'il s\'agit d\'une erreur, veuillez contacter le support.\n\n'
        f'Cordialement,\n'
        f'L\'équipe Woora Immo'
    )
    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur email suppression compte: {e}")
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

def send_referral_used_notification(agent_email, customer_name, property_title):
    """
    Notifie un agent que son code de parrainage a été utilisé pour une demande de visite.
    """
    msg = Message(
        subject="Votre code de parrainage a été utilisé !",
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[agent_email]
    )
    msg.body = f"""
    Bonjour,

    Bonne nouvelle ! Le client {customer_name} a utilisé votre code de parrainage pour demander une visite du bien suivant :
    "{property_title}".

    Nous vous tiendrons informé de la suite des événements.

    L'équipe Woora Immo
    """
    try:
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(f"Échec de l'envoi de l'email de notification de parrainage à {agent_email}: {e}")

def send_admin_response_to_seeker(customer_email, customer_name, original_request, admin_response):
    """
    Envoie un e-mail au client avec la réponse de l'administrateur à son alerte.

    :param customer_email: L'adresse e-mail du client.
    :param customer_name: Le prénom du client pour la personnalisation.
    :param original_request: Le texte de la demande initiale du client.
    :param admin_response: Le message de réponse rédigé par l'administrateur.
    """
    subject = "Réponse à votre alerte de recherche sur Woora Immo"
    
    # On utilise html_content pour un email plus riche et mieux formaté
    html_body = f"""
    <div style="font-family: Arial, sans-serif; color: #333;">
        <h2>Bonjour {customer_name},</h2>
        <p>Un de nos administrateurs a examiné votre alerte de recherche de bien et vous a laissé une réponse.</p>
        <hr>
        <p><strong>Rappel de votre demande :</strong></p>
        <blockquote style="border-left: 4px solid #ccc; padding-left: 15px; margin-left: 5px; color: #555;">
            <em>"{original_request}"</em>
        </blockquote>
        <br>
        <p><strong>Réponse de notre équipe :</strong></p>
        <div style="background-color: #f2f2f2; border-radius: 8px; padding: 15px;">
            <p style="margin: 0;">{admin_response}</p>
        </div>
        <br>
        <p>N'hésitez pas à nous recontacter si vous avez d'autres questions.</p>
        <p>Cordialement,</p>
        <p><strong>L'équipe Woora Immo</strong></p>
    </div>
    """

    msg = Message(
        subject=subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=html_body  # On assigne le contenu HTML ici
    )
    
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de réponse à l'alerte envoyé avec succès à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Échec de l'envoi de l'email de réponse à l'alerte pour {customer_email}: {e}", exc_info=True)
        return False
