import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
from flask import current_app

def init_cloudinary():
    """
    Initialise la configuration Cloudinary depuis les variables d'environnement.
    Doit être appelé au démarrage de l'application.
    """
    # L'URL CLOUDINARY_URL gère tout automatiquement si elle est définie en ENV.
    # Mais si on veut être explicite :
    if os.getenv('CLOUDINARY_URL'):
        return # Auto-config via Env Var
        
    cloudinary.config(
        cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key = os.getenv('CLOUDINARY_API_KEY'),
        api_secret = os.getenv('CLOUDINARY_API_SECRET'),
        secure = True
    )

def upload_image(file_storage, folder="woora_uploads"):
    """
    Upload un fichier image vers Cloudinary.
    
    Args:
        file_storage: L'objet FileStorage de Flask (request.files['image']) OU un chemin de fichier.
        folder: Le dossier dans lequel stocker l'image sur Cloudinary.

    Returns:
        str: L'URL sécurisée (HTTPS) de l'image uploadée, ou None en cas d'erreur.
    """
    try:
        # Si c'est un objet FileStorage de Flask, on lit le stream
        response = cloudinary.uploader.upload(file_storage, folder=folder)
        
        # On récupère l'URL sécurisée
        secure_url = response.get('secure_url')
        current_app.logger.info(f"Cloudinary Upload Success: {secure_url}")
        return secure_url
        
    except Exception as e:
        current_app.logger.error(f"Cloudinary Upload Error: {str(e)}")
        return None

def generate_cloudinary_signature(params):
    """
    Génère une signature pour un upload signé vers Cloudinary.
    
    Args:
        params: Dictionnaire des paramètres à signer (doit inclure 'timestamp').
    
    Returns:
        str: La signature générée.
    """
    api_secret = os.getenv('CLOUDINARY_API_SECRET')
    if not api_secret:
        # Si CLOUDINARY_URL est utilisé, on peut extraire le secret
        cloudinary_url = os.getenv('CLOUDINARY_URL')
        if cloudinary_url:
            # Format: cloudinary://api_key:api_secret@cloud_name
            try:
                api_secret = cloudinary_url.split(':')[2].split('@')[0]
            except Exception:
                pass
                
    if not api_secret:
        raise ValueError("Cloudinary API Secret non trouvé dans l'environnement.")
        
    return cloudinary.utils.api_sign_request(params, api_secret)
