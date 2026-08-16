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

Requires: pyvista, pyvistaqt, PyQt5, param, numpy, and the shared 3-D layout
primitives from ``kg_utils.viz3d`` (kgmodule-utils' ``viz3d`` extra).

Author: Eric G. Suchanek, PhD
"""

from __future__ import annotations

import atexit
import gc
import logging
import os
import shutil
import sys
import tempfile
import time
import warnings
from dataclasses import replace
from pathlib import Path

import numpy as np
import param
import pyvista as pv
from kg_utils.viz3d import LayoutEdge, LayoutNode
from markdown import markdown  # type: ignore[import-untyped]
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
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

#: Width left for the control panel's scrollbar so it never overlaps a widget.
SCROLLBAR_ALLOWANCE: int = 18
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

#: The two backends the Render button can drive.  PyVista draws into the live
#: viewport; POV-Ray ray-traces the same tree to an image file.  They are not
#: interchangeable in kind — one is a viewport, the other is a render — which
#: is why this is an explicit style rather than a quality setting.
RENDER_STYLE_PYVISTA: str = "PyVista (live)"
RENDER_STYLE_POVRAY: str = "POV-Ray (ray-traced)"
RENDER_STYLES: tuple[str, ...] = (RENDER_STYLE_PYVISTA, RENDER_STYLE_POVRAY)

#: Preview size for a POV-Ray render from the viewer.  Ray-tracing this tree
#: costs roughly 18 s at 640x480 on an M-series laptop and scales with pixels,
#: so this is chosen to stay under a minute rather than to look final —
#: `gutenkg pov --render` is the path for a picture worth keeping.
POV_PREVIEW_SIZE: tuple[int, int] = (900, 675)

#: Antialiasing threshold for a preview: ``None`` means the ``+A`` flag is
#: omitted entirely.  Measured on Huckleberry Finn at 900x675, this is the
#: whole cost of a preview — 30.9 s with POV-Ray's default ``+A0.3`` against
#: 10.3 s without.  Quality is almost free by comparison (``+Q5`` measured
#: 10.5 s, ``+Q3`` 8.7 s), so the lever worth pulling is the one that stops
#: supersampling every edge, not the one that removes shadows.  Casts keep
#: antialiasing: a quilt is the artifact you hold on to.
POV_PREVIEW_ANTIALIAS: float | None = None

#: Vertical FOV used when framing for a render.  Matches the `gutenkg pov`
#: and `gutenkg quilt` defaults, so the viewport, the ray-traced preview and
#: the cast quilt all compose the tree identically.
RENDER_FOV: float = 14.0

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

#: Three surface levels rather than one. The previous theme painted every
#: widget `#1a1a2e` with `border: none`, so a list, a combo box and the panel
#: behind them were the same flat slab — nothing to tell you where a control
#: started or whether it had focus. Depth here comes from a lighter surface as
#: a control becomes more interactive, plus a real 1 px edge on anything you
#: can type in, pick from or scroll.
BG_WINDOW: str = "#11151e"
BG_PANEL: str = "#1a2030"
BG_INPUT: str = "#232b3d"
BG_INPUT_HOVER: str = "#2b3448"
BORDER: str = "#3a4358"
BORDER_FOCUS: str = "#5FA8D3"
TEXT: str = "#e6e9ef"
TEXT_DIM: str = "#9aa4b8"
ACCENT: str = "#90EE90"
SELECT_BG: str = "#2E8B57"

DARK_STYLESHEET: str = f"""
    QMainWindow, QDialog {{ background-color: {BG_WINDOW}; }}
    QWidget {{ background-color: {BG_PANEL}; color: {TEXT}; }}
    QLabel {{ background: transparent; border: none; color: {TEXT}; }}

    /* Anything you type in, pick from, or scroll gets a real edge. */
    QLineEdit, QListWidget, QComboBox, QTextBrowser, QSpinBox {{
        background-color: {BG_INPUT};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 4px;
        padding: 4px;
        selection-background-color: {SELECT_BG};
        selection-color: white;
    }}
    QLineEdit:hover, QListWidget:hover, QComboBox:hover {{
        background-color: {BG_INPUT_HOVER};
        border-color: {BORDER_FOCUS};
    }}
    QLineEdit:focus, QListWidget:focus, QComboBox:focus {{
        border: 1px solid {BORDER_FOCUS};
    }}

    QListWidget::item {{ padding: 3px 4px; border-radius: 2px; }}
    QListWidget::item:hover {{ background-color: {BG_INPUT_HOVER}; }}
    QListWidget::item:selected {{ background-color: {SELECT_BG}; color: white; }}

    QComboBox::drop-down {{
        border-left: 1px solid {BORDER};
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER_FOCUS};
        selection-background-color: {SELECT_BG};
        outline: none;
    }}

    /* A checkbox with no visible box is just a label. */
    QCheckBox {{ background: transparent; padding: 3px; spacing: 7px; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {BORDER};
        border-radius: 3px;
        background-color: {BG_INPUT};
    }}
    QCheckBox::indicator:hover {{ border-color: {BORDER_FOCUS}; }}
    QCheckBox::indicator:checked {{
        background-color: {SELECT_BG};
        border-color: {ACCENT};
    }}

    QPushButton {{
        background-color: {SELECT_BG}; color: white;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 4px; padding: 6px; margin: 2px;
        font-size: 12px;
    }}
    QPushButton:hover {{ border-color: {ACCENT}; }}
    QPushButton:pressed {{ background-color: #26714a; }}
    QPushButton:disabled {{
        background-color: #2a3040; color: {TEXT_DIM};
        border-color: {BORDER};
    }}
    QPushButton#reset-view   {{ background-color: #FFEB3B; color: black; }}
    QPushButton#frame-render {{ background-color: #4A7C59; color: white; }}
    QPushButton#reset-all    {{ background-color: #8B0000; color: white; }}

    QScrollBar:vertical {{
        background: {BG_PANEL}; width: 11px; margin: 0;
        border: none; border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER}; border-radius: 5px; min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {BORDER_FOCUS}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

    QToolTip {{
        background-color: {BG_INPUT}; color: {TEXT};
        border: 1px solid {BORDER_FOCUS}; padding: 4px;
    }}
"""


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


class PovRenderWorker(QThread):
    """
    Ray-trace a written ``.pov`` off the GUI thread.

    POV-Ray is an external process and a slow one — roughly 18 s for a single
    900x675 view of a mid-sized book, and a 48-view quilt is that again per
    tile.  Calling it inline would freeze the window for the whole render,
    including the status label meant to report progress, so the work happens
    here and the window learns about it through signals.

    :param pov_path: The scene file to trace.
    :param spec: Quilt spec; a 1x1 spec renders a single image.
    :param camera: Camera in POV-Ray coordinates.
    :param jobs: Parallel POV-Ray processes.
    """

    #: Emitted with the assembled image once the render succeeds.
    finished_ok: pyqtSignal = pyqtSignal(object)
    #: Emitted with a human-readable reason when it does not.
    failed: pyqtSignal = pyqtSignal(str)

    def __init__(
        self,
        pov_path: Path,
        spec,
        camera,
        views_dir: Path,
        jobs: int = 1,
        antialias: float | None = 0.3,
    ) -> None:
        """Store the render inputs; nothing is traced until :meth:`run`."""
        super().__init__()
        self._pov_path = pov_path
        self._spec = spec
        self._camera = camera
        self._views_dir = views_dir
        self._jobs = jobs
        self._antialias = antialias

    def run(self) -> None:
        """Trace the scene, emitting :attr:`finished_ok` or :attr:`failed`."""
        try:
            import numpy as _np
            from PIL import Image as _Image
            from quiltwright import assemble_quilt
            from quiltwright.povray import render_pov_views

            # render_pov_views rather than render_pov_quilt: it writes one
            # viewNNN.png into a directory the caller owns as each trace
            # finishes, which is what makes progress observable at all. The
            # quilt path keeps its views in a private temp dir, so a caster
            # waiting minutes has nothing to watch.
            paths = render_pov_views(
                self._pov_path,
                self._spec,
                self._camera,
                self._views_dir,
                jobs=self._jobs,
                antialias=self._antialias,
                progress=False,
            )
            image = assemble_quilt(
                [_np.asarray(_Image.open(p).convert("RGB")) for p in paths], self._spec
            )
        except FileNotFoundError as exc:
            self.failed.emit(f"No povray binary on PATH — install POV-Ray to ray-trace. ({exc})")
        except Exception as exc:  # noqa: BLE001 - surfaced to the status bar
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(image)


class ImagePopup(QDialog):
    """
    A frameless-ish viewer for a rendered image.

    :param title: Window title.
    :param path: Image file to display.
    :param parent: Parent widget.
    """

    def __init__(self, title: str, path: Path, parent=None) -> None:
        """Show *path* scaled to fit, with the file location under it."""
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)

        label = QLabel(self)
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            label.setPixmap(
                pixmap.scaled(
                    min(pixmap.width(), 1100),
                    min(pixmap.height(), 800),
                    Qt.KeepAspectRatio,  # type: ignore[attr-defined]
                    Qt.SmoothTransformation,  # type: ignore[attr-defined]
                )
            )
        label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        layout.addWidget(label)

        where = QLabel(str(path), self)
        where.setStyleSheet(f"color:{ACCENT}; font-size:11px;")
        where.setTextInteractionFlags(Qt.TextSelectableByMouse)  # type: ignore[attr-defined]
        layout.addWidget(where)

        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.close)  # type: ignore[arg-type]
        layout.addWidget(close_btn)


def save_and_cast_quilt(image, stem: Path, spec, *, cast: bool) -> tuple[Path, str | None]:
    """
    Write a quilt to disk, then hand Bridge the **path** to it.

    Split out of the window because the two arguments are easy to confuse and
    the mistake is invisible until a panel is connected: ``save_quilt`` takes
    the array, ``cast_quilt`` takes a path on the Bridge host's filesystem.
    Passing the array to the caster raises ``argument should be a str or an
    os.PathLike object ... not 'ndarray'`` — after the minutes of ray-tracing,
    which is the worst possible moment to find out.

    The file is confirmed on disk before Bridge is contacted, so a cast that
    fails costs the connection and never the render.

    :param image: Assembled quilt as an RGB array.
    :param stem: Output path stem; ``save_quilt`` appends the spec suffix.
    :param spec: The spec it was rendered against.
    :param cast: Whether to push it to the Looking Glass after writing.
    :return: ``(written path, error message or None)``.
    """
    from quiltwright import save_quilt

    out = save_quilt(image, stem, spec)
    if not cast:
        return out, None
    if not out.exists():
        return out, f"{out} was not written"
    try:
        from quiltwright import cast_quilt

        # An absolute path: Bridge resolves it on its own filesystem.
        cast_quilt(out.resolve(), spec)
    except Exception as exc:  # noqa: BLE001 - the quilt file is kept regardless
        return out, str(exc)
    return out, None


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
    render_style: str = param.Selector(
        objects=list(RENDER_STYLES),
        default=RENDER_STYLE_PYVISTA,
        doc="Which backend the Render button drives",
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

        self.setStyleSheet(DARK_STYLESHEET)

        ctrl_widget = self._build_control_panel()
        vis_widget = self._build_viewport_panel()

        # The panel is taller than the window on a laptop display, and the
        # action buttons live at the bottom of it — so without this the Render
        # and Cast buttons are simply unreachable rather than merely cramped.
        ctrl_scroll = QScrollArea()
        ctrl_scroll.setWidget(ctrl_widget)
        ctrl_scroll.setWidgetResizable(True)
        ctrl_scroll.setFrameShape(QFrame.NoFrame)
        ctrl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ctrl_scroll.setFixedWidth(CONTROL_PANEL_WIDTH + SCROLLBAR_ALLOWANCE)

        main_layout.addWidget(ctrl_scroll)
        main_layout.addWidget(vis_widget, stretch=1)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        ctrl_scroll.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)

        self._setup_mesh_picking()
        self._connect_signals()

        self.setFont(QFont("Arial", 12))
        self.resize(width, height)

    # -- UI builder helpers --------------------------------------------------

    @staticmethod
    def _h2(text: str) -> QLabel:
        """Build a bold, light-green section-heading label for the control panel."""
        lbl = QLabel(f"<b style='font-size:13px;color:{ACCENT}'>{text}</b>")
        # A rule under each heading is what actually groups the panel: without
        # it the sections run together into one column of controls.
        lbl.setStyleSheet(
            f"background:transparent; border:none; border-bottom:1px solid {BORDER};"
            "padding-top:6px; padding-bottom:3px; margin-bottom:2px;"
        )
        return lbl

    @staticmethod
    def _lbl(text: str) -> QLabel:
        """Build a plain, muted-gray text label for the control panel."""
        lbl = QLabel(text)
        lbl.setStyleSheet(f"background:transparent; border:none; color:{TEXT_DIM};")
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

        style_row = QHBoxLayout()
        style_row.addWidget(self._lbl("Style:"))
        self.style_selector = QComboBox()
        self.style_selector.addItems(list(RENDER_STYLES))
        self.style_selector.setCurrentText(self.visualizer.render_style)
        self.style_selector.setToolTip(
            "PyVista draws into the viewport below.\n"
            "POV-Ray ray-traces the same tree to an image file — analytic\n"
            "primitives, exact silhouettes, and slow. Needs one book selected\n"
            "and a povray binary on PATH."
        )
        style_row.addWidget(self.style_selector, stretch=1)
        ctrl.addLayout(style_row)

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
            f"background:{BG_INPUT}; color:{ACCENT}; padding:6px;"
            f"border:1px solid {BORDER}; border-radius:4px;"
        )
        ctrl.addWidget(self.stats_label)

        # Action buttons
        ctrl.addSpacing(10)
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
        self.frame_btn = QPushButton("Frame for Render")
        self.frame_btn.setObjectName("frame-render")
        self.frame_btn.setFixedWidth(BUTTON_WIDTH + 30)
        self.frame_btn.setToolTip(
            "Place the camera exactly where the ray-tracer and the quilt will\n"
            "place it: level, +z up, standing off the crown at the render FOV.\n"
            "Reset View frames whatever is on screen; this frames the subject."
        )
        self.reset_settings_btn = QPushButton("Reset Settings")
        self.reset_settings_btn.setObjectName("reset-all")
        self.reset_settings_btn.setFixedWidth(BUTTON_WIDTH)
        self.status_display = QLabel("Ready")
        self.status_display.setStyleSheet(
            f"font-weight:bold; font-size:13px; background:{BG_INPUT}; color:{ACCENT};"
            f"padding:5px; border:1px solid {BORDER}; border-radius:4px;"
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(190)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m views")
        self.progress_bar.hide()

        btn_row.addWidget(self.reset_view_btn)
        btn_row.addWidget(self.frame_btn)
        btn_row.addWidget(self.reset_settings_btn)
        btn_row.addWidget(self.progress_bar)
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
        self.frame_btn.clicked.connect(self.frame_for_render)
        self.reset_settings_btn.clicked.connect(self.reset_settings)
        self.style_selector.currentTextChanged.connect(self._on_style_changed)

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

    def _on_style_changed(self, style: str) -> None:
        """Track the render-style combo, and relabel the buttons it governs.

        POV-Ray is a single-book backend, so selecting it also turns organic
        mode on: the spiral forest has no POV composer, and silently rendering
        something other than what the viewport shows would be worse than
        forcing the mode that matches.

        :param style: The newly selected entry of :data:`RENDER_STYLES`.
        """
        self.visualizer.render_style = style
        povray = style == RENDER_STYLE_POVRAY
        if povray and not self.cb_organic.isChecked():
            self.cb_organic.setChecked(True)
            self.visualizer.status = "POV-Ray renders one book — organic mode enabled."
        self.render_btn.setText("Ray-trace Tree" if povray else "Render Forest")
        self.cast_btn.setText("Cast to LG (POV)" if povray else "Cast to LG")

    def _single_book(self) -> tuple[str, str] | None:
        """Resolve the one loaded book, or report why there isn't one.

        The POV composer takes one book's nodes and edges; there is no forest
        equivalent. This is the same gate :func:`create_forest_visualization`
        applies to organic mode, kept in one shape so both report alike.

        :return: ``(slug, genre)``, or None with the status bar already set.
        """
        if not self.visualizer.all_nodes:
            self.visualizer.status = "Nothing loaded — select a book and render first."
            return None
        slugs = {n.id.split(":")[0] for n in self.visualizer.all_nodes}
        if len(slugs) != 1:
            self.visualizer.status = f"POV-Ray renders one book at a time ({len(slugs)} loaded)."
            return None
        slug = slugs.pop()
        return slug, self.visualizer._book_genre_map.get(slug, "unknown")

    def _build_pov_scene(self):
        """Grow the loaded book and compose it as POV-Ray primitives.

        The slug comes back with the scene so callers can name the output file
        without resolving the book a second time.

        :return: ``(scene, geometry, slug)``, or None with the status bar set.
        """
        resolved = self._single_book()
        if resolved is None:
            return None
        slug, genre = resolved
        from gutenberg_kg.povscene import build_tree_pov_scene

        def _progress(message: str) -> None:
            self.visualizer.status = message
            QApplication.processEvents()

        scene, geometry = build_tree_pov_scene(
            self.visualizer.all_nodes,
            self.visualizer.all_edges,
            slug=slug,
            genre=genre,
            entry_times=self.visualizer._entry_times,
            filters=SceneFilters(
                show_entities=self.visualizer.show_entities,
                show_topics=self.visualizer.show_entities,
            ),
            season=self.visualizer.season,
            progress=_progress,
        )
        return scene, geometry, slug

    def on_render_clicked(self) -> None:
        """Render button handler: drive whichever backend the style names."""
        if self.visualizer.render_style == RENDER_STYLE_POVRAY:
            self.render_povray()
        else:
            self.visualizer.visualize()

    def render_povray(self) -> None:
        """
        Ray-trace the loaded book and show the result.

        Loads if needed, writes the ``.pov`` beside the other renders, then
        hands the trace to :class:`PovRenderWorker` so the window stays
        responsive.  The camera comes from the viewport, so what is traced is
        what is being looked at — use **Frame for Render** first to put the
        viewport where the quilt would be.
        """
        if not self.visualizer.all_nodes:
            self.visualizer.load_selected()
        composed = self._build_pov_scene()
        if composed is None:
            return
        scene, geometry, slug = composed
        self._pov_geometry = geometry

        out_dir = Path(self.visualizer.corpus_root).parent / "renders" / "pov"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._pov_stem = out_dir / slug
        pov_path = scene.write(self._pov_stem.with_suffix(".pov"))
        self.visualizer.status = f"Wrote {pov_path.name} ({pov_path.stat().st_size / 1024:.0f} KB)"
        QApplication.processEvents()

        from quiltwright.povgen import pov_camera_from_plotter

        from gutenberg_kg.povscene import preview_spec

        camera = pov_camera_from_plotter(self.vtk_plotter, handedness=scene.handedness)
        spec = preview_spec(*POV_PREVIEW_SIZE)
        self._start_pov_render(
            pov_path,
            spec,
            camera,
            label="preview",
            cast=False,
            antialias=POV_PREVIEW_ANTIALIAS,
        )

    def cast_povray(self) -> None:
        """
        Ray-trace a full light-field quilt and push it to the Looking Glass.

        The same scene the preview traced, at the Looking Glass preset instead
        of a single view — so this is :data:`POV_PREVIEW_SIZE` arithmetic times
        ``n_views``, which is minutes rather than seconds.  The quilt is
        written to ``renders/pov/`` before Bridge is contacted, so a failed
        cast still leaves the hologram file behind.
        """
        composed = self._build_pov_scene()
        if composed is None:
            return
        scene, geometry, slug = composed
        self._pov_geometry = geometry

        out_dir = Path(self.visualizer.corpus_root).parent / "renders" / "pov"
        out_dir.mkdir(parents=True, exist_ok=True)
        self._pov_stem = out_dir / f"{slug}_quilt"
        pov_path = scene.write(self._pov_stem.with_suffix(".pov"))

        from quiltwright import QUILT_PRESETS
        from quiltwright.povgen import pov_camera_from_plotter

        preset = QUILT_PRESETS[QUILT_SPEC]
        spec = replace(
            preset,
            quilt_width=int(preset.quilt_width * CAST_SCALE) // preset.columns * preset.columns,
            quilt_height=int(preset.quilt_height * CAST_SCALE) // preset.rows * preset.rows,
        )
        camera = pov_camera_from_plotter(self.vtk_plotter, handedness=scene.handedness)
        self.visualizer.status = f"Wrote {pov_path.name}; ray-tracing {spec.n_views} views..."
        self._start_pov_render(pov_path, spec, camera, label="quilt", cast=True)

    def _start_pov_render(
        self,
        pov_path: Path,
        spec,
        camera,
        *,
        label: str,
        cast: bool,
        antialias: float | None = 0.3,
    ) -> None:
        """Run a POV-Ray trace in the background and route the result.

        :param pov_path: Scene to trace.
        :param spec: Quilt spec; 1x1 for a preview.
        :param camera: Camera in POV-Ray coordinates.
        :param label: Word for the status line.
        :param cast: Whether to push the finished quilt to the Looking Glass.
        :param antialias: POV-Ray ``+A`` threshold; None omits the flag.
        """
        self.render_btn.setEnabled(False)
        self.cast_btn.setEnabled(False)
        self.visualizer.status = (
            f"POV-Ray: tracing {spec.n_views} view(s) at "
            f"{spec.tile_width}x{spec.tile_height} — this is not fast..."
        )
        QApplication.processEvents()

        # The worker writes views here as it finishes them; the GUI thread
        # counts the files. Polling the filesystem beats threading a callback
        # out of an external process pool, and it cannot wedge the render.
        self._views_dir = Path(tempfile.mkdtemp(prefix="gutenkg-pov-"))
        self.progress_bar.setRange(0, spec.n_views)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self._pov_started = time.perf_counter()
        self.progress_bar.setFormat("%v / %m views")
        self._pov_timer = QTimer(self)
        self._pov_timer.timeout.connect(self._poll_pov_progress)
        self._pov_timer.start(400)

        worker = PovRenderWorker(
            pov_path,
            spec,
            camera,
            self._views_dir,
            jobs=max(1, (os.cpu_count() or 2) - 1),
            antialias=antialias,
        )
        worker.finished_ok.connect(lambda img: self._on_pov_done(img, spec, label, cast))
        worker.failed.connect(self._on_pov_failed)
        worker.finished.connect(self._finish_pov_render)
        self._pov_worker = worker  # keep a reference; a GC'd QThread is a crash
        worker.start()

    def _poll_pov_progress(self) -> None:
        """Count finished views on disk and advance the bar.

        Cheap enough at 400 ms: a directory listing against a render whose
        views take seconds each.
        """
        views_dir = getattr(self, "_views_dir", None)
        if views_dir is None or not views_dir.exists():
            return
        done = len(list(views_dir.glob("view*.png")))
        self.progress_bar.setValue(done)

        # Elapsed and ETA rather than a frame number. With jobs > 1 there is no
        # single "current frame" — roughly one trace per core is in flight, and
        # `done` is how many have landed, not which one is being worked on.
        # Extrapolating from the completed rate is the honest reading of that.
        started = getattr(self, "_pov_started", None)
        if started is None or done == 0:
            return
        elapsed = time.perf_counter() - started
        total = self.progress_bar.maximum()
        eta = elapsed / done * (total - done)
        self.progress_bar.setFormat(f"%v / %m views  ·  {elapsed:.0f}s, ~{eta:.0f}s left")

    def _finish_pov_render(self) -> None:
        """Stop polling, hide the bar, re-enable the buttons, drop the views."""
        timer = getattr(self, "_pov_timer", None)
        if timer is not None:
            timer.stop()
        self.progress_bar.hide()
        self.render_btn.setEnabled(True)
        self.cast_btn.setEnabled(True)
        views_dir = getattr(self, "_views_dir", None)
        if views_dir is not None:
            # Only ever a directory this method's owner created via mkdtemp.
            shutil.rmtree(views_dir, ignore_errors=True)
            self._views_dir = None

    def _on_pov_failed(self, message: str) -> None:
        """Report a failed trace on the status bar.

        :param message: Human-readable reason.
        """
        self.visualizer.status = f"POV-Ray failed: {message}"

    def _on_pov_done(self, image, spec, label: str, cast: bool) -> None:
        """Save the traced image, then preview or cast it.

        :param image: Assembled RGB array from POV-Ray.
        :param spec: The spec it was rendered against.
        :param label: Word for the status line.
        :param cast: Whether to push it to the Looking Glass.
        """
        try:
            out, error = save_and_cast_quilt(image, self._pov_stem, spec, cast=cast)
        except Exception as exc:  # noqa: BLE001 - surfaced to the status bar
            self.visualizer.status = f"POV-Ray render succeeded but saving failed: {exc}"
            return

        if not cast:
            self.visualizer.status = f"POV-Ray {label} → {out}"
            popup = ImagePopup(f"POV-Ray — {self.visualizer.window_title}", out, self)
            popup.resize(min(POV_PREVIEW_SIZE[0] + 40, 1200), POV_PREVIEW_SIZE[1] + 110)
            popup.show()
            return

        size_mb = out.stat().st_size / 1e6 if out.exists() else 0.0
        if error:
            self.visualizer.status = (
                f"Quilt saved to {out} ({size_mb:.1f} MB), casting failed: {error}"
            )
            return
        self.visualizer.status = (
            f"Cast POV-Ray quilt ({size_mb:.1f} MB) to the Looking Glass → {out}"
        )

    def frame_for_render(self) -> None:
        """
        Put the viewport camera exactly where the renderers will put theirs.

        ``Reset View`` frames whatever actors are on screen, ground slab and
        all.  This frames the *subject*: :func:`kg_utils.viz3d.frame_tree` is
        the one rule ``gutenkg pov`` and ``gutenkg quilt`` also use, so after
        pressing this the viewport is a true preview of the render — which is
        what makes the depth budget on a light-field panel predictable rather
        than a matter of nudging the mouse.

        Falls back to the plotter's bounds when no tree has been grown yet,
        the same fallback :func:`tree_pov_camera` makes.
        """
        if not self.plotter:
            return
        from gutenberg_kg.povscene import tree_camera_frame

        geometry = getattr(self, "_pov_geometry", None)
        bounds = None
        if geometry is None:
            raw = self.plotter.bounds
            if raw is None:
                self.visualizer.status = "Nothing to frame — render something first."
                return
            bounds = (
                np.array([raw[0], raw[2], raw[4]], dtype=float),
                np.array([raw[1], raw[3], raw[5]], dtype=float),
            )
        try:
            frame = tree_camera_frame(geometry, bounds=bounds, fov=RENDER_FOV)
        except ValueError as exc:
            self.visualizer.status = f"Cannot frame: {exc}"
            return

        self.plotter.camera_position = [frame.position, frame.focal_point, frame.up]
        self.plotter.camera.view_angle = RENDER_FOV
        self.plotter.render()
        self.visualizer.status = (
            f"Framed for render at {RENDER_FOV:.0f}° FOV"
            f"{'' if geometry is not None else ' (from scene bounds)'}."
        )

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

        if self.visualizer.render_style == RENDER_STYLE_POVRAY:
            self.cast_povray()
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
