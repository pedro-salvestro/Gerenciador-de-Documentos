from pathlib import Path

import pytest

from conftest import criar
from gerenciador.nucleo import espaco as modulo_espaco
from gerenciador.nucleo.arquivos import (
    listar_arquivos, listar_pastas, listar_pastas_vazias, remover_pastas_vazias,
    separar_lista, tipo_documento, tipo_limpeza,
)
from gerenciador.nucleo.erros import ErroValidacao
from gerenciador.nucleo.espaco import EspacoTrabalho


def test_tipo_documento():
    assert tipo_documento(Path("NVC00410A-DE-001.docx")) == "DE"
    assert tipo_documento(Path("x-fo-12.PDF")) == "FO"
    assert tipo_documento(Path("NVC00410A.dwg")) is None
    assert tipo_documento(Path("NVC00410A-DE-001_rev2.pdf")) is None


def test_tipo_limpeza():
    assert tipo_limpeza(Path("a.pdf")) is None
    assert tipo_limpeza(Path("X-et-01.docx")) == "documento ET"
    assert tipo_limpeza(Path("m.DWG")) == "arquivo STEP/DWG"
    assert tipo_limpeza(Path("m.xlsx")) == "documento Word/Excel"
    assert tipo_limpeza(Path("m.txt")) == "outro arquivo"


def test_listar_arquivos_ignora_relatorios_temporarios_e_dirs(espaco):
    criar(espaco.raiz, "a.docx", "~$a.docx", "sub/b.pdf", ".pdf_x/c.docx",
          "__pycache__/d.py", "arquivos_apagados.csv")
    assert [espaco.relativo(p) for p in listar_arquivos(espaco)] == ["a.docx", "sub/b.pdf"]


def test_listar_arquivos_ignora_programa(espaco, monkeypatch):
    exe = espaco.raiz / "Gerenciador.exe"
    exe.write_text("x")
    monkeypatch.setattr(modulo_espaco, "caminhos_programa", lambda: frozenset({exe.resolve()}))
    assert listar_arquivos(espaco) == []


def test_listar_pastas_ordem(espaco):
    criar(espaco.raiz, "b/c/", "a/", ".pdf_t/", ".git/")
    assert [espaco.relativo(p) for p in listar_pastas(espaco)] == ["a", "b", "b/c"]


def test_listar_pastas_vazias(tmp_path):
    criar(tmp_path, "a/b/", "c/x.txt")
    assert [p.name for p in listar_pastas_vazias(tmp_path)] == ["b"]


def test_separar_lista():
    assert separar_lista(' "Pasta\\A/" ; b,\nC ') == ["pasta/a", "b", "c"]


def test_remover_pastas_vazias_aninhadas(tmp_path):
    criar(tmp_path, "a/b/c/", "d/x.txt")
    assert remover_pastas_vazias(tmp_path) == 3
    assert (tmp_path / "d").is_dir() and not (tmp_path / "a").exists()


def test_abrir_pasta_inexistente():
    with pytest.raises(ErroValidacao):
        EspacoTrabalho.abrir("Z:/nao/existe/mesmo")
