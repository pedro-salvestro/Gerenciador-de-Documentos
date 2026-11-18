"""Aba avulsa: converter todos os Word/Excel da pasta de trabalho para PDF."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from ..nucleo.constantes import RELATORIO_CONVERTIDOS
from ..nucleo.conversao import (
    ResultadoConversao, TrabalhoConversao, converter_arquivo, documentos_convertiveis,
    executar_conversao, gravar_relatorio_conversao, planejar_conversao, processos_padrao,
)
from ..nucleo.espaco import EspacoTrabalho
from ..nucleo.relatorios import Relatorio
from .configuracoes import Configuracoes
from .dialogos import confirmar, mostrar_erro
from .seletor_pasta import SeletorPasta
from .tabela_itens import TabelaItens
from .trabalhador import Trabalhador, executar_em_segundo_plano

CHAVE_PASTA = "avulso/pasta"

class AbaConversao(QWidget):
    def __init__(self, configuracoes: Configuracoes, obter_relatorio: Callable[[], Relatorio],
                 funcao: Callable[..., tuple[str, str]] = converter_arquivo,
                 criar_executor: Callable[[int], Executor] | None = None,
                 pai: QWidget | None = None):
        super().__init__(pai)
        self._obter_relatorio = obter_relatorio
        self._funcao = funcao
        self._criar_executor = criar_executor
        self._espaco: EspacoTrabalho | None = None
        self._trabalhos: list[TrabalhoConversao] = []
        self._trabalhador: Trabalhador | None = None
        self._relatorio: Relatorio | None = None

        self.seletor = SeletorPasta("Pasta de trabalho:", CHAVE_PASTA, configuracoes)
        self.botao_analisar = QPushButton("Analisar")
        topo = QHBoxLayout()
        topo.addWidget(self.seletor, 1)
        topo.addWidget(self.botao_analisar)

        self.rotulo_resumo = QLabel(
            "Converte todos os Word/Excel da pasta (inclusive subpastas) para PDF. Word: "
            "Office quando disponível; LibreOffice como alternativa. Excel: Microsoft Excel. "
            "Os PDFs antigos são substituídos somente após sucesso.")
        self.rotulo_resumo.setWordWrap(True)
        self.tabela = TabelaItens(["Origem", "PDF de destino"])

        self.campo_processos = QSpinBox()
        self.campo_processos.setRange(1, 1)
        self.barra = QProgressBar()
        self.barra.setVisible(False)
        self.botao_cancelar = QPushButton("Cancelar")
        self.botao_cancelar.setVisible(False)
        self.botao_iniciar = QPushButton("Iniciar conversão")
        self.botao_iniciar.setEnabled(False)
        rodape = QHBoxLayout()
        rodape.addWidget(QLabel("Processos simultâneos:"))
        rodape.addWidget(self.campo_processos)
        rodape.addWidget(self.barra, 1)
        rodape.addWidget(self.botao_cancelar)
        rodape.addWidget(self.botao_iniciar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)

        layout = QVBoxLayout(self)
        layout.addLayout(topo)
        layout.addWidget(self.rotulo_resumo)
        layout.addWidget(self.tabela, 1)
        layout.addWidget(self.log)
        layout.addLayout(rodape)

        self.seletor.pasta_alterada.connect(lambda _: self._invalidar())
        self.botao_analisar.clicked.connect(self._analisar)
        self.botao_iniciar.clicked.connect(self._iniciar)
        self.botao_cancelar.clicked.connect(self._cancelar)

    def _invalidar(self) -> None:
        self._trabalhos = []
        self.tabela.limpar()
        self.botao_iniciar.setEnabled(False)

    def _analisar(self) -> None:
        texto = self.seletor.campo.text().strip()
        if not texto:
            mostrar_erro(self, "Conversão", "Escolha a pasta de trabalho.", [])
            return

        def tarefa(ctx):
            espaco = EspacoTrabalho.abrir(texto)
            return espaco, planejar_conversao(documentos_convertiveis(espaco))

        self._ocupado(True)
        self._trabalhador = executar_em_segundo_plano(
            self, tarefa, ao_concluir=self._ao_analisar, ao_falhar=self._ao_falhar)

    def _ao_analisar(self, resultado) -> None:
        self._ocupado(False)
        self._espaco, self._trabalhos = resultado
        espaco = self._espaco
        self.tabela.definir_linhas(
            [[espaco.relativo(t.origem), espaco.relativo(t.destino)] for t in self._trabalhos],
            self._trabalhos)
        quantidade = len(self._trabalhos)
        self.rotulo_resumo.setText(f"Documentos Word/Excel encontrados: {quantidade}")
        self.campo_processos.setRange(1, max(quantidade, 1))
        self.campo_processos.setValue(processos_padrao(quantidade))
        self.botao_iniciar.setEnabled(quantidade > 0)

    def _iniciar(self) -> None:
        espaco, trabalhos = self._espaco, list(self._trabalhos)
        if espaco is None or not trabalhos:
            return
        processos = self.campo_processos.value()
        if not confirmar(self, "Converter para PDF",
                         f"Converter {len(trabalhos)} documento(s) com {processos} "
                         "processo(s) simultâneo(s)?\nOs PDFs antigos são substituídos "
                         "somente após sucesso."):
            return
        relatorio = self._relatorio = self._obter_relatorio()
        indices = {id(t): i for i, t in enumerate(trabalhos)}

        def tarefa(ctx):
            def concluido(resultado: ResultadoConversao, feitos: int, total: int) -> None:
                ctx.log(f"{indices[id(resultado.trabalho)]}\t{resultado.status}\t"
                        f"{resultado.detalhe}")
                ctx.progresso("Convertendo", feitos, total)

            resultados = executar_conversao(
                trabalhos, processos, ao_concluir=concluido, cancelado=ctx.cancelado,
                funcao=self._funcao, criar_executor=self._criar_executor)
            gravar_relatorio_conversao(resultados, espaco.raiz, relatorio,
                                       espaco.caminho_relatorio(RELATORIO_CONVERTIDOS))
            return resultados

        self.log.clear()
        self._ocupado(True, cancelavel=True)
        self._trabalhador = executar_em_segundo_plano(
            self, tarefa, ao_concluir=self._ao_concluir, ao_falhar=self._ao_falhar,
            ao_progresso=self._ao_progresso, ao_log=self._ao_item)

    def _ao_item(self, mensagem: str) -> None:
        indice, status, detalhe = mensagem.split("\t", 2)
        linha = int(indice)
        self.tabela.definir_status(linha, status, erro=status != "convertido")
        origem = self.tabela.dados()[linha].origem
        texto = f"{status.upper()}: {self._espaco.relativo(origem) if self._espaco else origem}"
        self.log.appendPlainText(f"{texto} {detalhe}".strip())

    def _ao_progresso(self, etapa: str, atual: int, total: int) -> None:
        self.barra.setMaximum(max(total, 1))
        self.barra.setValue(atual)

    def _ao_concluir(self, resultados: list[ResultadoConversao]) -> None:
        self._ocupado(False)
        ok = sum(r.status == "convertido" for r in resultados)
        self.rotulo_resumo.setText(f"Convertidos: {ok}; erros/cancelados: {len(resultados) - ok}.")
        self.botao_iniciar.setEnabled(False)
        for aviso in self._relatorio.erros if self._relatorio else []:
            self.log.appendPlainText(f"AVISO: {aviso}")

    def _ao_falhar(self, mensagem: str, itens: list) -> None:
        self._ocupado(False)
        mostrar_erro(self, "Conversão", mensagem, itens)

    def _cancelar(self) -> None:
        if self._trabalhador:
            self._trabalhador.cancelar()
            self.botao_cancelar.setEnabled(False)

    def _ocupado(self, ocupado: bool, cancelavel: bool = False) -> None:
        for widget in (self.seletor, self.botao_analisar, self.botao_iniciar,
                       self.campo_processos):
            widget.setEnabled(not ocupado)
        self.barra.setVisible(ocupado and cancelavel)
        self.barra.setValue(0)
        self.botao_cancelar.setVisible(ocupado and cancelavel)
        self.botao_cancelar.setEnabled(True)

