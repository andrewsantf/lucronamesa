import os

class Config:
    """
    Configurações da aplicação.
    Lê todas as informações sensíveis das variáveis de ambiente.
    """
    # CHAVE SECRETA: Lida diretamente do painel do Render
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # BANCO DE DADOS: Lida diretamente do painel do Render
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # STRIPE: Lidas diretamente do painel do Render
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
    STRIPE_MONTHLY_PLAN_PRICE_ID = os.environ.get('STRIPE_MONTHLY_PLAN_PRICE_ID')
    STRIPE_ANNUAL_PLAN_PRICE_ID = os.environ.get('STRIPE_ANNUAL_PLAN_PRICE_ID')

    # E-MAIL: Lidas diretamente do painel do Render
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Limite para alerta de custo
    COST_ALERT_THRESHOLD = 15.0