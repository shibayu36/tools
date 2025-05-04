-- 新規フォルダを作成する関数
on createFolder(folderPath)
	do shell script "mkdir -p " & quoted form of folderPath
end createFolder

-- スクリーンショットを撮る関数
on takeScreenshot(savePath, x, y, width, height)
	do shell script "screencapture -R " & x & "," & y & "," & width & "," & height & " " & quoted form of savePath
end takeScreenshot

-- メインスクリプト
set pages to 3 -- スクリーンショット数
set keychar to (ASCII character 28) -- ページめくり方向(28=左,29=右)
set currentDate to do shell script "date +%Y%m%d_%H%M%S"
set folderPath to (POSIX path of (path to downloads folder)) & "Kindle_Screenshots_" & currentDate & "/"

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
