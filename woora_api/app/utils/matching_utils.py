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
            # City check (if specified in request)
            city_valid = True
            if req.city and prop.city:
                # Case-insensitive substring match
                if req.city.lower() not in prop.city.lower():
                    city_valid = False
            
            # Price check
            # Logic: If property has a price, it must fall within user's range (if specified)
            price_valid = True
            if prop.price:
                if req.min_price and prop.price < req.min_price:
                    price_valid = False
                if req.max_price and prop.price > req.max_price:
                    price_valid = False
            
            if city_valid and price_valid:
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
