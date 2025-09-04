# COPIE E COLE TODO ESTE CÓDIGO PARA DENTRO DE app/__init__.py

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_mail import Mail
# from apscheduler.schedulers.background import BackgroundScheduler # LINHA COMENTADA
from config import Config

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
migrate = Migrate()
mail = Mail()
# scheduler = BackgroundScheduler(daemon=True) # LINHA COMENTADA

def create_app(config_class=Config):
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

    # --- TODO O BLOCO DO SCHEDULER FOI REMOVIDO DAQUI ---
    # from app import tasks
    # if not scheduler.get_jobs():
    #     scheduler.add_job(
    #         func=tasks.gerar_relatorio_semanal, 
    #         trigger='cron', 
    #         day_of_week='mon', 
    #         hour=8, 
    #         id='relatorio_semanal_job', 
    #         args=[app]
    #     )
    # if not scheduler.running:
    #     scheduler.start()
    # ----------------------------------------------------

    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    return app