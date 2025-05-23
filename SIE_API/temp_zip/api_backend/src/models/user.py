from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
import uuid

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    email_confirmed = db.Column(db.Boolean, default=False)
    confirmation_token = db.Column(db.String(100), nullable=True)
    reset_password_token = db.Column(db.String(100), nullable=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relacionamento com instâncias do WhatsApp
    whatsapp_instances = db.relationship('WhatsAppInstance', backref='user', lazy=True)
    
    def __init__(self, email, password, name, is_admin=False):
        self.email = email
        self.password_hash = generate_password_hash(password)
        self.name = name
        self.is_admin = is_admin
        self.confirmation_token = str(uuid.uuid4())
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def generate_reset_token(self):
        self.reset_password_token = str(uuid.uuid4())
        self.reset_token_expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        return self.reset_password_token
    
    def confirm_email(self):
        self.email_confirmed = True
        self.confirmation_token = None
        self.is_active = True
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'name': self.name,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'email_confirmed': self.email_confirmed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class WhatsAppInstance(db.Model):
    __tablename__ = 'whatsapp_instances'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    session_id = db.Column(db.String(100), unique=True, nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    instance_type = db.Column(db.String(20), default='whatsapp-web.js')  # 'whatsapp-web.js' ou 'baileys'
    is_connected = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    webhook_url = db.Column(db.String(255), nullable=True)
    ignore_groups = db.Column(db.Boolean, default=False)
    block_calls = db.Column(db.Boolean, default=False)
    prevent_message_deletion = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'session_id': self.session_id,
            'phone_number': self.phone_number,
            'instance_type': self.instance_type,
            'is_connected': self.is_connected,
            'is_active': self.is_active,
            'webhook_url': self.webhook_url,
            'ignore_groups': self.ignore_groups,
            'block_calls': self.block_calls,
            'prevent_message_deletion': self.prevent_message_deletion,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
