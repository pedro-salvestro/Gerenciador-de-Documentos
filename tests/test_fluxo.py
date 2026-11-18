import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import criar, relativos
from falsos import converter_falha, converter_ok
from gerenciador.nucleo import fluxo as modulo_fluxo
from gerenciador.nucleo.erros import ErroValidacao
from gerenciador.nucleo.fluxo import (
    ParametrosFluxo, executar_fluxo, planejar_fluxo, separar_selecao, separar_tipos,
)
from gerenciador.nucleo.relatorios import Relatorio, ler_csv

TIPOS = frozenset({"DE", "LI", "LD", "PR", "FO"})


def plano_de(base, nome="Entrega", **kw):
    return planejar_fluxo(ParametrosFluxo(base=base, nome_destino=nome, tipos=TIPOS, **kw))


def executar(plano, funcao=converter_ok, relatorio=None, **kw):
    return executar_fluxo(plano, relatorio or Relatorio(), funcao_conversao=funcao,
                          criar_executor=ThreadPoolExecutor, **kw)


def test_separar_tipos_baguncado():
    assert separar_tipos("de; li ,pr\nfo") == {"DE", "LI", "PR", "FO"}


@pytest.mark.parametrize("texto", ["", " ; ", "D E X", "DEX", "1A"])
def test_separar_tipos_invalido(texto):
    with pytest.raises(ErroValidacao):
        separar_tipos(texto)


def test_classificacao(base):
    plano = plano_de(base)
    assert plano.destino_raiz == base.parent / "Entrega"
    acoes = {i.origem.relative_to(base).as_posix(): (i.acao, i.motivo) for i in plano.itens}
    assert acoes == {
        "a/X-DE-001.pdf": ("copiar", ""),
        "a/X-LI-002.docx": ("converter", ""),
        "a/X-ET-003.pdf": ("ignorar", "tipo ET não permitido"),
        "a/X-DE-004.dwg": ("ignorar", "formato .dwg não aceito"),
        "b/foto.jpg": ("ignorar", "sem código de tipo"),
        "b/pacote.zip": ("ignorar", "sem código de tipo"),
        "c/X-FO-005.XLSX": ("converter", ""),
        "c/X-PR-006.PDF": ("copiar", ""),
    }
    assert (len(plano.a_copiar), len(plano.a_converter), len(plano.ignorados)) == (2, 2, 4)
    assert plano.conflitos == []


def test_destino_existente(base):
    (base.parent / "Entrega").mkdir()
    with pytest.raises(ErroValidacao):
        plano_de(base)


@pytest.mark.parametrize("nome", ["obra/x", "CON", "nome."])
def test_nome_invalido(base, nome):
    with pytest.raises(ErroValidacao):
        plano_de(base, nome)


def test_base_inexistente(tmp_path):
    with pytest.raises(ErroValidacao):
        plano_de(tmp_path / "nao_existe")


def test_executar_resultado_final(base):
    plano = plano_de(base)
    resumo = executar(plano)
    assert relativos(plano.destino_raiz) == [
        "a/X-DE-001.pdf", "a/X-LI-002.pdf", "arquivos_convertidos.csv",
        "arquivos_ignorados.csv", "c/X-FO-005.pdf", "c/X-PR-006.PDF"]
    assert not (plano.destino_raiz / "b").exists()
    assert (resumo.copiados, resumo.convertidos, resumo.ignorados) == (2, 2, 4)
    assert resumo.erros == [] and resumo.cancelado is False
    _, ignorados = ler_csv(plano.destino_raiz / "arquivos_ignorados.csv")
    assert ["b/pacote.zip", "sem código de tipo"] in ignorados


def test_base_intacta(base):
    def foto():
        return sorted((p.relative_to(base).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
                      for p in base.rglob("*"))
    antes = foto()
    executar(plano_de(base))
    assert foto() == antes


def test_falha_de_conversao_mantem_original(base):
    plano = plano_de(base)
    resumo = executar(plano, funcao=converter_falha)
    assert (plano.destino_raiz / "a/X-LI-002.docx").exists()
    assert resumo.convertidos == 0
    assert ("a/X-LI-002.docx", "falhou") in resumo.erros


def test_cancelar_mantem_pendentes(base):
    plano = plano_de(base, processos=1)
    eventos = []
    resumo = executar(plano, ao_log=eventos.append,
                      cancelado=lambda: any(e.startswith("OK") for e in eventos))
    assert resumo.cancelado is True
    restantes = relativos(plano.destino_raiz)
    assert "a/X-LI-002.pdf" in restantes and "c/X-FO-005.XLSX" in restantes


def test_erro_ao_copiar_continua(base, monkeypatch):
    original = shutil.copy2

    def copy2(origem, destino, *a, **k):
        if str(origem).endswith("X-DE-001.pdf"):
            raise PermissionError("em uso")
        return original(origem, destino, *a, **k)

    monkeypatch.setattr(modulo_fluxo.shutil, "copy2", copy2)
    plano = plano_de(base)
    resumo = executar(plano)
    assert resumo.copiados == 1
    assert resumo.erros[0][0] == "a/X-DE-001.pdf"
    assert (plano.destino_raiz / "c/X-PR-006.PDF").exists()


def test_relatorios_desligados(base):
    plano = plano_de(base)
    executar(plano, relatorio=Relatorio(False))
    assert not list(plano.destino_raiz.rglob("*.csv"))


def test_conversao_desligada_copia_originais(base):
    plano = plano_de(base, converter=False)
    resumo = executar(plano)
    arquivos = relativos(plano.destino_raiz)
    assert "a/X-LI-002.docx" in arquivos and "c/X-FO-005.XLSX" in arquivos
    assert resumo.copiados == 4 and resumo.convertidos == 0


def test_conflito_detectado(base):
    criar(base, "a/X-LI-002.pdf")
    plano = plano_de(base)
    assert plano.conflitos == [plano.destino_raiz / "a" / "X-LI-002.pdf"]


# --- Pasta de destino escolhida --------------------------------------------------------

def test_destino_em_outra_pasta(base, tmp_path):
    outra = tmp_path / "saida"
    outra.mkdir()
    assert plano_de(base, pasta_destino=outra).destino_raiz == outra.resolve() / "Entrega"


def test_destino_inexistente(base, tmp_path):
    with pytest.raises(ErroValidacao, match="não existe"):
        plano_de(base, pasta_destino=tmp_path / "nada")


def test_destino_dentro_da_base(base):
    with pytest.raises(ErroValidacao, match="dentro da pasta base"):
        plano_de(base, pasta_destino=base / "a")


def test_destino_escolhido_executa(base, tmp_path):
    outra = tmp_path / "saida"
    outra.mkdir()
    plano = plano_de(base, pasta_destino=outra)
    executar(plano)
    assert (outra / "Entrega" / "a" / "X-LI-002.pdf").exists()
    assert not (base.parent / "Entrega").exists()


# --- Seleção por NVC / arquivo ---------------------------------------------------------

ARVORE_NVC = ("obra/a/NVC00410A-DE-001.pdf", "obra/a/NVC00410A-LI-002.docx",
              "obra/a/NVC00410B-DE-001.pdf", "obra/b/NVC00411A-DE-001.pdf",
              "obra/b/NVC00411A-ET-002.pdf", "obra/b/NVC004101A-DE-001.pdf",
              "obra/b/leia-me.txt")


@pytest.fixture
def base_nvc(tmp_path):
    criar(tmp_path, *ARVORE_NVC)
    return tmp_path / "obra"


def entram(plano):
    return sorted(i.origem.relative_to(plano.base).as_posix()
                  for i in plano.itens if i.acao != "ignorar")


def test_separar_selecao():
    assert separar_selecao(' NVC00410A;\n"nvc00410a", NVC00411\r\n') == ("NVC00410A",
                                                                        "NVC00411")
    assert separar_selecao("  ") == ()


@pytest.mark.parametrize("selecao, esperado", [
    (("NVC00410",), ["a/NVC00410A-DE-001.pdf", "a/NVC00410A-LI-002.docx",
                     "a/NVC00410B-DE-001.pdf"]),
    (("NVC00410A",), ["a/NVC00410A-DE-001.pdf", "a/NVC00410A-LI-002.docx"]),
    (("NVC00410A-DE-001",), ["a/NVC00410A-DE-001.pdf"]),
    (("nvc00410a-de-001.PDF",), ["a/NVC00410A-DE-001.pdf"]),
    (("NVC00410B", "NVC00411A-DE-001"), ["a/NVC00410B-DE-001.pdf",
                                         "b/NVC00411A-DE-001.pdf"]),
    ((), ["a/NVC00410A-DE-001.pdf", "a/NVC00410A-LI-002.docx", "a/NVC00410B-DE-001.pdf",
          "b/NVC004101A-DE-001.pdf", "b/NVC00411A-DE-001.pdf"]),
])
def test_selecao_filtra(base_nvc, selecao, esperado):
    plano = plano_de(base_nvc, selecao=selecao)
    assert entram(plano) == esperado
    for item in plano.itens:
        if item.acao != "ignorar":
            assert item.destino == plano.destino_raiz / item.origem.relative_to(plano.base)
    if selecao:
        fora = {i.origem.name: i.motivo for i in plano.itens}
        assert fora["leia-me.txt"] == "fora da lista"
    assert plano.problemas == []


def test_selecao_problemas(base_nvc):
    plano = plano_de(base_nvc, selecao=("XYZ", "NVC09999", "NVC00411A-ET-002", "NVC00410A"))
    assert plano.problemas == [("XYZ", "formato inválido"),
                               ("NVC09999", "não encontrado na pasta base"),
                               ("NVC00411A-ET-002", "tipo ET não permitido")]
    assert entram(plano) == ["a/NVC00410A-DE-001.pdf", "a/NVC00410A-LI-002.docx"]


def test_selecao_so_invalidos_nada_entra(base_nvc):
    plano = plano_de(base_nvc, selecao=("XYZ",))
    assert plano.a_copiar == [] and plano.a_converter == []
    assert plano.problemas == [("XYZ", "formato inválido")]


def test_selecao_no_relatorio_de_ignorados(base_nvc):
    plano = plano_de(base_nvc, selecao=("NVC00410A",))
    executar(plano)
    _, ignorados = ler_csv(plano.destino_raiz / "arquivos_ignorados.csv")
    assert ["b/NVC00411A-DE-001.pdf", "fora da lista"] in ignorados
