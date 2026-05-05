#!/usr/bin/env python3
"""Thin wrapper — delegates all logic to gutenberg_kg.gutenberg.

For direct invocation: python scripts/download_gutenberg.py <command> [options]
Prefer the installed CLI: gutenkg download <command> [options]
"""

import sys

from gutenberg_kg.gutenberg import main

sys.exit(main())
