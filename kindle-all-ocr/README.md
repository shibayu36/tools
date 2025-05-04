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

1. Kindle for Macアプリで、OCRしたい書籍を開き、最初のページを表示します。
2. ターミナルを開き、以下のコマンドを実行します:
   ```bash
   osascript kindle-all-ocr.applescript [出力先親フォルダパス] [--delete-intermediate]
   ```
   - `[出力先親フォルダパス]`: (任意) PDFや中間ファイルを出力する親フォルダを指定します。デフォルトは `~/Downloads` です。
   - `--delete-intermediate`: (任意) このフラグを付けると、処理完了後に中間ファイル (スクリーンショットPNGと個別OCR PDF) が保存されている `intermediate` フォルダを削除します。

   **実行例:**
   ```bash
   # デフォルト設定 (Downloadsフォルダに出力、中間ファイルは残す)
   osascript kindle-all-ocr.applescript

   # 出力先を ~/Documents に指定
   osascript kindle-all-ocr.applescript "/Users/your_username/Documents"

   # 出力先を ~/Documents に指定し、中間ファイルを削除
   osascript kindle-all-ocr.applescript "/Users/your_username/Documents" --delete-intermediate

   # デフォルトの出力先 (Downloads) で、中間ファイルのみ削除
   osascript kindle-all-ocr.applescript --delete-intermediate 
   ```
3. スクリプトが自動的にページめくりとスクリーンショット撮影、OCR処理、PDF結合を行います。
4. 完了すると、指定した出力先親フォルダ内に `intermediate` フォルダ（中間ファイル保存用、削除オプション指定時は削除される）と、結合されたPDFファイル (`combined_YYYYMMDD_HHMMSS.pdf`) が保存されます。 
