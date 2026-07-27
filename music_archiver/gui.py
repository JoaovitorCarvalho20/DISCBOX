"""Interface gráfica (PyQt6) do DISCBOX.

Fluxo em duas etapas: "Buscar" só lê os metadados da Spotify (mostra capa e
lista de faixas, sem baixar nada) — dá ao usuário um ponto de controle pra
conferir/trocar pasta, formato e qualidade antes de confirmar em "Baixar".
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from downloader import SUPPORTED_FORMATS, ffmpeg_available
from main import download_tracks, fetch_tracks

_DONE_STATUSES = {"concluído", "já existe", "falhou", "não encontrado", "cancelado"}
_FAILURE_STATUSES = {"falhou", "não encontrado"}
_ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.svg"


class FetchWorker(QThread):
    """Só busca os metadados (capa + faixas) — não baixa nada."""

    tracks_ready = pyqtSignal(object, list)  # container_name, tracks
    cover_ready = pyqtSignal(bytes)
    failed = pyqtSignal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url

    def run(self) -> None:
        try:
            _, container_name, tracks = fetch_tracks(self.url)
        except Exception as e:
            self.failed.emit(str(e))
            return

        self.tracks_ready.emit(container_name, tracks)

        cover_url = tracks[0].get("cover_url") if tracks else None
        if not cover_url:
            return
        try:
            resp = requests.get(cover_url, timeout=15)
            if resp.status_code == 200 and resp.content:
                self.cover_ready.emit(resp.content)
        except requests.RequestException:
            pass


class DownloadWorker(QThread):
    """Baixa uma lista de faixas já buscada por FetchWorker."""

    track_status = pyqtSignal(int, str)
    finished_ok = pyqtSignal(int, int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        tracks: list[dict],
        container_name: str | None,
        output_dir: str,
        audio_format: str,
        audio_quality: str,
        selected_indices: set[int],
    ) -> None:
        super().__init__()
        self.tracks = tracks
        self.container_name = container_name
        self.output_dir = output_dir
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.selected_indices = selected_indices
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            ok, failed = download_tracks(
                self.tracks,
                self.container_name,
                output_dir=self.output_dir,
                audio_format=self.audio_format,
                audio_quality=self.audio_quality,
                on_track_status=self.track_status.emit,
                is_cancelled=self._cancel_event.is_set,
                selected_indices=self.selected_indices,
            )
            self.finished_ok.emit(ok, failed)
        except Exception as e:
            self.failed.emit(str(e))


class MainWindow(QMainWindow):
    """Janela principal: buscar prévia (capa + faixas), depois confirmar o download."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DISCBOX")
        if _ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self.resize(760, 580)
        self._fetch_worker: FetchWorker | None = None
        self._download_worker: DownloadWorker | None = None
        self._pending_tracks: list[dict] = []
        self._pending_container_name: str | None = None
        self._failed_labels: list[str] = []
        self._build_ui()

        if not ffmpeg_available():
            self.status_label.setText("Aviso: FFmpeg não encontrado no PATH. Instale-o antes de baixar.")

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout()

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Cole a URL de uma faixa, álbum ou playlist da Spotify")
        self.url_input.returnPressed.connect(self._on_search_clicked)
        url_row.addWidget(self.url_input)

        self.search_button = QPushButton("Buscar")
        self.search_button.clicked.connect(self._on_search_clicked)
        url_row.addWidget(self.search_button)

        self.download_button = QPushButton("Baixar")
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self._on_download_clicked)
        url_row.addWidget(self.download_button)

        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        url_row.addWidget(self.cancel_button)

        layout.addLayout(url_row)

        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabBar::tab { padding: 6px 16px; margin-right: 2px; border-top-left-radius: 4px;"
            " border-top-right-radius: 4px; }"
        )
        tabs.addTab(self._build_tracks_tab(), "Faixas")
        tabs.addTab(self._build_settings_tab(), "Configurações")
        layout.addWidget(tabs)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        bottom_row = QHBoxLayout()
        self.status_label = QLabel("Pronto.")
        bottom_row.addWidget(self.status_label, 1)

        self.view_failures_button = QPushButton("Ver falhas")
        self.view_failures_button.setVisible(False)
        self.view_failures_button.clicked.connect(self._on_view_failures_clicked)
        bottom_row.addWidget(self.view_failures_button)
        layout.addLayout(bottom_row)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _build_tracks_tab(self) -> QWidget:
        tab = QWidget()
        content_row = QHBoxLayout()

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(120, 120)
        self.cover_label.setScaledContents(True)
        self.cover_label.setStyleSheet("background-color: #222; border-radius: 4px;")
        content_row.addWidget(self.cover_label)

        info_col = QVBoxLayout()

        self.container_label = QLabel("Cole uma URL e clique em Buscar.")
        self.container_label.setStyleSheet("font-weight: bold;")
        info_col.addWidget(self.container_label)

        self._all_checked_state = True
        self.track_table = QTableWidget(0, 3)
        self.track_table.setHorizontalHeaderLabels(["Título", "Artista", "☑"])
        header = self.track_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_section_clicked)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        info_col.addWidget(self.track_table)

        content_row.addLayout(info_col)
        tab.setLayout(content_row)
        return tab

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        options_row = QHBoxLayout()

        saved = config.load_gui_settings()

        self.format_combo = QComboBox()
        self.format_combo.addItems(sorted(SUPPORTED_FORMATS.keys()))
        self.format_combo.setCurrentText(saved.get("audio_format") or config.AUDIO_FORMAT)
        options_row.addWidget(QLabel("Formato:"))
        options_row.addWidget(self.format_combo)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["128", "192", "256", "320"])
        self.quality_combo.setCurrentText(saved.get("audio_quality") or config.AUDIO_QUALITY)
        options_row.addWidget(QLabel("Qualidade (kbps):"))
        options_row.addWidget(self.quality_combo)

        self.output_dir = saved.get("output_dir") or str(config.DOWNLOAD_DIR)
        self.choose_folder_button = QPushButton("Pasta de destino...")
        self.choose_folder_button.clicked.connect(self._choose_folder)
        options_row.addWidget(self.choose_folder_button)

        options_row.addStretch()

        wrapper = QVBoxLayout()
        wrapper.addLayout(options_row)
        wrapper.addStretch()
        tab.setLayout(wrapper)

        # Conectado só agora que os três campos já existem, pra não salvar
        # um output_dir inexistente enquanto o combo ainda está sendo montado.
        self.format_combo.currentTextChanged.connect(self._save_settings)
        self.quality_combo.currentTextChanged.connect(self._save_settings)
        return tab

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Escolha a pasta de destino", self.output_dir)
        if folder:
            self.output_dir = folder
            self._save_settings()

    def _save_settings(self) -> None:
        config.save_gui_settings(
            {
                "audio_format": self.format_combo.currentText(),
                "audio_quality": self.quality_combo.currentText(),
                "output_dir": self.output_dir,
            }
        )

    # -- etapa 1: buscar metadados (prévia) ---------------------------------

    def _on_search_clicked(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("Cole uma URL da Spotify primeiro.")
            return

        self.search_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.container_label.setText("Buscando metadados...")
        self.cover_label.setPixmap(QPixmap())
        self.track_table.setRowCount(0)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label.setText("Buscando...")
        self._pending_tracks = []
        self._pending_container_name = None

        self._fetch_worker = FetchWorker(url)
        self._fetch_worker.tracks_ready.connect(self._on_tracks_ready)
        self._fetch_worker.cover_ready.connect(self._on_cover_ready)
        self._fetch_worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker.start()

    def _on_tracks_ready(self, container_name: str | None, tracks: list[dict]) -> None:
        self.search_button.setEnabled(True)
        self._pending_tracks = tracks
        self._pending_container_name = container_name

        if not tracks:
            self.container_label.setText("Nenhuma faixa encontrada.")
            self.status_label.setText("Nada para baixar.")
            return

        self.container_label.setText(container_name if container_name else tracks[0]["name"])
        self.track_table.setRowCount(len(tracks))
        for row, track in enumerate(tracks):
            self.track_table.setItem(row, 0, QTableWidgetItem(track["name"]))
            self.track_table.setItem(row, 1, QTableWidgetItem(track["artist"]))
            checkbox_item = QTableWidgetItem()
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checkbox_item.setCheckState(Qt.CheckState.Checked)
            checkbox_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.track_table.setItem(row, 2, checkbox_item)
        self._all_checked_state = True
        self.track_table.setHorizontalHeaderItem(2, QTableWidgetItem("☑"))
        self.progress_bar.setRange(0, len(tracks))
        self.progress_bar.setValue(0)

        self.download_button.setEnabled(True)
        self.status_label.setText(
            f"{len(tracks)} faixa(s) encontrada(s). Confira a pasta/formato e clique em Baixar."
        )

    def _on_fetch_failed(self, message: str) -> None:
        self.search_button.setEnabled(True)
        self.container_label.setText("Erro na busca.")
        self.status_label.setText(f"Erro: {message}")

    def _on_cover_ready(self, data: bytes) -> None:
        image = QImage.fromData(data)
        if not image.isNull():
            self.cover_label.setPixmap(QPixmap.fromImage(image))

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.track_table.rowCount()):
            item = self.track_table.item(row, 2)
            if item:
                item.setCheckState(state)

    def _on_header_section_clicked(self, section: int) -> None:
        if section != 2:
            return
        self._all_checked_state = not self._all_checked_state
        self._set_all_checked(self._all_checked_state)
        self.track_table.setHorizontalHeaderItem(
            2, QTableWidgetItem("☑" if self._all_checked_state else "☐")
        )

    def _selected_indices(self) -> set[int]:
        return {
            row
            for row in range(self.track_table.rowCount())
            if self.track_table.item(row, 2)
            and self.track_table.item(row, 2).checkState() == Qt.CheckState.Checked
        }

    # -- etapa 2: baixar (só depois de confirmar) ----------------------------

    def _on_download_clicked(self) -> None:
        if not self._pending_tracks:
            return
        if not ffmpeg_available():
            self.status_label.setText("FFmpeg não encontrado — instale-o para baixar.")
            return

        selected_indices = self._selected_indices()
        if not selected_indices:
            self.status_label.setText("Selecione ao menos uma faixa antes de baixar.")
            return

        self.search_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.view_failures_button.setVisible(False)
        self.status_label.setText("Baixando...")
        self.progress_bar.setRange(0, len(selected_indices))
        self.progress_bar.setValue(0)
        self._failed_labels = []

        self._download_worker = DownloadWorker(
            self._pending_tracks,
            self._pending_container_name,
            self.output_dir,
            self.format_combo.currentText(),
            self.quality_combo.currentText(),
            selected_indices,
        )
        self._download_worker.track_status.connect(self._on_track_status)
        self._download_worker.finished_ok.connect(self._on_finished)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.start()

    def _on_cancel_clicked(self) -> None:
        if self._download_worker:
            self._download_worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelando... (termina a faixa atual e para)")

    def _on_track_status(self, index: int, status: str) -> None:
        if status == "baixando" and index < len(self._pending_tracks):
            track = self._pending_tracks[index]
            self.status_label.setText(f"Baixando: {track['artist']} - {track['name']}")
        if status in _FAILURE_STATUSES and index < len(self._pending_tracks):
            track = self._pending_tracks[index]
            self._failed_labels.append(f"{track['artist']} - {track['name']}")
        if status in _DONE_STATUSES:
            self.progress_bar.setValue(self.progress_bar.value() + 1)

    def _on_finished(self, ok: int, failed: int) -> None:
        self.search_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText(f"Concluído: {ok} ok, {failed} falha(s).")
        if self._failed_labels:
            self.view_failures_button.setText(f"Ver falhas ({len(self._failed_labels)})")
            self.view_failures_button.setVisible(True)

    def _on_download_failed(self, message: str) -> None:
        self.search_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status_label.setText(f"Erro: {message}")

    def _on_view_failures_clicked(self) -> None:
        QMessageBox.information(
            self,
            "Faixas que falharam",
            "\n".join(self._failed_labels) if self._failed_labels else "Nenhuma falha.",
        )


def main() -> None:
    if sys.platform == "win32":
        # Sem isso o Windows agrupa a janela pelo python.exe (ícone da
        # cobrinha) em vez do ícone do app, porque o Explorer usa o
        # AppUserModelID do processo pra decidir o ícone da barra de
        # tarefas — e por padrão o python.exe não declara um próprio.
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("discbox.musicdownloader")
        except Exception:
            pass

        # Rodar com "python main.py --gui" (em vez de "pythonw") abre um
        # console junto — é essa janelinha preta que aparece na barra de
        # tarefas com o ícone do Python. Escondemos ela assim que a GUI
        # sobe, então funciona igual não importa qual dos dois foi usado.
        try:
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            if console_window:
                ctypes.windll.user32.ShowWindow(console_window, 0)  # SW_HIDE
        except Exception:
            pass

    app = QApplication(sys.argv)
    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
