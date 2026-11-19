from concurrent.futures import ThreadPoolExecutor

import pytest
from PySide6.QtWidgets import QMessageBox

from conftest import criar, relativos
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


# --- Salvar em e lista de NVCs/arquivos -----------------------------------------------

def sim_capturando(monkeypatch):
    textos = []

    def question(pai, titulo, texto, *a, **k):
        textos.append(texto)
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, "question", question)
    return textos


def test_salvar_em_outra_pasta(qtbot, aba, base, tmp_path, monkeypatch):
    sim_capturando(monkeypatch)
    saida = tmp_path / "saida"
    saida.mkdir()
    preparar(aba, base)
    aba.seletor_destino.definir_pasta(saida)
    assert str(saida / "Entrega") in aba.rotulo_destino.text()
    analisar(qtbot, aba)
    aba.botao_executar.click()
    qtbot.waitUntil(lambda: aba.botao_abrir_pasta.isEnabled(), timeout=10000)
    assert (saida / "Entrega" / "a" / "X-LI-002.pdf").exists()
    assert not (base.parent / "Entrega").exists()


def test_selecao_com_problema_avisa(qtbot, aba, tmp_path, monkeypatch):
    criar(tmp_path, "obra/a/NVC00410A-DE-001.pdf", "obra/a/NVC00411A-DE-001.pdf")
    base = tmp_path / "obra"
    textos = sim_capturando(monkeypatch)
    preparar(aba, base)
    aba.campo_selecao.setPlainText("NVC00410A\nNVC09999")
    analisar(qtbot, aba)
    assert ("Itens da lista com problema: NVC09999 (não encontrado na pasta base)"
            in aba.rotulo_resumo.text())
    aba.botao_executar.click()
    qtbot.waitUntil(lambda: aba.botao_abrir_pasta.isEnabled(), timeout=10000)
    assert textos[0].startswith("Estes itens da lista não vão entrar:")
    assert "NVC09999 — não encontrado na pasta base" in textos[0]
    assert relativos(tmp_path / "Entrega") == ["a/NVC00410A-DE-001.pdf",
                                               "arquivos_ignorados.csv"]


def test_selecao_sem_problema_confirmacao_normal(qtbot, aba, base, monkeypatch):
    textos = sim_capturando(monkeypatch)
    preparar(aba, base)
    analisar(qtbot, aba)
    aba.botao_executar.click()
    qtbot.waitUntil(lambda: aba.botao_abrir_pasta.isEnabled(), timeout=10000)
    assert textos[0].startswith("Criar a pasta:")


def test_mudar_selecao_invalida_analise(qtbot, aba, base):
    preparar(aba, base)
    analisar(qtbot, aba)
    aba.campo_selecao.setPlainText("NVC1")
    assert not aba.botao_executar.isEnabled()


def test_campos_novos_lembrados(qtbot, config_temp, base, tmp_path):
    saida = tmp_path / "saida"
    saida.mkdir()
    primeira = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(primeira)
    primeira.seletor_destino.definir_pasta(saida)
    primeira.campo_selecao.setPlainText("NVC00410A, NVC00411")
    segunda = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(segunda)
    assert segunda.seletor_destino.pasta == saida
    assert segunda.campo_selecao.toPlainText() == "NVC00410A, NVC00411"


# --- Adicionar a uma pasta existente ---------------------------------------------------

def preparar_existente(aba, base, pasta):
    aba.seletor_base.definir_pasta(base)
    aba.opcao_existente.setChecked(True)
    aba.seletor_destino.definir_pasta(pasta)


@pytest.fixture
def entrega(tmp_path):
    pasta = tmp_path / "Entrega existente"
    criar(pasta, "a/X-DE-001.pdf")
    return pasta


def test_modo_existente_desativa_nome_e_mostra_substituir(aba):
    assert aba.opcao_nova.isChecked() and not aba.caixa_substituir.isVisibleTo(aba)
    aba.opcao_existente.setChecked(True)
    assert not aba.campo_nome.isEnabled()
    assert aba.caixa_substituir.isVisibleTo(aba) and not aba.caixa_substituir.isChecked()
    assert aba.caixa_substituir.text() == (
        "Substituir PDFs que já existem (os antigos vão para a Lixeira)")
    aba.opcao_nova.setChecked(True)
    assert aba.campo_nome.isEnabled() and not aba.caixa_substituir.isVisibleTo(aba)


def test_existente_rotulo_destino(aba, base, entrega):
    preparar_existente(aba, base, entrega)
    assert aba.rotulo_destino.text() == f"→ os PDFs serão adicionados em: {entrega}"


def test_existente_analise_mostra_ja_existem(qtbot, aba, base, entrega):
    preparar_existente(aba, base, entrega)
    analisar(qtbot, aba)
    texto = aba.rotulo_resumo.text()
    assert "1 já existem (mantidos)" in texto
    assert "Pasta existente:" in texto
    acoes = [aba.tabela.model().index(i, 1).data() for i in range(aba.tabela.quantidade())]
    assert "Já existe (mantido)" in acoes


def test_existente_executa_sem_tocar_no_existente(qtbot, aba, base, entrega, monkeypatch):
    textos = sim_capturando(monkeypatch)
    preparar_existente(aba, base, entrega)
    analisar(qtbot, aba)
    aba.botao_executar.click()
    qtbot.waitUntil(lambda: aba.botao_abrir_pasta.isEnabled(), timeout=10000)
    assert textos[0].startswith("Adicionar à pasta:")
    assert (entrega / "a/X-DE-001.pdf").read_text(encoding="utf-8") == "a/X-DE-001.pdf"
    assert (entrega / "a/X-LI-002.pdf").exists()
    assert "1 mantidos" in aba.rotulo_resumo.text()


def test_substituir_usa_lixeira(qtbot, config_temp, base, entrega, monkeypatch):
    import os
    enviados = []

    def lixeira(caminho):
        enviados.append(caminho)
        os.remove(caminho)

    aba = AbaFluxo(config_temp, lambda: Relatorio(), funcao_conversao=converter_ok,
                   criar_executor=ThreadPoolExecutor, lixeira=lixeira)
    qtbot.addWidget(aba)
    sim_capturando(monkeypatch)
    preparar_existente(aba, base, entrega)
    aba.caixa_substituir.setChecked(True)
    analisar(qtbot, aba)
    assert "1 PDFs serão substituídos" in aba.rotulo_resumo.text()
    aba.botao_executar.click()
    qtbot.waitUntil(lambda: aba.botao_abrir_pasta.isEnabled(), timeout=10000)
    assert [os.path.basename(c) for c in enviados] == ["X-DE-001.pdf"]
    assert "1 substituídos" in aba.rotulo_resumo.text()


def test_mudar_modo_invalida_analise(qtbot, aba, base, entrega):
    preparar_existente(aba, base, entrega)
    analisar(qtbot, aba)
    aba.caixa_substituir.setChecked(True)
    assert not aba.botao_executar.isEnabled()


def test_modo_lembrado_e_substituir_nao(qtbot, config_temp):
    primeira = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(primeira)
    primeira.opcao_existente.setChecked(True)
    primeira.caixa_substituir.setChecked(True)
    segunda = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(segunda)
    assert segunda.opcao_existente.isChecked()
    assert not segunda.caixa_substituir.isChecked()


def test_salvar_em_separado_por_modo(qtbot, config_temp, tmp_path):
    pai, entrega = tmp_path / "Entregas", tmp_path / "Entregas" / "Obra X"
    entrega.mkdir(parents=True)
    aba = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(aba)
    aba.seletor_destino.definir_pasta(pai)
    aba.opcao_existente.setChecked(True)
    assert aba.seletor_destino.campo.text() == ""  # não herda a pasta-pai do modo novo
    aba.seletor_destino.definir_pasta(entrega)
    aba.opcao_nova.setChecked(True)
    assert aba.seletor_destino.campo.text() == str(pai)
    aba.opcao_existente.setChecked(True)
    assert aba.seletor_destino.campo.text() == str(entrega)
    outra = AbaFluxo(config_temp, lambda: Relatorio())
    qtbot.addWidget(outra)
    assert outra.opcao_existente.isChecked()
    assert outra.seletor_destino.campo.text() == str(entrega)
