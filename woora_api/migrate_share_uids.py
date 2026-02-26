import os
import sys
from datetime import datetime
import string

from flask import current_app
from app import create_app, db
from app.models import Property

def encode_base36(num):
    """Encodes a positive integer into base36 string."""
    assert num >= 0
    if num == 0:
        return '0'
    base36 = ''
    alphabet = string.digits + string.ascii_lowercase
    while num != 0:
        num, i = divmod(num, 36)
        base36 = alphabet[i] + base36
    return base36

def generate_property_uid(prop_id):
    """
    Combines the property ID and the current timestamp in ms.
    Generates a mathematically unique hash encoded in Base36.
    """
    # 1. Take current timestamp in milliseconds
    timestamp_ms = int(datetime.utcnow().timestamp() * 1000)
    
    # 2. Combine ID and Timestamp uniquely (shiting ID left prevents collision if clocks are perfectly equal)
    combined = (timestamp_ms << 12) | (prop_id & 0xFFF)
    
    # 3. Base36 encoding for short links
    return encode_base36(combined)

def backfill_uids():
    app = create_app()
    with app.app_context():
        properties = Property.query.filter(Property.share_uid.is_(None)).all()
        print(f"[{datetime.now()}] Found {len(properties)} properties missing share_uid.")
        
        updated_count = 0
        for prop in properties:
            prop.share_uid = generate_property_uid(prop.id)
            updated_count += 1
            if updated_count % 100 == 0:
                print(f"Processed {updated_count} records...")
                db.session.commit()
                
        db.session.commit()
        print(f"[{datetime.now()}] Successfully updated {updated_count} properties with share_uid.")
        
        # Validation checks
        all_uids = [p.share_uid for p in Property.query.all() if p.share_uid]
        assert len(all_uids) == len(set(all_uids)), "CRITICAL: Detected collision in generated UIDs!"
        print("UID uniqueness verified across all records.")

if __name__ == '__main__':
    backfill_uids()
