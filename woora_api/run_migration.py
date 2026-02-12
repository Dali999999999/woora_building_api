
import os
import pymysql
from urllib.parse import urlparse

# Configuration de la base de données (A REMPLACER PAR VOS INFOS SI NON DEFINIES)
# Format: mysql+pymysql://USER:PASSWORD@HOST:PORT/DB_NAME
# D'après votre message: woora_user:WooraSecurePass2025!@72.61.160.103:3306/woora_db

DB_HOST = "72.61.160.103"
DB_USER = "woora_user"
DB_PASS = "WooraSecurePass2025!"
DB_NAME = "woora_db"
DB_PORT = 3306

def run_migration():
    print(f"Connexion à la base de données {DB_NAME} sur {DB_HOST}...")
    
    try:
        connection = pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            port=DB_PORT,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        print("Connexion réussie.")
        
        with connection.cursor() as cursor:
            # 1. Vérifier si la colonne existe déjà pour éviter les erreurs
            print("Vérification de l'existence de la colonne 'buyer_id'...")
            cursor.execute(f"""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = '{DB_NAME}' 
                AND TABLE_NAME = 'Properties' 
                AND COLUMN_NAME = 'buyer_id';
            """)
            result = cursor.fetchone()
            
            if result['COUNT(*)'] > 0:
                print("La colonne 'buyer_id' existe déjà. Aucune action nécessaire.")
            else:
                print("La colonne 'buyer_id' n'existe pas. Ajout en cours...")
                # 2. Ajouter la colonne
                # On ajoute buyer_id comme INT, NULLABLE, et on ajoute la Foreign Key
                alter_query = """
                ALTER TABLE Properties
                ADD COLUMN buyer_id INT NULL DEFAULT NULL,
                ADD CONSTRAINT fk_properties_buyer
                FOREIGN KEY (buyer_id) REFERENCES Users(id)
                ON DELETE SET NULL;
                """
                cursor.execute(alter_query)
                print("Colonne 'buyer_id' et contrainte de clé étrangère ajoutées avec succès.")
            
            connection.commit()
            print("Migration terminée avec succès.")

    except Exception as e:
        print(f"Erreur lors de la migration : {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()
            print("Connexion fermée.")

if __name__ == "__main__":
    run_migration()
