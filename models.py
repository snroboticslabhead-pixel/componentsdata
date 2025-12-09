from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

db = SQLAlchemy()

class Lab(db.Model):
    __tablename__ = 'labs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.now(IST))
    
    # Relationships
    categories = db.relationship('Category', backref='lab', lazy='joined')
    components = db.relationship('Component', backref='lab', lazy='joined')
    transactions = db.relationship('Transaction', backref='lab', lazy='joined')

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    lab_id = db.Column(db.Integer, db.ForeignKey('labs.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now(IST))
    
    # Relationships
    components = db.relationship('Component', backref='category', lazy='joined')

class Component(db.Model):
    __tablename__ = 'components'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    lab_id = db.Column(db.Integer, db.ForeignKey('labs.id'), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(50))
    description = db.Column(db.String(500))
    component_type = db.Column(db.String(100))
    date_added = db.Column(db.DateTime, default=datetime.now(IST))
    last_updated = db.Column(db.DateTime, default=datetime.now(IST))
    
    # Relationships
    transactions = db.relationship('Transaction', backref='component', lazy='joined')

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    component_id = db.Column(db.Integer, db.ForeignKey('components.id'), nullable=False)
    lab_id = db.Column(db.Integer, db.ForeignKey('labs.id'), nullable=True)
    campus = db.Column(db.String(100))
    person_name = db.Column(db.String(100), nullable=False)
    purpose = db.Column(db.String(500), nullable=False)
    qty_issued = db.Column(db.Integer, default=0)
    qty_returned = db.Column(db.Integer, default=0)
    pending_qty = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='Issued')
    issue_date = db.Column(db.DateTime, default=datetime.now(IST))
    date = db.Column(db.DateTime, default=datetime.now(IST))
    quantity_before = db.Column(db.Integer)
    quantity_after = db.Column(db.Integer)
    transaction_quantity = db.Column(db.Integer)
    last_action = db.Column(db.String(20))
    notes = db.Column(db.Text)
    last_updated = db.Column(db.DateTime, default=datetime.now(IST))
