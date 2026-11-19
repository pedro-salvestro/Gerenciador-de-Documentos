from gerenciador.nucleo.relatorios import Relatorio, ler_csv


def test_gravar_e_ler(tmp_path):
    c = tmp_path / "r.csv"
    assert Relatorio().gravar(c, ["a", "b"], [["1", "ç"]]) == c
    assert c.read_bytes().startswith(b"\xef\xbb\xbf")
    assert ler_csv(c) == (["a", "b"], [["1", "ç"]])


def test_inativo_nao_cria(tmp_path):
    assert Relatorio(ativo=False).gravar(tmp_path / "r.csv", ["a"], [["1"]]) is None
    assert not (tmp_path / "r.csv").exists()


def test_acrescentar_acumula_com_um_cabecalho(tmp_path):
    c = tmp_path / "r.csv"
    Relatorio().acrescentar(c, ["a", "b"], [["1", "x"]])
    Relatorio().acrescentar(c, ["a", "b"], [["2", "y"]])
    assert ler_csv(c) == (["a", "b"], [["1", "x"], ["2", "y"]])


def test_acrescentar_inativo(tmp_path):
    assert Relatorio(False).acrescentar(tmp_path / "r.csv", ["a"], [["1"]]) is None
    assert not (tmp_path / "r.csv").exists()


def test_acrescentar_falha_registra_erro(tmp_path):
    (tmp_path / "r.csv").mkdir()
    relatorio = Relatorio()
    assert relatorio.acrescentar(tmp_path / "r.csv", ["a"], [["1"]]) is None
    assert relatorio.erros
