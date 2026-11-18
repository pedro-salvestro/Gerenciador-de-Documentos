"""Fluxo de entrega: monta, ao lado da pasta base (ou na pasta escolhida), uma pasta nova
só com os PDFs dos tipos permitidos (PDFs existentes copiados; Word/Excel copiados e
convertidos), opcionalmente restrita a uma lista de NVCs ou arquivos.

A pasta base é somente leitura: nada nela é criado, alterado ou apagado.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from collections.abc import Callable
from concurrent.futures import Executor
from dataclasses import dataclass, field
from pathlib import Path

from .arquivos import listar_arquivos, remover_pastas_vazias, tipo_documento
from .constantes import EXCEL, PDF, RELATORIO_CONVERTIDOS, RELATORIO_IGNORADOS, WORD
from .conversao import (
    ResultadoConversao, TrabalhoConversao, converter_arquivo, executar_conversao,
    gravar_relatorio_conversao, planejar_conversao,
)
from .copia import validar_nome_pasta
from .erros import ErroValidacao
from .espaco import EspacoTrabalho
from .relatorios import CABECALHO_IGNORADOS, Relatorio

COPIAR, CONVERTER, IGNORAR = "copiar", "converter", "ignorar"
FORA_DA_LISTA = "fora da lista"

# NVC no começo do nome do arquivo: NVC00410A-DE-001 -> ("00410", "A").
_NVC_ARQUIVO = re.compile(r"NVC(\d+)([A-Z]?)(?![A-Z0-9])", re.IGNORECASE)
_NVC_SELECAO = re.compile(r"NVC(\d+)([A-Z]?)", re.IGNORECASE)

ChaveSelecao = tuple[str, str, str]  # ("nvc", dígitos, variante) | ("arquivo", nome, "")


def separar_tipos(texto: str) -> frozenset[str]:
    """'de; li ,pr' -> {'DE', 'LI', 'PR'}. Cada tipo tem exatamente duas letras."""
    partes = [p.strip().upper() for p in re.split(r"[;,\s]+", texto) if p.strip()]
    if not partes:
        raise ErroValidacao("Informe ao menos um tipo de documento.")
    invalidos = [p for p in partes if not re.fullmatch(r"[A-Z]{2}", p)]
    if invalidos:
        raise ErroValidacao("Tipos inválidos: use códigos de duas letras (ex.: DE, LI).",
                            invalidos)
    return frozenset(partes)


def separar_selecao(texto: str) -> tuple[str, ...]:
    """Lista de NVCs/arquivos separados por vírgula, ponto e vírgula ou quebra de linha,
    sem repetidos (maiúsculas/minúsculas tanto faz; fica a primeira grafia)."""
    itens: list[str] = []
    vistos: set[str] = set()
    for parte in re.split(r"[;,\r\n]+", texto):
        item = parte.strip().strip('"').strip("'").strip()
        if item and item.casefold() not in vistos:
            vistos.add(item.casefold())
            itens.append(item)
    return tuple(itens)


def _chave_selecao(item: str) -> ChaveSelecao | None:
    """NVC00410 (todas as variantes), NVC00410A (uma variante) ou nome de arquivo
    começando por NVC + dígitos. None = formato inválido."""
    nvc = _NVC_SELECAO.fullmatch(item)
    if nvc:
        return "nvc", nvc.group(1), nvc.group(2).upper()
    if _NVC_SELECAO.match(item):
        return "arquivo", item.casefold(), ""
    return None


def _casa(chave: ChaveSelecao, caminho: Path) -> bool:
    tipo, valor, variante = chave
    if tipo == "arquivo":
        return valor in (caminho.name.casefold(), caminho.stem.casefold())
    achado = _NVC_ARQUIVO.match(caminho.stem)
    return (achado is not None and achado.group(1) == valor
            and (not variante or achado.group(2).upper() == variante))


@dataclass
class ParametrosFluxo:
    base: Path
    nome_destino: str
    tipos: frozenset[str]
    converter: bool = True
    processos: int = 2
    pasta_destino: Path | None = None  # None = ao lado da pasta base
    selecao: tuple[str, ...] = ()  # NVCs/arquivos; vazio = todos


@dataclass
class ItemFluxo:
    origem: Path
    acao: str  # "copiar" | "converter" | "ignorar"
    motivo: str = ""
    destino: Path | None = None


@dataclass
class PlanoFluxo:
    parametros: ParametrosFluxo
    base: Path
    destino_raiz: Path
    itens: list[ItemFluxo]
    trabalhos: list[TrabalhoConversao]
    conflitos: list[Path]
    problemas: list[tuple[str, str]] = field(default_factory=list)  # (item da lista, motivo)

    def _com_acao(self, acao: str) -> list[ItemFluxo]:
        return [i for i in self.itens if i.acao == acao]

    @property
    def a_copiar(self) -> list[ItemFluxo]:
        return self._com_acao(COPIAR)

    @property
    def a_converter(self) -> list[ItemFluxo]:
        return self._com_acao(CONVERTER)

    @property
    def ignorados(self) -> list[ItemFluxo]:
        return self._com_acao(IGNORAR)


@dataclass
class ResumoFluxo:
    destino_raiz: Path
    copiados: int = 0
    convertidos: int = 0
    ignorados: int = 0
    erros: list[tuple[str, str]] = field(default_factory=list)
    cancelado: bool = False


def _classificar(caminho: Path, tipos: frozenset[str], converter: bool) -> tuple[str, str]:
    tipo = tipo_documento(caminho)
    if tipo is None:
        return IGNORAR, "sem código de tipo"
    if tipo not in tipos:
        return IGNORAR, f"tipo {tipo} não permitido"
    sufixo = caminho.suffix.casefold()
    if sufixo == PDF:
        return COPIAR, ""
    if sufixo in WORD | EXCEL:
        return (CONVERTER, "") if converter else (COPIAR, "conversão desligada")
    return IGNORAR, f"formato {sufixo or '(sem extensão)'} não aceito"


def planejar_fluxo(p: ParametrosFluxo) -> PlanoFluxo:
    """Valida os parâmetros e classifica cada arquivo da base. Não escreve nada."""
    espaco = EspacoTrabalho.abrir(p.base)
    nome = validar_nome_pasta(p.nome_destino)
    if not p.tipos:
        raise ErroValidacao("Informe ao menos um tipo de documento.")
    if p.pasta_destino is None:
        pasta_destino = espaco.raiz.parent
    elif Path(p.pasta_destino).is_dir():
        pasta_destino = Path(p.pasta_destino).resolve()
    else:
        raise ErroValidacao("A pasta onde salvar não existe.", [str(p.pasta_destino)])
    destino_raiz = pasta_destino / nome
    if destino_raiz == espaco.raiz or espaco.raiz in destino_raiz.parents:
        raise ErroValidacao("A pasta nova não pode ficar dentro da pasta base.",
                            [str(destino_raiz)])
    if destino_raiz.exists():
        raise ErroValidacao("Já existe uma pasta com esse nome; escolha outro nome.",
                            [str(destino_raiz)])

    chaves = [(item, _chave_selecao(item)) for item in p.selecao]
    validas = [(item, chave) for item, chave in chaves if chave is not None]
    achados: dict[str, list[ItemFluxo]] = {item: [] for item, _ in validas}

    itens = []
    for origem in listar_arquivos(espaco):
        casados = [item for item, chave in validas if _casa(chave, origem)]
        if p.selecao and not casados:
            acao, motivo = IGNORAR, FORA_DA_LISTA
        else:
            acao, motivo = _classificar(origem, p.tipos, p.converter)
        destino = None if acao == IGNORAR else destino_raiz / origem.relative_to(espaco.raiz)
        item_fluxo = ItemFluxo(origem, acao, motivo, destino)
        itens.append(item_fluxo)
        for item in casados:
            achados[item].append(item_fluxo)

    problemas = []
    for item, chave in chaves:
        if chave is None:
            problemas.append((item, "formato inválido"))
        elif not achados[item]:
            problemas.append((item, "não encontrado na pasta base"))
        elif all(i.acao == IGNORAR for i in achados[item]):
            motivos = dict.fromkeys(i.motivo for i in achados[item])
            problemas.append((item, "; ".join(motivos)))

    trabalhos = planejar_conversao([i.destino for i in itens if i.acao == CONVERTER])
    copiados = {str(i.destino).casefold() for i in itens if i.acao == COPIAR}
    conflitos = [t.destino for t in trabalhos if str(t.destino).casefold() in copiados]
    return PlanoFluxo(p, espaco.raiz, destino_raiz, itens, trabalhos, conflitos, problemas)


def executar_fluxo(
    plano: PlanoFluxo,
    relatorio: Relatorio,
    ao_progresso: Callable[[str, int, int], None] | None = None,
    ao_log: Callable[[str], None] | None = None,
    cancelado: Callable[[], bool] = lambda: False,
    funcao_conversao: Callable[..., tuple[str, str]] = converter_arquivo,
    criar_executor: Callable[[int], Executor] | None = None,
) -> ResumoFluxo:
    """Cria a pasta nova, copia, converte, apaga os originais convertidos e limpa
    pastas vazias. Falhas por arquivo são registradas e o fluxo continua."""
    destino_raiz = plano.destino_raiz
    resumo = ResumoFluxo(destino_raiz, ignorados=len(plano.ignorados))
    progresso = ao_progresso or (lambda etapa, atual, total: None)
    log = ao_log or (lambda mensagem: None)

    def rel(caminho: Path) -> str:
        return caminho.relative_to(destino_raiz).as_posix()

    try:
        destino_raiz.mkdir(parents=False)
    except FileExistsError as erro:
        raise ErroValidacao("Já existe uma pasta com esse nome; escolha outro nome.",
                            [str(destino_raiz)]) from erro
    except OSError as erro:
        raise ErroValidacao(f"Não foi possível criar a pasta nova: {erro}",
                            [str(destino_raiz)]) from erro
    log(f"Pasta criada: {destino_raiz}")

    # 1. Cópia dos arquivos que entram na entrega.
    a_copiar = [i for i in plano.itens if i.acao != IGNORAR]
    falharam: set[str] = set()
    for numero, item in enumerate(a_copiar, 1):
        if cancelado():
            resumo.cancelado = True
            log("Interrompido pelo usuário durante a cópia.")
            break
        assert item.destino is not None
        try:
            item.destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.origem, item.destino)
            # A cópia herda "somente leitura" da origem; na pasta nova ela precisa poder
            # ser substituída (conflito de PDF) ou apagada (original já convertido).
            os.chmod(item.destino, stat.S_IREAD | stat.S_IWRITE)
            if item.acao == COPIAR:
                resumo.copiados += 1
        except OSError as erro:
            if item.destino.exists():
                try:
                    item.destino.unlink()  # não deixa cópia parcial na entrega
                except OSError:
                    pass
            falharam.add(str(item.destino).casefold())
            resumo.erros.append((rel(item.destino), f"falha ao copiar: {erro}"))
            log(f"ERRO: {rel(item.destino)}: falha ao copiar: {erro}")
        progresso("Copiando", numero, len(a_copiar))

    # 2. Conversão dos Word/Excel copiados; o original sai só se a conversão deu certo.
    resultados: list[ResultadoConversao] = []
    trabalhos = [t for t in plano.trabalhos
                 if str(t.origem).casefold() not in falharam and t.origem.exists()]
    if trabalhos and not resumo.cancelado:
        def concluido(resultado: ResultadoConversao, feitos: int, total: int) -> None:
            origem = resultado.trabalho.origem
            if resultado.status == "convertido":
                resumo.convertidos += 1
                log(f"OK: {rel(resultado.trabalho.destino)}")
                try:
                    if destino_raiz in origem.resolve().parents:
                        origem.unlink()
                except OSError as erro:
                    resumo.erros.append((rel(origem), f"PDF gerado, mas o original não "
                                                      f"pôde ser removido: {erro}"))
                    log(f"ERRO: {rel(origem)}: original não removido: {erro}")
            elif resultado.status == "erro":
                resumo.erros.append((rel(origem), resultado.detalhe))
                log(f"ERRO: {rel(origem)}: {resultado.detalhe}")
            progresso("Convertendo", feitos, total)

        resultados = executar_conversao(
            trabalhos, plano.parametros.processos, ao_concluir=concluido, cancelado=cancelado,
            funcao=funcao_conversao, criar_executor=criar_executor)
        if any(r.status == "cancelado" for r in resultados):
            resumo.cancelado = True
            log("Interrompido pelo usuário: conversões pendentes não foram feitas.")

    # 3. Limpeza e relatórios.
    progresso("Finalizando", 0, 1)
    remover_pastas_vazias(destino_raiz)
    if resultados:
        gravar_relatorio_conversao(resultados, destino_raiz, relatorio,
                                   destino_raiz / RELATORIO_CONVERTIDOS)
    relatorio.gravar(destino_raiz / RELATORIO_IGNORADOS, CABECALHO_IGNORADOS,
                     [[i.origem.relative_to(plano.base).as_posix(), i.motivo]
                      for i in plano.ignorados])
    progresso("Finalizando", 1, 1)
    return resumo
