# Fluxo de entrega: escolher onde salvar e filtrar por NVC/arquivo

Data: 2026-11-18 · Tamanho: mudança pequena

## Intenção

1. Poder escolher **onde** a pasta de entrega é criada, em vez de sempre ao lado da
   pasta base (ex.: base numa pasta sincronizada do SharePoint, entrega em outro lugar).
2. Poder escolher **quais NVCs ou arquivos** passam pelo fluxo, colando uma lista.

## Objetivos

- Campo **Salvar em** na aba Fluxo. Vazio = ao lado da pasta base (comportamento atual).
- Caixa **NVCs / arquivos** na aba Fluxo. Vazia = todos entram (comportamento atual).
- Itens problemáticos da lista **não bloqueiam**: são avisados na análise e, ao
  executar, a confirmação lista quais são e pergunta se deseja continuar sem eles.
- Arquivos que entram mantêm a mesma estrutura de pastas relativa à base, como hoje.

## Não-objetivos

- Não muda as regras de tipo (DE, LI…) nem de formato: a lista é um filtro a mais.
- Não muda as abas Converter, Limpeza, Copiar por código e Relatórios.

## Regras

**Salvar em**
- Botão *Escolher…*; o rótulo "→ será criada: …" mostra o caminho final.
- A última pasta escolhida é lembrada (`fluxo/destino`).
- Continua proibido: pasta nova dentro da base, ou com nome de pasta já existente.
- A pasta escolhida precisa existir.

**Lista de NVCs / arquivos** (separada por vírgula, ponto e vírgula ou quebra de
linha — dá para colar uma coluna do Excel; maiúsculas/minúsculas tanto faz):

| Item da lista       | O que entra                                              |
|---------------------|----------------------------------------------------------|
| `NVC00410`          | todos os arquivos de todas as variantes (A, B…)          |
| `NVC00410A`         | todos os arquivos dessa variante                         |
| `NVC00410A-DE-001`  | só arquivos com esse nome (qualquer extensão)            |
| `NVC00410A-DE-001.pdf` | só esse arquivo exato                                 |

- O NVC de um arquivo é lido do começo do nome (`NVC` + dígitos + letra opcional).
- Um arquivo entra se casar com **qualquer** item da lista **e** passar nas regras de
  tipo/formato de hoje. Os que não casam ficam "Fora da entrega" com motivo
  "fora da lista".

**Itens problemáticos** — qualquer item da lista que não leva nenhum arquivo para a
entrega:
- formato inválido (não começa com `NVC` + dígitos);
- não encontrado na pasta base;
- encontrado, mas nada dele entra (ex.: "tipo XX não permitido").

Eles aparecem no resumo da análise ("Itens da lista com problema: …") e, ao clicar
*Executar fluxo*, a confirmação começa por eles: "Estes itens da lista não vão entrar:
… Deseja continuar sem eles?". Sem problemas, a confirmação é a de hoje.

## Abordagem

Filtro e destino viram parâmetros do núcleo (`ParametrosFluxo.pasta_destino`,
`ParametrosFluxo.selecao`); `planejar_fluxo` aplica o filtro, e o `PlanoFluxo` passa a
trazer a lista de itens problemáticos com o motivo. Assim prévia, relatório de
ignorados e testes ficam coerentes. Descartado: filtrar só na tela depois da análise
(tela e relatório discordariam).

## Decisões do Claude (revisar)

- A caixa da lista tem ~3 linhas e é lembrada entre usos, como os outros campos.
- Itens repetidos na lista são considerados uma vez.
