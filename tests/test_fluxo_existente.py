"""Fluxo de entrega adicionando PDFs a uma pasta já existente."""

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import criar
from falsos import converter_falha, converter_ok
from gerenciador.nucleo.erros import ErroValidacao
from gerenciador.nucleo.fluxo import ParametrosFluxo, executar_fluxo, planejar_fluxo
from gerenciador.nucleo.relatorios import Relatorio, ler_csv

TIPOS = frozenset({"DE", "LI", "LD", "PR", "FO"})


@pytest.fixture
def pasta(tmp_path):
    caminho = tmp_path / "Entrega"
    caminho.mkdir()
    return caminho


class Lixeira:
    def __init__(self, destino: Path):
        self.destino = destino
        self.enviados: list[str] = []

    def __call__(self, caminho: str) -> None:
        self.destino.mkdir(exist_ok=True)
        shutil.move(caminho, self.destino / f"{len(self.enviados)}_{Path(caminho).name}")
        self.enviados.append(caminho)


@pytest.fixture
def lixeira(tmp_path):
    return Lixeira(tmp_path / "lixeira")


def existente(base, pasta, tipos=TIPOS, **kw):
    return planejar_fluxo(ParametrosFluxo(base, "", tipos, pasta_destino=pasta,
                                          pasta_existente=True, **kw))


def executar(plano, funcao=converter_ok, relatorio=None, **kw):
    return executar_fluxo(plano, relatorio or Relatorio(), funcao_conversao=funcao,
                          criar_executor=ThreadPoolExecutor, **kw)


def texto(caminho):
    return caminho.read_text(encoding="utf-8")


def test_existente_mantem_pdf_que_ja_existe(base, pasta):
    criar(pasta, "a/X-DE-001.pdf")
    plano = existente(base, pasta)
    assert plano.destino_raiz == pasta.resolve()
    assert [i.final.name for i in plano.mantidos] == ["X-DE-001.pdf"]
    assert plano.mantidos[0].motivo == "já existe na pasta (mantido)"
    resumo = executar(plano)
    assert texto(pasta / "a/X-DE-001.pdf") == "a/X-DE-001.pdf"
    assert resumo.mantidos == 1 and resumo.copiados == 1
    assert (pasta / "a/X-LI-002.pdf").exists() and (pasta / "c/X-FO-005.pdf").exists()
    assert (pasta / "c/X-PR-006.PDF").exists()


def test_existente_converte_ja_existente_e_mantido(base, pasta):
    criar(pasta, "a/X-LI-002.pdf")
    plano = existente(base, pasta)
    assert "X-LI-002.docx" in [i.origem.name for i in plano.mantidos]
    assert all(t.destino.name != "X-LI-002.pdf" for t in plano.trabalhos)
    executar(plano)
    assert texto(pasta / "a/X-LI-002.pdf") == "a/X-LI-002.pdf"


def test_existente_substituir_manda_antigo_para_lixeira(base, pasta, lixeira):
    criar(pasta, "a/X-DE-001.pdf", "a/X-LI-002.pdf")
    plano = existente(base, pasta, substituir_existentes=True)
    assert len(plano.a_substituir) == 2 and plano.mantidos == []
    assert all(i.motivo == "substitui o PDF existente (antigo vai para a Lixeira)"
               for i in plano.a_substituir)
    resumo = executar(plano, lixeira=lixeira)
    assert sorted(Path(p).name for p in lixeira.enviados) == ["X-DE-001.pdf", "X-LI-002.pdf"]
    assert texto(pasta / "a/X-DE-001.pdf") == "obra/a/X-DE-001.pdf"  # veio da base
    assert (pasta / "a/X-LI-002.pdf").read_bytes() == b"%PDF-fake"
    assert resumo.substituidos == 2 and resumo.erros == []


def test_existente_docx_do_usuario_intacto(base, pasta):
    criar(pasta, "a/X-LI-002.docx")
    resumo = executar(existente(base, pasta))
    assert texto(pasta / "a/X-LI-002.docx") == "a/X-LI-002.docx"
    assert (pasta / "a/X-LI-002.pdf").exists() and resumo.erros == []


def test_existente_preserva_pasta_vazia_do_usuario(base, pasta):
    criar(pasta, "minha/vazia/")
    executar(existente(base, pasta))
    assert (pasta / "minha/vazia").is_dir()
    assert not any(p.name.startswith(".pdf_entrega_") for p in pasta.iterdir())


def test_existente_remove_pastas_criadas_vazias(base, pasta):
    executar(existente(base, pasta, tipos=frozenset({"DE"})))
    assert sorted(p.name for p in pasta.iterdir() if p.is_dir()) == ["a"]


def test_existente_contendo_a_base_recusado(base):
    with pytest.raises(ErroValidacao):
        existente(base, base.parent)


@pytest.mark.parametrize("onde", ["base", "dentro"])
def test_existente_base_ou_dentro_recusado(base, onde):
    with pytest.raises(ErroValidacao):
        existente(base, base if onde == "base" else base / "a")


def test_existente_sem_pasta_recusado(base):
    with pytest.raises(ErroValidacao):
        planejar_fluxo(ParametrosFluxo(base, "", TIPOS, pasta_existente=True))


def test_existente_nome_ignorado(base, pasta):
    plano = planejar_fluxo(ParametrosFluxo(base, "CON", TIPOS, pasta_destino=pasta,
                                           pasta_existente=True))
    assert plano.destino_raiz == pasta.resolve()


def test_existente_segunda_execucao_nada_muda(base, pasta):
    executar(existente(base, pasta))
    antes = {p: p.stat().st_mtime_ns for p in pasta.rglob("*.pdf")}
    plano = existente(base, pasta)
    assert plano.a_copiar == [] and plano.a_converter == [] and len(plano.mantidos) == 4
    resumo = executar(plano)
    assert {p: p.stat().st_mtime_ns for p in pasta.rglob("*.pdf")} == antes
    assert resumo.mantidos == 4 and resumo.erros == []


def test_existente_falha_da_lixeira_preserva_antigo(base, pasta):
    criar(pasta, "a/X-DE-001.pdf")

    def quebrada(caminho):
        raise OSError("lixeira indisponível")

    resumo = executar(existente(base, pasta, substituir_existentes=True), lixeira=quebrada)
    assert texto(pasta / "a/X-DE-001.pdf") == "a/X-DE-001.pdf"
    assert resumo.erros[0][0] == "a/X-DE-001.pdf" and resumo.substituidos == 0


def test_existente_relatorio_convertidos_acumula(base, pasta):
    executar(existente(base, pasta, tipos=frozenset({"LI"})))
    executar(existente(base, pasta, tipos=frozenset({"FO"})))
    _, linhas = ler_csv(pasta / "arquivos_convertidos.csv")
    assert [linha[1] for linha in linhas] == ["a/X-LI-002.docx", "c/X-FO-005.XLSX"]


def test_falha_conversao_existente_nao_sobrescreve_docx(base, pasta):
    criar(pasta, "a/X-LI-002.docx")
    resumo = executar(existente(base, pasta), funcao=converter_falha)
    assert texto(pasta / "a/X-LI-002.docx") == "a/X-LI-002.docx"
    assert any(arquivo == "a/X-LI-002.docx" for arquivo, _ in resumo.erros)
    assert not any(p.name.startswith(".pdf_entrega_") for p in pasta.iterdir())


def test_falha_conversao_existente_sem_conflito_leva_docx(base, pasta):
    executar(existente(base, pasta), funcao=converter_falha)
    assert (pasta / "a/X-LI-002.docx").exists()  # como na pasta nova: não se perde


def test_falha_ao_devolver_original_nao_derruba(base, pasta):
    # Na pasta existente há um ARQUIVO com o nome da subpasta "a": devolver o Word que
    # falhou para a/X-LI-002.docx é impossível. O fluxo deve registrar e seguir.
    (pasta / "a").write_text("sou um arquivo", encoding="utf-8")
    plano = existente(base, pasta)
    resumo = executar(plano, funcao=converter_falha)
    assert any(arquivo == "a/X-LI-002.docx" for arquivo, _ in resumo.erros)
    assert (pasta / "c/X-PR-006.PDF").exists()
    assert (pasta / "arquivos_ignorados.csv").exists()
    assert not any(p.name.startswith(".pdf_entrega_") for p in pasta.iterdir())
    assert (pasta / "a").read_text(encoding="utf-8") == "sou um arquivo"
