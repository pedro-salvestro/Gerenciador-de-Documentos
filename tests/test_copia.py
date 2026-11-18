import pytest

from conftest import criar
from gerenciador.nucleo.copia import executar_copia, planejar_copia, validar_nome_pasta
from gerenciador.nucleo.erros import ErroValidacao


@pytest.mark.parametrize("nome", ["", "a/b", "a\b", "..", ".", "CON", "com1.txt", "lpt9",
                                  "nome.", "x:y", "a*b"])
def test_nome_pasta_invalido(nome):
    with pytest.raises(ErroValidacao):
        validar_nome_pasta(nome)


def test_nome_pasta_tira_espacos():
    assert validar_nome_pasta("  Entrega ") == "Entrega"


def test_planejar_destino(espaco):
    criar(espaco.raiz, "docs/NVC00410A-DE-001.pdf", "docs/NVC00410A.dwg", "NVC00410AB-DE-1.pdf")
    plano = planejar_copia(espaco, "nvc00410a", "Arquivos")
    destinos = sorted(espaco.relativo(d) for _, d in plano.itens)
    assert destinos == ["NVC00410/A/Arquivos/NVC00410A-DE-001.pdf",
                        "NVC00410/A/Arquivos/NVC00410A.dwg"]


def test_codigo_invalido(espaco):
    criar(espaco.raiz, "x.pdf")
    with pytest.raises(ErroValidacao) as e:
        planejar_copia(espaco, "ABC1, NVC1A", "Arquivos")
    assert e.value.itens == ["abc1"]


def test_destino_existente(espaco):
    criar(espaco.raiz, "NVC1A-DE-1.pdf", "NVC1/A/Arquivos/")
    with pytest.raises(ErroValidacao):
        planejar_copia(espaco, "NVC1A", "Arquivos")


def test_codigo_sem_arquivos(espaco):
    criar(espaco.raiz, "NVC1A-DE-1.pdf")
    with pytest.raises(ErroValidacao) as e:
        planejar_copia(espaco, "NVC1A; NVC2B", "Arquivos")
    assert e.value.itens == ["nvc2b"]


def test_nome_repetido_no_destino(espaco):
    criar(espaco.raiz, "a/NVC1A-DE-1.pdf", "b/NVC1A-DE-1.pdf")
    with pytest.raises(ErroValidacao):
        planejar_copia(espaco, "NVC1A", "Arquivos")


def test_lista_vazia(espaco):
    with pytest.raises(ErroValidacao):
        planejar_copia(espaco, "  ", "Arquivos")


def test_executar_copia(espaco):
    criar(espaco.raiz, "NVC1A-DE-1.pdf")
    plano = planejar_copia(espaco, "NVC1A", "Arquivos")
    r = executar_copia(plano)
    destino = espaco.raiz / "NVC1/A/Arquivos/NVC1A-DE-1.pdf"
    assert destino.read_text(encoding="utf-8") == "NVC1A-DE-1.pdf"
    assert [x[2] for x in r] == ["copiado"]
