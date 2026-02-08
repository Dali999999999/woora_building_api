import pymysql

# Connection string
# woora_user:WooraSecurePass2025!@72.61.160.103:3306/woora_db

def create_table():
    print(f"Connecting to database...")
    try:
        connection = pymysql.connect(
            host='72.61.160.103',
            user='woora_user',
            password='WooraSecurePass2025!',
            database='woora_db',
            cursorclass=pymysql.cursors.DictCursor
        )
        print("Connected!")
        
        with connection.cursor() as cursor:
            # Check if table exists
            cursor.execute("SHOW TABLES LIKE 'PropertyRequestMatches'")
            result = cursor.fetchone()
            
            if result:
                print("Table 'PropertyRequestMatches' already exists.")
            else:
                print("Creating table 'PropertyRequestMatches'...")
                sql = """
                CREATE TABLE PropertyRequestMatches (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    property_request_id INT NOT NULL,
                    property_id INT NOT NULL,
                    is_read BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (property_request_id) REFERENCES PropertyRequests(id) ON DELETE CASCADE,
                    FOREIGN KEY (property_id) REFERENCES Properties(id) ON DELETE CASCADE
                )
                """
                cursor.execute(sql)
                connection.commit()
                print("Table created successfully.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

if __name__ == "__main__":
    create_table()
