from app import db
from app.models import Property, PropertyRequest, PropertyRequestMatch, User
from app.utils.email_utils import send_alert_match_email
from flask import current_app

def find_matches_for_property(property_id):
    """
    Finds and records matches for a given property against active PropertyRequests.
    Sends email notifications to seekers for new matches.
    """
    try:
        prop = Property.query.get(property_id)
        if not prop:
            current_app.logger.error(f"Property with ID {property_id} not found during matching.")
            return

        # 1. Find potential matching alerts
        # Criteria: Active requests + Type match + (City match OR Price range match logic)
        # Note: We do matching in Python to handle the precise logic, similar to the admin implementation
        matching_requests = PropertyRequest.query.filter(
            PropertyRequest.property_type_id == prop.property_type_id,
            PropertyRequest.status.in_(['new', 'in_progress', 'contacted'])
        ).all()

        current_app.logger.info(f"Matching Engine: Found {len(matching_requests)} potential requests for Property {property_id}")

        matches_created = 0

        for req in matching_requests:
            import json
            
            # --- NOUVEAU : Logique de Matching à 80% ---
            total_criteria = 0
            matched_criteria = 0
            is_mandatory_failed = False
            
            # 1. Vérification Ville (Obligatoire si spécifiée)
            if req.city:
                total_criteria += 1
                if prop.city and req.city.lower() in prop.city.lower():
                    matched_criteria += 1
                else:
                    is_mandatory_failed = True
            
            # 2. Vérification Prix (Obligatoire si spécifié)
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

            # Si un critère obligatoire (Ville ou Prix) a échoué, on passe au bien suivant directement
            if is_mandatory_failed:
                continue
                
            # 3. Vérification des Attributs Dynamiques
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
                if key not in ['city', 'min_price', 'max_price'] and req_val is not None and str(req_val).strip() != '':
                    total_criteria += 1
                    
                    # On cherche la correspondance dans les attributs du bien
                    prop_val = prop_attributes.get(key.lower())
                    
                    # Logique de comparaison flexible (ex: texte, nombre)
                    if prop_val is not None:
                        if str(req_val).lower() == str(prop_val).lower(): # Match exact texte
                            matched_criteria += 1
                        elif isinstance(req_val, (int, float)) and isinstance(prop_val, (int, float)):
                            if req_val == prop_val: # Match exact nombre
                                matched_criteria += 1
            
            # Calcul du score final
            # Si total_criteria est 0, c'est que l'alerte n'avait aucun critère (impossible avec la règle des 50% normalement)
            # Dans ce cas, on match par défaut puisque le type de bien correspond déjà (filtre initial)
            match_score = (matched_criteria / total_criteria) if total_criteria > 0 else 1.0
            
            current_app.logger.debug(f"Matching Property {prop.id} with Request {req.id} - Score: {match_score*100}% ({matched_criteria}/{total_criteria})")

            # Seuil de 80% (0.8)
            if match_score >= 0.8:
                # Check for existing match to avoid duplicates
                existing_match = PropertyRequestMatch.query.filter_by(
                    property_request_id=req.id,
                    property_id=prop.id
                ).first()

                if not existing_match:
                    # Create new match
                    new_match = PropertyRequestMatch(
                        property_request_id=req.id,
                        property_id=prop.id
                    )
                    db.session.add(new_match)
                    matches_created += 1

                    # Send Email Notification
                    seeker = User.query.get(req.customer_id)
                    if seeker:
                        send_alert_match_email(seeker.email, seeker.first_name, prop.title, prop.id)
        
        db.session.commit()
        current_app.logger.info(f"Matching Engine: Created {matches_created} new matches for Property {property_id}")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in find_matches_for_property: {e}", exc_info=True)
