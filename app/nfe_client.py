# Arquivo: app/nfe_client.py

import json
import os
from flask import current_app

def buscar_nfe_por_chave(chave_acesso):
    """
    Busca os dados de uma NF-e.
    ATUALMENTE: Lê um ficheiro de exemplo local para simular a resposta da API.
    FUTURAMENTE: Irá fazer uma chamada real à API do NFe.io.
    """
    print(f"A 'buscar' dados para a chave de acesso: {chave_acesso}")

    try:
        # Constrói o caminho para o nosso ficheiro de exemplo
        caminho_ficheiro = os.path.join(current_app.root_path, 'static', 'mock_data', 'nfe_example.json')

        with open(caminho_ficheiro, 'r', encoding='utf-8') as f:
            dados_nfe = json.load(f)
        
        print("Dados do ficheiro de exemplo lidos com sucesso.")
        return {"sucesso": True, "dados": dados_nfe}

    except FileNotFoundError:
        erro_msg = "Ficheiro de simulação nfe_example.json não encontrado."
        print(f"ERRO: {erro_msg}")
        return {"sucesso": False, "erro": erro_msg}
    except Exception as e:
        erro_msg = f"Ocorreu um erro inesperado ao ler o ficheiro de simulação: {e}"
        print(f"ERRO: {erro_msg}")
        return {"sucesso": False, "erro": erro_msg}