"""Aba avulsa: enviar arquivos ou pastas à Lixeira, com os 9 modos do script original."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit, QPushButton,
    QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from ..nucleo import limpeza
from ..nucleo.espaco import EspacoTrabalho
from ..nucleo.limpeza import ItemLimpeza, ResultadoLimpeza
from ..nucleo.relatorios import Relatorio
from .configuracoes import Configuracoes
from .dialogos import confirmar, listar_itens, mostrar_erro
from .seletor_pasta import SeletorPasta
from .tabela_itens import TabelaItens
from .trabalhador import executar_em_segundo_plano

CHAVE_PASTA = "avulso/pasta"
MODOS = [
    "Todos os arquivos não PDF",
    "Documentos Word/Excel",
    "Escolher extensões",
    "Escolher arquivos individualmente",
    "Apagar pastas vazias",
    "Apagar arquivos STEP/DWG",
    "Manter uma lista de arquivos e apagar os demais",
    "Manter uma lista de pastas e apagar as demais",
    "Apagar documentos ET, DT e MD (-ET-###, -DT-###, -MD-###), inclusive PDFs",
]
MODO_EXTENSOES, MODO_INDIVIDUAL, MODO_MANTER_ARQUIVOS, MODO_MANTER_PASTAS = 2, 3, 6, 7
AUTOMATICOS = {0: limpeza.selecionar_todos_nao_pdf, 1: limpeza.selecionar_word_excel,
               MODO_INDIVIDUAL: limpeza.candidatos, 4: limpeza.selecionar_pastas_vazias,
               5: limpeza.selecionar_cad, 8: limpeza.selecionar_et_dt_md}
INSTRUCOES = {
    MODO_MANTER_ARQUIVOS: "Informe os nomes ou caminhos relativos dos arquivos que devem ser "
                          "mantidos, separados por vírgula, ponto e vírgula ou um por linha. "
                          "Exemplo: projeto/modelo.dwg, notas.docx",
    MODO_MANTER_PASTAS: "Informe os nomes ou caminhos relativos das pastas que devem ser "
                        "mantidas, separados por vírgula, ponto e vírgula ou uma por linha. "
                        "A pasta e todo o seu conteúdo serão preservados. "
                        "Exemplo: projeto/modelos; documentos importantes",
}

Previa = tuple[EspacoTrabalho, list[ItemLimpeza], list[Path]]


class AbaLimpeza(QWidget):
    def __init__(self, configuracoes: Configuracoes, obter_relatorio: Callable[[], Relatorio],
                 lixeira: Callable[[str], None] | None = None, pai: QWidget | None = None):
        super().__init__(pai)
        self._config = configuracoes
        self._obter_relatorio = obter_relatorio
        self._lixeira = lixeira
        self._espaco: EspacoTrabalho | None = None
        self._geracao = 0
        self._caixas_extensao: list[QCheckBox] = []
        self._montar()

    # --- Montagem ----------------------------------------------------------------------

    def _montar(self) -> None:
        self.seletor = SeletorPasta("Pasta de trabalho:", CHAVE_PASTA, self._config)
        self.lista_modos = QListWidget()
        self.lista_modos.addItems(MODOS)
        self.lista_modos.setWordWrap(True)

        self.area_parametros = QStackedWidget()
        aviso = QLabel("Os itens encontrados aparecem na tabela. Confira e desmarque o que "
                       "não deve ir para a Lixeira.")
        aviso.setWordWrap(True)
        self.area_parametros.addWidget(aviso)
        pagina_ext = QWidget()
        self._layout_extensoes = QVBoxLayout(pagina_ext)
        self.botao_gerar_ext = QPushButton("Gerar prévia")
        self._layout_extensoes.addWidget(QLabel("Extensões:"))
        self._layout_extensoes.addStretch(1)
        self._layout_extensoes.addWidget(self.botao_gerar_ext)
        self.area_parametros.addWidget(pagina_ext)
        pagina_lista = QWidget()
        layout_lista = QVBoxLayout(pagina_lista)
        self.rotulo_instrucao = QLabel()
        self.rotulo_instrucao.setWordWrap(True)
        self.campo_lista = QPlainTextEdit()
        self.botao_gerar = QPushButton("Gerar prévia")
        layout_lista.addWidget(self.rotulo_instrucao)
        layout_lista.addWidget(self.campo_lista, 1)
        layout_lista.addWidget(self.botao_gerar)
        self.area_parametros.addWidget(pagina_lista)

        esquerda = QWidget()
        layout_esq = QVBoxLayout(esquerda)
        layout_esq.setContentsMargins(0, 0, 0, 0)
        layout_esq.addWidget(QLabel("O que enviar à Lixeira?"))
        layout_esq.addWidget(self.lista_modos, 2)
        layout_esq.addWidget(self.area_parametros, 1)

        self.rotulo_erro = QLabel()
        self.rotulo_erro.setWordWrap(True)
        self.rotulo_erro.setStyleSheet("color: #c62828;")
        self.tabela = TabelaItens(["Caminho", "Tipo"], marcavel=True)
        self.botao_marcar = QPushButton("Marcar todos")
        self.botao_desmarcar = QPushButton("Desmarcar todos")
        self.botao_enviar = QPushButton("Enviar 0 itens à Lixeira")
        self.botao_enviar.setEnabled(False)
        rodape = QHBoxLayout()
        rodape.addWidget(self.botao_marcar)
        rodape.addWidget(self.botao_desmarcar)
        rodape.addStretch(1)
        rodape.addWidget(self.botao_enviar)
        direita = QWidget()
        layout_dir = QVBoxLayout(direita)
        layout_dir.setContentsMargins(0, 0, 0, 0)
        layout_dir.addWidget(self.rotulo_erro)
        layout_dir.addWidget(self.tabela, 1)
        layout_dir.addLayout(rodape)

        divisor = QSplitter()
        divisor.addWidget(esquerda)
        divisor.addWidget(direita)
        divisor.setSizes([330, 800])
        layout = QVBoxLayout(self)
        layout.addWidget(self.seletor)
        layout.addWidget(divisor, 1)

        self.lista_modos.currentRowChanged.connect(self._ao_mudar_modo)
        self.seletor.pasta_alterada.connect(lambda _: self._ao_mudar_modo(self._modo()))
        self.botao_gerar.clicked.connect(self._gerar_previa_lista)
        self.botao_gerar_ext.clicked.connect(self._gerar_previa_extensoes)
        self.botao_marcar.clicked.connect(lambda: self.tabela.marcar_todos(True))
        self.botao_desmarcar.clicked.connect(lambda: self.tabela.marcar_todos(False))
        self.tabela.marcacao_alterada.connect(self._atualizar_botao)
        self.botao_enviar.clicked.connect(self._enviar)

    # --- Prévia ------------------------------------------------------------------------

    def _modo(self) -> int:
        return self.lista_modos.currentRow()

    def _limpar_previa(self, mensagem: str = "") -> None:
        self._geracao += 1
        self.tabela.limpar()
        self.rotulo_erro.setText(mensagem)

    def _ao_mudar_modo(self, modo: int) -> None:
        self._limpar_previa()
        if modo < 0:
            return
        if modo == MODO_EXTENSOES:
            self.area_parametros.setCurrentIndex(1)
            self._carregar_extensoes()
        elif modo in INSTRUCOES:
            self.area_parametros.setCurrentIndex(2)
            self.rotulo_instrucao.setText(INSTRUCOES[modo])
        else:
            self.area_parametros.setCurrentIndex(0)
            self._gerar_previa(lambda espaco: (AUTOMATICOS[modo](espaco), []),
                               marcados=modo != MODO_INDIVIDUAL)

    def _texto_pasta(self) -> str | None:
        texto = self.seletor.campo.text().strip()
        if not texto:
            self.rotulo_erro.setText("Escolha a pasta de trabalho.")
            return None
        return texto

    def _carregar_extensoes(self) -> None:
        for caixa in self._caixas_extensao:
            caixa.deleteLater()
        self._caixas_extensao = []
        texto = self._texto_pasta()
        if texto is None:
            return
        geracao = self._geracao

        def ao_concluir(extensoes: list[str]) -> None:
            if geracao != self._geracao:
                return
            for posicao, extensao in enumerate(extensoes, 1):
                caixa = QCheckBox(extensao)
                self._caixas_extensao.append(caixa)
                self._layout_extensoes.insertWidget(posicao, caixa)
            if not extensoes:
                self.rotulo_erro.setText("Não há arquivos não PDF nesta pasta.")

        executar_em_segundo_plano(
            self, lambda ctx: limpeza.extensoes_disponiveis(EspacoTrabalho.abrir(texto)),
            ao_concluir=ao_concluir, ao_falhar=self._ao_falhar_previa)

    def _gerar_previa_extensoes(self) -> None:
        escolhidas = {c.text() for c in self._caixas_extensao if c.isChecked()}
        if not escolhidas:
            self._limpar_previa("Escolha ao menos uma extensão.")
            return
        self._gerar_previa(
            lambda espaco: (limpeza.selecionar_por_extensoes(espaco, escolhidas), []))

    def _gerar_previa_lista(self) -> None:
        texto, modo = self.campo_lista.toPlainText(), self._modo()
        if modo == MODO_MANTER_ARQUIVOS:
            self._gerar_previa(
                lambda espaco: (limpeza.selecionar_manter_arquivos(espaco, texto), []))
        elif modo == MODO_MANTER_PASTAS:
            self._gerar_previa(lambda espaco: limpeza.selecionar_manter_pastas(espaco, texto))

    def _gerar_previa(self, seletor: Callable[[EspacoTrabalho], tuple[list, list]],
                      marcados: bool = True) -> None:
        self._limpar_previa()
        texto = self._texto_pasta()
        if texto is None:
            return
        geracao = self._geracao
        self.rotulo_erro.setText("Procurando…")

        def tarefa(ctx) -> Previa:
            espaco = EspacoTrabalho.abrir(texto)
            itens, mantidas = seletor(espaco)
            return espaco, itens, mantidas

        def ao_concluir(previa: Previa) -> None:
            if geracao == self._geracao:
                self._mostrar_previa(previa, marcados)

        def ao_falhar(mensagem: str, itens: list) -> None:
            if geracao == self._geracao:
                self._ao_falhar_previa(mensagem, itens)

        executar_em_segundo_plano(self, tarefa, ao_concluir=ao_concluir, ao_falhar=ao_falhar)

    def _mostrar_previa(self, previa: Previa, marcados: bool) -> None:
        espaco, itens, mantidas = previa
        self._espaco = espaco
        linhas = [[espaco.relativo(i.caminho), i.tipo] for i in itens]
        linhas += [[espaco.relativo(p), "MANTER"] for p in mantidas]
        self.tabela.definir_linhas(linhas, [*itens, *mantidas], marcados=marcados)
        for indice in range(len(itens), len(itens) + len(mantidas)):
            self.tabela.bloquear_marcacao(indice)
        self.rotulo_erro.setText("" if itens else "Nenhum arquivo selecionado.")
        self._atualizar_botao()

    def _ao_falhar_previa(self, mensagem: str, itens: list) -> None:
        self.rotulo_erro.setText(f"{mensagem}\n{listar_itens(itens)}".strip())
        self._atualizar_botao()

    # --- Envio -------------------------------------------------------------------------

    def _selecionados(self) -> list[ItemLimpeza]:
        return [i for i in self.tabela.marcados() if isinstance(i, ItemLimpeza)]

    def _atualizar_botao(self) -> None:
        quantidade = len(self._selecionados())
        self.botao_enviar.setText(f"Enviar {quantidade} itens à Lixeira")
        self.botao_enviar.setEnabled(quantidade > 0)

    def _ocupado(self, ocupado: bool) -> None:
        """Durante o envio nada pode trocar a tabela (os status são gravados por linha)."""
        for widget in (self.seletor, self.lista_modos, self.area_parametros,
                       self.botao_marcar, self.botao_desmarcar):
            widget.setEnabled(not ocupado)
        if ocupado:
            self.botao_enviar.setEnabled(False)
        else:
            self._atualizar_botao()

    def _enviar(self) -> None:
        itens, espaco = self._selecionados(), self._espaco
        if not itens or espaco is None:
            return
        if not confirmar(self, "Enviar à Lixeira",
                         f"Enviar {len(itens)} item(ns) à Lixeira?\n\n"
                         f"{listar_itens([espaco.relativo(i.caminho) for i in itens])}"):
            return
        relatorio = self._obter_relatorio()
        linhas = {id(item): indice for indice, item in enumerate(self.tabela.dados())}
        self._ocupado(True)

        def ao_concluir(resultados: list[ResultadoLimpeza]) -> None:
            self._ocupado(False)
            self._geracao += 1  # a prévia deixa de valer; gere outra para continuar
            for resultado in resultados:
                erro = resultado.status == "erro"
                texto = f"erro: {resultado.detalhe}" if erro else resultado.status
                self.tabela.definir_status(linhas[id(resultado.item)], texto, erro=erro)
            self.tabela.marcar_todos(False)
            enviados = sum(r.status != "erro" for r in resultados)
            self.rotulo_erro.setText("\n".join([
                f"{enviados} enviado(s) à Lixeira; {len(resultados) - enviados} erro(s).",
                *relatorio.erros]))

        def ao_falhar(mensagem: str, itens_erro: list) -> None:
            self._ocupado(False)
            mostrar_erro(self, "Limpeza", mensagem, itens_erro)

        executar_em_segundo_plano(
            self, lambda ctx: limpeza.enviar_lixeira(espaco, itens, relatorio,
                                                     lixeira=self._lixeira),
            ao_concluir=ao_concluir, ao_falhar=ao_falhar)
