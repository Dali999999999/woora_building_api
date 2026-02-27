# Fichier app/__init__.py ou équivalent

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from flask_cors import CORS # Import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
import re

db = SQLAlchemy()
mail = Mail()
jwt = JWTManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["1000 per day", "200 per hour"],
    storage_uri="memory://"
)

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    import logging
    from logging.handlers import RotatingFileHandler
    import traceback
    import os

    # Configuration du logging vers fichier (error.log)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        file_handler = RotatingFileHandler('error.log', maxBytes=1024 * 1024, backupCount=5)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.ERROR)
        app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.DEBUG)

    db.init_app(app)
    mail.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    CORS(app, resources={
        r"/*": {
            "origins": [
                re.compile(r"http://localhost:[0-9]+"),
                "https://woora-building-admin.vercel.app",
                "https://panel.wooraentreprises.com"
            ],
            "supports_credentials": True,
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        }
    })
    # Gestionnaires d'erreurs JWT
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        app.logger.error("🔑 Token JWT expiré")
        return jsonify({'message': 'Token expiré'}), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(callback_error):
        app.logger.error(f"🔑 Token JWT invalide: {callback_error}")
        return jsonify({'message': f'Token invalide: {callback_error}'}), 401

    @jwt.unauthorized_loader
    def unauthorized_callback(callback_error):
        app.logger.error(f"🔑 Accès non autorisé: {callback_error}")
        return jsonify({'message': f'Accès non autorisé: {callback_error}'}), 401

    @jwt.needs_fresh_token_loader
    def needs_fresh_token_callback(jwt_header, jwt_payload):
        app.logger.warning("🔑 Token JWT non frais requis")
        return jsonify({'message': 'Token non frais requis'}), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        app.logger.warning("🔑 Token JWT révoqué")
        return jsonify({'message': 'Token révoqué'}), 401

    @app.errorhandler(422)
    def handle_unprocessable_entity(e):
        messages = getattr(e, 'data', {}).get('messages', [str(e)])
        app.logger.error(f'❌ Erreur 422: {messages}')
        return jsonify({'error': 'Unprocessable Entity', 'details': messages}), 422

    @app.errorhandler(Exception)
    def handle_exception(e):
        # Capture le traceback complet pour le fichier de log
        tb = traceback.format_exc()
        app.logger.error(f"🚨 ERREUR 500 - Exception non gérée:\n{tb}")
        
        # En mode debug, on peut renvoyer l'erreur, sinon message générique
        message = str(e) if app.debug else "Une erreur interne est survenue sur le serveur."
        return jsonify({
            'message': message,
            'status': 500
        }), 500

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    from app.owners.routes import owners_bp
    app.register_blueprint(owners_bp)

    from app.agents.routes import agents_bp
    app.register_blueprint(agents_bp)

    from app.seekers.routes import seekers_bp
    app.register_blueprint(seekers_bp)

    from app.customers.routes import customers_bp
    app.register_blueprint(customers_bp)

    from app.main.routes import main_bp
    app.register_blueprint(main_bp)

    # --- AJOUT DU NOUVEAU BLUEPRINT POUR LES FAVORIS ---
    from app.favorites.routes import favorites_bp
    app.register_blueprint(favorites_bp)
    # --- FIN DE L'AJOUT ---

    from app.search.routes import search_bp
    app.register_blueprint(search_bp)

    # --- GEOCODING (GPS Autocomplete) ---
    from app.geocoding.routes import geocoding_bp
    app.register_blueprint(geocoding_bp)
    
    # --- PROPERTIES (Liste des statuts) ---
    from app.properties.routes import properties_bp
    app.register_blueprint(properties_bp)

    return app
