"""Janela principal: abas, opção de relatórios e situação do Office/LibreOffice."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QMainWindow, QMessageBox, QTabWidget, QWidget

from ..nucleo.conversao import detectar_mecanismos
from ..nucleo.relatorios import Relatorio
from .aba_conversao import AbaConversao
from .aba_copia import AbaCopia
from .aba_fluxo import AbaFluxo
from .aba_limpeza import AbaLimpeza
from .aba_relatorios import AbaRelatorios
from .configuracoes import Configuracoes
from .trabalhador import aguardar_todos, trabalhadores_ativos

TITULOS_ABAS = ("Fluxo de entrega", "Converter", "Limpeza", "Copiar por código", "Relatórios")


def _marca(disponivel: bool) -> str:
    return "✓" if disponivel else "✗"


class JanelaPrincipal(QMainWindow):
    def __init__(self, configuracoes: Configuracoes | None = None):
        super().__init__()
        self.configuracoes = configuracoes or Configuracoes()
        self.setWindowTitle("Gerenciador de Documentos")
        self.resize(1150, 780)

        self.caixa_relatorios = QCheckBox("Gerar relatórios CSV")
        self.caixa_relatorios.setChecked(self.configuracoes.gerar_relatorios)
        self.caixa_relatorios.toggled.connect(self._ao_mudar_relatorios)

        self.abas = QTabWidget()
        for titulo, aba in zip(TITULOS_ABAS, self._criar_abas(), strict=True):
            self.abas.addTab(aba, titulo)
        self.setCentralWidget(self.abas)

        mecanismos = detectar_mecanismos()
        self.rotulo_mecanismos = QLabel(
            f"Word {_marca(mecanismos['word'])}   Excel {_marca(mecanismos['excel'])}   "
            f"LibreOffice {_marca(mecanismos['libreoffice'])}")
        self.rotulo_mecanismos.setToolTip(
            "Excel é obrigatório para converter planilhas. Word usa o Office e, na falta "
            "dele, o LibreOffice.")
        self.statusBar().addWidget(self.caixa_relatorios)
        self.statusBar().addPermanentWidget(self.rotulo_mecanismos)

    def _criar_abas(self) -> list[QWidget]:
        return [
            AbaFluxo(self.configuracoes, self.relatorio),
            AbaConversao(self.configuracoes, self.relatorio),
            AbaLimpeza(self.configuracoes, self.relatorio),
            AbaCopia(self.configuracoes),
            AbaRelatorios(self.configuracoes),
        ]

    def relatorio(self) -> Relatorio:
        return Relatorio(ativo=self.caixa_relatorios.isChecked())

    def _ao_mudar_relatorios(self, ativo: bool) -> None:
        self.configuracoes.gerar_relatorios = ativo

    def closeEvent(self, evento) -> None:  # noqa: N802 - API do Qt
        if trabalhadores_ativos():
            resposta = QMessageBox.question(
                self, "Operação em andamento",
                "Há uma operação em andamento. Interromper e sair?\n"
                "As conversões que já começaram serão concluídas antes de fechar.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if resposta != QMessageBox.StandardButton.Yes:
                evento.ignore()
                return
            aguardar_todos(-1)
        evento.accept()
