"""Root Click group for the GutenbergKG CLI."""

import importlib.metadata

import click


@click.group()
@click.version_option(version=importlib.metadata.version("gutenberg-kg"))
def cli():
    """gutenkg — The Knowledge Press. Download, ingest, and query digitized text corpora."""
    pass


# Import subcommands to register them
from gutenberg_kg.cli import (  # noqa: E402, F401
    cmd_audit,
    cmd_authors,
    cmd_build_corpus,
    cmd_build_diaries,
    cmd_chat,
    cmd_chunk_diaries,
    cmd_download,
    cmd_export_embedder,
    cmd_export_swift,
    cmd_genres,
    cmd_ia,
    cmd_imagine,
    cmd_ingest,
    cmd_init,
    cmd_pov,
    cmd_query,
    cmd_quilt,
    cmd_rebuild,
    cmd_reregister,
    cmd_snapshot,
    cmd_status,
    cmd_viz3d,
    cmd_viz_timeline,
)
