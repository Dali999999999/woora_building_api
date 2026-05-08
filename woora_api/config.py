import os
from dotenv import load_dotenv

# Charger .env explicitement ici aussi (sécurité si Config est importé directement)
_basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(_basedir, '.env'))

class Config:
    # Security: Force environment variables for secrets (no fallback)
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    
    if not SECRET_KEY:
        raise RuntimeError("CRITICAL: SECRET_KEY must be set in environment variables")
    if not JWT_SECRET_KEY:
        raise RuntimeError("CRITICAL: JWT_SECRET_KEY must be set in environment variables")
    
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://user:password@localhost:3306/woora_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # SQLAlchemy Engine Options (Connection Pooling)
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'max_overflow': 20,
        'pool_recycle': 1800, # Recycle connections every 30 minutes
        'pool_pre_ping': True # Check connection health before using
    }
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    JWT_COOKIE_SECURE = True # Required for SameSite=None
    JWT_COOKIE_SAMESITE = 'None' # Allows cross-origin requests (panel -> api)
    JWT_ACCESS_COOKIE_PATH = '/'
    JWT_REFRESH_COOKIE_PATH = '/' # Simplify path to avoid mismatch on logout
    JWT_COOKIE_CSRF_PROTECT = True  # Security: Enable CSRF protection
    JWT_ACCESS_COOKIE_NAME = 'access_token_cookie'
    JWT_REFRESH_COOKIE_NAME = 'refresh_token_cookie'

    # Configuration pour Flask-Mail (envoi d'e-mails de vérification & notifications)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 465)
    # Parsing booléen correct : 'True' -> True, tout autre valeur -> False
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'False').strip().lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').strip().lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    # Supprime les espaces du mot de passe (App Password Gmail peut contenir des espaces)
    _mail_password_raw = os.environ.get('MAIL_PASSWORD', '')
    MAIL_PASSWORD = _mail_password_raw.replace(' ', '') if _mail_password_raw else None
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME') or 'noreply@example.com'
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    # Configuration Cloudinary (Géré automatiquement par CLOUDINARY_URL)
    # Plus besoin de clés explicites ici si .env est correct
    #Paiement
    FEDAPAY_SECRET_KEY = os.environ.get('FEDAPAY_SECRET_KEY')
    FEDAPAY_PUBLIC_KEY = os.environ.get('FEDAPAY_PUBLIC_KEY')
