import pymysql
import sys
import time

# Connection string
# woora_user:WooraSecurePass2025!@72.61.160.103:3306/woora_db

def inspect_db():
    output_file = "schema_output.txt"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"Connecting to database...\n")
            
            connection = pymysql.connect(
                host='72.61.160.103',
                user='woora_user',
                password='WooraSecurePass2025!',
                database='woora_db',
                cursorclass=pymysql.cursors.DictCursor
            )
            f.write("Connected!\n")
            
            with connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = [list(row.values())[0] for row in cursor.fetchall()]
                f.write(f"Found {len(tables)} tables.\n")
                
                relevant_tables = [t for t in tables if 'request' in t.lower() or 'alert' in t.lower() or 'match' in t.lower()]
                f.write(f"Relevant tables found: {relevant_tables}\n")
                
                for table_name in relevant_tables:
                    f.write(f"\n--- Schema for {table_name} ---\n")
                    cursor.execute(f"DESCRIBE {table_name}")
                    columns = cursor.fetchall()
                    for column in columns:
                        f.write(f"- {column['Field']} ({column['Type']})\n")
                        
                if 'Properties' in tables:
                    f.write(f"\n--- Schema for Properties (Attributes check) ---\n")
                    cursor.execute("DESCRIBE Properties")
                    columns = cursor.fetchall()
                    for column in columns:
                         if column['Field'] in ['attributes', 'city', 'price', 'property_type_id', 'status', 'is_validated']:
                            f.write(f"- {column['Field']} ({column['Type']})\n")

        print(f"Schema written to {output_file}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

if __name__ == "__main__":
    inspect_db()
