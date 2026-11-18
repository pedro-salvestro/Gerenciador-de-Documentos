import threading
import time

from gerenciador.gui.janela_principal import JanelaPrincipal
from gerenciador.gui.tabela_itens import TabelaItens
from gerenciador.gui.trabalhador import executar_em_segundo_plano
from gerenciador.nucleo.erros import ErroValidacao


def test_janela_tem_abas_na_ordem(qtbot, config_temp):
    j = JanelaPrincipal(config_temp)
    qtbot.addWidget(j)
    assert [j.abas.tabText(i) for i in range(j.abas.count())] == [
        "Fluxo de entrega", "Converter", "Limpeza", "Copiar por código", "Relatórios"]


def test_opcao_relatorios_persiste(qtbot, config_temp):
    j = JanelaPrincipal(config_temp)
    qtbot.addWidget(j)
    assert j.relatorio().ativo is True
    j.caixa_relatorios.setChecked(False)
    assert config_temp.gerar_relatorios is False
    assert j.relatorio().ativo is False


def test_configuracoes_valor(config_temp):
    assert config_temp.valor("x/y", "padrao") == "padrao"
    config_temp.definir("x/y", "z")
    assert config_temp.valor("x/y", "padrao") == "z"


def test_trabalhador_conclui(qtbot):
    resultados = []
    executar_em_segundo_plano(None, lambda ctx: 42, ao_concluir=resultados.append)
    qtbot.waitUntil(lambda: resultados == [42], timeout=5000)


def test_trabalhador_falha_validacao(qtbot):
    falhas = []

    def tarefa(ctx):
        raise ErroValidacao("x", ["a"])

    executar_em_segundo_plano(None, tarefa, ao_falhar=lambda m, i: falhas.append((m, i)))
    qtbot.waitUntil(lambda: falhas == [("x", ["a"])], timeout=5000)


def test_trabalhador_progresso_e_cancelar(qtbot):
    progresso, resultados = [], []
    iniciou = threading.Event()

    def tarefa(ctx):
        ctx.progresso("Etapa", 1, 2)
        iniciou.set()
        while not ctx.cancelado():
            time.sleep(0.01)
        return "parou"

    t = executar_em_segundo_plano(
        None, tarefa, ao_concluir=resultados.append,
        ao_progresso=lambda e, a, tot: progresso.append((e, a, tot)))
    assert iniciou.wait(5)
    t.cancelar()
    qtbot.waitUntil(lambda: resultados == ["parou"], timeout=5000)
    assert progresso == [("Etapa", 1, 2)]


def test_tabela_marcados(qtbot):
    tabela = TabelaItens(["A", "B"], marcavel=True)
    qtbot.addWidget(tabela)
    tabela.definir_linhas([["1", "x"], ["2", "y"]], ["d1", "d2"])
    assert tabela.marcados() == []
    tabela.marcar_todos(True)
    assert tabela.marcados() == ["d1", "d2"]
    tabela.definir_status(0, "ok")
    tabela.filtrar("y")
    assert tabela.model().rowCount() == 1


def test_trabalhador_erro_inesperado(qtbot):
    falhas = []

    def tarefa(ctx):
        raise RuntimeError("quebrou")

    executar_em_segundo_plano(None, tarefa, ao_falhar=lambda m, i: falhas.append(m))
    qtbot.waitUntil(lambda: falhas == ["quebrou"], timeout=5000)
