import pytest
from PySide6.QtWidgets import QMessageBox

from conftest import criar
from gerenciador.gui.aba_limpeza import MODOS, AbaLimpeza
from gerenciador.nucleo.relatorios import Relatorio
from test_limpeza import ARVORE


@pytest.fixture
def enviados():
    return []


@pytest.fixture
def aba(qtbot, config_temp, espaco, enviados):
    criar(espaco.raiz, *ARVORE)
    widget = AbaLimpeza(config_temp, lambda: Relatorio(), lixeira=enviados.append)
    qtbot.addWidget(widget)
    widget.seletor.definir_pasta(espaco.raiz)
    return widget


def responder(monkeypatch, botao):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: botao)


def test_modos_na_ordem(aba):
    assert [aba.lista_modos.item(i).text() for i in range(aba.lista_modos.count())] == MODOS
    assert len(MODOS) == 9


def test_modo6_previa_e_envio(qtbot, aba, enviados, monkeypatch):
    responder(monkeypatch, QMessageBox.StandardButton.Yes)
    aba.lista_modos.setCurrentRow(5)
    qtbot.waitUntil(lambda: aba.tabela.quantidade() == 1, timeout=5000)
    assert aba.botao_enviar.text() == "Enviar 1 itens à Lixeira"
    aba.botao_enviar.click()
    qtbot.waitUntil(lambda: aba.tabela.status(0) == "enviado à Lixeira", timeout=5000)
    assert len(enviados) == 1 and enviados[0].endswith("modelo.dwg")


def test_desmarcar_item_nao_envia(qtbot, aba, enviados, monkeypatch):
    responder(monkeypatch, QMessageBox.StandardButton.Yes)
    aba.lista_modos.setCurrentRow(0)
    qtbot.waitUntil(lambda: aba.tabela.quantidade() == 5, timeout=5000)
    aba.tabela.marcar_todos(False)
    assert not aba.botao_enviar.isEnabled()


def test_modo4_individual_comeca_desmarcado(qtbot, aba):
    aba.lista_modos.setCurrentRow(3)
    qtbot.waitUntil(lambda: aba.tabela.quantidade() == 5, timeout=5000)
    assert aba.tabela.marcados() == []


def test_modo7_nao_encontrado_bloqueia(qtbot, aba):
    aba.lista_modos.setCurrentRow(6)
    aba.campo_lista.setPlainText("inexistente.docx")
    aba.botao_gerar.click()
    qtbot.waitUntil(lambda: "inexistente.docx" in aba.rotulo_erro.text(), timeout=5000)
    assert not aba.botao_enviar.isEnabled()


def test_modo8_mostra_mantidas_sem_caixa(qtbot, aba):
    aba.lista_modos.setCurrentRow(7)
    aba.campo_lista.setPlainText("r/s")
    aba.botao_gerar.click()
    qtbot.waitUntil(lambda: aba.tabela.quantidade() == 3, timeout=5000)
    assert len(aba.tabela.marcados()) == 2


def test_cancelar_confirmacao_nao_envia(qtbot, aba, enviados, monkeypatch):
    responder(monkeypatch, QMessageBox.StandardButton.No)
    aba.lista_modos.setCurrentRow(5)
    qtbot.waitUntil(lambda: aba.tabela.quantidade() == 1, timeout=5000)
    aba.botao_enviar.click()
    assert enviados == []
