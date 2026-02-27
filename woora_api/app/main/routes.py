# app/main/routes.py

from flask import Blueprint, render_template, send_from_directory, current_app, jsonify
from app.models import Property
from flask_jwt_extended import jwt_required
from datetime import datetime
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/.well-known/assetlinks.json')
def serve_assetlinks():
    """
    Sert le fichier de configuration statique pour les App Links Android.
    """
    # On construit le chemin vers le dossier '.well-known' qui est à la racine
    # NOTE : 'app.root_path' pointe vers le dossier où l'application est définie (souvent la racine)
    directory = os.path.join(current_app.root_path, '.well-known')
    
    # send_from_directory est la fonction Flask conçue pour envoyer des fichiers statiques
    # en toute sécurité.
    return send_from_directory(directory, 'assetlinks.json', mimetype='application/json')

@main_bp.route('/biens/<int:property_id>')
def property_share_preview(property_id):
    """
    Cette page ne sert qu'à fournir les méta-données pour les aperçus.
    Elle n'est pas destinée à être vue par un utilisateur dans un navigateur.
    """
    prop = Property.query.get_or_404(property_id)
    
    # On récupère les infos pour l'aperçu
    title = prop.title
    description = prop.description or "Découvrez ce bien exceptionnel sur Woora Immo."
    image_url = prop.images[0].image_url if prop.images else "URL_de_votre_logo.png"
    
    # On renvoie une page HTML minimale avec les balises Open Graph
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta property="og:title" content="{title}" />
        <meta property="og:description" content="{description}" />
        <meta property="og:image" content="{image_url}" />
        <meta property="og:type" content="website" />
    </head>
    <body>
        <p>Redirection vers l'application Woora Immo...</p>
        <script>
            // Optionnel : Tenter une redirection si l'app n'est pas installée
            // window.location.replace("market://details?id=com.example.woora_buiding");
        </script>
    </body>
    </html>
    """

@main_bp.route('/cloudinary/signature', methods=['GET'])
@jwt_required()
def get_cloudinary_signature():
    """
    Génère une signature pour un upload signé vers Cloudinary.
    """
    timestamp = int(datetime.utcnow().timestamp())
    
    # On permet de spécifier le dossier, mais par défaut c'est woora_properties
    folder = request.args.get('folder', 'woora_properties')
    
    # Limitation des dossiers autorisés pour la sécurité
    allowed_folders = ['woora_properties', 'woora_profiles', 'woora_admin_uploads']
    if folder not in allowed_folders:
        folder = 'woora_properties'
    
    params = {
        'timestamp': timestamp,
        'folder': folder
    }
    
    from app.utils.cloudinary_utils import generate_cloudinary_signature
    try:
        signature = generate_cloudinary_signature(params)
        
        # Récupération des clés depuis l'env ou CLOUDINARY_URL
        api_key = os.getenv('CLOUDINARY_API_KEY')
        cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
        
        if not api_key or not cloud_name:
            cloudinary_url = os.getenv('CLOUDINARY_URL')
            if cloudinary_url:
                # Format: cloudinary://api_key:api_secret@cloud_name
                try:
                    parts = cloudinary_url.split('@')
                    cloud_name = parts[1]
                    creds = parts[0].split('//')[1].split(':')
                    api_key = creds[0]
                except Exception:
                    pass
                    
        return jsonify({
            'signature': signature,
            'timestamp': timestamp,
            'api_key': api_key,
            'cloud_name': cloud_name,
            'folder': folder
        }), 200
    except Exception as e:
        current_app.logger.error(f"Erreur signature Cloudinary: {e}")
        return jsonify({'message': "Erreur lors de la génération de la signature."}), 500
