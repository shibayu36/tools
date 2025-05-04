#!/bin/bash

# 引数チェック
if [ "$#" -lt 2 ]; then
    echo "Usage: $0 <input_dir> <output_pdf> [--delete-intermediate]"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_PDF="$2"
DELETE_INTERMEDIATE=false

# オプション引数の処理
if [ "$3" == "--delete-intermediate" ]; then
    DELETE_INTERMEDIATE=true
fi

# 入力ディレクトリ存在チェック
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' not found."
    exit 1
fi

echo "Starting OCR process for PNG files in $INPUT_DIR..."

# OCR実行 (中間PDFファイルは入力ディレクトリ内に作成)
processed_pdfs=()
shopt -s nullglob # マッチするファイルがない場合に空になるように設定
for img_file in "$INPUT_DIR"/*.png; do
    base_name=$(basename "$img_file" .png)
    pdf_output_base=$(echo "$INPUT_DIR/$base_name" | sed 's|//|/|g')
    echo "Processing $img_file..."
    pdf_output_path=$(echo "${pdf_output_base}.pdf" | sed 's|//|/|g')

    if tesseract "$img_file" "$pdf_output_base" -l jpn pdf; then
        echo "Successfully created $pdf_output_path"
        processed_pdfs+=("$pdf_output_path")
    else
        echo "Error: Failed to process $img_file with Tesseract."
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
if gs -dBATCH -dNOPAUSE -q -sDEVICE=pdfwrite -sOutputFile="$OUTPUT_PDF" "${processed_pdfs[@]}"; then
    echo "Successfully combined PDFs into $OUTPUT_PDF."
else
    echo "Error: Failed to combine PDFs with Ghostscript."
    exit 1
fi

# 中間ファイルの削除
if $DELETE_INTERMEDIATE; then
    echo "Deleting intermediate files..."
    # 個別PDFの削除
    for pdf_file in "${processed_pdfs[@]}"; do
        if [ -f "$pdf_file" ]; then
            rm "$pdf_file"
            echo "Deleted $pdf_file"
        fi
    done
fi

echo "Script finished successfully."
exit 0 
