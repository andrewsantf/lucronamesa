import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

instance_path = os.path.join(basedir, 'instance')
os.makedirs(instance_path, exist_ok=True)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or '41Bf@732_G@bsnow010'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(instance_path, "site.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuração de URL reativada para os e-mails funcionarem corretamente
    # Para o ambiente de desenvolvimento local
    SERVER_NAME = '127.0.0.1:5000'
    # Em produção (no Render, por exemplo), você mudaria para:
    # SERVER_NAME = 'lucronamesa.onrender.com'
    APPLICATION_ROOT = '/'
    PREFERRED_URL_SCHEME = 'http' # Em produção com HTTPS, mude para 'https'

    # Configurações do Stripe
    STRIPE_PUBLIC_KEY = 'pk_test_51S0yE49Vhvx9REw5koODhv6JUdhlG9fYOGXNiPozz9Qt8Ufy2NP6L32FgfG9QjzBT7iHLmvMaOZZxyBjz8qiGWqn00JYKXQ8ld'
    STRIPE_SECRET_KEY = 'sk_test_51S0yE49Vhvx9REw5pbCFKRXxlS929KgKPCAsqJnYKLvLwfxtGAHPcS6UIJcdOldl4NXe3FeBdm6FVY37wesdW1vf000er3oPsY'   
    STRIPE_ANNUAL_PLAN_PRICE_ID = 'price_1S0zDh9Vhvx9REw5utKPFX5N' 
    STRIPE_MONTHLY_PLAN_PRICE_ID = 'price_1S0zGA9Vhvx9REw5NTUT3TbR'
    STRIPE_WEBHOOK_SECRET = 'whsec_...'

    # Configurações de E-mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    COST_ALERT_THRESHOLD = 15.0