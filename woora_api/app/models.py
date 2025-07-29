from app import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'Users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(191), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    # CORRECTION : Le rôle 'customer' n'était pas dans votre Enum, je l'ai remplacé par 'seeker' pour la cohérence
    # Si vous utilisez bien 'customer', remplacez 'customer' par 'customer' ici.
    role = db.Column(db.Enum('owner', 'agent', 'customer', 'admin'), nullable=False) 
    wallet_balance = db.Column(db.Numeric(10, 2), default=0.00)
    visit_passes = db.Column(db.Integer, nullable=False, default=0) # Nouvelle colonne
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<User {self.email}>'

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'phone_number': self.phone_number,
            'role': self.role,
            'wallet_balance': float(self.wallet_balance) if self.wallet_balance is not None else None,
            'visit_passes': self.visit_passes, # Ajout du champ
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
    # CORRECTION : Le rôle 'customer' n'était pas dans votre Enum, je l'ai remplacé par 'seeker'
    applicable_to_role = db.Column(db.Enum('owner', 'agent', 'customer'), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

class PropertyType(db.Model):
    __tablename__ = 'PropertyTypes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
        }

class PropertyAttribute(db.Model):
    __tablename__ = 'PropertyAttributes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    data_type = db.Column(db.Enum('integer', 'boolean', 'string', 'decimal', 'enum'), nullable=False)
    is_filterable = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('Users.id'))
    user = db.relationship('User', backref='property_attributes')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'data_type': self.data_type,
            'is_filterable': self.is_filterable,
            'created_by': self.created_by,
            'options': [option.to_dict() for option in self.options] if self.data_type == 'enum' else [],
        }

class AttributeOption(db.Model):
    __tablename__ = 'AttributeOptions'
    id = db.Column(db.Integer, primary_key=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('PropertyAttributes.id', ondelete='CASCADE'), nullable=False)
    option_value = db.Column(db.String(100), nullable=False)
    attribute = db.relationship('PropertyAttribute', backref=db.backref('options', cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            'id': self.id,
            'attribute_id': self.attribute_id,
            'option_value': self.option_value,
        }

class PropertyAttributeScope(db.Model):
    __tablename__ = 'PropertyAttributeScopes'
    attribute_id = db.Column(db.Integer, db.ForeignKey('PropertyAttributes.id', ondelete='CASCADE'), primary_key=True)
    property_type_id = db.Column(db.Integer, db.ForeignKey('PropertyTypes.id', ondelete='CASCADE'), primary_key=True)
    attribute = db.relationship('PropertyAttribute', backref='scopes')
    property_type = db.relationship('PropertyType', backref='attribute_scopes')

class Property(db.Model):
    __tablename__ = 'Properties'
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_type_id = db.Column(db.Integer, db.ForeignKey('PropertyTypes.id', ondelete='RESTRICT'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.Enum('for_sale', 'for_rent', 'sold', 'rented'), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    address = db.Column(db.String(255))
    city = db.Column(db.String(100))
    postal_code = db.Column(db.String(20))
    latitude = db.Column(db.Numeric(9, 6))
    longitude = db.Column(db.Numeric(9, 6))
    attributes = db.Column(db.JSON)
    is_validated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    owner = db.relationship('User', backref='properties')
    property_type = db.relationship('PropertyType', backref='properties')

    # --- DÉBUT DE LA CORRECTION POUR LA SUPPRESSION ---
    images = db.relationship('PropertyImage', back_populates='property', cascade="all, delete-orphan", lazy=True)
    # --- FIN DE LA CORRECTION ---

    # --- CORRECTION DE LA SYNTAXE ET DE LA LOGIQUE ---
    # La définition de la méthode doit être indentée à l'intérieur de la classe
    def to_dict(self):
        # Dictionnaire de base avec les champs statiques comme source de vérité
        base_data = {
            'id': self.id,
            'owner_id': self.owner_id,
            'property_type_id': self.property_type_id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'price': float(self.price) if self.price is not None else None,
            'address': self.address,
            'city': self.city,
            'postal_code': self.postal_code,
            'latitude': float(self.latitude) if self.latitude is not None else None,
            'longitude': float(self.longitude) if self.longitude is not None else None,
            'is_validated': self.is_validated,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        # On crée un dictionnaire 'attributes' propre et cohérent
        attributes_dict = self.attributes.copy() if self.attributes else {}
        
        # On s'assure que les valeurs statiques écrasent les valeurs en double dans le JSON
        attributes_dict['title'] = self.title
        attributes_dict['price'] = float(self.price) if self.price is not None else None
        attributes_dict['status'] = self.status
        attributes_dict['description'] = self.description
        attributes_dict['address'] = self.address
        attributes_dict['city'] = self.city
        attributes_dict['postal_code'] = self.postal_code
        attributes_dict['latitude'] = float(self.latitude) if self.latitude is not None else None
        attributes_dict['longitude'] = float(self.longitude) if self.longitude is not None else None
        attributes_dict['property_type_id'] = self.property_type_id
        
        base_data['attributes'] = attributes_dict
        base_data['image_urls'] = [image.image_url for image in self.images]

        if self.property_type:
            base_data['property_type'] = {
                'id': self.property_type.id,
                'name': self.property_type.name
        }
        else:
            base_data['property_type'] = None

        return base_data
    # --- FIN DE LA CORRECTION ---

class PropertyImage(db.Model):
    __tablename__ = 'PropertyImages'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    
    # --- DÉBUT DE LA CORRECTION POUR LA SUPPRESSION ---
    # On remplace 'backref' par 'back_populates' pour une relation bidirectionnelle explicite
    property = db.relationship('Property', back_populates='images')
    # --- FIN DE LA CORRECTION ---

class Referral(db.Model):
    __tablename__ = 'Referrals'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    referral_code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('agent_id', 'property_id', name='unique_agent_property'),)
    agent = db.relationship('User', backref='referrals')
    property = db.relationship('Property', backref='referrals_received')
    visit_requests = db.relationship('VisitRequest', backref='referral', lazy='dynamic')

class VisitRequest(db.Model):
    __tablename__ = 'VisitRequests'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    referral_id = db.Column(db.Integer, db.ForeignKey('Referrals.id', ondelete='SET NULL')) # Nouvelle colonne
    requested_datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum('pending', 'confirmed', 'accepted', 'rejected', 'completed'), nullable=False, default='pending')
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('User', backref='visit_requests')
    property = db.relationship('Property', backref='visit_requests_received')
    referral = db.relationship('Referral', backref='visit_requests') # Nouvelle relation

class PropertyRequest(db.Model):
    __tablename__ = 'PropertyRequests'
    id = db.Column(db.Integer, primary_key=True)
    # CORRECTION : Le rôle 'customer' n'était pas dans votre Enum, je l'ai remplacé par 'seeker'
    customer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    request_details = db.Column(db.Text)
    city = db.Column(db.String(100))
    property_type_id = db.Column(db.Integer, db.ForeignKey('PropertyTypes.id', ondelete='SET NULL'))
    min_price = db.Column(db.Numeric(12, 2))
    max_price = db.Column(db.Numeric(12, 2))
    status = db.Column(db.Enum('new', 'in_progress', 'contacted', 'closed'), nullable=False, default='new')
    admin_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('User', backref='property_requests')
    property_type = db.relationship('PropertyType', backref='property_requests')

class Commission(db.Model):
    __tablename__ = 'Commissions'
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='RESTRICT'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum('pending', 'paid'), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    agent = db.relationship('User', backref='commissions_earned')
    property = db.relationship('Property', backref='commissions_paid')

class Transaction(db.Model):
    __tablename__ = 'Transactions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    service_fee_id = db.Column(db.Integer, db.ForeignKey('ServiceFees.id', ondelete='SET NULL'))
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    type = db.Column(db.Enum('deposit', 'withdrawal', 'payment', 'commission_payout'), nullable=False)
    description = db.Column(db.String(255))
    related_entity_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='transactions')
    service_fee = db.relationship('ServiceFee', backref='transactions')
