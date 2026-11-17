# Interface gráfica do Gerenciador de Documentos — plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development
> ou superpowers:executing-plans para executar este plano tarefa por tarefa. Os
> passos usam a sintaxe `- [ ]` para acompanhamento.

**Objetivo:** substituir o menu de terminal por um programa PySide6. A aba
principal executa o fluxo de entrega: monta uma pasta nova só com os PDFs dos
tipos permitidos. As abas avulsas mantêm as funções atuais. O programa é
distribuído como `.exe`.

**Arquitetura:**
- **Núcleo (`gerenciador/nucleo`):** sem Qt e sem `input()`/`print()`. Toda
  operação tem `planejar_*` (devolve uma prévia ou levanta `ErroValidacao`) e
  `executar_*` (recebe callbacks de progresso e cancelamento).
- **Interface (`gerenciador/gui`):** só monta telas e roda o núcleo em QThread,
  através do `Trabalhador`.
- **Testes:** o núcleo é testado com pytest. A GUI tem testes de fumaça com
  pytest-qt.

**Tecnologias:** Python 3.14, PySide6, pywin32, pypdf, Send2Trash, pytest,
pytest-qt e PyInstaller.

**Especificação:** `docs/superpowers/specs/2026-11-17-interface-grafica-design.md`

**Fonte das regras atuais:** `gerenciador_documentos.py` (o "script antigo"). As
referências `antigo:NN-MM` apontam para as linhas dele. Ele não é alterado.

## Restrições globais

- Windows 11, Python 3.14, rodando num venv `.venv` na pasta do projeto.
- O fluxo **nunca escreve, move ou apaga nada na pasta base**.
- Pasta nova: `base.parent / nome`. Se já existir, ou se cair dentro da base,
  gera `ErroValidacao` antes de qualquer escrita.
- Tipos padrão: `DE, LI, LD, PR, FO`. Tipo = regex `-([A-Za-z]{2})-\d+$` aplicada
  a `Path.stem`. A comparação é sem diferenciar maiúsculas e minúsculas, e o
  resultado é em maiúsculas.
- Entrega: entram PDFs de tipo permitido (copiados) e Word/Excel de tipo
  permitido (copiados e convertidos). O resto é ignorado.
- O Word/Excel copiado só é apagado (`unlink`, definitivo) depois de uma
  conversão bem-sucedida. Em falha ou cancelamento, ele permanece.
- Funções avulsas: mesmas regras e mensagens do script antigo. Elas usam a
  Lixeira (`send2trash`), nunca exclusão definitiva.
- O programa (`sys.executable` quando empacotado; `main.py` e `gerenciador/` em
  modo fonte) nunca aparece em listagens, prévias ou exclusões.
- CSV: `;`, `utf-8-sig`, com os cabeçalhos do script antigo. Com
  `Relatorio(ativo=False)`, nenhum CSV é criado.
- Nomes dos relatórios: `arquivos_convertidos.csv`, `arquivos_apagados.csv`,
  `arquivos_ignorados.csv`.
- `main.py` chama `multiprocessing.freeze_support()` antes de importar o Qt.
- Textos da interface em português.

## Pontos de atenção na revisão

1. **Falha ao copiar um arquivo** (em uso, sem permissão): o fluxo registra o erro
   desse arquivo e continua com os demais, sem derrubar o programa. Teste na
   Tarefa 6.
2. **Cancelar no meio da conversão:** os itens pendentes ficam `cancelado`, os
   Word/Excel deles permanecem na pasta nova e o resumo marca `cancelado=True`.
   Teste na Tarefa 6.
3. **Extensões em maiúsculas** (`.PDF`, `.DOCX`, `.XLSX`): são classificadas como
   as minúsculas. Teste na Tarefa 6.
4. **Campo de tipos digitado de forma bagunçada** (`"de; li ,pr\nfo"`): vira
   `{DE, LI, PR, FO}`. Entrada vazia ou item que não tem 2 letras gera
   `ErroValidacao`. Teste na Tarefa 6.
5. **Nome de pasta inválido no Windows** (`CON`, `nome.`, `" nome"`, `a/b`) **ou
   base inexistente:** gera `ErroValidacao` com mensagem clara, não traceback.
   Teste na Tarefa 5 (nome) e na Tarefa 6 (base).

**Sem git:** a pasta não é um repositório, então não há passos de commit. Se o
usuário criar um repositório, faça um commit ao fim de cada tarefa.

---

### Tarefa 1: Ambiente, esqueleto e utilitários de arquivos

**Arquivos:**
- Criar: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` (só
  `[tool.pytest.ini_options]`), `gerenciador/__init__.py`,
  `gerenciador/nucleo/__init__.py`, `gerenciador/nucleo/constantes.py`,
  `gerenciador/nucleo/erros.py`, `gerenciador/nucleo/espaco.py`,
  `gerenciador/nucleo/arquivos.py`
- Teste: `tests/test_arquivos.py`, `tests/conftest.py`

**Interfaces:**
- Produz:
  - `constantes`: `WORD`, `EXCEL`, `CAD` (conjuntos de antigo:14-16), `PDF = ".pdf"`,
    `IGNORAR_DIRS = {"__pycache__", ".git"}`, `TIPOS_PADRAO = ("DE","LI","LD","PR","FO")`,
    `RELATORIO_CONVERTIDOS = "arquivos_convertidos.csv"`, `RELATORIO_APAGADOS = "arquivos_apagados.csv"`,
    `RELATORIO_IGNORADOS = "arquivos_ignorados.csv"`.
  - `erros.ErroValidacao(mensagem: str, itens: Sequence[str] = ())`, com os
    atributos `.mensagem` e `.itens: list[str]`.
  - `espaco.EspacoTrabalho` (dataclass frozen), com:
    - `raiz: Path`;
    - `@classmethod abrir(cls, raiz: Path | str) -> EspacoTrabalho`: resolve o
      caminho e levanta `ErroValidacao("Pasta não encontrada: …")` se não for
      diretório;
    - `caminho_relatorio(self, nome: str) -> Path`;
    - `eh_relatorio(self, caminho: Path) -> bool`;
    - `eh_programa(self, caminho: Path) -> bool`;
    - `relativo(self, caminho: Path) -> str`;
    - `dentro_seguro(self, caminho: Path) -> bool`: o caminho não é link
      simbólico, a raiz resolvida está em `resolve(strict=True).parents` e o
      caminho não é a própria raiz.
  - `espaco.caminhos_programa() -> frozenset[Path]`.
  - `arquivos`:
    - `listar_arquivos(espaco) -> list[Path]`: regras de antigo:264-278, e
      exclui também `eh_programa`;
    - `listar_pastas(espaco) -> list[Path]`: regras de antigo:485-489;
    - `listar_pastas_vazias(raiz: Path) -> list[Path]`: antigo:384-395;
    - `remover_pastas_vazias(raiz: Path) -> int`;
    - `separar_lista(texto: str) -> list[str]`: antigo:398-401;
    - `tipo_documento(caminho: Path) -> str | None`;
    - `tipo_limpeza(caminho: Path) -> str | None`: antigo:371-381, verbatim.

- [ ] **Passo 1: Criar o venv e instalar as dependências**

`requirements.txt`: `PySide6>=6.8`, `pywin32>=306`, `pypdf>=4`, `Send2Trash>=1.8`.
`requirements-dev.txt`: `-r requirements.txt`, `pytest>=8`, `pytest-qt>=4.4`,
`pyinstaller>=6.11`.

Rodar: `py -3.14 -m venv .venv` e depois
`.venv\Scripts\python -m pip install -r requirements-dev.txt`.

Esperado: `.venv\Scripts\python -c "import PySide6, pytestqt, PyInstaller"` sai
sem erro.

`pyproject.toml`: `testpaths = ["tests"]`. `tests/conftest.py` define
`os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")` e a fixture
`espaco(tmp_path) -> EspacoTrabalho`.

- [ ] **Passo 2: Escrever os testes que falham**

```python
def test_tipo_documento():
    assert tipo_documento(Path("NVC00410A-DE-001.docx")) == "DE"
    assert tipo_documento(Path("x-fo-12.PDF")) == "FO"
    assert tipo_documento(Path("NVC00410A.dwg")) is None
    assert tipo_documento(Path("NVC00410A-DE-001_rev2.pdf")) is None

def test_listar_arquivos_ignora_relatorios_temporarios_e_dirs(espaco):
    # cria a.docx, ~$a.docx, sub/b.pdf, .pdf_x/c.docx, __pycache__/d.py, arquivos_apagados.csv
    assert [espaco.relativo(p) for p in listar_arquivos(espaco)] == ["a.docx", "sub/b.pdf"]

def test_listar_arquivos_ignora_programa(espaco, monkeypatch):
    # monkeypatch caminhos_programa -> {raiz/"Gerenciador.exe"}; cria o arquivo
    assert listar_arquivos(espaco) == []

def test_separar_lista():
    assert separar_lista(' "Pasta\\A/" ; b,\nC ') == ["pasta/a", "b", "c"]

def test_remover_pastas_vazias_aninhadas(tmp_path):
    # a/b/c vazias, d/ com arquivo
    assert remover_pastas_vazias(tmp_path) == 3
    assert (tmp_path / "d").is_dir() and not (tmp_path / "a").exists()

def test_abrir_pasta_inexistente():
    with pytest.raises(ErroValidacao):
        EspacoTrabalho.abrir("Z:/nao/existe")
```

- [ ] **Passo 3: Rodar e confirmar a falha**

Rodar: `.venv\Scripts\python -m pytest tests/test_arquivos.py -v`
Esperado: FAIL (ImportError).

- [ ] **Passo 4: Implementar os módulos da seção Interfaces**

`relativo` usa `/` como separador. `caminhos_programa()`:
- se `getattr(sys, "frozen", False)`: devolve `{Path(sys.executable).resolve()}`;
- senão: devolve o `main.py` e o diretório `gerenciador/`, que ficam em
  `Path(__file__).resolve().parents[2]`.

`eh_programa(c)` é verdadeiro se o caminho resolvido estiver no conjunto ou se
algum item do conjunto estiver em `c.resolve().parents`.

`remover_pastas_vazias` percorre com `os.walk(topdown=False)` e chama `rmdir` em
cada pasta (exceto a raiz) que esteja vazia **no momento da visita**.

- [ ] **Passo 5: Rodar e confirmar que passa**

Rodar: `.venv\Scripts\python -m pytest tests/test_arquivos.py -v`
Esperado: tudo PASS.

---

### Tarefa 2: Relatórios CSV desativáveis

**Arquivos:**
- Criar: `gerenciador/nucleo/relatorios.py`
- Teste: `tests/test_relatorios.py`

**Interfaces:**
- Consome: `constantes`.
- Produz:
  - `CABECALHO_CONVERTIDOS = ["data_hora","arquivo_origem","arquivo_pdf","resultado","detalhe"]`;
  - `CABECALHO_APAGADOS = ["data_hora","arquivo","tipo","resultado","detalhe"]`;
  - `CABECALHO_IGNORADOS = ["arquivo","motivo"]`;
  - `agora() -> str`: `datetime.now().isoformat(timespec="seconds")`;
  - `@dataclass class Relatorio: ativo: bool = True`;
  - `Relatorio.gravar(self, caminho: Path, cabecalho: list[str], linhas: list[list[str]]) -> Path | None`:
    devolve o caminho gravado, ou `None` se estiver inativo;
  - `ler_csv(caminho: Path) -> tuple[list[str], list[list[str]]]`: levanta
    `FileNotFoundError`.

- [ ] **Passo 1: Escrever os testes que falham**

```python
def test_gravar_e_ler(tmp_path):
    c = tmp_path / "r.csv"
    assert Relatorio().gravar(c, ["a", "b"], [["1", "ç"]]) == c
    assert c.read_bytes().startswith(b"\xef\xbb\xbf")
    assert ler_csv(c) == (["a", "b"], [["1", "ç"]])

def test_inativo_nao_cria(tmp_path):
    assert Relatorio(ativo=False).gravar(tmp_path / "r.csv", ["a"], [["1"]]) is None
    assert not (tmp_path / "r.csv").exists()
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_relatorios.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar** `relatorios.py`, com a gravação de antigo:285-289 e a leitura `csv.reader(delimiter=";")`.
- [ ] **Passo 4: Rodar e confirmar que passa.** Esperado: PASS.

---

### Tarefa 3: Conversão (portar e tornar testável)

**Arquivos:**
- Criar: `gerenciador/nucleo/conversao.py`
- Teste: `tests/test_conversao_plano.py`, `tests/falsos.py` (funções de conversão falsas, no nível do módulo)

**Interfaces:**
- Consome: `constantes`, `relatorios`, `EspacoTrabalho`, `listar_arquivos`.
- Produz:
  - portados **verbatim** de antigo:19-249:
    - `normalizar_nome_aba`, `orientacao_aba`, `localizar_libreoffice`;
    - `Conversor`;
    - `validar_pdf_a4`;
    - `converter_arquivo(origem: Path, destino: Path, mecanismo: str = "auto", incluir_abas_ocultas: bool = True) -> tuple[str, str]`.
    - O `print` de `Conversor.fechar` vira `logging.warning`.
  - `@dataclass(frozen=True) class TrabalhoConversao: origem: Path; destino: Path`.
  - `@dataclass class ResultadoConversao: trabalho: TrabalhoConversao; status: str; detalhe: str; data_hora: str`.
    O status é `"convertido" | "erro" | "cancelado"`.
  - `documentos_convertiveis(espaco) -> list[Path]`: antigo:281-282.
  - `planejar_conversao(origens: list[Path]) -> list[TrabalhoConversao]`: regra de
    nomes de antigo:299-315.
  - `processos_padrao(n: int) -> int`: `min(max(1, min(2, os.cpu_count() or 1)), max(n, 1))`.
  - `executar_conversao(trabalhos, processos, ao_concluir=None, cancelado=lambda: False, funcao=converter_arquivo, criar_executor=None) -> list[ResultadoConversao]`:
    - `ao_concluir(resultado, feitos, total)`;
    - devolve os resultados na ordem de `trabalhos`;
    - `criar_executor(max_workers)`: o padrão é
      `ProcessPoolExecutor(max_workers, mp_context=multiprocessing.get_context("spawn"))`.
  - `gravar_relatorio_conversao(resultados, base_relativa: Path, relatorio: Relatorio, caminho: Path) -> Path | None`:
    os caminhos ficam relativos a `base_relativa`, com o status
    `"convertido"`, `"erro"` ou `"cancelado"`.
  - `detectar_mecanismos() -> dict[str, bool]`: chaves `"word"`, `"excel"`,
    `"libreoffice"`. Office é detectado pela existência das chaves
    `HKEY_CLASSES_ROOT\Word.Application` e `Excel.Application` via `winreg`,
    sem abrir o Office.

- [ ] **Passo 1: Escrever os testes que falham**

`tests/falsos.py`:
- `converter_ok(origem, destino, *a)` grava `b"%PDF-fake"` em `destino` e
  devolve `("ok", "")`;
- `converter_falha(origem, destino, *a)` devolve `("erro", "falhou")`.

```python
def test_planejar_nomes_duplicados(tmp_path):
    t = planejar_conversao([tmp_path/"a.docx", tmp_path/"a.xlsx", tmp_path/"b.doc"])
    assert [x.destino.name for x in t] == ["a.docx.pdf", "a.xlsx.pdf", "b.pdf"]

def test_executar_ordem_e_status(tmp_path):
    t = planejar_conversao([tmp_path/"a.docx", tmp_path/"b.docx"])
    r = executar_conversao(t, 2, funcao=converter_ok, criar_executor=ThreadPoolExecutor)
    assert [x.status for x in r] == ["convertido", "convertido"]
    assert t[0].destino.read_bytes() == b"%PDF-fake"

def test_executar_cancelado_marca_pendentes(tmp_path):
    t = planejar_conversao([tmp_path/f"{i}.docx" for i in range(5)])
    feitos = []
    r = executar_conversao(t, 1, ao_concluir=lambda res, n, tot: feitos.append(n),
                           cancelado=lambda: len(feitos) >= 1,
                           funcao=converter_ok, criar_executor=ThreadPoolExecutor)
    assert r[0].status == "convertido" and "cancelado" in {x.status for x in r[1:]}

def test_relatorio_conversao_inativo(tmp_path): ...  # Relatorio(False) -> None, sem arquivo
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_conversao_plano.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar `conversao.py`**

Algoritmo de `executar_conversao`, que não é determinado pelos testes:
1. Submete todos os trabalhos.
2. Repete `concurrent.futures.wait(pendentes, timeout=0.2, return_when=FIRST_COMPLETED)`
   até não restarem pendentes.
3. A cada volta, se `cancelado()` for verdadeiro, chama `f.cancel()` em todos os
   pendentes. Os que retornarem `True` viram `ResultadoConversao(status="cancelado", detalhe="cancelado pelo usuário")`.
4. Uma exceção de `future.result()` vira `"erro"`, e `("ok", …)` vira
   `"convertido"`.

- [ ] **Passo 4: Rodar e confirmar que passa.** Esperado: PASS.

---

### Tarefa 4: Limpeza (9 modos + Lixeira)

**Arquivos:**
- Criar: `gerenciador/nucleo/limpeza.py`
- Teste: `tests/test_limpeza.py`

**Interfaces:**
- Consome: `EspacoTrabalho`, `listar_arquivos`, `listar_pastas`,
  `listar_pastas_vazias`, `separar_lista`, `tipo_limpeza`, `Relatorio`,
  `CABECALHO_APAGADOS`, `ErroValidacao`.
- Produz:
  - `@dataclass(frozen=True) class ItemLimpeza: caminho: Path; tipo: str`.
  - `@dataclass class ResultadoLimpeza: item: ItemLimpeza; status: str; detalhe: str; data_hora: str`.
  - `candidatos(espaco) -> list[ItemLimpeza]`: modo 4, seleção individual na GUI.
  - `selecionar_todos_nao_pdf(espaco)`: modo 1, inclui os relatórios existentes
    como `"relatório CSV"`.
  - `selecionar_word_excel(espaco)`: modo 2.
  - `extensoes_disponiveis(espaco) -> list[str]` e
    `selecionar_por_extensoes(espaco, extensoes: set[str])`: modo 3.
  - `selecionar_pastas_vazias(espaco)`: modo 5, tipo `"pasta vazia"`.
  - `selecionar_cad(espaco)`: modo 6.
  - `selecionar_manter_arquivos(espaco, texto: str) -> list[ItemLimpeza]`: modo 7,
    antigo:404-450.
  - `selecionar_manter_pastas(espaco, texto: str) -> tuple[list[ItemLimpeza], list[Path]]`:
    modo 8, antigo:479-546. Devolve `(apagar, mantidas)`.
  - `selecionar_et_dt_md(espaco)`: modo 9, antigo:603-617.
  - Todos os seletores devolvem `list[ItemLimpeza]`, exceto o modo 8.
  - `enviar_lixeira(espaco, itens, relatorio, lixeira=None, ao_progresso=None) -> list[ResultadoLimpeza]`:
    - a lixeira padrão é `send2trash`;
    - aplica as checagens de antigo:681-694;
    - grava o CSV segundo antigo:695-701. Não recria o CSV se ele estiver entre
      os itens.

Cada caso de "cancelar" do script antigo vira `ErroValidacao` com as mesmas
mensagens:
- lista vazia: "Lista vazia; operação cancelada para evitar apagar todos os arquivos.";
- nomes não encontrados: lista em `.itens`;
- sem resultados no modo 9 ou 6.

Se `send2trash` não estiver instalado, `enviar_lixeira` levanta `ErroValidacao`
com a mensagem de antigo:406.

- [ ] **Passo 1: Escrever os testes que falham.** Use uma árvore fixa:
  `p/NVC1A-DE-001.docx`, `p/NVC1A-ET-002.pdf`, `p/NVC1A-MD-003.xlsx`,
  `p/modelo.dwg`, `p/x.zip`, `q/vazia/`, `r/s/t.txt`, `a.pdf`.

```python
def test_modo1_todos_nao_pdf_inclui_relatorio(espaco): ...  # sem PDFs; inclui arquivos_apagados.csv quando existe
def test_modo2_word_excel_exclui_codigos_et_dt_md(espaco): ...  # só itens com tipo "documento Word/Excel"
def test_modo3_por_extensao(espaco): ...  # {".zip"} -> só x.zip
def test_modo5_pastas_vazias(espaco): ...  # [q/vazia]
def test_modo6_cad(espaco): ...  # [p/modelo.dwg]
def test_modo7_manter_arquivos_aceita_nome_sem_extensao(espaco): ...  # "modelo, a" mantém modelo.dwg
def test_modo7_nome_nao_encontrado(espaco):
    with pytest.raises(ErroValidacao) as e:
        selecionar_manter_arquivos(espaco, "inexistente.docx")
    assert e.value.itens == ["inexistente.docx"]
def test_modo7_lista_vazia(espaco): ...  # ErroValidacao
def test_modo8_manter_pastas_preserva_pais_e_filhos(espaco): ...  # manter "r/s" -> apaga p, q; mantém r
def test_modo9_inclui_pdfs(espaco): ...  # ET pdf, MD xlsx
def test_enviar_lixeira_usa_dublê_e_grava_csv(espaco): ...  # lixeira=lista.append; CSV com status "enviado à Lixeira"
def test_enviar_lixeira_pasta_que_deixou_de_ser_vazia(espaco): ...  # status "erro"
def test_enviar_lixeira_relatorio_inativo(espaco): ...  # sem CSV
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_limpeza.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar `limpeza.py`** portando as regras das linhas citadas, sem I/O de console.
- [ ] **Passo 4: Rodar e confirmar que passa.** Esperado: PASS.

---

### Tarefa 5: Cópia por código NVC

**Arquivos:**
- Criar: `gerenciador/nucleo/copia.py`
- Teste: `tests/test_copia.py`

**Interfaces:**
- Consome: `EspacoTrabalho`, `listar_arquivos`, `separar_lista`, `ErroValidacao`.
- Produz:
  - `validar_nome_pasta(nome: str) -> str`: devolve o nome sem espaços nas
    pontas. Rejeita:
    - os casos de antigo:728-729;
    - nomes reservados do Windows (`CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`,
      `LPT1`–`LPT9`, sem diferenciar maiúsculas e minúsculas, com ou sem
      extensão);
    - nome terminado em `.` ou espaço.

    Mensagem: "Nome de pasta inválido; use apenas o nome, sem caminho."
  - `@dataclass class PlanoCopia: nome_destino: str; itens: list[tuple[Path, Path]]`.
  - `planejar_copia(espaco, texto_codigos: str, nome_destino: str) -> PlanoCopia`:
    antigo:716-783. Cada cancelamento vira `ErroValidacao`.
  - `executar_copia(plano, ao_progresso=None) -> list[tuple[Path, Path, str, str]]`:
    devolve `(origem, destino, status, detalhe)`, com o status `"copiado"`,
    `"ignorado"` ou `"erro"`. Para no primeiro erro, como antigo:792-805.

- [ ] **Passo 1: Escrever os testes que falham**

```python
@pytest.mark.parametrize("nome", ["", "a/b", "..", "CON", "com1.txt", "nome.", "x:y"])
def test_nome_pasta_invalido(nome):
    with pytest.raises(ErroValidacao):
        validar_nome_pasta(nome)

def test_nome_pasta_tira_espacos():
    assert validar_nome_pasta("  Entrega ") == "Entrega"

def test_planejar_destino(espaco): ...  # NVC00410A-DE-001.pdf -> NVC00410/A/Arquivos/NVC00410A-DE-001.pdf
def test_codigo_invalido(espaco): ...  # "ABC1" -> ErroValidacao com itens ["abc1"]
def test_destino_existente(espaco): ...  # ErroValidacao
def test_codigo_sem_arquivos(espaco): ...  # ErroValidacao
def test_executar_copia(espaco): ...  # arquivo copiado com copy2; status "copiado"
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_copia.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar `copia.py`.**
- [ ] **Passo 4: Rodar e confirmar que passa.** Esperado: PASS.

---

### Tarefa 6: Fluxo de entrega

**Arquivos:**
- Criar: `gerenciador/nucleo/fluxo.py`
- Teste: `tests/test_fluxo.py`

**Interfaces:**
- Consome:
  - `EspacoTrabalho.abrir`, `listar_arquivos`, `tipo_documento`, `remover_pastas_vazias`;
  - `validar_nome_pasta` (Tarefa 5);
  - `planejar_conversao`, `executar_conversao`, `gravar_relatorio_conversao`,
    `converter_arquivo` (Tarefa 3);
  - `Relatorio`, `CABECALHO_IGNORADOS`, `RELATORIO_*`, `TIPOS_PADRAO`, `ErroValidacao`.
- Produz:
  - `separar_tipos(texto: str) -> frozenset[str]`: separa por `[;,\s]+`, converte
    para maiúsculas e exige `^[A-Z]{2}$`. Em caso de falha, levanta
    `ErroValidacao("Tipos inválidos", itens)` ou `ErroValidacao("Informe ao menos um tipo.")`.
  - `@dataclass class ParametrosFluxo: base: Path; nome_destino: str; tipos: frozenset[str]; converter: bool = True; processos: int = 2`.
  - `@dataclass class ItemFluxo: origem: Path; acao: str; motivo: str; destino: Path | None`:
    - a ação é `"copiar" | "converter" | "ignorar"`;
    - `destino` é onde a cópia fica na pasta nova (`None` para ignorados).
  - `@dataclass class PlanoFluxo`, com os campos:
    - `parametros`;
    - `base: Path`;
    - `destino_raiz: Path`;
    - `itens: list[ItemFluxo]`;
    - `trabalhos: list[TrabalhoConversao]`;
    - `conflitos: list[Path]`.

    E as propriedades `a_copiar`, `a_converter` e `ignorados`, que devolvem
    `list[ItemFluxo]`.
  - `@dataclass class ResumoFluxo`, com os campos:
    - `destino_raiz: Path`;
    - `copiados: int`;
    - `convertidos: int`;
    - `ignorados: int`;
    - `erros: list[tuple[str, str]]`;
    - `cancelado: bool`.
  - `planejar_fluxo(p: ParametrosFluxo) -> PlanoFluxo`.
  - `executar_fluxo(plano, relatorio, ao_progresso=None, ao_log=None, cancelado=lambda: False, funcao_conversao=converter_arquivo, criar_executor=None) -> ResumoFluxo`:
    - `ao_progresso(etapa: str, atual: int, total: int)`, com a etapa
      `"Copiando"`, `"Convertendo"` ou `"Finalizando"`;
    - `ao_log(msg: str)`.

Classificação, que segue a especificação:

| Situação | Ação | Motivo |
|---|---|---|
| Tipo é `None` | ignorar | `"sem código de tipo"` |
| Tipo fora da lista | ignorar | `f"tipo {t} não permitido"` |
| Sufixo `.pdf` | copiar | — |
| Sufixo em WORD\|EXCEL e `converter=True` | converter | — |
| Sufixo em WORD\|EXCEL e `converter=False` | copiar | `"conversão desligada"` |
| Outro sufixo | ignorar | `f"formato {sufixo} não aceito"` |

Os sufixos são comparados com `casefold`.

Os `trabalhos` vêm de `planejar_conversao` sobre os `destino` dos itens
"converter". Um `conflito` é um trabalho cujo `destino` coincide (casefold) com o
`destino` de um item "copiar".

- [ ] **Passo 1: Escrever os testes que falham.** Use a base
  `obra/a/X-DE-001.pdf`, `obra/a/X-LI-002.docx`, `obra/a/X-ET-003.pdf`,
  `obra/a/X-DE-004.dwg`, `obra/b/foto.jpg`, `obra/b/pacote.zip`,
  `obra/c/X-FO-005.XLSX`, `obra/c/X-PR-006.PDF`. Os testes usam
  `funcao_conversao=falsos.converter_ok` e `criar_executor=ThreadPoolExecutor`.

```python
def test_separar_tipos_baguncado():
    assert separar_tipos("de; li ,pr\nfo") == {"DE", "LI", "PR", "FO"}

@pytest.mark.parametrize("t", ["", "D E", "DEX", "1A"])
def test_separar_tipos_invalido(t): ...  # ErroValidacao

def test_classificacao(base): ...  # copiar: X-DE-001.pdf, X-PR-006.PDF; converter: X-LI-002.docx, X-FO-005.XLSX;
                                  # ignorar com motivos: X-ET-003 (tipo ET não permitido), X-DE-004.dwg (formato .dwg),
                                  # foto.jpg e pacote.zip (sem código de tipo)
def test_destino_existente_ou_dentro_da_base(base): ...  # ErroValidacao; nome "obra/x" também
def test_base_inexistente(tmp_path): ...  # ErroValidacao

def test_executar_resultado_final(base):
    resumo = executar_fluxo(plano, Relatorio(), funcao_conversao=converter_ok, criar_executor=ThreadPoolExecutor)
    arquivos = sorted(relativos(plano.destino_raiz))
    assert arquivos == ["a/X-DE-001.pdf", "a/X-LI-002.pdf", "arquivos_convertidos.csv",
                        "arquivos_ignorados.csv", "c/X-FO-005.pdf", "c/X-PR-006.PDF"]
    assert not (plano.destino_raiz / "b").exists()      # pasta vazia removida
    assert (resumo.copiados, resumo.convertidos, resumo.ignorados) == (2, 2, 4)

def test_base_intacta(base): ...  # snapshot (caminho, tamanho, mtime_ns) antes == depois
def test_falha_de_conversao_mantem_original(base): ...  # converter_falha -> a/X-LI-002.docx existe; erro no resumo
def test_cancelar_mantem_pendentes(base): ...  # cancelado após 1ª conversão, processos=1 -> resumo.cancelado; .docx/.xlsx pendente existe
def test_erro_ao_copiar_continua(base, monkeypatch): ...  # shutil.copy2 levanta PermissionError só para X-DE-001.pdf -> erro registrado, demais copiados
def test_relatorios_desligados(base): ...  # Relatorio(False) -> nenhum .csv na pasta nova
def test_conversao_desligada_copia_originais(base): ...  # converter=False -> .docx e .XLSX copiados sem conversão
def test_conflito_detectado(base): ...  # adiciona obra/a/X-LI-002.pdf -> plano.conflitos == [destino/a/X-LI-002.pdf]
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_fluxo.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar `fluxo.py`**

Ordem de `executar_fluxo`:
1. `destino_raiz.mkdir()`, sem `exist_ok`. Um `FileExistsError` vira `ErroValidacao`.
2. Copia cada item "copiar" e "converter" com `copy2`, criando os pais. Um
   `OSError` em um arquivo vai para `erros`, e esse item é retirado de
   `trabalhos`. Entre arquivos, verifica `cancelado()`.
3. Se `converter`, roda `executar_conversao` nos trabalhos restantes. Para cada
   `"convertido"`, confere `destino_raiz in origem.resolve().parents` e faz
   `origem.unlink()`.
4. Roda `remover_pastas_vazias(destino_raiz)`.
5. Grava os relatórios: `arquivos_convertidos.csv` (relativo a `destino_raiz`) e
   `arquivos_ignorados.csv` (relativo à base, com o motivo), os dois em
   `destino_raiz`.

- [ ] **Passo 4: Rodar a suíte inteira e confirmar que passa.** Rodar: `.venv\Scripts\python -m pytest -v`. Esperado: tudo PASS.

---

### Tarefa 7: Base da GUI (app, janela, trabalhador, componentes)

**Arquivos:**
- Criar:
  - `main.py`;
  - `gerenciador/gui/__init__.py`;
  - `gerenciador/gui/app.py`;
  - `gerenciador/gui/configuracoes.py`;
  - `gerenciador/gui/trabalhador.py`;
  - `gerenciador/gui/seletor_pasta.py`;
  - `gerenciador/gui/tabela_itens.py`;
  - `gerenciador/gui/janela_principal.py`.
- Teste: `tests/test_gui_base.py`

**Interfaces:**
- Consome: `detectar_mecanismos` e `ErroValidacao`.
- Produz:
  - `main.py`: `multiprocessing.freeze_support()`, depois `from gerenciador.gui.app import executar` e `sys.exit(executar())`.
  - `app.executar() -> int`: cria a `QApplication` com o nome "Gerenciador de Documentos" e mostra a `JanelaPrincipal`.
  - `Configuracoes(qsettings: QSettings | None = None)`, com:
    - `valor(chave: str, padrao)`;
    - `definir(chave: str, valor)`;
    - a propriedade `gerar_relatorios: bool` (padrão `True`).
  - `ContextoTarefa`, com:
    - `progresso(etapa: str, atual: int, total: int)`;
    - `log(msg: str)`;
    - `cancelado() -> bool`.
  - `Trabalhador(QObject)`, com:
    - os sinais `progresso(str, int, int)`, `log(str)`, `concluido(object)` e
      `falhou(str, list)`;
    - `cancelar()`.

    `ErroValidacao` emite `falhou(mensagem, itens)`. Outras exceções emitem
    `falhou(str(e), [traceback resumido])`.
  - `executar_em_segundo_plano(pai: QObject, funcao: Callable[[ContextoTarefa], object]) -> Trabalhador`:
    usa `QThread` e guarda a referência até terminar.
  - `SeletorPasta(QWidget)`, com:
    - `__init__(rotulo: str, chave_config: str, configuracoes)`;
    - o sinal `pasta_alterada(Path)`;
    - a propriedade `pasta -> Path | None`.

    Lembra a última pasta e abre `QFileDialog.getExistingDirectory`.
  - `TabelaItens(QTableView)`, com:
    - `__init__(colunas: list[str], marcavel: bool = False)`;
    - `definir_linhas(linhas: list[list[str]], dados: list[object])`;
    - `marcados() -> list[object]`;
    - `marcar_todos(bool)`;
    - `definir_status(indice: int, texto: str, erro: bool = False)`;
    - `filtrar(texto: str)`.

    Usa `QStandardItemModel` com `QSortFilterProxyModel`.
  - `JanelaPrincipal(QMainWindow)`, com:
    - um `QTabWidget` com as abas na ordem "Fluxo de entrega", "Converter",
      "Limpeza", "Copiar por código" e "Relatórios" (as Tarefas 8–10 trocam os
      espaços reservados);
    - na barra de status, `QCheckBox("Gerar relatórios CSV")` ligada a
      `Configuracoes.gerar_relatorios` e o rótulo de mecanismos
      ("Word ✓ Excel ✓ LibreOffice ✗");
    - `relatorio() -> Relatorio`, que as abas usam.

- [ ] **Passo 1: Escrever os testes que falham (pytest-qt)**

```python
def test_janela_tem_abas_na_ordem(qtbot, config_temp):
    j = JanelaPrincipal(config_temp); qtbot.addWidget(j)
    assert [j.abas.tabText(i) for i in range(j.abas.count())] == [
        "Fluxo de entrega", "Converter", "Limpeza", "Copiar por código", "Relatórios"]

def test_opcao_relatorios_persiste(qtbot, config_temp):
    j = JanelaPrincipal(config_temp); j.caixa_relatorios.setChecked(False)
    assert config_temp.gerar_relatorios is False and j.relatorio().ativo is False

def test_trabalhador_conclui_e_falha(qtbot): ...  # funcao que devolve 42 -> concluido(42); que levanta ErroValidacao("x",["a"]) -> falhou("x",["a"])
def test_trabalhador_cancelar(qtbot): ...  # funcao que espera ctx.cancelado() -> termina após cancelar()
def test_tabela_marcados(qtbot): ...  # marcavel=True, marcar_todos(True) -> marcados()==dados
```

A fixture `config_temp` usa `QSettings(str(tmp_path/"c.ini"), QSettings.IniFormat)`.

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_gui_base.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar os módulos da seção Interfaces.**
- [ ] **Passo 4: Rodar e confirmar que passa.** Também rode `.venv\Scripts\python main.py` e confira que a janela abre com as 5 abas e a barra de status. Feche a janela.

---

### Tarefa 8: Aba "Fluxo de entrega"

**Arquivos:**
- Criar: `gerenciador/gui/aba_fluxo.py`
- Modificar: `gerenciador/gui/janela_principal.py` (troca o espaço reservado da 1ª aba)
- Teste: `tests/test_gui_fluxo.py`

**Interfaces:**
- Consome:
  - `ParametrosFluxo`, `planejar_fluxo`, `executar_fluxo`, `separar_tipos`, `processos_padrao`, `TIPOS_PADRAO`;
  - `SeletorPasta`, `TabelaItens`, `executar_em_segundo_plano`, `Configuracoes`;
  - `JanelaPrincipal.relatorio()`.
- Produz: `AbaFluxo(QWidget)`, com:
  - `__init__(configuracoes, obter_relatorio: Callable[[], Relatorio], funcao_conversao=converter_arquivo, criar_executor=None)`.
    Os dois últimos parâmetros existem para os testes.
  - Os widgets públicos:
    - `seletor_base`;
    - `campo_nome`;
    - `rotulo_destino`;
    - `campo_tipos`;
    - `caixa_converter`;
    - `campo_processos` (`QSpinBox` 1–16);
    - `botao_analisar`;
    - `rotulo_resumo`;
    - `tabela`;
    - `filtro_acao` (Todos / Copiar / Converter / Ignorar);
    - `barra`;
    - `botao_cancelar`;
    - `botao_executar`;
    - `botao_abrir_pasta`;
    - `log` (`QPlainTextEdit` somente leitura).

Comportamento, conforme o desenho da especificação:
- **Rótulo de destino:** `rotulo_destino` mostra "→ será criada: <base.parent/nome>"
  enquanto o usuário digita.
- **Analisar:** "Analisar" roda `planejar_fluxo` em segundo plano. Ao concluir:
  - preenche a tabela com as colunas "Arquivo" (relativo à base), "Ação" e
    "Motivo";
  - preenche o resumo: "N PDFs a copiar · N Word/Excel a converter · N fora da
    entrega", mais "· N conflitos de PDF" se houver;
  - habilita "Executar fluxo".
- **Invalidação:** qualquer mudança de parâmetro desabilita "Executar fluxo" até
  uma nova análise.
- **Erro de validação:** `falhou` mostra um `QMessageBox.warning` com a mensagem e
  os itens.
- **Executar fluxo:**
  - mostra `QMessageBox.question` com os números do resumo e o caminho da pasta
    nova; o padrão é "Não";
  - ao aceitar, bloqueia os campos, mostra a barra e o Cancelar, e roda
    `executar_fluxo` com `obter_relatorio()`;
  - as mensagens de `ao_log` vão para `log`.
- **Fim da execução:** mostra o resumo final ("Concluído" ou "Interrompido" ·
  copiados · convertidos · erros) e habilita "Abrir pasta"
  (`QDesktopServices.openUrl`). Os erros vão para o log.
- **Memória dos campos:** base, nome, tipos, converter e processos são salvos em
  `Configuracoes` com as chaves `fluxo/base`, `fluxo/nome`, `fluxo/tipos`,
  `fluxo/converter` e `fluxo/processos`.

- [ ] **Passo 1: Escrever os testes que falham**

```python
def test_executar_desabilitado_ate_analisar(qtbot, aba, base): ...
def test_analisar_preenche_resumo(qtbot, aba, base):
    # define base/nome; clica analisar; qtbot.waitUntil(lambda: aba.botao_executar.isEnabled())
    assert "2 PDFs a copiar" in aba.rotulo_resumo.text()
def test_mudar_parametro_invalida_analise(qtbot, aba, base): ...
def test_executar_fluxo_completo(qtbot, aba, base, monkeypatch):
    # monkeypatch QMessageBox.question -> Yes; clica executar; waitUntil botao_abrir_pasta habilitado
    assert (base.parent / "Entrega" / "a" / "X-LI-002.pdf").exists()
def test_nome_invalido_mostra_aviso(qtbot, aba, base, monkeypatch): ...  # QMessageBox.warning chamado; nada criado
```

A fixture `aba` constrói a `AbaFluxo` com `funcao_conversao=falsos.converter_ok`
e `criar_executor=ThreadPoolExecutor`. A fixture `base` reaproveita a árvore da
Tarefa 6; mova-a para `tests/conftest.py`.

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_gui_fluxo.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar `aba_fluxo.py`** e ligá-la na janela.
- [ ] **Passo 4: Rodar a suíte inteira e confirmar que passa.**

---

### Tarefa 9: Abas Converter, Copiar por código e Relatórios

**Arquivos:**
- Criar:
  - `gerenciador/gui/aba_conversao.py`;
  - `gerenciador/gui/aba_copia.py`;
  - `gerenciador/gui/aba_relatorios.py`.
- Modificar: `gerenciador/gui/janela_principal.py`
- Teste: `tests/test_gui_avulsas.py`

**Interfaces:**
- Consome: `conversao.*`, `copia.*`, `ler_csv`, `RELATORIO_*` e os componentes da
  Tarefa 7.
- Produz:
  - `AbaConversao(QWidget)`:
    - `__init__(configuracoes, obter_relatorio, funcao=converter_arquivo, criar_executor=None)`;
    - chave do seletor `avulso/pasta`;
    - "Analisar" lista as colunas Origem, PDF de destino e Status, e ajusta o
      `QSpinBox` de processos para `1..len(trabalhos)`, com o padrão
      `processos_padrao`;
    - "Iniciar" pede confirmação com o texto de antigo:331-332, depois mostra o
      progresso e atualiza o status de cada linha;
    - "Cancelar" interrompe os pendentes;
    - ao fim, grava o CSV em `caminho_relatorio(RELATORIO_CONVERTIDOS)`.
  - `AbaCopia(QWidget)`:
    - `__init__(configuracoes)`;
    - uma caixa de códigos com a instrução de antigo:717-719 e o campo "Nome da
      pasta final";
    - "Gerar prévia" mostra a tabela Origem → Destino, e os erros aparecem num
      `QLabel` vermelho acima dela, com os itens;
    - "Copiar" pede confirmação e depois mostra o status por linha.
  - `AbaRelatorios(QWidget)`:
    - `__init__(configuracoes)`;
    - um `QComboBox` com Convertidos, Apagados e Ignorados (fluxo), uma tabela
      e os botões "Atualizar" e "Abrir no Excel" (`os.startfile`);
    - um arquivo ausente mostra "O relatório ainda não foi gerado.".

As três abas compartilham a chave `avulso/pasta`, para manter a mesma pasta de
trabalho entre elas.

- [ ] **Passo 1: Escrever os testes que falham**

```python
def test_conversao_analisa_e_converte(qtbot, espaco, monkeypatch): ...  # a.docx -> status "convertido"; CSV criado
def test_conversao_sem_relatorio(qtbot, espaco, monkeypatch): ...  # obter_relatorio -> Relatorio(False); sem CSV
def test_copia_erro_validacao_mostra_itens(qtbot, espaco): ...  # código "abc" -> rótulo contém "abc"; botão Copiar desabilitado
def test_copia_executa(qtbot, espaco, monkeypatch): ...
def test_relatorios_ausente_e_presente(qtbot, espaco): ...
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_gui_avulsas.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar** as três abas e ligá-las na janela.
- [ ] **Passo 4: Rodar a suíte inteira e confirmar que passa.**

---

### Tarefa 10: Aba Limpeza

**Arquivos:**
- Criar: `gerenciador/gui/aba_limpeza.py`
- Modificar: `gerenciador/gui/janela_principal.py`
- Teste: `tests/test_gui_limpeza.py`

**Interfaces:**
- Consome: `limpeza.*` (Tarefa 4) e os componentes da Tarefa 7.
- Produz: `AbaLimpeza(QWidget)`, com:
  - `__init__(configuracoes, obter_relatorio, lixeira=None)`;
  - os widgets públicos `lista_modos` (`QListWidget` com os 9 textos de
    antigo:584-592, na mesma ordem), `area_parametros` (`QStackedWidget`),
    `tabela` (`TabelaItens` marcável) e `botao_enviar`.

Cada modo mostra na `area_parametros`:

| Modo | Parâmetros |
|---|---|
| 1, 2, 5, 6, 9 | nenhum; a prévia é gerada ao selecionar |
| 3 | caixas de seleção por extensão, de `extensoes_disponiveis`, e "Gerar prévia" |
| 4 | todos os `candidatos` desmarcados e "Marcar todos" |
| 7, 8 | `QPlainTextEdit` com a instrução de antigo:410-412 / 495-498 e "Gerar prévia" |

No modo 8, a tabela mostra também as pastas mantidas, com a ação "MANTER", não
marcáveis.

Nos modos 1–3 e 5–9, todos os itens da prévia vêm marcados. O usuário pode
desmarcar.

- **Enviar:** `botao_enviar` mostra "Enviar N itens à Lixeira", onde N é o número
  de marcados. Ele pede `QMessageBox.question` (padrão "Não"), depois chama
  `enviar_lixeira` em segundo plano e atualiza o status por linha.
- **Erros:** `ErroValidacao` aparece num rótulo vermelho com os itens, e o botão
  fica desabilitado.

- [ ] **Passo 1: Escrever os testes que falham**

```python
def test_modos_na_ordem(qtbot, aba_limpeza): ...
def test_modo6_previa_e_envio(qtbot, aba_limpeza, espaco, monkeypatch):
    # lixeira=dublê; seleciona modo 6; Yes na confirmação -> dublê recebeu modelo.dwg; status "enviado à Lixeira"
def test_desmarcar_item_nao_envia(qtbot, aba_limpeza, espaco, monkeypatch): ...
def test_modo7_nao_encontrado_bloqueia(qtbot, aba_limpeza, espaco): ...
def test_cancelar_confirmacao_nao_envia(qtbot, aba_limpeza, espaco, monkeypatch): ...  # No -> dublê vazio
```

- [ ] **Passo 2: Rodar e confirmar a falha.** Rodar: `.venv\Scripts\python -m pytest tests/test_gui_limpeza.py -v`. Esperado: FAIL.
- [ ] **Passo 3: Implementar** `aba_limpeza.py` e ligá-la na janela.
- [ ] **Passo 4: Rodar a suíte inteira e confirmar que passa.**

---

### Tarefa 11: Executável, README e verificação real

**Arquivos:**
- Criar: `gerenciador.spec`, `README.md`

**Interfaces:**
- Consome: `main.py`.
- Produz: `dist/GerenciadorDocumentos.exe`.

- [ ] **Passo 1: Escrever `gerenciador.spec`**

O spec usa:
- `Analysis(["main.py"], hiddenimports=["win32com.client", "pythoncom", "pywintypes", "pypdf", "send2trash"])`;
- `excludes` com os módulos Qt não usados (`PySide6.QtWebEngineCore`,
  `QtQml`, `QtQuick`, `Qt3D*`, `QtMultimedia` e similares);
- `EXE(..., name="GerenciadorDocumentos", console=False, onefile)`, ou seja, sem
  `COLLECT`.

- [ ] **Passo 2: Gerar o executável**

Rodar: `.venv\Scripts\python -m PyInstaller gerenciador.spec --noconfirm`
Esperado: `dist\GerenciadorDocumentos.exe` existe.

- [ ] **Passo 3: Verificação manual com Office real.** Monte uma pasta de teste
  fora do projeto com:
  - `.docx` e `.xlsx` reais com nomes `T-DE-001` e `T-LI-002`;
  - um PDF `T-PR-003.pdf`;
  - um `T-ET-004.pdf`;
  - um `.zip`;
  - uma subpasta só com `.dwg`.

  Rode o fluxo pelo `.exe`, copiado para outra pasta, como o Pedro vai usar. Confira:
  - a pasta nova contém só `T-DE-001.pdf`, `T-LI-002.pdf`, `T-PR-003.pdf` e os 2 CSV;
  - a pasta base não mudou;
  - durante a conversão com 2 processos, **não abre nenhuma janela extra** do
    programa;
  - com "Gerar relatórios CSV" desligado, não há CSV.

  Teste também uma conversão avulsa e uma limpeza avulsa (modo 6) na pasta de
  teste.

- [ ] **Passo 4: Escrever o `README.md`** com estes tópicos:
  - o que o programa faz;
  - como rodar a partir do código (`.venv\Scripts\python main.py`);
  - como testar (`python -m pytest`);
  - como gerar o `.exe`;
  - requisitos na máquina de uso: Microsoft Office para Excel e, opcionalmente,
    LibreOffice.

- [ ] **Passo 5: Rodar a suíte final.** Rodar: `.venv\Scripts\python -m pytest -v`. Esperado: tudo PASS.
