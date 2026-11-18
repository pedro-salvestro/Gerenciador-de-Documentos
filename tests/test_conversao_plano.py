from concurrent.futures import ThreadPoolExecutor

from conftest import criar
from falsos import converter_ok
from gerenciador.nucleo.conversao import (
    documentos_convertiveis, executar_conversao, gravar_relatorio_conversao,
    planejar_conversao, processos_padrao,
)
from gerenciador.nucleo.relatorios import Relatorio, ler_csv


def test_planejar_nomes_duplicados(tmp_path):
    t = planejar_conversao([tmp_path / "a.docx", tmp_path / "a.xlsx", tmp_path / "b.doc"])
    assert [x.destino.name for x in t] == ["a.docx.pdf", "a.xlsx.pdf", "b.pdf"]


def test_documentos_convertiveis(espaco):
    criar(espaco.raiz, "a.docx", "b.pdf", "c/d.XLSX", "e.txt")
    assert [espaco.relativo(p) for p in documentos_convertiveis(espaco)] == ["a.docx", "c/d.XLSX"]


def test_processos_padrao():
    assert processos_padrao(1) == 1
    assert 1 <= processos_padrao(10) <= 2
    assert processos_padrao(0) == 1


def test_executar_ordem_e_status(tmp_path):
    t = planejar_conversao([tmp_path / "a.docx", tmp_path / "b.docx"])
    r = executar_conversao(t, 2, funcao=converter_ok, criar_executor=ThreadPoolExecutor)
    assert [x.status for x in r] == ["convertido", "convertido"]
    assert [x.trabalho for x in r] == t
    assert t[0].destino.read_bytes() == b"%PDF-fake"


def test_executar_cancelado_marca_pendentes(tmp_path):
    t = planejar_conversao([tmp_path / f"{i}.docx" for i in range(5)])
    feitos = []
    r = executar_conversao(
        t, 1, ao_concluir=lambda res, n, tot: feitos.append(n),
        cancelado=lambda: len(feitos) >= 1,
        funcao=converter_ok, criar_executor=ThreadPoolExecutor,
    )
    assert r[0].status == "convertido"
    assert "cancelado" in {x.status for x in r[1:]}


def test_relatorio_conversao(tmp_path):
    t = planejar_conversao([tmp_path / "a.docx"])
    r = executar_conversao(t, 1, funcao=converter_ok, criar_executor=ThreadPoolExecutor)
    caminho = gravar_relatorio_conversao(r, tmp_path, Relatorio(), tmp_path / "c.csv")
    cabecalho, linhas = ler_csv(caminho)
    assert cabecalho[1:] == ["arquivo_origem", "arquivo_pdf", "resultado", "detalhe"]
    assert linhas[0][1:4] == ["a.docx", "a.pdf", "convertido"]


def test_relatorio_conversao_inativo(tmp_path):
    t = planejar_conversao([tmp_path / "a.docx"])
    r = executar_conversao(t, 1, funcao=converter_ok, criar_executor=ThreadPoolExecutor)
    assert gravar_relatorio_conversao(r, tmp_path, Relatorio(False), tmp_path / "c.csv") is None
    assert not (tmp_path / "c.csv").exists()
