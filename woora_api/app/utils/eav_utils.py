import re
from app import db
from app.models import PropertyValue, PropertyAttribute

def clean_key(key):
    k = str(key).replace('.', ' ').strip().lower()
    return re.sub(r'\s+', ' ', k)

def get_normalized_attributes():
    attrs = PropertyAttribute.query.all()
    attr_map = {}
    for a in attrs:
        cleaned = clean_key(a.name)
        attr_map[cleaned] = a
        if cleaned == "surface m2":
            attr_map["surface (m2)"] = a
        if cleaned == "nombre de salle de bain":
            attr_map["nombre de salle de bains"] = a
        if cleaned == "niveau d'étage":
            attr_map["niveau d'étage"] = a
            attr_map["niveau d étage"] = a
        if cleaned == "giillage porte et fenêtre":
            attr_map["grille de protection"] = a
        if cleaned == "cours avant":
            attr_map["cour avant"] = a
    return attr_map

def save_property_eav_values(property_id, dynamic_attributes):
    """
    Parcourt le dictionnaire dynamique (ex: payload Flutter), trouve les PropertyAttributes correspondants,
    et insère/met à jour de manière robuste les lignes dans PropertyValues (modèle EAV).
    """
    if not dynamic_attributes or not isinstance(dynamic_attributes, dict):
        return
        
    attr_map = get_normalized_attributes()
    
    # Liste des clés qu'on sait appartenir directement à la table Properties principale, pas la peine d'en faire du EAV
    system_keys = ['price', 'title', 'status', 'description', 'address', 'city', 'latitude', 'longitude', 'jours_visite', 'horaires_visite', 'postal_code', 'property_type_id']
    
    # Nettoyer les anciennes valeurs EAV pour ce bien (en cas de mise à jour / PUT)
    PropertyValue.query.filter_by(property_id=property_id).delete()
    
    unique_attrs = set()

    for key, val in dynamic_attributes.items():
        if val is None or val == "":
            continue
            
        cleaned_k = clean_key(key)
        if cleaned_k in system_keys or cleaned_k.startswith('_'):
            continue
            
        # Chercher l'attribut officiel
        found_attr = attr_map.get(cleaned_k)
        
        # Fuzzy match si la clé exacte n'y est pas
        if not found_attr:
            for ak, av in attr_map.items():
                if cleaned_k in ak or ak in cleaned_k:
                    found_attr = av
                    break
        
        if not found_attr:
            continue
            
        attr_id = found_attr.id
        if attr_id in unique_attrs:
            continue # Evite le double save de la meme carac si le payload est sale
        unique_attrs.add(attr_id)

        d_type = found_attr.data_type
        v_str, v_int, v_bool, v_dec = None, None, None, None
        
        try:
            if d_type == 'boolean':
                if isinstance(val, bool): v_bool = val
                elif isinstance(val, str): v_bool = val.lower() in ['true', '1', 'oui', 'yes']
                else: v_bool = bool(val)
            elif d_type == 'integer':
                if isinstance(val, int): v_int = val
                elif isinstance(val, str):
                    match = re.search(r'\d+', val)
                    v_int = int(match.group()) if match else None
                else: v_int = int(val)
            elif d_type == 'decimal':
                v_dec = float(val)
            else:
                v_str = str(val)[:255]
        except Exception:
            continue
            
        if v_str is None and v_int is None and v_bool is None and v_dec is None:
            continue
            
        pv = PropertyValue(
            property_id=property_id,
            attribute_id=attr_id,
            value_string=v_str,
            value_integer=v_int,
            value_boolean=v_bool,
            value_decimal=v_dec
        )
        db.session.add(pv)
    
    db.session.flush() # Appliquer dans la transaction courante sans commiter (ça sera commité par la Route parent)
