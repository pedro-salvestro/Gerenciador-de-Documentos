"""Pasta de trabalho escolhida pelo usuário e caminhos que nunca devem ser tocados."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .constantes import RELATORIOS
from .erros import ErroValidacao

_RELATORIOS = frozenset(nome.casefold() for nome in RELATORIOS)


def caminhos_programa() -> frozenset[Path]:
    """Arquivos do próprio programa: o .exe empacotado ou o código-fonte."""
    if getattr(sys, "frozen", False):
        return frozenset({Path(sys.executable).resolve()})
    projeto = Path(__file__).resolve().parents[2]
    return frozenset({(projeto / "main.py").resolve(), (projeto / "gerenciador").resolve()})


@dataclass(frozen=True)
class EspacoTrabalho:
    raiz: Path

    @classmethod
    def abrir(cls, raiz: Path | str) -> EspacoTrabalho:
        if not str(raiz).strip():
            raise ErroValidacao("Escolha a pasta de trabalho.")
        caminho = Path(raiz)
        if not caminho.is_dir():
            raise ErroValidacao(f"Pasta não encontrada: {caminho}")
        return cls(caminho.resolve())

    def caminho_relatorio(self, nome: str) -> Path:
        return self.raiz / nome

    def eh_relatorio(self, caminho: Path) -> bool:
        """Relatórios ficam na raiz; só resolve o caminho se o nome coincidir."""
        if caminho.name.casefold() not in _RELATORIOS:
            return False
        return caminho.parent == self.raiz or caminho.resolve().parent == self.raiz

    @cached_property
    def _programa(self) -> tuple[bool, frozenset[Path]]:
        """(raiz inteira é do programa?, arquivos do programa dentro da raiz)."""
        programa = caminhos_programa()
        tudo = any(p == self.raiz or p in self.raiz.parents for p in programa)
        dentro = frozenset(p for p in programa if self.raiz in p.parents)
        return tudo, dentro

    def eh_programa(self, caminho: Path) -> bool:
        tudo, dentro = self._programa
        if tudo:
            return True
        if not dentro:
            return False
        resolvido = caminho.resolve()
        return resolvido in dentro or any(p in resolvido.parents for p in dentro)

    def relativo(self, caminho: Path) -> str:
        """Caminho relativo à raiz com '/'; caminhos de fora são devolvidos completos."""
        try:
            return caminho.relative_to(self.raiz).as_posix()
        except ValueError:
            return caminho.as_posix()

    def dentro_seguro(self, caminho: Path) -> bool:
        """Verdadeiro se o caminho existe, não é link e fica estritamente dentro da raiz."""
        try:
            if caminho.is_symlink():
                return False
            resolvido = caminho.resolve(strict=True)
        except OSError:
            return False
        return resolvido != self.raiz and self.raiz in resolvido.parents
