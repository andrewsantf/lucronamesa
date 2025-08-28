# Arquivo: config.py

import os
from dotenv import load_dotenv

# Encontra o caminho absoluto para o diretório raiz do projeto
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# --- CORREÇÃO IMPORTANTE ABAIXO ---
# Cria o caminho completo para a pasta 'instance', que é o local ideal para o banco de dados.
instance_path = os.path.join(basedir, 'instance')
# Garante que a pasta 'instance' exista. Se não existir, ela será criada.
os.makedirs(instance_path, exist_ok=True)


import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or '41Bf@732_G@bsnow010'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///site.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    STRIPE_PUBLIC_KEY = 'pk_test_51S0yE49Vhvx9REw5koODhv6JUdhlG9fYOGXNiPozz9Qt8Ufy2NP6L32FgfG9QjzBT7iHLmvMaOZZxyBjz8qiGWqn00JYKXQ8ld'  # Cole a chave pk_test_...
    STRIPE_SECRET_KEY = 'sk_test_51S0yE49Vhvx9REw5pbCFKRXxlS929KgKPCAsqJnYKLvLwfxtGAHPcS6UIJcdOldl4NXe3FeBdm6FVY37wesdW1vf000er3oPsY'   
    STRIPE_ANNUAL_PLAN_PRICE_ID = 'price_1S0zDh9Vhvx9REw5utKPFX5N' 
    STRIPE_MONTHLY_PLAN_PRICE_ID = 'price_1S0zGA9Vhvx9REw5NTUT3TbR' # <- NOVA LINHA
    STRIPE_WEBHOOK_SECRET = 'whsec_...'