"""Testes dos achados da revisão final (cada um reproduz um problema real)."""

import os
import pathlib
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import pytest
from PySide6.QtWidgets import QMessageBox

from conftest import criar
from falsos import converter_ok
from gerenciador.nucleo.arquivos import listar_arquivos
from gerenciador.nucleo.conversao import executar_conversao, planejar_conversao
from gerenciador.nucleo.fluxo import ParametrosFluxo, executar_fluxo, planejar_fluxo
from gerenciador.nucleo.limpeza import enviar_lixeira, selecionar_cad
from gerenciador.nucleo.relatorios import Relatorio

TIPOS = frozenset({"DE", "LI", "LD", "PR", "FO"})


def somente_leitura(caminho):
    os.chmod(caminho, stat.S_IREAD)


@pytest.fixture
def liberar_somente_leitura(tmp_path):
    yield
    for p in tmp_path.rglob("*"):
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass


# C1 ----------------------------------------------------------------------------------

def test_c1_original_somente_leitura_e_convertido(tmp_path, liberar_somente_leitura):
    base = tmp_path / "obra"
    criar(tmp_path, "obra/a/X-LI-001.docx", "obra/a/X-LI-002.docx", "obra/a/X-DE-009.pdf")
    somente_leitura(base / "a/X-LI-001.docx")
    plano = planejar_fluxo(ParametrosFluxo(base, "Entrega", TIPOS, processos=1))
    resumo = executar_fluxo(plano, Relatorio(), funcao_conversao=converter_ok,
                            criar_executor=ThreadPoolExecutor)
    arquivos = sorted(p.name for p in plano.destino_raiz.rglob("*.*"))
    assert "X-LI-001.docx" not in arquivos and "X-LI-002.docx" not in arquivos
    assert {"X-LI-001.pdf", "X-LI-002.pdf", "X-DE-009.pdf"} <= set(arquivos)
    assert resumo.convertidos == 2 and resumo.erros == []


def test_c1_conflito_com_pdf_somente_leitura(tmp_path, liberar_somente_leitura):
    base = tmp_path / "obra"
    criar(tmp_path, "obra/X-DE-001.pdf", "obra/X-DE-001.docx")
    somente_leitura(base / "X-DE-001.pdf")
    plano = planejar_fluxo(ParametrosFluxo(base, "Entrega", TIPOS, processos=1))
    resumo = executar_fluxo(plano, Relatorio(), funcao_conversao=converter_ok,
                            criar_executor=ThreadPoolExecutor)
    assert resumo.erros == []
    assert (plano.destino_raiz / "X-DE-001.pdf").read_bytes() == b"%PDF-fake"


def test_c1_falha_ao_remover_temporaria_nao_derruba(tmp_path, monkeypatch):
    # Os originais convertidos ficam na pasta temporária; se ela não puder ser removida
    # (arquivo em uso), o fluxo termina normalmente e só avisa.
    from gerenciador.nucleo import fluxo as modulo_fluxo
    base = tmp_path / "obra"
    criar(tmp_path, "obra/X-LI-001.docx", "obra/X-LI-002.docx")
    plano = planejar_fluxo(ParametrosFluxo(base, "Entrega", TIPOS, processos=1))

    def rmtree(caminho, *a, **k):
        raise PermissionError("em uso")

    monkeypatch.setattr(modulo_fluxo.shutil, "rmtree", rmtree)
    mensagens = []
    resumo = executar_fluxo(plano, Relatorio(), ao_log=mensagens.append,
                            funcao_conversao=converter_ok, criar_executor=ThreadPoolExecutor)
    assert resumo.convertidos == 2 and resumo.erros == []
    assert (plano.destino_raiz / "X-LI-001.pdf").exists()
    assert any(m.startswith("AVISO: não foi possível remover a pasta temporária") for m in mensagens)


# C2 ----------------------------------------------------------------------------------

def test_c2_tabela_grande_carrega_rapido(qtbot):
    from gerenciador.gui.tabela_itens import TabelaItens
    tabela = TabelaItens(["Arquivo", "Ação", "Motivo"], marcavel=True)
    qtbot.addWidget(tabela)
    linhas = [[f"pasta/{i:05d}.pdf", "Copiar", ""] for i in range(10000)]
    inicio = time.perf_counter()
    tabela.definir_linhas(linhas, list(range(10000)), marcados=True)
    assert time.perf_counter() - inicio < 3
    assert tabela.quantidade() == 10000
    assert tabela.model().index(0, 0).data() == "pasta/00000.pdf"
    assert len(tabela.marcados()) == 10000


# I1 ----------------------------------------------------------------------------------

class ExecutorQuebra(ThreadPoolExecutor):
    """Simula um pool de processos que quebra depois do primeiro envio."""

    def __init__(self, max_workers):
        super().__init__(max_workers)
        self.envios = 0

    def submit(self, *a, **k):
        self.envios += 1
        if self.envios > 1:
            raise BrokenProcessPool("processo filho terminou abruptamente")
        return super().submit(*a, **k)


def test_i1_pool_quebrado_marca_restantes_como_erro(tmp_path):
    trabalhos = planejar_conversao([tmp_path / f"{i}.docx" for i in range(4)])
    r = executar_conversao(trabalhos, 1, funcao=converter_ok, criar_executor=ExecutorQuebra)
    assert r[0].status == "convertido"
    assert [x.status for x in r[1:]] == ["erro", "erro", "erro"]
    assert "interrompido" in r[1].detalhe


# I2 ----------------------------------------------------------------------------------

def test_i2_varredura_nao_resolve_cada_arquivo(espaco, monkeypatch):
    criar(espaco.raiz, *[f"p/{i}.pdf" for i in range(200)])
    chamadas = []
    original = pathlib.Path.resolve

    def resolve(self, *a, **k):
        chamadas.append(self)
        return original(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    assert len(listar_arquivos(espaco)) == 200
    assert len(chamadas) < 20


def test_i2_relatorio_e_programa_ainda_excluidos(espaco, monkeypatch):
    from gerenciador.nucleo import espaco as modulo_espaco
    exe = espaco.raiz / "Ger.exe"
    criar(espaco.raiz, "Ger.exe", "ARQUIVOS_CONVERTIDOS.csv", "sub/arquivos_convertidos.csv", "a.pdf")
    monkeypatch.setattr(modulo_espaco, "caminhos_programa", lambda: frozenset({exe.resolve()}))
    from gerenciador.nucleo.espaco import EspacoTrabalho
    novo = EspacoTrabalho.abrir(espaco.raiz)
    assert [novo.relativo(p) for p in listar_arquivos(novo)] == ["a.pdf", "sub/arquivos_convertidos.csv"]


# I3 ----------------------------------------------------------------------------------

def test_i3_relatorio_bloqueado_nao_derruba_limpeza(espaco):
    criar(espaco.raiz, "m.dwg", "arquivos_apagados.csv/")  # pasta no lugar do CSV
    relatorio = Relatorio()
    r = enviar_lixeira(espaco, selecionar_cad(espaco), relatorio, lixeira=lambda c: None)
    assert r[0].status == "enviado à Lixeira"
    assert relatorio.erros and "arquivos_apagados.csv" in relatorio.erros[0]


# I4 ----------------------------------------------------------------------------------

def test_i4_limpeza_bloqueia_entradas_durante_envio(qtbot, config_temp, espaco, monkeypatch):
    from gerenciador.gui.aba_limpeza import AbaLimpeza
    criar(espaco.raiz, "m.dwg")
    liberar = threading.Event()
    aba = AbaLimpeza(config_temp, lambda: Relatorio(False), lixeira=lambda c: liberar.wait(5))
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    aba.lista_modos.setCurrentRow(5)
    qtbot.waitUntil(lambda: aba.tabela.quantidade() == 1, timeout=5000)
    aba.botao_enviar.click()
    assert not aba.seletor.isEnabled()
    assert not aba.area_parametros.isEnabled()
    assert not aba.botao_marcar.isEnabled()
    liberar.set()
    qtbot.waitUntil(lambda: aba.tabela.status(0) == "enviado à Lixeira", timeout=5000)
    assert aba.seletor.isEnabled() and aba.lista_modos.isEnabled()


def test_i4_copia_bloqueia_previa_durante_copia(qtbot, config_temp, espaco, monkeypatch):
    from gerenciador.gui import aba_copia
    from gerenciador.gui.aba_copia import AbaCopia
    criar(espaco.raiz, "NVC1A-DE-1.pdf")
    liberar = threading.Event()
    original = aba_copia.executar_copia
    monkeypatch.setattr(aba_copia, "executar_copia",
                        lambda plano: (liberar.wait(5), original(plano))[1])
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    aba = AbaCopia(config_temp)
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    aba.campo_codigos.setPlainText("NVC1A")
    aba.campo_nome.setText("Arquivos")
    aba.botao_previa.click()
    qtbot.waitUntil(aba.botao_copiar.isEnabled, timeout=5000)
    aba.botao_copiar.click()
    assert not aba.botao_previa.isEnabled() and not aba.seletor.isEnabled()
    liberar.set()
    qtbot.waitUntil(lambda: aba.tabela.status(0) == "copiado", timeout=5000)
    assert aba.botao_previa.isEnabled()
