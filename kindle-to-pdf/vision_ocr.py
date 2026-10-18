#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "ocrmypdf>=17.11,<18",
#     "ocrmac>=1.0,<2",
# ]
# ///
"""macOS標準のVisionフレームワークでOCRし、PDFにテキストレイヤーを付与する。

使い方: uv run vision_ocr.py <input.pdf> <output.pdf> [sidecar.txt] [--lang ja|en]

--lang で本の言語を指定する（デフォルトは ja）。日本語と英語の両方を認識対象にしたまま、
指定した言語を優先する。英語の本を日本語優先でOCRすると、記号が全角になったり
単語間の空白が消えたりする。

sidecar.txtを指定すると、OCR結果のテキストも書き出す（ページ区切りはフォームフィード）。

ocrmypdfのOCRエンジンプラグインとしても動作する（このファイル自身をpluginsに渡す）。
Visionは行単位で認識結果を返すため、1行を1つの単語(ocrx_word)として登録する。
tesseractのように日本語を細切れの単語に分割しないので、
pdftotextなどで抽出したときに文字間へ空白が入らない。
一方で行全体を1語として配置するため、行内の文字単位の位置は近似になる
（検索・コピー・テキスト抽出には影響しない）。
"""

from __future__ import annotations

import argparse
import logging
import platform
import sys
from pathlib import Path

import ocrmypdf
from ocrmac import ocrmac
from ocrmypdf import hookimpl
from ocrmypdf.exceptions import ExitCodeException
from ocrmypdf.models.ocr_element import BoundingBox, OcrClass, OcrElement
from ocrmypdf.pluginspec import OcrEngine, OcrOptions, OrientationConfidence
from PIL import Image

log = logging.getLogger(__name__)

# ocrmypdfの3文字言語コード -> Visionの言語コード
LANGUAGE_MAP = {
    "jpn": "ja-JP",
    "eng": "en-US",
}

# 本の言語 -> ocrmypdfに渡す言語の優先順（Visionには options.languages の順で渡る）
LANGUAGE_PRIORITY = {
    "ja": ["jpn", "eng"],
    "en": ["eng", "jpn"],
}


def _engine_name() -> str:
    return f"Apple Vision (macOS {platform.mac_ver()[0]})"


def _vision_bbox_to_pixels(
    bbox: tuple[float, float, float, float], image_width: int, image_height: int
) -> BoundingBox:
    """Visionのbbox(左下原点の正規化座標 x, y, w, h)を左上原点のピクセル座標に変換する。"""
    x, y, w, h = bbox
    return BoundingBox(
        left=x * image_width,
        top=(1 - y - h) * image_height,
        right=(x + w) * image_width,
        bottom=(1 - y) * image_height,
    )


class VisionOcrEngine(OcrEngine):
    @staticmethod
    def version() -> str:
        return platform.mac_ver()[0]

    @staticmethod
    def creator_tag(options: OcrOptions) -> str:
        return _engine_name()

    def __str__(self) -> str:
        return _engine_name()

    @staticmethod
    def languages(options: OcrOptions) -> set[str]:
        return set(LANGUAGE_MAP)

    @staticmethod
    def get_orientation(input_file: Path, options: OcrOptions) -> OrientationConfidence:
        return OrientationConfidence(angle=0, confidence=0.0)

    @staticmethod
    def generate_hocr(
        input_file: Path, output_hocr: Path, output_text: Path, options: OcrOptions
    ) -> None:
        raise NotImplementedError("VisionOcrEngine uses generate_ocr() instead")

    @staticmethod
    def generate_pdf(
        input_file: Path, output_pdf: Path, output_text: Path, options: OcrOptions
    ) -> None:
        raise NotImplementedError("VisionOcrEngine uses generate_ocr() instead")

    @staticmethod
    def supports_generate_ocr() -> bool:
        return True

    @staticmethod
    def generate_ocr(
        input_file: Path, options: OcrOptions, page_number: int = 0
    ) -> tuple[OcrElement, str]:
        with Image.open(input_file) as image:
            image_width, image_height = image.size
            results = ocrmac.text_from_image(
                image,
                recognition_level="accurate",
                language_preference=[LANGUAGE_MAP[lang] for lang in options.languages],
            )

        page = OcrElement(
            ocr_class=OcrClass.PAGE,
            bbox=BoundingBox(left=0, top=0, right=image_width, bottom=image_height),
            page_number=page_number,
        )
        text_lines: list[str] = []
        for raw_text, confidence, bbox in results:
            text = raw_text.strip()
            if not text:
                continue
            pixel_bbox = _vision_bbox_to_pixels(bbox, image_width, image_height)
            word = OcrElement(
                ocr_class=OcrClass.WORD,
                bbox=pixel_bbox,
                text=text,
                confidence=confidence,
            )
            page.children.append(
                OcrElement(ocr_class=OcrClass.LINE, bbox=pixel_bbox, children=[word])
            )
            text_lines.append(text)

        if not text_lines:
            log.warning("page %d: Vision returned no text", page_number + 1)

        return page, "\n".join(text_lines) + "\n"


@hookimpl
def get_ocr_engine(options: OcrOptions | None) -> OcrEngine:
    return VisionOcrEngine()


def main() -> int:
    parser = argparse.ArgumentParser(description="VisionでOCRし、PDFにテキストレイヤーを付与する")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument("sidecar", type=Path, nargs="?")
    parser.add_argument("--lang", choices=LANGUAGE_PRIORITY, default="ja")
    args = parser.parse_args()

    try:
        # --output-type pdf: PDF/A変換で画像が再エンコードされ画質が変わるのを避ける
        exit_code = ocrmypdf.ocr(
            args.input_pdf,
            args.output_pdf,
            language=LANGUAGE_PRIORITY[args.lang],
            output_type="pdf",
            skip_text=True,
            plugins=[Path(__file__)],
            sidecar=args.sidecar,
        )
    except ExitCodeException as e:
        print(f"vision_ocr: {type(e).__name__}: {e}", file=sys.stderr)
        return int(e.exit_code)
    return int(exit_code)


if __name__ == "__main__":
    sys.exit(main())
