from app import create_app
from flask_migrate import upgrade
from flask import Flask
import logging

app = create_app()

# Configura logging para ver mensagens no Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_migrations():
    """Aplica migrations automaticamente, mas ignora erros de duplicidade."""
    try:
        with app.app_context():
            logger.info("Aplicando migrations automáticas...")
            upgrade()
            logger.info("Migrations aplicadas com sucesso!")
    except Exception as e:
        logger.warning(f"Erro ao aplicar migrations (pode já ter sido aplicado): {e}")

# Aplica migrations quando o app iniciar
apply_migrations()

if __name__ == '__main__':
    app.run(debug=True)
