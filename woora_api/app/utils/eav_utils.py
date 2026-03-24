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
    
    # Clés à ignorer car stockées dans Properties (colonne)
    system_keys = ['price', 'title', 'status', 'description', 'address', 'city', 'latitude', 'longitude', 'jours_visite', 'horaires_visite', 'postal_code', 'property_type_id', 'is_validated', 'created_at', 'updated_at', 'deleted_at']

    # On ne supprime plus tout d'un coup pour éviter la perte de données (Merge/Upsert)
    # PropertyValue.query.filter_by(property_id=property_id).delete() # REMOVED
    
    unique_attrs_processed = set()

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
        if attr_id in unique_attrs_processed:
            continue 
        unique_attrs_processed.add(attr_id)

        # Si la valeur est nulle ou vide, on supprime l'attribut s'il existe
        if val is None or str(val).strip() == '':
            existing_pv = PropertyValue.query.filter_by(property_id=property_id, attribute_id=attr_id).first()
            if existing_pv:
                db.session.delete(existing_pv)
            continue

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
                v_str = str(val)[:255] if val is not None else None
        except Exception:
            continue
            
        if v_str is None and v_int is None and v_bool is None and v_dec is None:
            continue
            
        # --- UPSERT LOGIC ---
        existing_pv = PropertyValue.query.filter_by(property_id=property_id, attribute_id=attr_id).first()
        
        if existing_pv:
            existing_pv.value_string = v_str
            existing_pv.value_integer = v_int
            existing_pv.value_boolean = v_bool
            existing_pv.value_decimal = v_dec
        else:
            new_pv = PropertyValue(
                property_id=property_id,
                attribute_id=attr_id,
                value_string=v_str,
                value_integer=v_int,
                value_boolean=v_bool,
                value_decimal=v_dec
            )
            db.session.add(new_pv)
    
    db.session.flush() # Appliquer dans la transaction courante sans commiter (ça sera commité par la Route parent)
