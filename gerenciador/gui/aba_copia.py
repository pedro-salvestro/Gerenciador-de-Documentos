"""Aba avulsa: copiar arquivos por código NVC para NVCxxx/variante/<nome>."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from ..nucleo.copia import PlanoCopia, executar_copia, planejar_copia
from ..nucleo.espaco import EspacoTrabalho
from .configuracoes import Configuracoes
from .dialogos import confirmar, listar_itens, mostrar_erro
from .seletor_pasta import SeletorPasta
from .tabela_itens import TabelaItens
from .trabalhador import executar_em_segundo_plano

CHAVE_PASTA = "avulso/pasta"
INSTRUCAO = ("Informe os códigos dos itens (ex.: NVC00410A), separados por vírgula, ponto e "
             "vírgula ou um por linha. Serão copiados todos os arquivos cujo nome comece pelo "
             "código informado, como NVC00410A-DE-001.pdf.")


class AbaCopia(QWidget):
    def __init__(self, configuracoes: Configuracoes, pai: QWidget | None = None):
        super().__init__(pai)
        self._espaco: EspacoTrabalho | None = None
        self._plano: PlanoCopia | None = None

        self.seletor = SeletorPasta("Pasta de trabalho:", CHAVE_PASTA, configuracoes)
        instrucao = QLabel(INSTRUCAO)
        instrucao.setWordWrap(True)
        self.campo_codigos = QPlainTextEdit()
        self.campo_codigos.setPlaceholderText("NVC00410A, NVC00411B")
        self.campo_codigos.setMaximumHeight(90)
        self.campo_nome = QLineEdit()
        self.campo_nome.setPlaceholderText("Ex.: Arquivos")
        formulario = QFormLayout()
        formulario.addRow("Códigos:", self.campo_codigos)
        formulario.addRow("Nome da pasta final:", self.campo_nome)

        self.botao_previa = QPushButton("Gerar prévia")
        self.rotulo_erro = QLabel()
        self.rotulo_erro.setWordWrap(True)
        self.rotulo_erro.setStyleSheet("color: #c62828;")
        self.tabela = TabelaItens(["Origem", "Destino"])
        self.botao_copiar = QPushButton("Copiar")
        self.botao_copiar.setEnabled(False)

        acoes = QHBoxLayout()
        acoes.addWidget(self.rotulo_erro, 1)
        acoes.addWidget(self.botao_previa)
        rodape = QHBoxLayout()
        rodape.addStretch(1)
        rodape.addWidget(self.botao_copiar)

        layout = QVBoxLayout(self)
        layout.addWidget(self.seletor)
        layout.addWidget(instrucao)
        layout.addLayout(formulario)
        layout.addLayout(acoes)
        layout.addWidget(self.tabela, 1)
        layout.addLayout(rodape)

        for sinal in (self.campo_codigos.textChanged, self.campo_nome.textChanged):
            sinal.connect(self._invalidar)
        self.seletor.pasta_alterada.connect(lambda _: self._invalidar())
        self.botao_previa.clicked.connect(self._gerar_previa)
        self.botao_copiar.clicked.connect(self._copiar)

    def _invalidar(self) -> None:
        self._plano = None
        self.botao_copiar.setEnabled(False)

    def _gerar_previa(self) -> None:
        texto_pasta = self.seletor.campo.text().strip()
        codigos, nome = self.campo_codigos.toPlainText(), self.campo_nome.text()
        self.rotulo_erro.clear()
        self.tabela.limpar()
        if not texto_pasta:
            self.rotulo_erro.setText("Escolha a pasta de trabalho.")
            return

        def tarefa(ctx):
            espaco = EspacoTrabalho.abrir(texto_pasta)
            return espaco, planejar_copia(espaco, codigos, nome)

        self.botao_previa.setEnabled(False)
        executar_em_segundo_plano(self, tarefa, ao_concluir=self._ao_previa,
                                  ao_falhar=self._ao_falhar_previa)

    def _ao_previa(self, resultado) -> None:
        self.botao_previa.setEnabled(True)
        self._espaco, self._plano = resultado
        self.tabela.definir_linhas(
            [[self._espaco.relativo(o), self._espaco.relativo(d)] for o, d in self._plano.itens],
            self._plano.itens)
        self.botao_copiar.setEnabled(bool(self._plano.itens))

    def _ao_falhar_previa(self, mensagem: str, itens: list) -> None:
        self.botao_previa.setEnabled(True)
        self.rotulo_erro.setText(f"{mensagem}\n{listar_itens(itens)}".strip())

    def _copiar(self) -> None:
        plano = self._plano
        if plano is None:
            return
        if not confirmar(self, "Copiar arquivos",
                         f"Copiar {len(plano.itens)} arquivo(s) para as pastas "
                         f"NVCxxx/variante/{plano.nome_destino}?"):
            return
        self._ocupado(True)

        def ao_falhar(mensagem: str, itens: list) -> None:
            self._ocupado(False)
            mostrar_erro(self, "Cópia", mensagem, itens)

        executar_em_segundo_plano(self, lambda ctx: executar_copia(plano),
                                  ao_concluir=self._ao_copiar, ao_falhar=ao_falhar)

    def _ocupado(self, ocupado: bool) -> None:
        """Durante a cópia nada pode trocar a tabela (os status são gravados por linha)."""
        for widget in (self.seletor, self.campo_codigos, self.campo_nome, self.botao_previa):
            widget.setEnabled(not ocupado)
        self.botao_copiar.setEnabled(False)

    def _ao_copiar(self, resultados) -> None:
        self._ocupado(False)
        self._plano = None
        for indice, (_, _, status, detalhe) in enumerate(resultados):
            texto = f"{status}: {detalhe}" if detalhe else status
            self.tabela.definir_status(indice, texto, erro=status == "erro")
        if any(r[2] == "erro" for r in resultados):
            self.rotulo_erro.setText("Erro durante a cópia. Confira os arquivos que já foram "
                                     "copiados nas pastas de destino.")
