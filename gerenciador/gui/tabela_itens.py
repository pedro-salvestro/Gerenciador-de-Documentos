"""Tabela reutilizável: colunas de texto, coluna 'Status' e caixas de seleção opcionais."""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

COR_ERRO = QColor("#c62828")
COR_OK = QColor("#2e7d32")


class TabelaItens(QTableView):
    marcacao_alterada = Signal()

    def __init__(self, colunas: list[str], marcavel: bool = False, pai=None):
        super().__init__(pai)
        self._marcavel = marcavel
        self._dados: list[object] = []
        self._fonte = QStandardItemModel(0, len(colunas) + 1, self)
        self._fonte.setHorizontalHeaderLabels([*colunas, "Status"])
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._fonte)
        self._proxy.setFilterKeyColumn(-1)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setModel(self._proxy)
        self._fonte.itemChanged.connect(self._ao_mudar_item)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        cabecalho = self.horizontalHeader()
        cabecalho.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        cabecalho.setStretchLastSection(True)
        cabecalho.resizeSection(0, 420)

    @property
    def coluna_status(self) -> int:
        return self._fonte.columnCount() - 1

    def limpar(self) -> None:
        self.definir_linhas([], [])

    def definir_linhas(self, linhas: list[list[str]], dados: list[object],
                       marcados: bool = False) -> None:
        """Substitui o conteúdo. O modelo novo é montado desconectado do filtro/ordenação
        (preencher célula a célula com a ordenação ligada é quadrático)."""
        cabecalhos = [self._fonte.headerData(c, Qt.Orientation.Horizontal)
                      for c in range(self._fonte.columnCount())]
        estado = Qt.CheckState.Checked if marcados else Qt.CheckState.Unchecked
        novo = QStandardItemModel(0, len(cabecalhos), self)
        novo.setHorizontalHeaderLabels(cabecalhos)
        for valores in linhas:
            itens = [QStandardItem(str(valor)) for valor in [*valores, ""]]
            if self._marcavel:
                itens[0].setCheckable(True)
                itens[0].setCheckState(estado)
            novo.appendRow(itens)
        antigo, self._fonte = self._fonte, novo
        self._dados = list(dados)
        self._proxy.setSourceModel(novo)
        novo.itemChanged.connect(self._ao_mudar_item)
        antigo.deleteLater()
        self._ajustar_colunas()
        self.marcacao_alterada.emit()

    def _ajustar_colunas(self) -> None:
        """Ajusta as colunas ao conteúdo; o caminho fica entre 300 e 520 px."""
        if not self._fonte.rowCount():
            return
        for coluna in range(1, self.coluna_status):
            self.resizeColumnToContents(coluna)
        self.resizeColumnToContents(0)
        self.setColumnWidth(0, max(300, min(self.columnWidth(0), 520)))

    def quantidade(self) -> int:
        return self._fonte.rowCount()

    def dados(self) -> list[object]:
        return list(self._dados)

    def marcados(self) -> list[object]:
        if not self._marcavel:
            return list(self._dados)
        return [self._dados[linha] for linha in range(self._fonte.rowCount())
                if self._fonte.item(linha, 0).isCheckable()
                and self._fonte.item(linha, 0).checkState() == Qt.CheckState.Checked]

    def marcar_todos(self, marcado: bool) -> None:
        estado = Qt.CheckState.Checked if marcado else Qt.CheckState.Unchecked
        for linha in range(self._fonte.rowCount()):
            item = self._fonte.item(linha, 0)
            if item.isCheckable():
                item.setCheckState(estado)

    def bloquear_marcacao(self, indice: int) -> None:
        """Linha só informativa (ex.: pasta mantida): sem caixa de seleção."""
        item = self._fonte.item(indice, 0)
        item.setCheckable(False)
        item.setData(None, Qt.ItemDataRole.CheckStateRole)

    def definir_status(self, indice: int, texto: str, erro: bool = False) -> None:
        item = self._fonte.item(indice, self.coluna_status)
        item.setText(texto)
        item.setForeground(QBrush(COR_ERRO if erro else COR_OK))

    def status(self, indice: int) -> str:
        return self._fonte.item(indice, self.coluna_status).text()

    def _ao_mudar_item(self, item: QStandardItem) -> None:
        if item.column() == 0 and self._marcavel:
            self.marcacao_alterada.emit()

    def filtrar(self, texto: str) -> None:
        self._proxy.setFilterKeyColumn(-1)
        self._proxy.setFilterFixedString(texto)

    def filtrar_coluna(self, coluna: int, texto: str) -> None:
        self._proxy.setFilterKeyColumn(coluna if texto else -1)
        self._proxy.setFilterFixedString(texto)
