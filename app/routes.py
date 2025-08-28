import stripe
from flask import render_template, redirect, url_for, flash, request, Blueprint, abort, session, current_app
from app import db, bcrypt
from app.models import User, Ingredient, Recipe
from app.forms import RegistrationForm, LoginForm, IngredientForm, UpdateProfileForm, ChangePasswordForm
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
import re
from datetime import datetime, timedelta
from functools import wraps

main = Blueprint('main', __name__)

# --- DECORADOR PERSONALIZADO (GUARDIÃO DA ASSINATURA) ---
def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Se o usuário acabou de criar a conta, não mostrar mensagem de trial expirado
        if session.get('novo_usuario'):
            session.pop('novo_usuario')  # remove a flag após exibir a primeira vez
            return f(*args, **kwargs)

        # Se usuário não está ativo
        if not current_user.is_subscription_active:
            if current_user.subscription_status == 'trialing':
                flash('Seu período de teste expirou. Escolha um plano para continuar.', 'danger')
            elif current_user.subscription_status == 'pending':
                flash('Sua assinatura ainda não foi ativada. Escolha um plano para continuar.', 'info')
            else:
                flash('Sua assinatura expirou. Escolha um plano para continuar.', 'danger')
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

        # --- USUÁRIO TRIAL ---
        if plan_from_form == 'trial':
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(
                full_name=form.full_name.data,
                email=form.email.data,
                business_name=form.business_name.data,
                business_type=form.business_type.data,
                phone=form.phone.data,
                password=hashed_password,
                plan_type='Trial',
                subscription_status='trialing',
                trial_ends_at=datetime.utcnow() + timedelta(days=7)
            )
            db.session.add(user)
            db.session.commit()
            flash('Sua conta foi criada com sucesso! Aproveite seus 7 dias de teste.', 'success')
            login_user(user, remember=True)
            session['novo_usuario'] = True
            return redirect(url_for('main.dashboard'))

        # --- USUÁRIO PAGOS ---
        elif plan_from_form in ['mensal', 'anual']:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user = User(
                full_name=form.full_name.data,
                email=form.email.data,
                business_name=form.business_name.data,
                business_type=form.business_type.data,
                phone=form.phone.data,
                password=hashed_password,
                plan_type=None,
                subscription_status='pending'
            )
            db.session.add(user)
            db.session.commit()
            login_user(user, remember=True)
            flash('Sua conta foi criada! Agora escolha seu plano para ativar a assinatura.', 'info')
            session['novo_usuario'] = True
            return redirect(url_for('main.planos'))

    return render_template('register.html', form=form, title="Crie sua Conta", plan=plan)

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

# --- ROTAS DE BOAS-VINDAS PARA PLANOS PAGOS ---
@main.route('/welcome/mensal')
@login_required
def welcome_mensal():
    return redirect(url_for('main.criar_assinatura', plan='mensal'))

@main.route('/welcome/anual')
@login_required
def welcome_anual():
    return redirect(url_for('main.criar_assinatura', plan='anual'))

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
    return render_template('dashboard.html', title="Dashboard", ingredients=ingredients, recipes=recipes,
                           kpi_total_ingredients=kpi_total_ingredients, kpi_total_recipes=kpi_total_recipes,
                           kpi_avg_cost=kpi_avg_cost, chart_labels=chart_labels, chart_data=chart_data)

# --- ROTAS DE GERENCIAR ASSINATURA ---
@main.route('/gerenciar_assinatura')
@login_required
def gerenciar_assinatura():
    return redirect(url_for('main.planos'))

# --- ROTAS DE CRIAR ASSINATURA (CHECKOUT STRIPE) ---
@main.route('/criar_assinatura/<plan>')
@login_required
def criar_assinatura(plan):
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    price_id = current_app.config['STRIPE_ANNUAL_PLAN_PRICE_ID'] if plan == 'anual' else current_app.config['STRIPE_MONTHLY_PLAN_PRICE_ID']
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=url_for('main.dashboard', _external=True),
            cancel_url=url_for('main.planos', _external=True),
            customer_email=current_user.email
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'Erro ao conectar com o gateway de pagamento: {e}', 'danger')
        return redirect(url_for('main.planos'))

# --- ROTAS DE INGREDIENTES ---
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

# --- ROTAS DE RECEITAS ---
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
    return render_template('edit_recipe.html', recipe=recipe, all_ingredients=all_ingredients,
                           recipe_ingredients=recipe_ingredients, title=f"Editar '{recipe.name}'")

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

# --- ROTAS DE PERFIL ---
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

# --- ROTAS DE RELATÓRIOS ---
@main.route('/reports')
@login_required
@subscription_required
def reports():
    recipe_sort = request.args.get('recipe_sort', 'profit_desc')
    recipe_limit = request.args.get('recipe_limit', '5')
    ingredient_sort = request.args.get('ingredient_sort', 'desc')
    ingredient_limit = request.args.get('ingredient_limit', '5')

    # --- RECEITAS ---
    all_recipes = Recipe.query.filter_by(user_id=current_user.id).all()
    for r in all_recipes:
        r.profit = r.sale_price - r.total_cost if r.sale_price else 0
        r.margin = (r.profit / r.sale_price * 100) if r.sale_price and r.sale_price > 0 else 0

    # Ordenar receitas
    if recipe_sort == 'cost_asc':
        sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost)
    elif recipe_sort == 'profit_desc':
        sorted_recipes = sorted(all_recipes, key=lambda x: x.profit, reverse=True)
    elif recipe_sort == 'margin_desc':
        sorted_recipes = sorted(all_recipes, key=lambda x: x.margin, reverse=True)
    else:
        sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost, reverse=True)

    # Tratar recipe_limit seguro
    if recipe_limit.isdigit():
        recipes_to_display = sorted_recipes[:int(recipe_limit)]
    else:
        recipes_to_display = sorted_recipes  # 'all' ou vazio

    recipe_chart_labels = [r.name for r in recipes_to_display]
    recipe_chart_cost_data = [round(r.total_cost, 2) for r in recipes_to_display]
    recipe_chart_sale_data = [round(r.sale_price, 2) for r in recipes_to_display]

    # --- INGREDIENTES ---
    all_ingredients = Ingredient.query.filter_by(user_id=current_user.id).all()

    # Ordenar ingredientes
    if ingredient_sort == 'asc':
        sorted_ingredients = sorted(all_ingredients, key=lambda x: x.base_price)
    else:  # desc ou qualquer outro valor
        sorted_ingredients = sorted(all_ingredients, key=lambda x: x.base_price, reverse=True)

    # Tratar ingredient_limit seguro
    if ingredient_limit.isdigit():
        ingredients_to_display = sorted_ingredients[:int(ingredient_limit)]
    else:
        ingredients_to_display = sorted_ingredients  # 'all' ou vazio

    ingredient_chart_labels = [i.name for i in ingredients_to_display]
    ingredient_chart_data = [round(i.base_price, 2) for i in ingredients_to_display]

    return render_template(
        'reports.html',
        title="Relatórios",
        recipes=recipes_to_display,
        recipe_chart_labels=recipe_chart_labels,
        recipe_chart_cost_data=recipe_chart_cost_data,
        recipe_chart_sale_data=recipe_chart_sale_data,
        ingredient_chart_labels=ingredient_chart_labels,
        ingredient_chart_data=ingredient_chart_data,
        recipe_sort=recipe_sort,
        recipe_limit=recipe_limit,
        ingredient_sort=ingredient_sort,
        ingredient_limit=ingredient_limit
    )

# --- ROTAS DE TERMOS E PRIVACIDADE ---
@main.route('/terms')
def terms():
    return render_template('terms.html', title="Termos de Serviço")

@main.route('/privacy')
def privacy():
    return render_template('privacy.html', title="Política de Privacidade")

# --- FUNÇÕES AUXILIARES ---
def calculate_base_price(package_price, package_quantity, package_unit):
    if package_unit in ['kg', 'l']:
        base_price = package_price / package_quantity
        base_unit = package_unit[0]
    elif package_unit in ['g', 'ml']:
        base_price = package_price / package_quantity
        base_unit = package_unit
    else:
        base_price = package_price / package_quantity
        base_unit = 'un'
    return base_price, base_unit

def calculate_ingredient_cost_in_recipe(ingredient, quantity, unit_used):
    if ingredient.base_unit == unit_used:
        return ingredient.base_price * quantity
    elif ingredient.base_unit == 'g' and unit_used == 'kg':
        return ingredient.base_price * (quantity * 1000)
    elif ingredient.base_unit == 'ml' and unit_used == 'l':
        return ingredient.base_price * (quantity * 1000)
    elif ingredient.base_unit in ['kg', 'l'] and unit_used in ['g', 'ml']:
        return ingredient.base_price * (quantity / 1000)
    else:
        return ingredient.base_price * quantity
