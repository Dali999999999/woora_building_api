from app import db
from app.models import Property, PropertyRequest, PropertyRequestMatch, User
from app.utils.email_utils import send_alert_match_email
from flask import current_app
import json
import re

def _clean_text(s):
    if not s:
        return ""
    return re.sub(r'\s+', ' ', str(s).strip().lower())

def calculate_match_score(prop, req):
    """
    Calculates the matching score between a property and a request.
    Returns (score, total_criteria, matched_criteria, is_mandatory_failed)
    """
    total_criteria = 0
    matched_criteria = 0

    # 1. Verification: Type match (Obligatoire)
    if prop.property_type_id != req.property_type_id:
        return 0, 1, 0, True

    # 2. MATCHING STATUS / TRANSACTION TYPE (Obligatoire si spécifié)
    if req.preferred_status:
        total_criteria += 1
        req_status = _clean_text(req.preferred_status)
        prop_status = _clean_text(prop.status)
        if prop_status == req_status or req_status in prop_status:
            matched_criteria += 1
        else:
            return 0, total_criteria, matched_criteria, True

    # 3. Verification Ville & Quartier (Obligatoire si spécifiée)
    if req.city and str(req.city).strip():
        total_criteria += 1
        req_city = _clean_text(req.city)
        prop_city = _clean_text(prop.city)
        prop_address = _clean_text(prop.address)

        # Vérification souple :
        # - req_city dans prop_city ou inversement
        # - req_city dans prop_address ou inversement
        # - un mot-clé significatif (>= 3 lettres) en commun
        city_matched = False
        if req_city in prop_city or prop_city in req_city:
            city_matched = True
        elif req_city in prop_address or prop_address in req_city:
            city_matched = True
        else:
            req_words = [w for w in re.split(r'[\s,;/]+', req_city) if len(w) >= 3 and w not in ['rue', 'avenue', 'boulevard', 'pres', 'près', 'face']]
            prop_text = f"{prop_city} {prop_address}"
            if any(w in prop_text for w in req_words):
                city_matched = True

        if city_matched:
            matched_criteria += 1
        else:
            return 0, total_criteria, matched_criteria, True
    
    # 4. Verification Prix / Budget (Obligatoire si spécifié avec tolérance de 10%)
    req_min = None
    req_max = None
    if req.min_price is not None:
        try:
            req_min = float(str(req.min_price).replace(' ', '').replace(',', '.'))
        except (ValueError, TypeError):
            req_min = None

    if req.max_price is not None:
        try:
            req_max = float(str(req.max_price).replace(' ', '').replace(',', '.'))
        except (ValueError, TypeError):
            req_max = None

    if req_min is not None or req_max is not None:
        total_criteria += 1
        prop_price = None
        if prop.price is not None:
            try:
                prop_price = float(str(prop.price).replace(' ', '').replace(',', '.'))
            except (ValueError, TypeError):
                prop_price = None

        if prop_price is None and prop.attributes and isinstance(prop.attributes, dict):
            for pk in ['price', 'prix', 'montant', 'loyer']:
                if pk in prop.attributes and prop.attributes[pk] is not None:
                    try:
                        prop_price = float(str(prop.attributes[pk]).replace(' ', '').replace(',', '.'))
                        break
                    except (ValueError, TypeError):
                        pass

        if prop_price is not None:
            min_bound = (req_min * 0.90) if req_min is not None else 0
            max_bound = (req_max * 1.10) if req_max is not None else float('inf')

            if min_bound <= prop_price <= max_bound:
                is_strict = True
                if req_min is not None and prop_price < req_min:
                    is_strict = False
                if req_max is not None and prop_price > req_max:
                    is_strict = False
                
                matched_criteria += 1 if is_strict else 0.8
            else:
                return 0, total_criteria, matched_criteria, True
        else:
            return 0, total_criteria, matched_criteria, True

    # 5. Vérification des Attributs Dynamiques
    try:
        request_details = json.loads(req.request_details) if req.request_details else {}
    except (json.JSONDecodeError, TypeError):
        request_details = {}
        
    prop_attributes = {}
    for pv in prop.property_values:
        attr_name = pv.attribute.name if pv.attribute else None
        if not attr_name:
            continue
        clean_attr_name = _clean_text(attr_name)
        if pv.value_boolean is not None:
            prop_attributes[clean_attr_name] = pv.value_boolean
        elif pv.value_integer is not None:
            prop_attributes[clean_attr_name] = pv.value_integer
        elif pv.value_decimal is not None:
            try:
                prop_attributes[clean_attr_name] = float(pv.value_decimal)
            except (ValueError, TypeError):
                pass
        elif pv.value_string is not None:
            prop_attributes[clean_attr_name] = pv.value_string

    if prop.attributes and isinstance(prop.attributes, dict):
        for k, v in prop.attributes.items():
            ck = _clean_text(k)
            if ck not in prop_attributes and v is not None:
                prop_attributes[ck] = v

    ignored_dynamic_keys = [
        'city', 'ville', 'min_price', 'max_price', 'prix', 'price', 'budget',
        'status', 'preferred_status', 'latitude', 'longitude', 'country', 'pays',
        'disponibilités', 'jours_visite', 'horaires_visite', 'date_disponibilite',
        'notes_disponibilite', 'description', 'descriptions', 'title', 'titre', 'adresse', 'address'
    ]

    for key, req_val in request_details.items():
        clean_k = _clean_text(key)
        if clean_k in ignored_dynamic_keys or req_val is None or str(req_val).strip() in ['', 'Indifférent', 'indifferent']:
            continue
            
        total_criteria += 1
        prop_val = prop_attributes.get(clean_k)
        
        if prop_val is not None:
            if isinstance(req_val, bool) or str(req_val).lower() in ['true', 'false', 'oui', 'non']:
                req_b = req_val if isinstance(req_val, bool) else (str(req_val).lower() in ['true', 'oui'])
                prop_b = prop_val if isinstance(prop_val, bool) else (str(prop_val).lower() in ['true', 'oui'])
                if req_b == prop_b:
                    matched_criteria += 1
            elif isinstance(req_val, (int, float)) or (isinstance(req_val, str) and req_val.isdigit()):
                try:
                    rv_num = float(req_val)
                    pv_num = float(prop_val)
                    if pv_num >= rv_num:
                        matched_criteria += 1
                except (ValueError, TypeError):
                    if _clean_text(req_val) == _clean_text(prop_val):
                        matched_criteria += 1
            else:
                req_s = _clean_text(req_val)
                prop_s = _clean_text(prop_val)
                if req_s == prop_s or req_s in prop_s or prop_s in req_s:
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
            
            # Seuil de correspondance assoupli à 50%
            if not failed and score >= 0.5:
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

        validated_properties = Property.query.filter_by(
            property_type_id=req.property_type_id,
            is_validated=True
        ).all()

        matches_created = 0
        for prop in validated_properties:
            score, total, matched, failed = calculate_match_score(prop, req)
            
            # Seuil de correspondance assoupli à 50%
            if not failed and score >= 0.5:
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
        current_app.logger.error(f"Error in find_matches_for_request: {e}", exc_info=True)
