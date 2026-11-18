"""Seleção de arquivos/pastas para limpeza (9 modos) e envio à Lixeira.

Os seletores apenas montam a prévia; nada é apagado até `enviar_lixeira`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .arquivos import (
    listar_arquivos, listar_pastas, listar_pastas_vazias, separar_lista, tipo_documento,
    tipo_limpeza,
)
from .constantes import PDF, RELATORIO_APAGADOS, RELATORIOS
from .erros import ErroValidacao
from .espaco import EspacoTrabalho
from .relatorios import CABECALHO_APAGADOS, Relatorio, agora

try:
    from send2trash import send2trash
except ImportError:  # pragma: no cover - dependência obrigatória no .exe
    send2trash = None

TIPOS_ET_DT_MD = {"documento ET", "documento DT", "documento MD"}
FORA_LISTA_ARQUIVOS = "arquivo fora da lista de manutenção"
FORA_LISTA_PASTAS = "pasta fora da lista de manutenção"
PASTA_VAZIA = "pasta vazia"


@dataclass(frozen=True)
class ItemLimpeza:
    caminho: Path
    tipo: str


@dataclass
class ResultadoLimpeza:
    item: ItemLimpeza
    status: str
    detalhe: str = ""
    data_hora: str = field(default_factory=agora)


def candidatos(espaco: EspacoTrabalho) -> list[ItemLimpeza]:
    """Todos os arquivos não PDF, com sua categoria."""
    itens = []
    for caminho in listar_arquivos(espaco):
        tipo = tipo_limpeza(caminho)
        if tipo:
            itens.append(ItemLimpeza(caminho, tipo))
    return itens


def selecionar_todos_nao_pdf(espaco: EspacoTrabalho) -> list[ItemLimpeza]:
    itens = candidatos(espaco)
    # Os relatórios ficam fora da varredura geral, mas entram nesta limpeza explícita.
    for nome in (RELATORIO_APAGADOS, *[n for n in RELATORIOS if n != RELATORIO_APAGADOS]):
        relatorio = espaco.caminho_relatorio(nome)
        if relatorio.is_file():
            itens.append(ItemLimpeza(relatorio, "relatório CSV"))
    return itens


def selecionar_word_excel(espaco: EspacoTrabalho) -> list[ItemLimpeza]:
    return [i for i in candidatos(espaco) if i.tipo == "documento Word/Excel"]


def _extensao(caminho: Path) -> str:
    return caminho.suffix.casefold() or "(sem extensão)"


def extensoes_disponiveis(espaco: EspacoTrabalho) -> list[str]:
    return sorted({_extensao(i.caminho) for i in candidatos(espaco)})


def selecionar_por_extensoes(espaco: EspacoTrabalho, extensoes: set[str]) -> list[ItemLimpeza]:
    return [i for i in candidatos(espaco) if _extensao(i.caminho) in extensoes]


def selecionar_pastas_vazias(espaco: EspacoTrabalho) -> list[ItemLimpeza]:
    vazias = [p for p in listar_pastas_vazias(espaco.raiz) if not espaco.eh_programa(p)]
    if not vazias:
        raise ErroValidacao("Não há pastas vazias.")
    return [ItemLimpeza(p, PASTA_VAZIA) for p in vazias]


def selecionar_cad(espaco: EspacoTrabalho) -> list[ItemLimpeza]:
    itens = [i for i in candidatos(espaco) if i.tipo == "arquivo STEP/DWG"]
    if not itens:
        raise ErroValidacao("Não foram encontrados arquivos .step, .stp ou .dwg.")
    return itens


def selecionar_manter_arquivos(espaco: EspacoTrabalho, texto: str) -> list[ItemLimpeza]:
    """Todos os arquivos não PDF, exceto os da lista (nome, nome sem extensão ou caminho)."""
    manter = set(separar_lista(texto))
    if not manter:
        raise ErroValidacao("Lista vazia; operação cancelada para evitar apagar todos os arquivos.")
    apagar = []
    correspondencias: set[str] = set()
    for caminho in listar_arquivos(espaco):
        if caminho.suffix.casefold() == PDF:
            continue
        relativo = espaco.relativo(caminho).casefold()
        relativo_sem_ext = espaco.relativo(caminho.with_suffix("")).casefold()
        nomes = {relativo, relativo_sem_ext, caminho.name.casefold(), caminho.stem.casefold()}
        correspondencias.update(manter & nomes)
        if not manter & nomes:
            apagar.append(ItemLimpeza(caminho, FORA_LISTA_ARQUIVOS))
    nao_encontrados = manter - correspondencias
    if nao_encontrados:
        raise ErroValidacao(
            "Não encontrei estes nomes na pasta de trabalho; operação cancelada para evitar "
            "exclusões incorretas.", sorted(nao_encontrados))
    return apagar


def selecionar_manter_pastas(espaco: EspacoTrabalho,
                             texto: str) -> tuple[list[ItemLimpeza], list[Path]]:
    """Pastas fora da lista. Devolve (pastas a apagar, pastas mantidas).

    A pasta indicada, seus descendentes e as pastas-pai do caminho são preservados.
    Só a pasta mais externa de cada ramo é enviada (a Lixeira leva as subpastas)."""
    pastas = listar_pastas(espaco)
    if not pastas:
        raise ErroValidacao("Não há subpastas para processar.")
    manter = set(separar_lista(texto))
    if not manter:
        raise ErroValidacao("Lista vazia; operação cancelada para evitar apagar todas as pastas.")
    mantidas: set[Path] = set()
    correspondencias: set[str] = set()
    for pasta in pastas:
        nomes = {espaco.relativo(pasta).casefold(), pasta.name.casefold()}
        if manter & nomes:
            mantidas.add(pasta.resolve())
            correspondencias.update(manter & nomes)
    nao_encontrados = manter - correspondencias
    if nao_encontrados:
        raise ErroValidacao(
            "Não encontrei estas pastas na pasta de trabalho; operação cancelada para evitar "
            "exclusões incorretas.", sorted(nao_encontrados))

    def protegida(pasta: Path) -> bool:
        resolvida = pasta.resolve()
        return any(m == resolvida or m in resolvida.parents or resolvida in m.parents
                   for m in mantidas)

    raizes: list[Path] = []
    for pasta in pastas:
        if protegida(pasta):
            continue
        if not any(pasta == r or r in pasta.parents for r in raizes):
            raizes.append(pasta)
    ordenadas = sorted(mantidas, key=lambda p: str(p).casefold())
    return [ItemLimpeza(p, FORA_LISTA_PASTAS) for p in raizes], ordenadas


def selecionar_et_dt_md(espaco: EspacoTrabalho) -> list[ItemLimpeza]:
    """Documentos -ET-###, -DT-### e -MD-###, inclusive PDFs."""
    nao_pdf = [i for i in candidatos(espaco) if i.tipo in TIPOS_ET_DT_MD]
    pdfs = []
    for caminho in listar_arquivos(espaco):
        if caminho.suffix.casefold() != PDF:
            continue
        tipo = tipo_documento(caminho)
        if tipo in {"ET", "DT", "MD"}:
            pdfs.append(ItemLimpeza(caminho, f"documento {tipo}"))
    itens = nao_pdf + pdfs
    if not itens:
        raise ErroValidacao(
            "Não encontrei documentos com nome nos padrões *-ET-###, *-DT-### ou *-MD-###.")
    return itens


def enviar_lixeira(
    espaco: EspacoTrabalho,
    itens: list[ItemLimpeza],
    relatorio: Relatorio,
    lixeira: Callable[[str], None] | None = None,
    ao_progresso: Callable[[int, int], None] | None = None,
) -> list[ResultadoLimpeza]:
    """Envia cada item à Lixeira, com checagens de segurança, e grava o relatório."""
    if lixeira is None:
        if send2trash is None:
            raise ErroValidacao(
                "Falta a dependência Send2Trash. Instale com: py -m pip install Send2Trash")
        lixeira = send2trash
    resultados = []
    for numero, item in enumerate(itens, 1):
        try:
            if not espaco.dentro_seguro(item.caminho) or espaco.eh_programa(item.caminho):
                raise RuntimeError("Caminho inseguro; preservado.")
            resolvido = item.caminho.resolve(strict=True)
            if item.tipo == PASTA_VAZIA and (not resolvido.is_dir() or any(resolvido.iterdir())):
                raise RuntimeError("A pasta não está mais vazia; preservada.")
            lixeira(str(resolvido))
            status, detalhe = "enviado à Lixeira", ""
        except Exception as erro:  # noqa: BLE001 - cada item é independente
            status, detalhe = "erro", str(erro)
        resultados.append(ResultadoLimpeza(item, status, detalhe))
        if ao_progresso:
            ao_progresso(numero, len(itens))
    destino = espaco.caminho_relatorio(RELATORIO_APAGADOS)
    # Se o usuário escolheu apagar o próprio relatório, ele não é recriado.
    if not any(i.caminho.resolve() == destino.resolve() for i in itens):
        relatorio.gravar(destino, CABECALHO_APAGADOS,
                         [[r.data_hora, espaco.relativo(r.item.caminho), r.item.tipo,
                           r.status, r.detalhe] for r in resultados])
    return resultados

