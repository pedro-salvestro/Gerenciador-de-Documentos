"""Aba principal: fluxo de entrega (pasta nova só com PDFs dos tipos permitidos)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Executor
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
    QWidget,
)

from ..nucleo.conversao import converter_arquivo, processos_padrao
from ..nucleo.erros import ErroValidacao
from ..nucleo.fluxo import (
    COPIAR, CONVERTER, IGNORAR, MANTER, ParametrosFluxo, PlanoFluxo, ResumoFluxo, executar_fluxo,
    planejar_fluxo, separar_selecao, separar_tipos,
)
from ..nucleo.constantes import TIPOS_PADRAO
from ..nucleo.relatorios import Relatorio
from .configuracoes import Configuracoes
from .dialogos import confirmar, listar_itens, mostrar_erro
from .seletor_pasta import SeletorPasta
from .tabela_itens import TabelaItens
from .trabalhador import Trabalhador, executar_em_segundo_plano

ROTULO_ACAO = {COPIAR: "Copiar", CONVERTER: "Converter", IGNORAR: "Fora da entrega",
               MANTER: "Já existe (mantido)"}
FILTROS = ("Todos", "Copiar", "Converter", "Já existe", "Fora da entrega")
TEXTO_SUBSTITUIR = "Substituir PDFs que já existem (os antigos vão para a Lixeira)"
CHAVE_MODO = "fluxo/pasta_existente"
LIMITE_PROBLEMAS_RESUMO = 5


def resumir_problemas(problemas: list[tuple[str, str]]) -> str:
    """'Itens da lista com problema: A (motivo), B (motivo) e mais N'."""
    partes = [f"{item} ({motivo})" for item, motivo in problemas[:LIMITE_PROBLEMAS_RESUMO]]
    texto = "Itens da lista com problema: " + ", ".join(partes)
    if len(problemas) > LIMITE_PROBLEMAS_RESUMO:
        texto += f" e mais {len(problemas) - LIMITE_PROBLEMAS_RESUMO}"
    return texto


class AbaFluxo(QWidget):
    def __init__(self, configuracoes: Configuracoes, obter_relatorio: Callable[[], Relatorio],
                 funcao_conversao: Callable[..., tuple[str, str]] = converter_arquivo,
                 criar_executor: Callable[[int], Executor] | None = None,
                 lixeira: Callable[[str], None] | None = None,
                 pai: QWidget | None = None):
        super().__init__(pai)
        self._lixeira = lixeira
        self._config = configuracoes
        self._obter_relatorio = obter_relatorio
        self._funcao_conversao = funcao_conversao
        self._criar_executor = criar_executor
        self._plano: PlanoFluxo | None = None
        self._trabalhador: Trabalhador | None = None
        self._destino_final: Path | None = None
        self._relatorio: Relatorio | None = None
        self._montar()
        self._carregar_preferencias()
        self._conectar()
        self._atualizar_destino()

    # --- Montagem ----------------------------------------------------------------------

    def _montar(self) -> None:
        self.seletor_base = SeletorPasta("", "fluxo/base", self._config)
        self.opcao_nova = QRadioButton("Criar pasta nova")
        self.opcao_existente = QRadioButton("Adicionar a uma pasta existente")
        self.opcao_nova.setChecked(True)
        self._grupo_modo = QButtonGroup(self)
        self._grupo_modo.addButton(self.opcao_nova)
        self._grupo_modo.addButton(self.opcao_existente)
        modo = QHBoxLayout()
        modo.addWidget(self.opcao_nova)
        modo.addWidget(self.opcao_existente)
        modo.addStretch(1)
        self.caixa_substituir = QCheckBox(TEXTO_SUBSTITUIR)
        self.caixa_substituir.setToolTip(
            "Desmarcado: os PDFs que já estão na pasta são mantidos e só entra o que é novo.")
        self.caixa_substituir.setVisible(False)
        self.campo_nome = QLineEdit()
        self.campo_nome.setPlaceholderText("Ex.: Obra X - Entrega")
        self.seletor_destino = SeletorPasta("", "fluxo/destino", self._config)
        self.seletor_destino.campo.setPlaceholderText("Vazio = ao lado da pasta base")
        self.rotulo_destino = QLabel()
        self.rotulo_destino.setStyleSheet("font-style: italic;")
        self.campo_tipos = QLineEdit()
        self.campo_tipos.setToolTip("Códigos de duas letras separados por vírgula. "
                                    "O tipo vem do fim do nome: NVC00410A-DE-001 → DE.")
        self.campo_selecao = QPlainTextEdit()
        self.campo_selecao.setPlaceholderText(
            "Vazio = todos. Ex.: NVC00410A, NVC00411, NVC00412A-DE-001")
        self.campo_selecao.setToolTip(
            "Um por linha ou separados por vírgula.\n"
            "NVC00410 → todas as variantes · NVC00410A → só essa variante · "
            "NVC00410A-DE-001 → só esse arquivo.")
        self.campo_selecao.setFixedHeight(
            self.campo_selecao.fontMetrics().lineSpacing() * 3 + 12)
        self.caixa_converter = QCheckBox("Converter Word/Excel para PDF")
        self.campo_processos = QSpinBox()
        self.campo_processos.setRange(1, 16)
        self.campo_processos.setToolTip("Quantas conversões ao mesmo tempo.")

        opcoes = QHBoxLayout()
        opcoes.addWidget(self.caixa_converter)
        opcoes.addSpacing(24)
        opcoes.addWidget(QLabel("Processos simultâneos:"))
        opcoes.addWidget(self.campo_processos)
        opcoes.addStretch(1)

        formulario = QFormLayout()
        formulario.addRow("Pasta base:", self.seletor_base)
        formulario.addRow("Destino:", modo)
        formulario.addRow("Nome da pasta nova:", self.campo_nome)
        formulario.addRow("Salvar em:", self.seletor_destino)
        formulario.addRow("", self.rotulo_destino)
        formulario.addRow("", self.caixa_substituir)
        formulario.addRow("Tipos mantidos:", self.campo_tipos)
        formulario.addRow("NVCs / arquivos:", self.campo_selecao)
        formulario.addRow("Opções:", opcoes)
        grupo = QGroupBox("O que fazer")
        grupo.setLayout(formulario)

        self.botao_analisar = QPushButton("Analisar")
        self.botao_analisar.setDefault(True)
        self.rotulo_resumo = QLabel("Escolha a pasta base e o nome da pasta nova, depois "
                                    "clique em Analisar.")
        self.rotulo_resumo.setWordWrap(True)
        linha_analisar = QHBoxLayout()
        linha_analisar.addWidget(self.rotulo_resumo, 1)
        linha_analisar.addWidget(self.botao_analisar)

        self.filtro_acao = QComboBox()
        self.filtro_acao.addItems(FILTROS)
        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText("Buscar arquivo…")
        linha_filtro = QHBoxLayout()
        linha_filtro.addWidget(QLabel("Mostrar:"))
        linha_filtro.addWidget(self.filtro_acao)
        linha_filtro.addWidget(self.campo_busca, 1)
        self.tabela = TabelaItens(["Arquivo", "Ação", "Motivo"])

        self.barra = QProgressBar()
        self.barra.setVisible(False)
        self.rotulo_etapa = QLabel()
        self.botao_cancelar = QPushButton("Cancelar")
        self.botao_cancelar.setVisible(False)
        linha_progresso = QHBoxLayout()
        linha_progresso.addWidget(self.barra, 1)
        linha_progresso.addWidget(self.rotulo_etapa)
        linha_progresso.addWidget(self.botao_cancelar)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        self.log.setPlaceholderText("Registro da execução")

        self.botao_abrir_pasta = QPushButton("Abrir pasta")
        self.botao_abrir_pasta.setEnabled(False)
        self.botao_executar = QPushButton("Executar fluxo")
        self.botao_executar.setEnabled(False)
        linha_acoes = QHBoxLayout()
        linha_acoes.addStretch(1)
        linha_acoes.addWidget(self.botao_abrir_pasta)
        linha_acoes.addWidget(self.botao_executar)

        layout = QVBoxLayout(self)
        layout.addWidget(grupo)
        layout.addLayout(linha_analisar)
        layout.addLayout(linha_filtro)
        layout.addWidget(self.tabela, 1)
        layout.addLayout(linha_progresso)
        layout.addWidget(self.log)
        layout.addLayout(linha_acoes)

    def _carregar_preferencias(self) -> None:
        self.campo_nome.setText(str(self._config.valor("fluxo/nome", "") or ""))
        self.campo_tipos.setText(str(self._config.valor("fluxo/tipos", ", ".join(TIPOS_PADRAO))))
        self.campo_selecao.setPlainText(str(self._config.valor("fluxo/selecao", "") or ""))
        self.caixa_converter.setChecked(self._config.valor_bool("fluxo/converter", True))
        self.campo_processos.setValue(
            self._config.valor_int("fluxo/processos", processos_padrao(16)))
        if self._config.valor_bool(CHAVE_MODO, False):
            self.opcao_existente.setChecked(True)
        self._aplicar_modo()

    def _conectar(self) -> None:
        self.seletor_base.pasta_alterada.connect(lambda _: self._parametros_mudaram())
        self.seletor_destino.campo.textChanged.connect(self._parametros_mudaram)
        self.campo_nome.textChanged.connect(self._parametros_mudaram)
        self.campo_tipos.textChanged.connect(self._parametros_mudaram)
        self.campo_selecao.textChanged.connect(self._parametros_mudaram)
        self.caixa_converter.toggled.connect(self._parametros_mudaram)
        self.opcao_existente.toggled.connect(self._modo_mudou)
        self.caixa_substituir.toggled.connect(self._parametros_mudaram)
        self.campo_processos.valueChanged.connect(
            lambda v: self._config.definir("fluxo/processos", v))
        self.filtro_acao.currentTextChanged.connect(self._aplicar_filtro)
        self.campo_busca.textChanged.connect(self.tabela.filtrar)
        self.botao_analisar.clicked.connect(self._analisar)
        self.botao_executar.clicked.connect(self._executar)
        self.botao_cancelar.clicked.connect(self._cancelar)
        self.botao_abrir_pasta.clicked.connect(self._abrir_pasta)

    # --- Parâmetros --------------------------------------------------------------------

    def _parametros_mudaram(self, *_args) -> None:
        self._config.definir("fluxo/nome", self.campo_nome.text())
        self._config.definir("fluxo/tipos", self.campo_tipos.text())
        self._config.definir("fluxo/selecao", self.campo_selecao.toPlainText())
        self._config.definir("fluxo/converter", self.caixa_converter.isChecked())
        self._plano = None
        self.botao_executar.setEnabled(False)
        self._atualizar_destino()

    def _modo_existente(self) -> bool:
        return self.opcao_existente.isChecked()

    def _aplicar_modo(self) -> None:
        existente = self._modo_existente()
        self.campo_nome.setEnabled(not existente)
        self.caixa_substituir.setVisible(existente)
        if not existente:
            self.caixa_substituir.setChecked(False)
        # "Salvar em" significa coisas diferentes em cada modo (pasta-pai x a própria
        # entrega): cada modo lembra a sua, para não herdar a pasta-pai por engano.
        self.seletor_destino.trocar_chave(
            "fluxo/destino_existente" if existente else "fluxo/destino")
        self.seletor_destino.campo.setPlaceholderText(
            "Pasta da entrega já existente" if existente else "Vazio = ao lado da pasta base")

    def _modo_mudou(self, *_args) -> None:
        self._config.definir(CHAVE_MODO, self._modo_existente())
        self._aplicar_modo()
        self._parametros_mudaram()

    def _texto_base(self) -> str:
        return self.seletor_base.campo.text().strip()

    def _texto_destino(self) -> str:
        return self.seletor_destino.campo.text().strip()

    def _atualizar_destino(self) -> None:
        if self._modo_existente():
            self.rotulo_destino.setText(
                f"→ os PDFs serão adicionados em: {self._texto_destino()}"
                if self._texto_destino() else '→ escolha a pasta existente em "Salvar em"')
            return
        base, nome = self._texto_base(), self.campo_nome.text().strip()
        pasta = self._texto_destino() or (str(Path(base).parent) if base else "")
        if pasta and nome:
            self.rotulo_destino.setText(f"→ será criada: {Path(pasta) / nome}")
        elif self._texto_destino():
            self.rotulo_destino.setText(f"→ a pasta nova é criada em {self._texto_destino()}")
        else:
            self.rotulo_destino.setText("→ a pasta nova é criada ao lado da pasta base")

    def _parametros(self) -> ParametrosFluxo:
        if not self._texto_base():
            raise ErroValidacao("Escolha a pasta base.")
        destino = self._texto_destino()
        return ParametrosFluxo(
            base=Path(self._texto_base()), nome_destino=self.campo_nome.text(),
            tipos=separar_tipos(self.campo_tipos.text()),
            converter=self.caixa_converter.isChecked(),
            processos=self.campo_processos.value(),
            pasta_destino=Path(destino) if destino else None,
            selecao=separar_selecao(self.campo_selecao.toPlainText()),
            pasta_existente=self._modo_existente(),
            substituir_existentes=self._modo_existente() and self.caixa_substituir.isChecked())

    def _aplicar_filtro(self, texto: str) -> None:
        self.tabela.filtrar_coluna(1, "" if texto == "Todos" else texto)

    # --- Análise -----------------------------------------------------------------------

    def _analisar(self) -> None:
        try:
            parametros = self._parametros()
        except ErroValidacao as erro:
            mostrar_erro(self, "Não foi possível analisar", erro.mensagem, erro.itens)
            return
        self._definir_ocupado(True, cancelavel=False)
        self.rotulo_resumo.setText("Analisando a pasta base…")
        self._trabalhador = executar_em_segundo_plano(
            self, lambda ctx: planejar_fluxo(parametros),
            ao_concluir=self._ao_analisar, ao_falhar=self._ao_falhar_analise)

    def _ao_analisar(self, plano: PlanoFluxo) -> None:
        self._definir_ocupado(False)
        self._plano = plano
        conflitos = {str(c).casefold() for c in plano.conflitos}
        destino_trabalho = iter(plano.trabalhos)
        linhas = []
        for item in plano.itens:
            motivo = item.motivo
            if item.acao == CONVERTER:
                trabalho = next(destino_trabalho)
                if str(trabalho.destino).casefold() in conflitos:
                    motivo = "o PDF convertido substitui o PDF existente"
            linhas.append([item.origem.relative_to(plano.base).as_posix(),
                           ROTULO_ACAO[item.acao], motivo])
        self.tabela.definir_linhas(linhas, plano.itens)
        partes = [f"{len(plano.a_copiar)} PDFs a copiar",
                  f"{len(plano.a_converter)} Word/Excel a converter",
                  f"{len(plano.ignorados)} fora da entrega"]
        if plano.mantidos:
            partes.append(f"{len(plano.mantidos)} já existem (mantidos)")
        if plano.a_substituir:
            partes.append(f"{len(plano.a_substituir)} PDFs serão substituídos")
        if plano.conflitos:
            partes.append(f"{len(plano.conflitos)} conflitos de PDF")
        rotulo = "Pasta existente" if plano.parametros.pasta_existente else "Pasta nova"
        texto = " · ".join(partes) + f"\n{rotulo}: {plano.destino_raiz}"
        if plano.problemas:
            texto += "\n" + resumir_problemas(plano.problemas)
        self.rotulo_resumo.setText(texto)
        self.botao_executar.setEnabled(bool(plano.a_copiar or plano.a_converter))

    def _ao_falhar_analise(self, mensagem: str, itens: list) -> None:
        self._definir_ocupado(False)
        self.rotulo_resumo.setText(mensagem)
        mostrar_erro(self, "Não foi possível analisar", mensagem, itens)

    # --- Execução ----------------------------------------------------------------------

    def _executar(self) -> None:
        plano = self._plano
        if plano is None:
            return
        plano.parametros.processos = self.campo_processos.value()
        aviso = ""
        if plano.problemas:
            aviso = ("Estes itens da lista não vão entrar:\n"
                     + listar_itens([f"{item} — {motivo}" for item, motivo in plano.problemas])
                     + "\n\nDeseja continuar sem eles?\n\n")
        existente = plano.parametros.pasta_existente
        linhas_existentes = ""
        if plano.mantidos:
            linhas_existentes += f"• {len(plano.mantidos)} já existem na pasta e serão mantidos\n"
        if plano.a_substituir:
            linhas_existentes += (f"• {len(plano.a_substituir)} PDFs existentes serão "
                                  "substituídos (os antigos vão para a Lixeira)\n")
        if not confirmar(
                self, "Executar fluxo",
                f"{aviso}{'Adicionar à pasta' if existente else 'Criar a pasta'}:\n"
                f"{plano.destino_raiz}\n\n"
                f"• {len(plano.a_copiar)} PDFs serão copiados\n"
                f"• {len(plano.a_converter)} Word/Excel serão convertidos\n"
                f"{linhas_existentes}"
                f"• {len(plano.ignorados)} arquivos ficam fora da entrega\n\n"
                "A pasta base não será alterada. Continuar?"):
            return
        relatorio = self._relatorio = self._obter_relatorio()
        self.log.clear()
        self._destino_final = plano.destino_raiz
        self.botao_abrir_pasta.setEnabled(False)
        self._definir_ocupado(True, cancelavel=True)
        self.rotulo_resumo.setText("Executando…")
        self._trabalhador = executar_em_segundo_plano(
            self,
            lambda ctx: executar_fluxo(
                plano, relatorio, ao_progresso=ctx.progresso, ao_log=ctx.log,
                cancelado=ctx.cancelado, funcao_conversao=self._funcao_conversao,
                criar_executor=self._criar_executor, lixeira=self._lixeira),
            ao_concluir=self._ao_executar, ao_falhar=self._ao_falhar_execucao,
            ao_progresso=self._ao_progresso, ao_log=self.log.appendPlainText)

    def _ao_progresso(self, etapa: str, atual: int, total: int) -> None:
        self.barra.setMaximum(max(total, 1))
        self.barra.setValue(atual)
        self.rotulo_etapa.setText(f"{etapa} {atual}/{total}")

    def _ao_executar(self, resumo: ResumoFluxo) -> None:
        self._definir_ocupado(False)
        self._plano = None
        self.botao_executar.setEnabled(False)
        self.botao_abrir_pasta.setEnabled(True)
        situacao = "Interrompido" if resumo.cancelado else "Concluído"
        self.rotulo_resumo.setText(
            f"{situacao} · {resumo.copiados} PDFs copiados · {resumo.convertidos} convertidos"
            f" · {resumo.mantidos} mantidos"
            + (f" · {resumo.substituidos} substituídos" if resumo.substituidos else "")
            + f" · {len(resumo.erros)} erros · {resumo.ignorados} fora da entrega"
            f"\nPasta: {resumo.destino_raiz}")
        if resumo.erros:
            self.log.appendPlainText("\nArquivos com erro:")
            for arquivo, detalhe in resumo.erros:
                self.log.appendPlainText(f" • {arquivo}: {detalhe}")
        for aviso in self._relatorio.erros if self._relatorio else []:
            self.log.appendPlainText(f"AVISO: {aviso}")

    def _ao_falhar_execucao(self, mensagem: str, itens: list) -> None:
        self._definir_ocupado(False)
        self._plano = None
        self.botao_executar.setEnabled(False)
        self.rotulo_resumo.setText(mensagem)
        mostrar_erro(self, "O fluxo não foi concluído", mensagem, itens)

    def _cancelar(self) -> None:
        if self._trabalhador is not None:
            self._trabalhador.cancelar()
            self.botao_cancelar.setEnabled(False)
            self.log.appendPlainText("Cancelando: as conversões em andamento serão concluídas…")

    def _abrir_pasta(self) -> None:
        if self._destino_final and self._destino_final.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._destino_final)))

    def _definir_ocupado(self, ocupado: bool, cancelavel: bool = False) -> None:
        for widget in (self.seletor_base, self.campo_nome, self.seletor_destino,
                       self.opcao_nova, self.opcao_existente, self.caixa_substituir,
                       self.campo_tipos, self.campo_selecao, self.caixa_converter,
                       self.campo_processos, self.botao_analisar):
            widget.setEnabled(not ocupado)
        if not ocupado:
            self.campo_nome.setEnabled(not self._modo_existente())
        if ocupado:
            self.botao_executar.setEnabled(False)
        self.barra.setVisible(ocupado and cancelavel)
        self.barra.setValue(0)
        self.rotulo_etapa.setText("")
        self.botao_cancelar.setVisible(ocupado and cancelavel)
        self.botao_cancelar.setEnabled(True)
