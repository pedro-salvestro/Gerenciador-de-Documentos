from concurrent.futures import ThreadPoolExecutor

import pytest
from PySide6.QtWidgets import QMessageBox

from falsos import converter_ok
from gerenciador.gui.aba_fluxo import AbaFluxo
from gerenciador.nucleo.relatorios import Relatorio


@pytest.fixture
def aba(qtbot, config_temp):
    widget = AbaFluxo(config_temp, lambda: Relatorio(), funcao_conversao=converter_ok,
                      criar_executor=ThreadPoolExecutor)
    qtbot.addWidget(widget)
    return widget


def preparar(aba, base, nome="Entrega"):
    aba.seletor_base.definir_pasta(base)
    aba.campo_nome.setText(nome)


def analisar(qtbot, aba):
    aba.botao_analisar.click()
    qtbot.waitUntil(lambda: aba.botao_executar.isEnabled(), timeout=5000)


def test_executar_desabilitado_ate_analisar(aba, base):
    preparar(aba, base)
    assert not aba.botao_executar.isEnabled()


def test_tipos_padrao_e_destino(aba, base):
    assert aba.campo_tipos.text() == "DE, LI, LD, PR, FO"
    preparar(aba, base)
    assert str(base.parent / "Entrega") in aba.rotulo_destino.text()


def test_analisar_preenche_resumo(qtbot, aba, base):
    preparar(aba, base)
    analisar(qtbot, aba)
    texto = aba.rotulo_resumo.text()
    assert "2 PDFs a copiar" in texto
    assert "2 Word/Excel a converter" in texto
    assert "4 fora da entrega" in texto
    assert aba.tabela.quantidade() == 8


def test_mudar_parametro_invalida_analise(qtbot, aba, base):
    preparar(aba, base)
    analisar(qtbot, aba)
    aba.campo_tipos.setText("DE")
    assert not aba.botao_executar.isEnabled()


def test_executar_fluxo_completo(qtbot, aba, base, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    preparar(aba, base)
    analisar(qtbot, aba)
    aba.botao_executar.click()
    qtbot.waitUntil(lambda: aba.botao_abrir_pasta.isEnabled(), timeout=10000)
    destino = base.parent / "Entrega"
    assert (destino / "a" / "X-LI-002.pdf").exists()
    assert not (destino / "a" / "X-LI-002.docx").exists()
    assert "Concluído" in aba.rotulo_resumo.text()
    assert aba.campo_nome.isEnabled()


def test_confirmacao_negada_nao_cria_pasta(qtbot, aba, base, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    preparar(aba, base)
    analisar(qtbot, aba)
    aba.botao_executar.click()
    assert not (base.parent / "Entrega").exists()


def test_nome_invalido_mostra_aviso(qtbot, aba, base, monkeypatch):
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda pai, titulo, texto, *a, **k: avisos.append(texto))
    preparar(aba, base, nome="CON")
    aba.botao_analisar.click()
    qtbot.waitUntil(lambda: bool(avisos), timeout=5000)
    assert "Nome de pasta inválido" in avisos[0]
    assert not aba.botao_executar.isEnabled()


def test_campos_lembrados(qtbot, config_temp, base):
    primeira = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(primeira)
    preparar(primeira, base, "Minha entrega")
    primeira.campo_tipos.setText("DE, PR")
    segunda = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(segunda)
    assert segunda.campo_nome.text() == "Minha entrega"
    assert segunda.campo_tipos.text() == "DE, PR"
    assert segunda.seletor_base.pasta == base
