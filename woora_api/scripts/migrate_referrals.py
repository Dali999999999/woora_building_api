import sqlite3
import os
import sys

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import db, create_app
from sqlalchemy import text

app = create_app()

def migrate():
    with app.app_context():
        print("Checking Referrals table for 'status' column...")
        try:
            # Check if column exists
            columns = db.session.execute(text("PRAGMA table_info(Referrals)")).fetchall()
            column_names = [col[1] for col in columns]
            
            if 'status' not in column_names:
                print("Adding 'status' column to Referrals table...")
                db.session.execute(text("ALTER TABLE Referrals ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                db.session.commit()
                print("Column 'status' added successfully.")
            else:
                print("Column 'status' already exists.")
                
            # Update matching engine to ensure we don't have null preferred_status in requests
            print("Checking PropertyRequests table for 'preferred_status' column...")
            columns_req = db.session.execute(text("PRAGMA table_info(PropertyRequests)")).fetchall()
            column_names_req = [col[1] for col in columns_req]
            if 'preferred_status' not in column_names_req:
                print("Adding 'preferred_status' column to PropertyRequests table...")
                db.session.execute(text("ALTER TABLE PropertyRequests ADD COLUMN preferred_status VARCHAR(50)"))
                db.session.commit()
                print("Column 'preferred_status' added successfully.")
            else:
                print("Column 'preferred_status' already exists.")

        except Exception as e:
            print(f"Error during migration: {e}")
            db.session.rollback()

if __name__ == "__main__":
    migrate()
