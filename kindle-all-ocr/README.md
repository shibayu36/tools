# Kindle All OCR

macOS上でKindle for Macアプリを利用し、表示されている書籍の全ページをOCR（光学文字認識）処理して、検索可能な単一のPDFファイルとして保存するツールです。

## 機能

- Kindle for Mac の表示内容をページごとにスクリーンショット撮影
- Tesseract OCR を利用して各ページの画像を日本語テキスト認識
- Ghostscript を利用してOCR処理済みのページPDFを単一ファイルに結合

## 必要なもの (依存関係)

このツールを実行するには、以下のソフトウェアがインストールされている必要があります。

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- Tesseract 日本語言語データ (`tesseract-lang`)
- [Ghostscript](https://ghostscript.com/)

## インストール

Homebrewを使用して必要な依存関係をインストールします。

```bash
brew install tesseract tesseract-lang ghostscript
```

## 使い方

1. Kindle for Macアプリで、処理したい書籍を開き、最初のページを表示します。
2. ターミナルを開き、以下のコマンドを実行します。 `--enable-ocr` フラグを追加するとOCRが実行されます。
   ```bash
   osascript kindle-all-ocr.applescript [出力先親フォルダパス] [--enable-ocr]
   ```
   - `[出力先親フォルダパス]`: (任意) PDFや中間ファイルを出力する親フォルダを指定します。デフォルトは `~/Downloads` です。
   - `--enable-ocr`: (任意) このフラグを指定すると、Tesseract OCRによる文字認識が実行されます。指定しない場合は、スクリーンショットがOCRなしでPDFに変換・結合されます。

   **実行例:**
   ```bash
   # デフォルト設定 (Downloadsフォルダに出力, OCRなし)
   osascript kindle-all-ocr.applescript

   # 出力先を ~/Documents に指定
   osascript kindle-all-ocr.applescript "/Users/your_username/Documents"

   # OCRを有効にして実行 (Downloadsフォルダに出力)
   osascript kindle-all-ocr.applescript --enable-ocr

   # 出力先を指定し、OCRを有効にして実行
   osascript kindle-all-ocr.applescript "/Users/your_username/Documents" --enable-ocr
   ```
3. スクリプトが自動的にページめくりとスクリーンショット撮影を行います。
4. `--enable-ocr` フラグが指定されている場合はOCR処理が行われます。指定されていない場合は、OCRなしでPDF変換が行われます。
5. 最後に、各ページのPDFが結合されます。
6. 完了すると、指定した出力先親フォルダ内に `intermediate` フォルダ（中間ファイル保存用）と、結合されたPDFファイル (`combined_YYYYMMDD_HHMMSS.pdf`) が保存されます。 
