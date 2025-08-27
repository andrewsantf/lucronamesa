from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from config import Config  # Importa a classe Config que criamos

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message_category = 'info'

def create_app():
    app = Flask(__name__)
    
    # ESTA LINHA AGORA CARREGA TODAS AS CONFIGURAÇÕES (SECRET_KEY, DATABASE_URL, ETC.)
    app.config.from_object(Config)

    # As linhas que definiam a SECRET_KEY e a DATABASE_URI aqui foram removidas.

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    return app