import os
from dotenv import load_dotenv
from flask import Flask
from flask_mail import Mail, Message

# Force load .env
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

app = Flask(__name__)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT') or 587)
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

mail = Mail(app)

with app.app_context():
    print(f"Sending test email from {app.config['MAIL_DEFAULT_SENDER']}...")
    try:
        msg = Message(
            subject="TEST WOORA BUILDING - CONFIG VERIFICATION",
            recipients=[app.config['MAIL_USERNAME']], # Send to self
            body="Ceci est un email de test généré depuis le script de diagnostic sur le serveur.\nSi vous recevez ceci, la configuration SMTP est correcte et le code Python envoie bien du texte brut."
        )
        mail.send(msg)
        print("✅ Email envoyé avec succès !")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi : {e}")
