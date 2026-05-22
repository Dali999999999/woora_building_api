import os
from dotenv import load_dotenv

# Force load .env from current directory
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

from app import create_app, db
from sqlalchemy import text
from app.models import AppSetting, ServiceFee

app = create_app()

with app.app_context():
    print("Updating database schema for Subscription System...")
    try:
        with db.engine.connect() as connection:
            trans = connection.begin()
            try:
                print("Adding 'subscription_expires_at' column to Users...")
                connection.execute(text("ALTER TABLE Users ADD COLUMN subscription_expires_at DATETIME NULL"))
                trans.commit()
                print("✅ Column added successfully!")
            except Exception as e:
                trans.rollback()
                print(f"⚠️ Error executing SQL (The columns might already exist): {e}")

        # Add or update default settings
        print("Ensuring default settings exist...")
        
        # 1. Free property publication limit
        limit_setting = AppSetting.query.filter_by(setting_key='free_property_publication_limit').first()
        if not limit_setting:
            limit_setting = AppSetting(
                setting_key='free_property_publication_limit',
                setting_value='5',
                description='Le nombre maximum de biens immobiliers qu\'un agent ou propriétaire peut publier gratuitement.',
                data_type='integer',
                is_editable_by_admin=True
            )
            db.session.add(limit_setting)
            print("Added 'free_property_publication_limit' setting.")

        # 2. Subscription duration
        duration_setting = AppSetting.query.filter_by(setting_key='property_subscription_duration_days').first()
        if not duration_setting:
            duration_setting = AppSetting(
                setting_key='property_subscription_duration_days',
                setting_value='30',
                description='La durée de validité (en jours) d\'un abonnement de publication de biens.',
                data_type='integer',
                is_editable_by_admin=True
            )
            db.session.add(duration_setting)
            print("Added 'property_subscription_duration_days' setting.")

        # 3. Subscription price service fee
        sub_fee = ServiceFee.query.filter_by(service_key='property_subscription_purchase').first()
        if not sub_fee:
            sub_fee = ServiceFee(
                service_key='property_subscription_purchase',
                name='Abonnement Publication Biens',
                description='Abonnement pour pouvoir publier un nombre illimité de biens.',
                amount=5000.00,
                applicable_to_role='agent', # Or owner, the logic applies to both usually, so we can just use agent as default or customer
                is_active=True
            )
            db.session.add(sub_fee)
            print("Added 'property_subscription_purchase' service fee.")
        
        db.session.commit()
        print("✅ Default settings ensured.")

    except Exception as e:
        print(f"❌ Critical Error: {e}")
