import os
import subprocess
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.models import PropertyImage, User

# CRÉDENTIALS DE LA CLIENTE
NEW_CLOUD_NAME = "dminotqao"
NEW_API_KEY = "183296265123124"
NEW_API_SECRET = "FUpmkucAjKbVXsCPZFHWej2OpaQ"

TEMP_FOLDER = "temp_mega"

def migrate_mega_images():
    app = create_app()
    with app.app_context():
        # Configuration Cloudinary
        cloudinary.config(
            cloud_name=NEW_CLOUD_NAME,
            api_key=NEW_API_KEY,
            api_secret=NEW_API_SECRET,
            secure=True
        )

        if not os.path.exists(TEMP_FOLDER):
            os.makedirs(TEMP_FOLDER)

        print(f"🚀 Migration des images MEGA vers {NEW_CLOUD_NAME}")

        # 1. Propriétés
        mega_images = PropertyImage.query.filter(PropertyImage.image_url.like('%mega%')).all()
        print(f"🖼️  {len(mega_images)} images Mega trouvées dans les propriétés.")

        for img in mega_images:
            try:
                print(f"  -> Traitement ID {img.id}: {img.image_url}")
                
                # Téléchargement via megadl
                # --path spécifie où enregistrer le fichier
                cmd = ["megadl", "--path", TEMP_FOLDER, img.image_url]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"  ❌ Erreur megadl : {result.stderr.strip()}")
                    continue

                # Trouver le fichier téléchargé dans le dossier temp
                files = os.listdir(TEMP_FOLDER)
                if not files:
                    print("  ❌ Fichier non trouvé après téléchargement.")
                    continue
                
                local_file = os.path.join(TEMP_FOLDER, files[0])
                
                # Upload vers Cloudinary
                upload_res = cloudinary.uploader.upload(local_file, folder="woora_uploads")
                new_url = upload_res.get('secure_url')

                if new_url:
                    img.image_url = new_url
                    db.session.commit()
                    print(f"  ✅ Migré : {new_url}")
                
                # Nettoyage du fichier local immédiatement
                os.remove(local_file)

            except Exception as e:
                print(f"  ❌ Erreur critique sur ID {img.id}: {e}")
                db.session.rollback()

        # 2. Profils Utilisateurs
        mega_profiles = User.query.filter(User.profile_picture_url.like('%mega%')).all()
        print(f"👤 {len(mega_profiles)} photos de profil Mega trouvées.")

        for user in mega_profiles:
            try:
                print(f"  -> Traitement User {user.id}: {user.profile_picture_url}")
                
                cmd = ["megadl", "--path", TEMP_FOLDER, user.profile_picture_url]
                subprocess.run(cmd, capture_output=True)
                
                files = os.listdir(TEMP_FOLDER)
                if files:
                    local_file = os.path.join(TEMP_FOLDER, files[0])
                    upload_res = cloudinary.uploader.upload(local_file, folder="woora_profile_pictures")
                    new_url = upload_res.get('secure_url')
                    
                    if new_url:
                        user.profile_picture_url = new_url
                        db.session.commit()
                        print(f"  ✅ Profil migré : {new_url}")
                    
                    os.remove(local_file)

            except Exception as e:
                print(f"  ❌ Erreur User {user.id}: {e}")
                db.session.rollback()

        # Nettoyage final du dossier
        if os.path.exists(TEMP_FOLDER):
            os.removedirs(TEMP_FOLDER)
            
        print("\n✨ Migration MEGA terminée !")

if __name__ == "__main__":
    migrate_mega_images()
