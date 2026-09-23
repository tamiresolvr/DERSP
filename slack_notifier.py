import requests


class SlackNotifier:

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def enviar(self, mensagem):
        if not self.webhook_url:
            print("⚠️ Webhook do Slack não configurado.")
            return

        resposta = requests.post(
            self.webhook_url,
            json={
                "text": mensagem
            }
        )

        resposta.raise_for_status()
        print("Mensagem enviada para Slack")

    # Apelido para manter compatibilidade com as chamadas do main.py
    def enviar_mensagem(self, mensagem):
        self.enviar(mensagem)