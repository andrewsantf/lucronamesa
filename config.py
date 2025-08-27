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


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'voce-precisa-mudar-isso'
    
    # Usa o caminho absoluto para o arquivo do banco de dados dentro da pasta 'instance'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(instance_path, 'site.db')
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False