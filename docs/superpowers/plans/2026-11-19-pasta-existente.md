# Fluxo de entrega em pasta existente — plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development ou
> superpowers:executing-plans para executar este plano tarefa por tarefa. Os passos usam a
> sintaxe `- [ ]` para acompanhamento.

**Objetivo:** permitir que o fluxo de entrega acrescente PDFs a uma pasta já existente. Por
padrão, os PDFs que já existem são mantidos; com a opção marcada, são substituídos e os
antigos vão para a Lixeira.

**Arquitetura:**
- O fluxo atual ganha um modo novo (`pasta_existente`).
- O planejamento passa a calcular o arquivo final de cada item e marca como `MANTER` o que
  já existe.
- A conversão passa a acontecer numa pasta temporária `.pdf_entrega_*` dentro do destino.
  Só o PDF pronto é movido para o lugar final.
- A limpeza de pastas vazias remove apenas as pastas que a própria execução criou.

**Tecnologias:** Python 3.14, PySide6, Send2Trash, pytest e pytest-qt. O ambiente é o
`.venv` do projeto.

**Especificação:** `docs/superpowers/specs/2026-11-19-pasta-existente-design.md`

## Restrições globais

- A pasta base nunca é alterada (regra que já existe).
- Na pasta existente, nenhum arquivo pré-existente pode ser apagado ou sobrescrito sem
  `substituir_existentes=True`. Quando a substituição acontece, o arquivo antigo vai para
  a Lixeira (`send2trash`), nunca é apagado de vez.
- Só são removidas as pastas criadas pela própria execução, mais a pasta temporária.
- A caixa "Substituir" sempre começa desmarcada e não é lembrada. O modo é lembrado na
  chave `fluxo/pasta_existente`.
- Textos fixos:
  - ação na tabela: `"Já existe (mantido)"`;
  - motivo dos mantidos: `"já existe na pasta (mantido)"`;
  - motivo dos substituídos: `"substitui o PDF existente (antigo vai para a Lixeira)"`;
  - rótulo da caixa: `"Substituir PDFs que já existem (os antigos vão para a Lixeira)"`.
- **Decisão sobre falha ou cancelamento da conversão:** o Word/Excel vai para o seu lugar
  na entrega, como acontece hoje na pasta nova, **só se não existir arquivo com esse
  nome**. Se existir, o Word/Excel fica de fora e o erro avisa. Assim os testes atuais
  continuam valendo e nenhum arquivo do usuário é sobrescrito.

## Pontos de atenção na revisão

1. **Pasta existente com um `.docx` do usuário que tem o mesmo nome de um Word da base:**
   o `.docx` do usuário fica intacto. Teste na Tarefa 2.
2. **Subpasta vazia que já existia na pasta de destino:** ela é preservada. Teste na
   Tarefa 2.
3. **"Salvar em" apontando para uma pasta que contém a base** (por exemplo, a pasta-pai):
   gera `ErroValidacao`. Teste na Tarefa 2.
4. **Rodar a mesma seleção duas vezes:** a segunda execução não copia nem converte nada,
   tudo aparece como mantido e o arquivo existente fica intacto. Teste na Tarefa 2.
5. **Falha da Lixeira ao substituir:** o arquivo antigo fica, o novo não é gravado e o
   erro vai para o resumo. Teste na Tarefa 2.

---

### Tarefa 1: Relatório que acumula

**Arquivos:** modificar `gerenciador/nucleo/relatorios.py` e `gerenciador/nucleo/conversao.py`
(`gravar_relatorio_conversao`). Testes em `tests/test_relatorios.py`.

**Interfaces:**
- Produz:
  - `Relatorio.acrescentar(self, caminho: Path, cabecalho: list[str], linhas: list[list[str]]) -> Path | None`:
    - escreve o cabeçalho só se o arquivo não existir;
    - se o relatório estiver inativo, devolve `None`;
    - um `OSError` vai para `self.erros`, como em `gravar`.
  - `gravar_relatorio_conversao(resultados, base_relativa, relatorio, caminho, acrescentar: bool = False)`.

- [ ] **Passo 1: Escrever o teste que falha**

```python
def test_acrescentar_acumula_com_um_cabecalho(tmp_path):
    c = tmp_path / "r.csv"
    Relatorio().acrescentar(c, ["a", "b"], [["1", "x"]])
    Relatorio().acrescentar(c, ["a", "b"], [["2", "y"]])
    assert ler_csv(c) == (["a", "b"], [["1", "x"], ["2", "y"]])

def test_acrescentar_inativo(tmp_path):
    assert Relatorio(False).acrescentar(tmp_path / "r.csv", ["a"], [["1"]]) is None
    assert not (tmp_path / "r.csv").exists()
```

- [ ] **Passo 2:** `.venv\Scripts\python -m pytest tests/test_relatorios.py -q`. Esperado: FAIL (AttributeError).
- [ ] **Passo 3: Implementar.** Use o modo `"a"`. Escreva o BOM `utf-8-sig` só quando o
  arquivo for novo; para isso, abra com `encoding="utf-8"` se o arquivo já existir.
- [ ] **Passo 4:** rodar o mesmo comando. Esperado: PASS.

---

### Tarefa 2: Núcleo do fluxo em pasta existente

**Arquivos:** modificar `gerenciador/nucleo/fluxo.py`. Testes em `tests/test_fluxo_existente.py`
(novo).

**Interfaces:**
- Consome:
  - `Relatorio.acrescentar` e `gravar_relatorio_conversao(..., acrescentar=True)` (Tarefa 1);
  - `planejar_conversao` e `executar_conversao` (já existem).
- Produz:
  - `MANTER = "manter"`.
  - `ParametrosFluxo` ganha `pasta_existente: bool = False` e
    `substituir_existentes: bool = False`.
  - `ItemFluxo` ganha:
    - `final: Path | None = None`, o arquivo que fica na entrega (PDF copiado, PDF
      convertido ou cópia sem conversão);
    - `substituir: bool = False`.
  - `PlanoFluxo` ganha as propriedades `mantidos -> list[ItemFluxo]` (ação `MANTER`) e
    `a_substituir -> list[ItemFluxo]` (`substituir=True`). As propriedades `a_copiar` e
    `a_converter` continuam sem os mantidos.
  - `ResumoFluxo` ganha `mantidos: int = 0` e `substituidos: int = 0`.
  - `executar_fluxo(..., lixeira: Callable[[str], None] | None = None)`. Sem esse
    parâmetro, a lixeira padrão é `send2trash`.

Regras de `planejar_fluxo`:
- **Com `pasta_existente=True`:**
  - "Salvar em" vazio gera `ErroValidacao("Escolha a pasta existente em \"Salvar em\".")`;
  - uma pasta inexistente gera a mensagem que já existe ("A pasta onde salvar não existe.");
  - `destino_raiz = pasta_destino.resolve()`;
  - `nome_destino` é ignorado e não é validado.
- **Proteções:** ficam as que já existem (destino igual à base ou dentro dela) e entra
  uma nova: se o destino contém a base (`destino_raiz in base.parents`), gera
  `ErroValidacao("A pasta de destino não pode conter a pasta base.")`.
- **Quando o arquivo final já existe:**
  1. Primeiro, calcule os `trabalhos` com **todos** os itens a converter. Isso evita que os
     nomes de PDF mudem entre execuções.
  2. Depois, para cada item que não é `IGNORAR`, verifique se `final` já existe. Se existir
     e `substituir_existentes=False`, o item vira `MANTER` com o motivo do texto fixo. Se
     existir e `substituir_existentes=True`, ele recebe `substituir=True` e o motivo do texto
     fixo.
  3. Por fim, retire de `trabalhos` os trabalhos dos itens `MANTER`.

Regras de `executar_fluxo`, em ordem:
1. **Pasta de destino:**
   - no modo nova, `mkdir`, como hoje;
   - no modo existente, se a pasta sumiu, gera `ErroValidacao`.
2. **Pastas que faltam:** crie-as por um auxiliar que registra cada pasta criada.
3. **Cópia dos PDFs (itens `COPIAR`):**
   - se `substituir`, envie o arquivo final antigo para a lixeira; se a lixeira falhar,
     registre o erro e pule o item;
   - se o arquivo final existir sem `substituir` e não tiver sido copiado nesta execução,
     registre o erro "já existe" e pule;
   - depois, faça `copy2` + `chmod`, como hoje.
4. **Conversão:**
   - copie os Word/Excel para `staging = tempfile.mkdtemp(prefix=".pdf_entrega_", dir=destino_raiz)`,
     no mesmo caminho relativo;
   - converta com `trabalhos` remapeados para dentro do staging;
   - quando a conversão der certo, aplique as mesmas regras de lixeira e "já existe" do
     passo 3 e faça `os.replace` do PDF do staging para o arquivo final;
   - quando falhar ou for cancelada, mova o Word/Excel para `item.destino` só se esse
     caminho não existir; se existir, registre o erro.
5. **Limpeza:** faça `shutil.rmtree(staging)` e remova, das mais fundas para as mais
   rasas, as pastas criadas que ficaram vazias. Não use `remover_pastas_vazias` na raiz.
6. **Relatórios:** convertidos com `acrescentar=True` (relativos ao staging, que é igual
   ao caminho final); ignorados com `gravar`, como hoje.
7. **Resumo:** `mantidos = len(plano.mantidos)` e `substituidos` igual à quantidade de
   envios bem-sucedidos para a lixeira.

- [ ] **Passo 1: Escrever os testes que falham.** Use o fixture `base` do conftest. A
  `pasta` é `tmp_path / "Entrega"`, criada no teste. A lixeira é um dublê que move o
  arquivo para `tmp_path / "lixeira"` e anota o caminho.

```python
def existente(base, pasta, **kw): return planejar_fluxo(ParametrosFluxo(base, "", TIPOS, pasta_destino=pasta, pasta_existente=True, **kw))

def test_existente_mantem_pdf_que_ja_existe(base, pasta):
    criar(pasta, "a/X-DE-001.pdf")   # conteúdo "a/X-DE-001.pdf"
    plano = existente(base, pasta)
    assert [i.final.name for i in plano.mantidos] == ["X-DE-001.pdf"]
    resumo = executar(plano)
    assert (pasta / "a/X-DE-001.pdf").read_text(encoding="utf-8") == "a/X-DE-001.pdf"
    assert resumo.mantidos == 1 and resumo.copiados == 1      # só X-PR-006.PDF
    assert (pasta / "a/X-LI-002.pdf").exists() and (pasta / "c/X-FO-005.pdf").exists()

def test_existente_converte_ja_existente_e_mantido(base, pasta):  # PDF de conversão já existe
    criar(pasta, "a/X-LI-002.pdf"); plano = existente(base, pasta)
    assert "X-LI-002.docx" in [i.origem.name for i in plano.mantidos]
    assert all(t.destino.name != "X-LI-002.pdf" for t in plano.trabalhos)

def test_existente_substituir_manda_antigo_para_lixeira(base, pasta, lixeira):
    criar(pasta, "a/X-DE-001.pdf", "a/X-LI-002.pdf")
    plano = existente(base, pasta, substituir_existentes=True)
    resumo = executar(plano, lixeira=lixeira)
    assert sorted(Path(p).name for p in lixeira.enviados) == ["X-DE-001.pdf", "X-LI-002.pdf"]
    assert (pasta / "a/X-LI-002.pdf").read_bytes() == b"%PDF-fake"
    assert resumo.substituidos == 2

def test_existente_docx_do_usuario_intacto(base, pasta):          # Review Focus 1
    criar(pasta, "a/X-LI-002.docx")
    resumo = executar(existente(base, pasta))
    assert (pasta / "a/X-LI-002.docx").read_text(encoding="utf-8") == "a/X-LI-002.docx"
    assert (pasta / "a/X-LI-002.pdf").exists() and resumo.erros == []

def test_existente_preserva_pasta_vazia_do_usuario(base, pasta):  # Review Focus 2
    criar(pasta, "minha/vazia/")
    executar(existente(base, pasta))
    assert (pasta / "minha/vazia").is_dir()
    assert not any(p.name.startswith(".pdf_entrega_") for p in pasta.iterdir())

def test_existente_remove_pastas_criadas_vazias(base, pasta):
    executar(existente(base, pasta, selecao=("X-DE-001",)))  # tipo DE; b/ e c/ nunca criadas
    assert sorted(p.name for p in pasta.iterdir() if p.is_dir()) == ["a"]

def test_existente_contendo_a_base_recusado(base):                # Review Focus 3
    with pytest.raises(ErroValidacao): existente(base, base.parent)

@pytest.mark.parametrize("onde", ["base", "dentro"])
def test_existente_base_ou_dentro_recusado(base, onde): ...       # base e base/"a"

def test_existente_sem_pasta_recusado(base):
    with pytest.raises(ErroValidacao): planejar_fluxo(ParametrosFluxo(base, "", TIPOS, pasta_existente=True))

def test_existente_segunda_execucao_nada_muda(base, pasta):       # Review Focus 4
    executar(existente(base, pasta))
    antes = {p: p.stat().st_mtime_ns for p in pasta.rglob("*.pdf")}
    plano = existente(base, pasta)
    assert plano.a_copiar == [] and plano.a_converter == [] and len(plano.mantidos) == 4
    executar(plano)
    assert {p: p.stat().st_mtime_ns for p in pasta.rglob("*.pdf")} == antes

def test_existente_falha_da_lixeira_preserva_antigo(base, pasta):  # Review Focus 5
    criar(pasta, "a/X-DE-001.pdf")
    def quebrada(c): raise OSError("lixeira indisponível")
    resumo = executar(existente(base, pasta, substituir_existentes=True), lixeira=quebrada)
    assert (pasta / "a/X-DE-001.pdf").read_text(encoding="utf-8") == "a/X-DE-001.pdf"
    assert resumo.erros[0][0] == "a/X-DE-001.pdf" and resumo.substituidos == 0

def test_existente_relatorio_convertidos_acumula(base, pasta):
    executar(existente(base, pasta, selecao=("X-LI-002",)))
    executar(existente(base, pasta, selecao=("X-FO-005",)))
    _, linhas = ler_csv(pasta / "arquivos_convertidos.csv")
    assert [l[1] for l in linhas] == ["a/X-LI-002.docx", "c/X-FO-005.XLSX"]

def test_falha_conversao_existente_nao_sobrescreve_docx(base, pasta):
    criar(pasta, "a/X-LI-002.docx")
    resumo = executar(existente(base, pasta), funcao=converter_falha)
    assert (pasta / "a/X-LI-002.docx").read_text(encoding="utf-8") == "a/X-LI-002.docx"
    assert any(a == "a/X-LI-002.docx" for a, _ in resumo.erros)
```

As fixtures `pasta` (cria e devolve `tmp_path / "Entrega"`) e `lixeira` ficam neste
arquivo. `executar` e `TIPOS` seguem o mesmo padrão de `tests/test_fluxo.py`.

- [ ] **Passo 2:** `.venv\Scripts\python -m pytest tests/test_fluxo_existente.py -q`. Esperado: FAIL.
- [ ] **Passo 3: Implementar as regras acima em `fluxo.py`.**
- [ ] **Passo 4:** `.venv\Scripts\python -m pytest tests/test_fluxo_existente.py tests/test_fluxo.py tests/test_revisao.py -q`.
  Esperado: PASS, com os testes antigos do fluxo intactos.

---

### Tarefa 3: Aba Fluxo de entrega

**Arquivos:** modificar `gerenciador/gui/aba_fluxo.py`. Testes em `tests/test_gui_fluxo.py`.

**Interfaces:**
- Consome: `MANTER`, os novos campos de `ParametrosFluxo`, `ResumoFluxo` e `PlanoFluxo`, e
  `executar_fluxo(..., lixeira=)`.
- Produz:
  - `AbaFluxo(..., lixeira: Callable[[str], None] | None = None)`;
  - os widgets públicos `opcao_nova` e `opcao_existente` (`QRadioButton`, num
    `QButtonGroup`) e `caixa_substituir` (`QCheckBox`).

Comportamento:
- **Botões de opção:** os dois botões de opção ficam acima de "Nome da pasta nova".
- **Modo existente:**
  - o `campo_nome` fica desativado;
  - a `caixa_substituir` fica visível;
  - o placeholder de "Salvar em" vira "Pasta da entrega já existente";
  - o `rotulo_destino` mostra "→ os PDFs serão adicionados em: <pasta>", ou
    "→ escolha a pasta existente em \"Salvar em\"" se o campo estiver vazio.
- **Modo novo:** o comportamento atual, com a caixa oculta e desmarcada.
- **Invalidação:** mudar o modo ou a caixa invalida a análise. O modo é salvo em
  `fluxo/pasta_existente`.
- **Tabela:**
  - `ROTULO_ACAO[MANTER] = "Já existe (mantido)"`;
  - `FILTROS` ganha `"Já existe"`;
  - o filtro "Já existe" usa a coluna 1 com o texto `"Já existe"`.
- **Resumo da análise:** acrescenta `f"{n} já existem (mantidos)"` ou
  `f"{n} PDFs serão substituídos"` quando houver. A linha de destino vira
  `"Pasta existente: …"` no modo existente.
- **Confirmação:** no modo existente, o texto começa com "Adicionar à pasta:" em vez de
  "Criar a pasta:" e inclui as linhas de mantidos e substituídos.
- **Resumo final:** acrescenta `f"{resumo.mantidos} mantidos"` e, se houver,
  `f"{resumo.substituidos} substituídos"`.

- [ ] **Passo 1: Escrever os testes que falham**

```python
def test_modo_existente_desativa_nome_e_mostra_substituir(aba): ...
    # opcao_existente.setChecked(True) -> not campo_nome.isEnabled(); caixa_substituir.isVisibleTo(aba); not isChecked()
def test_existente_analise_mostra_ja_existem(qtbot, aba, base, tmp_path):
    # pasta=tmp_path/"Entrega" com a/X-DE-001.pdf; modo existente; seletor_destino=pasta; analisar
    assert "1 já existem (mantidos)" in aba.rotulo_resumo.text()
def test_existente_executa_sem_tocar_no_existente(qtbot, aba, base, tmp_path, monkeypatch): ...
    # Yes na confirmação; espera botao_abrir_pasta; X-DE-001.pdf com o mesmo conteúdo; X-LI-002.pdf criado
def test_substituir_usa_lixeira(qtbot, config_temp, base, tmp_path, monkeypatch): ...
    # AbaFluxo(..., lixeira=enviados.append); marca caixa; executa; enviados contém X-DE-001.pdf
def test_modo_lembrado_e_substituir_nao(qtbot, config_temp): ...
    # marca existente + substituir; nova AbaFluxo: opcao_existente marcado, caixa desmarcada
```

- [ ] **Passo 2:** `.venv\Scripts\python -m pytest tests/test_gui_fluxo.py -q`. Esperado: FAIL nos novos testes.
- [ ] **Passo 3: Implementar.** A lixeira do teste de substituição precisa remover o
  arquivo, por exemplo com `os.remove` junto de um append. Senão `os.replace` sobrescreve
  e o teste não distingue os casos. Ajuste o dublê de acordo.
- [ ] **Passo 4:** `.venv\Scripts\python -m pytest -q`. Esperado: suíte inteira PASS.

---

### Tarefa 4: Documentação e executável

- [ ] **Passo 1:** no `README.md`, na seção do Fluxo de entrega, acrescente um parágrafo
  sobre "Adicionar a uma pasta existente": o que é mantido, a caixa Substituir e a
  Lixeira.
- [ ] **Passo 2:** `.venv\Scripts\python -m PyInstaller gerenciador.spec --noconfirm`. Esperado:
  `dist\GerenciadorDocumentos.exe` atualizado.
- [ ] **Passo 3:** verificação manual com Office real pelo código-fonte. Rode o script
  `verificacao_real` adaptado: primeiro uma execução numa pasta nova com a seleção `T-DE`,
  depois uma segunda no modo existente com a seleção `T-LI`. Confira que o PDF do primeiro
  continua igual e que o segundo foi acrescentado.
