import pymysql
import json
import re

db_config = {
    'host': '72.61.160.103',
    'user': 'woora_user',
    'password': 'WooraSecurePass2025!',
    'database': 'woora_db',
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit': True,
    'connect_timeout': 60
}

def clean_key(key):
    k = str(key).replace('.', ' ').strip().lower()
    return re.sub(r'\s+', ' ', k)

def get_normalized_attributes(cursor):
    cursor.execute("SELECT * FROM PropertyAttributes")
    attrs = cursor.fetchall()
    attr_map = {}
    for a in attrs:
        cleaned = clean_key(a['name'])
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

def migrate():
    print("Phase 1: Downloading all data into memory...")
    connection = pymysql.connect(**db_config)
    try:
        with connection.cursor() as cursor:
            # S'assurer que la table existe et est vide
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS PropertyValues (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    property_id INT NOT NULL,
                    attribute_id INT NOT NULL,
                    value_string VARCHAR(255),
                    value_integer INT,
                    value_boolean BOOLEAN,
                    value_decimal DECIMAL(12,2),
                    UNIQUE KEY unique_prop_attr (property_id, attribute_id),
                    FOREIGN KEY (property_id) REFERENCES Properties(id) ON DELETE CASCADE,
                    FOREIGN KEY (attribute_id) REFERENCES PropertyAttributes(id) ON DELETE CASCADE
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)
            cursor.execute("DELETE FROM PropertyValues")
            print("Table PropertyValues purgée.")

            attr_map = get_normalized_attributes(cursor)
            # Requis explicitement
            cursor.execute("SELECT id, attributes FROM Properties WHERE attributes IS NOT NULL AND deleted_at IS NULL")
            all_properties = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return
    finally:
        connection.close()

    print(f"Phase 2: Processing {len(all_properties)} properties locally...")
    insert_payloads = []
    unmapped = set()
    system_keys = ['price', 'title', 'status', 'description', 'address', 'city', 'latitude', 'longitude', 'jours_visite', 'horaires_visite', 'postal_code', 'property_type_id', 'disponibilité', 'date d\'intégration']
    
    unique_prop_attrs = set()

    for row in all_properties:
        prop_id = row['id']
        raw_attrs = row['attributes']

        if isinstance(raw_attrs, str):
            try:
                attrs = json.loads(raw_attrs)
            except:
                continue
        else:
            attrs = raw_attrs

        if not attrs or not isinstance(attrs, dict):
            continue

        for key, val in attrs.items():
            if val is None or val == "":
                continue

            cleaned_k = clean_key(key)
            if cleaned_k in system_keys or cleaned_k.startswith('_'):
                continue

            found_attr = attr_map.get(cleaned_k)
            if not found_attr:
                for ak, av in attr_map.items():
                    if cleaned_k in ak or ak in cleaned_k:
                        found_attr = av
                        break

            if not found_attr:
                unmapped.add(key)
                continue

            attr_id = found_attr['id']
            ident = f"{prop_id}-{attr_id}"
            # Deduplicate inputs per property to satisfy Unique Key
            if ident in unique_prop_attrs:
                continue
            unique_prop_attrs.add(ident)

            d_type = found_attr['data_type']
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

            insert_payloads.append((prop_id, attr_id, v_str, v_int, v_bool, v_dec))

    print(f"Phase 3: Fast writing {len(insert_payloads)} records to database in chunks...")
    connection = pymysql.connect(**db_config)
    try:
        with connection.cursor() as cursor:
            insert_sql = """
                INSERT IGNORE INTO PropertyValues 
                (property_id, attribute_id, value_string, value_integer, value_boolean, value_decimal)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            chunk_size = 500
            for i in range(0, len(insert_payloads), chunk_size):
                chunk = insert_payloads[i:i + chunk_size]
                cursor.executemany(insert_sql, chunk)
                print(f"Inserted chunk {i} to {i+len(chunk)}")
                
            print(f"\nMigration terminée ! {len(insert_payloads)} caractéristiques insérées.")
            
            if unmapped:
                print("\nClés ignorées (Non trouvées dans la base PropertyAttributes ou redondantes) :")
                for u in sorted(unmapped):
                    print(f" - {u}")
    except Exception as e:
        print(f"Erreur d'insertion globale : {e}")
    finally:
        connection.close()

if __name__ == '__main__':
    migrate()
