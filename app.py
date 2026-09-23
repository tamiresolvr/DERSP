"""
app.py - Interface Gráfica Moderna para Automação DER-SP
-------------------------------------------------------
"""

import sys
import os
import time
import threading
from datetime import datetime
import customtkinter as ctk

# Importa a lógica do ciclo e os alertas do seu projeto existente
from main import processar_ciclo, notificar_erro_slack

# Configuração visual do CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AppAutomacaoDER(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configurações da Janela
        self.title("Robô DER-SP — Peticionamento Automático")
        self.geometry("500x380")
        self.resizable(False, False)

        self.rodando = False

        # --- CABEÇALHO ---
        self.lbl_titulo = ctk.CTkLabel(
            self, 
            text="Automação DER-SP (Projeto BOBA)", 
            font=("Arial", 18, "bold")
        )
        self.lbl_titulo.pack(pady=(20, 5))

        self.lbl_subtitulo = ctk.CTkLabel(
            self, 
            text="Peticionamento e Indicação de Condutor", 
            font=("Arial", 12),
            text_color="#94a3b8"
        )
        self.lbl_subtitulo.pack(pady=(0, 15))

        # --- QUADRO DE STATUS ---
        self.frame_status = ctk.CTkFrame(self, width=440, height=120, corner_radius=10)
        self.frame_status.pack(pady=10, padx=20, fill="x")

        self.lbl_status_titulo = ctk.CTkLabel(
            self.frame_status, 
            text="STATUS DO SISTEMA", 
            font=("Arial", 10, "bold"),
            text_color="#64748b"
        )
        self.lbl_status_titulo.pack(pady=(12, 2))

        self.lbl_status = ctk.CTkLabel(
            self.frame_status, 
            text="⚪ Robô Parado", 
            font=("Arial", 14, "bold"),
            text_color="#94a3b8"
        )
        self.lbl_status.pack(pady=5)

        self.lbl_ultima_exec = ctk.CTkLabel(
            self.frame_status, 
            text="Última execução: Nenhum ciclo realizado", 
            font=("Arial", 11),
            text_color="#64748b"
        )
        self.lbl_ultima_exec.pack(pady=(0, 10))

        # --- BOTÕES DE AÇÃO ---
        self.btn_iniciar = ctk.CTkButton(
            self, 
            text="🚀 Iniciar Automação", 
            font=("Arial", 14, "bold"),
            height=40,
            command=self.alternar_execucao
        )
        self.btn_iniciar.pack(pady=15, padx=30, fill="x")

        self.lbl_info = ctk.CTkLabel(
            self, 
            text="O robô executa a cada 30 minutos quando ativo.", 
            font=("Arial", 10),
            text_color="#64748b"
        )
        self.lbl_info.pack(side="bottom", pady=10)

    def alternar_execucao(self):
        """Liga ou desliga o robô sem travar a interface."""
        if not self.rodando:
            self.rodando = True
            self.btn_iniciar.configure(
                text="🛑 Parar Automação", 
                fg_color="#dc2626", 
                hover_color="#991b1b"
            )
            self.atualizar_status("🟢 Robô Ativo — Aguardando inicio de ciclo...", "#10b981")
            
            # Dispara o loop em uma Thread separada
            threading.Thread(target=self.loop_automacao, daemon=True).start()
        else:
            self.rodando = False
            self.btn_iniciar.configure(
                text="🚀 Iniciar Automação", 
                fg_color=["#3B82F6", "#1D4ED8"], 
                hover_color=["#1D4ED8", "#1E40AF"]
            )
            self.atualizar_status("⚪ Robô Parado", "#94a3b8")

    def atualizar_status(self, texto: str, cor: str):
        """Atualiza os textos de status na tela."""
        self.lbl_status.configure(text=texto, text_color=cor)

    def loop_automacao(self):
        """Loop principal rodando em background."""
        while self.rodando:
            agora = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
            self.lbl_ultima_exec.configure(text=f"Última execução iniciada: {agora}")
            self.atualizar_status("🔄 Processando Cards no DER-SP...", "#f59e0b")

            try:
                # Executa o seu ciclo original
                processar_ciclo()
            except Exception as e:
                print(f"❌ Erro no ciclo visual: {e}")
                notificar_erro_slack(card_key="Geral / Sistema", ait="N/A", erro=e)

            if not self.rodando:
                break

            # Contagem regressiva para os 30 minutos (1800s)
            self.atualizar_status("⏳ Aguardando próximo ciclo (30 min)...", "#3b82f6")
            for _ in range(1800):
                if not self.rodando:
                    break
                time.sleep(1)


if __name__ == "__main__":
    app = AppAutomacaoDER()
    app.mainloop()