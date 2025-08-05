import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'une_cle_secrete_tres_difficile_a_deviner'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'mysql+pymysql://user:password@localhost:3306/woora_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'super_secret_jwt_key'

    # Configuration pour Flask-Mail (pour l'envoi d'e-mails de vérification)
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.example.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@example.com'

    # Configuration Mega.nz
    MEGA_EMAIL = os.environ.get('MEGA_EMAIL') or 'dev03112005@gmail.com'
    MEGA_PASSWORD = os.environ.get('MEGA_PASSWORD') or 'CXW404notfound'
    #Paiement
    FEDAPAY_SECRET_KEY = os.environ.get('FEDAPAY_SECRET_KEY')
    FEDAPAY_PUBLIC_KEY = os.environ.get('FEDAPAY_PUBLIC_KEY')
