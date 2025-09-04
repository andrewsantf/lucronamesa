# NOVO CÓDIGO TEMPORÁRIO PARA app/__init__.py

from flask import Flask

def create_app():
    app = Flask(__name__)
    
    # Todas as extensões (db, mail, login_manager) estão desativadas por enquanto
    
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app