# Gerenciador de Documentos

Programa para preparar pastas de entrega de projetos e organizar documentos.

## O que ele faz

- **Fluxo de entrega** (aba principal): você escolhe a *pasta base*, o *nome da pasta
  nova* e os *tipos mantidos* (padrão `DE, LI, LD, PR, FO`). O programa cria a pasta nova
  ao lado da base contendo **apenas PDFs desses tipos**:
  - PDFs existentes do tipo permitido são copiados;
  - Word/Excel do tipo permitido são copiados e convertidos para PDF (o original sai da
    pasta nova só se a conversão der certo);
  - todo o resto fica de fora (sem código de tipo, outros tipos, outros formatos, `.zip`),
    e pastas vazias não são criadas.

  O tipo vem do fim do nome do arquivo: `NVC00410A-DE-001.pdf` → `DE`.

  - **Salvar em** (opcional): pasta onde a pasta nova é criada. Vazio = ao lado da base.
  - **NVCs / arquivos** (opcional): restringe a entrega a uma lista, um por linha ou
    separados por vírgula. `NVC00410` → todas as variantes; `NVC00410A` → só essa
    variante; `NVC00410A-DE-001` → só esse arquivo. A estrutura de pastas é mantida e as
    regras de tipo continuam valendo. Itens que não levam nenhum arquivo (formato
    inválido, não encontrados ou fora dos tipos) aparecem na análise e, ao executar, a
    confirmação pergunta se deseja continuar sem eles.
  - **Adicionar a uma pasta existente** (opção *Destino*): em vez de criar uma pasta
    nova, os PDFs entram numa entrega já começada, apontada em *Salvar em* — útil para
    acrescentar NVCs depois. As subpastas que faltarem são criadas. PDFs que **já
    existem** na pasta são **mantidos** (aparecem como "Já existe (mantido)"); marque
    *Substituir PDFs que já existem* para trocá-los — os antigos vão para a **Lixeira**.
    A conversão é feita numa pasta temporária, então nenhum Word/Excel ou pasta que já
    estava lá é apagado. O relatório de convertidos acumula as execuções.
  **A pasta base nunca é alterada.** Clique em *Analisar* para ver a prévia e em
  *Executar fluxo* para criar a pasta (ou adicionar à existente).
- **Converter**: converte todos os Word/Excel de uma pasta para PDF.
- **Limpeza**: envia à Lixeira arquivos ou pastas (9 modos, com prévia e confirmação).
- **Copiar por código**: copia arquivos `NVC…` para `NVCxxx/variante/<nome>`.
- **Relatórios**: mostra os CSV gerados. Na barra inferior, *Gerar relatórios CSV* liga ou
  desliga a geração de relatórios.

Requisitos na máquina de uso: Windows, **Microsoft Excel** (obrigatório para planilhas) e
Microsoft Word ou LibreOffice (para documentos Word).

## Para desenvolvedores

```bash
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

Rodar a partir do código:

```bash
.venv\Scripts\python main.py
```

Testes:

```bash
.venv\Scripts\python -m pytest
```

Gerar o executável (`dist\GerenciadorDocumentos.exe`, arquivo único):

```bash
.venv\Scripts\python -m PyInstaller gerenciador.spec --noconfirm
```

### Estrutura

```
main.py                 ponto de entrada (freeze_support + interface)
gerenciador/nucleo/     regras de negócio, sem interface (testáveis)
  arquivos.py           varredura e classificação por nome
  conversao.py          Office/LibreOffice -> PDF, em processos paralelos
  fluxo.py              fluxo de entrega (planejar -> executar)
  limpeza.py            9 modos de seleção + envio à Lixeira
  copia.py              cópia por código NVC
  relatorios.py         CSV (desativável)
gerenciador/gui/        interface PySide6 (uma aba por função)
tests/                  testes pytest / pytest-qt
```

Toda operação segue o padrão *planejar* (prévia, sem alterar nada; erros viram
`ErroValidacao`) e *executar* (com progresso e cancelamento). A interface roda o núcleo
em segundo plano para não travar a janela.

O script antigo `gerenciador_documentos.py` (menu de terminal) ficou como referência.
