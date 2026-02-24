from app import db
from datetime import datetime

# ===================================================================
# MODÈLES DE BASE (UTILISATEURS, PARAMÈTRES)
# ===================================================================

class User(db.Model):
    __tablename__ = 'Users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(191), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    role = db.Column(db.Enum('owner', 'agent', 'customer', 'admin'), nullable=False)
    wallet_balance = db.Column(db.Numeric(10, 2), default=0.00)
    visit_passes = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    profile_picture_url = db.Column(db.String(255), nullable=True)
    profession = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    
    # Suspension logic
    is_suspended = db.Column(db.Boolean, default=False, nullable=False)
    suspension_reason = db.Column(db.Text, nullable=True)
    
    # Soft Delete
    deleted_at = db.Column(db.DateTime, nullable=True)
    deletion_reason = db.Column(db.Text, nullable=True)

    # Verification logic
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code = db.Column(db.String(10), nullable=True)
    verification_code_expires = db.Column(db.DateTime, nullable=True)

    # Password Reset Logic (Stored in DB for Multi-Worker Support)
    reset_password_token = db.Column(db.String(10), nullable=True) # Le code OTP
    reset_password_expires = db.Column(db.DateTime, nullable=True)

    # Relations (si un utilisateur est supprimé, toutes ses données associées le sont aussi)
    properties = db.relationship('Property', back_populates='owner', foreign_keys='Property.owner_id', cascade="all, delete-orphan")
    created_properties = db.relationship('Property', foreign_keys='Property.agent_id')
    property_attributes = db.relationship('PropertyAttribute', back_populates='user', cascade="all, delete-orphan")
    referrals = db.relationship('Referral', back_populates='agent', cascade="all, delete-orphan")
    visit_requests = db.relationship('VisitRequest', back_populates='customer', cascade="all, delete-orphan")
    property_requests = db.relationship('PropertyRequest', back_populates='customer', foreign_keys='PropertyRequest.customer_id', cascade="all, delete-orphan")
    commissions_earned = db.relationship('Commission', back_populates='agent', cascade="all, delete-orphan")
    transactions = db.relationship('Transaction', back_populates='user', cascade="all, delete-orphan")
    payout_requests = db.relationship('PayoutRequest', back_populates='agent', cascade="all, delete-orphan")
    favorites = db.relationship('UserFavorite', back_populates='user', cascade="all, delete-orphan")
    reviews_received = db.relationship('AgentReview', foreign_keys='AgentReview.agent_id', back_populates='agent', cascade="all, delete-orphan")
    reviews_given = db.relationship('AgentReview', foreign_keys='AgentReview.customer_id', back_populates='customer', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<User {self.email}>'

    def to_dict(self):
        return {
            'id': self.id, 'email': self.email, 'first_name': self.first_name,
            'last_name': self.last_name, 'phone_number': self.phone_number, 'role': self.role,
            'wallet_balance': float(self.wallet_balance) if self.wallet_balance is not None else None,
            'visit_passes': self.visit_passes, 'profile_picture_url': self.profile_picture_url,
            'profession': self.profession, 'address': self.address, 'city': self.city,
            'country': self.country, 'bio': self.bio,
            'is_verified': self.is_verified,
            'is_suspended': self.is_suspended, 'suspension_reason': self.suspension_reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class AppSetting(db.Model):
    __tablename__ = 'AppSettings'
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    data_type = db.Column(db.Enum('integer', 'decimal', 'string', 'boolean'), nullable=False, default='string')
    is_editable_by_admin = db.Column(db.Boolean, nullable=False, default=True)

class ServiceFee(db.Model):
    __tablename__ = 'ServiceFees'
    id = db.Column(db.Integer, primary_key=True)
    service_key = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    applicable_to_role = db.Column(db.Enum('owner', 'agent', 'customer'), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    transactions = db.relationship('Transaction', back_populates='service_fee')

# ===================================================================
# MODÈLES LIÉS AUX BIENS IMMOBILIERS (PROPERTIES)
# ===================================================================

class PropertyType(db.Model):
    __tablename__ = 'PropertyTypes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    
    properties = db.relationship('Property', back_populates='property_type')
    attribute_scopes = db.relationship('PropertyAttributeScope', back_populates='property_type', cascade="all, delete-orphan")
    property_requests = db.relationship('PropertyRequest', back_populates='property_type')

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'description': self.description, 'is_active': self.is_active}

class PropertyAttribute(db.Model):
    __tablename__ = 'PropertyAttributes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    data_type = db.Column(db.Enum('integer', 'boolean', 'string', 'decimal', 'enum'), nullable=False)
    is_filterable = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('Users.id'))
    
    user = db.relationship('User', back_populates='property_attributes')
    options = db.relationship('AttributeOption', back_populates='attribute', cascade="all, delete-orphan")
    scopes = db.relationship('PropertyAttributeScope', back_populates='attribute', cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'data_type': self.data_type,
            'is_filterable': self.is_filterable, 'created_by': self.created_by,
            'options': [option.to_dict() for option in self.options] if self.data_type == 'enum' else []
        }

class AttributeOption(db.Model):
    __tablename__ = 'AttributeOptions'
    id = db.Column(db.Integer, primary_key=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('PropertyAttributes.id', ondelete='CASCADE'), nullable=False)
    option_value = db.Column(db.String(100), nullable=False)
    attribute = db.relationship('PropertyAttribute', back_populates='options')
    
    def to_dict(self):
        return {'id': self.id, 'attribute_id': self.attribute_id, 'option_value': self.option_value}

class PropertyValue(db.Model):
    __tablename__ = 'PropertyValues'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    attribute_id = db.Column(db.Integer, db.ForeignKey('PropertyAttributes.id', ondelete='CASCADE'), nullable=False)
    value_string = db.Column(db.String(255), nullable=True)
    value_integer = db.Column(db.Integer, nullable=True)
    value_boolean = db.Column(db.Boolean, nullable=True)
    value_decimal = db.Column(db.Numeric(12, 2), nullable=True)

    property = db.relationship('Property', back_populates='property_values', foreign_keys=[property_id])
    attribute = db.relationship('PropertyAttribute')

class PropertyAttributeScope(db.Model):
    __tablename__ = 'PropertyAttributeScopes'
    attribute_id = db.Column(db.Integer, db.ForeignKey('PropertyAttributes.id', ondelete='CASCADE'), primary_key=True)
    property_type_id = db.Column(db.Integer, db.ForeignKey('PropertyTypes.id', ondelete='CASCADE'), primary_key=True)
    
    attribute = db.relationship('PropertyAttribute', back_populates='scopes')
    property_type = db.relationship('PropertyType', back_populates='attribute_scopes')

class PropertyStatus(db.Model):
    __tablename__ = 'PropertyStatuses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    color = db.Column(db.String(20), default='#000000')
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'description': self.description
        }

class Property(db.Model):
    __tablename__ = 'Properties'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='SET NULL'), nullable=True)  # Agent qui a ajouté le bien
    
    # --- AJOUT NOUVEAU CHAMP : BUYER_ID ---
    # Permet de savoir QUI a acheté ou loué le bien (historique des transactions)
    buyer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='SET NULL'), nullable=True)

    property_type_id = db.Column(db.Integer, db.ForeignKey('PropertyTypes.id', ondelete='RESTRICT'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # --- MODIFICATION STATUT DYNAMIQUE ---
    # Ancien champ (optionnel de le garder ou le supprimer, ici on le garde en compatibilité mais non utilisé)
    status = db.Column(db.String(50), nullable=True, default='for_sale') 
    
    # Nouveau champ FK
    status_id = db.Column(db.Integer, db.ForeignKey('PropertyStatuses.id'), nullable=True)
    property_status = db.relationship('PropertyStatus')
    
    price = db.Column(db.Numeric(12, 2), nullable=False)
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    latitude = db.Column(db.Numeric(9, 6))
    longitude = db.Column(db.Numeric(9, 6))
    attributes = db.Column(db.JSON)
    # Soft Delete for Property
    deleted_at = db.Column(db.DateTime, nullable=True)
    deletion_reason = db.Column(db.Text, nullable=True)

    # INDEXES POUR LA PERFORMANCE
    __table_args__ = (
        db.Index('idx_property_status', 'status'),
        db.Index('idx_property_price', 'price'),
        db.Index('idx_property_city', 'city'),
        db.Index('idx_property_type', 'property_type_id'),
    )

    is_validated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    owner = db.relationship('User', back_populates='properties', foreign_keys=[owner_id])
    agent = db.relationship('User', back_populates='created_properties', foreign_keys=[agent_id])
    buyer = db.relationship('User', foreign_keys=[buyer_id]) # Relation vers l'acheteur
    property_type = db.relationship('PropertyType', back_populates='properties')

    # Relations avec suppression en cascade
    images = db.relationship('PropertyImage', back_populates='property', cascade="all, delete-orphan")
    property_values = db.relationship('PropertyValue', back_populates='property', cascade="all, delete-orphan")
    favorited_by = db.relationship('UserFavorite', back_populates='property', cascade="all, delete-orphan")
    referrals_received = db.relationship('Referral', back_populates='property', cascade="all, delete-orphan")
    visit_requests_received = db.relationship('VisitRequest', back_populates='property', cascade="all, delete-orphan")
    commissions_paid = db.relationship('Commission', back_populates='property', cascade="all, delete-orphan")

    def to_dict(self):
        # Récupérer l'objet statut lié
        status_data = self.property_status.to_dict() if self.property_status else {
            'id': 0, 'name': 'Statut Inconnu', 'color': '#808080'
        }
        
        base_data = {
            'id': self.id, 'owner_id': self.owner_id, 'agent_id': self.agent_id, 
            'buyer_id': self.buyer_id, # Inclure l'ID de l'acheteur
            'property_type_id': self.property_type_id,
            'title': self.title, 'description': self.description, 
            'status': status_data, # Renvoie maintenant un OBJET complet {id, name, color}
            'price': float(self.price) if self.price is not None else None,
            'address': self.address, 'city': self.city, 'postal_code': self.postal_code,
            'latitude': float(self.latitude) if self.latitude is not None else None,
            'longitude': float(self.longitude) if self.longitude is not None else None,
            'is_validated': self.is_validated,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # Build attributes dynamically from EAV PropertyValues table
        attributes_dict = {}
        for pv in self.property_values:
            attr_name = pv.attribute.name if pv.attribute else None
            if not attr_name:
                continue
                
            if pv.value_boolean is not None:
                attributes_dict[attr_name] = pv.value_boolean
            elif pv.value_integer is not None:
                attributes_dict[attr_name] = pv.value_integer
            elif pv.value_decimal is not None:
                attributes_dict[attr_name] = float(pv.value_decimal)
            elif pv.value_string is not None:
                attributes_dict[attr_name] = pv.value_string

        # Fallback to the old JSON attributes only if EAV is empty for some reason (smooth transition)
        if not attributes_dict and self.attributes:
            attributes_dict = self.attributes.copy()
            
        base_data['attributes'] = attributes_dict
        base_data['image_urls'] = [image.image_url for image in self.images]
        base_data['property_type'] = {'id': self.property_type.id, 'name': self.property_type.name} if self.property_type else None
        
        # Ajouter les informations de l'agent si le bien a été créé par un agent
        if self.agent:
            base_data['created_by_agent'] = {
                'agent_id': self.agent.id,
                'agent_name': f"{self.agent.first_name} {self.agent.last_name}",
                'agent_email': self.agent.email
            }
        
        # Ajouter les informations de l'acheteur s'il existe (Admin only idéalement, mais ici inclus)
        if self.buyer:
             base_data['buyer_details'] = {
                'buyer_id': self.buyer.id,
                'buyer_name': f"{self.buyer.first_name} {self.buyer.last_name}",
                'buyer_email': self.buyer.email
            }
        
        return base_data

class PropertyImage(db.Model):
    __tablename__ = 'PropertyImages'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    
    property = db.relationship('Property', back_populates='images')

class UserFavorite(db.Model):
    __tablename__ = 'user_favorites'
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='favorites')
    user = db.relationship('User', back_populates='favorites')
    property = db.relationship('Property', back_populates='favorited_by')

class AgentReview(db.Model):
    __tablename__ = 'AgentReviews'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    rating = db.Column(db.Integer, nullable=False) # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    agent = db.relationship('User', foreign_keys=[agent_id], back_populates='reviews_received')
    customer = db.relationship('User', foreign_keys=[customer_id], back_populates='reviews_given')

    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'customer_id': self.customer_id,
            'customer_name': f"{self.customer.first_name} {self.customer.last_name}",
            'rating': self.rating,
            'comment': self.comment,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# ===================================================================
# MODÈLES LIÉS AUX INTERACTIONS (VISITES, DEMANDES, PARRAINAGES)
# ===================================================================

class Referral(db.Model):
    __tablename__ = 'Referrals'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    referral_code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('agent_id', 'property_id', name='unique_agent_property'),)
    
    agent = db.relationship('User', back_populates='referrals')
    property = db.relationship('Property', back_populates='referrals_received')
    visit_requests = db.relationship('VisitRequest', back_populates='referral')

class VisitRequest(db.Model):
    __tablename__ = 'VisitRequests'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    referral_id = db.Column(db.Integer, db.ForeignKey('Referrals.id', ondelete='SET NULL'))
    requested_datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum('pending', 'confirmed', 'accepted', 'rejected', 'completed'), nullable=False, default='pending')
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    customer = db.relationship('User', back_populates='visit_requests')
    property = db.relationship('Property', back_populates='visit_requests_received')
    referral = db.relationship('Referral', back_populates='visit_requests')

    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'property_id': self.property_id,
            'referral_id': self.referral_id,
            'requested_datetime': self.requested_datetime.isoformat() if self.requested_datetime else None,
            'status': self.status,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'customer': self.customer.to_dict() if self.customer else None,
            'property': self.property.to_dict() if self.property else None,
            'referral': {
                'id': self.referral.id,
                'code': self.referral.referral_code
            } if self.referral else None
        }

class PropertyRequestMatch(db.Model):
    __tablename__ = 'PropertyRequestMatches'
    id = db.Column(db.Integer, primary_key=True)
    property_request_id = db.Column(db.Integer, db.ForeignKey('PropertyRequests.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    property_request = db.relationship('PropertyRequest', back_populates='matches')
    property = db.relationship('Property')

class PropertyRequest(db.Model):
    __tablename__ = 'PropertyRequests'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_type_id = db.Column(db.Integer, db.ForeignKey('PropertyTypes.id', ondelete='SET NULL'))
    request_details = db.Column(db.Text)
    city = db.Column(db.String(100))
    min_price = db.Column(db.Numeric(12, 2))
    max_price = db.Column(db.Numeric(12, 2))
    status = db.Column(db.Enum('new', 'in_progress', 'contacted', 'closed'), nullable=False, default='new')
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Soft Delete (Archivage)
    archived_at = db.Column(db.DateTime, nullable=True)
    archived_by = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='SET NULL'), nullable=True)
    
    customer = db.relationship('User', back_populates='property_requests', foreign_keys=[customer_id])
    property_type = db.relationship('PropertyType', back_populates='property_requests')
    matches = db.relationship('PropertyRequestMatch', back_populates='property_request', cascade="all, delete-orphan", lazy='dynamic')

    def to_dict(self):
        matches_count = self.matches.count() if self.id else 0
        latest_matches = []
        if self.id:
            # Fetch last 5 matches for display
            latest_matches_objs = self.matches.order_by(PropertyRequestMatch.created_at.desc()).limit(5).all()
            for match in latest_matches_objs:
                if match.property:
                    latest_matches.append({
                        'id': match.property.id,
                        'title': match.property.title,
                        'price': float(match.property.price) if match.property.price else 0,
                        'city': match.property.city,
                        'image_url': match.property.images[0].image_url if match.property.images else None,
                        'is_read': match.is_read
                    })

        return {
            'id': self.id, 'customer_id': self.customer_id, 'request_details': self.request_details,
            'city': self.city, 'property_type_id': self.property_type_id,
            'property_type_name': self.property_type.name if self.property_type else "Tous types",
            'min_price': float(self.min_price) if self.min_price is not None else None,
            'max_price': float(self.max_price) if self.max_price is not None else None,
            'status': self.status, 
            'admin_notes': self.admin_notes,
            'admin_response': self.admin_notes,  # Alias pour l'app mobile
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'archived_at': self.archived_at.isoformat() if self.archived_at else None,
            'archived_by': self.archived_by,
            'matches_count': matches_count,
            'matches': latest_matches,
            'customer': {
                'id': self.customer.id,
                'first_name': self.customer.first_name,
                'last_name': self.customer.last_name,
                'email': self.customer.email,
                'phone_number': self.customer.phone_number,
                'profile_image_url': self.customer.profile_picture_url
            } if self.customer else None
        }

# ===================================================================
# MODÈLES FINANCIERS (TRANSACTIONS, COMMISSIONS)
# ===================================================================

class Commission(db.Model):
    __tablename__ = 'Commissions'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum('pending', 'paid'), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    agent = db.relationship('User', back_populates='commissions_earned')
    property = db.relationship('Property', back_populates='commissions_paid')

class Transaction(db.Model):
    __tablename__ = 'Transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    service_fee_id = db.Column(db.Integer, db.ForeignKey('ServiceFees.id', ondelete='SET NULL'))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    type = db.Column(db.Enum('deposit', 'withdrawal', 'payment', 'commission_payout'), nullable=False)
    description = db.Column(db.String(255))
    related_entity_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='transactions')
    service_fee = db.relationship('ServiceFee', back_populates='transactions')

class PayoutRequest(db.Model):
    __tablename__ = 'PayoutRequests'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    requested_amount = db.Column(db.Numeric(10, 2), nullable=False)
    actual_amount = db.Column(db.Numeric(10, 2), nullable=True)
    fedapay_transaction_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.Enum('pending', 'processing', 'completed', 'failed', 'cancelled'), nullable=False, default='pending')
    payment_method = db.Column(db.String(50), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    agent = db.relationship('User', back_populates='payout_requests')
    
    def to_dict(self):
        return {
            'id': self.id, 'agent_id': self.agent_id,
            'requested_amount': float(self.requested_amount) if self.requested_amount else 0,
            'actual_amount': float(self.actual_amount) if self.actual_amount else None,
            'fedapay_transaction_id': self.fedapay_transaction_id, 'status': self.status,
            'payment_method': self.payment_method, 'phone_number': self.phone_number,
            'admin_notes': self.admin_notes, 'error_message': self.error_message,
            'requested_at': self.requested_at.isoformat() if self.requested_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
