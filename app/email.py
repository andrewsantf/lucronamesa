from flask import current_app, render_template, url_for
from flask_mail import Message
from app import mail
from threading import Thread

def send_async_email(app, msg):
    """Função para ser executada em uma thread separada para não bloquear a aplicação."""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"FALHA ao enviar e-mail em segundo plano: {e}")

def send_cost_alert_email(user, ingredient, old_price, old_unit, new_price, new_unit, increase_percentage):
    """Monta e envia o e-mail de alerta de custo para o usuário."""
    app = current_app._get_current_object()
    subject = f"Alerta de Custo: O preço de '{ingredient.name}' subiu!"
    msg = Message(subject, sender=('LucroNaMesa', app.config['MAIL_USERNAME']), recipients=[user.email])
    msg.html = render_template('email/cost_alert.html',
                               user=user, ingredient=ingredient,
                               old_price=old_price, old_unit=old_unit,
                               new_price=new_price, new_unit=new_unit,
                               increase_percentage=increase_percentage)
    thr = Thread(target=send_async_email, args=[app, msg])
    thr.start()
    return thr

# --- NOVA FUNÇÃO ADICIONADA AQUI ---
def send_weekly_report_email(app, user, top_receitas, top_ingredientes):
    """Monta e envia o e-mail de relatório semanal."""
    with app.app_context():
        subject = "LucroNaMesa: O seu resumo de desempenho da semana"
        msg = Message(subject, sender=('LucroNaMesa', app.config['MAIL_USERNAME']), recipients=[user.email])
        msg.html = render_template('email/relatorio_semanal.html',
                                   user=user,
                                   top_receitas=top_receitas,
                                   top_ingredientes=top_ingredientes)
        # Para relatórios, podemos enviá-los de forma assíncrona, mas dentro da mesma thread da tarefa.
        # Simplifica o processo, já que a tarefa já corre em segundo plano.
        try:
            mail.send(msg)
            print(f"    -> E-mail de relatório enviado com sucesso para {user.email}")
        except Exception as e:
            print(f"    -> FALHA ao enviar e-mail de relatório para {user.email}: {e}")