"""Exceções do núcleo."""

from collections.abc import Sequence


class ErroValidacao(Exception):
    """Operação inviável: nada foi alterado. Traz a mensagem e os itens problemáticos."""

    def __init__(self, mensagem: str, itens: Sequence[str] = ()):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.itens = list(itens)
