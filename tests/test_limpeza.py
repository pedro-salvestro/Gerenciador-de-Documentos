import pytest

from conftest import criar
from gerenciador.nucleo.erros import ErroValidacao
from gerenciador.nucleo.limpeza import (
    ItemLimpeza, candidatos, enviar_lixeira, extensoes_disponiveis, selecionar_cad,
    selecionar_et_dt_md, selecionar_manter_arquivos, selecionar_manter_pastas,
    selecionar_pastas_vazias, selecionar_por_extensoes, selecionar_todos_nao_pdf,
    selecionar_word_excel,
)
from gerenciador.nucleo.relatorios import Relatorio, ler_csv

ARVORE = ("p/NVC1A-DE-001.docx", "p/NVC1A-ET-002.pdf", "p/NVC1A-MD-003.xlsx",
          "p/modelo.dwg", "p/x.zip", "q/vazia/", "r/s/t.txt", "a.pdf")


@pytest.fixture
def arvore(espaco):
    criar(espaco.raiz, *ARVORE)
    return espaco


def rel(espaco, itens):
    return [espaco.relativo(i.caminho) for i in itens]


def test_candidatos(arvore):
    assert rel(arvore, candidatos(arvore)) == [
        "p/modelo.dwg", "p/NVC1A-DE-001.docx", "p/NVC1A-MD-003.xlsx", "p/x.zip", "r/s/t.txt"]


def test_modo1_todos_nao_pdf_inclui_relatorio(arvore):
    criar(arvore.raiz, "arquivos_apagados.csv")
    itens = selecionar_todos_nao_pdf(arvore)
    assert rel(arvore, itens)[-1] == "arquivos_apagados.csv"
    assert itens[-1].tipo == "relatório CSV"
    assert not any(i.caminho.suffix == ".pdf" for i in itens)


def test_modo2_word_excel_exclui_codigos_et_dt_md(arvore):
    assert rel(arvore, selecionar_word_excel(arvore)) == ["p/NVC1A-DE-001.docx"]


def test_modo3_por_extensao(arvore):
    assert extensoes_disponiveis(arvore) == [".docx", ".dwg", ".txt", ".xlsx", ".zip"]
    assert rel(arvore, selecionar_por_extensoes(arvore, {".zip"})) == ["p/x.zip"]


def test_modo5_pastas_vazias(arvore):
    itens = selecionar_pastas_vazias(arvore)
    assert rel(arvore, itens) == ["q/vazia"] and itens[0].tipo == "pasta vazia"


def test_modo6_cad(arvore):
    assert rel(arvore, selecionar_cad(arvore)) == ["p/modelo.dwg"]


def test_modo7_manter_arquivos_aceita_nome_sem_extensao(arvore):
    itens = selecionar_manter_arquivos(arvore, "modelo; p/x.zip")
    assert rel(arvore, itens) == ["p/NVC1A-DE-001.docx", "p/NVC1A-MD-003.xlsx", "r/s/t.txt"]
    assert itens[0].tipo == "arquivo fora da lista de manutenção"


def test_modo7_nome_nao_encontrado(arvore):
    with pytest.raises(ErroValidacao) as e:
        selecionar_manter_arquivos(arvore, "inexistente.docx")
    assert e.value.itens == ["inexistente.docx"]


def test_modo7_lista_vazia(arvore):
    with pytest.raises(ErroValidacao):
        selecionar_manter_arquivos(arvore, " ; ")


def test_modo8_manter_pastas_preserva_pais_e_filhos(arvore):
    apagar, mantidas = selecionar_manter_pastas(arvore, "r/s")
    assert rel(arvore, apagar) == ["p", "q"]
    assert [arvore.relativo(p) for p in mantidas] == ["r/s"]


def test_modo8_nao_encontrada(arvore):
    with pytest.raises(ErroValidacao) as e:
        selecionar_manter_pastas(arvore, "zzz")
    assert e.value.itens == ["zzz"]


def test_modo9_inclui_pdfs(arvore):
    itens = selecionar_et_dt_md(arvore)
    assert rel(arvore, itens) == ["p/NVC1A-MD-003.xlsx", "p/NVC1A-ET-002.pdf"]
    assert [i.tipo for i in itens] == ["documento MD", "documento ET"]


def test_enviar_lixeira_usa_duble_e_grava_csv(arvore):
    enviados = []
    itens = selecionar_cad(arvore)
    r = enviar_lixeira(arvore, itens, Relatorio(), lixeira=enviados.append)
    assert enviados == [str(itens[0].caminho.resolve())]
    assert r[0].status == "enviado à Lixeira"
    _, linhas = ler_csv(arvore.raiz / "arquivos_apagados.csv")
    assert linhas[0][1:4] == ["p/modelo.dwg", "arquivo STEP/DWG", "enviado à Lixeira"]


def test_enviar_lixeira_pasta_que_deixou_de_ser_vazia(arvore):
    itens = selecionar_pastas_vazias(arvore)
    criar(arvore.raiz, "q/vazia/novo.txt")
    enviados = []
    r = enviar_lixeira(arvore, itens, Relatorio(), lixeira=enviados.append)
    assert r[0].status == "erro" and enviados == []


def test_enviar_lixeira_caminho_fora_da_raiz(arvore, tmp_path_factory):
    fora = tmp_path_factory.mktemp("fora") / "x.txt"
    fora.write_text("x")
    enviados = []
    r = enviar_lixeira(arvore, [ItemLimpeza(fora, "outro arquivo")], Relatorio(False),
                       lixeira=enviados.append)
    assert r[0].status == "erro" and enviados == []


def test_enviar_lixeira_relatorio_inativo(arvore):
    enviar_lixeira(arvore, selecionar_cad(arvore), Relatorio(False), lixeira=lambda c: None)
    assert not (arvore.raiz / "arquivos_apagados.csv").exists()


def test_enviar_lixeira_nao_recria_csv_apagado(arvore):
    criar(arvore.raiz, "arquivos_apagados.csv")
    itens = [i for i in selecionar_todos_nao_pdf(arvore) if i.tipo == "relatório CSV"]
    enviar_lixeira(arvore, itens, Relatorio(), lixeira=lambda c: __import__("os").remove(c))
    assert not (arvore.raiz / "arquivos_apagados.csv").exists()
