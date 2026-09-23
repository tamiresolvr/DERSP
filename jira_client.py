"""
jira_client.py
Busca no Jira os cards do projeto BOBA que precisam de indicação de condutor,
extraindo AIT, Placa e dados do condutor (CNH, Validade, UF).
"""

import os

import requests
import time
import re
import json
from datetime import datetime
from unidecode import unidecode


def _norm(texto: str) -> str:
    """Normaliza texto para comparação: minúsculo, sem acento, sem espaço extra."""
    if texto is None:
        return ""
    return unidecode(str(texto)).strip().lower()


def extrair_texto_adf(no) -> str:
    """Extrai texto limpo de estruturas ADF (JSON v3 do Jira Cloud) tratando None com segurança."""
    if no is None:
        return ""
    if isinstance(no, str):
        return no
    if isinstance(no, dict):
        textos = []
        if no.get("type") == "text":
            textos.append(no.get("text", ""))
        content = no.get("content") or []
        for sub in content:
            textos.append(extrair_texto_adf(sub))
        return "\n".join(filter(None, textos))
    if isinstance(no, list):
        return "\n".join(filter(None, [extrair_texto_adf(item) for item in no]))
    return ""


def extrair_ait_e_placa(texto: str) -> tuple[str, str]:
    """
    Extrai o AIT e a Placa de qualquer formato de título.
    Suporta:
    - [URGENTE] Gral Transportes - 1VA4511383 - TJS7G36
    - [IDC] 66.708.042 GABRIEL RIBEIRO DE LIMA - AIT 1DL3595391 - Placa UFM6J63
    """
    if not texto:
        return "", ""

    # Remove tags entre colchetes como [URGENTE] ou [IDC] do início
    texto_limpo = re.sub(r"^\s*\[.*?\]\s*", "", texto).strip()

    # 1. Busca a Placa (7 caracteres alfanuméricos no padrão Mercosul/Antigo)
    placa_match = re.search(r"\b([A-Z]{3}[0-9][A-Z0-9][0-9]{2})\b", texto_limpo, re.IGNORECASE)

    # 2. Busca o AIT (Entre 8 e 15 caracteres alfanuméricos com pelo menos um número)
    ait_match = re.search(r"\b(?=[A-Z0-9]*[0-9])[A-Z0-9]{8,15}\b", texto_limpo, re.IGNORECASE)

    ait = ait_match.group(0).strip().upper() if ait_match else ""
    placa = placa_match.group(0).strip().upper() if placa_match else ""

    return ait, placa   
    

def extrair_dados_condutor(descricao_bruta) -> dict:
    """Extrai CNH, Data de Expiração da CNH e UF varrendo o texto limpo do Jira."""
    if not descricao_bruta:
        return {"cnh": "", "validade_cnh": "", "uf_cnh": "SP", "uf": "SP"}

    text_raw = extrair_texto_adf(descricao_bruta)

    if not text_raw:
        return {"cnh": "", "validade_cnh": "", "uf_cnh": "SP", "uf": "SP"}

    texto_limpo = text_raw.replace("\xa0", " ")

    # 1. Captura CNH
    cnh_match = re.search(r'CNH\D*?(\d{8,11})', texto_limpo, re.IGNORECASE)
    cnh = cnh_match.group(1).strip() if cnh_match else ""

    # 2. Captura Data de Validade da CNH
    validade_raw = ""
    val_match = re.search(
        r'(?:expira[çc][ãa]o|validade|vencimento)\D*?(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})',
        texto_limpo,
        re.IGNORECASE
    )

    if val_match:
        validade_raw = val_match.group(1).strip()

    # 3. Captura UF da CNH com suporte melhorado a 'UF CNH:' e 'UF:'
    uf_match = re.search(r'(?:UF\s*CNH|UF)\D*?([A-Za-z]{2})\b', texto_limpo, re.IGNORECASE)
    uf = uf_match.group(1).strip().upper() if uf_match else "SP"

    # Converte formato ISO (2033-05-29) para formato BR (29/05/2033)
    validade_formatada = validade_raw
    if validade_raw:
        match_iso = re.match(r'(\d{4})[-/](\d{2})[-/](\d{2})', validade_raw)
        if match_iso:
            ano, mes, dia = match_iso.groups()
            validade_formatada = f"{dia}/{mes}/{ano}"

    return {
        "cnh": cnh,
        "validade_cnh": validade_formatada,
        "uf_cnh": uf,
        "uf": uf
    }


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token)
        print("EMAIL USADO NA API:", email)
        print("TOKEN TEM TAMANHO:", len(api_token))
        self.headers = {"Accept": "application/json"}

        teste = requests.get(
            f"{self.base_url}/rest/api/3/myself",
            headers=self.headers,
            auth=self.auth,
        )
        print("USUARIO JIRA API - STATUS:", teste.status_code)

        self._field_map = None
    def anexar_arquivo(self, card_key: str, caminho_arquivo: str):
        """Anexa um arquivo local (ex: print de erro) diretamente ao card do Jira."""
        if not os.path.exists(caminho_arquivo):
            print(f"⚠️ Arquivo {caminho_arquivo} não foi encontrado para anexar.")
            return False

        # Endpoint de anexos do Jira usando self.base_url
        url = f"{self.base_url}/rest/api/2/issue/{card_key}/attachments"
        
        # O Jira EXIGE este cabeçalho e NÃO aceita Accept/Content-Type json no upload
        headers = {
            "X-Atlassian-Token": "no-check"
        }

        try:
            with open(caminho_arquivo, "rb") as f:
                files = {"file": f}
                resposta = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    auth=self.auth,  # Usa o (email, api_token) do seu __init__
                    timeout=25
                )

            if resposta.status_code in [200, 201]:
                print(f"📸 Print anexado com sucesso no Jira ({card_key})!")
                return True
            else:
                print(f"⚠️ Erro ao anexar no Jira (Status {resposta.status_code}): {resposta.text}")
                return False

        except Exception as e:
            print(f"⚠️ Falha de conexão ao anexar arquivo no Jira: {e}")
            return False
    def _carregar_campos(self):
        if self._field_map is not None:
            return self._field_map

        resp = requests.get(
            f"{self.base_url}/rest/api/3/field",
            headers=self.headers,
            auth=self.auth,
        )
        resp.raise_for_status()
        campos = resp.json()

        mapa = {}
        for campo in campos:
            mapa[_norm(campo["name"])] = campo["id"]
        self._field_map = mapa
        return mapa

    def encontrar_campo(self, *pistas):
        mapa = self._carregar_campos()
        for nome_normalizado, campo_id in mapa.items():
            for pista in pistas:
                if _norm(pista) in nome_normalizado:
                    return campo_id
        return None

    def buscar_issues(self, jql: str, campos_extra: list[str] = None):
        """Executa a busca JQL usando o endpoint do Jira Cloud."""
        issues = []
        next_page_token = None

        if campos_extra is None:
            campos_extra = ["summary", "description", "customfield_10618", "customfield_10619"]

        while True:
            body = {
                "jql": jql,
                "maxResults": 50,
                "fields": campos_extra,
            }

            if next_page_token:
                body["nextPageToken"] = next_page_token

            resp = requests.post(
                f"{self.base_url}/rest/api/3/search/jql",
                headers={**self.headers, "Content-Type": "application/json"},
                auth=self.auth,
                json=body,
            )

            resp.raise_for_status()
            data = resp.json()

            issues.extend(data.get("issues", []))
            next_page_token = data.get("nextPageToken")

            if not next_page_token:
                break

        print("TOTAL DE CARDS ENCONTRADOS NO JIRA:", len(issues))
        return issues

    def listar_cards_para_indicacao(self, jql: str):
        """Busca os cards e extrai AIT, Placa e dados do Condutor."""
        issues = self.buscar_issues(jql)
        cards = []

        for issue in issues:
            fields = issue.get("fields", {})
            summary = fields.get("summary", "")
            
            ait = fields.get("customfield_10619")
            placa = fields.get("customfield_10618")

            if not ait or not placa:
                ait_ext, placa_ext = extrair_ait_e_placa(summary)
                ait = ait or ait_ext
                placa = placa or placa_ext

            desc = fields.get("description")
            condutor = extrair_dados_condutor(desc)

            cards.append({
                "chave": issue.get("key"),
                "ait": ait,
                "placa": placa,
                "boba": issue.get("key"),
                "condutor": condutor
            })

        return cards

    def adicionar_comentario(self, issue_key: str, texto_mensagem: str):
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"

        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": str(texto_mensagem)
                            }
                        ]
                    }
                ]
            }
        }

        resp = requests.post(
            url,
            headers={**self.headers, "Content-Type": "application/json"},
            auth=self.auth,
            json=body
        )

        resp.raise_for_status()
        print(f"Comentário adicionado em {issue_key}")
    def atualizar_status_nao_elegivel(self, card_key: str, motivo: str):
            """Atualiza o status do card para 'Não Elegível' (Declined) e adiciona a observação."""
            # 1. Adiciona o comentário/observação com o motivo exato
            self.adicionar_comentario(card_key, f"⚠️ Indicação cancelada: {motivo}")
    
            # 2. Transiciona o status para Não Elegível (Declined)
            # Substitua 'Não Elegível' ou 'Declined' pelo nome exato da transição no seu Jira
            url = f"{self.base_url}/rest/api/2/issue/{card_key}/transitions"
            
            # Primeiro, busca as transições disponíveis para o card
            try:
                res_trans = requests.get(url, headers={"Accept": "application/json"}, auth=self.auth)
                if res_trans.status_code == 200:
                    transitions = res_trans.json().get("transitions", [])
                    transition_id = None
                    
                    for t in transitions:
                        nome_t = t.get("name", "").lower()
                        if "não elegível" in nome_t or "nao elegivel" in nome_t or "declined" in nome_t:
                            transition_id = t.get("id")
                            break
    
                    if transition_id:
                        payload = {"transition": {"id": transition_id}}
                        requests.post(url, json=payload, headers={"Content-Type": "application/json"}, auth=self.auth)
                        print(f"🚫 Card {card_key} alterado para status 'Não Elegível'.")
                    else:
                        print(f"⚠️ Transição 'Não Elegível' não encontrada para o card {card_key}.")
            except Exception as e:
                print(f"⚠️ Erro ao atualizar status para Não Elegível no Jira: {e}")    
    def atualizar_metodo_online(self, chave: str):
        campo_metodo = "customfield_10621"
        url = f"{self.base_url}/rest/api/3/issue/{chave}"

        try:
            payload = {
                "fields": {
                    campo_metodo: {"value": "Online"}
                }
            }

            resposta = requests.put(
                url,
                json=payload,
                headers=self.headers,
                auth=self.auth
            )

            if resposta.status_code not in (200, 204):
                payload_texto = {
                    "fields": {
                        campo_metodo: "Online"
                    }
                }
                resposta = requests.put(
                    url,
                    json=payload_texto,
                    headers=self.headers,
                    auth=self.auth
                )

            resposta.raise_for_status()
            print(f"Método atualizado para Online em {chave}")

        except Exception as e:
            print(f"⚠️ Erro ao atualizar método em {chave}: {e}")

    def atualizar_data_indicacao(self, chave: str):
        campo_data = "customfield_10620"
        url = f"{self.base_url}/rest/api/3/issue/{chave}"
        hoje = datetime.now().strftime("%Y-%m-%d")
        payload = {"fields": {campo_data: hoje}}

        resposta = requests.put(
            url,
            json=payload,
            headers=self.headers,
            auth=self.auth
        )
        resposta.raise_for_status()
        print(f"Data de indicação atualizada em {chave}: {hoje}")

    def atualizar_status_em_andamento(self, chave: str):
        url = f"{self.base_url}/rest/api/3/issue/{chave}/transitions"

        resposta = requests.get(
            url,
            headers=self.headers,
            auth=self.auth
        )
        resposta.raise_for_status()
        transicoes = resposta.json().get("transitions", [])

        transicao_id = None
        for t in transicoes:
            if t["name"].strip().lower() == "enviada para órgão" or str(t["id"]) == "131":
                transicao_id = t["id"]
                break

        if transicao_id is None:
            print(f"ℹ️ Transição 'Enviada para órgão' não encontrada para {chave}.")
            return

        resposta = requests.post(
            url,
            headers={**self.headers, "Content-Type": "application/json"},
            auth=self.auth,
            json={"transition": {"id": transicao_id}}
        )
        resposta.raise_for_status()
        print(f"Status atualizado para Enviada para órgão em {chave}")
   