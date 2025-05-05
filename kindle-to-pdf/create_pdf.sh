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

# PDF変換実行 (中間PDFファイルは入力ディレクトリ内に作成)
processed_pdfs=()
shopt -s nullglob # マッチするファイルがない場合に空になるように設定
for img_file in "$INPUT_DIR"/*.png; do
    base_name=$(basename "$img_file" .png)
    pdf_output_path="$INPUT_DIR/${base_name}.pdf"

    echo "Processing $img_file (converting to PDF using sips)..."
    if sips -s format pdf "$img_file" --out "$pdf_output_path" > /dev/null 2>&1; then # sipsの出力を抑制
        echo "Successfully created $pdf_output_path via sips"
        processed_pdfs+=("$pdf_output_path")
    else
        echo "Error: Failed to convert $img_file to PDF with sips."
        exit 1
    fi
done
shopt -u nullglob # 設定を元に戻す

# 処理されたPDFがない場合は終了
if [ ${#processed_pdfs[@]} -eq 0 ]; then
    echo "No PNG files found or processed in $INPUT_DIR. Exiting."
    exit 0
fi

echo "Combining PDF files into $OUTPUT_PDF..."

# gsコマンドの実行 (ファイルリストは配列展開で渡す)
# shellcheck disable=SC2086
if gs -dBATCH -dNOPAUSE -q -dAutoRotatePages=/None -sDEVICE=pdfwrite -sOutputFile="$OUTPUT_PDF" "${processed_pdfs[@]}"; then
    echo "Successfully combined PDFs into $OUTPUT_PDF."
else
    echo "Error: Failed to combine PDFs with Ghostscript."
    exit 1
fi

echo "Script finished successfully."
exit 0 
