from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from flask_cors import CORS # Import CORS
from config import Config

db = SQLAlchemy()
mail = Mail()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Définir le niveau de journalisation pour afficher les messages DEBUG
    import logging
    app.logger.setLevel(logging.DEBUG)

    db.init_app(app)
    mail.init_app(app)
    jwt.init_app(app)
    CORS(app, resources={r"/admin/*": {"origins": "http://localhost:3000"}}) # Configure CORS for admin routes

    # Gestionnaires d'erreurs JWT
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        app.logger.error("🔑 Token JWT expiré")
        return jsonify({'message': 'Token expiré'}), 401 # Changed to 401 Unauthorized

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

    # Gestionnaire d'erreur 422 générique
    @app.errorhandler(422)
    def handle_unprocessable_entity(e):
        # Cette erreur est souvent levée par webargs/marshmallow si utilisé, ou par Flask-JWT-Extended
        # Nous allons essayer de récupérer les détails si possible
        messages = getattr(e, 'data', {}).get('messages', [str(e)])
        app.logger.error(f'❌ Erreur 422: {messages}')
        return jsonify({'error': 'Unprocessable Entity', 'details': messages}), 422

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    from app.owners.routes import owners_bp
    app.register_blueprint(owners_bp)

    return app
