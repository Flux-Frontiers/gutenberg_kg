"""
viz3d.py — 3-D Knowledge Tree Forest visualiser for GutenbergKG.

Each book is rendered as a tree:
  - Trunk   → document node (brown cylinder, height ∝ log(chunk_count))
  - Branches → section nodes (forest-green spheres radiating from trunk apex)
  - Leaves   → chunk nodes (light-green spheres clustered around each section)
  - Spores   → entity / topic nodes (gold dots floating above the canopy)

Books are grouped by genre into groves, with genres arranged in a large
Fibonacci annulus so the whole corpus forms a navigable 3-D forest.

This module is the **Qt viewer** only: corpus scanning, layout, and scene
composition live in :mod:`gutenberg_kg.scene`, which knows nothing about Qt so
the off-screen light-field renderer (``gutenkg quilt``) can share them.

Requires: pyvista, pyvistaqt, PyQt5, param, numpy
(all available in the pycode_kg environment).

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import atexit
import gc
import logging
import sys
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import param
import pyvista as pv
from markdown import markdown  # type: ignore[import-untyped]
from pycode_kg.layout3d import LayoutEdge, LayoutNode
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from pyvistaqt import QtInteractor
from rich.logging import RichHandler

from gutenberg_kg import __version__
from gutenberg_kg.scene import (
    DEFAULT_CORPUS,
    DEFAULT_SEASON,
    KIND_SIZE,
    SEASONS,
    BookMeta,
    SceneFilters,
    SceneInfo,
    build_forest_scene,
    build_tree_scene,
    load_book_graph,
    load_entry_times,
    make_node_mesh,
    scan_corpus,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING, handlers=[RichHandler()])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

__author__ = "Eric G. Suchanek, PhD"

DEFAULT_SAVE = "gutenberg_forest_3d"

CONTROL_PANEL_WIDTH: int = 260
BUTTON_WIDTH: int = 120
ZOOM_FACTOR: float = 8.0

#: Looking Glass preset the "Cast to LG" button renders for — the 16" Gen3
#: Landscape, matching the `gutenkg quilt` default.
QUILT_SPEC: str = "16-landscape"

#: Fraction of the preset's pixel size used when casting from the viewer.
#: Rendering a full 7680x4320 quilt costs about a second here but leaves Bridge
#: a 33-megapixel PNG to load and decode, which is where the wait actually is.
#: Halving each axis quarters that; the lenticular optics hide the difference.
#: `gutenkg quilt` still writes full resolution for files that get kept.
CAST_SCALE: float = 0.5


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------


def _text_to_markdown(text: str | None) -> str:
    """Format a raw text excerpt as Markdown for the popup.

    :param text: Raw node text (chunk content, entity name, etc.).
    :return: Markdown string.
    """
    if not text:
        return "No text available."
    return text.strip()


# ---------------------------------------------------------------------------
# DocstringPopup — reused from pycode_kg pattern
# ---------------------------------------------------------------------------


class TextPopup(QDialog):
    """
    Modeless popup that renders node text as Markdown HTML.

    :param title: Window title.
    :param text: Raw text content.
    :param parent: Parent widget.
    :param on_close_callback: Called when the window closes.
    """

    def __init__(self, title: str, text: str, parent=None, on_close_callback=None):
        """Build the popup dialog: title bar, rendered Markdown browser, and Close button."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 420)
        self.on_close_callback = on_close_callback
        self.setWindowModality(Qt.NonModal)  # type: ignore[attr-defined]

        if parent:
            geo = parent.screen().geometry()
            self.move(geo.x() + 60, geo.y() + 60)

        layout = QVBoxLayout(self)
        html = markdown(text or "No text available.")
        browser = QTextBrowser(self)
        browser.setHtml(html)
        layout.addWidget(browser)

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.close)  # type: ignore[arg-type]
        layout.addWidget(close_btn)

    def closeEvent(self, event):
        """Invoke the close callback, if any, then let the dialog close normally."""
        if self.on_close_callback:
            self.on_close_callback()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# create_forest_visualization
# ---------------------------------------------------------------------------


def create_forest_visualization(
    viz: GutenbergForestVisualizer,
    plotter: pv.Plotter,
) -> tuple[pv.Plotter, str, dict[str, dict]]:
    """
    Render the knowledge tree forest into *plotter* for the Qt viewer.

    Thin wrapper over :func:`gutenberg_kg.scene.build_forest_scene`: it maps
    the visualiser's ``param`` toggles onto :class:`~gutenberg_kg.scene.SceneFilters`
    and pumps the Qt event loop from the builder's progress callback so the
    status bar stays live during a long build.

    :param viz: :class:`GutenbergForestVisualizer` instance.
    :param plotter: The ``QtInteractor`` to render into.
    :return: ``(plotter, title_text, actor_to_node)``
    """

    def _progress(message: str) -> None:
        viz.status = message
        QApplication.processEvents()

    if viz.organic:
        slugs = {n.id.split(":")[0] for n in viz.all_nodes}
        if len(slugs) != 1:
            viz.status = f"Organic mode needs exactly one book selected ({len(slugs)} loaded)."
            return plotter, viz.window_title, {}
        slug = slugs.pop()
        tree: SceneInfo = build_tree_scene(
            viz.all_nodes,
            viz.all_edges,
            plotter,
            slug=slug,
            genre=viz._book_genre_map.get(slug, "unknown"),
            entry_times=viz._entry_times,
            # One checkbox drives both clouds here, so the viewer keeps the
            # behaviour it had before entities and topics were split apart.
            filters=SceneFilters(show_entities=viz.show_entities, show_topics=viz.show_entities),
            season=viz.season,
            progress=_progress,
        )
        plotter.reset_camera()  # type: ignore[call-arg]
        plotter.render()
        # Picking has nothing to hit: the organic scene is swept wood and
        # glyphed foliage, not one actor per node.
        return plotter, tree.title, {}

    info: SceneInfo = build_forest_scene(
        viz.all_nodes,
        viz.all_edges,
        plotter,
        book_genre_map=viz._book_genre_map,
        entry_times=viz._entry_times,
        filters=SceneFilters(
            show_sections=viz.show_sections,
            show_chunks=viz.show_chunks,
            show_entities=viz.show_entities,
            show_topics=viz.show_entities,
            show_contains=viz.show_contains,
            show_similar=viz.show_similar,
            show_next=viz.show_next,
        ),
        progress=_progress,
    )
    return plotter, info.title, info.actor_to_node


# ---------------------------------------------------------------------------
# GutenbergForestVisualizer — data and state model
# ---------------------------------------------------------------------------


class GutenbergForestVisualizer(param.Parameterized):
    """
    Data and state model for the Gutenberg 3-D forest visualiser.

    Reactive attributes (via ``param``) drive the Qt control panel.

    :param corpus_root: Path to the corpus directory.
    :param plotter: The ``QtInteractor`` to render into.
    """

    corpus_root: str = param.String(default=DEFAULT_CORPUS, doc="Corpus root path")
    save_path: str = param.String(default=DEFAULT_SAVE, doc="Save path stem")
    save_format: str = param.Selector(
        objects=["html", "png", "jpg"], default="html", doc="Export format"
    )

    # Render mode
    organic: bool = param.Boolean(
        default=False, doc="Grow the selected book as an organic tree instead of the spiral forest"
    )
    season: str = param.Selector(
        objects=list(SEASONS), default=DEFAULT_SEASON, doc="Foliage palette for the organic tree"
    )

    # Visibility toggles by node kind
    show_sections: bool = param.Boolean(default=True, doc="Render section (branch) nodes")
    show_chunks: bool = param.Boolean(default=True, doc="Render chunk (leaf) nodes")
    show_entities: bool = param.Boolean(default=False, doc="Render entity / topic nodes")

    # Edge visibility
    show_contains: bool = param.Boolean(default=False, doc="CONTAINS structural edges")
    show_similar: bool = param.Boolean(default=False, doc="SIMILAR_TO semantic edges")
    show_next: bool = param.Boolean(default=False, doc="NEXT sequential edges")

    # Status / title
    status: str = param.String(default="Ready", doc="Status bar text")
    window_title: str = param.String(
        default=f"Gutenberg KG Forest v{__version__}", doc="Window title"
    )

    # Stats
    num_books: int = param.Integer(default=0)
    num_genres: int = param.Integer(default=0)

    # Genre / book selectors
    available_genres: list[str] = param.List(default=[], doc="Available genre names")
    selected_genres: list[str] = param.ListSelector(default=[], objects=[], doc="Selected genres")
    available_books: list[str] = param.List(default=[], doc="Books in selected genres")
    selected_books: list[str] = param.ListSelector(
        default=[], objects=[], doc="Selected books (empty = all in genre)"
    )

    def __init__(self, plotter: pv.Plotter | None = None, **params) -> None:
        """
        Initialise the visualiser data model.

        :param plotter: The ``QtInteractor`` to render into.
        :param params: Additional ``param`` keyword arguments.
        """
        super().__init__(**params)
        self.plotter: pv.Plotter | None = plotter

        # Book catalogue: {genre: [BookMeta]}
        self._catalogue: dict[str, list[BookMeta]] = {}
        # Loaded graph data (all books currently selected)
        self.all_nodes: list[LayoutNode] = []
        self.all_edges: list[LayoutEdge] = []
        # slug → genre mapping for ForestLayout
        self._book_genre_map: dict[str, str] = {}
        # entry document id → ISO timestamp, for dated (diary) books
        self._entry_times: dict[str, str] = {}

        self.actor_to_node: dict[str, dict] = {}
        self._load_catalogue()

    @param.depends("corpus_root", watch=True)
    def _load_catalogue(self) -> None:
        """Scan corpus_root and populate the genre/book selectors."""
        root = Path(self.corpus_root)
        if not root.exists():
            self.status = f"Corpus not found: {root}"
            return

        self.status = "Scanning corpus..."
        QApplication.processEvents()

        self._catalogue = scan_corpus(root)
        genres = sorted(self._catalogue.keys())
        self.available_genres = genres
        self.param.selected_genres.objects = genres
        self.selected_genres = []

        n_books = sum(len(v) for v in self._catalogue.values())
        self.num_genres = len(genres)
        self.num_books = n_books
        self.status = f"Corpus: {len(genres)} genres, {n_books} ingested books"

    @param.depends("selected_genres", watch=True)
    def _on_genre_change(self) -> None:
        """Refresh available books when genre selection changes."""
        books: list[str] = []
        for genre in self.selected_genres:
            for meta in self._catalogue.get(genre, []):
                books.append(meta.title)
        books.sort()
        self.available_books = books
        self.param.selected_books.objects = books
        self.selected_books = []

    def load_selected(self) -> None:
        """
        Load nodes and edges for the currently selected genres/books.
        Populates :attr:`all_nodes`, :attr:`all_edges`, :attr:`_book_genre_map`.
        """
        self.status = "Loading book graphs..."
        QApplication.processEvents()

        genres_to_load = self.selected_genres or list(self._catalogue.keys())
        books_filter = set(self.selected_books)

        self.all_nodes = []
        self.all_edges = []
        self._book_genre_map = {}
        self._entry_times = {}

        loaded = 0
        for genre in genres_to_load:
            for meta in self._catalogue.get(genre, []):
                if books_filter and meta.title not in books_filter:
                    continue
                self.status = f"Loading: {meta.title}"
                QApplication.processEvents()
                try:
                    nodes, edges = load_book_graph(meta)
                    self.all_nodes.extend(nodes)
                    self.all_edges.extend(edges)
                    self._entry_times.update(load_entry_times(meta))
                    self._book_genre_map[meta.slug] = genre
                    loaded += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to load %s: %s", meta.title, exc)

        self.status = (
            f"Loaded {loaded} book(s): {len(self.all_nodes):,} nodes, {len(self.all_edges):,} edges"
        )

    def visualize(self) -> None:
        """Load selected books and render the 3-D forest."""
        if not self.plotter:
            return
        self.load_selected()
        if not self.all_nodes:
            self.status = "No books loaded — select a genre and render."
            return

        try:
            _, title, actor_to_node = create_forest_visualization(self, self.plotter)
            self.actor_to_node = actor_to_node
            self.window_title = title
        except (ValueError, RuntimeError) as exc:
            self.status = f"Error: {exc}"
            logger.exception("Render error")


# ---------------------------------------------------------------------------
# ForestMainWindow
# ---------------------------------------------------------------------------


class ForestMainWindow(QMainWindow):
    """
    Qt main window for the Gutenberg 3-D forest visualiser.

    Left panel  — corpus path, genre selector, book selector, render options.
    Right panel — PyVista QtInteractor + button row.

    :param corpus_root: Path to the corpus directory.
    :param save_path: Default output file stem for exports.
    :param width: Initial window width in pixels.
    :param height: Initial window height in pixels.
    """

    status_changed: pyqtSignal = pyqtSignal(str)

    def __init__(
        self,
        corpus_root: str = DEFAULT_CORPUS,
        save_path: str = DEFAULT_SAVE,
        width: int = 1500,
        height: int = 950,
    ) -> None:
        """Build the main window: control/viewport panels, mesh picking, and signal wiring."""
        super().__init__()
        self.timer = None
        self._current_picked_actor = None
        self._current_popup: TextPopup | None = None

        self.setGeometry(100, 100, width, height)

        self.vtk_plotter: QtInteractor = QtInteractor(self)
        self.visualizer: GutenbergForestVisualizer = GutenbergForestVisualizer(
            plotter=self.vtk_plotter,
            corpus_root=corpus_root,
            save_path=save_path,
        )
        self.plotter = self.vtk_plotter

        self.setWindowTitle(self.visualizer.window_title)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        self.setStyleSheet("""
            QPushButton {
                background-color: #2E8B57; color: white;
                border: none; border-radius: 3px; padding: 6px; margin: 2px;
            }
            QPushButton#reset-view  { background-color: #FFEB3B; color: black; }
            QPushButton#reset-all   { background-color: #8B0000; color: white; }
            QPushButton { font-size: 12px; }
            QWidget { background-color: #1a1a2e; color: #e0e0e0; }
            QLabel  { background: transparent; border: none; }
        """)

        ctrl_widget = self._build_control_panel()
        vis_widget = self._build_viewport_panel()

        main_layout.addWidget(ctrl_widget)
        main_layout.addWidget(vis_widget, stretch=1)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        ctrl_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)

        self._setup_mesh_picking()
        self._connect_signals()

        self.setFont(QFont("Arial", 12))
        self.resize(width, height)

    # -- UI builder helpers --------------------------------------------------

    @staticmethod
    def _h2(text: str) -> QLabel:
        """Build a bold, light-green section-heading label for the control panel."""
        lbl = QLabel(f"<b style='font-size:13px;color:#90EE90'>{text}</b>")
        lbl.setStyleSheet("background:transparent; border:none;")
        return lbl

    @staticmethod
    def _lbl(text: str) -> QLabel:
        """Build a plain, muted-gray text label for the control panel."""
        lbl = QLabel(text)
        lbl.setStyleSheet("background:transparent; border:none; color:#c0c0c0;")
        return lbl

    def _build_control_panel(self) -> QWidget:
        """Build the left control panel: corpus path, genre/book selectors, visibility
        checkboxes, stats label, and render/save buttons."""
        ctrl = QVBoxLayout()
        ctrl.setSpacing(10)
        ctrl.setContentsMargins(6, 6, 6, 6)

        # Corpus path
        ctrl.addWidget(self._h2("Corpus"))
        self.corpus_input = QLineEdit(self.visualizer.corpus_root)
        self.corpus_input.setPlaceholderText("corpus/")
        ctrl.addWidget(self.corpus_input)

        # Genre selector
        ctrl.addWidget(self._h2("Genres"))
        ctrl.addWidget(self._lbl("Select genres (empty = all):"))
        self.genre_selector = QListWidget()
        self.genre_selector.setSelectionMode(QListWidget.MultiSelection)
        self.genre_selector.setMaximumHeight(100)
        for g in self.visualizer.available_genres:
            self.genre_selector.addItem(g)
        ctrl.addWidget(self.genre_selector)

        # Book selector
        ctrl.addWidget(self._h2("Books"))
        ctrl.addWidget(self._lbl("Select books (empty = all in genre):"))
        self.book_selector = QListWidget()
        self.book_selector.setSelectionMode(QListWidget.MultiSelection)
        self.book_selector.setMaximumHeight(100)
        ctrl.addWidget(self.book_selector)

        # Render mode
        ctrl.addWidget(self._h2("Render Mode"))
        self.cb_organic = QCheckBox("Organic tree (one book)")
        self.cb_organic.setChecked(self.visualizer.organic)
        self.cb_organic.setToolTip(
            "Grow the selected book by space colonization — limbs reach its own\n"
            "chunks. Select exactly one book. This is what `gutenkg quilt` renders."
        )
        ctrl.addWidget(self.cb_organic)

        season_row = QHBoxLayout()
        season_row.addWidget(self._lbl("Season:"))
        self.season_selector = QComboBox()
        self.season_selector.addItems(list(SEASONS))
        self.season_selector.setCurrentText(self.visualizer.season)
        self.season_selector.setToolTip("Foliage palette. Winter bares the wood.")
        season_row.addWidget(self.season_selector, stretch=1)
        ctrl.addLayout(season_row)

        # Render options
        ctrl.addWidget(self._h2("Node Visibility"))
        self.cb_sections = QCheckBox("Sections (branches)")
        self.cb_sections.setChecked(self.visualizer.show_sections)
        self.cb_chunks = QCheckBox("Chunks (leaves)")
        self.cb_chunks.setChecked(self.visualizer.show_chunks)
        self.cb_entities = QCheckBox("Entities / Topics")
        self.cb_entities.setChecked(self.visualizer.show_entities)
        for cb in (self.cb_sections, self.cb_chunks, self.cb_entities):
            ctrl.addWidget(cb)

        ctrl.addWidget(self._h2("Edge Visibility"))
        self.cb_contains = QCheckBox("CONTAINS (structure)")
        self.cb_contains.setChecked(False)
        self.cb_similar = QCheckBox("SIMILAR_TO (semantic)")
        self.cb_similar.setChecked(self.visualizer.show_similar)
        self.cb_next = QCheckBox("NEXT (sequence)")
        self.cb_next.setChecked(self.visualizer.show_next)
        for cb in (self.cb_contains, self.cb_similar, self.cb_next):
            ctrl.addWidget(cb)

        # Stats label
        ctrl.addWidget(self._h2("Corpus Stats"))
        self.stats_label = QLabel(self._stats_text())
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet(
            "background:#0d1b2a; color:#90EE90; padding:5px; border-radius:3px;"
        )
        ctrl.addWidget(self.stats_label)

        # Action buttons
        ctrl.addStretch()
        self.render_btn = QPushButton("Render Forest")
        self.render_btn.setMinimumHeight(44)
        self.render_btn.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; background-color: #2E8B57; }"
        )
        ctrl.addWidget(self.render_btn)

        self.cast_btn = QPushButton("Cast to LG")
        self.cast_btn.setMinimumHeight(32)
        self.cast_btn.setStyleSheet("QPushButton { font-weight: bold; background-color: #3E5F8A; }")
        self.cast_btn.setToolTip(
            "Render the current view as a light-field quilt and push it to the\n"
            "Looking Glass via Bridge. Uses the camera you are looking through."
        )
        ctrl.addWidget(self.cast_btn)

        btn_row = QHBoxLayout()
        self.show_text_btn = QPushButton("Show Text")
        self.save_btn = QPushButton("Save View")
        btn_row.addWidget(self.show_text_btn)
        btn_row.addWidget(self.save_btn)
        ctrl.addLayout(btn_row)

        widget = QWidget()
        widget.setLayout(ctrl)
        widget.setFixedWidth(CONTROL_PANEL_WIDTH)
        return widget

    def _build_viewport_panel(self) -> QWidget:
        """Build the right panel: the PyVista viewport plus a reset/status button row."""
        vis = QVBoxLayout()
        vis.setSpacing(8)
        vis.setContentsMargins(8, 8, 8, 8)
        vis.addWidget(self.vtk_plotter, stretch=1)

        btn_row = QHBoxLayout()
        self.reset_view_btn = QPushButton("Reset View")
        self.reset_view_btn.setObjectName("reset-view")
        self.reset_view_btn.setFixedWidth(BUTTON_WIDTH)
        self.reset_settings_btn = QPushButton("Reset Settings")
        self.reset_settings_btn.setObjectName("reset-all")
        self.reset_settings_btn.setFixedWidth(BUTTON_WIDTH)
        self.status_display = QLabel("Ready")
        self.status_display.setStyleSheet(
            "font-weight:bold; font-size:13px; background:#0d1b2a; color:#90EE90; padding:3px;"
        )
        btn_row.addWidget(self.reset_view_btn)
        btn_row.addWidget(self.reset_settings_btn)
        btn_row.addWidget(self.status_display, stretch=1)
        vis.addLayout(btn_row)

        widget = QWidget()
        widget.setLayout(vis)
        return widget

    def _stats_text(self) -> str:
        """Return the multi-line corpus/nodes/edges summary shown in the stats label."""
        v = self.visualizer
        return (
            f"Genres: {v.num_genres}\n"
            f"Books (with KG): {v.num_books}\n"
            f"Nodes loaded: {len(v.all_nodes):,}\n"
            f"Edges loaded: {len(v.all_edges):,}"
        )

    # -- Signals / slots -----------------------------------------------------

    def _setup_mesh_picking(self) -> None:
        """Enable right-click mesh picking on the plotter, routed to :meth:`on_pick`."""
        self.vtk_plotter.enable_mesh_picking(
            callback=self.on_pick,
            show=False,
            show_actors=False,
            show_message=False,
            font_size=14,
            left_clicking=False,
            use_actor=True,
            through=True,
        )
        if hasattr(self.vtk_plotter, "picker"):
            self.vtk_plotter.picker.SetTolerance(0.005)
            self.vtk_plotter.picker.SetPickFromList(0)

    def _connect_signals(self) -> None:
        """Wire all Qt widget signals and ``param`` watchers to their handler slots."""
        self.corpus_input.editingFinished.connect(self._on_corpus_path_edited)
        self.genre_selector.itemSelectionChanged.connect(self._on_genre_selection_changed)
        self.book_selector.itemSelectionChanged.connect(self._on_book_selection_changed)

        self.season_selector.currentTextChanged.connect(
            lambda text: setattr(self.visualizer, "season", text)
        )
        self.cb_organic.stateChanged.connect(
            lambda s: self._on_organic_toggled(s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cast_btn.clicked.connect(self.cast_to_looking_glass)
        self.cb_sections.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_sections", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_chunks.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_chunks", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_entities.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_entities", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_contains.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_contains", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_similar.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_similar", s == Qt.Checked)  # type: ignore[attr-defined]
        )
        self.cb_next.stateChanged.connect(
            lambda s: setattr(self.visualizer, "show_next", s == Qt.Checked)  # type: ignore[attr-defined]
        )

        self.render_btn.clicked.connect(self.on_render_clicked)
        self.show_text_btn.clicked.connect(self.show_selected_text)
        self.save_btn.clicked.connect(self.save_current_view)
        self.reset_view_btn.clicked.connect(self.reset_camera)
        self.reset_settings_btn.clicked.connect(self.reset_settings)

        self.status_changed.connect(self.update_status_display)
        self.visualizer.param.watch(self.on_status_change, "status")
        self.visualizer.param.watch(self.update_window_title, "window_title")
        self.visualizer.param.watch(
            lambda _: self.stats_label.setText(self._stats_text()), "status"
        )
        self.visualizer.param.watch(self._on_genres_loaded, "available_genres")
        self.visualizer.param.watch(self._on_books_updated, "available_books")

    # -- Corpus / genre / book updates ---------------------------------------

    def _on_corpus_path_edited(self) -> None:
        """Push the edited corpus path text into the visualizer, triggering a rescan."""
        self.visualizer.corpus_root = self.corpus_input.text().strip()

    def _on_genre_selection_changed(self) -> None:
        """Sync the visualizer's selected genres with the genre list widget selection."""
        self.visualizer.selected_genres = [
            item.text() for item in self.genre_selector.selectedItems()
        ]

    def _on_book_selection_changed(self) -> None:
        """Sync the visualizer's selected books with the book list widget selection."""
        self.visualizer.selected_books = [
            item.text() for item in self.book_selector.selectedItems()
        ]

    def _on_genres_loaded(self, event: param.Event) -> None:
        """Repopulate the genre list widget when the visualizer's genre list changes."""
        self.genre_selector.clear()
        for g in event.new:
            self.genre_selector.addItem(g)

    def _on_books_updated(self, event: param.Event) -> None:
        """Repopulate the book list widget when the visualizer's book list changes."""
        self.book_selector.clear()
        for b in event.new:
            self.book_selector.addItem(b)

    def _on_organic_toggled(self, checked: bool) -> None:
        """
        Switch between forest and single-book modes.

        Organic mode grows exactly one book, so the book list drops to
        single-selection rather than letting a multi-selection be made that
        the renderer would only reject.

        :param checked: Whether organic mode is now on.
        """
        self.visualizer.organic = checked
        self.book_selector.setSelectionMode(
            QListWidget.SingleSelection if checked else QListWidget.MultiSelection
        )
        if checked:
            # Keep the first of any existing multi-selection.
            chosen = self.book_selector.selectedItems()
            self.book_selector.clearSelection()
            if chosen:
                chosen[0].setSelected(True)
        self.render_btn.setText("Render Book" if checked else "Render Forest")

    # -- Render / pick -------------------------------------------------------

    def on_render_clicked(self) -> None:
        """Render button handler: trigger a full load + render of the scene."""
        self.visualizer.visualize()

    def cast_to_looking_glass(self) -> None:
        """
        Render the current view as a quilt and push it to the Looking Glass.

        Re-composes the same scene into an off-screen plotter and copies this
        window's camera, so what is cast is the view being looked at — then
        hands the quilt to Bridge.  Needs Looking Glass Bridge running on this
        machine; the render is kept either way.

        The quilt is rendered at :data:`CAST_SCALE` of the preset's pixel size:
        the local render costs about a second at full size, but the wait is
        Bridge loading the resulting PNG, and that scales with its area.
        """
        try:
            from quiltwright import QUILT_PRESETS, cast_quilt, render_quilt, save_quilt
        except ImportError:
            self.visualizer.status = "Casting needs quiltwright: pip install gutenberg-kg[viz3d]"
            return
        if not self.visualizer.all_nodes:
            self.visualizer.status = "Nothing to cast — render something first."
            return

        preset = QUILT_PRESETS[QUILT_SPEC]
        spec = replace(
            preset,
            quilt_width=int(preset.quilt_width * CAST_SCALE) // preset.columns * preset.columns,
            quilt_height=int(preset.quilt_height * CAST_SCALE) // preset.rows * preset.rows,
        )

        def step(n: int, message: str) -> None:
            self.visualizer.status = f"Cast {n}/4 — {message}"
            self.cast_btn.setEnabled(False)
            QApplication.processEvents()

        offscreen = pv.Plotter(off_screen=True)
        started = time.perf_counter()
        try:
            step(1, "building scene...")
            create_forest_visualization(self.visualizer, offscreen)
            offscreen.camera_position = self.vtk_plotter.camera_position

            step(2, f"rendering {spec.n_views} views at {spec.tile_width}x{spec.tile_height}...")
            quilt = render_quilt(offscreen, spec)

            step(3, f"writing {spec.quilt_width}x{spec.quilt_height} quilt...")
            out_dir = Path(self.visualizer.corpus_root).parent / "renders" / "quilts"
            path = save_quilt(quilt, out_dir / f"{Path(self.visualizer.save_path).name}_cast", spec)

            step(4, "handing to Bridge...")
            cast_quilt(path.resolve(), spec)
            self.visualizer.status = f"Cast {path.name} in {time.perf_counter() - started:.1f}s"
        except Exception as exc:  # noqa: BLE001 — a dark panel must not kill the viewer
            logger.exception("Cast failed")
            self.visualizer.status = f"Cast failed (is Bridge running?): {exc}"
        finally:
            offscreen.close()
            self.cast_btn.setEnabled(True)

    def on_pick(self, actor) -> None:
        """Right-click callback: find nearest node and show text popup."""
        if not self.visualizer.plotter:
            return
        self._clear_highlight()
        if self._current_popup and self._current_popup.isVisible():
            self._current_popup.close()
            self._current_popup = None
        if actor is None:
            self.update_status_display("Right-click a node sphere or trunk to inspect.")
            return
        if not hasattr(self.vtk_plotter, "picked_point") or self.vtk_plotter.picked_point is None:
            self.update_status_display("No pick point — zoom in and right-click closer to a node.")
            return

        picked_point = np.asarray(self.vtk_plotter.picked_point, float)

        # Identify actor name and map to a node kind
        picked_kind: str | None = None
        for name, act in self.plotter.actors.items():
            if act != actor:
                continue
            if name == "trunks":
                # Trunk click → find nearest document node (shows book info)
                picked_kind = "document"
            else:
                for kind in KIND_SIZE:
                    if name == f"{kind}_nodes":
                        picked_kind = kind
                        break
            break

        if picked_kind is None:
            self.update_status_display("Click on a node sphere or trunk cylinder.")
            return

        # Find closest node of that kind
        best_id, best_dist = None, float("inf")
        for mesh_id, elem in self.visualizer.actor_to_node.items():
            if elem["kind"] != picked_kind:
                continue
            d = float(np.linalg.norm(np.asarray(elem["position"], float) - picked_point))
            if d < best_dist:
                best_dist = d
                best_id = mesh_id

        if best_id is None:
            self.update_status_display(f"No {picked_kind} node near pick point.")
            return

        elem = self.visualizer.actor_to_node[best_id]
        # Build highlight mesh at the picked node position (no per-node mesh stored)
        pos = np.asarray(elem["position"], float)
        highlight = make_node_mesh(elem["kind"], pos, KIND_SIZE[elem["kind"]] * 1.5, "high")
        self._highlight_mesh(highlight)

        kind_label = elem["kind"].capitalize()
        raw_name = elem["name"]
        title = f"{kind_label}: {raw_name}"
        text = elem.get("docstring") or f"**{raw_name}**\n\n_{kind_label} node._"
        self._current_popup = TextPopup(title, text, self, on_close_callback=self._on_popup_close)
        self._current_popup.show()
        self.update_status_display(f"Picked: {title} (dist {best_dist:.1f})")

    def _highlight_mesh(self, mesh) -> None:
        """Clear any existing highlight, then add *mesh* as the yellow-edged highlight actor."""
        self._clear_highlight()
        self.plotter.add_mesh(
            mesh,
            color="white",
            show_edges=True,
            edge_color="yellow",
            line_width=3,
            pickable=False,
            show_scalar_bar=False,
            reset_camera=False,
            name="_forest_highlight",
        )
        self._current_picked_actor = self.plotter.actors.get("_forest_highlight")

    def _clear_highlight(self) -> None:
        """Remove the current pick-highlight actor from the plotter, if one exists."""
        if self._current_picked_actor:
            try:
                self.plotter.remove_actor(self._current_picked_actor, reset_camera=False)
            except Exception:  # noqa: BLE001
                pass
            self._current_picked_actor = None

    def _on_popup_close(self) -> None:
        """TextPopup close callback: clear the pick highlight and re-render the scene."""
        self._clear_highlight()
        self.plotter.render()

    def show_selected_text(self) -> None:
        """Show text for the first selected book in the book selector."""
        items = self.book_selector.selectedItems()
        if not items:
            self.update_status_display("Select a book first.")
            return
        book_title = items[0].text()
        self._current_popup = TextPopup(
            book_title,
            f"**{book_title}**\n\nSelect a node in the scene to view its text.",
            self,
            on_close_callback=self._on_popup_close,
        )
        self._current_popup.show()

    # -- Camera --------------------------------------------------------------

    def reset_camera(self) -> None:
        """Reset the plotter camera to the default isometric view and zoom level."""
        if not self.plotter:
            return
        self.plotter.reset_camera()  # type: ignore[call-arg]
        self.plotter.view_isometric()  # type: ignore[call-arg]
        self.plotter.render()
        self.plotter.camera.zoom(2)

    # -- Save ----------------------------------------------------------------

    def save_current_view(self) -> None:
        """Save View button handler: export the current scene to HTML or a screenshot."""
        save_path = Path(self.visualizer.save_path)
        fmt = self.visualizer.save_format
        if save_path.suffix.lstrip(".") != fmt:
            save_path = save_path.with_suffix(f".{fmt}")
        self.visualizer.status = f"Saving → {save_path}…"
        QApplication.processEvents()
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "html":
                self.plotter.export_html(str(save_path))
            else:
                self.plotter.screenshot(str(save_path))
            self.visualizer.status = f"Saved → {save_path}"
        except (OSError, RuntimeError, ImportError) as exc:
            self.visualizer.status = f"Error saving: {exc}"

    # -- Reset ---------------------------------------------------------------

    def reset_settings(self) -> None:
        """Reset Settings button handler: clear selections, restore default visibility
        checkboxes, and reset the camera."""
        self.genre_selector.clearSelection()
        self.book_selector.clearSelection()
        self.cb_organic.setChecked(False)
        self.season_selector.setCurrentText(DEFAULT_SEASON)
        self.cb_sections.setChecked(True)
        self.cb_chunks.setChecked(True)
        self.cb_entities.setChecked(False)
        self.cb_contains.setChecked(True)
        self.cb_similar.setChecked(False)
        self.cb_next.setChecked(False)
        self.reset_camera()
        self.visualizer.status = "Ready"

    # -- Status --------------------------------------------------------------

    def on_status_change(self, event: param.Event) -> None:
        """``param`` watcher for ``visualizer.status``: re-emit as the Qt ``status_changed`` signal."""
        self.status_changed.emit(event.new)
        QApplication.processEvents()

    def update_status_display(self, status: str) -> None:
        """Render *status* into the status label, color-coded by message type (error/busy/done)."""
        if status.startswith("Error"):
            html = f"<span style='color:#FF6B6B;font-size:13px;'><b>{status}</b></span>"
        elif any(kw in status for kw in ("Rendering", "Loading", "Building", "Drawing")):
            html = f"<span style='color:#87CEEB;font-size:13px;'><b>⏳ {status}</b></span>"
        elif any(kw in status for kw in ("rendered", "Saved", "Loaded", "Corpus")):
            html = f"<span style='color:#90EE90;font-size:13px;'><b>✓ {status}</b></span>"
        else:
            html = f"<span style='color:#c0c0c0;font-size:13px;'>{status}</span>"
        self.status_display.setText(html)

    def update_window_title(self, event: param.Event) -> None:
        """``param`` watcher for ``visualizer.window_title``: apply it to the Qt window."""
        self.setWindowTitle(event.new)

    # -- Cleanup -------------------------------------------------------------

    def cleanup(self) -> None:
        """Close any open popup and tear down the VTK plotter to release GPU resources."""
        if self._current_popup and hasattr(self._current_popup, "isVisible"):
            try:
                self._current_popup.close()
            except Exception:  # noqa: BLE001
                pass
        if self.plotter:
            try:
                self.plotter.clear_actors()
                self.plotter.close()
                self.visualizer.plotter = None
                self.plotter = None
                self.vtk_plotter = None
            except Exception:  # noqa: BLE001
                pass
        gc.collect()

    def closeEvent(self, event) -> None:
        """Qt window-close handler: run :meth:`cleanup` (warnings suppressed) then accept."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                self.cleanup()
            except Exception:  # noqa: BLE001
                pass
        event.accept()


# ---------------------------------------------------------------------------
# launch() — entry point
# ---------------------------------------------------------------------------


def launch(
    corpus_root: str = DEFAULT_CORPUS,
    width: int = 1500,
    height: int = 950,
    **_kwargs,
) -> None:
    """
    Open the Gutenberg KG Forest window and run the Qt event loop.

    :param corpus_root: Path to the corpus directory (``corpus/`` by default).
    :param width: Initial window width in pixels.
    :param height: Initial window height in pixels.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("gutenberg-kg-forest")

    win = ForestMainWindow(
        corpus_root=corpus_root,
        save_path=str(Path(corpus_root).parent / DEFAULT_SAVE),
        width=width,
        height=height,
    )
    win.show()
    sys.exit(app.exec())


atexit.register(gc.collect)
