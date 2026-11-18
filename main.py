"""Gerenciador de Documentos — ponto de entrada (também usado pelo PyInstaller)."""

import multiprocessing
import sys

if __name__ == "__main__":
    # Necessário no .exe: os processos de conversão reutilizam este executável.
    multiprocessing.freeze_support()
    from gerenciador.gui.app import executar

    sys.exit(executar())
