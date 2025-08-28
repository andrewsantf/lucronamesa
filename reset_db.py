from app import create_app, db

app = create_app()

with app.app_context():
    # Apaga todas as tabelas do banco
    db.drop_all()
    print("Todas as tabelas apagadas.")

    # Cria todas as tabelas novamente
    db.create_all()
    print("Banco de dados resetado com sucesso!")
