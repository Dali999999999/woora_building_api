from app import db
from app.models import Property, PropertyRequest, PropertyRequestMatch, User
from app.utils.email_utils import send_alert_match_email
from flask import current_app
import json

def calculate_match_score(prop, req):
    """
    Calculates the matching score between a property and a request.
    Returns (score, total_criteria, matched_criteria, is_mandatory_failed)
    """
    total_criteria = 0
    matched_criteria = 0
    is_mandatory_failed = False

    # 1. Verification: Type match (Pre-filtered usually, but kept for robustness)
    if prop.property_type_id != req.property_type_id:
        return 0, 1, 0, True

    # 2. MATCHING STATUS (IMPORTANT)
    # The property status (for_sale, for_rent, etc.) must match the request's preferred status if specified.
    if req.preferred_status:
        total_criteria += 1
        if prop.status == req.preferred_status:
            matched_criteria += 1
        else:
            is_mandatory_failed = True
            return 0, total_criteria, matched_criteria, True

    # 3. Verification Ville (Obligatoire si spécifiée)
    if req.city:
        total_criteria += 1
        if prop.city and req.city.lower() in prop.city.lower():
            matched_criteria += 1
        else:
            is_mandatory_failed = True
            return 0, total_criteria, matched_criteria, True
    
    # 4. Verification Prix (Obligatoire si spécifié)
    if req.min_price or req.max_price:
        total_criteria += 1
        price_match = True
        if prop.price:
            if req.min_price and prop.price < req.min_price:
                price_match = False
            if req.max_price and prop.price > req.max_price:
                price_match = False
        else:
            price_match = False # Si la requête a un prix mais le bien n'en a pas
        
        if price_match:
            matched_criteria += 1
        else:
            is_mandatory_failed = True
            return 0, total_criteria, matched_criteria, True

    # 5. Vérification des Attributs Dynamiques (80% rule applies here)
    try:
        request_details = json.loads(req.request_details) if req.request_details else {}
    except json.JSONDecodeError:
        request_details = {}
        
    prop_attributes = {}
    for pv in prop.property_values:
        attr_name = pv.attribute.name if pv.attribute else None
        if not attr_name:
            continue
        if pv.value_boolean is not None:
            prop_attributes[attr_name.lower()] = pv.value_boolean
        elif pv.value_integer is not None:
            prop_attributes[attr_name.lower()] = pv.value_integer
        elif pv.value_decimal is not None:
            prop_attributes[attr_name.lower()] = float(pv.value_decimal)
        elif pv.value_string is not None:
            prop_attributes[attr_name.lower()] = pv.value_string
    
    for key, req_val in request_details.items():
        # Skip criteria already handled at top level
        if key.lower() in ['city', 'min_price', 'max_price', 'status', 'preferred_status'] or req_val is None or str(req_val).strip() == '':
            continue
            
        total_criteria += 1
        # On cherche la correspondance dans les attributs du bien
        prop_val = prop_attributes.get(key.lower())
        
        if prop_val is not None:
            if str(req_val).lower() == str(prop_val).lower(): # Match exact texte
                matched_criteria += 1
            elif isinstance(req_val, (int, float)) and isinstance(prop_val, (int, float)):
                if req_val == prop_val: # Match exact nombre
                    matched_criteria += 1
    
    score = (matched_criteria / total_criteria) if total_criteria > 0 else 1.0
    return score, total_criteria, matched_criteria, False

def find_matches_for_property(property_id):
    """
    Finds and records matches for a given property against active PropertyRequests.
    Triggered when a property is validated by Admin.
    """
    try:
        prop = Property.query.get(property_id)
        if not prop:
            return

        # SAFETY: Only validated properties should trigger alerts
        if not prop.is_validated:
            current_app.logger.warning(f"Matching Engine: Skipping unvalidated property {property_id}")
            return

        matching_requests = PropertyRequest.query.filter(
            PropertyRequest.property_type_id == prop.property_type_id,
            PropertyRequest.status.in_(['new', 'in_progress', 'contacted'])
        ).all()

        matches_created = 0
        for req in matching_requests:
            score, total, matched, failed = calculate_match_score(prop, req)
            
            if not failed and score >= 0.8:
                # Check for existing match
                existing_match = PropertyRequestMatch.query.filter_by(
                    property_request_id=req.id,
                    property_id=prop.id
                ).first()

                if not existing_match:
                    db.session.add(PropertyRequestMatch(property_request_id=req.id, property_id=prop.id))
                    matches_created += 1
                    seeker = User.query.get(req.customer_id)
                    if seeker:
                        send_alert_match_email(seeker.email, seeker.first_name, prop.title, prop.id)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in find_matches_for_property: {e}", exc_info=True)

def find_matches_for_request(request_id):
    """
    Finds and records matches for a new PropertyRequest against existing VALIDATED properties.
    Triggered when a seeker creates a new alert.
    """
    try:
        req = PropertyRequest.query.get(request_id)
        if not req:
            return

        # Look for validated properties of the same type
        validated_properties = Property.query.filter_by(
            property_type_id=req.property_type_id,
            is_validated=True
        ).all()

        matches_created = 0
        for prop in validated_properties:
            score, total, matched, failed = calculate_match_score(prop, req)
            
            if not failed and score >= 0.8:
                existing_match = PropertyRequestMatch.query.filter_by(
                    property_request_id=req.id,
                    property_id=prop.id
                ).first()

                if not existing_match:
                    db.session.add(PropertyRequestMatch(property_request_id=req.id, property_id=prop.id))
                    matches_created += 1
                    # Notification optionnelle ici ? Le user vient de créer l'alerte. 
                    # On enverra quand même un mail pour confirmer.
                    seeker = User.query.get(req.customer_id)
                    if seeker:
                        send_alert_match_email(seeker.email, seeker.first_name, prop.title, prop.id)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in find_matches_for_request: {e}", exc_info=True)
