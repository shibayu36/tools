from ocr_to_markdown import Toc, TocEntry, build_markdown, find_headings, heading_candidates, join_paragraphs

FULL = "あ" * 20


def test_join_paragraphs_joins_wrapped_lines():
    lines = [FULL, FULL, "おわり。", FULL, "次の段落。"]
    assert join_paragraphs(lines, 40) == [FULL * 2 + "おわり。", FULL + "次の段落。"]


def test_join_paragraphs_inserts_space_between_english_words():
    assert join_paragraphs(["a" * 38 + " word", "next line."], 40) == ["a" * 38 + " word next line."]


def test_join_paragraphs_continues_nearly_full_line_in_mid_sentence():
    nearly_full = "あ" * 17
    assert join_paragraphs([nearly_full, "続き。"], 40) == [nearly_full + "続き。"]
    assert join_paragraphs([nearly_full[:-1] + "。", "次。"], 40) == [nearly_full[:-1] + "。", "次。"]


def test_join_paragraphs_breaks_before_short_heading_after_full_sentence():
    line = "あ" * 19 + "。"
    assert join_paragraphs([line, "小見出し", FULL], 40) == [line, "小見出し", FULL]


def test_find_headings_matches_garbled_and_wrapped_titles():
    lines = ["¾4⅜", "アウトプット制御のための", "テスト駆動開発", "本文。", "4.1", "トレードオフ", "本文。"]
    entries = [TocEntry("第4章 アウトプット制御のためのテスト駆動開発", 1), TocEntry("4.1 トレードオフ", 2)]
    headings, missing = find_headings(lines, entries, set())
    assert [(h.start, h.end) for h in headings] == [(1, 3), (4, 6)]
    assert missing == []


def test_find_headings_prefers_occurrence_closest_to_next_heading():
    lines = ["第1章", "現状と課題", "はじめにの本文。", "第1章 現状と課題", "本文。", "1.1 現場", "本文。"]
    entries = [TocEntry("第1章 現状と課題", 1), TocEntry("1.1 現場", 2)]
    headings, _ = find_headings(lines, entries, set())
    assert [h.start for h in headings] == [3, 5]


def test_find_headings_missing_heading_does_not_drag_others_to_mentions():
    overview = ["第1章 現状と課題", "第2章 フレームワーク"]
    body = ["第1章 現状と課題", "本文。", "1.1 現場", "本文。", "崩れたOCR", "本文。", "2.1 式で捉える", "本文。"]
    entries = [
        TocEntry("第1章 現状と課題", 1),
        TocEntry("1.1 現場", 2),
        TocEntry("第2章 フレームワーク", 1),
        TocEntry("2.1 式で捉える", 2),
    ]
    headings, missing = find_headings(overview + body, entries, set())
    assert [h.start for h in headings] == [2, 4, 8]
    assert missing == [entries[2]]


def test_find_headings_skips_lines_and_reports_missing():
    lines = ["1.1 現場", "本文。", "1.1 現場", "本文。"]
    entries = [TocEntry("1.1 現場", 2), TocEntry("9.9 存在しない見出し", 2)]
    headings, missing = find_headings(lines, entries, {2})
    assert [h.start for h in headings] == [0]
    assert missing == [entries[1]]


def test_heading_candidates_returns_short_lines_split_by_page_breaks():
    text = f"{FULL}\n{'あ' * 15}。\f6章\n知識と記憶\n{FULL}"
    assert heading_candidates(text) == [(3, "6章"), (4, "知識と記憶")]


def test_build_markdown():
    text = "目次\n第1章 現状\n\f第1章 現状\n本文。\n# コード中のコメント\n"
    toc = Toc(toc_pages=(1, 1), entries=[TocEntry("第1章 現状", 1)])
    markdown, missing = build_markdown(text, toc)
    assert markdown == "目次\n\n第1章 現状\n\n# 第1章 現状\n\n本文。\n\n\\# コード中のコメント\n"
    assert missing == []
