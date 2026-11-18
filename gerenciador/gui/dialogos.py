"""Diálogos e formatação de mensagens comuns às abas."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

LIMITE_ITENS = 30


def listar_itens(itens: list[str]) -> str:
    texto = "\n".join(f" • {i}" for i in itens[:LIMITE_ITENS])
    if len(itens) > LIMITE_ITENS:
        texto += f"\n … e mais {len(itens) - LIMITE_ITENS}"
    return texto


def mostrar_erro(pai: QWidget, titulo: str, mensagem: str, itens: list[str]) -> None:
    QMessageBox.warning(pai, titulo, f"{mensagem}\n\n{listar_itens(itens)}".strip())


def confirmar(pai: QWidget, titulo: str, texto: str) -> bool:
    """Pergunta Sim/Não com 'Não' como padrão."""
    resposta = QMessageBox.question(
        pai, titulo, texto,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No)
    return resposta == QMessageBox.StandardButton.Yes
