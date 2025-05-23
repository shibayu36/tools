# 要件

## 1. 前提環境

- macOS + Kindle for Mac
- Homebrewで以下をインストール
  - tesseract（日本語OCRデータ jpn）
  - ghostscript

## 2. スクリーンショット取得

- まずは固定3ページでキャプチャを試し、高速にトライ＆エラー
- 最終的に末尾検知ロジックでページ末尾を自動判定
- 適切なdelay設定（保存待ち＋ページめくり安定）

## 3. OCR実行

- 各PNGに対し以下コマンドでOCR付きPDFを生成
```
tesseract image.png image -l jpn pdf
```
- 失敗時のリトライとログ出力をサポート

## 4. PDF結合

- ghostscriptを使用して個別PDFを1つに結合
```
gs -dBATCH -dNOPAUSE -sDEVICE=pdfwrite -sOutputFile=output.pdf *.pdf
```

## 5. 入出力管理

- タイムスタンプ付き出力フォルダ／ファイル名規則
- 中間ファイル（PNG、単体PDF）の削除オプション

## 6. エラーハンドリング＆ログ

- 各ステップの成否判定とエラー報告
- 実行状況を見やすくログ出力

## 7. 実行手順

- AppleScriptとシェルスクリプトをワンコマンドで実行
- 必要パラメータ（末尾検知フラグなど）の入力方法 

# 実装TODO

- [x] AppleScriptに固定3ページのキャプチャロジックを実装
- [x] AppleScriptからシェルスクリプト呼び出しのインターフェース追加
- [x] シェルスクリプトでPNGをOCR付きPDFに変換
- [x] ghostscriptを使ったPDF結合処理の実装
- [x] CLI引数で出力フォルダ指定 & 中間ファイル削除オプションを実装
- [ ] AppleScriptに末尾検知ロジックを実装
- [ ] OCR処理がそもそもうまくいってなさそう
- [ ] READMEおよびドキュメントの更新
- [ ] コンテンツのマージンを調整した方が良いか検討
