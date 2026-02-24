import pymysql
import json

connection = pymysql.connect(
    host='72.61.160.103',
    user='woora_user',
    password='WooraSecurePass2025!',
    database='woora_db',
    cursorclass=pymysql.cursors.DictCursor
)

try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM PropertyTypes")
        property_types = cursor.fetchall()
        
        cursor.execute("SELECT * FROM PropertyAttributes")
        attributes = cursor.fetchall()
        
        cursor.execute("SELECT * FROM AttributeOptions")
        options = cursor.fetchall()
        
        cursor.execute("SELECT * FROM PropertyAttributeScopes")
        scopes = cursor.fetchall()
        
        cursor.execute("SELECT id, property_type_id, attributes FROM Properties WHERE attributes IS NOT NULL")
        properties = cursor.fetchall()

        with open('db_analysis.log', 'w', encoding='utf-8') as f:
            f.write("=== Property Types ===\n")
            for pt in property_types:
                f.write(f"[{pt['id']}] {pt['name']} - Active: {pt['is_active']}\n")
            
            f.write("\n=== Property Attributes ===\n")
            for attr in attributes:
                f.write(f"[{attr['id']}] {attr['name']} ({attr['data_type']})\n")
                
            f.write("\n=== Attribute Scopes ===\n")
            for scope in scopes:
                f.write(f"Type {scope['property_type_id']} -> Attr {scope['attribute_id']}\n")
                
            f.write(f"\n=== Analyzing {len(properties)} Properties JSON ===\n")
            unique_keys = {}
            for p in properties:
                type_id = p['property_type_id']
                if type_id not in unique_keys:
                    unique_keys[type_id] = {}
                
                try:
                    attrs = p['attributes']
                    if isinstance(attrs, str):
                        attrs = json.loads(attrs)
                        
                    if attrs and isinstance(attrs, dict):
                        for k, v in attrs.items():
                            val_type = type(v).__name__
                            if k not in unique_keys[type_id]:
                                unique_keys[type_id][k] = set()
                            unique_keys[type_id][k].add(val_type)
                except Exception as e:
                    pass
                    
            for typ, keys in unique_keys.items():
                f.write(f"Property Type {typ}:\n")
                for k, v_types in keys.items():
                    f.write(f"  - {k} : {', '.join(list(v_types))}\n")

finally:
    connection.close()

print("Done")
