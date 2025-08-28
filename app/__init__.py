def create_app():
    app = Flask(__name__)
    
    # Carrega todas as configurações
    app.config.from_object(Config)

    # Inicializa as extensões
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    # Importa e registra o Blueprint
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # === ROTA TEMPORÁRIA PARA CRIAR COLUNAS NO RENDER ===
    @app.route("/fix_columns")
    def fix_columns():
        try:
            db.session.execute(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS plan_type VARCHAR(50);'
            )
            db.session.execute(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50);'
            )
            db.session.execute(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP;'
            )
            db.session.execute(
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100);'
            )
            db.session.commit()
            return "Colunas criadas com sucesso!"
        except Exception as e:
            return f"Erro: {e}"

    return app
