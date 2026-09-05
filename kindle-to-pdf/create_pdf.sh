#!/bin/bash

# PNG画像をPDFに変換する関数
# 使用方法: convert_to_pdf <output_file> <input_files...>
convert_to_pdf() {
    local output_file="$1"
    shift
    local input_files=("$@")

    # 圧縮なし
    magick "${input_files[@]}" -strip -compress jpeg "$output_file"

    # グレースケールへの変更のみ
    # magick "${input_files[@]}" -colorspace Gray -strip -compress jpeg "$output_file"

    # 解像度落とした圧縮。電子書籍として見る分にはボヤけが気にならない程度で圧縮を行う。ただしOCR精度が落ちるので注意
    # magick "${input_files[@]}" -filter Lanczos -colorspace sRGB -resize 80% -quality 62 -sampling-factor 4:2:0 -strip -compress jpeg "$output_file"
}

# PDFにOCRでテキストレイヤーを付与する関数
# 使用方法: add_ocr <input_pdf> <output_pdf>
# 言語は横書き日本語+英語で固定。縦書き対応が必要になったらここで -l と --tesseract-pagesegmode を変える
add_ocr() {
    local input_pdf="$1"
    local output_pdf="$2"

    # --output-type pdf を外すとPDF/A変換で画像が再エンコードされ、convert_to_pdf で調整した画質が変わる
    ocrmypdf -l jpn+eng --output-type pdf --skip-text --jobs "$(sysctl -n hw.ncpu)" "$input_pdf" "$output_pdf"
}

usage() {
    echo "Usage: $0 <input_dir> <output_pdf> [--ocr] [--pages-per-pdf N]"
    echo "  --ocr:             Optional. Add a searchable text layer with OCR (Japanese + English)."
    echo "  --pages-per-pdf N: Optional. Number of pages per PDF file."
    echo "                     If not specified, all pages will be combined into one PDF."
    exit 1
}

POSITIONAL=()
PAGES_PER_PDF=""
OCR=false

while [ $# -gt 0 ]; do
    case "$1" in
        --ocr)
            OCR=true
            shift
            ;;
        --pages-per-pdf)
            [ $# -ge 2 ] || usage
            PAGES_PER_PDF="$2"
            shift 2
            ;;
        --*)
            echo "Error: Unknown option '$1'"
            usage
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done

[ ${#POSITIONAL[@]} -eq 2 ] || usage

INPUT_DIR="${POSITIONAL[0]}"
OUTPUT_PDF="${POSITIONAL[1]}"

# 入力ディレクトリ存在チェック
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' not found."
    exit 1
fi

if [ "$OCR" = true ] && ! command -v ocrmypdf >/dev/null 2>&1; then
    echo "Error: ocrmypdf is required for --ocr but not installed."
    echo "  brew install ocrmypdf"
    exit 1
fi

# OCR時はOCRなしの中間PDFをここに書き、失敗時も含めて終了時に削除する
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# PNGファイルのリストを取得してソート
PNG_FILES=($(ls "$INPUT_DIR"/*.png 2>/dev/null | sort))

if [ ${#PNG_FILES[@]} -eq 0 ]; then
    echo "Error: No PNG files found in $INPUT_DIR"
    exit 1
fi

# ページ分割が指定されていない場合は、全ファイル数を設定（実質的に分割なし）
if [ -z "$PAGES_PER_PDF" ]; then
    PAGES_PER_PDF=${#PNG_FILES[@]}
else
    # 数値チェック
    if ! [[ "$PAGES_PER_PDF" =~ ^[0-9]+$ ]] || [ "$PAGES_PER_PDF" -le 0 ]; then
        echo "Error: --pages-per-pdf must be a positive integer."
        exit 1
    fi
fi

# 出力ファイル名のベース名と拡張子を分離
OUTPUT_BASE="${OUTPUT_PDF%.*}"
OUTPUT_EXT="${OUTPUT_PDF##*.}"

# PDFの番号
PDF_NUM=1

# 複数PDFになるかチェック（全ファイル数がページ指定より多い場合）
IS_MULTI_PDF=false
if [ ${#PNG_FILES[@]} -gt $PAGES_PER_PDF ]; then
    IS_MULTI_PDF=true
fi

# PNGファイルを指定ページ数ごとに処理
for ((i=0; i<${#PNG_FILES[@]}; i+=PAGES_PER_PDF)); do
    # 出力ファイル名を生成
    if [ "$IS_MULTI_PDF" = true ]; then
        # 複数PDFの場合は連番を付与（3桁のゼロパディング）
        OUTPUT_FILE=$(printf "%s_%03d.%s" "$OUTPUT_BASE" "$PDF_NUM" "$OUTPUT_EXT")
    else
        # 単一PDFの場合は元のファイル名を使用
        OUTPUT_FILE="$OUTPUT_PDF"
    fi

    # このグループのファイル数を計算
    END_INDEX=$((i + PAGES_PER_PDF))
    if [ $END_INDEX -gt ${#PNG_FILES[@]} ]; then
        END_INDEX=${#PNG_FILES[@]}
    fi

    # このグループのファイルを取得
    GROUP_FILES=("${PNG_FILES[@]:$i:$PAGES_PER_PDF}")

    if [ "$OCR" = true ]; then
        # OCR失敗時に出力先へ不完全なPDFを残さないよう、変換結果は一時ファイルに書く
        CONVERTED_FILE="$TMP_DIR/converted_$PDF_NUM.pdf"
    else
        CONVERTED_FILE="$OUTPUT_FILE"
    fi

    # PDFに変換
    if ! convert_to_pdf "$CONVERTED_FILE" "${GROUP_FILES[@]}"; then
        echo "Error: Failed to convert PNG files to $OUTPUT_FILE with magick."
        exit 1
    fi

    if [ "$OCR" = true ]; then
        if ! add_ocr "$CONVERTED_FILE" "$OUTPUT_FILE"; then
            echo "Error: Failed to add OCR text layer to $OUTPUT_FILE with ocrmypdf."
            exit 1
        fi
        rm -f "$CONVERTED_FILE"
    fi

    echo "Successfully created $OUTPUT_FILE"

    PDF_NUM=$((PDF_NUM + 1))
done

exit 0
