# Kindle To PDF

macOS上でKindle for Macアプリを利用し、表示されている書籍のページをスクリーンショット撮影し、単一のPDFファイルとして保存するツールです。

## 機能

- Kindle for Mac の表示内容を指定ページ数分スクリーンショット撮影 (`kindle-screenshot.applescript`)
    - 撮影中に `.` キーを押し続けることで中断可能
- 撮影されたスクリーンショット画像から不要なものを手動で削除
- 残った画像をPDFに変換し、単一ファイルに結合 (`create_pdf.sh`)
    - PDF変換・結合エンジンとして [ImageMagick](https://imagemagick.org/) (`magick` コマンド) を利用
    - `--ocr` を指定すると、OCRで本文をテキストとして検索・コピーできるPDFになる（LLMに読ませる用途向け）
    - `--ocr` では、目次の見出しと段落を付けたMarkdownもあわせて作成する (`ocr_to_markdown.py`)

## 必要なもの (依存関係)

このツールを実行するには、以下のソフトウェアがインストールされている必要があります。

- [ImageMagick](https://imagemagick.org/)
   - PNG画像からPDFへの変換・結合に使用
- 以下は `--ocr` を使う場合のみ
   - [uv](https://docs.astral.sh/uv/)
      - `vision_ocr.py` の実行環境（[OCRmyPDF](https://ocrmypdf.readthedocs.io/) と [ocrmac](https://github.com/straussmaximilian/ocrmac) のPythonパッケージ）を初回実行時に自動で用意する
   - [Ghostscript](https://www.ghostscript.com/)
      - OCRmyPDF がページ画像のラスタライズに使用
   - [Tesseract](https://github.com/tesseract-ocr/tesseract)
      - OCRエンジンとしては使わないが、OCRmyPDF の起動時チェックでバイナリの存在が必要
   - 以下はMarkdownを作成する場合のみ（`--no-markdown` を付けない場合）
      - [Claude Code](https://claude.com/claude-code) (`claude` コマンド)
         - PDFの目次ページの画像から見出しの一覧を抽出するのに使用
      - [Poppler](https://poppler.freedesktop.org/) (`pdftoppm` コマンド)
         - 目次を探すPDFページを画像にするのに使用

OCRエンジンには macOS 標準の Vision フレームワークを使うため、macOS でのみ動作します。

## インストール

Homebrewを使用して必要な依存関係をインストールします。

```bash
brew install imagemagick

# --ocr を使う場合
brew install uv ghostscript tesseract poppler
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
    # ~/Downloads/mybook/intermediate フォルダに最大200ページ撮影 (右から左へページめくり)
    osascript kindle-screenshot.applescript "$HOME/Downloads/mybook/intermediate" --pages=200

    # ~/Documents/anotherbook/intermediate フォルダに最大150ページ撮影 (左から右へページめくり)
    osascript kindle-screenshot.applescript "$HOME/Documents/anotherbook/intermediate" --pages=150 --left-to-right
    ```
3.  スクリプトが自動的にページめくりとスクリーンショット撮影を開始します。
4.  撮影を途中で終了したい場合は、`.` (ピリオド) キーを押し続けてください。スクリプトが停止します。
5.  撮影完了後、指定した出力先フォルダを開き、表紙や目次、白紙ページなど、最終的なPDFに含めたくないスクリーンショット画像ファイル（`screenshot_XXX.png`）を手動で削除してください。

**ステップ2: PDFへの変換・結合 (`create_pdf.sh`)**

1.  ターミナルで、以下のコマンドを実行します。
    ```bash
    ./create_pdf.sh [スクリーンショット保存フォルダパス] [出力PDFファイルパス] [--ocr] [--ocr-lang ja|en] [--no-markdown] [--pages-per-pdf <1PDFあたりのページ数>]
    ```
    - `[スクリーンショット保存フォルダパス]`: (必須) ステップ1でスクリーンショットを保存し、不要なファイルを削除したフォルダのパスを指定します。
    - `[出力PDFファイルパス]`: (任意) 結合されたPDFファイルの出力パスを指定します（例: `~/Downloads/combined_book.pdf`）。省略した場合、スクリーンショット保存フォルダの親フォルダに、親フォルダ名の `.pdf` を作成します（例: `~/Downloads/mybook/intermediate` を指定すると `~/Downloads/mybook/mybook.pdf`）。
    - `--ocr`: (任意) OCRで本文のテキストレイヤーを付与します。横書き日本語と英語を認識対象とします。LLMに読ませたり、ビューアで本文を検索・コピーしたりできるようになります。あわせて、OCR結果のテキストを出力PDFと同じ名前の `.txt` として書き出します（ページ区切りはフォームフィード）。ページ分割と併用した場合、分割された各PDFすべてにテキストレイヤーと `.txt` が付きます。さらに、目次の見出しと段落を付けたMarkdownを `.md` として書き出します（後述の「Markdownの作成」を参照）。
    - `--ocr-lang ja|en`: (任意) `--ocr` で優先する本の言語を指定します。デフォルトは `ja` です。英語の本では `en` を指定してください。日本語優先のままだと、`,` や `(` が全角になる、単語間の空白が消える、`AI` が `Al` になるなどの誤認識が増えます。
    - `--no-markdown`: (任意) `--ocr` 時のMarkdownの作成を行いません。
    - `--pages-per-pdf <1PDFあたりのページ数>`: (任意) 1つのPDFファイルに含めるページ数を指定します。指定しない場合、すべてのページが1つのPDFに結合されます。指定した場合、複数のPDFファイルが作成され、ファイル名に連番（例: `_001.pdf`, `_002.pdf`）が付きます。

    **実行例:**
    ```bash
    # すべてのページを1つのPDFに生成（~/Downloads/mybook/mybook.pdf が作成される）
    ./create_pdf.sh "$HOME/Downloads/mybook/intermediate"

    # 出力先を明示して生成
    ./create_pdf.sh "$HOME/Downloads/mybook/intermediate" "$HOME/Downloads/mybook_combined.pdf"

    # OCR付きで1つのPDFに生成
    ./create_pdf.sh "$HOME/Downloads/mybook/intermediate" --ocr

    # 英語の本をOCR付きで生成
    ./create_pdf.sh "$HOME/Downloads/mybook/intermediate" --ocr --ocr-lang en

    # 50ページごとに分割してPDFを生成（mybook_001.pdf, mybook_002.pdf, ...が作成される）
    ./create_pdf.sh "$HOME/Downloads/mybook/intermediate" --pages-per-pdf 50
    ```
2.  スクリプトがフォルダ内のPNGファイルを処理し、指定したパスにPDFファイルとして保存します。
    - ページ分割を指定した場合、複数のPDFファイルが作成されます。
    - ページ分割を指定しない場合、単一のPDFファイルが作成されます。
3.  完了すると、指定した出力先にPDFファイルが作成されます。

**`--ocr` の補足**

- OCRは `vision_ocr.py` が macOS 標準の Vision フレームワークで行い、OCRmyPDF のプラグインとしてテキストレイヤーを埋め込みます。Tesseract は日本語を細かい単語に分割して配置するため、抽出したテキストの文字間に空白が入り、太字の見出しも崩れやすい問題がありました。Vision は行単位で認識するのでこれらが起きません。
- 見開き（2ページ横並び）のスクリーンショットでは、抽出したテキストの行が左右ページで交互になることがあります。段組の分割は行っていないためです。読み順が重要な場合は Kindle を1ページ表示にして撮影してください。
- OCRの精度を保つため、`create_pdf.sh` 内の圧縮設定は「圧縮なし」のままにしてください。解像度を落とす圧縮設定はOCRの誤認識を増やします。
- 日本語グリフを持つフォント（NotoSansJP など）が未導入だと、ocrmypdf が警告を出し、テキストレイヤーは不可視で埋め込まれます。検索・コピー・LLMへの入力には支障ありませんが、ビューアで本文を選択したときにハイライトが空白に見えます。気になる場合は NotoSansJP を導入してください。
- 目安として、見開き12ページのPDFのOCRに約25秒かかります（1ページあたり約2秒）。初回実行時は uv による Python パッケージの取得で追加の時間がかかります。

**Markdownの作成 (`ocr_to_markdown.py`)**

`--ocr` を指定すると、OCR後に `ocr_to_markdown.py` が自動で実行され、出力PDFと同じ名前の `.md` を作成します。Obsidianに入れたり、LLMに読ませたりする用途向けです。

- PDFの1〜20ページを画像にして `claude -p` に渡し、目次から見出しの一覧を抽出します。目次ページが見つからない場合（Kindle版で目次がナビゲーションにしかない本など）は、本文から見出しらしい短い行を抜き出して `claude -p` に渡し、見出しの一覧を作ります。結果は `.toc.json` として保存します。
- 目次の見出しを、目次の順番どおりに本文（`.txt`）から探して照合し、Markdownの見出しにします。目次に載っていない階層（例: 目次が節までの本の項）は見出しになりません。本文で見つからなかった見出しは警告を表示します。
- それ以外の行は、画面幅で折り返された改行だけをつないで段落にします。誤字・図の中の文字・脚注などはOCR結果のまま残ります。
- ページ分割（`--pages-per-pdf`）と併用した場合は、目次が先頭のPDFにしかないため、Markdownは作成しません。
- 単体で実行することもできます。目次が21ページ以降にある場合は `--toc-pages` で範囲を指定してください。
    ```bash
    uv run ocr_to_markdown.py ~/Downloads/mybook/mybook.pdf [出力Markdownパス] [--toc-pages 1-20]
    ```

## 翻訳の容量制限になってしまったために分割したい
qpdfを活用する。OCR付きにしたい場合は、先に `--ocr` で1つのPDFを作ってから分割する。

```bash
brew install qpdf
```

```bash
qpdf input.pdf --pages . 1-20 -- output1.pdf
qpdf input.pdf --pages . 21-z -- output2.pdf
```

翻訳後に結合
```bash
qpdf --empty --pages output1.pdf output2.pdf -- merged.pdf
```
