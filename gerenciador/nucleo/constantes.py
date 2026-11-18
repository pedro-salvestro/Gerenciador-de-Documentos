"""Constantes compartilhadas pelo núcleo."""

WORD = frozenset({".doc", ".docx", ".docm", ".dot", ".dotx", ".dotm"})
EXCEL = frozenset({".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".xltm"})
CAD = frozenset({".step", ".stp", ".dwg"})
PDF = ".pdf"

IGNORAR_DIRS = frozenset({"__pycache__", ".git"})
PREFIXO_TEMPORARIO = ".pdf_"

TIPOS_PADRAO = ("DE", "LI", "LD", "PR", "FO")

RELATORIO_CONVERTIDOS = "arquivos_convertidos.csv"
RELATORIO_APAGADOS = "arquivos_apagados.csv"
RELATORIO_IGNORADOS = "arquivos_ignorados.csv"
RELATORIOS = (RELATORIO_CONVERTIDOS, RELATORIO_APAGADOS, RELATORIO_IGNORADOS)
