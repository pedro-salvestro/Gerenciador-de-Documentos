# Interface gráfica do Gerenciador de Documentos — design

Data: 2026-11-17 (revisão 2: fluxo automatizado e relatórios opcionais)

## Intenção

Hoje o Gerenciador de Documentos (`gerenciador_documentos.py`) é um menu de
terminal que trabalha na pasta onde o script está. O usuário repete sempre a
mesma tarefa: preparar uma **pasta de entrega** só com os PDFs dos tipos de
documento relevantes. O objetivo é:

1. **Automatizar essa tarefa** num fluxo único: escolher a pasta base, o nome da
   pasta nova, os tipos e então executar. A pasta base nunca é alterada.
2. Ter interface gráfica (janela) no lugar do menu de terminal, mantendo as
   funções avulsas atuais para uso manual.
3. Permitir **escolher a pasta de trabalho no programa**. O `.exe` pode ficar em
   qualquer lugar.
4. Permitir **desativar os relatórios CSV**.
5. Distribuir como **executável Windows** (`.exe`) que roda sem Python instalado.
6. Reestruturar o código com boas práticas: lógica separada da interface,
   dividida em módulos e testável.

## Objetivos

### Fluxo de entrega (aba principal)

Entrada: pasta base, nome da pasta nova e tipos permitidos (padrão: DE, LI, LD,
PR, FO, editável). Resultado: uma pasta nova, ao lado da base, que contém
**apenas PDFs dos tipos permitidos**, na mesma estrutura de subpastas da base.

Regras de quais arquivos vão para a entrega:

- **Tipo do arquivo:** é o código do nome no padrão `...-XX-<número>`, ao fim do
  nome sem extensão (mesma forma da regra atual `-(ET|DT|MD)-\d+$`). Exemplo:
  `NVC00410A-DE-001.docx` tem tipo DE. A comparação ignora maiúsculas e
  minúsculas.
- **PDF de tipo permitido:** é mantido como está.
- **Word/Excel de tipo permitido:** é convertido para PDF, e o original não fica
  na entrega.
- **Todo o resto não vai para a entrega:**
  - arquivos sem código de tipo;
  - arquivos de tipo não permitido;
  - arquivos de tipo permitido em outro formato, como `-DE-001.dwg`;
  - `.zip`;
  - pastas que ficariam vazias.

### Funções avulsas (demais abas)

Mantidas com **as mesmas regras de negócio** de hoje:

- converter Word/Excel para PDF;
- os 9 modos de envio à Lixeira;
- ver os relatórios;
- copiar por código NVC.

Todas as salvaguardas atuais continuam valendo:

- prévia antes de agir e confirmação explícita;
- Lixeira em vez de exclusão definitiva;
- checagem de caminho seguro;
- cancelar quando há nome não encontrado;
- não sobrescrever destinos de cópia;
- substituir o PDF só depois de sucesso;
- validação A4 do Excel.

### Geral

- Opção "Gerar relatórios CSV", lembrada entre usos, que vale para o fluxo e para
  as funções avulsas.
- Operações longas sem travar a janela, com barra de progresso e log ao vivo.

## Fora do escopo

- Editor genérico de fluxos (adicionar, remover ou reordenar passos
  arbitrários). O fluxo é fixo e só os parâmetros são editáveis.
- Mudar as regras das funções avulsas, o formato dos CSV ou os critérios de
  conversão.
- `.exe` para macOS/Linux, instalador e atualização automática.

## O que tornaria isto um fracasso mesmo funcionando

- O fluxo alterar ou apagar **qualquer coisa na pasta base**.
- A entrega conter um arquivo fora da regra, ou faltar um PDF de tipo permitido
  sem que o resumo final aponte o motivo.
- O fluxo sobrescrever uma pasta de entrega que já existe.
- Uma função avulsa apagar algo sem prévia e confirmação, ou enviar à Lixeira o
  próprio `.exe`.
- A janela congelar durante a conversão, ou cada processo de conversão abrir uma
  janela nova do programa.

## Restrições

- Windows 11, Python 3.14. pywin32, pypdf e Send2Trash já estão instalados.
  Faltam PySide6 e PyInstaller.
- O Excel é obrigatório para planilhas. O Word usa Office, com LibreOffice como
  alternativa (comportamento atual).
- Objetos COM ficam restritos ao processo filho (comportamento atual).

## Abordagens consideradas

### Biblioteca de interface

| Abordagem | Prós | Contras |
|---|---|---|
| **PySide6 (Qt)** — escolhida pelo usuário | Visual moderno; tabelas com caixas de seleção; threads e progresso robustos | `.exe` maior (~60–90 MB) |
| Tkinter (ttk) | Já vem no Python; `.exe` pequeno | Visual datado; listas e tabelas mais trabalhosas |
| Web (Flet/Electron) | Visual livre | Pesado; sem ganho para ferramenta desktop interna |

### Como montar a pasta de entrega

| Abordagem | Prós | Contras |
|---|---|---|
| Copiar a base inteira e depois apagar (passos literais do usuário) | Espelha o processo manual | Copia gigabytes que serão apagados; lento; muitas exclusões |
| **Copiar só o que sobrevive e converter na cópia** — escolhida (decisão do Claude) | Mesmo resultado final; muito mais rápido; nada é apagado da base nem há exclusões em massa | O passo "apagar" deixa de existir como etapa visível; a prévia mostra o que fica de fora |

Com essa escolha, a única exclusão na pasta nova é a do Word/Excel original
depois de convertido. Essa exclusão é **definitiva**, sem Lixeira, porque o
arquivo é uma cópia e o original está intacto na base.

## Decisões do usuário

- O usuário escolhe a pasta de trabalho no programa. O `.exe` pode ficar em
  qualquer lugar.
- Interface em PySide6, com código reestruturado em módulos.
- A aba principal escolhe e executa o fluxo, para automatizar a tarefa.
- Os relatórios podem ser desativados.
- O fluxo trabalha numa **pasta nova, com nome escolhido pelo usuário**. A base
  não é alterada.
- A entrega contém só PDFs dos tipos DE, LI, LD, PR e FO. Os PDFs existentes
  desses tipos são mantidos, e os Word/Excel desses tipos são convertidos.
- Arquivos sem código de tipo, de outros tipos ou de outros formatos (inclusive
  `.dwg` de tipo permitido) e `.zip` ficam de fora. Pastas vazias são removidas.

## Decisões do Claude (o usuário pode corrigir)

- **Local da pasta nova:** fica ao lado da base, com o nome digitado. Por exemplo,
  `Projetos\Obra X` com o nome "Obra X - Entrega" gera
  `Projetos\Obra X - Entrega`. Se ela já existir, o fluxo para antes de começar.
- **Confirmação:** uma só, no início, com um resumo (quantos PDFs serão copiados,
  quantos Word/Excel serão convertidos, quantos arquivos ficam de fora) e a lista
  detalhada consultável. Depois disso, tudo roda sem novas perguntas.
- **Falha de conversão:** o Word/Excel original **fica** na pasta nova, para não
  se perder, e o arquivo aparece como erro no resumo final e no relatório.
- **Conflito de PDF:** se existirem `X-DE-001.docx` e `X-DE-001.pdf`, o PDF gerado
  da conversão substitui o PDF copiado, que é o comportamento atual da conversão.
  O resumo inicial lista esses casos.
- **Tipos permitidos:** a lista fica num campo de texto, com o padrão
  "DE, LI, LD, PR, FO", e a última lista usada é lembrada.
- **Ligar e desligar passos:** cada passo do fluxo pode ser desligado, por
  exemplo para só montar a entrega sem converter. Por padrão, todos ficam
  ligados.
- **Relatórios na pasta nova:** quando ligados, os relatórios do fluxo
  (`arquivos_convertidos.csv` e `arquivos_ignorados.csv`, este com o que ficou de
  fora) são gravados na pasta nova. Nas funções avulsas, continuam na pasta de
  trabalho, como hoje.
- **Proteção do programa:** as funções avulsas nunca listam o próprio `.exe` nem
  o código-fonte, em nenhum modo. Hoje, o modo "todos os não PDF" incluiria o
  próprio script.

## Design

### Estrutura de arquivos

```
Gerenciador de Documentos/
  main.py                      # ponto de entrada (freeze_support + abre a GUI)
  gerenciador/
    __init__.py
    nucleo/                    # sem Qt, sem input()/print(); testável
      __init__.py
      constantes.py            # extensões WORD/EXCEL/CAD, nomes de relatório, IGNORAR_DIRS
      espaco.py                # EspacoTrabalho: raiz + caminhos protegidos
      arquivos.py              # listar_arquivos, listar_pastas, pastas vazias, separar_lista, tipo_documento
      relatorios.py            # Relatorio (pode estar desativado), gravar/ler CSV
      conversao.py             # Conversor, validar_pdf_a4, converter_arquivo, planejar/executar
      fluxo.py                 # ParametrosFluxo, planejar_fluxo -> PlanoFluxo, executar_fluxo
      limpeza.py               # 9 seletores -> Previa; enviar_lixeira
      copia.py                 # planejar_copia -> PlanoCopia; executar_copia
      erros.py                 # ErroValidacao (mensagem + itens)
    gui/
      __init__.py
      app.py                   # QApplication, configurações (QSettings)
      janela_principal.py      # abas + opção de relatórios + barra de status
      trabalhador.py           # execução em segundo plano (QThread) com sinais
      tabela_itens.py          # tabela reutilizável com caixas de seleção
      seletor_pasta.py         # campo + botão "Escolher…"
      aba_fluxo.py             # aba principal
      aba_conversao.py
      aba_limpeza.py
      aba_copia.py
      aba_relatorios.py
  tests/
    test_arquivos.py, test_fluxo.py, test_limpeza.py, test_copia.py,
    test_conversao_plano.py, test_relatorios.py
  requirements.txt             # PySide6, pywin32, pypdf, Send2Trash
  requirements-dev.txt         # pytest, pyinstaller
  gerenciador.spec             # configuração do PyInstaller
  README.md                    # como rodar, testar e gerar o .exe
```

### Núcleo: separar "planejar" de "executar"

Toda operação longa ou destrutiva tem duas etapas, sem `input()` nem `print()`:

- **Planejar:** recebe a pasta e os parâmetros e devolve uma prévia (os itens
  com tipo, destino e motivo). Se algo inviabiliza a operação, levanta
  `ErroValidacao` com a mensagem e a lista de itens.
- **Executar:** recebe o plano confirmado, informa o progresso por callback,
  respeita o cancelamento e devolve os resultados por item.

`Relatorio` recebe `ativo: bool`. Quando está desativado, as gravações não fazem
nada, então as funções de execução não precisam de `if` espalhado.

`EspacoTrabalho(raiz)` substitui o `RAIZ` global e sabe quais caminhos são
protegidos: os relatórios, `sys.executable` quando está empacotado, e
`main.py`/`gerenciador/` quando a pasta é a do código-fonte.

### Fluxo de entrega

`ParametrosFluxo`: base, nome_destino, tipos, converter (bool) e processos.

`planejar_fluxo(parametros) -> PlanoFluxo`:
1. Valida o nome da pasta (as mesmas regras do nome de pasta da cópia atual).
   Garante que `destino = base.parent / nome` não existe e não fica dentro da
   base.
2. Percorre a base com `listar_arquivos` e classifica cada arquivo em `copiar`
   (PDF de tipo permitido), `converter` (Word/Excel de tipo permitido) ou
   `ignorar` (com motivo: sem tipo, tipo não permitido, formato não aceito).
3. Calcula o PDF de destino de cada conversão com a regra atual de nomes
   duplicados e detecta os conflitos com PDFs copiados.

`executar_fluxo(plano, relatorio, ao_progresso, cancelado)`:
1. Cria a pasta destino e copia (`copy2`) os PDFs e os Word/Excel do plano,
   recriando as subpastas.
2. Converte os Word/Excel **dentro da pasta destino**, reaproveitando
   `executar_conversao` com o `ProcessPoolExecutor` atual.
3. Para cada conversão bem-sucedida, apaga o Word/Excel copiado. Antes de apagar,
   confere que o caminho está dentro da pasta destino.
4. Remove as pastas vazias da pasta destino.
5. Grava os relatórios (se ativos) e devolve o resumo: copiados, convertidos,
   erros, ignorados e cancelados.

Cancelamento: os itens pendentes não iniciam. A pasta nova fica com o que já foi
feito, e o resumo indica que o fluxo foi interrompido. Nada é desfeito, porque a
base está intacta e basta apagar a pasta nova e rodar de novo.

A base é somente leitura no fluxo. Os testes verificam isso comparando a
árvore da base antes e depois.

### Conversão (função avulsa e reutilizada pelo fluxo)

- `planejar_conversao(espaco)` monta os pares (origem, destino) com a regra atual
  de duplicados.
- `executar_conversao(trabalhos, processos, ao_concluir_item, cancelado)` usa o
  `ProcessPoolExecutor` com `spawn`, como hoje.
- Cancelar não inicia os itens pendentes. Os itens em andamento terminam, para
  não deixar o Excel órfão.
- `main.py` chama `multiprocessing.freeze_support()` antes de importar o Qt.

### Interface

```
┌──────────────────────────────────────────────────────────────────┐
│ [Fluxo de entrega] [Converter] [Limpeza] [Copiar por código] [Relatórios] │
├──────────────────────────────────────────────────────────────────┤
│ Pasta base:      [C:\Projetos\Obra X                ] [Escolher…] │
│ Nome da nova:    [Obra X - Entrega          ]                     │
│                  → será criada: C:\Projetos\Obra X - Entrega       │
│ Tipos mantidos:  [DE, LI, LD, PR, FO        ]                     │
│ Passos:  [x] Montar pasta com os tipos   [x] Converter Word/Excel  │
│ Processos simultâneos: [2]                                        │
│                                         [ Analisar ]              │
│ ┌ Resumo ──────────────────────────────────────────────────────┐ │
│ │ 312 PDFs a copiar · 48 Word/Excel a converter · 1.204 fora     │ │
│ │ 2 conflitos de PDF (ver lista)                                 │ │
│ │ [Ver detalhes ▾] tabela: arquivo | ação | motivo               │ │
│ └──────────────────────────────────────────────────────────────┘ │
│ [████████████░░░░░░░░] 60%  Convertendo 29/48      [Cancelar]     │
│                                         [ Executar fluxo ]        │
├──────────────────────────────────────────────────────────────────┤
│ [x] Gerar relatórios CSV   ·  Office: Word ✓ Excel ✓  · LO ✗       │
└──────────────────────────────────────────────────────────────────┘
```

- **Fluxo de entrega (aba inicial):**
  - Os campos são lembrados entre usos (QSettings).
  - "Analisar" gera o plano numa thread separada e mostra o resumo, com uma
    tabela filtrável por ação.
  - "Executar fluxo" só fica habilitado depois de analisar e pede uma
    confirmação com os números do resumo.
  - Durante a execução, os campos ficam bloqueados e aparecem o progresso, o log
    e o botão Cancelar.
  - Ao fim, mostra o resumo e o botão "Abrir pasta".
- **Converter, Limpeza e Copiar por código:** cada aba tem o próprio seletor de
  "Pasta de trabalho", com a última usada lembrada, e o mesmo comportamento
  descrito na revisão 1:
  - prévia em tabela;
  - nomes não encontrados em vermelho bloqueiam a operação;
  - confirmação antes de agir;
  - resultado na tabela.
  - Na Limpeza, os 9 modos ficam numa lista à esquerda. Os modos com lista de
    manutenção usam uma caixa de texto para colar a lista.
- **Relatórios:** escolhe a pasta, alterna entre Convertidos, Apagados e
  Ignorados (fluxo), mostra a tabela e tem os botões "Abrir no Excel" e
  "Atualizar".
- **Barra inferior:** caixa "Gerar relatórios CSV" (global, lembrada) e a
  detecção de Office/LibreOffice.

### Testes

pytest sobre o núcleo, com `tmp_path` e arquivos fictícios. Os testes cobrem:

- classificação do fluxo (cada regra de tipo e formato, `.zip`, sem tipo,
  maiúsculas e minúsculas);
- base intacta depois do fluxo;
- destino existente ou dentro da base;
- remoção de pastas vazias;
- o original fica quando a conversão falha;
- os relatórios desativados não criam arquivos.

Para isso, a conversão é substituída por um dublê que gera um PDF fictício ou
falha de propósito.

Também cobrem:

- os 9 seletores de limpeza, com `send2trash` dublado;
- o plano de cópia;
- o plano de conversão com duplicados;
- os caminhos protegidos;
- `separar_lista` e o CSV.

A conversão real (COM/LibreOffice) é verificada manualmente com `.docx` e `.xlsx`
de exemplo, rodando o fluxo pelo programa e pelo `.exe`.

### Executável

- PyInstaller em modo onefile e `--windowed`, gerando
  `dist/GerenciadorDocumentos.exe`.
- Inclui pywin32 (`pythoncom`, `win32com`), pypdf e Send2Trash. O PySide6 é
  limitado a QtCore, QtGui e QtWidgets.
- Verificar que a conversão em vários processos funciona dentro do `.exe`, sem
  abrir janelas extras.

### Script antigo

`gerenciador_documentos.py` fica intocado como referência. Ele só é removido no
fim, se o usuário aprovar.

## Deixado para quem implementar

- Layout fino, textos dos botões e ícone (sem ícone, usa o padrão).
- Divisão interna das funções em cada módulo.
- Reaproveitar as mensagens de erro atuais sempre que possível.

## Observações

A pasta não é um repositório git, então este documento não foi commitado.
