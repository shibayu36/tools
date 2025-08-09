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

# 位置引数の数をチェック
if [ $# -lt 2 ] || [ $# -gt 3 ]; then
    echo "Usage: $0 <input_dir> <output_pdf> [pages_per_pdf]"
    echo "  pages_per_pdf: Optional. Number of pages per PDF file."
    echo "                 If not specified, all pages will be combined into one PDF."
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_PDF="$2"
PAGES_PER_PDF="$3"

# 入力ディレクトリ存在チェック
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' not found."
    exit 1
fi

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
        echo "Error: pages_per_pdf must be a positive integer."
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

    # PDFに変換
    if convert_to_pdf "$OUTPUT_FILE" "${GROUP_FILES[@]}"; then
        echo "Successfully created $OUTPUT_FILE"
    else
        echo "Error: Failed to convert PNG files to $OUTPUT_FILE with magick."
        exit 1
    fi

    PDF_NUM=$((PDF_NUM + 1))
done

exit 0
