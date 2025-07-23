from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_jwt_extended import JWTManager
from config import Config

db = SQLAlchemy()
mail = Mail()
jwt = JWTManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    mail.init_app(app)
    jwt.init_app(app)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    return app
