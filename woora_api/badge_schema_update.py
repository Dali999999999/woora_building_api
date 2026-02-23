import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Adding badge columns...")
    try:
        with db.engine.connect() as connection:
            trans = connection.begin()
            try:
                print("Adding 'customer_has_unread_update' to VisitRequests...")
                connection.execute(text("ALTER TABLE VisitRequests ADD COLUMN customer_has_unread_update BOOLEAN DEFAULT FALSE"))
                print("Adding 'is_read' to Commissions...")
                connection.execute(text("ALTER TABLE Commissions ADD COLUMN is_read BOOLEAN DEFAULT FALSE"))
                
                trans.commit()
                print("✅ Database updated successfully!")
            except Exception as e:
                trans.rollback()
                print(f"⚠️  Error executing SQL (The columns might already exist): {e}")
                
    except Exception as e:
        print(f"❌ Critical Error: {e}")
