# Kindle To PDF

macOS上でKindle for Macアプリを利用し、表示されている書籍のページをスクリーンショット撮影し、単一のPDFファイルとして保存するツールです。

## 機能

- Kindle for Mac の表示内容を指定ページ数分スクリーンショット撮影 (`kindle-screenshot.applescript`)
    - 撮影中に `.` キーを押し続けることで中断可能
- 撮影されたスクリーンショット画像から不要なものを手動で削除
- 残った画像をPDFに変換し、単一ファイルに結合 (`create_pdf.sh`)
    - PDF変換・結合エンジンとして macOS標準の`sips`とGhostscript を利用

## 必要なもの (依存関係)

このツールを実行するには、以下のソフトウェアがインストールされている必要があります。

- [Ghostscript](https://ghostscript.com/)
   - PDF結合に使用

## インストール

Homebrewを使用して必要な依存関係をインストールします。

```bash
brew install ghostscript
```

## 使い方

このツールは2つのステップで実行します。

**ステップ1: スクリーンショットの撮影 (`kindle-screenshot.applescript`)**

1.  Kindle for Macアプリで、処理したい書籍を開き、最初のページを表示します。
2.  ターミナルを開き、以下のコマンドを実行します。
    ```bash
    osascript kindle-screenshot.applescript [出力先フォルダパス] --pages=<撮影枚数> [--left-to-right] [--crop-top=<ピクセル数>] [--crop-bottom=<ピクセル数>]
    ```
    - `[出力先フォルダパス]`: (必須) スクリーンショット画像を保存するフォルダを指定します。**フォルダは事前に存在している必要があります。**
    - `--pages=[撮影枚数]`: (必須) 撮影する最大ページ数を指定します。
    - `--left-to-right`: (任意) このフラグを指定すると、ページめくりが右方向（左から右へ）になります。デフォルトは左方向（右から左へ）です。
    - `--crop-top=<ピクセル数>`: (任意) スクリーンショットの上部を指定したピクセル数だけ切り取ります。デフォルトは0です。
    - `--crop-bottom=<ピクセル数>`: (任意) スクリーンショットの下部を指定したピクセル数だけ切り取ります。デフォルトは0です。

    Kindle アプリの標準的なビューでは、ヘッダーとフッターを除外するために `--crop-top=46 --crop-bottom=46` を指定するのがおすすめです。

    **実行例:**
    ```bash
    # ~/Downloads/mybook フォルダに最大200ページ撮影 (右から左へページめくり)
    osascript kindle-screenshot.applescript "$HOME/Downloads/mybook" --pages=200

    # ~/Documents/anotherbook フォルダに最大150ページ撮影 (左から右へページめくり)
    osascript kindle-screenshot.applescript "$HOME/Documents/anotherbook" --pages=150 --left-to-right
    ```
3.  スクリプトが自動的にページめくりとスクリーンショット撮影を開始します。
4.  撮影を途中で終了したい場合は、`.` (ピリオド) キーを押し続けてください。スクリプトが停止します。
5.  撮影完了後、指定した出力先フォルダを開き、表紙や目次、白紙ページなど、最終的なPDFに含めたくないスクリーンショット画像ファイル（`screenshot_XXX.png`）を手動で削除してください。

**ステップ2: PDFへの変換・結合 (`create_pdf.sh`)**

1.  ターミナルで、以下のコマンドを実行します。
    ```bash
    ./create_pdf.sh [スクリーンショット保存フォルダパス] [出力PDFファイルパス]
    ```
    - `[スクリーンショット保存フォルダパス]`: (必須) ステップ1でスクリーンショットを保存し、不要なファイルを削除したフォルダのパスを指定します。
    - `[出力PDFファイルパス]`: (必須) 結合されたPDFファイルの出力パスを指定します（例: `~/Downloads/combined_book.pdf`）。

    **実行例:**
    ```bash
    # PDFを生成
    ./create_pdf.sh "$HOME/Downloads/mybook" "$HOME/Downloads/mybook_combined.pdf"
    ```
2.  スクリプトがフォルダ内のPNGファイルを処理し、指定したパスに単一のPDFファイルとして結合・保存します。
3.  完了すると、指定した出力先に結合されたPDFファイルが作成されます。
