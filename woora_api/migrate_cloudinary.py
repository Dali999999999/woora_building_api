import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
load_dotenv() # Charger le fichier .env avant tout le reste

from app import create_app, db
from app.models import PropertyImage, User

# CRÉDENTIALS DE LA CLIENTE
NEW_CLOUD_NAME = "dminotqao"
NEW_API_KEY = "183296265123124"
NEW_API_SECRET = "FUpmkucAjKbVXsCPZFHWej2OpaQ"

def migrate_images():
    app = create_app()
    with app.app_context():
        # Configuration Cloudinary pour le NOUVEAU compte
        cloudinary.config(
            cloud_name=NEW_CLOUD_NAME,
            api_key=NEW_API_KEY,
            api_secret=NEW_API_SECRET,
            secure=True
        )

        print(f"🚀 Démarrage de la migration vers le compte : {NEW_CLOUD_NAME}")

        # 1. Migration des images des propriétés
        property_images = PropertyImage.query.all()
        print(f"🖼️  Traitement de {len(property_images)} images de propriétés...")
        
        for img in property_images:
            if not img.image_url or NEW_CLOUD_NAME in img.image_url:
                continue # Déjà migré ou vide
            
            try:
                print(f"  -> Migration image ID {img.id}: {img.image_url}")
                # Upload vers le nouveau compte en utilisant l'URL actuelle
                # On garde le même dossier "woora_uploads"
                result = cloudinary.uploader.upload(img.image_url, folder="woora_uploads")
                new_url = result.get('secure_url')
                
                if new_url:
                    img.image_url = new_url
                    db.session.commit()
                    print(f"  ✅ Succès : {new_url}")
            except Exception as e:
                print(f"  ❌ Erreur sur {img.id}: {e}")
                db.session.rollback()

        # 2. Migration des photos de profil
        users = User.query.filter(User.profile_picture_url.isnot(None)).all()
        print(f"👤 Traitement de {len(users)} photos de profil...")
        
        for user in users:
            if not user.profile_picture_url or NEW_CLOUD_NAME in user.profile_picture_url:
                continue
            
            try:
                print(f"  -> Migration profil User {user.id}: {user.profile_picture_url}")
                result = cloudinary.uploader.upload(user.profile_picture_url, folder="woora_profile_pictures")
                new_url = result.get('secure_url')
                
                if new_url:
                    user.profile_picture_url = new_url
                    db.session.commit()
                    print(f"  ✅ Succès : {new_url}")
            except Exception as e:
                print(f"  ❌ Erreur sur User {user.id}: {e}")
                db.session.rollback()

        print("\n✨ Migration terminée !")

if __name__ == "__main__":
    migrate_images()
