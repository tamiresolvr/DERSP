"""
drive_helper.py
Localiza as pastas no Google Drive e classifica/organiza os PDFs encontrados.
Garante a unificação automática de todas as sobras no Botão 5 do DER-SP.
"""

import os
import re
from unidecode import unidecode
from pypdf import PdfWriter


PADROES_DOCUMENTOS = {
    "formulario": [r"^form\b", r"formulario", r"^fii\b"],
    "cnh_condutor": [r"cnh.*cond", r"cnh_cond", r"cnh.*infrator"],
    
    # Agrupa todas as variações de Documento do Proprietário / Procurador (Mapeia para o Botão 3)
    "doc_proprietario": [
        r"doc.*prop", r"doc_prop", 
        r"cnh.*prop", r"cnh_prop", 
        r"doc.*proc", r"doc_proc", 
        r"cnh.*proc", r"cnh_proc", 
        r"proprietario", r"procurador"
    ],
    
    "contrato_social": [r"^cs\b", r"contrato.*social", r"estatuto"],
    "termo_responsabilidade": [r"^tr\b", r"termo.*responsab"],
    "procuracao": [r"^proc\b", r"procuracao"],
    "contrato_locacao": [r"^cl\b", r"contrato.*loc"],
}


class DriveHelper:
    def __init__(self):
        self.raiz = self.encontrar_raiz_drive()

    def encontrar_raiz_drive(self) -> str | None:
        """
        Procura automaticamente a pasta INDICAÇÕES testando:
        1. As unidades mapeadas pelo Google Drive (A:\ até Z:\)
        2. A pasta do perfil do usuário do Windows (%USERPROFILE%)
        3. O atributo self.raiz já configurado
        """
        caminho_relativo = os.path.join("Drives compartilhados", "INDICAÇÕES")
        user_profile = os.environ.get("USERPROFILE", "")

        # Lista de possíveis locais onde 'Drives compartilhados/INDICAÇÕES' pode estar
        locais_para_testar = []

        # 1. Testa todas as letras de unidade (G:\, H:\, etc.)
        for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            locais_para_testar.append(os.path.join(f"{letra}:\\", caminho_relativo))

        # 2. Testa dentro da pasta do usuário do Windows (C:\Users\NOME_USUARIO\...)
        if user_profile:
            locais_para_testar.extend([
                os.path.join(user_profile, "Google Drive", caminho_relativo),
                os.path.join(user_profile, "Meu Drive", caminho_relativo),
                os.path.join(user_profile, "Drive", caminho_relativo),
                os.path.join(user_profile, "GoogleDrive", caminho_relativo),
            ])

        # 3. Testa o caminho vindo da variável 'raiz', se existir
        if hasattr(self, "raiz") and self.raiz:
            locais_para_testar.insert(0, self.raiz)

        # Percorre as possibilidades e retorna a primeira que existir na máquina
        for caminho in locais_para_testar:
            if caminho and os.path.isdir(caminho):
                print(f"📍 Pasta 'INDICAÇÕES' localizada em: {caminho}")
                return caminho

        return None

    def encontrar_pasta_boba(self, numero_boba: str) -> str | None:
        """Procura a pasta correspondente ao card BOBA no diretório raiz do Drive."""
        raiz_dinamica = self.encontrar_raiz_drive()

        if not raiz_dinamica or not os.path.isdir(raiz_dinamica):
            print(f"⚠️ Diretório 'INDICAÇÕES' do Drive não foi encontrado nesta máquina.")
            return None

        # Atualiza o atributo self.raiz para chamadas subsequentes
        self.raiz = raiz_dinamica

        # Extrai apenas os números do card (ex: "BOBA-15536" -> "15536")
        num_limpo = re.sub(r"\D", "", str(numero_boba))
        if not num_limpo:
            return None

        print(f"📁 Procurando pasta para BOBA-{num_limpo} em: {self.raiz}")

        # Regex flexível para encontrar variações ("BOBA 15536", "BOBA-15536", "BOBA15536", etc.)
        padrao = re.compile(
            rf"BOBA[\s\-:]*{re.escape(num_limpo)}",
            re.IGNORECASE
        )

        try:
            for nome in os.listdir(self.raiz):
                caminho = os.path.join(self.raiz, nome)
                if os.path.isdir(caminho) and padrao.search(nome):
                    print(f"✅ Pasta encontrada: {caminho}")
                    return caminho
        except Exception as e:
            print(f"⚠️ Erro ao listar diretório {self.raiz}: {e}")

        print(f"❌ Pasta do card BOBA-{num_limpo} não foi encontrada no caminho do Drive.")
        return None
    def classificar_documentos(self, pasta: str) -> dict:
        """Varre a pasta e subpastas classificando os arquivos PDF."""
        encontrados = {}
        ignorados = []

        if not os.path.isdir(pasta):
            return {"_ignorados": []}

        for root, dirs, files in os.walk(pasta):
            for arquivo in sorted(files):
                if arquivo.startswith("~$") or arquivo.startswith(".") or not arquivo.lower().endswith(".pdf"):
                    continue

                nome_norm = unidecode(arquivo).lower()
                casou = False

                for tipo, padroes in PADROES_DOCUMENTOS.items():
                    for padrao in padroes:
                        if re.search(padrao, nome_norm):
                            caminho_completo = os.path.join(root, arquivo)
                            if tipo not in encontrados:
                                encontrados[tipo] = caminho_completo
                            else:
                                ignorados.append(arquivo)
                            casou = True
                            break
                    if casou:
                        break

        encontrados["_ignorados"] = ignorados
        return encontrados

    def fundir_pdfs(self, lista_caminhos: list, caminho_saida: str) -> str | None:
        """Junta múltiplos arquivos PDF em um único arquivo."""
        merger = PdfWriter()
        arquivos_validos = [f for f in lista_caminhos if f and os.path.exists(f)]

        if not arquivos_validos:
            return None

        if len(arquivos_validos) == 1:
            return arquivos_validos[0]

        for pdf in arquivos_validos:
            merger.append(pdf)

        merger.write(caminho_saida)
        merger.close()
        return caminho_saida

    def organizar_pacote_der(self, documentos_encontrados: dict, pasta_destino: str) -> dict:
        """
        Organiza os documentos dos botões 1 a 4 e JUNTA OBRIGATORIAMENTE
        todas as sobras (Procuração, CL, TR) em um único PDF para o Botão 5.
        """
        pacote_final = {}

        # 1. Atribuição direta dos botões 1, 2, 3 e 4
        pacote_final["formulario"] = documentos_encontrados.get("formulario")
        pacote_final["cnh_condutor"] = documentos_encontrados.get("cnh_condutor")
        pacote_final["doc_proprietario"] = documentos_encontrados.get("doc_proprietario")
        pacote_final["contrato_social"] = documentos_encontrados.get("contrato_social")

        # 2. Coleta de todas as sobras possíveis para o Botão 5
        sobras_lista = []
        for chave in ["procuracao", "contrato_locacao", "termo_responsabilidade"]:
            caminho_arq = documentos_encontrados.get(chave)
            if caminho_arq and os.path.exists(caminho_arq):
                sobras_lista.append(caminho_arq)

        # 3. Tratamento para o Botão 5 (pdf_sobras)
        if len(sobras_lista) > 1:
            print(f"📄 Unificando {len(sobras_lista)} documentos excedentes (Procuração / CL / TR) em um único PDF para o Botão 5...")
            pdf_sobras_unificado = os.path.join(pasta_destino, "sobras_juntadas.pdf")
            pacote_final["pdf_sobras"] = self.fundir_pdfs(sobras_lista, pdf_sobras_unificado)
        elif len(sobras_lista) == 1:
            pacote_final["pdf_sobras"] = sobras_lista[0]
        else:
            pacote_final["pdf_sobras"] = None

        return pacote_final

    def obter_pacote_documentos(self, chave_card: str, ait: str) -> dict:
        """
        Método chamado pelo main.py para buscar, fundir e validar os arquivos necessários.
        """
        print(f"📁 Buscando pasta para {chave_card} (AIT: {ait})...")
        pasta = self.encontrar_pasta_boba(chave_card)

        if not pasta:
            print(f"⚠️ Pasta não encontrada no Drive para {chave_card}")
            return {"_faltando": ["Pasta do Card não encontrada no Drive"]}

        docs_brutos = self.classificar_documentos(pasta)
        docs_brutos["_pasta"] = pasta

        # Organiza o pacote e garante a fusão das sobras na chave 'pdf_sobras'
        pacote = self.organizar_pacote_der(docs_brutos, pasta)
        pacote["_pasta"] = pasta

        # Requisitos mínimos de documentos para indicação
        faltando = []
        if "formulario" not in pacote or not pacote["formulario"]:
            faltando.append("Formulário de Indicação")
        if "cnh_condutor" not in pacote or not pacote["cnh_condutor"]:
            faltando.append("CNH do Condutor")

        if faltando:
            pacote["_faltando"] = faltando

        return pacote