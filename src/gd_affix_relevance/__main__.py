"""Allow ``python -m gd_affix_relevance`` to run the CLI directly."""

from __future__ import annotations

import sys

from gd_affix_relevance.cli import main

if __name__ == "__main__":
    sys.exit(main())
