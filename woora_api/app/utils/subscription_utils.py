from app.models import Property, AppSetting
from datetime import datetime
from app import db

def check_publication_limit(user, role):
    """
    Vérifie si un utilisateur (owner ou agent) a le droit de publier un nouveau bien.
    
    Retourne True si autorisé, False sinon.
    """
    # 1. Compter le nombre de biens actuels de l'utilisateur
    if role == 'owner':
        property_count = Property.query.filter_by(owner_id=user.id, deleted_at=None).count()
    elif role == 'agent':
        property_count = Property.query.filter_by(agent_id=user.id, deleted_at=None).count()
    else:
        return False # Rôle non supporté

    # 2. Récupérer la limite gratuite
    limit_setting = AppSetting.query.filter_by(setting_key='free_property_publication_limit').first()
    free_limit = int(limit_setting.setting_value) if limit_setting and limit_setting.setting_value.isdigit() else 5

    # 3. Vérification de la limite
    if property_count < free_limit:
        return True # Encore dans la limite gratuite

    # 4. Vérification de l'abonnement
    if user.subscription_expires_at and user.subscription_expires_at > datetime.utcnow():
        return True # L'abonnement est actif

    return False # Limite atteinte et pas d'abonnement actif
