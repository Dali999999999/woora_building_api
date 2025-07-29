
# app/utils/helpers.py (ou directement dans le fichier de routes)
import random
import string
from app.models import Referral

def generate_unique_referral_code():
    """Génère un code de parrainage unique et vérifie qu'il n'existe pas déjà."""
    while True:
        # Crée un code du type WOORA-XXXX-XXXX
        part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        code = f"WOORA-{part1}-{part2}"
        
        # Vérifie si le code existe déjà dans la base de données
        if not Referral.query.filter_by(referral_code=code).first():
            return code
