#!/bin/bash

ENABLE_OCR="false"
INPUT_DIR=""
OUTPUT_PDF=""
POSITIONAL_ARGS=()

# 引数パース
while [[ $# -gt 0 ]]; do
  case $1 in
    --enable-ocr)
      ENABLE_OCR="true"
      shift
      ;;
    *)
      POSITIONAL_ARGS+=("$1")
      shift
      ;;
  esac
done

# 位置引数の数をチェック
if [ ${#POSITIONAL_ARGS[@]} -ne 2 ]; then
    echo "Usage: $0 <input_dir> <output_pdf> [--enable-ocr]"
    exit 1
fi

INPUT_DIR="${POSITIONAL_ARGS[0]}"
OUTPUT_PDF="${POSITIONAL_ARGS[1]}"

# 入力ディレクトリ存在チェック
if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: Input directory '$INPUT_DIR' not found."
    exit 1
fi

if [ "$ENABLE_OCR" = "true" ]; then
    echo "Starting OCR and PDF generation process for PNG files in $INPUT_DIR..."
else
    echo "Starting PDF generation (without OCR) process for PNG files in $INPUT_DIR..."
fi

# OCR実行 (中間PDFファイルは入力ディレクトリ内に作成)
processed_pdfs=()
shopt -s nullglob # マッチするファイルがない場合に空になるように設定
for img_file in "$INPUT_DIR"/*.png; do
    base_name=$(basename "$img_file" .png)
    pdf_output_path="$INPUT_DIR/${base_name}.pdf" # Use corrected path generation

    if [ "$ENABLE_OCR" = "true" ]; then
        echo "Processing $img_file with OCR..."
        # Tesseractは出力ファイル名に拡張子.pdfを自動で付けるため、ベース名のみ渡す
        tesseract_output_base="$INPUT_DIR/$base_name"
        if tesseract "$img_file" "$tesseract_output_base" -l jpn pdf; then
            echo "Successfully created $pdf_output_path via Tesseract"
            processed_pdfs+=("$pdf_output_path")
        else
            echo "Error: Failed to process $img_file with Tesseract."
            exit 1
        fi
    else
        echo "Processing $img_file without OCR (converting to PDF using sips)..."
        if sips -s format pdf "$img_file" --out "$pdf_output_path" > /dev/null 2>&1; then # sipsの出力を抑制
            echo "Successfully created $pdf_output_path via sips"
            processed_pdfs+=("$pdf_output_path")
        else
            echo "Error: Failed to convert $img_file to PDF with sips."
            exit 1
        fi
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
