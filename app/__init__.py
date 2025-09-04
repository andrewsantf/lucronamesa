# COPIE E COLE TODO ESTE CÓDIGO PARA DENTRO DE app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_mail import Mail
from apscheduler.schedulers.background import BackgroundScheduler
from config import Config

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
migrate = Migrate()
mail = Mail()
scheduler = BackgroundScheduler(daemon=True)

def create_app(config_class=Config):
    print("-----> PONTO 1: Função create_app() foi chamada.") # Log 1
    app = Flask(__name__)
    
    app.config.from_object(config_class)

    app.config.update(
        MAIL_SERVER = os.environ.get('MAIL_SERVER'),
        MAIL_PORT = int(os.environ.get('MAIL_PORT', 587)),
        MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1'],
        MAIL_USERNAME = os.environ.get('MAIL_USERNAME'),
        MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    )
    
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    print("-----> PONTO 2: Todas as extensões Flask foram inicializadas.") # Log 2

    from app import tasks

    if not scheduler.get_jobs():
        print("-----> PONTO 3: Configurando o job do scheduler.") # Log 3
        scheduler.add_job(
            func=tasks.gerar_relatorio_semanal, 
            trigger='cron', 
            day_of_week='mon', 
            hour=8, 
            id='relatorio_semanal_job', 
            args=[app]
        )
        
    if not scheduler.running:
        print("-----> PONTO 4: Iniciando o scheduler.") # Log 4
        scheduler.start()

    print("-----> PONTO 5: Tentando registrar o blueprint 'main'.") # Log 5
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)
    print("-----> PONTO 6: O BLUEPRINT 'main' FOI REGISTRADO COM SUCESSO.") # Log 6

    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    print("-----> PONTO 7: Aplicação pronta para ser retornada.") # Log 7
    return app