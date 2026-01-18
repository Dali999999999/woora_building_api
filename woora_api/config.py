import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'une_cle_secrete_tres_difficile_a_deviner'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://user:password@localhost:3306/woora_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT Configuration
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'super_secret_jwt_key'
    JWT_TOKEN_LOCATION = ['headers', 'cookies'] # Support both for mobile/web compatibility
    JWT_COOKIE_SECURE = False # Set to True in production (HTTPS)
    JWT_ACCESS_COOKIE_PATH = '/'
    JWT_REFRESH_COOKIE_PATH = '/auth/refresh' # Only send refresh token to this path
    JWT_COOKIE_CSRF_PROTECT = False # Disable CSRF for now for simplicity, enable later for better security
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
