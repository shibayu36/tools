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
	set defaultDeleteIntermediate to false

	set outputParentPosix to defaultOutputParentPosix
	set deleteIntermediate to defaultDeleteIntermediate

	-- Parse arguments
	if (count of argv) > 0 then
		-- Check if the first argument is the flag or the path
		if item 1 of argv is not "--delete-intermediate" then
			set outputParentPosix to item 1 of argv
			-- Remove trailing slash if exists
			if outputParentPosix ends with "/" then
				set outputParentPosix to text 1 thru -2 of outputParentPosix
			end if
			-- Check for the flag in the second argument
			if (count of argv) > 1 and (item 2 of argv is "--delete-intermediate") then
				set deleteIntermediate to true
			end if
		else
			-- First argument is the flag, use default path
			set deleteIntermediate to true
		end if
	end if

	set pages to 3 -- スクリーンショット数
	set keychar to (ASCII character 28) -- ページめくり方向(28=左,29=右)
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

	set deleteOption to ""
	if deleteIntermediate then
		set deleteOption to "--delete-intermediate"
	end if
	set shellCommand to quoted form of scriptToRun & " " & quoted form of folderPath & " " & quoted form of outputPdfPath & " " & deleteOption

	try
		set scriptResult to do shell script shellCommand
		log "シェルスクリプトが完了しました。\n\n出力:\n" & scriptResult
		return "OK: " & outputPdfPath -- Return generated PDF path on success
	on error errMsg number errNum
		log "シェルスクリプト実行エラー: " & errMsg & " (エラー番号: " & errNum & ")"
		error "Error: " & errMsg number errNum -- Return error to caller
	end try
end run
