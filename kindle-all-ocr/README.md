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
2. `kindle-all-ocr.applescript` をスクリプトエディタで開くか、`osascript kindle-all-ocr.applescript` コマンドで実行します。
3. スクリプトが自動的にページめくりとスクリーンショット撮影、OCR処理、PDF結合を行います。
4. 完了すると、ダウンロードフォルダ内に `Kindle_Screenshots_YYYYMMDD_HHMMSS` というフォルダが作成され、その中に結合されたPDFファイル (`combined_YYYYMMDD_HHMMSS.pdf`) が保存されます。 
