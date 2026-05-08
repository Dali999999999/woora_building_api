"""
Script de diagnostic email - À exécuter directement sur le serveur :
  cd /var/www/api/woora_building_api/woora_api
  python send_test_email.py
"""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Force load .env
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'), override=True)

# Lire les variables
MAIL_SERVER   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT_RAW = os.environ.get('MAIL_PORT', '465')
MAIL_USE_TLS  = os.environ.get('MAIL_USE_TLS', 'False').strip().lower() == 'true'
MAIL_USE_SSL  = os.environ.get('MAIL_USE_SSL', 'False').strip().lower() == 'true'
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD_RAW = os.environ.get('MAIL_PASSWORD', '')
MAIL_PASSWORD = MAIL_PASSWORD_RAW.replace(' ', '')  # Supprimer espaces App Password
MAIL_FROM     = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
RECIPIENT     = MAIL_USERNAME  # On s'envoie à soi-même

print("=" * 60)
print("🔧 CONFIGURATION EMAIL LUES DEPUIS .env")
print("=" * 60)
print(f"  MAIL_SERVER   : {MAIL_SERVER}")
print(f"  MAIL_PORT     : {MAIL_PORT_RAW}")
print(f"  MAIL_USE_TLS  : {MAIL_USE_TLS}")
print(f"  MAIL_USE_SSL  : {MAIL_USE_SSL}")
print(f"  MAIL_USERNAME : {MAIL_USERNAME}")
print(f"  MAIL_PASSWORD : {'*' * len(MAIL_PASSWORD)} ({len(MAIL_PASSWORD)} chars, espaces supprimés)")
print(f"  MAIL_FROM     : {MAIL_FROM}")
print("=" * 60)

def send_via_ssl(port=465):
    """Test avec SSL direct (port 465) — recommandé sur VPS."""
    print(f"\n📨 Test 1 : SMTP SSL direct sur port {port}...")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(MAIL_SERVER, port, context=context, timeout=10) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            msg = MIMEText(
                "Ceci est un email de test Woora Building.\n"
                "Envoyé via SMTP SSL (port 465).\n"
                "Si vous recevez ceci, la configuration fonctionne ! ✅"
            )
            msg['Subject'] = '[WOORA TEST] Diagnostic SSL Port 465'
            msg['From']    = MAIL_FROM
            msg['To']      = RECIPIENT
            server.sendmail(MAIL_FROM, [RECIPIENT], msg.as_string())
        print(f"  ✅ SUCCÈS via SSL port {port} !")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"  ❌ ÉCHEC Auth : {e}")
        print("     → Vérifiez l'App Password Gmail (2FA activée ? Bon compte ?)")
        return False
    except ConnectionRefusedError:
        print(f"  ❌ CONNEXION REFUSÉE sur port {port}")
        print("     → Ce port est bloqué par le firewall du VPS")
        return False
    except TimeoutError:
        print(f"  ❌ TIMEOUT sur port {port}")
        print("     → Ce port est bloqué par le firewall du VPS ou ISP")
        return False
    except Exception as e:
        print(f"  ❌ Erreur : {type(e).__name__}: {e}")
        return False

def send_via_starttls(port=587):
    """Test avec STARTTLS (port 587)."""
    print(f"\n📨 Test 2 : SMTP STARTTLS sur port {port}...")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(MAIL_SERVER, port, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            msg = MIMEText(
                "Ceci est un email de test Woora Building.\n"
                "Envoyé via SMTP STARTTLS (port 587).\n"
                "Si vous recevez ceci, la configuration fonctionne ! ✅"
            )
            msg['Subject'] = '[WOORA TEST] Diagnostic STARTTLS Port 587'
            msg['From']    = MAIL_FROM
            msg['To']      = RECIPIENT
            server.sendmail(MAIL_FROM, [RECIPIENT], msg.as_string())
        print(f"  ✅ SUCCÈS via STARTTLS port {port} !")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"  ❌ ÉCHEC Auth : {e}")
        print("     → Vérifiez l'App Password Gmail (2FA activée ? Bon compte ?)")
        return False
    except ConnectionRefusedError:
        print(f"  ❌ CONNEXION REFUSÉE sur port {port}")
        print("     → Ce port est bloqué par le firewall du VPS")
        return False
    except TimeoutError:
        print(f"  ❌ TIMEOUT sur port {port}")
        print("     → Ce port est bloqué par le firewall du VPS ou ISP")
        return False
    except Exception as e:
        print(f"  ❌ Erreur : {type(e).__name__}: {e}")
        return False

print()
ssl_ok = send_via_ssl(465)
tls_ok = send_via_starttls(587)

print("\n" + "=" * 60)
print("📊 RÉSUMÉ")
print("=" * 60)
print(f"  Port 465 SSL     : {'✅ OK' if ssl_ok  else '❌ ÉCHEC'}")
print(f"  Port 587 STARTTLS: {'✅ OK' if tls_ok  else '❌ ÉCHEC'}")

if ssl_ok:
    print("\n✅ RECOMMANDATION : Utilisez la config SSL (port 465)")
    print("   Dans votre .env serveur, mettez :")
    print("     MAIL_PORT=465")
    print("     MAIL_USE_TLS=False")
    print("     MAIL_USE_SSL=True")
elif tls_ok:
    print("\n✅ RECOMMANDATION : Utilisez la config STARTTLS (port 587)")
    print("   Dans votre .env serveur, vérifiez :")
    print("     MAIL_PORT=587")
    print("     MAIL_USE_TLS=True")
    print("     MAIL_USE_SSL=False")
else:
    print("\n❌ LES DEUX PORTS ÉCHOUENT. Causes possibles :")
    print("   1. L'App Password Gmail est invalide ou révoqué")
    print("      → Allez sur myaccount.google.com → Sécurité → App Passwords")
    print("      → Générez un NOUVEAU mot de passe pour 'Mail > Autre'")
    print("   2. Les ports SMTP sont tous bloqués par le VPS")
    print("      → Contactez votre hébergeur pour débloquer le port 465 ou 587")
    print("      → Ou utilisez un relay SMTP (Brevo, SendGrid, Mailgun)")
    print("   3. La 2FA n'est pas activée sur le compte Gmail")
    print("      → Les App Passwords nécessitent absolument la 2FA active")
