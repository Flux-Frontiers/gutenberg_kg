#!/usr/bin/env python3
"""Thin wrapper — delegates all logic to gutenberg_kg.ia.

For direct invocation: python scripts/download_ia.py <command> [options]
Prefer the installed CLI: gutenkg ia <command> [options]
"""

import sys

from gutenberg_kg.ia import main

sys.exit(main())
