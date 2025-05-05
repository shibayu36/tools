-- 新規フォルダを作成する関数
on createFolder(folderPath)
	do shell script "mkdir -p " & quoted form of folderPath
end createFolder

-- スクリーンショットを撮る関数
on takeScreenshot(savePath, x, y, width, height)
	do shell script "screencapture -R " & x & "," & y & "," & width & "," & height & " " & quoted form of savePath
end takeScreenshot

on run argv
	-- Default values
	set defaultOutputParentPosix to POSIX path of (path to downloads folder)
	set outputParentPosix to defaultOutputParentPosix
	set enableOCR to false
	set isLeftToRight to false -- デフォルト: 左めくり（標準的な読み方）

	-- 引数をパース
	repeat with aRef in argv
		set arg to contents of aRef
		if arg = "--enable-ocr" then
			set enableOCR to true
		else if arg = "--left-to-right" then
			set isLeftToRight to true
		else if arg does not start with "--" then
			-- フラグでない引数は出力パスとみなす
			set outputParentPosix to arg
			-- 末尾のスラッシュがあれば削除
			if outputParentPosix ends with "/" then
				set outputParentPosix to text 1 thru -2 of outputParentPosix
			end if
		else
			-- 不明なフラグはログに出力する（エラーにはしない）
			log "不明なフラグ: " & arg
		end if
	end repeat

	set pages to 3 -- スクリーンショット枚数
	-- isLeftToRight フラグに基づいてキーコードを設定
	if isLeftToRight then
		set keychar to (ASCII character 29) -- 右矢印（左から右へのページめくり）
	else
		set keychar to (ASCII character 28) -- 左矢印（デフォルト：右から左へのページめくり）
	end if
	set currentDate to do shell script "date +%Y%m%d_%H%M%S"
	set folderPath to outputParentPosix & "/intermediate/"

	-- 新規フォルダの作成
	createFolder(folderPath)

	-- Kindleアプリの前面化
	tell application "Amazon Kindle" to activate
	delay 1.0

	-- Kindleのウインドウサイズを取得
	tell application "System Events" to tell process "Amazon Kindle"
		set {xPos, yPos} to value of attribute "AXPosition" of front window
		set {wSize, hSize} to value of attribute "AXSize" of front window
	end tell

	-- スクリーンショットを取得
	set screenshotPaths to {}
	repeat with i from 1 to pages
		set screenshotPath to folderPath & "screenshot_" & i & ".png"
		
		-- スクリーンショットを撮影
		takeScreenshot(screenshotPath, xPos, yPos, wSize, hSize)
		
		-- スクリーンショットのパスをリストに追加
		copy screenshotPath to end of screenshotPaths
		
		delay 0.3 -- スクリーンショット保存時間
		
		-- ページめくり
		tell application "System Events"
			keystroke keychar
			delay 0.2 -- ページめくり後の安定時間
		end tell
	end repeat

	-- シェルスクリプトを実行してOCRとPDF結合を行う
	tell application "System Events"
		set scriptPath to path to me
		set scriptFolder to POSIX path of (container of scriptPath)
	end tell

	set scriptToRun to scriptFolder & "/ocr_and_combine.sh"
	set outputPdfPath to outputParentPosix & "/combined_" & currentDate & ".pdf"

	-- enableOCR の値を引数に追加
	set shellCommand to quoted form of scriptToRun & " " & quoted form of folderPath & " " & quoted form of outputPdfPath & " " & enableOCR

	try
		set scriptResult to do shell script shellCommand
		log "シェルスクリプトが完了しました。\\n\\n出力:\\n" & scriptResult
		if enableOCR then
			return "OK: " & outputPdfPath
		else
			-- OCRが無効な場合もPDFは生成されるので、そのパスを返す
			return "OK (No OCR): " & outputPdfPath
		end if
	on error errMsg number errNum
		log "シェルスクリプト実行エラー: " & errMsg & " (エラー番号: " & errNum & ")"
		error "Error: " & errMsg number errNum
	end try
end run
