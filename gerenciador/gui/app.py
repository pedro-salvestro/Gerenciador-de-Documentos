"""Ponto de partida da interface gráfica."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .janela_principal import JanelaPrincipal


def executar() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Gerenciador de Documentos")
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()
