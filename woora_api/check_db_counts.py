import sys
import os
sys.path.append('c:/Users/dalin/Desktop/Project/Woora_building/woora_building_api/woora_api')
from app import create_app, db
from app.models import Property

app = create_app()
with app.app_context():
    print(f"Property.query.count(): {Property.query.count()}")
    properties = Property.query.all()
    print(f"Total properties: {len(properties)}")
    
    # Let's count properties based on is_validated
    validated = len([p for p in properties if p.is_validated])
    not_validated = len([p for p in properties if not p.is_validated])
    print(f"Validated: {validated}, Not Validated: {not_validated}")
