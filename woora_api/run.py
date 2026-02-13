from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from flask import request, jsonify, send_file, make_response, current_app, send_from_directory
# from app.utils.mega_utils import get_mega_instance # REMOVED
import mimetypes
import os
import json

app = create_app()

@app.before_request
def log_request_info():
    current_app.logger.debug(f'🌐 Requête reçue: {request.method} {request.path}')
    current_app.logger.debug(f'🔑 Headers: {dict(request.headers)}')
    current_app.logger.debug(f'📦 Content-Type: {request.content_type}')
    if request.is_json and request.content_length and request.content_length > 0:
        try:
            current_app.logger.debug(f'📄 Body JSON: {request.get_json(silent=True)}')
        except Exception:
            current_app.logger.debug(f'📄 Body brut (non JSON): {request.get_data()}')
    else:
        current_app.logger.debug(f'📄 Body: {request.get_data()}')

@app.after_request
def log_response_info(response):
    """
    Logge les informations de la réponse après chaque requête.
    Gère différemment les réponses JSON et les réponses de fichiers binaires.
    """
    
    # Vérifie si la réponse est un fichier envoyé en streaming (comme une image)
    if response.direct_passthrough:
        # Dans ce cas, on ne peut pas lire le contenu avec get_data(), car cela causerait une erreur.
        # On se contente donc de logger le statut et le type de contenu.
        current_app.logger.debug(
            f'📤 Réponse: {response.status_code} - Envoi d\'un fichier binaire. '
            f'Content-Type: {response.content_type}'
        )
    else:
        # Pour toutes les autres réponses (généralement du JSON), on peut lire le début du contenu.
        current_app.logger.debug(
            f'📤 Réponse: {response.status_code} - {response.get_data(as_text=True)[:200]}'
        )
        
    return response

# Dossier temporaire pour les téléchargements
DOWNLOAD_FOLDER = '/tmp' # Ou un autre chemin approprié
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/.well-known/assetlinks.json')
def serve_assetlinks():
    """
    Sert le fichier de configuration statique pour les App Links Android.
    Cette version lit le fichier manuellement pour être plus robuste.
    """
    try:
        # On suppose que le dossier .well-known est au même niveau que le dossier 'app'
        # C'est le chemin le plus courant.
        # os.path.abspath('.') donne le répertoire de travail actuel.
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, '..', '.well-known', 'assetlinks.json')
        
        # Pour Render, la structure peut être différente. On essaie un autre chemin.
        if not os.path.exists(file_path):
            # Ce chemin suppose que run.py est dans un sous-dossier comme 'woora_api'
            file_path = os.path.join(current_dir, '..', '..', '.well-known', 'assetlinks.json')

        # Ultime tentative à la racine du projet
        if not os.path.exists(file_path):
            file_path = os.path.join(os.path.abspath('.'), '.well-known', 'assetlinks.json')

        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # On renvoie le contenu JSON avec le bon mimetype
        return jsonify(data)
        
    except FileNotFoundError:
        current_app.logger.error(f"Fichier assetlinks.json non trouvé au chemin calculé: {file_path}")
        return "assetlinks.json not found", 404
    except Exception as e:
        current_app.logger.error(f"Erreur lors de la lecture de assetlinks.json: {e}")
        return "Error processing assetlinks.json", 500

# --- MEGA PROXY REMOVED ---
# Les images sont maintenant servies directement par Cloudinary via des URLs publiques.
# La route /get_image_from_mega_link est obsolète.

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
