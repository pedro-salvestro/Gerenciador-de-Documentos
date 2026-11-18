import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest

from gerenciador.nucleo.espaco import EspacoTrabalho


def criar(raiz, *relativos):
    """Cria arquivos (ou pastas, se terminarem em '/') com conteúdo simples."""
    for rel in relativos:
        caminho = raiz / rel
        if rel.endswith("/"):
            caminho.mkdir(parents=True, exist_ok=True)
        else:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(rel, encoding="utf-8")


@pytest.fixture
def espaco(tmp_path):
    return EspacoTrabalho.abrir(tmp_path)


ARVORE_OBRA = ("obra/a/X-DE-001.pdf", "obra/a/X-LI-002.docx", "obra/a/X-ET-003.pdf",
               "obra/a/X-DE-004.dwg", "obra/b/foto.jpg", "obra/b/pacote.zip",
               "obra/c/X-FO-005.XLSX", "obra/c/X-PR-006.PDF")


@pytest.fixture
def base(tmp_path):
    criar(tmp_path, *ARVORE_OBRA)
    return tmp_path / "obra"


def relativos(raiz):
    return sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if p.is_file())


@pytest.fixture
def config_temp(tmp_path_factory):
    from PySide6.QtCore import QSettings
    from gerenciador.gui.configuracoes import Configuracoes
    arquivo = tmp_path_factory.mktemp("config") / "config.ini"
    return Configuracoes(QSettings(str(arquivo), QSettings.Format.IniFormat))


@pytest.fixture(autouse=True)
def _aguardar_trabalhadores():
    yield
    try:
        from gerenciador.gui.trabalhador import aguardar_todos
    except ImportError:
        return
    aguardar_todos(5000)
