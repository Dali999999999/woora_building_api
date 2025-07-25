from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from flask import request, jsonify, send_file, make_response, current_app
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
    """Logge les informations de la réponse après chaque requête."""
    # --- DÉBUT DE LA CORRECTION ---
    if response.direct_passthrough:
        # Si c'est un fichier streamé (ex: une image), on ne peut pas lire les données.
        current_app.logger.debug(f'📤 Réponse: {response.status_code} - Envoi d\'un fichier binaire (ex: image).')
    else:
        # Pour les réponses JSON normales, on continue comme avant.
        current_app.logger.debug(f'📤 Réponse: {response.status_code} - {response.get_data(as_text=True)[:100]}')
    # --- FIN DE LA CORRECTION ---
    return response

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
