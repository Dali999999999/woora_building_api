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
    CORS(app, resources={r"/admin/*": {"origins": "http://localhost:3000", "https://woora-building-api.onrender.com"}}) # Configure CORS for admin routes

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    return app
