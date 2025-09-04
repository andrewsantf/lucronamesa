import stripe
from flask import render_template, redirect, url_for, flash, request, Blueprint, abort, session, current_app, Response
from app import db, bcrypt
from app.models import User, Ingredient, Recipe, PriceHistory, RecipeIngredient
from app.forms import RegistrationForm, LoginForm, IngredientForm, RecipeForm, UpdateProfileForm, ChangePasswordForm
from app.email import send_cost_alert_email
from app.nfe_client import buscar_nfe_por_chave
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
import re
import json
import os
from datetime import datetime, timedelta
from functools import wraps
import io
import csv
from twilio.rest import Client

main = Blueprint('main', __name__)

# --- Filtro Jinja2 para data ---
@main.app_template_filter()
def reverse_date(s):
    parts = str(s).split('-')
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return s

# --- DECORADOR ---
def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and not current_user.onboarding_complete:
            allowed_endpoints = ['main.onboarding', 'main.onboarding_example', 
                                 'main.ingredients', 'main.recipes', 'main.logout', 'main.importar_nfe']
            
            if request.endpoint in allowed_endpoints:
                return f(*args, **kwargs)
            else:
                return redirect(url_for('main.onboarding'))

        if not current_user.is_subscription_active:
            if current_user.subscription_status == 'trialing':
                flash('Seu período de teste expirou. Escolha um plano para continuar.', 'danger')
            else:
                flash('Sua assinatura não está ativa. Escolha um plano para continuar.', 'danger')
            return redirect(url_for('main.planos'))
            
        return f(*args, **kwargs)
    return decorated_function

# --- ROTA DO WHATSAPP ---
@main.route('/whatsapp', methods=['POST'])
def whatsapp_webhook():
    remetente = request.form.get('From')
    mensagem_recebida = request.form.get('Body', '').lower().strip()
    resposta = ""

    print(f"--- MENSAGEM DO WHATSAPP RECEBIDA ---\nDe: {remetente}\nMensagem: {mensagem_recebida}\n------------------------------------")

    numero_telefone = remetente.split(':')[-1] if ':' in remetente else remetente
    user = User.query.filter_by(phone=numero_telefone).first()

    if not user:
        resposta = "Olá! Não consegui encontrar o seu utilizador. Verifique se o número de telemóvel está registado corretamente no seu perfil LucroNaMesa."
    else:
        # --- LÓGICA DE MÚLTIPLOS COMANDOS ---
        if mensagem_recebida.startswith('custo '):
            nome_receita = mensagem_recebida.replace('custo ', '').strip()
            receita = Recipe.query.filter(func.lower(Recipe.name) == func.lower(nome_receita), Recipe.user_id == user.id).first()
            if receita:
                resposta = (f"Olá, {user.full_name.split()[0]}!\n\n"
                            f"O custo total da sua receita *'{receita.name}'* é de *R$ {receita.total_cost:.2f}*.")
            else:
                resposta = f"Desculpe, não encontrei a receita com o nome '{nome_receita}'. Por favor, verifique o nome exato."

        elif mensagem_recebida.startswith('venda '):
            nome_receita = mensagem_recebida.replace('venda ', '').strip()
            receita = Recipe.query.filter(func.lower(Recipe.name) == func.lower(nome_receita), Recipe.user_id == user.id).first()
            if receita:
                resposta = (f"Olá, {user.full_name.split()[0]}!\n\n"
                            f"O preço de venda sugerido para *'{receita.name}'* é de *R$ {receita.sale_price:.2f}*.")
            else:
                resposta = f"Desculpe, não encontrei a receita com o nome '{nome_receita}'. Por favor, verifique o nome exato."

        elif mensagem_recebida.startswith('lucro '):
            nome_receita = mensagem_recebida.replace('lucro ', '').strip()
            receita = Recipe.query.filter(func.lower(Recipe.name) == func.lower(nome_receita), Recipe.user_id == user.id).first()
            if receita:
                lucro = (receita.sale_price or 0) - (receita.total_cost or 0)
                resposta = (f"Olá, {user.full_name.split()[0]}!\n\n"
                            f"O lucro estimado para *'{receita.name}'* é de *R$ {lucro:.2f}*.")
            else:
                resposta = f"Desculpe, não encontrei a receita com o nome '{nome_receita}'. Por favor, verifique o nome exato."

        elif mensagem_recebida.startswith('ingredientes '):
            nome_receita = mensagem_recebida.replace('ingredientes ', '').strip()
            receita = Recipe.query.filter(func.lower(Recipe.name) == func.lower(nome_receita), Recipe.user_id == user.id).first()
            if receita:
                resposta = f"Ingredientes para a receita *'{receita.name}'*:\n\n"
                for item in receita.ingredients:
                    resposta += f"- {item.ingredient.name}: {item.quantity} {item.unit_used}\n"
            else:
                resposta = f"Desculpe, não encontrei a receita com o nome '{nome_receita}'. Por favor, verifique o nome exato."
        
        else:
            # Mensagem de ajuda atualizada
            resposta = (f"Olá, {user.full_name.split()[0]}! Comandos disponíveis:\n\n"
                        "➡️ *custo [nome da receita]*\n"
                        "➡️ *venda [nome da receita]*\n"
                        "➡️ *lucro [nome da receita]*\n"
                        "➡️ *ingredientes [nome da receita]*")

    # Envia a resposta de volta
    try:
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN')
        client = Client(account_sid, auth_token)
        message = client.messages.create(
                              body=resposta,
                              from_=request.form.get('To'),
                              to=remetente
                          )
        print(f"Resposta enviada com sucesso! SID: {message.sid}")
    except Exception as e:
        print(f"ERRO ao enviar resposta via Twilio: {e}")

    return '', 200

# --- ROTAS DE NF-e ---
@main.route('/nfe/importar', methods=['GET', 'POST'])
@login_required
@subscription_required
def importar_nfe():
    resultado = None
    ingredientes_utilizador = Ingredient.query.filter_by(author=current_user).order_by(Ingredient.name).all()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'buscar_nfe':
            chave_acesso = request.form.get('chave_acesso')
            if chave_acesso:
                resultado = buscar_nfe_por_chave(chave_acesso)
                if resultado and resultado.get('sucesso'):
                    session['nfe_produtos'] = resultado['dados']['produtos']
            else:
                flash('Por favor, insira uma chave de acesso.', 'warning')
        
        elif action == 'importar_produtos':
            try:
                produtos_nfe = session.get('nfe_produtos', [])
                if not produtos_nfe:
                    flash('Sessão expirada ou dados da NF-e não encontrados. Por favor, busque a nota novamente.', 'warning')
                    return redirect(url_for('main.importar_nfe'))

                ingredientes_importados = 0
                for i, produto in enumerate(produtos_nfe):
                    ingrediente_id_assoc = request.form.get(f'ingrediente_assoc_{i}')
                    
                    if ingrediente_id_assoc:
                        ingrediente_para_atualizar = Ingredient.query.get(ingrediente_id_assoc)
                        
                        if ingrediente_para_atualizar and ingrediente_para_atualizar.author == current_user:
                            novo_preco = float(produto['valorUnitario'])
                            nova_quantidade = float(produto['quantidade'])
                            nova_unidade = str(produto['unidade']).lower()

                            ingrediente_para_atualizar.package_price = novo_preco
                            ingrediente_para_atualizar.package_quantity = nova_quantidade
                            
                            if nova_unidade in ['dz', 'cx']:
                                nova_unidade = 'un'
                            
                            ingrediente_para_atualizar.package_unit = nova_unidade

                            ingrediente_para_atualizar.base_price, ingrediente_para_atualizar.base_unit = calculate_base_price(
                                novo_preco, nova_quantidade, nova_unidade
                            )

                            price_record = PriceHistory(
                                ingredient=ingrediente_para_atualizar,
                                price=novo_preco,
                                quantity=nova_quantidade,
                                unit=nova_unidade
                            )
                            db.session.add(price_record)
                            ingredientes_importados += 1
                
                if ingredientes_importados > 0:
                    db.session.commit()
                    flash(f'{ingredientes_importados} ingredientes foram atualizados com sucesso!', 'success')
                else:
                    flash('Nenhum ingrediente foi associado para importação.', 'info')

                session.pop('nfe_produtos', None)
                return redirect(url_for('main.dashboard', _anchor='ingredients-tab-pane'))

            except Exception as e:
                db.session.rollback()
                flash(f'Ocorreu um erro ao importar os produtos: {e}', 'danger')

    return render_template('import_nfe.html', 
                           title="Importar NF-e", 
                           resultado=resultado,
                           ingredientes=ingredientes_utilizador)

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
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user_data = {
            'full_name': form.full_name.data, 'email': form.email.data,
            'business_name': form.business_name.data, 'business_type': form.business_type.data,
            'phone': form.phone.data, 'password': hashed_password
        }
        if plan_from_form == 'trial':
            user = User(**user_data, plan_type='Trial', subscription_status='trialing',
                        trial_ends_at=datetime.utcnow() + timedelta(days=7))
        else:
            user = User(**user_data, plan_type=None, subscription_status='pending')
        db.session.add(user)
        db.session.commit()
        login_user(user, remember=True)
        if plan_from_form == 'trial':
            flash('Sua conta foi criada com sucesso! Vamos começar.', 'success')
            return redirect(url_for('main.onboarding'))
        else:
            flash('Sua conta foi criada! Agora escolha seu plano para ativar a assinatura.', 'info')
            return redirect(url_for('main.planos'))
    return render_template('register.html', form=form, title="Crie sua Conta", plan=plan)

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.login'))

# --- ROTAS DE ONBOARDING ---
@main.route('/onboarding')
@login_required
def onboarding():
    if current_user.onboarding_complete:
        return redirect(url_for('main.dashboard'))
    if current_user.has_created_ingredient and current_user.has_created_recipe:
        current_user.onboarding_complete = True
        db.session.commit()
        flash('Parabéns! Você completou os passos iniciais.', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('onboarding.html', title="Bem-vindo ao LucroNaMesa")

@main.route('/onboarding/preencher-exemplo', methods=['POST'])
@login_required
def onboarding_example():
    try:
        ing1 = Ingredient.query.filter_by(author=current_user, name="Farinha de Trigo (Exemplo)").first()
        if not ing1:
            ing1 = Ingredient(name="Farinha de Trigo (Exemplo)", package_price=5.50, package_quantity=1, package_unit='kg', author=current_user)
            ing1.base_price, ing1.base_unit = calculate_base_price(ing1.package_price, ing1.package_quantity, ing1.package_unit)
            db.session.add(ing1)
        ing2 = Ingredient.query.filter_by(author=current_user, name="Ovos (Exemplo)").first()
        if not ing2:
            ing2 = Ingredient(name="Ovos (Exemplo)", package_price=12.00, package_quantity=12, package_unit='un', author=current_user)
            ing2.base_price, ing2.base_unit = calculate_base_price(ing2.package_price, ing2.package_quantity, ing2.package_unit)
            db.session.add(ing2)
        db.session.flush()
        recipe_ex = Recipe.query.filter_by(author=current_user, name="Bolo Simples (Exemplo)").first()
        if not recipe_ex:
            cost1 = calculate_ingredient_cost_in_recipe(ing1, 300, 'g')
            cost2 = calculate_ingredient_cost_in_recipe(ing2, 3, 'un')
            total_cost_ex = cost1 + cost2
            profit_margin_ex = 150.0
            yield_quantity_ex = 8.0
            sale_price_ex = total_cost_ex * (1 + profit_margin_ex / 100)
            cost_per_serving_ex = total_cost_ex / yield_quantity_ex
            recipe_ex = Recipe(name="Bolo Simples (Exemplo)", preparation_steps="1. Misture tudo.\n2. Asse.", yield_quantity=yield_quantity_ex, yield_unit="fatias", loss_percentage=5, profit_margin=profit_margin_ex, author=current_user,total_cost=total_cost_ex,sale_price=sale_price_ex,cost_per_serving=cost_per_serving_ex)
            db.session.add(recipe_ex)
            db.session.flush()
            ri1 = RecipeIngredient(recipe_id=recipe_ex.id, ingredient_id=ing1.id, quantity=300, unit_used='g')
            ri2 = RecipeIngredient(recipe_id=recipe_ex.id, ingredient_id=ing2.id, quantity=3, unit_used='un')
            db.session.add(ri1)
            db.session.add(ri2)
        current_user.has_created_ingredient = True
        current_user.has_created_recipe = True
        current_user.onboarding_complete = True
        db.session.commit()
        flash('Dados de exemplo foram adicionados! Explore o dashboard para ver o resultado.', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocorreu um erro ao criar os dados de exemplo: {e}', 'danger')
    return redirect(url_for('main.dashboard'))

@main.route('/welcome/mensal')
@login_required
def welcome_mensal():
    return redirect(url_for('main.criar_assinatura', plan='mensal'))
@main.route('/welcome/anual')
@login_required
def welcome_anual():
    return redirect(url_for('main.criar_assinatura', plan='anual'))
@main.route('/gerenciar_assinatura')
@login_required
def gerenciar_assinatura():
    return redirect(url_for('main.planos'))
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
        
@main.route('/dashboard')
@login_required
@subscription_required
def dashboard():
    period = request.args.get('period', '30d')
    end_date = datetime.utcnow()
    if period == '7d':
        start_date = end_date - timedelta(days=7)
    elif period == 'month':
        start_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = end_date - timedelta(days=30)
        period = '30d'
    prev_end_date = start_date - timedelta(seconds=1)
    prev_start_date = prev_end_date - (end_date - start_date)
    
    all_recipes_list = Recipe.query.filter_by(user_id=current_user.id).order_by(Recipe.name).all()
    all_ingredients_list = Ingredient.query.filter_by(user_id=current_user.id).order_by(Ingredient.name).all()
    recipes_current_period = Recipe.query.filter(Recipe.user_id == current_user.id, Recipe.created_at.between(start_date, end_date)).all()
    recipes_prev_period = Recipe.query.filter(Recipe.user_id == current_user.id, Recipe.created_at.between(prev_start_date, prev_end_date)).all()
    
    for r in recipes_current_period: r.profit = r.sale_price - r.total_cost if r.sale_price and r.total_cost is not None else 0
    for r in recipes_prev_period: r.profit = r.sale_price - r.total_cost if r.sale_price and r.total_cost is not None else 0
    current_profit = sum(r.profit for r in recipes_current_period)
    prev_profit = sum(r.profit for r in recipes_prev_period)
    profit_change = 0
    if prev_profit > 0:
        profit_change = ((current_profit - prev_profit) / prev_profit) * 100
    current_recipes_count = len(recipes_current_period)
    prev_recipes_count = len(recipes_prev_period)
    recipes_count_change = 0
    if prev_recipes_count > 0:
        recipes_count_change = ((current_recipes_count - prev_recipes_count) / prev_recipes_count) * 100
    kpis = {
        'total_profit': {'value': current_profit, 'change': profit_change},
        'recipes_created': {'value': current_recipes_count, 'change': recipes_count_change},
    }
    
    alerts = []
    for ingredient in all_ingredients_list:
        history = sorted(ingredient.price_history, key=lambda x: x.recorded_at, reverse=True)
        if len(history) >= 2:
            if history[0].quantity > 0 and history[1].quantity > 0:
                latest_price_per_unit = history[0].price / history[0].quantity
                previous_price_per_unit = history[1].price / history[1].quantity
                
                if previous_price_per_unit > 0 and (latest_price_per_unit / previous_price_per_unit - 1) > 0.10:
                    if ingredient.last_alerted_at and (datetime.utcnow() - ingredient.last_alerted_at < timedelta(minutes=30)):
                        percentage_increase = (latest_price_per_unit / previous_price_per_unit - 1) * 100
                        alerts.append({
                            "type": "cost",
                            "message": f"O custo de '{ingredient.name}' subiu {percentage_increase:.0f}%. Considere revisar suas receitas.",
                            "link": url_for('main.edit_ingredient', ingredient_id=ingredient.id)
                        })
    
    most_profitable_recipe = max(recipes_current_period, key=lambda r: r.profit, default=None)
    
    top_3_profitable = sorted(recipes_current_period, key=lambda r: r.profit, reverse=True)[:3]
    top_3_costly = sorted(recipes_current_period, key=lambda r: r.total_cost, reverse=True)[:3]
    
    trend_ingredient = max(all_ingredients_list, key=lambda i: i.base_price, default=None)
    trend_labels, trend_data = [], []
    if trend_ingredient:
        price_history = PriceHistory.query.filter(
            PriceHistory.ingredient_id == trend_ingredient.id,
            PriceHistory.recorded_at.between(start_date, end_date)
        ).order_by(PriceHistory.recorded_at.asc()).all()
        trend_labels = [h.recorded_at.strftime('%d/%m') for h in price_history]
        trend_data = [round(h.price / h.quantity, 2) for h in price_history if h.quantity > 0]
    
    chart_recipes = sorted(recipes_current_period, key=lambda r: r.profit, reverse=True)[:7]
    chart_labels = [r.name for r in chart_recipes]
    chart_data_profit = [round(r.profit, 2) for r in chart_recipes]
    chart_data_cost = [round(r.total_cost, 2) for r in chart_recipes]

    return render_template(
        'dashboard.html', title="Dashboard", recipes=all_recipes_list, ingredients=all_ingredients_list,
        kpis=kpis, alerts=alerts, most_profitable_recipe=most_profitable_recipe,
        top_3_profitable=top_3_profitable, top_3_costly=top_3_costly,
        trend_ingredient=trend_ingredient, trend_labels=trend_labels, trend_data=trend_data,
        chart_labels=chart_labels, chart_data_profit=chart_data_profit,
        chart_data_cost=chart_data_cost, active_period=period
    )

@main.route('/ingredients', methods=['GET', 'POST'])
@login_required
@subscription_required
def ingredients():
    form = IngredientForm()
    if form.validate_on_submit():
        package_price = float(str(form.package_price.data).replace(',', '.'))
        package_quantity = float(str(form.package_quantity.data).replace(',', '.'))
        base_price, base_unit = calculate_base_price(package_price, package_quantity, form.package_unit.data)
        ingredient = Ingredient(name=form.name.data, package_price=package_price, package_quantity=package_quantity, package_unit=form.package_unit.data, base_price=base_price, base_unit=base_unit, author=current_user)
        db.session.add(ingredient)
        price_record = PriceHistory(ingredient=ingredient, price=package_price, quantity=package_quantity, unit=form.package_unit.data)
        db.session.add(price_record)
        if not current_user.has_created_ingredient:
            current_user.has_created_ingredient = True
        db.session.commit()
        flash('Ingrediente adicionado com sucesso!', 'success')
        return redirect(url_for('main.dashboard', _anchor='ingredients-tab-pane'))
    return render_template('ingredients.html', form=form, title="Adicionar Ingrediente")

@main.route('/ingredient/<int:ingredient_id>/edit', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_ingredient(ingredient_id):
    ingredient = Ingredient.query.get_or_404(ingredient_id)
    if ingredient.author != current_user:
        abort(403)
    
    form = IngredientForm()
    
    if form.validate_on_submit():
        old_package_price = ingredient.package_price
        old_package_quantity = ingredient.package_quantity
        old_package_unit = ingredient.package_unit

        new_package_price = float(str(form.package_price.data).replace(',', '.'))
        new_package_quantity = float(str(form.package_quantity.data).replace(',', '.'))
        new_package_unit = form.package_unit.data
        
        price_changed = (old_package_price != new_package_price or
                         old_package_quantity != new_package_quantity or
                         old_package_unit != new_package_unit)
        
        if price_changed:
            old_base_price, _ = calculate_base_price(old_package_price, old_package_quantity, old_package_unit)
            new_base_price, _ = calculate_base_price(new_package_price, new_package_quantity, new_package_unit)

            if old_base_price > 0 and new_base_price > old_base_price:
                increase_percentage = ((new_base_price - old_base_price) / old_base_price) * 100
                threshold = current_app.config.get('COST_ALERT_THRESHOLD', 15.0)
                
                if increase_percentage > threshold:
                    send_cost_alert_email(
                        user=current_user,
                        ingredient=ingredient,
                        old_price=old_package_price,
                        old_unit=old_package_unit,
                        new_price=new_package_price,
                        new_unit=new_package_unit,
                        increase_percentage=increase_percentage
                    )
                    # flash(f'Detectamos um aumento de {increase_percentage:.0f}% no custo de "{ingredient.name}". Um alerta foi enviado para o seu e-mail.', 'warning')
                    ingredient.last_alerted_at = datetime.utcnow()

            price_record = PriceHistory(
                ingredient=ingredient,
                price=new_package_price,
                quantity=new_package_quantity,
                unit=new_package_unit
            )
            db.session.add(price_record)

        ingredient.name = form.name.data
        ingredient.package_price = new_package_price
        ingredient.package_quantity = new_package_quantity
        ingredient.package_unit = new_package_unit
        ingredient.base_price, ingredient.base_unit = calculate_base_price(
            ingredient.package_price, ingredient.package_quantity, ingredient.package_unit)
        
        db.session.commit()
        
        flash('Ingrediente atualizado com sucesso!', 'success')
        return redirect(url_for('main.dashboard', _anchor='ingredients-tab-pane'))
    
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
    return redirect(url_for('main.dashboard', _anchor='ingredients-tab-pane'))

@main.route('/recipes', methods=['GET', 'POST'])
@login_required
@subscription_required
def recipes():
    form = RecipeForm()
    ingredients = Ingredient.query.filter_by(user_id=current_user.id).order_by(Ingredient.name).all()
    if request.method == 'POST' and form.validate_on_submit():
        ingredient_ids = request.form.getlist('ingredient_ids')
        if not ingredient_ids:
            flash('Uma receita precisa de pelo menos um ingrediente.', 'warning')
            return redirect(url_for('main.recipes'))
        
        total_cost, total_weight_g = 0, 0
        recipe_ingredients_to_add = []
        for ing_id in ingredient_ids:
            ingredient = Ingredient.query.get(ing_id)
            quantity_str = request.form.get(f'quantity_{ing_id}', '').replace(',', '.')
            if not quantity_str:
                flash(f'Erro: Informe a quantidade para "{ingredient.name}".', 'danger')
                return redirect(url_for('main.recipes'))
            quantity = float(quantity_str)
            unit_used = request.form.get(f'unit_{ing_id}')
            cost = calculate_ingredient_cost_in_recipe(ingredient, quantity, unit_used)
            total_cost += cost
            total_weight_g += convert_to_grams(quantity, unit_used)
            recipe_ingredient = RecipeIngredient(ingredient_id=ingredient.id, quantity=quantity, unit_used=unit_used)
            recipe_ingredients_to_add.append(recipe_ingredient)

        new_recipe = Recipe(
            name=form.name.data, author=current_user, yield_quantity=form.yield_quantity.data,
            yield_unit=form.yield_unit.data, loss_percentage=form.loss_percentage.data,
            profit_margin=form.profit_margin.data,
            preparation_steps=form.preparation_steps.data,
            total_cost=total_cost, 
            total_weight_g=total_weight_g
        )
        new_recipe.sale_price = new_recipe.total_cost * (1 + new_recipe.profit_margin / 100)
        new_recipe.cost_per_serving = new_recipe.total_cost / new_recipe.yield_quantity if new_recipe.yield_quantity > 0 else 0
        
        db.session.add(new_recipe)
        for item in recipe_ingredients_to_add:
            item.recipe = new_recipe
            db.session.add(item)
        
        if not current_user.has_created_recipe:
            current_user.has_created_recipe = True
        db.session.commit()
        
        flash('Receita criada e preço de venda calculado com sucesso!', 'success')
        return redirect(url_for('main.dashboard', _anchor='recipes-tab-pane'))
    return render_template('recipes.html', form=form, ingredients=ingredients, title="Adicionar Receita")

@main.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.author != current_user: abort(403)
    form = RecipeForm(obj=recipe)
    all_ingredients = Ingredient.query.filter_by(user_id=current_user.id).order_by(Ingredient.name).all()
    if request.method == 'POST' and form.validate_on_submit():
        RecipeIngredient.query.filter_by(recipe_id=recipe.id).delete()
        ingredient_ids = request.form.getlist('ingredient_ids')
        if not ingredient_ids:
            flash('Uma receita precisa de pelo menos um ingrediente.', 'warning')
            return redirect(url_for('main.edit_recipe', recipe_id=recipe.id))
        
        total_cost, total_weight_g = 0, 0
        for ing_id in ingredient_ids:
            ingredient = Ingredient.query.get(ing_id)
            quantity_str = request.form.get(f'quantity_{ing_id}', '').replace(',', '.')
            if not quantity_str:
                flash(f'Erro: Informe a quantidade para "{ingredient.name}".', 'danger')
                return redirect(url_for('main.edit_recipe', recipe_id=recipe.id))
            quantity = float(quantity_str)
            unit_used = request.form.get(f'unit_{ing_id}')
            cost = calculate_ingredient_cost_in_recipe(ingredient, quantity, unit_used)
            total_cost += cost
            total_weight_g += convert_to_grams(quantity, unit_used)
            new_recipe_ingredient = RecipeIngredient(recipe_id=recipe.id, ingredient_id=ingredient.id, quantity=quantity, unit_used=unit_used)
            db.session.add(new_recipe_ingredient)
            
        recipe.name = form.name.data
        recipe.yield_quantity = form.yield_quantity.data
        recipe.yield_unit = form.yield_unit.data
        recipe.loss_percentage = form.loss_percentage.data
        recipe.profit_margin = form.profit_margin.data
        recipe.preparation_steps = form.preparation_steps.data
        recipe.total_cost = total_cost
        recipe.total_weight_g = total_weight_g
        recipe.sale_price = total_cost * (1 + recipe.profit_margin / 100)
        recipe.cost_per_serving = total_cost / recipe.yield_quantity if recipe.yield_quantity > 0 else 0
        
        db.session.commit()
        flash('Receita atualizada com sucesso!', 'success')
        return redirect(url_for('main.dashboard', _anchor='recipes-tab-pane'))
        
    recipe_ingredients_dict = {ri.ingredient_id: {'quantity': ri.quantity, 'unit': ri.unit_used} for ri in recipe.ingredients}
    return render_template('edit_recipe.html', form=form, recipe=recipe, all_ingredients=all_ingredients,
                           recipe_ingredients=recipe_ingredients_dict, title=f"Editar '{recipe.name}'")

@main.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
@login_required
@subscription_required
def delete_recipe(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.author != current_user: abort(403)
    db.session.delete(recipe)
    db.session.commit()
    flash('Receita excluída com sucesso!', 'success')
    return redirect(url_for('main.dashboard', _anchor='recipes-tab-pane'))

@main.route('/recipe/<int:recipe_id>/detail')
@login_required
@subscription_required
def recipe_detail(recipe_id):
    recipe = Recipe.query.get_or_404(recipe_id)
    if recipe.author != current_user:
        abort(403)
    
    return render_template(
        'recipe_detail.html', 
        recipe=recipe, 
        title=recipe.name,
        calculate_ingredient_cost_in_recipe=calculate_ingredient_cost_in_recipe
    )

@main.route('/profile', methods=['GET', 'POST'])
@login_required
@subscription_required
def profile():
    profile_form = UpdateProfileForm()
    password_form = ChangePasswordForm()
    if profile_form.validate_on_submit() and profile_form.submit.data:
        current_user.full_name = profile_form.full_name.data; current_user.email = profile_form.email.data
        current_user.business_name = profile_form.business_name.data; current_user.business_type = profile_form.business_type.data
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

    if recipe_sort == 'cost_asc': sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost)
    elif recipe_sort == 'profit_desc': sorted_recipes = sorted(all_recipes, key=lambda x: x.profit, reverse=True)
    elif recipe_sort == 'margin_desc': sorted_recipes = sorted(all_recipes, key=lambda x: x.margin, reverse=True)
    else: sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost, reverse=True)

    recipes_for_table = sorted_recipes

    recipes_for_chart = sorted_recipes[:int(recipe_limit)] if recipe_limit.isdigit() else sorted_recipes
    recipe_chart_labels = [r.name for r in recipes_for_chart]
    recipe_chart_cost_data = [round(r.total_cost, 2) for r in recipes_for_chart]
    recipe_chart_sale_data = [round(r.sale_price or 0, 2) for r in recipes_for_chart]

    all_ingredients = Ingredient.query.filter_by(user_id=current_user.id).all()
    sorted_ingredients = sorted(all_ingredients, key=lambda x: x.base_price, reverse=(ingredient_sort == 'desc'))
    
    ingredients_for_chart = sorted_ingredients[:int(ingredient_limit)] if ingredient_limit.isdigit() else sorted_ingredients
    ingredient_chart_labels = [i.name for i in ingredients_for_chart]
    ingredient_chart_data = [round(i.base_price, 4) if i.base_price else 0 for i in ingredients_for_chart]

    return render_template(
        'reports.html',
        title="Relatórios",
        recipes=recipes_for_table,
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

@main.route('/reports/export/recipes')
@login_required
@subscription_required
def export_recipes_csv():
    recipe_sort = request.args.get('recipe_sort', 'profit_desc')
    all_recipes = Recipe.query.filter_by(user_id=current_user.id).all()
    for r in all_recipes:
        r.profit = r.sale_price - r.total_cost if r.sale_price else 0
        r.margin = (r.profit / r.sale_price * 100) if r.sale_price and r.sale_price > 0 else 0
    if recipe_sort == 'cost_asc': sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost)
    elif recipe_sort == 'profit_desc': sorted_recipes = sorted(all_recipes, key=lambda x: x.profit, reverse=True)
    elif recipe_sort == 'margin_desc': sorted_recipes = sorted(all_recipes, key=lambda x: x.margin, reverse=True)
    else: sorted_recipes = sorted(all_recipes, key=lambda x: x.total_cost, reverse=True)
    si = io.StringIO()
    cw = csv.writer(si)
    header = ['Nome da Receita', 'Custo Total (R$)', 'Preco de Venda (R$)', 'Lucro (R$)', 'Margem (%)', 'Rendimento', 'Custo por Porcao (R$)']
    cw.writerow(header)
    for recipe in sorted_recipes:
        row = [
            recipe.name, f"{recipe.total_cost:.2f}".replace('.', ','),
            f"{recipe.sale_price:.2f}".replace('.', ',') if recipe.sale_price else '0,00',
            f"{recipe.profit:.2f}".replace('.', ','), f"{recipe.margin:.1f}".replace('.', ',') if recipe.margin else '0,0',
            f"{recipe.yield_quantity} {recipe.yield_unit}",
            f"{recipe.cost_per_serving:.2f}".replace('.', ',') if recipe.cost_per_serving else '0,00'
        ]
        cw.writerow(row)
    output = si.getvalue()
    return Response(
        output, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=relatorio_de_rentabilidade.csv"}
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
    if package_quantity == 0: return 0, package_unit[0] if package_unit in ['kg', 'l'] else package_unit
    if package_unit == 'kg':
        return package_price / (package_quantity * 1000), 'g'
    elif package_unit == 'l':
        return package_price / (package_quantity * 1000), 'ml'
    elif package_unit in ['g', 'ml', 'un']:
        return package_price / package_quantity, package_unit
    return 0, 'un'
def calculate_ingredient_cost_in_recipe(ingredient, quantity, unit_used):
    cost = 0
    if not ingredient or not ingredient.base_price: return 0
    if ingredient.base_unit == unit_used:
        cost = ingredient.base_price * quantity
    elif ingredient.base_unit == 'g' and unit_used == 'kg':
        cost = ingredient.base_price * (quantity * 1000)
    elif ingredient.base_unit == 'ml' and unit_used == 'l':
        cost = ingredient.base_price * (quantity * 1000)
    elif ingredient.base_unit == 'kg' and unit_used == 'g':
         cost = ingredient.base_price * (quantity / 1000)
    elif ingredient.base_unit == 'l' and unit_used == 'ml':
         cost = ingredient.base_price * (quantity / 1000)
    elif ingredient.base_unit == 'un':
        cost = ingredient.base_price * quantity
    return cost
def convert_to_grams(quantity, unit):
    if unit in ['g', 'ml']:
        return quantity
    if unit in ['kg', 'l']:
        return quantity * 1000
    return 0