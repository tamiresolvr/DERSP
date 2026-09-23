# 🤖 Automação DER-SP & Integração Jira

Uma automação em Python desenvolvida para simplificar e acelerar o monitoramento de processos no portal do **DER-SP (Departamento de Estradas de Rodagem de São Paulo)**, integrando os dados extraídos diretamente com o **Jira**.

O objetivo do projeto foi substituir a verificação manual de status por um robô autônomo que roda em background, economizando tempo operacional e evitando falhas de acompanhamento.

---

## 💡 O que o robô faz?

* **Navegação Autônoma:** Acessa o portal do DER-SP utilizando **Playwright** (modo headless/silencioso).
* **Autenticação Segura:** Realiza login automático consumindo credenciais protegidas via variáveis de ambiente.
* **Extração de Dados:** Raspagem de informações essenciais de processos e chamados.
* **Integração com Jira:** Cria e atualiza cards/tickets automaticamente via API REST para a equipe acompanhar o fluxo de trabalho.
* **Execução em Ciclo:** Programado para rodar verificações periódicas sem necessidade de intervenção humana.

---

## 🛠️ Tecnologias Utilizadas

* **Python 3.13** — Linguagem principal.
* **Playwright** — Automação web e scraping de alta performance.
* **Python-Decouple / PyDOTENV** — Gestão segura de variáveis de ambiente.
* **Requests / Jira API** — Comunicação com a API do Jira.
* **PyInstaller** — Empacotamento do projeto em executável executável e portátil (`.exe`).

---

## 🚀 Como rodar o projeto localmente

### Pré-requisitos
* Python 3.10+ instalado.
* Git instalado.

### Passo a passo

# 1. Baixa e entra na pasta do projeto
git clone https://github.com/tamiresolvr/DERSP.git
cd DERSP

# 2. Cria e ativa o ambiente virtual
python -m venv .venv
.\.venv\Scripts\activate

# 3. Instala todas as bibliotecas necessárias
pip install -r requirements.txt
python -m playwright install

# 4. Cria o .env.example 
# E cria o seu .env com suas senhas reais para rodar o projeto
