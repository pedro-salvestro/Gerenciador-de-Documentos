"""Varredura de arquivos e pastas e classificação por nome."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .constantes import CAD, EXCEL, IGNORAR_DIRS, PDF, PREFIXO_TEMPORARIO, WORD
from .espaco import EspacoTrabalho

_TIPO = re.compile(r"-([A-Za-z]{2})-\d+$")
_CODIGO_LIMPEZA = re.compile(r"-(ET|DT|MD)-\d+$", re.IGNORECASE)


def _pasta_ignorada(nome: str) -> bool:
    return nome.casefold() in IGNORAR_DIRS or nome.startswith(PREFIXO_TEMPORARIO)


def listar_arquivos(espaco: EspacoTrabalho) -> list[Path]:
    """Arquivos comuns da pasta (recursivo), sem relatórios, temporários e o programa."""
    arquivos = []
    for pasta, diretorios, nomes in os.walk(espaco.raiz, followlinks=False):
        diretorios[:] = sorted(d for d in diretorios if not _pasta_ignorada(d))
        for nome in sorted(nomes, key=str.casefold):
            caminho = Path(pasta) / nome
            if caminho.is_symlink() or nome.startswith("~$"):
                continue
            if espaco.eh_relatorio(caminho) or espaco.eh_programa(caminho):
                continue
            arquivos.append(caminho)
    return arquivos


def listar_pastas(espaco: EspacoTrabalho) -> list[Path]:
    """Subpastas (recursivo), da mais rasa para a mais funda."""
    pastas = []
    for atual, diretorios, _ in os.walk(espaco.raiz, topdown=True, followlinks=False):
        diretorios[:] = [d for d in diretorios if not _pasta_ignorada(d)]
        pastas.extend(Path(atual) / nome for nome in diretorios)
    return sorted((p for p in pastas if not p.is_symlink() and not espaco.eh_programa(p)),
                  key=lambda p: (len(p.parts), str(p).casefold()))


def listar_pastas_vazias(raiz: Path) -> list[Path]:
    vazias = []
    for pasta, _, _ in os.walk(raiz, topdown=False, followlinks=False):
        atual = Path(pasta)
        if atual == raiz or atual.is_symlink():
            continue
        try:
            if not any(atual.iterdir()):
                vazias.append(atual)
        except OSError:
            continue
    return sorted(vazias, key=lambda p: str(p).casefold())


def remover_pastas_vazias(raiz: Path) -> int:
    """Remove, de baixo para cima, as pastas que estiverem vazias. Devolve a quantidade."""
    removidas = 0
    for pasta, _, _ in os.walk(raiz, topdown=False, followlinks=False):
        atual = Path(pasta)
        if atual == raiz or atual.is_symlink():
            continue
        try:
            if not any(atual.iterdir()):
                atual.rmdir()
                removidas += 1
        except OSError:
            continue
    return removidas


def separar_lista(texto: str) -> list[str]:
    """Aceita itens separados por vírgula, ponto e vírgula ou quebra de linha."""
    return [item.strip().strip('"').strip("'").replace("\\", "/").strip("/").casefold()
            for item in re.split(r"[;,\r\n]+", texto) if item.strip()]


def tipo_documento(caminho: Path) -> str | None:
    """Código de tipo do nome (ex.: NVC00410A-DE-001 -> 'DE'), em maiúsculas."""
    encontrado = _TIPO.search(caminho.stem)
    return encontrado.group(1).upper() if encontrado else None


def tipo_limpeza(caminho: Path) -> str | None:
    """Categoria usada pelos modos de limpeza; None para PDFs."""
    sufixo = caminho.suffix.casefold()
    if sufixo == PDF:
        return None
    codigo = _CODIGO_LIMPEZA.search(caminho.stem)
    if codigo:
        return f"documento {codigo.group(1).upper()}"
    if sufixo in CAD:
        return "arquivo STEP/DWG"
    if sufixo in WORD | EXCEL:
        return "documento Word/Excel"
    return "outro arquivo"
