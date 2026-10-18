#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""create_pdf.sh --ocr が書き出したPDFとOCRテキストからMarkdownを作る。

使い方: uv run ocr_to_markdown.py <book.pdf> [output.md] [--toc-pages 1-20]

<book.pdf> と同じ場所にある <book>.txt（ページ区切りはフォームフィード）を本文として使う。

1. PDFの冒頭ページを画像にして `claude -p` に渡し、目次から見出しの一覧を抽出する。
   目次ページが見つからない場合は、本文の短い行を `claude -p` に渡して見出しの一覧を作る
   （どちらも <output>.toc.json に保存する）
2. 見出しを目次の順番で本文と照合し、Markdownの見出しにする
3. それ以外の行は、画面幅で折り返された改行だけをつないで段落にする。
   横書きの本文は両端揃えなので、行幅が本文の典型的な幅に達している行は折り返し途中、
   達していない行は段落の終わりとみなす

本文の文字はOCR結果をそのまま使い、誤字などは直さない。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

# 典型的な本文の行幅に対してこの割合以上の幅がある行は、次の行に続くとみなす
FULL_LINE_RATIO = 0.9
NEARLY_FULL_LINE_RATIO = 0.8
# 典型的な行幅を求めるときに、見出しや図中の短い行を除外するための下限
MIN_BODY_WIDTH = 20
SENTENCE_END_RE = re.compile(r"[。．.！？!?」』）)]$")

# 見出しは本文中で複数行に折り返されることがあるので、連続するこの行数までをつないで照合する
MAX_HEADING_LINES = 4
# 目次の見出しと本文の行の類似度がこれ以上なら同じ見出しとみなす
HEADING_MATCH_THRESHOLD = 0.8

# 目次ページがない本で、典型的な行幅に対してこの割合より短い行を見出しの候補として `claude -p` に渡す
HEADING_CANDIDATE_RATIO = 0.6

ENTRIES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "level": {"type": "integer"},
        },
        "required": ["title", "level"],
    },
}

TOC_SCHEMA = {
    "type": "object",
    "properties": {
        "toc_pages": {
            "type": "object",
            "properties": {
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            },
            "required": ["start", "end"],
        },
        "entries": ENTRIES_SCHEMA,
    },
    "required": ["toc_pages", "entries"],
}

INFERRED_TOC_SCHEMA = {
    "type": "object",
    "properties": {"entries": ENTRIES_SCHEMA},
    "required": ["entries"],
}

TOC_PROMPT = """\
このディレクトリにある page-NNN.png は、電子書籍のPDFの冒頭ページの画像です。NNNはPDFのページ番号です。
Readツールで画像を読んで目次ページを見つけ、目次に載っている見出しをすべて、目次の順番どおりに抽出してください。

- title: 目次に書かれているとおりの見出し。「第1章」「1.1」などの番号も含める。2行に折り返されていても1つにまとめる
- level: 目次での階層。最上位を1とする
- toc_pages: 目次が載っているPDFページ番号の範囲

目次が見つからない場合は、entries を空の配列にしてください。
"""

INFER_TOC_PROMPT = """\
以下は、電子書籍をOCRしたテキストから、本文の行より短い行だけを「行番号: テキスト」の形で抜き出したものです。
見出しのほかに、図や表の中の文字、コード、箇条書き、段落の最終行なども含まれます。
この中から本の見出しを選び、本の順番どおりに目次を作ってください。

- 本文の章・節・項は、「1章」「1.1」のように番号が付いた見出しがある本では番号付きのものだけを対象にする。番号がない本では、章に相当する大きな見出しを対象にする
- これとは別に、「まえがき」「謝辞」「本書について」「おわりに」「付録」「用語集」「索引」「著者紹介」など、本文の前後にある番号のない大きな見出しもlevel 1として含める
- title: 行のテキストをそのまま使う。OCRの誤字も直さない。番号だけの行と続くタイトルの行は空白でつなぐ。連続する行に折り返された見出しは、空白を入れずにつなぐ
- 見出しの番号が前の行にまとめてOCRされ、候補から消えていることがある。番号の並びから見出しが欠けていると判断できる場合は、タイトルにあたる行のテキストの前に番号を補って含める。タイトルにあたる行も見当たらない場合は含めない
- level: 章を1、節を2、項を3とする
"""


@dataclass
class TocEntry:
    title: str
    level: int


@dataclass
class Toc:
    toc_pages: tuple[int, int]
    entries: list[TocEntry]


@dataclass
class Heading:
    start: int
    end: int
    entry: TocEntry


# ---- 段落 ----


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


def typical_line_width(lines: list[str]) -> int:
    widths = Counter(display_width(line) for line in lines if display_width(line) >= MIN_BODY_WIDTH)
    if not widths:
        return 0
    return widths.most_common(1)[0][0]


def _join(left: str, right: str) -> str:
    # 英単語どうしが行をまたぐ場合だけ空白で区切る
    if re.search(r"[A-Za-z0-9,.;:)]$", left) and re.match(r"[A-Za-z0-9(]", right):
        return f"{left} {right}"
    return left + right


def _ends_sentence(line: str) -> bool:
    return bool(SENTENCE_END_RE.search(line))


def join_paragraphs(lines: list[str], full_width: int) -> list[str]:
    def is_full(line: str) -> bool:
        return display_width(line) >= full_width * FULL_LINE_RATIO

    stripped = [line.strip() for line in lines]
    paragraphs: list[str] = []
    current = ""
    for i, line in enumerate(stripped):
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        current = _join(current, line) if current else line
        next_line = stripped[i + 1] if i + 1 < len(stripped) else ""
        # 半角文字の多い行は実際より狭く数えられるので、文の途中で終わる行は少し短くても続きとみなす
        continues = is_full(line) or (
            display_width(line) >= full_width * NEARLY_FULL_LINE_RATIO and not _ends_sentence(line)
        )
        # 段落がちょうど行末で終わり、次が見出しや図中の文字のような短い行のときも段落を切る
        ends_at_line_end = (
            _ends_sentence(line) and next_line and not is_full(next_line) and not _ends_sentence(next_line)
        )
        if not continues or ends_at_line_end:
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return paragraphs


# ---- 目次の抽出 ----


def _run_claude(prompt: str, schema: dict, tools: str, cwd: str | None = None) -> dict:
    result = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            "sonnet",
            "--tools",
            tools,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
        ],
        input=prompt,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    output = json.loads(result.stdout)
    if output.get("is_error") or "structured_output" not in output:
        raise RuntimeError(f"claude -p failed: {output.get('result')}")
    return output["structured_output"]


def extract_toc(pdf: Path, first_page: int, last_page: int) -> Toc:
    with tempfile.TemporaryDirectory() as tmp_dir:
        subprocess.run(
            ["pdftoppm", "-f", str(first_page), "-l", str(last_page), "-scale-to", "1600", "-png", str(pdf.resolve()), "page"],
            cwd=tmp_dir,
            check=True,
        )
        return toc_from_dict(_run_claude(TOC_PROMPT, TOC_SCHEMA, "Read", cwd=tmp_dir))


def heading_candidates(text: str) -> list[tuple[int, str]]:
    """見出しの候補として、本文の典型的な行幅より十分短い行を(行番号, テキスト)で返す。"""
    # ページ区切りのフォームフィードの直前には改行がないことがあるので、ページごとに行へ分ける
    lines = [line.strip() for page in text.split("\f") for line in page.splitlines()]
    full_width = typical_line_width(lines)
    return [
        (number, line)
        for number, line in enumerate(lines, start=1)
        if line and display_width(line) < full_width * HEADING_CANDIDATE_RATIO
    ]


def infer_toc_from_text(text: str) -> Toc:
    """目次ページがない本のために、本文の短い行から `claude -p` で見出しの一覧を作る。"""
    candidates = "\n".join(f"{number}: {line}" for number, line in heading_candidates(text))
    data = _run_claude(INFER_TOC_PROMPT + "\n" + candidates, INFERRED_TOC_SCHEMA, "")
    return Toc(toc_pages=(0, 0), entries=[TocEntry(e["title"], e["level"]) for e in data["entries"]])


def toc_from_dict(data: dict) -> Toc:
    return Toc(
        toc_pages=(data["toc_pages"]["start"], data["toc_pages"]["end"]),
        entries=[TocEntry(e["title"], e["level"]) for e in data["entries"]],
    )


def toc_to_dict(toc: Toc) -> dict:
    return {
        "toc_pages": {"start": toc.toc_pages[0], "end": toc.toc_pages[1]},
        "entries": [{"title": e.title, "level": e.level} for e in toc.entries],
    }


# ---- 見出しの照合 ----


def _normalize(text: str) -> str:
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", text))


@dataclass
class _Candidate:
    entry_index: int
    start: int
    end: int
    score: float


def _find_candidates(normalized: list[str], entry_index: int, target: str, skip: set[int]) -> list[_Candidate]:
    """本文中でtargetに似ている範囲（連続する1〜MAX_HEADING_LINES行）をすべて返す。"""
    matcher = SequenceMatcher(None, "", target)
    spans: list[_Candidate] = []
    for start in range(len(normalized)):
        best: _Candidate | None = None
        candidate = ""
        for i in range(start, min(start + MAX_HEADING_LINES, len(normalized))):
            if i in skip or not normalized[i]:
                break
            candidate += normalized[i]
            if len(candidate) > len(target) * 2:
                break
            matcher.set_seq1(candidate)
            if matcher.quick_ratio() < HEADING_MATCH_THRESHOLD:
                continue
            score = matcher.ratio()
            if score >= HEADING_MATCH_THRESHOLD and (best is None or score > best.score):
                best = _Candidate(entry_index, start, i + 1, score)
        if best:
            spans.append(best)

    # 「4.1」「タイトル」と折り返された見出しは「タイトル」だけでも一致するので、重なる範囲は最も似ているものだけ残す
    kept: list[_Candidate] = []
    for span in sorted(spans, key=lambda s: (-s.score, s.start)):
        if all(span.end <= k.start or k.end <= span.start for k in kept):
            kept.append(span)
    return kept


def find_headings(lines: list[str], entries: list[TocEntry], skip: set[int]) -> tuple[list[Heading], list[TocEntry]]:
    """目次の見出しを本文から探す。見つからなかった見出しは2つ目の戻り値で返す。

    skipに含まれる行（本文中の目次ページなど）は照合しない。
    「はじめに」の章紹介などで見出しの文言が本物の見出し以外にも現れるので、
    目次の順番と本文での順番が揃う候補の組み合わせのうち、一致する見出しが最も多いものを選ぶ。
    同数なら類似度の合計が高いもの、さらに同じなら後ろ（次の見出しに近い位置）にあるものを選ぶ。
    """
    normalized = [_normalize(line) for line in lines]
    candidates = sorted(
        (c for index, entry in enumerate(entries) for c in _find_candidates(normalized, index, _normalize(entry.title), skip)),
        key=lambda c: c.start,
    )

    # best[k]: candidates[k]で終わる組み合わせの (見出し数, 類似度の合計, 開始行の合計) と直前の候補
    best: list[tuple[tuple[int, float, int], int | None]] = []
    for k, current in enumerate(candidates):
        value, previous = (1, current.score, current.start), None
        for j in range(k):
            before = candidates[j]
            if before.end <= current.start and before.entry_index < current.entry_index:
                count, score, starts = best[j][0]
                extended = (count + 1, score + current.score, starts + current.start)
                if extended > value:
                    value, previous = extended, j
        best.append((value, previous))

    chosen: list[_Candidate] = []
    k = max(range(len(candidates)), key=lambda i: best[i][0]) if candidates else None
    while k is not None:
        chosen.append(candidates[k])
        k = best[k][1]
    chosen.reverse()

    found = {c.entry_index for c in chosen}
    headings = [Heading(c.start, c.end, entries[c.entry_index]) for c in chosen]
    missing = [entry for index, entry in enumerate(entries) if index not in found]
    return headings, missing


# ---- Markdown ----


def build_markdown(text: str, toc: Toc) -> tuple[str, list[TocEntry]]:
    lines: list[str] = []
    toc_lines: set[int] = set()
    first_toc_page, last_toc_page = toc.toc_pages
    for page_number, page in enumerate(text.split("\f"), start=1):
        for line in page.splitlines():
            if first_toc_page <= page_number <= last_toc_page:
                toc_lines.add(len(lines))
            lines.append(line)

    headings, missing = find_headings(lines, toc.entries, toc_lines)
    full_width = typical_line_width(lines)

    def paragraphs(start: int, end: int) -> list[str]:
        # 本の中のコード例などにある行頭の#が見出しにならないようにする
        return [re.sub(r"^#", r"\\#", p) for p in join_paragraphs(lines[start:end], full_width)]

    blocks: list[str] = []
    position = 0
    for heading in headings:
        blocks.extend(paragraphs(position, heading.start))
        blocks.append(f"{'#' * heading.entry.level} {heading.entry.title}")
        position = heading.end
    blocks.extend(paragraphs(position, len(lines)))
    return "\n\n".join(blocks) + "\n", missing


def parse_page_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)-(\d+)", value)
    if not match or int(match[1]) > int(match[2]):
        raise argparse.ArgumentTypeError(f"invalid page range: {value} (e.g. 1-20)")
    return int(match[1]), int(match[2])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Convert a PDF and its OCR text into Markdown.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_md", type=Path, nargs="?")
    parser.add_argument(
        "--toc-pages",
        type=parse_page_range,
        default=(1, 20),
        help="PDF pages to search for the table of contents (default: 1-20)",
    )
    args = parser.parse_args(argv[1:])

    input_txt = args.pdf.with_suffix(".txt")
    output_md = args.output_md or args.pdf.with_suffix(".md")
    toc_json = output_md.with_suffix(".toc.json")

    text = input_txt.read_text()
    toc = extract_toc(args.pdf, *args.toc_pages)
    if not toc.entries:
        print("No table of contents found in the PDF. Inferring headings from the text.")
        toc = infer_toc_from_text(text)
    toc_json.write_text(json.dumps(toc_to_dict(toc), ensure_ascii=False, indent=2) + "\n")
    if not toc.entries:
        print("Warning: no headings found. Markdown has no headings.", file=sys.stderr)

    markdown, missing = build_markdown(text, toc)
    for entry in missing:
        print(f"Warning: heading not found in text: {entry.title}", file=sys.stderr)

    output_md.write_text(markdown)
    print(f"Successfully created {output_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
