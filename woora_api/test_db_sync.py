# test_db_sync.py
import sys
import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

from app import create_app, db
from app.models import (
    User, Property, PropertyType, PropertyAttribute, PropertyValue,
    AttributeOption, PropertyAttributeScope, PropertyImage, PropertyStatus,
    VisitRequest, PropertyRequest, PropertyRequestMatch, Referral,
    Commission, PayoutRequest, ServiceFee, Transaction, AgentReview,
    AppSetting
)
from sqlalchemy import inspect

app = create_app()

def test_sqlalchemy_models_against_db():
    print("=" * 65)
    print("🔍 VÉRIFICATION AUTOMATISÉE API <-> BASE DE DONNÉES (WOORA BUILDING)")
    print("=" * 65)
    
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
        except Exception as e:
            print(f"❌ Impossible de se connecter à la base de données: {e}")
            return

        models = [
            User, Property, PropertyType, PropertyAttribute, PropertyValue,
            AttributeOption, PropertyAttributeScope, PropertyImage, PropertyStatus,
            VisitRequest, PropertyRequest, PropertyRequestMatch, Referral,
            Commission, PayoutRequest, ServiceFee, Transaction, AgentReview,
            AppSetting
        ]
        
        total_checks = 0
        passed_checks = 0
        failed_checks = 0
        
        for model in models:
            table_name = model.__tablename__
            print(f"\n📦 Modèle: {model.__name__} ---> Table SQL: '{table_name}'")
            
            if table_name not in existing_tables:
                print(f"   ❌ TABLE MANQUANTE DANS LA DB: '{table_name}'")
                failed_checks += 1
                continue
            
            db_columns = {c['name']: c for c in inspector.get_columns(table_name)}
            mapper = inspect(model)
            
            table_passed = True
            for col_name in mapper.columns.keys():
                total_checks += 1
                if col_name in db_columns:
                    passed_checks += 1
                else:
                    print(f"   ❌ COLONNE MANQUANTE dans la DB: {table_name}.{col_name}")
                    failed_checks += 1
                    table_passed = False
            
            # Test d'exécution de requête SQL réelle (ORM mapping check)
            try:
                count = db.session.query(model).count()
                if table_passed:
                    print(f"   ✅ Synchronisé & Valide ({count} entrée(s) trouvée(s))")
            except Exception as e:
                print(f"   ❌ ERREUR MAPPING REQUÊTE: {e}")
                failed_checks += 1
                db.session.rollback()

        print("\n" + "=" * 65)
        if failed_checks == 0:
            print(f"🎉 SUCCÈS TOTAL: {passed_checks}/{total_checks} colonnes vérifiées et 100% synchronisées !")
            print("L'API Flask et la base de données SQL sont en parfaite harmonie.")
        else:
            print(f"⚠️  RÉSULTAT: {passed_checks} vérifications réussies, {failed_checks} échec(s) détecté(s).")
        print("=" * 65)

if __name__ == '__main__':
    test_sqlalchemy_models_against_db()
