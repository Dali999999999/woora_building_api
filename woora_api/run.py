from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from flask import request, jsonify, send_file, make_response, current_app, send_from_directory
from app.utils.mega_utils import get_mega_instance
import mimetypes
import os

app = create_app()

@app.before_request
def log_request_info():
    current_app.logger.debug(f'🌐 Requête reçue: {request.method} {request.path}')
    current_app.logger.debug(f'🔑 Headers: {dict(request.headers)}')
    current_app.logger.debug(f'📦 Content-Type: {request.content_type}')
    if request.is_json:
        try:
            current_app.logger.debug(f'📄 Body JSON: {request.get_json()}')
        except Exception as e:
            current_app.logger.error(f'Erreur de parsing JSON: {e}')
            current_app.logger.debug(f'📄 Body brut (non JSON): {request.get_data()}')
    else:
        current_app.logger.debug(f'📄 Body brut: {request.get_data()}')

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

@app.route('/get_image_from_mega_link', methods=['GET'])
def get_image_from_mega_link():
    app.logger.info("Requête GET reçue sur /get_image_from_mega_link")

    # --- DÉBUT DE LA CORRECTION ---
    # On lit le paramètre depuis l'URL (ex: ?url=...) au lieu d'un corps JSON
    mega_url = request.args.get('url') 
    # --- FIN DE LA CORRECTION ---

    if not mega_url:
        app.logger.warning("DownloadProxy: Paramètre d'URL 'url' manquant.")
        return jsonify({"error": "Paramètre d'URL 'url' manquant"}), 400

    if not mega_url.startswith("https://mega.") or '!' not in mega_url:
        app.logger.warning(f"DownloadProxy: Format URL Mega invalide reçu: {mega_url}")
        return jsonify({"error": "URL invalide"}), 400

    app.logger.info(f"DownloadProxy: Traitement du lien: {mega_url[:35]}...")

    temp_download_path = None
    try:
        # ... Le reste de votre logique de téléchargement est CORRECT et ne change pas ...
        mega_downloader = get_mega_instance()
        if mega_downloader is None:
            app.logger.error("DownloadProxy: Échec connexion Mega.")
            return jsonify({"error": "Échec connexion service de stockage"}), 503

        app.logger.info(f"DownloadProxy: Tentative de téléchargement depuis l'URL Mega...")
        downloaded_filepath = mega_downloader.download_url(
            url=mega_url,
            dest_path=DOWNLOAD_FOLDER
        )
        temp_download_path = str(downloaded_filepath)
        app.logger.info(f"DownloadProxy: Fichier téléchargé et déchiffré sur le serveur : '{temp_download_path}'")

        if not os.path.exists(temp_download_path):
            app.logger.error(f"DownloadProxy: Fichier téléchargé non trouvé sur disque à '{temp_download_path}' après download_url !")
            return jsonify({"error": "Erreur interne: Fichier disparu après téléchargement"}), 500

        mimetype, _ = mimetypes.guess_type(temp_download_path)
        if not mimetype or not mimetype.startswith('image/'):
            app.logger.warning(f"DownloadProxy: Impossible de déterminer un mimetype d'image valide pour '{temp_download_path}'. Mimetype deviné: {mimetype}. Utilisation de 'application/octet-stream'.")
            mimetype = 'application/octet-stream'

        app.logger.info(f"DownloadProxy: Envoi du fichier '{os.path.basename(temp_download_path)}' avec mimetype '{mimetype}'...")

        return send_file(temp_download_path, mimetype=mimetype, as_attachment=False)

    except Exception as e:
        app.logger.error(f"DownloadProxy: Erreur inattendue lors du téléchargement/envoi: {e}", exc_info=True)
        return jsonify({"error": f"Erreur interne du serveur ({type(e).__name__})."}), 500
    finally:
        if temp_download_path and os.path.exists(temp_download_path):
            try:
                os.remove(temp_download_path)
                app.logger.info(f"DownloadProxy: Fichier temporaire serveur supprimé: '{temp_download_path}'")
            except OSError as e_remove:
                app.logger.error(f"DownloadProxy: Erreur suppression temp serveur '{temp_download_path}': {e_remove}")

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
