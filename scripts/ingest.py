#!/usr/bin/env python3
"""Thin wrapper — delegates all logic to gutenberg_kg.ingest.

For direct invocation: python scripts/ingest.py [options]
Prefer the installed CLI: gutenkg ingest [options]
"""

import sys

from gutenberg_kg.ingest import main

sys.exit(main())
