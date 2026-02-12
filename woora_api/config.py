import os

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

    # Configuration pour Flask-Mail (pour l'envoi d'e-mails de vérification)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.example.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@example.com'

    # Configuration Cloudinary (Géré automatiquement par CLOUDINARY_URL)
    # Plus besoin de clés explicites ici si .env est correct
    #Paiement
    FEDAPAY_SECRET_KEY = os.environ.get('FEDAPAY_SECRET_KEY')
    FEDAPAY_PUBLIC_KEY = os.environ.get('FEDAPAY_PUBLIC_KEY')
