"""Conversão de Word/Excel para PDF (Office via COM, LibreOffice como alternativa no Word).

As funções `Conversor`, `validar_pdf_a4` e `converter_arquivo` foram portadas do script
original sem mudança de comportamento. `converter_arquivo` roda no processo filho; objetos
COM nunca saem desse processo.
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import shutil
import subprocess
import tempfile
import unicodedata
from collections.abc import Callable
from concurrent.futures import (
    FIRST_COMPLETED, BrokenExecutor, Executor, ProcessPoolExecutor, wait,
)
from dataclasses import dataclass, field
from pathlib import Path

from .arquivos import listar_arquivos
from .constantes import EXCEL, WORD
from .espaco import EspacoTrabalho
from .relatorios import CABECALHO_CONVERTIDOS, Relatorio, agora

log = logging.getLogger(__name__)

def normalizar_nome_aba(nome):
    """Reconhece nomes com variacoes de caixa, acentos e espacos."""
    normalizado = unicodedata.normalize("NFKD", nome.casefold())
    normalizado = "".join(
        c for c in normalizado if not unicodedata.combining(c) and not c.isspace()
    )
    return normalizado


def orientacao_aba(nome):
    return 1 if normalizar_nome_aba(nome) in {"capa", "folhaderevisao"} else 2


def localizar_libreoffice():
    for nome in ("soffice", "libreoffice"):
        encontrado = shutil.which(nome)
        if encontrado:
            return encontrado
    for variavel in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        raiz = os.environ.get(variavel)
        if raiz:
            candidato = Path(raiz) / "LibreOffice/program/soffice.exe"
            if candidato.is_file():
                return str(candidato)
    candidato = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    return str(candidato) if candidato.is_file() else None


class Conversor:
    def __init__(self, mecanismo):
        self.incluir_abas_ocultas = True
        self.mecanismo = mecanismo
        self.apps = {}
        self.indisponiveis = {}
        self.libreoffice = localizar_libreoffice()

    def aplicativo_office(self, tipo):
        if tipo in self.indisponiveis:
            raise RuntimeError(self.indisponiveis[tipo])
        if tipo not in self.apps:
            app = None
            try:
                import win32com.client
                nome = "Word.Application" if tipo == "word" else "Excel.Application"
                app = win32com.client.DispatchEx(nome)
                app.Visible = False
                app.DisplayAlerts = 0
                # Desabilita macros dos documentos abertos por automacao.
                app.AutomationSecurity = 3
                if tipo == "excel":
                    app.AskToUpdateLinks = False
                else:
                    app.Options.UpdateLinksAtOpen = False
                self.apps[tipo] = app
            except Exception as erro:
                if app is not None:
                    try:
                        app.Quit()
                    except Exception:
                        pass
                mensagem = f"Office indisponivel ({tipo}): {erro}"
                self.indisponiveis[tipo] = mensagem
                raise RuntimeError(mensagem) from erro
        return self.apps[tipo]

    def converter(self, origem, destino):
        tipo = "word" if origem.suffix.lower() in WORD else "excel"
        if tipo == "excel":
            # Excel obrigatorio: nao troca silenciosamente o renderizador.
            app = self.aplicativo_office("excel")
            self.converter_office(app, tipo, origem, destino, self.incluir_abas_ocultas)
            return
        if self.mecanismo != "libreoffice":
            try:
                app = self.aplicativo_office(tipo)
            except RuntimeError:
                if self.mecanismo == "office" or not self.libreoffice:
                    raise
            else:
                self.converter_office(app, tipo, origem, destino)
                return
        self.converter_libreoffice(origem, destino)

    @staticmethod
    def converter_office(app, tipo, origem, destino, incluir_abas_ocultas=True):
        documento = None
        mapeamento_papel_original = None
        try:
            if tipo == "word":
                documento = app.Documents.Open(
                    FileName=str(origem), ReadOnly=True,
                    AddToRecentFiles=False, Visible=False,
                    PasswordDocument="", WritePasswordDocument="",
                )
                documento.ExportAsFixedFormat(
                    OutputFileName=str(destino), ExportFormat=17,
                    OpenAfterExport=False,
                )
            else:
                # O Excel pode trocar A4 por Carta mesmo com PaperSize=9.
                # Desativa essa compatibilidade apenas durante esta exportacao.
                mapeamento_papel_original = app.MapPaperSize
                app.MapPaperSize = False
                documento = app.Workbooks.Open(
                    Filename=str(origem), UpdateLinks=0, ReadOnly=True,
                    IgnoreReadOnlyRecommended=True, AddToMru=False,
                    Password="", WriteResPassword="",
                )
                if incluir_abas_ocultas:
                    for aba in documento.Sheets:
                        if aba.Visible != -1:
                            aba.Visible = -1  # xlSheetVisible; nao salva no original.
                for aba in documento.Worksheets:
                    if aba.Visible != -1:
                        continue
                    try:
                        pagina = aba.PageSetup
                        pagina.PaperSize = 9  # xlPaperA4 (210 x 297 mm).
                        pagina.Orientation = orientacao_aba(aba.Name)
                        pagina.Zoom = False  # Habilita FitToPagesWide/Tall.
                        pagina.FitToPagesWide = 1
                        capa = normalizar_nome_aba(aba.Name) == "capa"
                        if capa:
                            # A area da capa inclui a arte e exclui objetos de edicao
                            # distantes que causariam reducao excessiva na impressao.
                            pagina.FitToPagesTall = 1
                        else:
                            pagina.PrintArea = ""
                            pagina.FitToPagesTall = False  # Sem limite vertical.
                    except Exception as erro:
                        raise RuntimeError(
                            f"Nao foi possivel ajustar a impressao da aba {aba.Name!r}: {erro}"
                        ) from erro
                # Mantem larguras, alturas, fontes, mesclagens e titulos de impressao.
                # Nao aplica AutoFit: pode distorcer layouts e celulas mescladas.
                # Exporta a pasta de trabalho inteira, sem intervalo From/To.
                documento.ExportAsFixedFormat(
                    Type=0, Filename=str(destino), Quality=0,
                    IncludeDocProperties=True, IgnorePrintAreas=False,
                    OpenAfterPublish=False,
                )
        finally:
            try:
                if documento is not None:
                    documento.Close(SaveChanges=False)
            finally:
                if mapeamento_papel_original is not None:
                    app.MapPaperSize = mapeamento_papel_original

    def converter_libreoffice(self, origem, destino):
        if not self.libreoffice:
            raise RuntimeError("LibreOffice nao encontrado. Instale-o ou use Office + pywin32.")
        # Perfil separado evita interferir em uma sessao aberta do LibreOffice.
        with tempfile.TemporaryDirectory(prefix="conversao_pdf_") as pasta:
            temporaria = Path(pasta)
            perfil = (temporaria / "perfil").as_uri()
            resultado = subprocess.run(
                [self.libreoffice, f"-env:UserInstallation={perfil}",
                 "--headless", "--convert-to", "pdf", "--outdir",
                 str(temporaria), str(origem)],
                capture_output=True, text=True, errors="replace", timeout=180,
            )
            pdf = temporaria / (origem.stem + ".pdf")
            if resultado.returncode or not pdf.is_file():
                detalhe = (resultado.stderr or resultado.stdout).strip()
                raise RuntimeError(f"LibreOffice nao gerou o PDF: {detalhe}")
            shutil.copyfile(pdf, destino)

    def fechar(self):
        for app in self.apps.values():
            try:
                app.Quit()
            except Exception as erro:
                log.warning("Nao foi possivel encerrar o Office: %s", erro)


def validar_pdf_a4(caminho):
    """Confere o PDF real antes de substituir o anterior; tolerancia de 0,5 mm."""
    try:
        from pypdf import PdfReader
    except ImportError as erro:
        raise RuntimeError("Instale a validacao de PDF: py -m pip install pypdf") from erro
    with caminho.open("rb") as arquivo:
        leitor = PdfReader(arquivo)
        if not leitor.pages:
            raise RuntimeError("PDF sem paginas.")
        for numero, pagina in enumerate(leitor.pages, 1):
            unidade = float(pagina.get("/UserUnit", 1))
            for nome, caixa in (("papel", pagina.mediabox), ("area visivel", pagina.cropbox)):
                medidas = sorted(float(v) * unidade * 25.4 / 72
                                 for v in (caixa.width, caixa.height))
                if abs(medidas[0] - 210) > 0.5 or abs(medidas[1] - 297) > 0.5:
                    raise RuntimeError(
                        f"Pagina {numero}: {nome} fora do A4 "
                        f"({medidas[0]:.1f} x {medidas[1]:.1f} mm). "
                        "PDF anterior preservado. Confira o driver de impressao."
                    )


def converter_arquivo(origem, destino, mecanismo, incluir_abas_ocultas=True):
    """Executada no processo filho; objetos COM nunca saem desse processo."""
    conversor = Conversor(mecanismo)
    conversor.incluir_abas_ocultas = incluir_abas_ocultas
    com = None
    try:
        if (mecanismo != "libreoffice" or origem.suffix.lower() in EXCEL) and os.name == "nt":
            try:
                import pythoncom
            except ImportError:
                pass  # O modo automatico ainda pode usar LibreOffice.
            else:
                pythoncom.CoInitialize()
                com = pythoncom
        with tempfile.TemporaryDirectory(dir=origem.parent, prefix=".pdf_") as pasta:
            temporario = Path(pasta) / "convertido.pdf"
            conversor.converter(origem, temporario)
            if not temporario.is_file() or temporario.stat().st_size == 0:
                raise RuntimeError("O conversor nao produziu um PDF valido.")
            if origem.suffix.lower() in EXCEL:
                validar_pdf_a4(temporario)
            # Mesmo volume: substitui somente depois de concluir a exportacao.
            # Se a conversao ou a substituicao falhar, o PDF anterior permanece.
            os.replace(temporario, destino)
        return "ok", f"PID {os.getpid()}"
    except Exception as erro:
        return "erro", str(erro)
    finally:
        conversor.fechar()
        conversor.apps.clear()
        if com is not None:
            com.CoUninitialize()


# --- Planejamento e execução em lote -------------------------------------------------


@dataclass(frozen=True)
class TrabalhoConversao:
    origem: Path
    destino: Path


@dataclass
class ResultadoConversao:
    trabalho: TrabalhoConversao
    status: str  # "convertido" | "erro" | "cancelado"
    detalhe: str = ""
    data_hora: str = field(default_factory=agora)


def documentos_convertiveis(espaco: EspacoTrabalho) -> list[Path]:
    return [p for p in listar_arquivos(espaco) if p.suffix.casefold() in WORD | EXCEL]


def planejar_conversao(origens: list[Path]) -> list[TrabalhoConversao]:
    """Define o PDF de cada documento. Nomes que colidiriam ganham a extensão original
    (a.docx -> a.docx.pdf) e, se ainda colidirem, um sufixo numérico."""
    contagens: dict[str, int] = {}
    for origem in origens:
        chave = str(origem.with_suffix(".pdf")).casefold()
        contagens[chave] = contagens.get(chave, 0) + 1
    trabalhos = []
    reservados: set[str] = set()
    for origem in origens:
        destino = origem.with_suffix(".pdf")
        if contagens[str(destino).casefold()] > 1:
            destino = origem.with_name(origem.name + ".pdf")
        base = destino
        numero = 2
        while str(destino).casefold() in reservados:
            destino = base.with_name(f"{base.stem}_{numero}.pdf")
            numero += 1
        reservados.add(str(destino).casefold())
        trabalhos.append(TrabalhoConversao(origem, destino))
    return trabalhos


def processos_padrao(n: int) -> int:
    return min(max(1, min(2, os.cpu_count() or 1)), max(n, 1))


def _executor_processos(max_workers: int) -> Executor:
    return ProcessPoolExecutor(max_workers=max_workers,
                               mp_context=multiprocessing.get_context("spawn"))


def executar_conversao(
    trabalhos: list[TrabalhoConversao],
    processos: int,
    ao_concluir: Callable[[ResultadoConversao, int, int], None] | None = None,
    cancelado: Callable[[], bool] = lambda: False,
    funcao: Callable[..., tuple[str, str]] = converter_arquivo,
    criar_executor: Callable[[int], Executor] | None = None,
) -> list[ResultadoConversao]:
    """Converte em paralelo e devolve os resultados na ordem de `trabalhos`.

    Os trabalhos são enviados aos poucos (no máximo `processos` em andamento): ao
    cancelar, os que ainda não começaram são marcados como "cancelado" e os que já
    estão em andamento terminam normalmente (interromper o Office deixaria processos
    órfãos)."""
    total = len(trabalhos)
    resultados: dict[int, ResultadoConversao] = {}
    if not trabalhos:
        return []
    largura = max(1, min(processos, total))
    fabrica = criar_executor or _executor_processos

    def registrar(indice: int, resultado: ResultadoConversao) -> None:
        resultados[indice] = resultado
        if ao_concluir:
            ao_concluir(resultado, len(resultados), total)

    with fabrica(largura) as executor:
        fila = list(enumerate(trabalhos))
        em_andamento = {}
        while fila or em_andamento:
            while fila and len(em_andamento) < largura and not cancelado():
                indice, trabalho = fila[0]
                try:
                    futuro = executor.submit(funcao, trabalho.origem, trabalho.destino,
                                             "auto", True)
                except (BrokenExecutor, RuntimeError) as erro:
                    # Um processo de conversão morreu (ex.: falha do Office): os itens
                    # restantes não podem mais ser enviados a este pool.
                    detalhe = f"processo de conversão interrompido: {erro}"
                    for indice_restante, trabalho_restante in fila:
                        registrar(indice_restante,
                                  ResultadoConversao(trabalho_restante, "erro", detalhe))
                    fila.clear()
                    break
                fila.pop(0)
                em_andamento[futuro] = indice
            if cancelado() and fila:
                for indice, trabalho in fila:
                    registrar(indice, ResultadoConversao(trabalho, "cancelado",
                                                         "cancelado pelo usuário"))
                fila.clear()
            if not em_andamento:
                continue
            prontos, _ = wait(em_andamento, timeout=0.2, return_when=FIRST_COMPLETED)
            for futuro in prontos:
                indice = em_andamento.pop(futuro)
                trabalho = trabalhos[indice]
                try:
                    status, detalhe = futuro.result()
                except Exception as erro:  # noqa: BLE001 - falha do processo filho
                    status, detalhe = "erro", str(erro)
                if status == "ok":
                    registrar(indice, ResultadoConversao(trabalho, "convertido"))
                else:
                    registrar(indice, ResultadoConversao(trabalho, "erro", detalhe))
    return [resultados[i] for i in range(total)]


def gravar_relatorio_conversao(resultados: list[ResultadoConversao], base_relativa: Path,
                               relatorio: Relatorio, caminho: Path) -> Path | None:
    linhas = [[r.data_hora,
               r.trabalho.origem.relative_to(base_relativa).as_posix(),
               r.trabalho.destino.relative_to(base_relativa).as_posix(),
               r.status, r.detalhe] for r in resultados]
    return relatorio.gravar(caminho, CABECALHO_CONVERTIDOS, linhas)


def detectar_mecanismos() -> dict[str, bool]:
    """Detecta Word, Excel e LibreOffice sem abrir nenhum deles."""
    disponivel = {"word": False, "excel": False,
                  "libreoffice": localizar_libreoffice() is not None}
    try:
        import winreg
    except ImportError:
        return disponivel
    for chave, progid in (("word", "Word.Application"), ("excel", "Excel.Application")):
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid))
            disponivel[chave] = True
        except OSError:
            pass
    return disponivel
