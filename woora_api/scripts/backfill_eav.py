"""
Script de backfill EAV - Exécuter UNE SEULE FOIS
==================================================
Ce script parcourt tous les biens immobiliers qui ont des données dans la colonne
JSON `attributes` mais qui n'ont PAS (ou peu) de données dans la table `PropertyValues` (EAV).
Il migre ces données vers l'architecture EAV, puis peut afficher un rapport.

Usage:  
    Depuis le dossier woora_api/ :
    python scripts/backfill_eav.py

    Pour réellement appliquer les changements (par défaut: dry-run):
    python scripts/backfill_eav.py --apply
"""

import sys
import os
import argparse

# Ajouter le dossier parent au path pour importer l'app Flask
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import Property, PropertyValue
from app.utils.eav_utils import save_property_eav_values

def run_backfill(apply=False):
    app = create_app()
    
    with app.app_context():
        # Récupérer tous les biens qui ont un JSON attributes non vide
        all_props = Property.query.filter(Property.attributes != None).all()
        
        total = len(all_props)
        migrated = 0
        skipped = 0
        
        print(f"\n{'='*60}")
        print(f"  Biens avec colonne JSON attributes : {total}")
        print(f"  Mode : {'APPLY (écriture réelle)' if apply else 'DRY-RUN (aucun changement)'}")
        print(f"{'='*60}\n")
        
        for prop in all_props:
            if not prop.attributes or not isinstance(prop.attributes, dict):
                skipped += 1
                continue
            
            # Vérifier si ce bien a déjà des données EAV
            existing_eav_count = PropertyValue.query.filter_by(property_id=prop.id).count()
            
            if existing_eav_count > 0:
                print(f"  [SKIP]  Property #{prop.id} '{prop.title[:40]}' - déjà {existing_eav_count} valeurs EAV")
                skipped += 1
                continue
            
            print(f"  [MIGRATE] Property #{prop.id} '{prop.title[:40]}' - {len(prop.attributes)} clés JSON")
            
            if apply:
                try:
                    save_property_eav_values(prop.id, prop.attributes)
                    db.session.commit()
                    migrated += 1
                    print(f"           ✓ Migré avec succès")
                except Exception as e:
                    db.session.rollback()
                    print(f"           ✗ ERREUR: {e}")
            else:
                # Dry run - simuler ce qui serait fait
                migrated += 1
        
        print(f"\n{'='*60}")
        print(f"  Biens migrés (ou à migrer) : {migrated}")
        print(f"  Biens ignorés (EAV déjà présent ou JSON vide) : {skipped}")
        if not apply:
            print(f"\n  ⚠️  C'était un DRY-RUN. Ajoutez --apply pour appliquer réellement.")
        else:
            print(f"\n  ✅  Migration terminée. Vérifiez avec :")
            print(f"      SELECT property_id, COUNT(*) FROM PropertyValues GROUP BY property_id ORDER BY property_id;")
        print(f"{'='*60}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill EAV depuis la colonne JSON attributes')
    parser.add_argument('--apply', action='store_true', help='Appliquer réellement la migration (défaut: dry-run)')
    args = parser.parse_args()
    
    run_backfill(apply=args.apply)
