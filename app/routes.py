# NOVO CÓDIGO TEMPORÁRIO PARA app/routes.py

from flask import Blueprint, render_template

main = Blueprint('main', __name__)

# Rota principal para a landing page
@main.route('/')
def index():
    # Esta rota não depende de login nem do banco de dados
    return render_template('landing_page.html')

# Rota de login, simplificada para não usar o banco de dados
@main.route('/login')
def login():
    return "Página de Login (Teste)"