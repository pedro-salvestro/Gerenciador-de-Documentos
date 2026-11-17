from pathlib import Path
from datetime import datetime
import csv
import os
import argparse
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
import shutil
import subprocess
import tempfile
import unicodedata

WORD = {".doc", ".docx", ".docm", ".dot", ".dotx", ".dotm"}
EXCEL = {".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm"}
CAD = {".step", ".stp", ".dwg"}


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
                print(f"AVISO: nao foi possivel encerrar o Office: {erro}")


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


try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


RAIZ = Path(__file__).resolve().parent
RELATORIO_CONVERTIDOS = RAIZ / "arquivos_convertidos.csv"
RELATORIO_APAGADOS = RAIZ / "arquivos_apagados.csv"
IGNORAR_DIRS = {"__pycache__", ".git"}


def listar_arquivos():
    arquivos = []
    for pasta, diretorios, nomes in os.walk(RAIZ, followlinks=False):
        diretorios[:] = sorted(
            d for d in diretorios
            if d.casefold() not in IGNORAR_DIRS and not d.startswith(".pdf_")
        )
        for nome in sorted(nomes, key=str.casefold):
            caminho = Path(pasta) / nome
            if caminho.is_symlink() or nome.startswith("~$"):
                continue
            if caminho.resolve() in {RELATORIO_CONVERTIDOS.resolve(), RELATORIO_APAGADOS.resolve()}:
                continue
            arquivos.append(caminho)
    return arquivos


def documentos_convertiveis():
    return [p for p in listar_arquivos() if p.suffix.casefold() in WORD | EXCEL]


def gravar_csv(caminho, cabecalho, linhas):
    with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def converter_todos():
    documentos = documentos_convertiveis()
    print(f"\nDocumentos Word/Excel encontrados: {len(documentos)}")
    if not documentos:
        input("Pressione Enter para voltar ao menu...")
        return

    contagens = {}
    for origem in documentos:
        chave = str(origem.with_suffix(".pdf")).casefold()
        contagens[chave] = contagens.get(chave, 0) + 1
    trabalhos = []
    reservados = set()
    for origem in documentos:
        destino = origem.with_suffix(".pdf")
        if contagens[str(destino).casefold()] > 1:
            destino = origem.with_name(origem.name + ".pdf")
        base = destino
        numero = 2
        while str(destino).casefold() in reservados:
            destino = base.with_name(f"{base.stem}_{numero}.pdf")
            numero += 1
        reservados.add(str(destino).casefold())
        trabalhos.append((origem, destino))

    limite = max(1, min(2, os.cpu_count() or 1))
    while True:
        texto = input(f"Quantos processos simultâneos? [1-{len(trabalhos)}] (padrão {limite}): ").strip()
        if not texto:
            processos = min(limite, len(trabalhos))
            break
        try:
            processos = int(texto)
            if 1 <= processos <= len(trabalhos):
                break
        except ValueError:
            pass
        print(f"Digite um número inteiro entre 1 e {len(trabalhos)}.")

    print(f"Conversão de Word: Office quando disponível; LibreOffice como alternativa. Processos: {processos}.")
    print("Conversão de Excel: Microsoft Excel. Os PDFs antigos são substituídos somente após sucesso.")
    if input("Iniciar conversão de todos? [s/N]: ").strip().casefold() not in {"s", "sim"}:
        return

    resultados = []
    concluidos = {}
    multiprocessing.freeze_support()
    with ProcessPoolExecutor(
        max_workers=min(processos, len(trabalhos)),
        mp_context=multiprocessing.get_context("spawn"),
    ) as pool:
        futuros = {
            pool.submit(converter_arquivo, origem, destino, "auto", True): (origem, destino)
            for origem, destino in trabalhos
        }
        for indice, futuro in enumerate(as_completed(futuros), 1):
            origem, destino = futuros[futuro]
            try:
                status, detalhe = futuro.result()
            except Exception as erro:
                status, detalhe = "erro", str(erro)
            if status == "ok":
                status, detalhe = "convertido", ""
                print(f"OK: {destino.relative_to(RAIZ)}")
            else:
                print(f"ERRO: {origem.relative_to(RAIZ)}: {detalhe}")
            concluidos[origem] = [datetime.now().isoformat(timespec="seconds"),
                                  str(origem.relative_to(RAIZ)), str(destino.relative_to(RAIZ)),
                                  status, detalhe]
            print(f"Progresso: {indice}/{len(trabalhos)}")
    resultados = [concluidos[o] for o, _ in trabalhos]
    gravar_csv(RELATORIO_CONVERTIDOS,
               ["data_hora", "arquivo_origem", "arquivo_pdf", "resultado", "detalhe"], resultados)
    ok = sum(l[3] == "convertido" for l in resultados)
    print(f"\nConvertidos: {ok}; erros: {len(resultados) - ok}.")
    print(f"Relatório: {RELATORIO_CONVERTIDOS}")
    input("Pressione Enter para voltar ao menu...")


def tipo_limpeza(caminho):
    if caminho.suffix.casefold() == ".pdf":
        return None
    codigo = re.search(r"-(ET|DT|MD)-\d+$", caminho.stem, re.IGNORECASE)
    if codigo:
        return f"documento {codigo.group(1).upper()}"
    if caminho.suffix.casefold() in CAD:
        return "arquivo STEP/DWG"
    if caminho.suffix.casefold() in WORD | EXCEL:
        return "documento Word/Excel"
    return "outro arquivo"


def listar_pastas_vazias():
    vazias = []
    for pasta, diretorios, _ in os.walk(RAIZ, topdown=False, followlinks=False):
        atual = Path(pasta)
        if atual == RAIZ or atual.is_symlink():
            continue
        try:
            if not any(atual.iterdir()):
                vazias.append(atual)
        except OSError:
            continue
    return sorted(vazias, key=lambda p: str(p).casefold())


def separar_lista(texto):
    """Aceita itens separados por vírgula, ponto e vírgula ou quebra de linha."""
    return [item.strip().strip('"').strip("'").replace("\\", "/").strip("/").casefold()
            for item in re.split(r"[;,\r\n]+", texto) if item.strip()]


def escolher_arquivos_manter():
    if send2trash is None:
        print("Falta a dependência Send2Trash. Instale com: py -m pip install Send2Trash")
        input("Pressione Enter para voltar ao menu...")
        return

    print("Informe os nomes ou caminhos relativos dos arquivos que devem ser mantidos,")
    print("separados por vírgula, ponto e vírgula ou uma entrada por linha.")
    print("Exemplo: projeto/modelo.dwg, notas.docx")
    texto = input("Arquivos a manter: ").strip()
    manter = set(separar_lista(texto))
    if not manter:
        print("Lista vazia; operação cancelada para evitar apagar todos os arquivos.")
        input("Pressione Enter para voltar ao menu...")
        return

    arquivos = []
    arquivos_escaneados = listar_arquivos()
    correspondencias = set()
    for caminho in arquivos_escaneados:
        if caminho.suffix.casefold() == ".pdf":
            continue
        if caminho.resolve() in {RELATORIO_CONVERTIDOS.resolve(), RELATORIO_APAGADOS.resolve()}:
            continue
        if caminho.resolve() == Path(__file__).resolve():
            continue
        relativo = str(caminho.relative_to(RAIZ)).replace("\\", "/").casefold()
        nome = caminho.name.casefold()
        nome_sem_extensao = caminho.stem.casefold()
        relativo_sem_extensao = str(caminho.relative_to(RAIZ).with_suffix("")).replace("\\", "/").casefold()
        nomes_correspondentes = {relativo, nome, nome_sem_extensao, relativo_sem_extensao}
        correspondencias.update(manter & nomes_correspondentes)
        if not manter.intersection(nomes_correspondentes):
            arquivos.append(caminho)

    nao_encontrados = manter - correspondencias
    if nao_encontrados:
        print("Não encontrei estes nomes na pasta de trabalho; operação cancelada para evitar exclusões incorretas:")
        for item in sorted(nao_encontrados):
            print(f" - {item}")
        input("Pressione Enter para voltar ao menu...")
        return

    print(f"\nArquivos da lista mantidos: {len(manter)} entrada(s).")
    print(f"Arquivos que serão enviados à Lixeira: {len(arquivos)}")
    for caminho in arquivos:
        print(f" - {caminho.relative_to(RAIZ)}")
    if not arquivos:
        print("Nenhum arquivo restante para apagar.")
        input("Pressione Enter para voltar ao menu...")
        return
    if input(f"\nEnviar esses {len(arquivos)} arquivo(s) à Lixeira? [s/N]: ").strip().casefold() not in {"s", "sim"}:
        print("Cancelado; nenhum arquivo foi removido.")
        return

    resultados = []
    for caminho in arquivos:
        try:
            resolvido = caminho.resolve(strict=True)
            if caminho.is_symlink() or RAIZ.resolve() not in resolvido.parents:
                raise RuntimeError("Caminho inseguro; preservado.")
            send2trash(str(resolvido))
            status, detalhe = "enviado à Lixeira", ""
            print(f"ENVIADO À LIXEIRA: {caminho.relative_to(RAIZ)}")
        except Exception as erro:
            status, detalhe = "erro", str(erro)
            print(f"ERRO: {caminho}: {detalhe}")
        resultados.append([datetime.now().isoformat(timespec="seconds"), str(caminho.relative_to(RAIZ)),
                           "arquivo fora da lista de manutenção", status, detalhe])
    gravar_csv(RELATORIO_APAGADOS,
               ["data_hora", "arquivo", "tipo", "resultado", "detalhe"], resultados)
    print(f"Relatório: {RELATORIO_APAGADOS}")
    input("Pressione Enter para voltar ao menu...")


def escolher_pastas_manter():
    if send2trash is None:
        print("Falta a dependência Send2Trash. Instale com: py -m pip install Send2Trash")
        input("Pressione Enter para voltar ao menu...")
        return

    pastas = []
    for raiz_atual, diretorios, _ in os.walk(RAIZ, topdown=True, followlinks=False):
        diretorios[:] = [d for d in diretorios if not d.startswith(".pdf_") and d.casefold() not in IGNORAR_DIRS]
        pastas.extend(Path(raiz_atual) / nome for nome in diretorios)
    pastas = sorted((p for p in pastas if not p.is_symlink()), key=lambda p: (len(p.parts), str(p).casefold()))
    if not pastas:
        print("Não há subpastas para processar.")
        input("Pressione Enter para voltar ao menu...")
        return

    print("Informe os nomes ou caminhos relativos das pastas que devem ser mantidas,")
    print("separados por vírgula, ponto e vírgula ou uma entrada por linha.")
    print("A pasta selecionada e todo o seu conteúdo serão preservados.")
    print("Exemplo: projeto/modelos; documentos importantes")
    texto = input("Pastas a manter: ").strip()
    manter = set(separar_lista(texto))
    if not manter:
        print("Lista vazia; operação cancelada para evitar apagar todas as pastas.")
        input("Pressione Enter para voltar ao menu...")
        return

    caminhos_manter = set()
    correspondencias = set()
    for pasta in pastas:
        relativo = str(pasta.relative_to(RAIZ)).replace("\\", "/").casefold()
        nome = pasta.name.casefold()
        if relativo in manter or nome in manter:
            caminhos_manter.add(pasta.resolve())
            correspondencias.update(manter & {relativo, nome})

    nao_encontrados = manter - correspondencias
    if nao_encontrados:
        print("Não encontrei estas pastas na pasta de trabalho; operação cancelada para evitar exclusões incorretas:")
        for item in sorted(nao_encontrados):
            print(f" - {item}")
        input("Pressione Enter para voltar ao menu...")
        return

    apagar = []
    for pasta in pastas:
        resolvida = pasta.resolve()
        # Protege a pasta indicada, todos os seus descendentes e as pastas-pai
        # necessárias para preservar o caminho relativo.
        protegida = any(k == resolvida or k in resolvida.parents or resolvida in k.parents
                        for k in caminhos_manter)
        if not protegida:
            apagar.append(pasta)

    # Envia apenas as pastas mais externas de cada ramo; o envio à Lixeira inclui
    # automaticamente as subpastas que também foram selecionadas para remoção.
    raizes_apagar = []
    for pasta in apagar:
        if not any(pai == selecionada or selecionada in pai.parents
                   for selecionada in raizes_apagar for pai in (pasta,)):
            raizes_apagar.append(pasta)

    print(f"\nPastas correspondentes à lista de manutenção: {len(caminhos_manter)}")
    for pasta in sorted(caminhos_manter, key=lambda p: str(p).casefold()):
        print(f" MANTER: {pasta.relative_to(RAIZ)}")
    print(f"Pastas que serão enviadas à Lixeira: {len(raizes_apagar)}")
    for pasta in raizes_apagar:
        print(f" - {pasta.relative_to(RAIZ)}")
    if not raizes_apagar:
        print("Nenhuma pasta restante para apagar.")
        input("Pressione Enter para voltar ao menu...")
        return
    if input(f"\nEnviar essas {len(raizes_apagar)} pasta(s) à Lixeira? [s/N]: ").strip().casefold() not in {"s", "sim"}:
        print("Cancelado; nenhuma pasta foi removida.")
        return

    resultados = []
    for pasta in raizes_apagar:
        try:
            resolvida = pasta.resolve(strict=True)
            if pasta.is_symlink() or RAIZ.resolve() not in resolvida.parents or resolvida == RAIZ.resolve():
                raise RuntimeError("Caminho inseguro; preservado.")
            send2trash(str(resolvida))
            status, detalhe = "enviada à Lixeira", ""
            print(f"ENVIADA À LIXEIRA: {pasta.relative_to(RAIZ)}")
        except Exception as erro:
            status, detalhe = "erro", str(erro)
            print(f"ERRO: {pasta}: {detalhe}")
        resultados.append([datetime.now().isoformat(timespec="seconds"), str(pasta.relative_to(RAIZ)),
                           "pasta fora da lista de manutenção", status, detalhe])
    gravar_csv(RELATORIO_APAGADOS,
               ["data_hora", "arquivo", "tipo", "resultado", "detalhe"], resultados)
    print(f"Relatório: {RELATORIO_APAGADOS}")
    input("Pressione Enter para voltar ao menu...")


def escolher_apagados():
    todos = [(p, tipo_limpeza(p)) for p in listar_arquivos()]
    candidatos = [(p, t) for p, t in todos if t]
    pastas_vazias = listar_pastas_vazias()
    if not candidatos and not pastas_vazias:
        print("Não há arquivos não PDF nem pastas vazias para apagar.")
        input("Pressione Enter para voltar ao menu...")
        return
    print("\nO que deseja selecionar para enviar à Lixeira?")
    print("1. Todos os arquivos não PDF")
    print("2. Documentos Word/Excel")
    print("3. Escolher extensões")
    print("4. Escolher arquivos individualmente")
    print("5. Apagar pastas vazias")
    print("6. Apagar arquivos STEP/DWG")
    print("7. Manter uma lista de arquivos e apagar os demais")
    print("8. Manter uma lista de pastas e apagar as demais")
    print("9. Apagar documentos ET, DT e MD (-ET-###, -DT-###, -MD-###), inclusive PDFs")
    print("0. Voltar")
    escolha = input("Opção: ").strip()
    if escolha == "0":
        return
    if escolha == "7":
        escolher_arquivos_manter()
        return
    if escolha == "8":
        escolher_pastas_manter()
        return
    if escolha == "9":
        codigos_especiais = {"documento ET", "documento DT", "documento MD"}
        docs_nao_pdf = [(p, t) for p, t in candidatos if t in codigos_especiais]
        docs_pdf = []
        for p in listar_arquivos():
            if p.suffix.casefold() != ".pdf":
                continue
            codigo = re.search(r"-(ET|DT|MD)-\d+$", p.stem, re.IGNORECASE)
            if codigo:
                docs_pdf.append((p, f"documento {codigo.group(1).upper()}"))
        selecionados = docs_nao_pdf + docs_pdf
        if not selecionados:
            print("Não encontrei documentos com nome nos padrões *-ET-###, *-DT-### ou *-MD-###.")
            input("Pressione Enter para voltar ao menu...")
            return
    elif escolha == "5":
        if not pastas_vazias:
            print("Não há pastas vazias.")
            input("Pressione Enter para voltar ao menu...")
            return
        selecionados = [(p, "pasta vazia") for p in pastas_vazias]
    elif escolha == "6":
        selecionados = [(p, t) for p, t in candidatos if t == "arquivo STEP/DWG"]
        if not selecionados:
            print("Não foram encontrados arquivos .step, .stp ou .dwg.")
            input("Pressione Enter para voltar ao menu...")
            return
    elif escolha == "1":
        selecionados = candidatos
        # Estes relatórios são ocultados da varredura geral para não serem
        # confundidos com documentos comuns, mas entram nesta limpeza explícita.
        for relatorio in (RELATORIO_APAGADOS, RELATORIO_CONVERTIDOS):
            if relatorio.is_file():
                selecionados.append((relatorio, "relatório CSV"))
    elif escolha == "2":
        selecionados = [(p, t) for p, t in candidatos if t == "documento Word/Excel"]
    elif escolha == "3":
        extensoes = sorted({p.suffix.casefold() or "(sem extensão)" for p, _ in candidatos})
        for i, ext in enumerate(extensoes, 1):
            print(f"{i}. {ext}")
        texto = input("Números separados por vírgula: ")
        try:
            indices = {int(n.strip()) for n in texto.split(",") if n.strip()}
            escolhidas = {extensoes[i - 1] for i in indices if 1 <= i <= len(extensoes)}
        except ValueError:
            print("Seleção inválida.")
            return
        selecionados = [(p, t) for p, t in candidatos if (p.suffix.casefold() or "(sem extensão)") in escolhidas]
    elif escolha == "4":
        for i, (p, tipo) in enumerate(candidatos, 1):
            print(f"{i}. {p.relative_to(RAIZ)} [{tipo}]")
        texto = input("Números separados por vírgula (ou 'todos'): ").strip().casefold()
        if texto == "todos":
            selecionados = candidatos
        else:
            try:
                indices = {int(n.strip()) for n in texto.split(",") if n.strip()}
                selecionados = [item for i, item in enumerate(candidatos, 1) if i in indices]
            except ValueError:
                print("Seleção inválida.")
                return
    else:
        print("Opção inválida.")
        return
    if not selecionados:
        print("Nenhum arquivo selecionado.")
        return
    if send2trash is None:
        print("Falta a dependência Send2Trash. Instale com: py -m pip install Send2Trash")
        input("Pressione Enter para voltar ao menu...")
        return
    print("\nPrévia dos arquivos selecionados:")
    for caminho, _ in selecionados:
        print(f" - {caminho.relative_to(RAIZ)}")
    if input(f"\nEnviar {len(selecionados)} arquivo(s) à Lixeira? [s/N]: ").strip().casefold() not in {"s", "sim"}:
        print("Cancelado; nenhum arquivo foi removido.")
        return
    resultados = []
    for caminho, tipo in selecionados:
        try:
            resolvido = caminho.resolve(strict=True)
            if caminho.is_symlink() or RAIZ.resolve() not in resolvido.parents or resolvido == RAIZ.resolve():
                raise RuntimeError("Caminho inseguro; preservado.")
            if tipo == "pasta vazia" and (not resolvido.is_dir() or any(resolvido.iterdir())):
                raise RuntimeError("A pasta não está mais vazia; preservada.")
            send2trash(str(resolvido))
            status, detalhe = "enviado à Lixeira", ""
            print(f"ENVIADO À LIXEIRA: {caminho.relative_to(RAIZ)}")
        except Exception as erro:
            status, detalhe = "erro", str(erro)
            print(f"ERRO: {caminho}: {detalhe}")
        resultados.append([datetime.now().isoformat(timespec="seconds"), str(caminho.relative_to(RAIZ)), tipo, status, detalhe])
    if any(caminho.resolve() == RELATORIO_APAGADOS.resolve() for caminho, _ in selecionados):
        # O usuário escolheu apagar o próprio arquivo de relatório; não o recriamos.
        print("O CSV de arquivos apagados foi incluído na limpeza e não será recriado nesta execução.")
    else:
        gravar_csv(RELATORIO_APAGADOS,
                   ["data_hora", "arquivo", "tipo", "resultado", "detalhe"], resultados)
        print(f"Relatório: {RELATORIO_APAGADOS}")
    input("Pressione Enter para voltar ao menu...")


def mostrar_relatorio(caminho):
    if not caminho.exists():
        print("O relatório ainda não foi gerado.")
    else:
        print(f"\nRelatório: {caminho}")
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            for linha in csv.reader(arquivo, delimiter=";"):
                print(" | ".join(linha))
    input("Pressione Enter para voltar ao menu...")


def copiar_arquivos_listados():
    print("Informe os códigos dos itens (ex.: NVC00410A), separados por vírgula,")
    print("ponto e vírgula ou uma entrada por linha. Serão copiados todos os arquivos cujo")
    print("nome comece pelo código informado, como NVC00410A-DE-001.pdf.")
    texto = input("Códigos para copiar: ").strip()
    solicitados = set(separar_lista(texto))
    if not solicitados:
        print("Lista vazia; nenhuma cópia foi feita.")
        input("Pressione Enter para voltar ao menu...")
        return

    nome_destino = input("Nome da pasta final (ex.: Arquivos): ").strip()
    if (not nome_destino or Path(nome_destino).name != nome_destino
            or nome_destino in {".", ".."} or re.search(r'[<>:"/\\|?*]', nome_destino)):
        print("Nome de pasta inválido; use apenas o nome, sem caminho.")
        input("Pressione Enter para voltar ao menu...")
        return

    destinos_por_codigo = {}
    codigos_invalidos = []
    for codigo in solicitados:
        partes = re.fullmatch(r"(NVC\d+)([A-Z])", codigo, re.IGNORECASE)
        if not partes:
            codigos_invalidos.append(codigo)
            continue
        equipamento, variante = partes.groups()
        destinos_por_codigo[codigo] = RAIZ / equipamento / variante / nome_destino
    if codigos_invalidos:
        print("Estes códigos não seguem o formato NVC + número + variante (ex.: NVC00410A); cópia cancelada:")
        for codigo in sorted(codigos_invalidos):
            print(f" - {codigo}")
        input("Pressione Enter para voltar ao menu...")
        return
    destinos_existentes = [p for p in destinos_por_codigo.values() if p.exists()]
    if destinos_existentes:
        print("Já existe pasta de destino; cópia cancelada para não sobrescrever conteúdo:")
        for caminho in destinos_existentes:
            print(f" - {caminho.relative_to(RAIZ)}")
        input("Pressione Enter para voltar ao menu...")
        return

    correspondencias = {codigo: [] for codigo in solicitados}
    for caminho in listar_arquivos():
        stem = caminho.stem.casefold()
        for codigo in solicitados:
            if stem == codigo or stem.startswith(codigo + "-"):
                correspondencias[codigo].append(caminho)

    nao_encontrados = [item for item, achados in correspondencias.items() if not achados]
    if nao_encontrados:
        print("Não encontrei estes itens; cópia cancelada:")
        for item in sorted(nao_encontrados):
            print(f" - {item}")
        input("Pressione Enter para voltar ao menu...")
        return

    destinos_arquivos = []
    nomes_destino = set()
    for codigo, achados in correspondencias.items():
        destino = destinos_por_codigo[codigo]
        for origem in achados:
            chave = (str(destino).casefold(), origem.name.casefold())
            if chave in nomes_destino:
                print(f"Há arquivos com o mesmo nome para {codigo}; cópia cancelada para evitar sobrescrita: {origem.name}")
                input("Pressione Enter para voltar ao menu...")
                return
            nomes_destino.add(chave)
            destinos_arquivos.append((origem, destino / origem.name))

    print("\nPrévia dos arquivos e destinos:")
    for origem, destino_arquivo in destinos_arquivos:
        print(f" - {origem.relative_to(RAIZ)} -> {destino_arquivo.relative_to(RAIZ)}")
    if input("\nConfirmar cópia? [s/N]: ").strip().casefold() not in {"s", "sim"}:
        print("Cancelado; nenhum arquivo foi copiado.")
        return

    try:
        copiados = 0
        for origem, destino_arquivo in destinos_arquivos:
            if origem.is_symlink() or not origem.is_file():
                print(f"IGNORADO: {origem.relative_to(RAIZ)} (não é arquivo regular)")
                continue
            destino_arquivo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino_arquivo)
            copiados += 1
            print(f"COPIADO: {origem.relative_to(RAIZ)} -> {destino_arquivo.relative_to(RAIZ)}")
        print(f"\nCópia concluída: {copiados} arquivo(s) organizados em pastas NVCxxx/variante/{nome_destino}.")
    except Exception as erro:
        print(f"Erro durante a cópia: {erro}")
        print("Confira os arquivos que já foram copiados nas pastas de destino exibidas acima.")
    input("Pressione Enter para voltar ao menu...")


def main():
    while True:
        print("\n=== GERENCIADOR DE DOCUMENTOS ===")
        print(f"Pasta de trabalho: {RAIZ}")
        print("1. Converter todos os arquivos Word/Excel para PDF")
        print("2. Apagar arquivos ou pastas vazias (envia à Lixeira)")
        print("3. Ver lista de arquivos convertidos")
        print("4. Ver lista de arquivos apagados")
        print("5. Copiar arquivos listados para uma pasta nomeada")
        print("0. Sair")
        escolha = input("Escolha uma opção: ").strip()
        if escolha == "1":
            converter_todos()
        elif escolha == "2":
            escolher_apagados()
        elif escolha == "3":
            mostrar_relatorio(RELATORIO_CONVERTIDOS)
        elif escolha == "4":
            mostrar_relatorio(RELATORIO_APAGADOS)
        elif escolha == "5":
            copiar_arquivos_listados()
        elif escolha == "0":
            print("Até logo.")
            break
        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()

