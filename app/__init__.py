from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate # 1. Importe o Migrate
from config import Config

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'
migrate = Migrate() # 2. Crie a instância do Migrate aqui

def create_app():
    app = Flask(__name__)
    
    # Carrega todas as configurações do arquivo config.py
    app.config.from_object(Config)

    # Inicializa as extensões com a aplicação
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db) # 3. Inicialize o Migrate com o app e o db

    # Importa e registra o Blueprint
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # O user_loader e o create_all foram movidos para dentro da função
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # A linha abaixo deve ser removida ou usada com cautela.
    # Usar Flask-Migrate é a forma correta de gerenciar o banco de dados.
    # with app.app_context():
    #     db.create_all()

    return app