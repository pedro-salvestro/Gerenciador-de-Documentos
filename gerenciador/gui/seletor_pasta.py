"""Campo de pasta com botão "Escolher…" que lembra a última pasta usada."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from .configuracoes import Configuracoes


class SeletorPasta(QWidget):
    pasta_alterada = Signal(object)  # Path | None

    def __init__(self, rotulo: str, chave_config: str, configuracoes: Configuracoes,
                 pai: QWidget | None = None):
        super().__init__(pai)
        self._chave = chave_config
        self._config = configuracoes
        self.campo = QLineEdit(str(configuracoes.valor(chave_config, "") or ""))
        self.campo.setPlaceholderText("Escolha uma pasta…")
        self.botao = QPushButton("Escolher…")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if rotulo:
            layout.addWidget(QLabel(rotulo))
        layout.addWidget(self.campo, 1)
        layout.addWidget(self.botao)
        self.botao.clicked.connect(self._escolher)
        self.campo.editingFinished.connect(self._ao_editar)

    @property
    def pasta(self) -> Path | None:
        texto = self.campo.text().strip()
        if not texto:
            return None
        caminho = Path(texto)
        return caminho if caminho.is_dir() else None

    def definir_pasta(self, caminho: Path | str) -> None:
        self.campo.setText(str(caminho))
        self._ao_editar()

    def _escolher(self) -> None:
        inicial = self.campo.text().strip() or str(Path.home())
        escolhida = QFileDialog.getExistingDirectory(self, "Escolher pasta", inicial)
        if escolhida:
            self.definir_pasta(str(Path(escolhida)))

    def _ao_editar(self) -> None:
        self._config.definir(self._chave, self.campo.text().strip())
        self.pasta_alterada.emit(self.pasta)
