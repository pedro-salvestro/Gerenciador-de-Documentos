# Fluxo de entrega em pasta existente — design

Data: 2026-11-19

## Intenção

Hoje o fluxo de entrega sempre cria uma pasta nova (`Salvar em` + `Nome da pasta nova`)
e recusa executar se ela já existir. O usuário monta entregas aos poucos: faz a pasta
com alguns NVCs e depois quer **acrescentar outros NVCs na mesma pasta**, sem refazer
tudo e sem estragar o que já está lá.

## Objetivos

- Na aba Fluxo de entrega, escolher entre **Criar pasta nova** (comportamento atual) e
  **Adicionar a uma pasta existente**.
- Na pasta existente, os PDFs entram respeitando a mesma estrutura de subpastas da
  base; subpastas que faltarem são criadas.
- PDF que **já existe** na pasta: por padrão é **mantido** (pulado). Uma caixa
  "Substituir PDFs que já existem" (desmarcada por padrão) faz substituir; o antigo vai
  para a **Lixeira**.
- A análise mostra quantos já existem e se serão mantidos ou substituídos.

## Fora do escopo

- Comparar conteúdo/data dos PDFs para decidir sozinho se é revisão nova.
- Remover da pasta PDFs que não estão mais na seleção.

## O que tornaria isto um fracasso

- Apagar ou sobrescrever qualquer arquivo do usuário na pasta existente sem que a
  análise tenha mostrado e a caixa "Substituir" esteja marcada.
- Remover pastas (vazias ou não) que já existiam na pasta de destino.
- Alterar qualquer coisa na pasta base (regra atual, mantida).

## Abordagens consideradas

| Abordagem | Prós | Contras |
|---|---|---|
| **Modo no fluxo atual** (escolhida — decisão do Claude) | Reaproveita análise, seleção de NVCs, conversão e relatórios; uma só tela | `planejar`/`executar_fluxo` ganham dois parâmetros |
| Aba separada "Adicionar à entrega" | Fluxos independentes | Duplica a seleção, a análise e a conversão |
| Montar numa pasta temporária e depois mesclar | Execução atual intocada | Dobra cópias e espaço; a mescla repete as mesmas regras de conflito |

## Decisões do usuário

- Uso: acrescentar NVCs a uma entrega já começada.
- Conflito com PDF existente: **opção 3** — caixa "Substituir os que já existem",
  desmarcada por padrão (padrão = manter).

## Decisões do Claude (o usuário pode corrigir)

- **Tela:** dois botões de opção acima de "Nome da pasta nova": *Criar pasta nova* /
  *Adicionar a uma pasta existente*. No segundo modo, "Salvar em" passa a ser
  obrigatório e é a própria pasta da entrega; "Nome da pasta nova" fica desativado.
  O modo é lembrado entre usos; a caixa "Substituir" sempre começa desmarcada.
- **Conversão em pasta temporária:** os Word/Excel são copiados e convertidos dentro de
  uma pasta temporária `.pdf_entrega_*` criada na pasta de destino (mesmo disco; a
  varredura já ignora pastas `.pdf_*`). Só o PDF pronto é movido para o lugar final.
  Nenhum `.docx`/`.xlsx` do usuário é sobrescrito ou apagado. Vale para os dois modos.
- **Pastas vazias:** só são removidas as pastas que o próprio fluxo criou (nos dois
  modos), além da pasta temporária.
- **Proteções novas:** a pasta existente não pode ser a pasta base, ficar dentro dela
  nem conter a pasta base (evita gravar dentro da base por um caminho relativo).
- **Com a conversão desligada:** o "arquivo final" de um Word/Excel é a própria cópia;
  a mesma regra de manter/substituir vale para ele.
- **Relatórios na pasta existente:** `arquivos_convertidos.csv` **acumula** (acrescenta
  linhas a cada execução, cabeçalho só na primeira); `arquivos_ignorados.csv` é
  substituído (reflete a última execução). Na pasta nova o resultado é igual ao atual.
- **Resumo final:** passa a informar também quantos foram mantidos e substituídos.
- **Rótulos:** ação "Já existe (mantido)" na tabela; com "Substituir" marcada, as linhas
  mostram o motivo "substitui o PDF existente (antigo vai para a Lixeira)".

## Design

Núcleo (`gerenciador/nucleo/fluxo.py`):

- `ParametrosFluxo` ganha `pasta_existente: bool = False` e
  `substituir_existentes: bool = False`.
- `planejar_fluxo`: no modo existente, `destino_raiz = pasta_destino.resolve()` (precisa
  existir), sem validar nome. Para cada item que entra na entrega, calcula o arquivo
  final (PDF copiado, PDF da conversão ou cópia sem conversão). Se o final já existe:
  sem "substituir" → nova ação `MANTER` ("já existe na pasta (mantido)"), não é copiado
  nem convertido; com "substituir" → mantém a ação e marca para substituir. O plano
  expõe `ja_existem` (lista) e a propriedade `mantidos`.
- `executar_fluxo` (novo parâmetro `lixeira`, padrão `send2trash`, para testes):
  1. Cria a pasta nova (modo novo) ou confere que a existente ainda existe.
  2. Copia os PDFs; antes de gravar sobre um existente marcado para substituir,
     envia o antigo à Lixeira.
  3. Copia os Word/Excel para a pasta temporária, converte lá e move cada PDF pronto ao
     lugar final (Lixeira antes, se substituir). Em falha/cancelamento, o Word/Excel vai
     para o lugar dele na entrega (como hoje na pasta nova) **só se não existir arquivo
     com esse nome**; senão fica de fora e o erro avisa.
  4. Remove a pasta temporária e, de baixo para cima, as pastas criadas por esta
     execução que ficaram vazias.
  5. Relatórios: `Relatorio.acrescentar(...)` para convertidos; `gravar` para ignorados.
- `ResumoFluxo` ganha `mantidos` e `substituidos`.

Interface (`gerenciador/gui/aba_fluxo.py`): os dois botões de opção, caixa "Substituir…"
visível só no modo existente, textos do rótulo de destino, do resumo da análise, da
confirmação e do resumo final ajustados. Mudar modo ou caixa invalida a análise.

Testes: núcleo (manter, substituir com dublê da Lixeira, subpasta nova criada e
removida se vazia, pasta vazia pré-existente preservada, `.docx` do usuário com mesmo
nome intacto, proteções de caminho, CSV acumulado) e GUI (modo existente desativa o
nome, análise mostra "já existem", execução acrescenta sem tocar no existente).
