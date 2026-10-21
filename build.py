#!/usr/bin/env python3
"""Inline css + js into one ready-to-publish index.html."""
import pathlib, sys

root = pathlib.Path(__file__).parent
src = root / "src"
out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else root / "index.html")

css = (src / "style.css").read_text(encoding="utf-8")
js_parts = []
for name in ["ind.js", "data.js", "chart.js", "ui.js"]:
    t = (src / name).read_text(encoding="utf-8")
    # node-only export lines are harmless in the browser, but drop them for cleanliness
    t = "\n".join(l for l in t.split("\n") if not l.startswith("if (typeof module"))
    js_parts.append(t)
js = "\n".join(js_parts).replace("</script", "<\\/script")

html = (src / "shell.html").read_text(encoding="utf-8").replace("{{CSS}}", css).replace("{{JS}}", js)
out.write_text(html, encoding="utf-8")
print("wrote", out, f"{len(html)/1024:.0f} KB")
