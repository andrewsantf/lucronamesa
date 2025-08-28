import stripe
from flask import render_template, redirect, url_for, flash, request, Blueprint, abort, session, current_app
from app import db, bcrypt
from app.models import User, Ingredient, Recipe
from app.forms import RegistrationForm, LoginForm, IngredientForm, UpdateProfileForm, ChangePasswordForm
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func, desc
import re
from datetime import datetime, timedelta
from functools import wraps

main = Blueprint('main', __name__)

# --- DECORADOR PERSONALIZADO (GUARDIÃO DA ASSINATURA) ---
def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_subscription_active:
            flash('Sua assinatura ou período de teste expirou. Por favor, escolha um plano para continuar.', 'warning')
            return redirect(url_for('main.planos'))
        return f(*args, **kwargs)
    return decorated_function


# --- MANIPULADORES DE ERRO ---
@main.app_errorhandler(404)
def error_404(error):
    return render_template('404.html', title="Página não encontrada"), 404

@main.app_errorhandler(500)
def error_500(error):
    db.session.rollback()
    return render_template('500.html', title="Erro interno"), 500

# --- ROTAS PÚBLICAS E DE AUTENTICAÇÃO ---
@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('landing_page.html', title="LucroNaMesa - A forma inteligente de precifiar")

@main.route('/planos')
def planos():
    return render_template('plans.html', title="Escolha seu Plano")

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Login sem sucesso. Verifique o e-mail e a senha.', 'danger')
    return render_template('login.html', form=form, title="Login")

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    plan = request.args.get('plan', 'trial')
    form = RegistrationForm()
    if form.validate_on_submit():
        plan_from_form = request.form.get('plan')
        if plan_from_form == 'trial':
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(
                full_name=form.full_name.data, email=form.email.data,
                business_name=form.business_name.data, business_type=form.business_type.data,
                phone=form.phone.data, password=hashed_password,
                plan_type='Trial', subscription_status='trialing',
                trial_ends_at=datetime.utcnow() + timedelta(days=7)
            )
            db.session.add(user)
            db.session.commit()
            flash('Sua conta foi criada com sucesso! Aproveite seus 7 dias de teste.', 'success')
            login_user(user, remember=True)
            return redirect(url_for('main.dashboard'))
        elif plan_from_form in ['mensal', 'anual']:
            pending_data = form.data
            pending_data['password'] = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            session['pending_registration_data'] = pending_data
            price_id = current_app.config['STRIPE_ANNUAL_PLAN_PRICE_ID'] if plan_from_form == 'anual' else current_app.config['STRIPE_MONTHLY_PLAN_PRICE_ID']
            stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
            try:
                checkout_session = stripe.checkout.Session.create(
                    line_items=[{'price': price_id, 'quantity': 1}],
                    mode='subscription',
                    success_url=url_for('main.dashboard', _external=True),
                    cancel_url=url_for('main.register', plan=plan_from_form, _external=True),
                    customer_email=form.email.data
                )
                return redirect(checkout_session.url, code=303)
            except Exception as e:
                flash(f'Erro ao conectar com o gateway de pagamento: {e}', 'danger')
                return redirect(url_for('main.register', plan=plan_from_form))
    return render_template('register.html', form=form, title="Crie sua Conta", plan=plan)

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

# --- ROTAS PROTEGIDAS PELA ASSINATURA ---
@main.route('/dashboard')
@login_required
@subscription_required
def dashboard():
    ingredients = Ingredient.query.filter_by(user_id=current_user.id).order_by(Ingredient.name).all()
    recipes = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.name).all()
    kpi_total_ingredients = len(ingredients)
    kpi_total_recipes = len(recipes)
    total_cost_sum = db.session.query(func.sum(Recipe.total_cost)).filter_by(user_id=current_user.id).scalar() or 0
    kpi_avg_cost = total_cost_sum / kpi_total_recipes if kpi_total_recipes > 0 else 0
    top_5_recipes = sorted(recipes, key=lambda x: x.total_cost, reverse=True)[:5]
    chart_labels = [recipe.name for recipe in top_5_recipes]
    chart_data = [round(recipe.total_cost, 2) for recipe in top_5_recipes]
    return render_template('dashboard.html', title="Dashboard", ingredients=ingredients, recipes=recipes, kpi_total_ingredients=kpi_total_ingredients, kpi_total_recipes=kpi_total_recipes, kpi_avg_cost=kpi_avg_cost, chart_labels=chart_labels, chart_data=chart_data)

@main.route('/ingredients', methods=['GET', 'POST'])
@login_required
@subscription_required
def ingredients():
    form = IngredientForm()
    if form.validate_on_submit():
        package_price = float(str(form.package_price.data).replace(',', '.'))
        package_quantity = float(str(form.package_quantity.data).replace(',', '.'))
        base_price, base_unit = calculate_base_price(package_price, package_quantity, form.package_unit.data)
        ingredient = Ingredient(name=form.name.data, package_price=package_price, 
                                package_quantity=package_quantity, package_unit=form.package_unit.data, 
                                base_price=base_price, base_unit=base_unit, author=current_user)
        db.session.add(ingredient)
        db.session.commit()
        flash('Ingrediente adicionado com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('ingredients.html', form=form, title="Adicionar Ingrediente")

@main.route('/ingredient/<int:ingredient_id>/edit', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    if ingredient.author != current_user: abort(403)
    form = IngredientForm()
    if form.validate_on_submit():
        ingredient.name = form.name.data
        package_price = float(str(form.package_price.data).replace(',', '.'))
        package_quantity = float(str(form.package_quantity.data).replace(',', '.'))
        ingredient.package_price = package_price
        ingredient.package_quantity = package_quantity
        ingredient.package_unit = form.package_unit.data
        ingredient.base_price, ingredient.base_unit = calculate_base_price(
            ingredient.package_price, ingredient.package_quantity, ingredient.package_unit)
        db.session.commit()
        flash('Ingrediente atualizado com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))
    elif request.method == 'GET':
        form.name.data = ingredient.name
        form.package_price.data = str(ingredient.package_price).replace('.', ',')
        form.package_quantity.data = str(ingredient.package_quantity).replace('.', ',')
        form.package_unit.data = ingredient.package_unit
    return render_template('ingredients.html', form=form, title=f"Editar '{ingredient.name}'")

@main.route('/ingredient/<int:ingredient_id>/delete', methods=['POST'])
@login_required
@subscription_required
def delete_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    if ingredient.author != current_user: abort(403)
    db.session.delete(ingredient)
    db.session.commit()
    flash('Ingrediente excluído com sucesso!', 'success')
    return redirect(url_for('main.dashboard'))

@main.route('/recipes', methods=['GET', 'POST'])
@login_required
@subscription_required
def recipes():
    ingredients = Ingredient.query.filter_by(user_id=current_user.id).order_by(Ingredient.name).all()
    if request.method == 'POST':
        name = request.form.get('name')
        ingredient_ids = request.form.getlist('ingredient_ids')
        profit_margin_str = request.form.get('profit_margin', '').replace(',', '.')
        if not name or not ingredient_ids or not profit_margin_str:
            flash('Por favor, preencha todos os campos obrigatórios.', 'warning')
            return redirect(url_for('main.recipes'))
        total_cost = 0
        recipe_ingredients_text = []
        for ing_id in ingredient_ids:
            ingredient = Ingredient.query.get(ing_id)
            quantity_str = request.form.get(f'quantity_{ing_id}', '').replace(',', '.')
            if not quantity_str:
                flash(f'Erro: Por favor, informe a quantidade para o ingrediente "{ingredient.name}".', 'danger')
                return redirect(url_for('main.recipes'))
            quantity = float(quantity_str)
            unit_used = request.form.get(f'unit_{ing_id}')
            cost = calculate_ingredient_cost_in_recipe(ingredient, quantity, unit_used)
            total_cost += cost
            recipe_ingredients_text.append(f'{ingredient.name}:{quantity}{unit_used}')
        profit_margin = float(profit_margin_str)
        sale_price = total_cost * (1 + profit_margin / 100)
        ingredients_str = ';'.join(recipe_ingredients_text)
        new_recipe = Recipe(name=name, total_cost=total_cost, ingredients_list=ingredients_str, 
                            profit_margin=profit_margin, sale_price=sale_price, user_id=current_user.id)
        db.session.add(new_recipe)
        db.session.commit()
        flash('Receita criada e preço de venda calculado com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('recipes.html', ingredients=ingredients, title="Adicionar Receita")

@main.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.author != current_user: abort(403)
    all_ingredients = Ingredient.query.filter_by(user_id=current_user.id).order_by(Ingredient.name).all()
    if request.method == 'POST':
        recipe.name = request.form.get('name')
        ingredient_ids = request.form.getlist('ingredient_ids')
        profit_margin_str = request.form.get('profit_margin', '').replace(',', '.')
        if not ingredient_ids or not profit_margin_str:
            flash('Uma receita deve ter ao menos um ingrediente e uma margem de lucro.', 'warning')
            return redirect(url_for('main.edit_recipe', recipe_id=recipe.id))
        total_cost = 0
        recipe_ingredients_text = []
        for ing_id in ingredient_ids:
            ingredient = Ingredient.query.get(ing_id)
            quantity_str = request.form.get(f'quantity_{ing_id}', '').replace(',', '.')
            if not quantity_str:
                flash(f'Erro: Por favor, informe a quantidade para o ingrediente "{ingredient.name}".', 'danger')
                return redirect(url_for('main.edit_recipe', recipe_id=recipe.id))
            quantity = float(quantity_str)
            unit_used = request.form.get(f'unit_{ing_id}')
            cost = calculate_ingredient_cost_in_recipe(ingredient, quantity, unit_used)
            total_cost += cost
            recipe_ingredients_text.append(f'{ingredient.name}:{quantity}{unit_used}')
        recipe.ingredients_list = ';'.join(recipe_ingredients_text)
        recipe.total_cost = total_cost
        recipe.profit_margin = float(profit_margin_str)
        recipe.sale_price = total_cost * (1 + recipe.profit_margin / 100)
        db.session.commit()
        flash('Receita atualizada com sucesso!', 'success')
        return redirect(url_for('main.dashboard'))
    
    recipe_ingredients = {}
    if recipe.ingredients_list:
        parts = recipe.ingredients_list.split(';')
        for part in parts:
            try:
                name, quant_unit = part.split(':', 1)
                match = re.match(r"(\d*\.?\d+)([a-zA-Z]+)", quant_unit)
                if match:
                    quantity = match.group(1)
                    unit = match.group(2)
                    ingredient_obj = Ingredient.query.filter_by(name=name, user_id=current_user.id).first()
                    if ingredient_obj:
                        recipe_ingredients[ingredient_obj.id] = {'quantity': float(quantity), 'unit': unit}
            except (ValueError, AttributeError):
                continue
    return render_template('edit_recipe.html', recipe=recipe, all_ingredients=all_ingredients, recipe_ingredients=recipe_ingredients, title=f"Editar '{recipe.name}'")

@main.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
@subscription_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.author != current_user: abort(403)
    db.session.delete(recipe)
    db.session.commit()
    flash('Receita excluída com sucesso!', 'success')
    return redirect(url_for('main.dashboard'))

@main.route('/profile', methods=['GET', 'POST'])
@login_required
@subscription_required
def profile():
    profile_form = UpdateProfileForm()
    password_form = ChangePasswordForm()
    if profile_form.validate_on_submit() and profile_form.submit.data:
        current_user.full_name = profile_form.full_name.data
        current_user.email = profile_form.email.data
        current_user.business_name = profile_form.business_name.data
        current_user.business_type = profile_form.business_type.data
        current_user.phone = profile_form.phone.data
        db.session.commit()
        flash('Seu perfil foi atualizado com sucesso!', 'success')
        return redirect(url_for('main.profile'))
    if password_form.validate_on_submit() and password_form.submit_password.data:
        if bcrypt.check_password_hash(current_user.password, password_form.current_password.data):
            hashed_password = bcrypt.generate_password_hash(password_form.new_password.data).decode('utf-8')
            current_user.password = hashed_password
            db.session.commit()
            flash('Sua senha foi alterada com sucesso!', 'success')
            return redirect(url_for('main.profile'))
        else:
            flash('Senha atual incorreta.', 'danger')
    if request.method == 'GET':
        profile_form.full_name.data = current_user.full_name
        profile_form.email.data = current_user.email
        profile_form.business_name.data = current_user.business_name
        profile_form.business_type.data = current_user.business_type
        profile_form.phone.data = current_user.phone
    return render_template('profile.html', profile_form=profile_form, password_form=password_form, title="Meu Perfil")

@main.route('/reports')
@login_required
@subscription_required
def reports():
    recipe_sort = request.args.get('recipe_sort', 'profit_desc')
    recipe_limit = request.args.get('recipe_limit', '5')
    ingredient_sort = request.args.get('ingredient_sort', 'desc')
    ingredient_limit = request.args.get('ingredient_limit', '5')
    all_recipes = Recipe.query.filter_by(user_id=current_user.id).all()
    for r in all_recipes:
        r.profit = r.sale_price - r.total_cost if r.sale_price else 0
        r.margin = (r.profit / r.sale_price * 100) if r.sale_price and r.sale_price > 0 else 0
    if recipe_sort == 'cost_asc':
        sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost)
    elif recipe_sort == 'profit_desc':
        sorted_recipes = sorted(all_recipes, key=lambda x: x.profit, reverse=True)
    elif recipe_sort == 'margin_desc':
        sorted_recipes = sorted(all_recipes, key=lambda x: x.margin, reverse=True)
    else:
        sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost, reverse=True)
    if recipe_limit != 'all':
        recipes_to_display = sorted_recipes[:int(recipe_limit)]
    else:
        recipes_to_display = sorted_recipes
    recipe_chart_labels = [r.name for r in recipes_to_display]
    recipe_chart_cost_data = [round(r.total_cost, 2) for r in recipes_to_display]
    recipe_chart_sale_data = [round(r.sale_price, 2) for r in recipes_to_display]
    recipe_chart_ids = [r.id for r in recipes_to_display]
    ingredient_query = Ingredient.query.filter_by(user_id=current_user.id)
    if ingredient_sort == 'asc':
        ingredient_query = ingredient_query.order_by(Ingredient.base_price.asc())
    else:
        ingredient_query = ingredient_query.order_by(Ingredient.base_price.desc())
    if ingredient_limit != 'all':
        ingredients = ingredient_query.limit(int(ingredient_limit)).all()
    else:
        ingredients = ingredient_query.all()
    ingredient_chart_labels = []
    ingredient_chart_data = []
    for i in ingredients:
        if i.base_unit in ['g', 'ml']:
            ingredient_chart_labels.append(f"{i.name} (R$/{'kg' if i.base_unit == 'g' else 'l'})")
            ingredient_chart_data.append(round(i.base_price * 1000, 2))
        else:
            ingredient_chart_labels.append(f"{i.name} (R$/un)")
            ingredient_chart_data.append(round(i.base_price, 2))
    return render_template('reports.html', title="Relatórios",
        recipe_chart_labels=recipe_chart_labels, 
        recipe_chart_cost_data=recipe_chart_cost_data,
        recipe_chart_sale_data=recipe_chart_sale_data,
        recipe_chart_ids=recipe_chart_ids,
        ingredient_chart_labels=ingredient_chart_labels, 
        ingredient_chart_data=ingredient_chart_data,
        recipe_sort=recipe_sort, recipe_limit=recipe_limit,
        ingredient_sort=ingredient_sort, ingredient_limit=ingredient_limit)

@main.route('/terms')
def terms():
    return render_template('terms.html', title="Termos de Serviço")

@main.route('/privacy')
def privacy():
    return render_template('privacy.html', title="Política de Privacidade")

# --- ROTAS DO GATEWAY DE PAGAMENTO ---
@main.route('/criar-assinatura/<plan>')
@login_required
def criar_assinatura(plan):
    if current_user.stripe_customer_id and current_user.subscription_status == 'active':
        flash('Você já possui uma assinatura ativa.', 'warning')
        return redirect(url_for('main.profile'))
    price_id = None
    if plan == 'mensal':
        price_id = current_app.config['STRIPE_MONTHLY_PLAN_PRICE_ID']
    elif plan == 'anual':
        price_id = current_app.config['STRIPE_ANNUAL_PLAN_PRICE_ID']
    else:
        flash('Plano inválido.', 'danger')
        return redirect(url_for('main.planos'))
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=url_for('main.dashboard', _external=True),
            cancel_url=url_for('main.planos', _external=True),
            client_reference_id=current_user.id
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'Erro ao conectar com o gateway de pagamento: {e}', 'danger')
        return redirect(url_for('main.planos'))

@main.route('/pagamento-sucesso')
def payment_success():
    flash('Seu pagamento está sendo processado! Sua conta será atualizada em instantes.', 'info')
    return redirect(url_for('main.login'))

@main.route('/webhook-stripe', methods=['POST'])
def webhook_stripe():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return f'Webhook error: {e}', 400
    if event['type'] == 'checkout.session.completed':
        checkout_session = event['data']['object']
        user_id = checkout_session.get('client_reference_id')
        if user_id:
            user = User.query.get(user_id)
            if user:
                stripe_customer_id = checkout_session.get('customer')
                stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
                line_items = stripe.checkout.Session.list_line_items(checkout_session.id, limit=1)
                price_id = line_items.data[0].price.id
                plan_type = 'Anual' if price_id == current_app.config['STRIPE_ANNUAL_PLAN_PRICE_ID'] else 'Mensal'
                user.plan_type = plan_type
                user.subscription_status = 'active'
                user.stripe_customer_id = stripe_customer_id
                user.trial_ends_at = None
                db.session.commit()
                print(f"Assinatura do usuário {user.email} atualizada para o plano {plan_type}!")
        else:
            form_data = session.get('pending_registration_data')
            if form_data:
                stripe_customer_id = checkout_session.get('customer')
                stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
                line_items = stripe.checkout.Session.list_line_items(checkout_session.id, limit=1)
                price_id = line_items.data[0].price.id
                plan_type = 'Anual' if price_id == current_app.config['STRIPE_ANNUAL_PLAN_PRICE_ID'] else 'Mensal'
                user = User(
                    full_name=form_data.get('full_name'), email=form_data.get('email'),
                    business_name=form_data.get('business_name'), business_type=form_data.get('business_type'),
                    phone=form_data.get('phone'), password=form_data.get('password'),
                    plan_type=plan_type, subscription_status='active',
                    stripe_customer_id=stripe_customer_id
                )
                db.session.add(user)
                db.session.commit()
                session.pop('pending_registration_data', None)
                print(f"Usuário {user.email} criado com sucesso com o plano {plan_type}!")
    if event['type'] == 'customer.subscription.updated':
        subscription_data = event['data']['object']
        stripe_customer_id = subscription_data.get('customer')
        new_status = subscription_data.get('status')
        user = User.query.filter_by(stripe_customer_id=stripe_customer_id).first()
        if user:
            user.subscription_status = new_status
            db.session.commit()
            print(f"Status da assinatura do usuário {user.email} atualizado para {new_status}")
    return 'Success', 200

# --- FUNÇÕES AUXILIARES ---
def calculate_base_price(price, quantity, unit):
    if not quantity or quantity == 0: return 0, unit
    if unit == 'kg': return price / (quantity * 1000), 'g'
    elif unit == 'l': return price / (quantity * 1000), 'ml'
    else: return price / quantity, unit

def calculate_ingredient_cost_in_recipe(ingredient, quantity_used, unit_used):
    cost = 0
    if unit_used == 'kg': quantity_used *= 1000
    elif unit_used == 'l': quantity_used *= 1000
    cost = ingredient.base_price * quantity_used
    return cost
