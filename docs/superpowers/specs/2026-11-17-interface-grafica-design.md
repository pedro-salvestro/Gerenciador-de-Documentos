# Interface gráfica do Gerenciador de Documentos — design

Data: 2026-11-17

## Intenção

Hoje o Gerenciador de Documentos (`gerenciador_documentos.py`) roda como menu de
terminal e trabalha sempre na pasta onde o script está. O objetivo é:

1. Substituir o menu por uma interface gráfica (janela).
2. Permitir **escolher, dentro do programa, a pasta de trabalho**. O executável
   não precisa estar dentro dela.
3. Distribuir como **executável Windows** (`.exe`) que roda sem Python instalado.
4. Reestruturar o código com boas práticas de engenharia de software: separar a
   lógica da interface, dividir em módulos e tornar a lógica testável.

## Objetivos

- Manter as 5 funções atuais com **as mesmas regras de negócio**:
  1. Converter todos os Word/Excel da pasta (recursivo) para PDF.
  2. Enviar à Lixeira, com os 9 modos atuais:
     - todos os não PDF;
     - Word/Excel;
     - por extensão;
     - seleção individual;
     - pastas vazias;
     - STEP/DWG;
     - manter lista de arquivos;
     - manter lista de pastas;
     - documentos ET/DT/MD, inclusive PDFs.
  3. Ver o relatório de convertidos.
  4. Ver o relatório de apagados.
  5. Copiar arquivos por código NVC para `NVCxxx/variante/<nome>`.
- Manter todas as salvaguardas atuais:
  - prévia antes de agir e confirmação explícita;
  - Lixeira em vez de exclusão definitiva;
  - checagem de caminho seguro (dentro da pasta, sem links simbólicos);
  - cancelar quando há nome não encontrado;
  - não sobrescrever destinos de cópia;
  - substituir o PDF antigo só depois de sucesso;
  - validação A4 do Excel;
  - relatórios CSV.
- Fazer a conversão sem travar a janela, com barra de progresso e log ao vivo.
- Ter um código organizado em pacotes, com a lógica coberta por testes automatizados.

## Fora do escopo

- Mudar regras de seleção, nomes de destino, formato dos CSV ou critérios de
  conversão.
- Suporte a macOS/Linux no `.exe`. A conversão de Excel depende do Microsoft Excel
  via COM, ou seja, de Windows. O núcleo continua portável onde já era.
- Instalador (MSI/Inno Setup), atualização automática, idiomas além do português.

## O que tornaria isto um fracasso mesmo funcionando

- A interface apagar algo que o script atual não apagaria, ou apagar sem mostrar
  a prévia e pedir confirmação.
- O programa enviar o próprio `.exe` ou os relatórios à Lixeira por acidente,
  fora do modo que inclui relatórios explicitamente.
- A janela congelar durante a conversão, ou cada processo de conversão abrir uma
  janela nova do programa.

## Restrições

- Windows 11, Python 3.14 (instalado), pywin32, pypdf e Send2Trash já instalados.
- Será preciso instalar PySide6 e PyInstaller.
- Excel obrigatório para planilhas. Word usa Office, com LibreOffice como
  alternativa (comportamento atual).
- Objetos COM ficam restritos ao processo filho (comportamento atual, mantido).

## Abordagens consideradas

| Abordagem | Prós | Contras |
|---|---|---|
| **PySide6 (Qt)** — escolhida | Visual moderno; tabelas com caixas de seleção; threads e progresso robustos | `.exe` maior (~60–90 MB) |
| Tkinter (ttk) | Já vem no Python; `.exe` pequeno | Visual datado; listas com seleção e tabelas mais trabalhosas |
| Web (Flet/Electron) | Visual livre | Pesado; sem ganho real para ferramenta desktop interna |

O usuário escolheu PySide6, porque o uso principal é ver listas de arquivos,
marcar itens e conferir antes de confirmar.

## Decisões do usuário

- A pasta de trabalho é escolhida no programa. O `.exe` pode ficar em qualquer
  lugar.
- Interface em PySide6.
- O código deve ser reestruturado e separado em módulos.

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
      espaco.py                # EspacoTrabalho: raiz escolhida + caminhos protegidos
      arquivos.py              # listar_arquivos, listar_pastas, listar_pastas_vazias, separar_lista
      relatorios.py            # gravar_csv, ler_csv, caminhos dos relatórios
      conversao.py             # Conversor, validar_pdf_a4, converter_arquivo, planejar/executar
      limpeza.py               # 9 seletores -> Previa; enviar_lixeira
      copia.py                 # planejar_copia -> PlanoCopia; executar_copia
      erros.py                 # ErroValidacao (mensagem + itens)
    gui/
      __init__.py
      app.py                   # cria QApplication e janela
      janela_principal.py      # seletor de pasta + abas
      trabalhador.py           # execução em segundo plano (QThread) com sinais
      tabela_itens.py          # tabela reutilizável com caixas de seleção
      aba_conversao.py
      aba_limpeza.py
      aba_copia.py
      aba_relatorios.py
  tests/
    test_arquivos.py, test_limpeza.py, test_copia.py, test_conversao_plano.py, test_relatorios.py
  requirements.txt             # PySide6, pywin32, pypdf, Send2Trash
  requirements-dev.txt         # pytest, pyinstaller
  gerenciador.spec             # configuração do PyInstaller
  README.md                    # como rodar, testar e gerar o .exe
```

### Núcleo: separar "planejar" de "executar"

Cada operação destrutiva ou longa vira duas etapas, e nenhuma delas faz `input()`
nem `print()`:

- **Planejar:** recebe a pasta e os parâmetros e devolve uma prévia, ou seja, a
  lista de itens com tipo e destino. Se algo inviabiliza a operação (nomes não
  encontrados, código inválido, destino já existe), levanta `ErroValidacao` com a
  mensagem e a lista de itens problemáticos.
- **Executar:** recebe a prévia confirmada e devolve a lista de resultados por
  item. Também grava o CSV.

`EspacoTrabalho(raiz)` substitui o `RAIZ` global e conhece os caminhos
protegidos que nunca entram em listagens nem em prévias:

- os dois relatórios CSV, como hoje (exceto no modo "todos os não PDF", que os
  inclui de propósito, como hoje);
- `sys.executable` quando o programa está empacotado, além de `main.py` e da pasta
  `gerenciador/` se a pasta de trabalho for a do código-fonte. Isso substitui a
  proteção atual do próprio `.py`.

**Mudança deliberada:** hoje o modo "todos os não PDF" incluiria o próprio script
se ele estivesse na pasta. A nova versão protege o programa em todos os modos.

Os relatórios continuam sendo gravados **na pasta de trabalho escolhida**,
como hoje.

### Conversão

- `planejar_conversao(espaco)` monta a lista de pares (origem, destino) com a
  regra atual de nomes duplicados e sufixos `_2`, `_3`…
- `executar_conversao(trabalhos, processos, ao_concluir_item, cancelado)` usa o
  `ProcessPoolExecutor` com `spawn`, como hoje. `converter_arquivo` continua
  sendo uma função de módulo, que pode ser enviada ao processo filho.
- O cancelamento cancela os itens ainda não iniciados. Os itens em andamento
  terminam, porque matar o Excel no meio deixaria processos órfãos. Itens
  cancelados aparecem no relatório como `cancelado`.
- `main.py` chama `multiprocessing.freeze_support()` antes de qualquer
  importação de Qt. Isso é necessário no `.exe`.

### Interface

```
┌──────────────────────────────────────────────────────────────┐
│ Pasta de trabalho: [C:\...\Projeto X            ] [Escolher…] │
├──────────────────────────────────────────────────────────────┤
│ [Converter] [Limpeza] [Copiar por código] [Relatórios]       │
│                                                              │
│  (conteúdo da aba)                                           │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│ status: 128 arquivos na pasta · Office: Word ✓ Excel ✓ · LO ✗ │
└──────────────────────────────────────────────────────────────┘
```

- **Pasta de trabalho:** botão "Escolher…" abre o seletor de pastas. A última
  pasta usada é lembrada (QSettings). Sem pasta válida, as abas ficam
  desabilitadas.
- **Converter:** botão "Analisar" monta uma tabela com Origem, PDF de destino e
  Status, além do campo "Processos simultâneos" (padrão = regra atual). Ao clicar
  em "Iniciar", a barra de progresso avança e cada linha mostra OK ou o erro.
  O botão "Cancelar" interrompe os itens pendentes. Ao fim, um resumo mostra
  convertidos e erros, com link para o relatório.
- **Limpeza:** lista com os 9 modos à esquerda.
  - Modos simples mostram direto a prévia em tabela (caminho e tipo).
  - "Por extensão" mostra caixas de seleção por extensão.
  - "Seleção individual" mostra a tabela com caixas marcáveis e um botão
    "Marcar todos".
  - "Manter lista de arquivos/pastas" mostra uma caixa de texto para colar a
    lista (vírgula, ponto e vírgula ou uma por linha, como hoje) e o botão
    "Gerar prévia". Nomes não encontrados aparecem em vermelho e bloqueiam a
    operação.
  - O botão "Enviar N itens à Lixeira" abre uma confirmação com o número de
    itens. O resultado aparece na própria tabela.
- **Copiar por código:** caixa para colar códigos e campo "Nome da pasta final".
  "Gerar prévia" mostra a tabela Origem → Destino, e "Copiar" pede confirmação.
  Os erros de validação aparecem acima da tabela.
- **Relatórios:** alternância entre Convertidos e Apagados, com tabela lida do
  CSV, botão "Abrir no Excel" (abre o arquivo) e "Atualizar".
- Operações que varrem a pasta inteira ou executam ações rodam no
  `trabalhador.py` (QThread) para não travar a janela.

### Testes

- pytest sobre o núcleo, usando pastas temporárias (`tmp_path`) com arquivos
  fictícios. Os testes cobrem:
  - os 9 seletores de limpeza, incluindo nomes não encontrados e proteção de
    pastas-pai;
  - o plano de conversão com nomes duplicados;
  - o plano de cópia: código inválido, destino existente, nome repetido;
  - os caminhos protegidos (`.exe`, relatórios);
  - `separar_lista`;
  - gravação e leitura de CSV.
- O envio à Lixeira é testado com `send2trash` substituído por um dublê, para que
  os testes não mexam na Lixeira real.
- A conversão real (COM/LibreOffice) não entra nos testes automatizados. Ela é
  verificada manualmente com um `.docx` e um `.xlsx` de exemplo.

### Executável

- PyInstaller em modo **onefile** e `--windowed` (sem console). Gera um único
  `GerenciadorDocumentos.exe` em `dist/`.
- Inclui pywin32 (`pythoncom`, `win32com`), pypdf e Send2Trash. O PySide6 é
  enxugado: só QtCore, QtGui e QtWidgets.
- Primeiro, valido que a conversão em vários processos funciona dentro do `.exe`
  (`freeze_support`), sem abrir janelas extras.

### Script antigo

`gerenciador_documentos.py` fica intocado durante o trabalho, como referência.
Ele só é removido no fim, se o usuário aprovar.

## Deixado para quem implementar

- Layout fino dos widgets, textos de botões e ícone do programa. Se não houver
  ícone, usa o padrão.
- Divisão interna das funções dentro de cada módulo do núcleo.
- Mensagens de erro: reaproveitar as atuais sempre que possível.

## Observações

A pasta não é um repositório git, então este documento não foi commitado. Se
desejar, posso iniciar um repositório git.
