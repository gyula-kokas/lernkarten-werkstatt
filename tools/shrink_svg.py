#!/usr/bin/env python3
"""Shrink an oversized SVG picture so it still looks right on a card.

Some picture sources (photo tracings, scanned art) ship vector files with
thousands of tiny filled areas and a coordinate precision no card can show.
For those the honest answer is a raster at print resolution; for ordinary line
art it is enough to round the coordinates.

Two modes:

``--round`` (default)
    Rewrites the numbers inside every ``d="…"`` and keeps the command structure
    exactly as it is. Arc flags are read as flags, so the compact spelling
    ``a1 1 0 0110`` (flags 0,1, then x=10) survives - a naive number regex would
    glue flags and coordinates together and destroy the shape. Shapes do not
    change, only the precision.

``--rasterize --height N``
    Renders the picture ``N`` pixels high (28 mm at 600 dpi = 662 px, at 300 dpi
    = 331 px) and writes a derived asset ``<slug>-karte.json`` that wraps the PNG
    in a small SVG. Needs ``inkscape`` and ImageMagick's ``convert``. The
    original asset stays untouched and the source/license fields are copied.

Neither mode touches the editor's own data: point a word at the new asset with
the derived slug afterwards (Selections or the editor's own-image path).

Example:
  python3 tools/shrink_svg.py image-library/o263320-barber-and-customer.json --round --dry-run
  python3 tools/shrink_svg.py image-library/o263320-barber-and-customer.json --rasterize --height 662
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Kommandos und ihre Argumentzahl (A hat 7 Zahlen).
ARGS = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}
PATH = re.compile(r'(<path\b[^>]*?\sd=")([^"]*)(")')
VIEWBOX = re.compile(r'viewBox="([\d.\- ]+)"')


class Reader:
    """Zeichenleser für ein Pfad-``d``.

    Die Flags von ``a``/``A`` sind einzelne Ziffern und dürfen ohne Trenner
    direkt an die nächste Zahl anschließen (``a1 1 0 0110`` = Flags 0,1,
    x=10). Ein reiner Zahlen-Tokenizer scheitert daran.
    """

    NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
    SEP = " \t\r\n,"

    def __init__(self, d: str) -> None:
        self.d = d
        self.i = 0

    def skip(self) -> None:
        while self.i < len(self.d) and self.d[self.i] in self.SEP:
            self.i += 1

    def peek(self) -> str:
        self.skip()
        return self.d[self.i] if self.i < len(self.d) else ""

    def read_command(self) -> str:
        self.skip()
        char = self.d[self.i]
        self.i += 1
        return char

    def read_number(self) -> float:
        self.skip()
        match = self.NUMBER.match(self.d, self.i)
        if not match:
            raise ValueError(f"Zahl erwartet bei {self.d[self.i:self.i + 12]!r}")
        self.i = match.end()
        return float(match.group())

    def read_flag(self) -> int:
        self.skip()
        char = self.d[self.i] if self.i < len(self.d) else ""
        if char not in "01":
            raise ValueError(f"Flag (0/1) erwartet bei {self.d[self.i:self.i + 12]!r}")
        self.i += 1
        return int(char)


def number(value: float, decimals: int) -> str:
    rounded = round(value, decimals)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")


def round_d(d: str, decimals: int) -> str:
    """Nur die Zahlen ersetzen - Kommandostruktur und Form bleiben gleich."""
    reader = Reader(d)
    out: list[str] = []
    last = ""
    written = ""
    while True:
        char = reader.peek()
        if not char:
            break
        if char.isalpha():
            cmd = reader.read_command()
        elif last and last.lower() != "z":
            cmd = {"M": "L", "m": "l"}.get(last, last)
        else:
            break
        code = cmd.lower()
        if code not in ARGS:
            break
        if code == "z":
            out.append("z")
            written = ""
            last = cmd
            continue
        if cmd != written:
            out.append(cmd)
            written = cmd
        if code == "a":
            rx, ry, rot = reader.read_number(), reader.read_number(), reader.read_number()
            large, sweep = reader.read_flag(), reader.read_flag()
            x, y = reader.read_number(), reader.read_number()
            out.append(" ".join([number(rx, decimals), number(ry, decimals), number(rot, decimals),
                                 str(large), str(sweep), number(x, decimals), number(y, decimals)]))
        else:
            out.append(" ".join(number(reader.read_number(), decimals) for _ in range(ARGS[code])))
        last = cmd
    return " ".join(out)


def round_svg(svg: str, decimals: int) -> str:
    return PATH.sub(lambda m: m.group(1) + round_d(m.group(2), decimals) + m.group(3), svg)


def rasterize(svg_path: Path, height: int, colors: int) -> tuple[str, int] | None:
    """SVG rendern und als PNG mit Transparenz zurückgeben (base64, Bytes)."""
    if not shutil.which("inkscape") or not shutil.which("convert"):
        return None
    with tempfile.TemporaryDirectory(prefix="ded-svg-") as raw:
        png = Path(raw) / "bild.png"
        small = Path(raw) / "klein.png"
        subprocess.run(["inkscape", "--export-type=png", f"--export-filename={png}",
                        f"--export-height={height}", str(svg_path)],
                       check=True, capture_output=True)
        subprocess.run(["convert", str(png), "-strip", "-colors", str(colors),
                        f"PNG8:{small}"], check=True, capture_output=True)
        return base64.b64encode(small.read_bytes()).decode("ascii"), small.stat().st_size


def main() -> None:
    ap = argparse.ArgumentParser(description="Große SVG-Bilder für Lernkarten verkleinern")
    ap.add_argument("asset", type=Path, help="Datei in image-library/ (JSON mit \"svg\")")
    ap.add_argument("--round", action="store_true", help="nur Koordinaten runden (Standard)")
    ap.add_argument("--decimals", type=int, default=1, help="Nachkommastellen beim Runden (Standard 1)")
    ap.add_argument("--rasterize", action="store_true",
                    help="als Raster in Druckauflösung ablegen (neue Datei <slug>-karte.json)")
    ap.add_argument("--height", type=int, default=662, help="Rasterhöhe in Pixeln (28 mm bei 600 dpi)")
    ap.add_argument("--colors", type=int, default=128, help="Farben der PNG-Palette (Standard 128)")
    ap.add_argument("--write", action="store_true", help="Datei(en) schreiben (sonst nur rechnen)")
    args = ap.parse_args()

    path = args.asset if args.asset.is_absolute() else ROOT / args.asset
    asset = json.loads(path.read_text(encoding="utf-8"))
    svg = str(asset.get("svg") or "")
    if not svg:
        raise SystemExit(f"{path.name}: kein \"svg\"-Feld")
    before = len(svg.encode())

    if args.rasterize:
        with tempfile.TemporaryDirectory(prefix="ded-svg-") as raw:
            quelle = Path(raw) / "quelle.svg"
            quelle.write_text(svg, encoding="utf-8")
            made = rasterize(quelle, args.height, args.colors)
        if made is None:
            raise SystemExit("Für den Raster-Weg werden inkscape und ImageMagick (convert) gebraucht.")
        data, png_bytes = made
        view = VIEWBOX.search(svg)
        box = view.group(1).strip() if view else "0 0 1000 1000"
        x, y, w, h = [float(v) for v in box.split()[:4]]
        wrapper = (
            # xlink:href statt href: das verstehen Browser und Grafikprogramme
            # (inkscape zeichnet ein <image href="…"> nicht).
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="{box}">'
            f'<image xlink:href="data:image/png;base64,{data}" '
            f'x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" preserveAspectRatio="xMidYMid meet"/></svg>'
        )
        after = len(wrapper.encode())
        print(f"{path.name}: {before/1024:.0f} KiB → {after/1024:.0f} KiB ({after/before*100:.0f} %)")
        print(f"  Raster {args.height} px hoch · PNG {png_bytes/1024:.0f} KiB · {args.colors} Farben · mit Transparenz")
        if not args.write:
            print("  Probelauf – nichts geschrieben.")
            return
        neu = json.loads(json.dumps(asset))
        neu["slug"] = f"{asset.get('slug') or path.stem}-karte"
        neu["svg"] = wrapper
        neu["provider"] = "local-upload"
        neu["imageChanges"] = (f"In Druckauflösung gerastert ({args.height} px Höhe, {args.colors} Farben) "
                               f"und als PNG in SVG eingebettet – Fassung für Lernkarten.")
        ziel = path.with_name(neu["slug"] + ".json")
        ziel.write_text(json.dumps(neu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  geschrieben: {ziel.name} · slug {neu['slug']}")
        print(f"  Ausgangsdatei bleibt: {path.name}")
        return

    klein = round_svg(svg, args.decimals)
    after = len(klein.encode())
    print(f"{path.name}: {before/1024:.0f} KiB → {after/1024:.0f} KiB ({after/before*100:.0f} %)")
    print(f"  {args.decimals} Nachkommastelle(n), Form unverändert")
    if args.write:
        asset["svg"] = klein
        path.write_text(json.dumps(asset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  geschrieben: {path.name}")
    else:
        print("  Probelauf – nichts geschrieben.")


if __name__ == "__main__":
    main()
