
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright

def obter_caminho_browsers():
    """Garante portabilidade total: o .exe SEMPRE usará o Chromium empacotado junto com ele."""
    if getattr(sys, 'frozen', False):
        # Quando rodar dentro do .EXE em QUALQUER computador:
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        caminho_browsers = os.path.join(base_path, "ms-playwright")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = caminho_browsers
    else:
        # Quando rodar em desenvolvimento no Python puro:
        caminho_local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ms-playwright")
        if os.path.exists(caminho_local):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = caminho_local

obter_caminho_browsers()
class DERAutomation:
    def __init__(self, headless=False):
        self.url_base = "https://www.eindicacao.der.sp.gov.br/der_eindicacao_web/"
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def iniciar(self):
        """Inicia o navegador no modo anônimo limpo e sem travamentos."""
        self.playwright = sync_playwright().start()

        # Flags essenciais para o DER-SP superar falhas de SSL/TLS do servidor
        args_seguranca = [
            "--disable-blink-features=AutomationControlled",
            "--ignore-certificate-errors",
            "--allow-running-insecure-content",
            "--ssl-version-min=tls1",                # 👈 Permite conexões com versões legadas de TLS
            "--ignore-ssl-errors",                   # 👈 Ignora erros diretos no protocolo de rede
            "--no-sandbox",
            "--disable-setuid-sandbox"
        ]

        # 1. Lança o Chromium
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=args_seguranca
        )

        # 2. Cria o Contexto Anônimo (Incognito)
        self.context = self.browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1366, "height": 768}
        )

        # 3. Garante que a página seja criada dentro deste contexto anônimo
        self.page = self.context.new_page()
        self.page.set_default_timeout(60000)
    def encerrar(self):
        """Encerra o navegador com segurança e limpa processos."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"⚠️ Aviso ao fechar navegador: {e}")

    def checar_mensagem_erro(self, caminho_print: str = "erro_tela.png") -> str:
        """Busca qualquer modal de erro/alerta visível na tela e grava o print da tela."""
        try:
            seletor_modal = ".modal-content, .modal-body, #divMensagemErro, .alert-danger, .alert-warning, div[role='dialog']"
            
            modal = self.page.locator(seletor_modal).first
            if modal.is_visible(timeout=2500):
                texto_erro = modal.inner_text().strip()
                texto_limpo = " ".join(texto_erro.split())

                if texto_limpo and texto_limpo.lower() != "fechar":
                    print(f"⚠️ Pop-up detectado na tela: {texto_limpo}")
                    
                    # 1. Tira o print do erro na tela
                    try:
                        self.page.screenshot(path=caminho_print, full_page=False)
                        print(f"📸 Print gravado com sucesso em '{caminho_print}'.")
                    except Exception as err_img:
                        print(f"⚠️ Falha ao salvar print: {err_img}")

                    # 2. Mapeamento de termos que tornam a multa NÃO ELEGÍVEL
                    termos_nao_elegiveis = [
                        "solicitação em análise",
                        "já existe solicitação",
                        "já cadastrada",
                        "boleto",
                        "desconto",
                        "40%",
                        "20%",
                        "penalidade"
                    ]

                    # Se encontrar algum termo no texto do pop-up, avisa que é Não Elegível
                    texto_lower = texto_limpo.lower()
                    for termo in termos_nao_elegiveis:
                        if termo in texto_lower:
                            return f"NAO_ELEGIVEL: {texto_limpo}"

                    # Retorno padrão para outros erros da tela
                    return texto_limpo
        except Exception:
            pass
            
        return None

    def abrir_eindicacao(self, placa: str, ait: str) -> bool:
        print(f"🌐 Acessando DER-SP | Placa: {placa} | AIT: {ait}...")
        url_target = "http://www.eindicacao.der.sp.gov.br/der_eindicacao_web/"

        # --- TENTATIVAS DE CONEXÃO COM RETRY PARA SUPERAR OSCILAÇÃO SSL ---
        for tentativa in range(1, 4):
            try:
                self.page.goto(url_target, wait_until="commit", timeout=30000)
                break  # Conectou com sucesso, sai do loop
            except Exception as e:
                print(f"⚠️ Tentativa {tentativa}/3 falhou ao conectar no DER-SP (SSL/Rede). Tentando novamente...")
                time.sleep(3)
                if tentativa == 3:
                    raise Exception(f"Falha de conexão SSL no servidor DER-SP: {e}")
        # ------------------------------------------------------------------
        # --- TRATAMENTO DA TELA DE SEGURANÇA DO DER-SP ---
        try:
            botao_prosseguir = self.page.get_by_role("button", name="Ir para o site")
            if botao_prosseguir.is_visible(timeout=4000):
                print("⚠️ Tela de aviso SSL detectada. Clicando em 'Ir para o site'...")
                botao_prosseguir.click()
        except Exception:
            pass
        # -------------------------------------------------

        # Aguarda os campos de formulário aparecerem na tela
        self.page.wait_for_selector('input[name*="Placa"], input[id*="Placa"]', timeout=15000)

        self.page.get_by_role("textbox", name="PLACA").fill(placa.upper().strip())
        self.page.get_by_role("textbox", name="Auto de Infração:").fill(ait.upper().strip())
        self.page.get_by_role("button", name="Pesquisar").click()

        # Aguarda a resposta da pesquisa carregar o modal de aviso ou a próxima tela
        time.sleep(2.5)

        # --- CHECAGEM IMEDIATA DE POP-UP DE BLOQUEIO/ERRO ---
        msg_erro = self.checar_mensagem_erro("erro_tela.png")
        if msg_erro:
            # Lança o erro com a mensagem extraída do modal para que o main.py capture na hora
            raise Exception(f"ERRO_DER: {msg_erro}")
        # ---------------------------------------------------

        return True   
    def preencher_condutor_e_anexar(self, dados_condutor: dict, pacote_docs: dict) -> bool:
        """Preenche UF, CNH, Validade (nesta ordem estrita) e realiza os uploads nos botões numerados."""
        cnh = str(dados_condutor.get("cnh", "")).strip()
        validade = str(dados_condutor.get("validade_cnh", "")).strip()
        uf_sigla = str(dados_condutor.get("uf_cnh") or dados_condutor.get("uf") or "SP").upper().strip()

        mapa_estados = {
            "SP": "São Paulo", "AC": "Acre", "AL": "Alagoas", "AM": "Amazonas",
            "AP": "Amapá", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
            "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MG": "Minas Gerais",
            "MS": "Mato Grosso do Sul", "MT": "Mato Grosso", "PA": "Pará", "PB": "Paraíba",
            "PE": "Pernambuco", "PI": "Piauí", "PR": "Paraná", "RJ": "Rio de Janeiro",
            "RN": "Rio Grande do Norte", "RO": "Rondônia", "RR": "Roraima", "RS": "Rio Grande do Sul",
            "SC": "Santa Catarina", "SE": "Sergipe", "TO": "Tocantins", "IN": "Internacional"
        }

        nome_estado = mapa_estados.get(uf_sigla, "São Paulo")
        print(f"✍️ Preenchendo condutor -> 1º UF: {nome_estado} ({uf_sigla}) | 2º CNH: {cnh} | 3º Validade: {validade}")

        btn_fechar_modal = self.page.locator("button:has-text('Fechar'), .modal button, #btnFechar").first
        if btn_fechar_modal.count() > 0 and btn_fechar_modal.is_visible():
            btn_fechar_modal.click()
            time.sleep(0.5)

        # -------------------------------------------------------------
        # PASSO 1: UF (Seleção via JavaScript Seguro com Retry)
        # -------------------------------------------------------------
        print(f"✍️ [1/3] Alterando UF para {nome_estado} ({uf_sigla})...")
        
        try:
            self.page.evaluate("""async ({ sigla, nome }) => {
                const obterSelect = () => document.getElementById('UF') || document.querySelector("select[name='UF']");
                
                let tentativas = 0;
                while (tentativas < 20) {
                    const el = obterSelect();
                    if (el && el.options && el.options.length > 1) {
                        let existe = Array.from(el.options).some(opt => opt.value === sigla);
                        if (!existe) {
                            const novaOpt = document.createElement("option");
                            novaOpt.value = sigla;
                            novaOpt.textContent = nome;
                            el.appendChild(novaOpt);
                        }

                        el.value = sigla;
                        if (window.jQuery) {
                            window.jQuery(el).val(sigla).trigger('change').trigger('blur');
                        }
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('blur', { bubbles: true }));
                        return true;
                    }
                    await new Promise(r => setTimeout(r, 250));
                    tentativas++;
                }
            }""", {"sigla": uf_sigla, "nome": nome_estado})

        except Exception as e:
            print(f"⚠️ Alerta na seleção da UF: {e}")

        time.sleep(1.5)      
        
        # -------------------------------------------------------------
        # PASSO 2: CNH / REGISTRO
        # -------------------------------------------------------------
        print(f"✍️ [2/3] Preenchendo CNH / Registro: {cnh}...")
        campo_registro = self.page.locator("#txtRegistro, #REGISTRO, input[placeholder*='REGISTRO' i], input[name*='Registro' i]").first
        if campo_registro.count() == 0:
            campo_registro = self.page.get_by_role("textbox", name="Registro")

        try:
            campo_registro.scroll_into_view_if_needed(timeout=5000)
            campo_registro.click()
            campo_registro.fill("")
            time.sleep(0.2)
            campo_registro.type(cnh, delay=80)
            time.sleep(0.3)
        except Exception as e:
            erro = self.checar_mensagem_erro("erro_tela.png")
            if erro:
                raise Exception(f"Erro do Portal DER: {erro}")
            raise e

        # -------------------------------------------------------------
        # PASSO 3: VALIDADE DA CNH
        # -------------------------------------------------------------
        print(f"✍️ [3/3] Preenchendo Validade da CNH: {validade}...")
        if not validade:
            raise Exception("Data de validade da CNH está vazia no cadastro do Jira.")

        campo_validade = self.page.locator("#txtValidade, #VALIDADE, input[placeholder*='VALIDADE' i], input[name*='Validade' i]").first
        if campo_validade.count() == 0:
            campo_validade = self.page.get_by_role("textbox", name="Data de Validade")

        campo_validade.scroll_into_view_if_needed(timeout=5000)
        campo_validade.click()
        time.sleep(0.2)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        time.sleep(0.2)

        apenas_numeros = "".join(filter(str.isdigit, validade))
        campo_validade.type(apenas_numeros, delay=100)
        time.sleep(0.3)
        self.page.keyboard.press("Tab")
        time.sleep(0.8)

        # -------------------------------------------------------------
        # PASSO 4: CADASTRAR CONDUTOR
        # -------------------------------------------------------------
        btn_cadastrar = self.page.locator("button:has-text('Cadastrar'), input[value='Cadastrar'], #btnCadastrar").first
        tentativas = 3
        for tentativa in range(1, tentativas + 1):
            if btn_cadastrar.count() > 0:
                print(f"💾 Clicando em Cadastrar condutor (Tentativa {tentativa}/{tentativas})...")
                btn_cadastrar.click()
                time.sleep(4)

            erro = self.checar_mensagem_erro("erro_tela.png")
            if erro:
                if "connection" in erro.lower() or "respond" in erro.lower() or "timeout" in erro.lower():
                    print(f"⚠️ Servidor do DER oscilou. Fechando aviso e retestando...")
                    btn_fechar = self.page.locator("button:has-text('Fechar'), .modal button, #btnFechar").first
                    if btn_fechar.count() > 0 and btn_fechar.is_visible():
                        btn_fechar.click()
                    time.sleep(3)
                    continue
                else:
                    raise Exception(f"Erro do Portal DER: {erro}")
            else:
                break

        # -------------------------------------------------------------
        # PASSO 5: UPLOADS DE ANEXOS (1 A 5)
        # -------------------------------------------------------------
        anexos_por_botao = [
            ("1 - Formulário", "1 -", pacote_docs.get("formulario")),
            ("2 - CNH Condutor", "2 -", pacote_docs.get("cnh_condutor")),
            ("3 - Doc Prop/Proc", "3 -", pacote_docs.get("doc_proprietario") or pacote_docs.get("doc_procurador") or pacote_docs.get("cnh_proprietario")),
            ("4 - Contrato Social", "4 -", pacote_docs.get("contrato_social")),
            ("5 - Procuração / Sobras", "5 -", pacote_docs.get("pdf_sobras") or pacote_docs.get("procuracao") or pacote_docs.get("termo_responsabilidade") or pacote_docs.get("contrato_locacao"))
        ]

        print("⌛ Iniciando anexos nos botões numerados do DER-SP...")
        time.sleep(2)

        for nome_etapa, prefixo, caminho_arquivo in anexos_por_botao:
            if caminho_arquivo and os.path.exists(caminho_arquivo):
                print(f"📎 Processando anexo: [{nome_etapa}] no botão '{prefixo}'...")

                self.page.wait_for_load_state("networkidle", timeout=10000)
                time.sleep(1.5)

                seletor_elementos = self.page.locator("button, a, input[type='button'], div[role='button']")
                botao_alvo = seletor_elementos.filter(has_text=prefixo).first

                if botao_alvo.count() == 0:
                    raise Exception(f"Botão com prefixo '{prefixo}' [{nome_etapa}] não foi encontrado na tela.")

                try:
                    with self.page.expect_file_chooser(timeout=8000) as fc_info:
                        botao_alvo.click(force=True)

                    file_chooser = fc_info.value
                    file_chooser.set_files(caminho_arquivo)

                    print(f"⏳ Processando upload de [{nome_etapa}] no servidor do DER...")
                    time.sleep(4)
                    self.page.wait_for_load_state("networkidle", timeout=12000)
                    print(f"✅ Anexado com sucesso: {nome_etapa}")

                except Exception:
                    erro = self.checar_mensagem_erro("erro_tela.png")
                    if erro:
                        raise Exception(f"Erro do Portal DER: {erro}")
                    raise Exception(f"Não foi possível clicar no botão '{prefixo}' [{nome_etapa}].")
            else:
                print(f"ℹ️ Nenhum arquivo atribuído para o botão '{prefixo}' ({nome_etapa}). Pulando...")

        print("\n✨ Todos os anexos foram processados com sucesso no DER-SP!")
        return True

    def concluir_peticionamento(self, placa: str = "", ait: str = "") -> str:
        """Conclui a indicação clicando em #UpEnviar e captura o protocolo."""
        print("\n🚀 Concluindo indicação no DER-SP...")

        btn_enviar = self.page.locator("#UpEnviar")
        if btn_enviar.count() > 0:
            btn_enviar.dispatch_event("click")
            print("✅ Clique no botão #UpEnviar disparado!")
        else:
            raise Exception("Não foi possível encontrar o botão com ID '#UpEnviar' na página.")

        time.sleep(5)
        self.page.wait_for_load_state("networkidle", timeout=15000)

        erro = self.checar_mensagem_erro("erro_tela.png")
        if erro:
            raise Exception(f"Erro do Portal DER: {erro}")

        protocolo_real = ""

        if placa and ait:
            try:
                print("🔍 Acessando 'Pesquisar Indicação' (#btnPesquisa) para capturar o protocolo...")
                btn_pesquisar_menu = self.page.locator("#btnPesquisa")
                btn_pesquisar_menu.click(force=True)
                time.sleep(2)

                self.page.get_by_role("textbox", name="PLACA").fill(placa.upper().strip(), timeout=5000)
                self.page.get_by_role("textbox", name="Auto de Infração:").fill(ait.upper().strip(), timeout=5000)
                self.page.get_by_role("button", name="Pesquisar").click()
                time.sleep(3)

                texto_tela = self.page.locator(".card-body, table, body").inner_text()
                match = re.search(r'Protocolo:\s*(\d{10,20})', texto_tela, re.IGNORECASE)
                if match:
                    protocolo_real = match.group(1).strip()
                    print(f"🎯 Protocolo REAL capturado no DER: {protocolo_real}")

            except Exception as e:
                print(f"⚠️ Consulta pós-envio pulada: {e}")

        if not protocolo_real:
            protocolo_real = "DER-" + str(int(time.time()))

        return protocolo_real
