"""Aba de relatórios: mostra os CSV gerados numa pasta."""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..nucleo.constantes import RELATORIO_APAGADOS, RELATORIO_CONVERTIDOS, RELATORIO_IGNORADOS
from ..nucleo.relatorios import ler_csv
from .configuracoes import Configuracoes
from .seletor_pasta import SeletorPasta

CHAVE_PASTA = "avulso/pasta"
TIPOS = (("Convertidos", RELATORIO_CONVERTIDOS),
         ("Apagados", RELATORIO_APAGADOS),
         ("Ignorados (fluxo de entrega)", RELATORIO_IGNORADOS))


class AbaRelatorios(QWidget):
    def __init__(self, configuracoes: Configuracoes, pai: QWidget | None = None):
        super().__init__(pai)
        self.seletor = SeletorPasta("Pasta:", CHAVE_PASTA, configuracoes)
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems([t for t, _ in TIPOS])
        self.botao_atualizar = QPushButton("Atualizar")
        self.botao_abrir = QPushButton("Abrir no Excel")
        self.rotulo_situacao = QLabel()
        self.tabela = QTableWidget()
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setSortingEnabled(True)
        self.tabela.horizontalHeader().setStretchLastSection(True)

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Relatório:"))
        linha.addWidget(self.combo_tipo)
        linha.addWidget(self.rotulo_situacao, 1)
        linha.addWidget(self.botao_atualizar)
        linha.addWidget(self.botao_abrir)
        layout = QVBoxLayout(self)
        layout.addWidget(self.seletor)
        layout.addLayout(linha)
        layout.addWidget(self.tabela, 1)

        self.seletor.pasta_alterada.connect(lambda _: self.atualizar())
        self.combo_tipo.currentIndexChanged.connect(lambda _: self.atualizar())
        self.botao_atualizar.clicked.connect(self.atualizar)
        self.botao_abrir.clicked.connect(self._abrir)

    def _caminho(self):
        pasta = self.seletor.pasta
        return pasta / TIPOS[self.combo_tipo.currentIndex()][1] if pasta else None

    def atualizar(self) -> None:
        self.tabela.setSortingEnabled(False)
        self.tabela.clear()
        self.tabela.setRowCount(0)
        self.tabela.setColumnCount(0)
        caminho = self._caminho()
        self.botao_abrir.setEnabled(bool(caminho and caminho.is_file()))
        if caminho is None:
            self.rotulo_situacao.setText("Escolha a pasta.")
            return
        try:
            cabecalho, linhas = ler_csv(caminho)
        except FileNotFoundError:
            self.rotulo_situacao.setText("O relatório ainda não foi gerado.")
            return
        except (OSError, UnicodeError) as erro:
            self.rotulo_situacao.setText(f"Não foi possível ler o relatório: {erro}")
            return
        self.tabela.setColumnCount(len(cabecalho))
        self.tabela.setHorizontalHeaderLabels(cabecalho)
        self.tabela.setRowCount(len(linhas))
        for i, valores in enumerate(linhas):
            for j, valor in enumerate(valores[:len(cabecalho)]):
                self.tabela.setItem(i, j, QTableWidgetItem(valor))
        self.tabela.resizeColumnsToContents()
        self.tabela.setSortingEnabled(True)
        self.rotulo_situacao.setText(f"{len(linhas)} linha(s) · {caminho}")

    def _abrir(self) -> None:
        caminho = self._caminho()
        if caminho and caminho.is_file():
            os.startfile(caminho)  # noqa: S606 - abre no programa padrão (Excel)
