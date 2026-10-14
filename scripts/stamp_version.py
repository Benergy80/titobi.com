#!/usr/bin/env python3
"""Stamp ?v=<time> onto the CSS/JS links in every page so browsers fetch fresh copies after a push.
GitHub Pages lets browsers cache assets for 10 minutes. Run before committing a change to assets/."""
import re
import time
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
stamp = time.strftime("%Y%m%d%H%M")
for page in sorted(SITE.glob("*.html")):
    html = page.read_text()
    new = re.sub(r'(assets/[\w.-]+\.(?:css|js))(\?v=\w+)?"', rf'\1?v={stamp}"', html)
    if new != html:
        page.write_text(new)
print(f"stamped v={stamp}")
