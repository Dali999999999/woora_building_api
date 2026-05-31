
from flask_mail import Message
from flask import current_app
from app import mail
from datetime import datetime

def get_email_template(title, body_content):
    """
    Génère un template HTML professionnel pour les emails WOORA BUILDING.
    """
    year = datetime.utcnow().year
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .header {{ background-color: #2C3E50; padding: 25px; text-align: center; }}
            .header h1 {{ color: #ffffff; margin: 0; font-size: 24px; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; }}
            .content {{ padding: 30px; color: #333333; line-height: 1.6; font-size: 16px; }}
            .footer {{ background-color: #ecf0f1; padding: 20px; text-align: center; font-size: 12px; color: #7f8c8d; border-top: 1px solid #e0e0e0; }}
            .highlight {{ color: #2980b9; font-weight: 600; }}
            .btn {{ display: inline-block; padding: 10px 20px; background-color: #2980b9; color: #ffffff !important; text-decoration: none; border-radius: 5px; margin-top: 15px; font-weight: bold; }}
            blockquote {{ border-left: 4px solid #2980b9; margin: 15px 0; padding: 10px 15px; background-color: #f8f9fa; color: #555; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>WOORA BUILDING</h1>
            </div>
            <div class="content">
                {body_content}
            </div>
            <div class="footer">
                <p>&copy; {year} WOORA BUILDING. Tous droits réservés.</p>
                <p>Ceci est un message automatique, merci de ne pas y répondre directement.</p>
                <p>Une question ? Contactez-nous à <a href="mailto:contact@woorabuilding.com" style="color: #2980b9;">contact@woorabuilding.com</a></p>
            </div>
        </div>
    </body>
    </html>
    """

def send_new_visit_request_notification(owner_email, property_title, requested_datetime, message):
    """
    Notifie le PROPRIÉTAIRE / AGENT d'une nouvelle demande de visite.
    IMPORTANT : Ne contient AUCUNE donnée personnelle du client.
    """
    subject = f'Nouvelle Demande de Visite pour votre bien : {property_title}'
    
    body_html = f"""
        <p>Bonjour,</p>
        <p>Une nouvelle demande de visite a été soumise pour votre bien <strong>"{property_title}"</strong> sur la plateforme <strong>WOORA Building</strong>.</p>
        
        <h3>Détails de la demande :</h3>
        <ul>
            <li><strong>Bien :</strong> <span class="highlight">{property_title}</span></li>
            <li><strong>Date et Heure Souhaitées :</strong> {requested_datetime}</li>
        </ul>
        
        <p><strong>Message du visiteur :</strong></p>
        <blockquote>{message if message else "Aucun message particulier."}</blockquote>
        
        <p>Veuillez vous connecter à votre application <strong>WOORA Building</strong> pour <strong>accepter</strong> ou <strong>refuser</strong> cette demande.</p>
        <p>Cordialement,<br>L'équipe WOORA Building</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[owner_email],
        html=get_email_template("Nouvelle Demande de Visite", body_html)
    )
    
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de notification de nouvelle demande de visite envoyé au propriétaire {owner_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email de notification au propriétaire: {e}", exc_info=True)
        return False


def send_owner_accepted_to_admin(admin_email, property_title, requested_datetime):
    """
    Notifie l'ADMIN que le propriétaire a accepté une demande de visite.
    L'admin doit maintenant valider pour que le client reçoive la confirmation.
    """
    subject = f'Action requise : Demande de visite validée par le propriétaire – {property_title}'

    body_html = f"""
        <p>Bonjour Administrateur,</p>
        <p>Le propriétaire du bien <strong>"{property_title}"</strong> a <strong style="color:#27AE60;">accepté</strong> une demande de visite.</p>

        <h3>Détails :</h3>
        <ul>
            <li><strong>Bien :</strong> <span class="highlight">{property_title}</span></li>
            <li><strong>Date et Heure Souhaitées :</strong> {requested_datetime}</li>
        </ul>

        <p>La demande est désormais en attente de votre <strong>validation finale</strong>. Connectez-vous au panel d'administration pour confirmer ou refuser cette visite.</p>
        <p>Cordialement,<br>L'équipe WOORA Building</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[admin_email],
        html=get_email_template("Validation requise – Demande de visite", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email 'proprio a accepté' envoyé à l'admin {admin_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur envoi email owner_accepted à admin: {e}", exc_info=True)
        return False

def send_admin_rejection_notification(customer_email, property_title, message):
    subject = f'Concernant votre demande de visite pour {property_title}'
    
    body_html = f"""
        <p>Bonjour,</p>
        <p>Nous avons le regret de vous informer que votre demande de visite pour le bien <strong>"{property_title}"</strong> a été refusée par l'administration.</p>
        
        <p><strong>Motif du refus :</strong></p>
        <blockquote>{message if message else "Aucune raison spécifique fournie."}</blockquote>
        
        <p>Nous vous invitons à choisir <strong>une autre date</strong> pour ce bien ou à consulter <strong>d'autres biens similaires</strong> en option sur notre plateforme, le temps qu'une nouvelle opportunité se présente.</p>
        
        <p>L'équipe WOORA Building reste à votre entière disposition pour vous accompagner dans vos recherches.</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Avis sur votre demande de visite", body_html)
    )
    
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de rejet admin envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email de rejet admin: {e}", exc_info=True)
        return False

def send_visit_request_confirmation_to_customer(customer_email, customer_name, property_title, requested_datetime):
    subject = f'Confirmation de votre demande de visite - {property_title}'
    
    body_html = f"""
        <p>Bonjour {customer_name},</p>
        <p>Nous confirmons la réception de votre demande de visite pour le bien <strong>"{property_title}"</strong>.</p>
        
        <h3>Détails de votre demande :</h3>
        <ul>
            <li><strong>Date et Heure Souhaitées :</strong> {requested_datetime}</li>
            <li><strong>Statut actuel :</strong> En attente de validation</li>
        </ul>
        
        <p>Nous avons notifié le propriétaire et l'administrateur. Vous recevrez une notification dès que votre demande sera traitée.</p>
        <p>Merci de votre confiance !</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Demande de visite enregistrée", body_html)
    )
    
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de confirmation envoyé au client {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email de confirmation au client: {e}", exc_info=True)
        return False

def send_property_invalidation_email(owner_email, property_title, reason):
    subject = f'Attention requise : {property_title}'
    
    body_html = f"""
        <p>Bonjour,</p>
        <p>Nous souhaitons vous informer d'une mise à jour concernant votre bien <strong>"{property_title}"</strong>.</p>
        <p>Après examen par notre équipe qualité, ce bien ne peut pas être publié en l'état et a été placé en statut <strong style="color:red;">Non Validé</strong>.</p>
        
        <p><strong>Motif indiqué :</strong></p>
        <blockquote>{reason if reason else "Non spécifié"}</blockquote>
        
        <p>Vous pouvez modifier votre annonce depuis votre application <strong>WOORA BUILDING</strong> pour corriger ces points et la soumettre à nouveau pour validation.</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[owner_email],
        html=get_email_template("Validation de votre bien", body_html)
    )
    
    try:
        mail.send(msg)
        current_app.logger.info(f"Email d'invalidation de bien envoyé à {owner_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email d'invalidation: {e}", exc_info=True)
        return False

def send_alert_match_email(customer_email, customer_name, property_title, property_id):
    subject = 'Nouveau bien correspondant à votre recherche ! 🏠'
    
    body_html = f"""
        <p>Bonjour {customer_name},</p>
        <p>Bonne nouvelle ! Un nouveau bien vient d'être publié sur <strong>WOORA BUILDING</strong> et correspond à vos critères de recherche.</p>
        
        <div style="text-align: center; margin: 20px 0;">
            <h3 class="highlight">"{property_title}"</h3>
        </div>
        
        <p>Ouvrez vite l'application <strong>WOORA BUILDING</strong> pour le consulter avant tout le monde !</p>
        
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Alerte Nouveauté", body_html)
    )

    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur email alerte: {e}")
        return False

def send_account_deletion_email(user_email, user_name, reason):
    subject = 'Fermeture de votre compte WOORA BUILDING'
    
    body_html = f"""
        <p>Bonjour {user_name},</p>
        <p>Nous vous informons que votre compte <strong>WOORA BUILDING</strong> a été supprimé par l'administrateur.</p>
        
        <p><strong>Motif :</strong></p>
        <blockquote>{reason if reason else "Aucun motif spécifique."}</blockquote>
        
        <p>Vos données et vos annonces ne sont plus accessibles.</p>
        <p>Si vous pensez qu'il s'agit d'une erreur, veuillez contacter le support.</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[user_email],
        html=get_email_template("Suppression de compte", body_html)
    )

    try:
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur email suppression compte: {e}")
        return False

def send_admin_confirmation_to_owner(owner_email, customer_name, property_title, requested_datetime):
    """
    [DÉPRÉCIÉE – conservée pour compatibilité avec les visites 'confirmed' existantes]
    Dans le nouveau flux, l'admin confirme après le propriétaire.
    """
    subject = f'Demande de Visite Confirmée pour {property_title}'
    
    body_html = f"""
        <p>Bonjour Propriétaire,</p>
        <p>Une demande de visite pour votre bien <strong>"{property_title}"</strong> a été pré-validée par l'administrateur <strong>WOORA Building</strong>.</p>
        
        <h3>Détails de la demande :</h3>
        <ul>
            <li><strong>Client intéressé :</strong> {customer_name}</li>
            <li><strong>Date et Heure Souhaitées :</strong> {requested_datetime}</li>
        </ul>
        
        <p>Veuillez vous connecter à votre application pour <strong>accepter</strong> ou <strong>refuser</strong> cette demande de visite.</p>
        <p>Cordialement,<br>L'équipe WOORA Building</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[owner_email],
        html=get_email_template("Confirmation de demande de visite", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email de confirmation admin envoyé au propriétaire {owner_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email de confirmation admin au propriétaire: {e}", exc_info=True)
        return False

def send_owner_acceptance_notification(customer_email, property_title, requested_datetime):
    subject = f'Visite confirmée : {property_title}'
    
    body_html = f"""
        <h2 style="color: #27AE60;">Félicitations !</h2>
        <p>Votre demande de visite pour le bien <strong>"{property_title}"</strong> a été acceptée par le propriétaire.</p>
        
        <p><strong>La visite est confirmée pour le :</strong></p>
        <p style="font-size: 18px; font-weight: bold;">{requested_datetime}</p>
        
        <p>Nous vous souhaitons une excellente visite !</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Visite Confirmée", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email d'acceptation propriétaire envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email d'acceptation propriétaire: {e}", exc_info=True)
        return False

def send_owner_rejection_notification(customer_email, property_title, message):
    subject = f'Concernant votre demande de visite pour {property_title}'
    
    body_html = f"""
        <p>Bonjour,</p>
        <p>Nous avons le regret de vous informer que votre demande de visite pour le bien <strong>"{property_title}"</strong> a été refusée par le propriétaire.</p>
        
        <p><strong>Raison indiquée :</strong></p>
        <blockquote>{message if message else "Aucune raison spécifique fournie."}</blockquote>
        
        <p>N'hésitez pas à soumettre une nouvelle demande pour un autre créneau ou à consulter nos autres biens sur <strong>WOORA BUILDING</strong>.</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Demande de visite refusée", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email de rejet propriétaire envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur lors de l'envoi de l'email de rejet propriétaire: {e}", exc_info=True)
        return False

def send_referral_used_notification(agent_email, customer_name, property_title):
    subject = "Votre code de parrainage a été utilisé !"
    
    body_html = f"""
        <p>Bonjour,</p>
        <p>Bonne nouvelle ! Le client <strong>{customer_name}</strong> a utilisé votre code de parrainage pour demander une visite du bien suivant :</p>
        <p class="highlight">"{property_title}"</p>
        <p>Nous vous tiendrons informé de la suite des événements concernant cette transaction.</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[agent_email],
        html=get_email_template("Succès Parrainage", body_html)
    )

    try:
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(f"Échec de l'envoi de l'email de notification de parrainage à {agent_email}: {e}")

def send_admin_response_to_seeker(customer_email, customer_name, original_request, admin_response):
    subject = "Réponse à votre alerte de recherche sur WOORA BUILDING"
    
    body_html = f"""
        <p>Bonjour {customer_name},</p>
        <p>Un de nos administrateurs a examiné votre alerte de recherche de bien et vous a laissé une réponse.</p>
        
        <p><strong>Rappel de votre demande :</strong></p>
        <blockquote style="background-color: #f1f1f1; font-style: italic;">"{original_request}"</blockquote>
        
        <p><strong>Réponse de notre équipe :</strong></p>
        <div style="background-color: #e8f4fc; border-left: 4px solid #3498db; padding: 15px; border-radius: 4px;">
            {admin_response}
        </div>
        
        <p>N'hésitez pas à nous recontacter si vous avez d'autres questions.</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Réponse à votre alerte", body_html)
    )
    
    try:
        mail.send(msg)
        current_app.logger.info(f"Email de réponse à l'alerte envoyé avec succès à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Échec de l'envoi de l'email de réponse à l'alerte pour {customer_email}: {e}", exc_info=True)
        return False

def send_commission_paid_notification(agent_email, agent_name, amount, property_title):
    subject = "Félicitations ! Commission Reçue 💰"
    
    body_html = f"""
        <p>Bonjour {agent_name},</p>
        <p>Excellente nouvelle ! Une transaction a été finalisée grâce à votre parrainage.</p>
        
        <div style="background-color: #e8f8f5; border-left: 4px solid #2ecc71; padding: 15px; margin: 20px 0;">
            <p style="margin: 0; font-size: 18px;">Vous avez reçu une commission de :</p>
            <h2 style="color: #27ae60; margin: 10px 0;">{amount} FCFA</h2>
            <p style="margin: 0;">Pour le bien : <strong>{property_title}</strong></p>
        </div>
        
        <p>Ce montant a été crédité sur votre portefeuille <strong>WOORA BUILDING</strong>.</p>
        <p>Continuez votre excellent travail !</p>
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[agent_email],
        html=get_email_template("Commission Reçue", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email de commission envoyé à {agent_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur envoi email commission: {e}")
        return False

def send_deal_closed_client_notification(customer_email, customer_name, property_title, agent_id=None):
    subject = f"Félicitations pour votre acquisition : {property_title} ! 🎉"
    
    review_section = ""
    if agent_id:
        review_section = f"""
            <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                <p>Avez-vous apprécié l'accompagnement de votre agent ?</p>
                <a href="https://woorabuilding.com/rate-agent/{agent_id}" class="btn">Noter mon agent</a>
            </div>
        """

    body_html = f"""
        <p>Bonjour {customer_name},</p>
        <p>Toute l'équipe de <strong>WOORA BUILDING</strong> vous félicite pour l'acquisition du bien <strong>"{property_title}"</strong> !</p>
        
        <p>Nous espérons que ce nouveau chapitre vous apportera entière satisfaction.</p>
        
        <p>Merci de nous avoir fait confiance pour votre projet immobilier.</p>
        
        {review_section}
        
        <p>Cordialement,<br>L'équipe WOORA BUILDING</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Félicitations", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email deal closed envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur envoi email deal closed: {e}")
        return False

def send_visit_request_confirmation_to_customer(customer_email, customer_name, property_title, requested_datetime):
    """
    Confirme au CLIENT que sa demande de visite a bien été reçue.
    Lui explique le processus : proprio → admin → confirmation client.
    """
    subject = f'Demande de visite reçue – {property_title}'

    body_html = f"""
        <p>Bonjour {customer_name},</p>
        <p>Votre demande de visite pour le bien <strong>"{property_title}"</strong> a bien été enregistrée sur <strong>WOORA Building</strong>.</p>

        <h3>Récapitulatif :</h3>
        <ul>
            <li><strong>Bien :</strong> <span class="highlight">{property_title}</span></li>
            <li><strong>Date et heure souhaitées :</strong> {requested_datetime}</li>
        </ul>

        <p><strong>Prochaines étapes :</strong></p>
        <ol>
            <li>Le propriétaire va être notifié de votre demande.</li>
            <li>S'il l'accepte, l'équipe WOORA Building validera définitivement la visite.</li>
            <li>Vous recevrez un email de confirmation dès que tout sera validé.</li>
        </ol>

        <p>Vous pouvez suivre l'état de votre demande dans l'application <strong>WOORA Building</strong>.</p>
        <p>Cordialement,<br>L'équipe WOORA Building</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Demande de visite reçue", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email de confirmation de réception envoyé au client {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur envoi email confirmation client: {e}", exc_info=True)
        return False


def send_visit_completed_email(customer_email, customer_name, property_title):
    """
    Envoie un email de remerciement et de félicitations au client après une visite effectuée.
    """
    subject = f'Visite effectuée avec succès – {property_title}'

    body_html = f"""
        <p>Bonjour {customer_name},</p>
        <p>Nous espérons que votre visite pour le bien <strong>"{property_title}"</strong> s'est bien déroulée.</p>

        <p>Votre demande de visite est maintenant marquée comme <strong style="color:#27AE60;">Effectuée</strong> dans votre espace personnel <strong>WOORA Building</strong>.</p>
        
        <p>N'hésitez pas à nous faire part de vos commentaires et à continuer de parcourir nos offres pour trouver le bien de vos rêves.</p>

        <p>L'équipe WOORA Building reste à votre entière disposition.</p>
    """

    msg = Message(
        subject,
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        recipients=[customer_email],
        html=get_email_template("Visite effectuée", body_html)
    )

    try:
        mail.send(msg)
        current_app.logger.info(f"Email de remerciement de visite effectuée envoyé à {customer_email}")
        return True
    except Exception as e:
        current_app.logger.error(f"Erreur envoi email visite effectuée: {e}", exc_info=True)
        return False
