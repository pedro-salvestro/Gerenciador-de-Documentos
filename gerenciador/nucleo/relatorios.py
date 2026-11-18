"""Relatórios CSV (separador ';', UTF-8 com BOM para abrir direto no Excel)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CABECALHO_CONVERTIDOS = ["data_hora", "arquivo_origem", "arquivo_pdf", "resultado", "detalhe"]
CABECALHO_APAGADOS = ["data_hora", "arquivo", "tipo", "resultado", "detalhe"]
CABECALHO_IGNORADOS = ["arquivo", "motivo"]


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Relatorio:
    """Grava relatórios CSV; quando inativo, não grava nada.

    Uma falha ao gravar (ex.: CSV aberto no Excel) não desfaz nem interrompe a operação
    que já foi feita: ela fica registrada em `erros` para a interface avisar."""

    ativo: bool = True
    erros: list[str] = field(default_factory=list)

    def gravar(self, caminho: Path, cabecalho: list[str], linhas: list[list[str]]) -> Path | None:
        if not self.ativo:
            return None
        try:
            with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";")
                escritor.writerow(cabecalho)
                escritor.writerows(linhas)
        except OSError as erro:
            self.erros.append(f"Relatório não gravado ({caminho.name}): {erro}")
            return None
        return caminho


def ler_csv(caminho: Path) -> tuple[list[str], list[list[str]]]:
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.reader(arquivo, delimiter=";"))
    if not linhas:
        return [], []
    return linhas[0], linhas[1:]
