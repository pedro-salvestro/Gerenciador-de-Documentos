"""Cópia de arquivos por código NVC para pastas NVCxxx/variante/<nome>."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .arquivos import listar_arquivos, separar_lista
from .erros import ErroValidacao
from .espaco import EspacoTrabalho

_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
               *(f"LPT{i}" for i in range(1, 10))}
MENSAGEM_NOME_INVALIDO = "Nome de pasta inválido; use apenas o nome, sem caminho."


def validar_nome_pasta(nome: str) -> str:
    """Valida um nome de pasta do Windows (sem caminho) e devolve-o sem espaços nas pontas."""
    nome = nome.strip()
    if (not nome or nome in {".", ".."} or Path(nome).name != nome
            or re.search(r'[<>:"/\|?*\x00-\x1f]', nome)
            or nome.endswith((".", " "))
            or nome.split(".")[0].strip().upper() in _RESERVADOS):
        raise ErroValidacao(MENSAGEM_NOME_INVALIDO, [nome])
    return nome


@dataclass
class PlanoCopia:
    nome_destino: str
    itens: list[tuple[Path, Path]]


def planejar_copia(espaco: EspacoTrabalho, texto_codigos: str, nome_destino: str) -> PlanoCopia:
    solicitados = set(separar_lista(texto_codigos))
    if not solicitados:
        raise ErroValidacao("Lista vazia; nenhuma cópia foi feita.")
    nome_destino = validar_nome_pasta(nome_destino)

    destinos: dict[str, Path] = {}
    invalidos = []
    for codigo in solicitados:
        partes = re.fullmatch(r"(NVC\d+)([A-Z])", codigo, re.IGNORECASE)
        if not partes:
            invalidos.append(codigo)
            continue
        equipamento, variante = partes.groups()
        destinos[codigo] = espaco.raiz / equipamento.upper() / variante.upper() / nome_destino
    if invalidos:
        raise ErroValidacao("Estes códigos não seguem o formato NVC + número + variante "
                            "(ex.: NVC00410A); cópia cancelada.", sorted(invalidos))
    existentes = [espaco.relativo(p) for p in destinos.values() if p.exists()]
    if existentes:
        raise ErroValidacao("Já existe pasta de destino; cópia cancelada para não "
                            "sobrescrever conteúdo.", sorted(existentes))

    achados: dict[str, list[Path]] = {codigo: [] for codigo in solicitados}
    for caminho in listar_arquivos(espaco):
        stem = caminho.stem.casefold()
        for codigo in solicitados:
            if stem == codigo or stem.startswith(codigo + "-"):
                achados[codigo].append(caminho)
    nao_encontrados = sorted(c for c, lista in achados.items() if not lista)
    if nao_encontrados:
        raise ErroValidacao("Não encontrei estes itens; cópia cancelada.", nao_encontrados)

    itens = []
    nomes: set[tuple[str, str]] = set()
    for codigo in sorted(achados):
        destino = destinos[codigo]
        for origem in achados[codigo]:
            chave = (str(destino).casefold(), origem.name.casefold())
            if chave in nomes:
                raise ErroValidacao(f"Há arquivos com o mesmo nome para {codigo}; cópia "
                                    "cancelada para evitar sobrescrita.", [origem.name])
            nomes.add(chave)
            itens.append((origem, destino / origem.name))
    return PlanoCopia(nome_destino, itens)


def executar_copia(plano: PlanoCopia, ao_progresso: Callable[[int, int], None] | None = None,
                   ) -> list[tuple[Path, Path, str, str]]:
    """Copia os itens; para no primeiro erro (os já copiados permanecem)."""
    resultados = []
    for numero, (origem, destino) in enumerate(plano.itens, 1):
        if origem.is_symlink() or not origem.is_file():
            resultados.append((origem, destino, "ignorado", "não é arquivo regular"))
        else:
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origem, destino)
                resultados.append((origem, destino, "copiado", ""))
            except OSError as erro:
                resultados.append((origem, destino, "erro", str(erro)))
                break
        if ao_progresso:
            ao_progresso(numero, len(plano.itens))
    return resultados
