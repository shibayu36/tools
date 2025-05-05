#!/bin/bash

# 位置引数の数をチェック
if [ $# -ne 2 ]; then
    echo "Usage: $0 <input_dir> <output_pdf>"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_PDF="$2"

# 入力ディレクトリ存在チェック
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' not found."
    exit 1
fi

echo "Starting PDF generation process for PNG files in $INPUT_DIR..."

# magick コマンドを使用してPNGを直接PDFに変換および結合
# 電子書籍として見る分にはボヤけが気にならない程度で圧縮を行う
echo "Converting PNG files to $OUTPUT_PDF using magick..."
if magick "$INPUT_DIR"/*.png -filter Lanczos -colorspace sRGB -resize 80% -quality 62 -sampling-factor 4:2:0 -strip -compress jpeg "$OUTPUT_PDF"; then
    echo "Successfully created $OUTPUT_PDF using magick."
else
    echo "Error: Failed to convert PNG files to PDF with magick."
    exit 1
fi

echo "Script finished successfully."
exit 0 
