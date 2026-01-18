# Fichier app/__init__.py ou équivalent

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from flask_cors import CORS # Import CORS
from config import Config
import re

db = SQLAlchemy()
mail = Mail()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    import logging
    app.logger.setLevel(logging.DEBUG)

    db.init_app(app)
    mail.init_app(app)
    jwt.init_app(app)
    CORS(app, resources={
    r"/*": {
        "origins": [
            re.compile(r"http://localhost:[0-9]+"),
            "https://woora-building-admin.vercel.app"
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

    return app
