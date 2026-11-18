"""Conversores falsos usados nos testes (no nível do módulo)."""


def converter_ok(origem, destino, *args):
    destino.write_bytes(b"%PDF-fake")
    return "ok", ""


def converter_falha(origem, destino, *args):
    return "erro", "falhou"
