import sys
import os
import argparse

# Ajouter le dossier parent au path pour importer l'app Flask
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from sqlalchemy import text

def run_migration():
    app = create_app()
    with app.app_context():
        print("Vérification de la table PropertyStatuses...")
        inspector = db.inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('PropertyStatuses')]
        
        if 'is_deterministic' not in columns:
            print("Ajout de la colonne 'is_deterministic' à PropertyStatuses...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE PropertyStatuses ADD COLUMN is_deterministic BOOLEAN NOT NULL DEFAULT FALSE"))
                conn.commit()
            print("✅ Colonne 'is_deterministic' ajoutée avec succès.")
        else:
            print("ℹ️ La colonne 'is_deterministic' existe déjà.")

if __name__ == '__main__':
    run_migration()
