from app import create_app, db
from sqlalchemy import text

app = create_app()

with app.app_context():
    print("Updating database schema...")
    try:
        # Tries to add the columns. 
        # Note: 'IF NOT EXISTS' for columns is not supported by all SQL dialects directly in ALTER TABLE in a standard way,
        # so we often just try and catch the error if they exist, or query information_schema.
        # For simplicity in this dev script, we'll try to add them.
        
        with db.engine.connect() as connection:
            # Using transaction
            trans = connection.begin()
            try:
                # Add deleted_at
                print("Adding 'deleted_at' column...")
                connection.execute(text("ALTER TABLE Properties ADD COLUMN deleted_at DATETIME NULL"))
                
                # Add deletion_reason
                print("Adding 'deletion_reason' column...")
                connection.execute(text("ALTER TABLE Properties ADD COLUMN deletion_reason TEXT NULL"))
                
                trans.commit()
                print("✅ Database updated successfully!")
            except Exception as e:
                trans.rollback()
                print(f"⚠️  Error executing SQL (The columns might already exist): {e}")
                
    except Exception as e:
        print(f"❌ Critical Error: {e}")
