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
    role = db.Column(db.Enum('owner', 'agent', 'customer', 'admin'), nullable=False)
    wallet_balance = db.Column(db.Numeric(10, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code = db.Column(db.String(6), unique=True, nullable=True) # 6-digit code

    def __repr__(self):
        return f'<User {self.email}>'

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

class PropertyType(db.Model):
    __tablename__ = 'PropertyTypes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

class PropertyAttribute(db.Model):
    __tablename__ = 'PropertyAttributes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    data_type = db.Column(db.Enum('integer', 'boolean', 'string', 'decimal', 'enum'), nullable=False)
    is_filterable = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('Users.id'))
    user = db.relationship('User', backref='property_attributes')

class AttributeOption(db.Model):
    __tablename__ = 'AttributeOptions'
    id = db.Column(db.Integer, primary_key=True)
    attribute_id = db.Column(db.Integer, db.ForeignKey('PropertyAttributes.id', ondelete='CASCADE'), nullable=False)
    option_value = db.Column(db.String(100), nullable=False)
    attribute = db.relationship('PropertyAttribute', backref='options')

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

class PropertyImage(db.Model):
    __tablename__ = 'PropertyImages'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    display_order = db.Column(db.Integer, default=0)
    property = db.relationship('Property', backref='images')

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

class VisitRequest(db.Model):
    __tablename__ = 'VisitRequests'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('Users.id', ondelete='CASCADE'), nullable=False)
    property_id = db.Column(db.Integer, db.ForeignKey('Properties.id', ondelete='CASCADE'), nullable=False)
    requested_datetime = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Enum('pending', 'confirmed', 'rejected', 'completed'), nullable=False, default='pending')
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship('User', backref='visit_requests')
    property = db.relationship('Property', backref='visit_requests_received')

class PropertyRequest(db.Model):
    __tablename__ = 'PropertyRequests'
    id = db.Column(db.Integer, primary_key=True)
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
