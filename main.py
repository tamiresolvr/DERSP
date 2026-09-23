"""
main.py - Automação de Indicação de Condutor no DER-SP
------------------------------------------------------
1. Busca cards pendentes no Jira (Projeto BOBA).
2. Localiza as pastas e valida os documentos no Google Drive.
3. Acessa o portal do DER-SP via Playwright (Placa + AIT).
4. Preenche os dados do condutor (CNH, Validade CNH, UF) extraídos do Jira.
5. Anexa a documentação e conclui a indicação.
6. Atualiza o Jira (comentário, método e status 'Enviada para órgão').
7. Registra no relatório CSV e envia notificação no Slack.
"""
import calendar  
import csv
from datetime import datetime
import os
import sys
import time

from dotenv import load_dotenv
import requests


from der_automation import DERAutomation
from drive_helper import DriveHelper
from jira_client import JiraClient
from slack_notifier import SlackNotifier

# Mapeamento dinâmico para o Playwright funcionar no PyInstaller (.exe)
if getattr(sys, 'frozen', False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(sys._MEIPASS, "ms-playwright")
else:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.path.dirname(__file__), "ms-playwright")

# --- SUBTITUA O CARREGAMENTO ANTIGO POR ESTE BLOCO ---

# Mapeamento do caminho do arquivo .env
if getattr(sys, 'frozen', False):
    # Procura o .env na pasta temporária descompactada pelo PyInstaller
    caminho_env = os.path.join(sys._MEIPASS, ".env")
    if not os.path.exists(caminho_env):
        # Fallback: procura o .env na mesma pasta onde está o executável .exe
        caminho_env = os.path.join(os.path.dirname(sys.executable), ".env")
else:
    caminho_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

load_dotenv(caminho_env)

# Garante que NUNCA seja None (evita o erro 'NoneType' object has no attribute 'rstrip')
JIRA_URL = (os.getenv("JIRA_URL") or "").strip()
JIRA_EMAIL = (os.getenv("JIRA_EMAIL") or "").strip()
JIRA_API_TOKEN = (os.getenv("JIRA_API_TOKEN") or "").strip()
JIRA_JQL = (os.getenv("JIRA_JQL") or 'project = "BOBA" AND status = "Aguardando Indicação"').strip()

SLACK_WEBHOOK_URL = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
HEADLESS = os.getenv("HEADLESS", "False").strip().lower() == "true"

def notificar_erro_slack(card_key: str, ait: str, erro: Exception):
    """Envia o alerta formatado para o Slack via Webhook."""
    if not SLACK_WEBHOOK_URL:
        return

    detalhe_erro = str(erro)

    if "Erro do Portal DER:" in detalhe_erro:
        titulo_tipo = "⚠️ Validação do Portal DER-SP"
        mensagem_detalhada = detalhe_erro.replace("Erro do Portal DER:", "").strip()
    else:
        titulo_tipo = f"🚨 Falha Técnica ({type(erro).__name__})"
        mensagem_detalhada = detalhe_erro[:500]

    mensagem = {
        "text": "🚨 *ERRO NA AUTOMAÇÃO DER-SP*",
        "attachments": [
            {
                "color": "#FF0000",
                "fields": [
                    {"title": "Card / BOBA", "value": str(card_key), "short": True},
                    {"title": "AIT", "value": str(ait), "short": True},
                    {"title": "Tipo do Erro", "value": titulo_tipo, "short": False},
                    {"title": "Mensagem / Motivo", "value": f"```{mensagem_detalhada}```", "short": False},
                    {"title": "Print da Tela", "value": "📸 _Print do erro anexado diretamente no Card do Jira._", "short": False}
                ]
            }
        ]
    }
    
    for tentativa in range(3):
        try:
            res = requests.post(SLACK_WEBHOOK_URL, json=mensagem, timeout=15)
            if res.status_code == 200:
                break
        except Exception as e:
            print(f"⚠️ Tentativa {tentativa + 1}/3 - Falha ao enviar para o Slack: {e}")
            time.sleep(2)


def registrar_csv(card_chave: str, ait: str, placa: str, protocolo: str):
    """Registra a conclusão em uma planilha CSV mensal na pasta Documentos."""
    agora = datetime.now()

    # Pega a pasta Documentos de qualquer usuário dinamicamente
    pasta_destino = os.path.join(os.path.expanduser("~"), "Documents")

    nome_arquivo = f"relatorio_der_{agora.strftime('%Y_%m')}.csv"
    caminho_completo = os.path.join(pasta_destino, nome_arquivo)

    file_exists = os.path.exists(caminho_completo)

    try:
        with open(
            caminho_completo, mode="a", newline="", encoding="utf-8-sig"
        ) as f:
            writer = csv.writer(f, delimiter=";")
            if not file_exists:
                writer.writerow(
                    ["Data/Hora", "Card Jira", "AIT", "Placa", "Protocolo DER"]
                )
            writer.writerow([
                agora.strftime("%Y-%m-%d %H:%M:%S"),
                card_chave,
                ait,
                placa,
                protocolo,
            ])
        print(
            f"📊 Card {card_chave} registrado no relatório CSV ({caminho_completo})."
        )
    except PermissionError:
        print(
            f"⚠️ Erro de permissão ao gravar em {caminho_completo}. Verifique se a planilha está aberta no Excel."
        )
    except Exception as e:
        print(f"⚠️ Falha ao salvar o relatório CSV: {e}")
def verificar_envio_mensal_slack_der(slack: SlackNotifier):
    """Envia o relatório CSV mensal acumulado para o Slack caso hoje seja o último dia do mês."""
    hoje = datetime.now().date()
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]

    # Verifica se hoje é o último dia do mês
    if hoje.day == ultimo_dia:
        pasta_destino = os.path.join(os.path.expanduser("~"), "Documents")
        caminho_csv = os.path.join(
            pasta_destino, f"relatorio_der_{hoje.strftime('%Y_%m')}.csv"
        )

        if os.path.exists(caminho_csv):
            print(
                "📅 Último dia do mês detectado! Enviando relatório CSV do DER-SP para o Slack..."
            )
            try:
                # Se o seu SlackNotifier envia mensagens simples via Webhook:
                msg = f"📊 *Relatório Consolidado de Indicações DER-SP - {hoje.strftime('%m/%Y')}*\n_O arquivo CSV do mês está disponível em Documents no computador de execução._"

                # Se a sua classe SlackNotifier possuir método para envio de arquivo, use-o aqui.
                if hasattr(slack, "enviar_arquivo"):
                    slack.enviar_arquivo(
                        caminho_csv,
                        f"📊 Relatório Mensal DER-SP - {hoje.strftime('%m/%Y')}",
                    )
                else:
                    slack.enviar_mensagem(msg)

                print("✅ Notificação/Relatório mensal enviado para o Slack!")
            except Exception as e:
                print(f"⚠️ Falha ao notificar o relatório mensal no Slack: {e}")        
def processar_ciclo():
    print("\n==================================================")
    print(f"🚀 INICIANDO CICLO DE PETICIONAMENTO DER-SP: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("==================================================")

    jira = JiraClient(JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN)
    drive = DriveHelper()
    slack = SlackNotifier(SLACK_WEBHOOK_URL) if SLACK_WEBHOOK_URL else None

    cards = jira.listar_cards_para_indicacao(JIRA_JQL)
    if not cards:
        print("ℹ️ Nenhum card retornado na busca do Jira.")
        return

    print(f"📋 Encontrados {len(cards)} cards para processar.\n")

    der = DERAutomation(headless=HEADLESS)
    der.iniciar()

    try:
        for c in cards:
            chave = c.get("chave")
            ait = c.get("ait")
            placa = c.get("placa")
            condutor = c.get("condutor", {})

            print(f"\n--- Processando Card: {chave} | AIT: {ait} | Placa: {placa} ---")

            if not ait or not placa:
                msg_erro = f"⚠️ Card {chave} ignorado: Faltam informações de AIT ou Placa."
                print(msg_erro)
                if slack:
                    slack.enviar_mensagem(msg_erro)
                continue

            if not condutor.get("cnh"):
                msg_erro = f"⚠️ Card {chave}: CNH do condutor não encontrada na descrição."
                print(msg_erro)
                if slack:
                    slack.enviar_mensagem(msg_erro)
                continue

            print(f"🔍 Buscando documentos no Drive para AIT {ait}...")
            pacote_docs = drive.obter_pacote_documentos(chave, ait)

            if not pacote_docs or (isinstance(pacote_docs, dict) and pacote_docs.get("_faltando")):
                faltando = pacote_docs.get("_faltando", []) if isinstance(pacote_docs, dict) else ["Pasta não encontrada"]
                msg_bloqueio = f"🛑 Card {chave} bloqueado: Documentos ausentes no Drive -> {', '.join(faltando)}"
                print(msg_bloqueio)
                jira.adicionar_comentario(chave, f"Automação DER-SP não executada: Documentação incompleta ({', '.join(faltando)})")
                if slack:
                    slack.enviar_mensagem(msg_bloqueio)
                continue

            try:
                der.abrir_eindicacao(placa, ait)
                der.preencher_condutor_e_anexar(condutor, pacote_docs)
                protocolo = der.concluir_peticionamento(placa, ait)

                if not protocolo:
                    raise Exception("Não foi possível gerar/obter o número de protocolo no DER-SP.")

                jira.adicionar_comentario(chave, f"Indicação realizada com sucesso no DER-SP. Comprovante/Protocolo: {protocolo}")
                jira.atualizar_metodo_online(chave)
                jira.atualizar_data_indicacao(chave)
                jira.atualizar_status_em_andamento(chave)

                msg_sucesso = (
                    f"✅ *Indicação enviada para o órgão (DER-SP)*\n\n"
                    f"    *Card:* {chave}\n"
                    f"    *AIT:* {ait}\n"
                    f"    *Placa:* {placa}\n"
                    f"    *Protocolo:* {protocolo}\n"
                    f"    *Método:* Online\n"
                    f"    *Status:* ENVIADA PARA ÓRGÃO"
                )
                print(msg_sucesso)
                if slack:
                    slack.enviar_mensagem(msg_sucesso)

                try:
                    registrar_csv(chave, ait, placa, protocolo)
                except Exception as err_csv:
                    print(f"⚠️ Aviso: Não foi possível gravar no CSV local: {err_csv}")

            except Exception as e:
                msg_falha = str(e)
                print(f"❌ Falha ao processar o card {chave}: {msg_falha}")

                # 1. Anexa o print no Jira se ele existir
                if os.path.exists("erro_tela.png"):
                    try:
                        jira.anexar_arquivo(chave, "erro_tela.png")
                    except Exception as err_jira:
                        print(f"⚠️ Falha ao anexar print no Jira: {err_jira}")

                msg_upper = msg_falha.upper()
                motivo_exato = None

                # 2. Identifica os cenários de Não Elegibilidade
                if "MULTA NAO E DE CONDUTOR" in msg_upper or "MULTA NÃO É DE CONDUTOR" in msg_upper:
                    motivo_exato = "INDICACAO NAO PERMITIDA. MULTA NAO E DE CONDUTOR"

                elif "ANALISE" in msg_upper or "ANÁLISE" in msg_upper or "JA EXISTE SOLICITACAO" in msg_upper or "JÁ EXISTE SOLICITAÇÃO" in msg_upper:
                    motivo_exato = "SOLICITACAO JA EXISTE EM ANALISE NO PORTAL DER"

                elif "BOLETO" in msg_upper or "20%" in msg_upper or "40%" in msg_upper:
                    motivo_exato = "SOLICITACAO DE BOLETO DETECTADA NO PORTAL DER"

                # 3. Se for um caso de Não Elegível, atualiza Jira e notifica Slack
                if motivo_exato:
                    print(f"🚫 Aplicando regra de não elegibilidade no card {chave}: {motivo_exato}")
                    
                    jira.atualizar_status_nao_elegivel(chave, motivo_exato)

                    if slack:
                        msg_slack = (
                            f"🚫 *Indicação Não Permitida (DER-SP)*\n\n"
                            f"    *Card:* {chave}\n"
                            f"    *AIT:* {ait}\n"
                            f"    *Placa:* {placa}\n"
                            f"    *Motivo:* {motivo_exato}\n"
                            f"    *Status Jira:* NÃO ELEGÍVEL"
                        )
                        slack.enviar_mensagem(msg_slack)
                else:
                    notificar_erro_slack(card_key=chave, ait=ait, erro=e)

                if os.path.exists("erro_tela.png"):
                    try:
                        os.remove("erro_tela.png")
                    except Exception:
                        pass

                continue

    finally:
        try:
            der.encerrar()
        except Exception:
            pass
# No final do lote ou quando não houver cards:
    if slack:
        verificar_envio_mensal_slack_der(slack)

    print("\n🏁 Execução do ciclo DER-SP concluída.")

def main():
    print("🤖 Robô DER-SP iniciado com sucesso! Executando a cada 30 minutos...")
    while True:
        try:
            processar_ciclo()
        except Exception as e:
            print(f"❌ Erro não tratado durante o ciclo: {e}")
            notificar_erro_slack(card_key="Geral / Sistema", ait="N/A", erro=e)

        print("\n😴 Aguardando 30 minutos para a próxima execução...")
        time.sleep(1800)


if __name__ == "__main__":
    main()