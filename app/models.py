from app import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timedelta

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    business_name = db.Column(db.String(100), nullable=False)
    business_type = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password = db.Column(db.String(60), nullable=False)
    
    # --- CAMPOS DE ASSINATURA ---
    plan_type = db.Column(db.String(50), nullable=False, default='Trial')
    subscription_status = db.Column(db.String(50), nullable=False, default='trialing')
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(120), nullable=True)

    ingredients = db.relationship('Ingredient', backref='author', lazy=True)
    recipes = db.relationship('Recipe', backref='author', lazy=True)

    # --- NOVA PROPRIEDADE INTELIGENTE ---
    @property
    def is_subscription_active(self):
        # Um usuário está ativo se seu status for 'active' (pago)
        if self.subscription_status == 'active':
            return True
        # Ou se ele estiver em 'trialing' E a data de fim do teste ainda não passou
        if self.subscription_status == 'trialing' and self.trial_ends_at and datetime.utcnow() < self.trial_ends_at:
            return True
        # Caso contrário, a assinatura não está ativa
        return False

    def __repr__(self):
        return f"User('{self.full_name}', '{self.email}')"

class Ingredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    package_price = db.Column(db.Float, nullable=False)
    package_quantity = db.Column(db.Float, nullable=False)
    package_unit = db.Column(db.String(10), nullable=False)
    base_price = db.Column(db.Float, nullable=False)
    base_unit = db.Column(db.String(10), nullable=False)

    def __repr__(self):
        return f"Ingredient('{self.name}', '{self.package_price}')"

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    ingredients_list = db.Column(db.String(500), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    profit_margin = db.Column(db.Float, nullable=True)
    sale_price = db.Column(db.Float, nullable=True)

    def __repr__(self):
        return f"Recipe('{self.name}', 'Cost: {self.total_cost}')"
