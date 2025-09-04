# Arquivo: app/tasks.py (VERSÃO DE DEPURAÇÃO)

from datetime import datetime, timedelta
from .models import User, Recipe, PriceHistory
from .email import send_weekly_report_email

def gerar_relatorio_semanal(app):
    """
    Função de depuração para entender o fluxo do relatório.
    """
    with app.app_context():
        print(f"\n[{datetime.now()}] --- INÍCIO DA TAREFA DE RELATÓRIO SEMANAL ---")

        users = User.query.filter_by(subscription_status='active').all()
        if not users:
            print("  [INFO] Nenhum utilizador ativo encontrado. A encerrar tarefa.")
        
        for user in users:
            print(f"\n  A processar utilizador: {user.email}")
            
            uma_semana_atras = datetime.utcnow() - timedelta(days=7)

            # --- Diagnóstico das Receitas ---
            receitas_da_semana = Recipe.query.filter(
                Recipe.user_id == user.id,
                Recipe.created_at >= uma_semana_atras
            ).all()
            print(f"    [RECEITAS] Encontradas {len(receitas_da_semana)} receitas nos últimos 7 dias.")

            for receita in receitas_da_semana:
                lucro = (receita.sale_price or 0) - (receita.total_cost or 0)
                receita.lucro_calculado = lucro
            
            receitas_lucrativas_ordenadas = sorted(receitas_da_semana, key=lambda r: r.lucro_calculado, reverse=True)
            top_3_receitas = receitas_lucrativas_ordenadas[:3]
            print(f"    [RECEITAS] Top 3 receitas selecionadas: {[r.name for r in top_3_receitas]}")


            # --- Diagnóstico dos Ingredientes ---
            ingredientes_do_utilizador = user.ingredients
            variacoes = []
            print(f"    [INGREDIENTES] A analisar {len(ingredientes_do_utilizador)} ingredientes do utilizador.")
            
            for ingrediente in ingredientes_do_utilizador:
                historico_semanal = PriceHistory.query.filter(
                    PriceHistory.ingredient_id == ingrediente.id,
                    PriceHistory.recorded_at >= uma_semana_atras
                ).order_by(PriceHistory.recorded_at.asc()).all()
                
                # Apenas para depuração, vamos ver quantos registos de preço encontramos
                if len(historico_semanal) > 0:
                    print(f"      - Para '{ingrediente.name}', encontrados {len(historico_semanal)} registos de preço na semana.")

                if len(historico_semanal) >= 2:
                    primeiro_registo, ultimo_registo = historico_semanal[0], historico_semanal[-1]
                    if primeiro_registo.quantity > 0 and ultimo_registo.quantity > 0:
                        preco_antigo_unitario = primeiro_registo.price / primeiro_registo.quantity
                        preco_novo_unitario = ultimo_registo.price / ultimo_registo.quantity
                        if preco_antigo_unitario > 0:
                            variacao_percentual = ((preco_novo_unitario - preco_antigo_unitario) / preco_antigo_unitario) * 100
                            variacoes.append({'nome': ingrediente.name, 'variacao': variacao_percentual})

            ingredientes_maior_variacao = sorted(variacoes, key=lambda i: i['variacao'], reverse=True)[:3]
            print(f"    [INGREDIENTES] Top 3 variações selecionadas: {ingredientes_maior_variacao}")

            # --- Diagnóstico da Decisão de Envio ---
            print(f"  [DECISÃO] Condição de envio: len(top_3_receitas) > 0 ({len(top_3_receitas) > 0}) OU len(ingredientes_maior_variacao) > 0 ({len(ingredientes_maior_variacao) > 0})")
            if top_3_receitas or ingredientes_maior_variacao:
                print("  [AÇÃO] A condição foi cumprida. A chamar a função de envio de e-mail...")
                send_weekly_report_email(app, user, top_3_receitas, ingredientes_maior_variacao)
            else:
                print("  [AÇÃO] A condição NÃO foi cumprida. E-mail não será enviado.")
            
        print(f"\n[{datetime.now()}] --- FIM DA TAREFA ---")