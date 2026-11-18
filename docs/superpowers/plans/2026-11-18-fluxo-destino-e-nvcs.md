# Fluxo: destino escolhível e seleção por NVC/arquivo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na aba Fluxo, permitir escolher a pasta onde a entrega é criada e filtrar por
uma lista de NVCs/arquivos, avisando itens problemáticos na confirmação.

**Architecture:** Dois parâmetros novos em `ParametrosFluxo` (`pasta_destino`,
`selecao`); `planejar_fluxo` aplica o filtro e devolve `PlanoFluxo.problemas`. A aba
Fluxo ganha um `SeletorPasta` "Salvar em" e uma caixa de texto da lista, e mostra os
problemas no resumo e no início da confirmação.

**Tech Stack:** Python 3.14, PySide6, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-11-18-fluxo-destino-e-nvcs-design.md`

## Global Constraints

- Campos vazios mantêm o comportamento atual (destino ao lado da base; todos os NVCs).
- A pasta base nunca é alterada.
- Itens problemáticos não bloqueiam a análise nem a execução; só são avisados.
- Textos da interface em português, no tom das mensagens existentes.
- Rodar testes: `.venv\Scripts\python -m pytest -q` (linha de base: 112 passando).

## Review Focus

- Lista com só itens inválidos → nada entra, *Executar* fica desabilitado, problemas aparecem no resumo.
- Item repetido com caixa diferente (`nvc00410a` e `NVC00410A`) → um só item, sem aviso duplicado.
- `NVC00410` não pode casar com `NVC004101A-…` (dígitos diferentes) → comparação pelo número inteiro.
- "Salvar em" apontando para dentro da base → erro "A pasta nova não pode ficar dentro da pasta base."
- "Salvar em" com pasta inexistente → erro claro, nada é criado.

---

### Task 1: Núcleo — pasta de destino escolhível

**Files:**
- Modify: `gerenciador/nucleo/fluxo.py` (`ParametrosFluxo`, `planejar_fluxo`)
- Test: `tests/test_fluxo.py`

**Interfaces:**
- Produces: `ParametrosFluxo.pasta_destino: Path | None = None`. `None` → `espaco.raiz.parent`.

- [ ] **Step 1: Testes que falham**

```python
def test_destino_em_outra_pasta(base, tmp_path):
    outra = tmp_path / "saida"; outra.mkdir()
    assert plano_de(base, pasta_destino=outra).destino_raiz == outra.resolve() / "Entrega"

def test_destino_inexistente(base, tmp_path):
    with pytest.raises(ErroValidacao, match="não existe"):
        plano_de(base, pasta_destino=tmp_path / "nada")

def test_destino_dentro_da_base(base):
    with pytest.raises(ErroValidacao, match="dentro da pasta base"):
        plano_de(base, pasta_destino=base / "a")
```

- [ ] **Step 2:** `.venv\Scripts\python -m pytest tests/test_fluxo.py -q` → os 3 falham.
- [ ] **Step 3:** Implementar. Se `pasta_destino` não for diretório: `ErroValidacao("A pasta onde salvar não existe.", [str(p)])`; senão usar `pasta_destino.resolve()`. As checagens existentes (dentro da base, já existe) passam a valer para o destino escolhido.
- [ ] **Step 4:** Rodar a suíte inteira → tudo passa.
- [ ] **Step 5:** Commit `feat(fluxo): permite escolher onde criar a pasta de entrega`.

### Task 2: Núcleo — seleção por NVC/arquivo e itens problemáticos

**Files:**
- Modify: `gerenciador/nucleo/fluxo.py`
- Test: `tests/test_fluxo.py`

**Interfaces:**
- Produces:
  - `separar_selecao(texto: str) -> tuple[str, ...]` — separa por `,` `;` ou quebra de linha, tira espaços/aspas, remove repetidos sem diferenciar maiúsculas (mantém a primeira grafia).
  - `ParametrosFluxo.selecao: tuple[str, ...] = ()` — vazio = sem filtro.
  - `PlanoFluxo.problemas: list[tuple[str, str]]` — `(item, motivo)` na ordem da lista.
  - Motivos: `"formato inválido"`, `"não encontrado na pasta base"`, ou, se achado mas nada entra, os motivos distintos dos arquivos dele unidos por `"; "` (ex.: `"tipo ET não permitido"`).
  - Arquivo fora da seleção: `IGNORAR`, motivo `"fora da lista"`.

Regras de casamento (sem diferenciar maiúsculas), com o NVC do arquivo lido por
`^NVC(\d+)([A-Z]?)(?![A-Za-z0-9])` no nome sem extensão:
- `NVC\d+` → mesmo número (comparar como texto dos dígitos), qualquer variante;
- `NVC\d+[A-Z]` → mesmo número e variante;
- outro texto começando com `NVC\d+` → nome do arquivo com extensão **ou** sem extensão igual ao item;
- qualquer outra coisa → `"formato inválido"`, não casa com nada.

O filtro vem antes de `_classificar`: arquivo que não casa com nenhum item fica
"fora da lista"; o que casa segue as regras de tipo/formato de hoje.

- [ ] **Step 1: Testes que falham** (criar arquivos com `criar(base, ...)` em uma árvore própria de NVCs):

```python
ARVORE_NVC = ("a/NVC00410A-DE-001.pdf", "a/NVC00410A-LI-002.docx", "a/NVC00410B-DE-001.pdf",
              "b/NVC00411A-DE-001.pdf", "b/NVC00411A-ET-002.pdf", "b/NVC004101A-DE-001.pdf")

def test_separar_selecao():
    assert separar_selecao(' NVC00410A;\n"nvc00410a", NVC00411\r\n') == ("NVC00410A", "NVC00411")

# entram (relativos à base) para cada seleção:
# ("NVC00410",)              -> a/NVC00410A-DE-001.pdf, a/NVC00410A-LI-002.docx, a/NVC00410B-DE-001.pdf
# ("NVC00410A",)             -> a/NVC00410A-DE-001.pdf, a/NVC00410A-LI-002.docx
# ("NVC00410A-DE-001",)      -> a/NVC00410A-DE-001.pdf
# ("nvc00410a-de-001.PDF",)  -> a/NVC00410A-DE-001.pdf
# ()                         -> os 5 de tipo permitido (sem filtro)
# Para cada caso: destino = destino_raiz / mesmo caminho relativo; os demais têm motivo "fora da lista".

def test_problemas(tmp_path):
    # seleção ("XYZ", "NVC09999", "NVC00411A-ET-002", "NVC00410A")
    assert plano.problemas == [("XYZ", "formato inválido"),
                               ("NVC09999", "não encontrado na pasta base"),
                               ("NVC00411A-ET-002", "tipo ET não permitido")]

def test_so_itens_invalidos_nada_entra(tmp_path):
    # seleção ("XYZ",) -> a_copiar == a_converter == [] e problemas == [("XYZ", "formato inválido")]
```

- [ ] **Step 2:** Rodar → falham (import de `separar_selecao` / atributo `problemas`).
- [ ] **Step 3:** Implementar `separar_selecao`, o casamento e `problemas` em `planejar_fluxo`.
- [ ] **Step 4:** Suíte inteira passa (o relatório de ignorados já inclui "fora da lista" sem mudança).
- [ ] **Step 5:** Commit `feat(fluxo): filtra a entrega por lista de NVCs ou arquivos`.

### Task 3: Aba Fluxo — "Salvar em" e lista de NVCs/arquivos

**Files:**
- Modify: `gerenciador/gui/aba_fluxo.py`
- Test: `tests/test_gui_fluxo.py`

**Interfaces:**
- Consumes: `ParametrosFluxo.pasta_destino`, `ParametrosFluxo.selecao`, `separar_selecao`, `PlanoFluxo.problemas`.
- Produces (usados nos testes): `aba.seletor_destino: SeletorPasta` (chave `fluxo/destino`, placeholder `"Vazio = ao lado da pasta base"`), `aba.campo_selecao: QPlainTextEdit` (~3 linhas de altura, placeholder `"Vazio = todos. Ex.: NVC00410A, NVC00411, NVC00412A-DE-001"`, lembrado em `fluxo/selecao`).

Comportamento:
- Formulário: "Salvar em:" logo após "Nome da pasta nova:"; "NVCs / arquivos:" após "Tipos mantidos:".
- Mudança em qualquer um dos dois invalida a análise (`_parametros_mudaram`) e atualiza o rótulo de destino: `→ será criada: {destino or base.parent}/{nome}`.
- `_definir_ocupado` também desabilita os dois campos.
- Resumo da análise: se houver problemas, acrescentar linha `"Itens da lista com problema: "` + até 5 itens no formato `"ITEM (motivo)"` separados por `", "` + `" e mais N"` se passar de 5.
- Confirmação: se houver problemas, o texto começa com `"Estes itens da lista não vão entrar:\n"` + `listar_itens([f"{item} — {motivo}" ...])` + `"\n\nDeseja continuar sem eles?\n\n"`, seguido do texto atual.

- [ ] **Step 1: Testes que falham**

```python
def test_salvar_em_outra_pasta(qtbot, aba, base, tmp_path, monkeypatch):
    # sim no question; seletor_destino.definir_pasta(tmp_path/"saida" criada) -> executa
    # -> (tmp_path/"saida"/"Entrega"/"a"/"X-LI-002.pdf").exists() e rotulo_destino contém esse caminho

def test_selecao_com_problema_avisa_na_confirmacao(qtbot, aba, base, monkeypatch):
    # campo_selecao "X-DE-001, NVC09999"? -> usar árvore com NVC; capturar texto do question
    # -> texto começa com "Estes itens da lista não vão entrar:" e contém "NVC09999 — não encontrado na pasta base"
    # -> rotulo_resumo contém "Itens da lista com problema: NVC09999 (não encontrado na pasta base)"

def test_campos_novos_lembrados(qtbot, config_temp, base, tmp_path):
    # destino e seleção definidos numa aba aparecem numa segunda AbaFluxo com o mesmo config
```

- [ ] **Step 2:** Rodar → falham.
- [ ] **Step 3:** Implementar na `AbaFluxo`.
- [ ] **Step 4:** Suíte inteira passa.
- [ ] **Step 5:** Atualizar o README (seção Fluxo de entrega: "Salvar em" e lista de NVCs/arquivos) e commit `feat(gui): salvar em e lista de NVCs na aba Fluxo`.
