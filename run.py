from app import create_app
import logging

app = create_app()

# Configura logging para ver mensagens no Render
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    # Para desenvolvimento local
    app.run(debug=True)
