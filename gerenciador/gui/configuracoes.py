"""Preferências persistentes do usuário (últimas pastas, opções)."""

from __future__ import annotations

from PySide6.QtCore import QSettings

CHAVE_RELATORIOS = "geral/gerar_relatorios"


class Configuracoes:
    def __init__(self, qsettings: QSettings | None = None):
        self._s = qsettings or QSettings("GerenciadorDocumentos", "GerenciadorDocumentos")

    def valor(self, chave: str, padrao=None):
        return self._s.value(chave, padrao)

    def valor_bool(self, chave: str, padrao: bool) -> bool:
        valor = self._s.value(chave, padrao)
        if isinstance(valor, str):
            return valor.strip().lower() in {"true", "1", "sim", "yes"}
        return bool(valor)

    def valor_int(self, chave: str, padrao: int) -> int:
        try:
            return int(self._s.value(chave, padrao))
        except (TypeError, ValueError):
            return padrao

    def definir(self, chave: str, valor) -> None:
        self._s.setValue(chave, valor)
        self._s.sync()

    @property
    def gerar_relatorios(self) -> bool:
        return self.valor_bool(CHAVE_RELATORIOS, True)

    @gerar_relatorios.setter
    def gerar_relatorios(self, ativo: bool) -> None:
        self.definir(CHAVE_RELATORIOS, bool(ativo))
