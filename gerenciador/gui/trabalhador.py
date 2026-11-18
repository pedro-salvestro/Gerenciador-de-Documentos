"""Execução de tarefas do núcleo em segundo plano, sem travar a janela.

A função recebe um `ContextoTarefa` para informar progresso, registrar mensagens e
consultar se o usuário pediu cancelamento. Os sinais chegam na thread da interface.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from ..nucleo.erros import ErroValidacao

log = logging.getLogger(__name__)
_ativos: set["Trabalhador"] = set()


class ContextoTarefa:
    def __init__(self, trabalhador: "Trabalhador"):
        self._trabalhador = trabalhador

    def progresso(self, etapa: str, atual: int, total: int) -> None:
        self._trabalhador.progresso.emit(etapa, int(atual), int(total))

    def log(self, mensagem: str) -> None:
        self._trabalhador.log.emit(mensagem)

    def cancelado(self) -> bool:
        return self._trabalhador.cancelamento_pedido()


class _Linha(QThread):
    def __init__(self, alvo: Callable[[], None]):
        super().__init__()
        self._alvo = alvo

    def run(self) -> None:
        self._alvo()


class Trabalhador(QObject):
    progresso = Signal(str, int, int)
    log = Signal(str)
    concluido = Signal(object)
    falhou = Signal(str, list)
    terminado = Signal()

    def __init__(self, funcao: Callable[[ContextoTarefa], object], pai: QObject | None = None):
        super().__init__(pai)
        self._funcao = funcao
        self._cancelar = threading.Event()
        self._linha = _Linha(self._executar)
        self._linha.finished.connect(self._ao_terminar)

    def iniciar(self) -> None:
        _ativos.add(self)
        self._linha.start()

    def cancelar(self) -> None:
        self._cancelar.set()

    def cancelamento_pedido(self) -> bool:
        return self._cancelar.is_set()

    def em_execucao(self) -> bool:
        return self._linha.isRunning()

    def aguardar(self, milissegundos: int = -1) -> bool:
        if milissegundos < 0:
            return self._linha.wait()
        return self._linha.wait(milissegundos)

    def _executar(self) -> None:
        try:
            resultado = self._funcao(ContextoTarefa(self))
        except ErroValidacao as erro:
            self.falhou.emit(erro.mensagem, list(erro.itens))
        except Exception as erro:  # noqa: BLE001 - mostrado ao usuário
            log.exception("Falha inesperada em tarefa de segundo plano")
            resumo = traceback.format_exc(limit=3).strip().splitlines()[-3:]
            self.falhou.emit(str(erro) or type(erro).__name__, resumo)
        else:
            self.concluido.emit(resultado)

    def _ao_terminar(self) -> None:
        _ativos.discard(self)
        self.terminado.emit()


def executar_em_segundo_plano(
    pai: QObject | None,
    funcao: Callable[[ContextoTarefa], object],
    ao_concluir: Callable[[object], None] | None = None,
    ao_falhar: Callable[[str, list], None] | None = None,
    ao_progresso: Callable[[str, int, int], None] | None = None,
    ao_log: Callable[[str], None] | None = None,
) -> Trabalhador:
    """Conecta os callbacks e só então inicia a tarefa (nenhum sinal é perdido)."""
    trabalhador = Trabalhador(funcao, pai)
    for sinal, callback in ((trabalhador.concluido, ao_concluir),
                            (trabalhador.falhou, ao_falhar),
                            (trabalhador.progresso, ao_progresso),
                            (trabalhador.log, ao_log)):
        if callback is not None:
            sinal.connect(callback)
    trabalhador.iniciar()
    return trabalhador


def trabalhadores_ativos() -> list[Trabalhador]:
    return [t for t in _ativos if t.em_execucao()]


def aguardar_todos(milissegundos: int = 5000) -> None:
    for trabalhador in list(_ativos):
        trabalhador.cancelar()
        trabalhador.aguardar(milissegundos)
