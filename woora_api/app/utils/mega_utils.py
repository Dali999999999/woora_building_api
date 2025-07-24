

import os
import logging
from mega import Mega
from mega.errors import RequestError

logger = logging.getLogger(__name__)

# Variable globale pour mettre en cache l'instance Mega et éviter les logins répétés.
_mega_instance = None

def get_mega_instance():
    """
    Initialise et retourne une instance Mega connectée.
    Tente de réutiliser une session existante. Si la session a expiré
    (détecté par une erreur), elle se reconnecte automatiquement.
    """
    global _mega_instance

    # 1. Si une instance existe, on essaie de l'utiliser.
    if _mega_instance:
        try:
            # On fait un appel léger pour vérifier si la session est toujours valide.
            logger.info("Vérification de la session Mega existante...")
            _mega_instance.get_user() # get_user() est plus léger que get_quota()
            logger.info("Session Mega existante est valide.")
            return _mega_instance
        except RequestError as e:
            # Le code -9 (Not Found) ou -15 (Session ID) indique souvent une session expirée.
            logger.warning(f"La session Mega a probablement expiré (erreur {e.code}). Tentative de reconnexion.")
            _mega_instance = None # On force la réinitialisation
        except Exception as e:
            logger.error(f"Erreur inattendue avec la session Mega existante: {e}", exc_info=True)
            _mega_instance = None # On force la réinitialisation

    # 2. Si l'instance est None (soit au démarrage, soit après une erreur), on se connecte.
    if _mega_instance is None:
        mega_email = os.environ.get('MEGA_EMAIL') or os.getenv('MEGA_EMAIL')
        mega_password = os.environ.get('MEGA_PASSWORD') or os.getenv('MEGA_PASSWORD')

        if not mega_email or not mega_password:
            logger.error("Tentative de connexion Mega échouée : Identifiants non configurés.")
            return None
        try:
            logger.info(f"Nouvelle connexion à Mega avec l'email : {mega_email[:4]}...")
            # Ajout d'un timeout pour éviter un blocage infini
            mega = Mega({'timeout': 60})
            m = mega.login(mega_email, mega_password)
            logger.info("Connexion à Mega réussie.")
            _mega_instance = m # On met en cache la nouvelle instance valide
            return _mega_instance
        except RequestError as req_err:
            logger.error(f"Échec de la connexion à Mega (RequestError {req_err.code}): {req_err}")
            return None
        except Exception as e:
            logger.error(f"Échec de la connexion à Mega (Erreur générale): {e}", exc_info=True)
            return None
