"""Render deterministic local HTML review cards without assigning speculative labels."""

import argparse
import html
import os
from pathlib import Path
from urllib.parse import quote

from sahulat_visual.dataset import resolve_image
from sahulat_visual.io import read_json


def render(benchmark: Path, root: Path, output: Path, limit: int) -> None:
    if limit < 1:
        raise ValueError("limit must be positive")
    failures = read_json(benchmark / "failures.json")
    selected = sorted(
        (row for row in failures if row["metrics"]["precision_at_1"] == 0),
        key=lambda row: row["query"]["image_id"],
    )[:limit]
    cards = []

    def figure(path: str, caption: str) -> str:
        image_path = resolve_image(root, path)
        relative = Path(os.path.relpath(image_path, output.resolve().parent)).as_posix()
        return (
            f'<figure><img loading="lazy" src="{quote(relative, safe="/.")}" '
            f'alt="{html.escape(caption, quote=True)}"><figcaption>'
            f"{html.escape(caption)}</figcaption></figure>"
        )

    for row in selected:
        query = row["query"]
        figures = [figure(query["image_path"], "Query: " + query["image_id"])]
        figures += [
            figure(
                product["matched_image_path"],
                f"#{rank} product {product['product_id']} — score {product['score']:.4f}",
            )
            for rank, product in enumerate(row["top_products"], 1)
        ]
        cards.append(
            f"<section><h2>Ground truth: {html.escape(query['product_id'])}</h2>"
            f'<div class="views">{"".join(figures)}</div></section>'
        )
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Visual retrieval failure review</title><style>"
        "body{font-family:system-ui;margin:2rem;color:#162536;background:#f5f7fa}"
        ".views{display:flex;flex-wrap:wrap;gap:1rem}figure{margin:0;width:180px}"
        "img{width:180px;height:240px;object-fit:contain;background:white}"
        "section{background:white;padding:1rem;margin:1rem 0;border:1px solid #ddd}"
        "figcaption{overflow-wrap:anywhere;font-size:.85rem}"
        "</style><h1>Visual retrieval failure review</h1>"
        f"<p>First {len(selected)} incorrect P@1 queries ordered by image ID. "
        "This display subset does not change benchmark metrics or exclusions. "
        "No visual failure category has been assigned automatically. "
        "Images are relative links to the local dataset.</p>" + "".join(cards) + "</html>"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"Rendered {len(selected)} review cards: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    render(args.benchmark, args.root, args.output, args.limit)
