from app import create_app, db
from sqlalchemy import text

def update_monetary_precision():
    app = create_app()
    with app.app_context():
        print("🚀 Starting database schema update for monetary precision...")
        
        updates = [
            # 1. Properties
            "ALTER TABLE Properties MODIFY COLUMN price DECIMAL(20, 2) NOT NULL",
            
            # 2. PropertyValues (EAV)
            "ALTER TABLE PropertyValues MODIFY COLUMN value_decimal DECIMAL(20, 2)",
            
            # 3. Users (Wallet)
            "ALTER TABLE Users MODIFY COLUMN wallet_balance DECIMAL(20, 2) DEFAULT 0.00",
            
            # 4. Commissions
            "ALTER TABLE Commissions MODIFY COLUMN amount DECIMAL(20, 2) NOT NULL",
            
            # 5. Transactions
            "ALTER TABLE Transactions MODIFY COLUMN amount DECIMAL(20, 2) NOT NULL",
            
            # 6. PayoutRequests
            "ALTER TABLE PayoutRequests MODIFY COLUMN requested_amount DECIMAL(20, 2) NOT NULL",
            "ALTER TABLE PayoutRequests MODIFY COLUMN actual_amount DECIMAL(20, 2)",
            
            # 7. ServiceFees
            "ALTER TABLE ServiceFees MODIFY COLUMN amount DECIMAL(20, 2) NOT NULL",
            
            # Redundancy for previous fixes (just in case)
            "ALTER TABLE Commissions ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE VisitRequests ADD COLUMN IF NOT EXISTS customer_has_unread_update BOOLEAN DEFAULT FALSE NOT NULL"
        ]
        
        for sql in updates:
            try:
                print(f"Executing: {sql}")
                db.session.execute(text(sql))
                db.session.commit()
                print("✅ Success")
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error: {e}")
                
        print("\n✨ Database schema updated successfully!")

if __name__ == "__main__":
    update_monetary_precision()
