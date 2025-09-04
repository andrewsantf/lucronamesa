from app import db # Apenas o 'db' é necessário aqui
from flask_login import UserMixin
from datetime import datetime

# A função @login_manager.user_loader foi REMOVIDA daqui.

class RecipeIngredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(db.Integer, db.ForeignKey('recipe.id'), nullable=False)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_used = db.Column(db.String(20), nullable=False)
    ingredient = db.relationship('Ingredient')

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    business_name = db.Column(db.String(100), nullable=False)
    business_type = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    password = db.Column(db.String(60), nullable=False)
    plan_type = db.Column(db.String(50), nullable=False, default='Trial')
    subscription_status = db.Column(db.String(50), nullable=False, default='trialing')
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    stripe_customer_id = db.Column(db.String(120), nullable=True)
    onboarding_complete = db.Column(db.Boolean, default=False)
    has_created_ingredient = db.Column(db.Boolean, default=False)
    has_created_recipe = db.Column(db.Boolean, default=False)
    ingredients = db.relationship('Ingredient', backref='author', lazy=True, cascade="all, delete-orphan")
    recipes = db.relationship('Recipe', backref='author', lazy=True, cascade="all, delete-orphan")

    @property
    def is_subscription_active(self):
        if self.subscription_status == 'active': return True
        if self.subscription_status == 'trialing' and self.trial_ends_at and datetime.utcnow() < self.trial_ends_at: return True
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
    price_history = db.relationship('PriceHistory', backref='ingredient', lazy=True, cascade="all, delete-orphan")
    last_alerted_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"Ingredient('{self.name}', '{self.package_price}')"

class PriceHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ingredient_id = db.Column(db.Integer, db.ForeignKey('ingredient.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(10), nullable=False)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"PriceHistory(Ingredient ID: {self.ingredient_id}, Price: {self.price}, Date: {self.recorded_at})"

class Recipe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    yield_quantity = db.Column(db.Float, nullable=True)
    yield_unit = db.Column(db.String(50), nullable=True)
    total_weight_g = db.Column(db.Float, nullable=True)
    loss_percentage = db.Column(db.Float, nullable=True, default=0)
    total_cost = db.Column(db.Float, nullable=False)
    cost_per_serving = db.Column(db.Float, nullable=True)
    profit_margin = db.Column(db.Float, nullable=True)
    sale_price = db.Column(db.Float, nullable=True)
    ingredients = db.relationship('RecipeIngredient', backref='recipe', lazy='dynamic', cascade="all, delete-orphan")
    preparation_steps = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"Recipe('{self.name}', 'Cost: {self.total_cost}')"