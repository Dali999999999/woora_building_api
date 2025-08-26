# app/main/routes.py

from flask import Blueprint, render_template
from app.models import Property

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

  
