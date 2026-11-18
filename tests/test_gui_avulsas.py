from concurrent.futures import ThreadPoolExecutor

from PySide6.QtWidgets import QMessageBox

from conftest import criar
from falsos import converter_ok
from gerenciador.gui.aba_conversao import AbaConversao
from gerenciador.gui.aba_copia import AbaCopia
from gerenciador.gui.aba_relatorios import AbaRelatorios
from gerenciador.nucleo.relatorios import Relatorio

SIM = QMessageBox.StandardButton.Yes


def test_conversao_analisa_e_converte(qtbot, config_temp, espaco, monkeypatch):
    criar(espaco.raiz, "a.docx", "b.pdf")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: SIM)
    aba = AbaConversao(config_temp, lambda: Relatorio(), funcao=converter_ok,
                       criar_executor=ThreadPoolExecutor)
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    aba.botao_analisar.click()
    qtbot.waitUntil(aba.botao_iniciar.isEnabled, timeout=5000)
    assert aba.tabela.quantidade() == 1
    aba.botao_iniciar.click()
    qtbot.waitUntil(lambda: aba.tabela.status(0) == "convertido", timeout=5000)
    assert (espaco.raiz / "a.pdf").exists()
    assert (espaco.raiz / "arquivos_convertidos.csv").exists()


def test_conversao_sem_relatorio(qtbot, config_temp, espaco, monkeypatch):
    criar(espaco.raiz, "a.docx")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: SIM)
    aba = AbaConversao(config_temp, lambda: Relatorio(False), funcao=converter_ok,
                       criar_executor=ThreadPoolExecutor)
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    aba.botao_analisar.click()
    qtbot.waitUntil(aba.botao_iniciar.isEnabled, timeout=5000)
    aba.botao_iniciar.click()
    qtbot.waitUntil(lambda: aba.tabela.status(0) == "convertido", timeout=5000)
    assert not (espaco.raiz / "arquivos_convertidos.csv").exists()


def test_copia_erro_validacao_mostra_itens(qtbot, config_temp, espaco):
    criar(espaco.raiz, "NVC1A-DE-1.pdf")
    aba = AbaCopia(config_temp)
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    aba.campo_codigos.setPlainText("abc")
    aba.campo_nome.setText("Arquivos")
    aba.botao_previa.click()
    qtbot.waitUntil(lambda: "abc" in aba.rotulo_erro.text(), timeout=5000)
    assert not aba.botao_copiar.isEnabled()


def test_copia_executa(qtbot, config_temp, espaco, monkeypatch):
    criar(espaco.raiz, "NVC1A-DE-1.pdf")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: SIM)
    aba = AbaCopia(config_temp)
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    aba.campo_codigos.setPlainText("NVC1A")
    aba.campo_nome.setText("Arquivos")
    aba.botao_previa.click()
    qtbot.waitUntil(aba.botao_copiar.isEnabled, timeout=5000)
    aba.botao_copiar.click()
    qtbot.waitUntil(lambda: aba.tabela.status(0) == "copiado", timeout=5000)
    assert (espaco.raiz / "NVC1/A/Arquivos/NVC1A-DE-1.pdf").exists()


def test_relatorios_ausente_e_presente(qtbot, config_temp, espaco):
    aba = AbaRelatorios(config_temp)
    qtbot.addWidget(aba)
    aba.seletor.definir_pasta(espaco.raiz)
    aba.combo_tipo.setCurrentIndex(0)
    aba.botao_atualizar.click()
    assert aba.rotulo_situacao.text() == "O relatório ainda não foi gerado."
    Relatorio().gravar(espaco.raiz / "arquivos_apagados.csv", ["a", "b"], [["1", "2"]])
    aba.combo_tipo.setCurrentIndex(1)
    aba.botao_atualizar.click()
    assert aba.tabela.rowCount() == 1 and aba.tabela.columnCount() == 2
