"""Generate a local SVG coverage badge from coverage.xml."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree


def _badge_color(coverage: float) -> str:
    if coverage >= 90.0:
        return "#2ea043"
    if coverage >= 80.0:
        return "#97ca00"
    if coverage >= 70.0:
        return "#dfb317"
    if coverage >= 60.0:
        return "#fe7d37"
    return "#e05d44"


def _read_coverage_percent(xml_path: Path) -> float:
    root = ElementTree.parse(xml_path).getroot()
    line_rate = root.attrib.get("line-rate")
    if line_rate is None:
        raise ValueError("coverage.xml missing 'line-rate' in root <coverage>")
    return round(float(line_rate) * 100.0, 1)


def _render_svg(percent: float, color: str) -> str:
    label = "coverage"
    value = f"{percent:.1f}%"

    label_width = 78
    value_width = 66
    total_width = label_width + value_width

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" '
        f'aria-label="{label}: {value}">'
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/>'
        '</linearGradient>'
        '<clipPath id="r">'
        f'<rect width="{total_width}" height="20" rx="3" fill="#fff"/>'
        '</clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="{label_width}" height="20" fill="#555"/>'
        f'<rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>'
        f'<rect width="{total_width}" height="20" fill="url(#s)"/>'
        '</g>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{label_width / 2}" y="15" fill="#010101" fill-opacity=".3">{label}</text>'
        f'<text x="{label_width / 2}" y="14">{label}</text>'
        f'<text x="{label_width + (value_width / 2)}" y="15" fill="#010101" fill-opacity=".3">{value}</text>'
        f'<text x="{label_width + (value_width / 2)}" y="14">{value}</text>'
        '</g>'
        '</svg>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local coverage SVG badge")
    parser.add_argument("--input", default="coverage.xml", help="Path to coverage.xml")
    parser.add_argument("--output", default="badges/coverage.svg", help="Path to output SVG")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    coverage = _read_coverage_percent(input_path)
    color = _badge_color(coverage)
    svg = _render_svg(coverage, color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    print(f"Coverage badge written to {output_path} ({coverage:.1f}%)")


if __name__ == "__main__":
    main()
