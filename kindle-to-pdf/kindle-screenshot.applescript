use framework "AppKit"
use scripting additions

property kVK_ANSI_Period : 47 -- .

-- 新規フォルダを作成する関数
on createFolder(folderPath)
	do shell script "mkdir -p " & quoted form of folderPath
end createFolder

-- スクリーンショットを撮る関数
on takeScreenshot(savePath, x, y, width, height)
	do shell script "screencapture -R " & x & "," & y & "," & width & "," & height & " " & quoted form of savePath
end takeScreenshot

on isKeyDown(keyCode)
    -- kCGEventSourceStateCombinedSessionState を指定すると
    -- どのアプリで押されていても判定できる
    return (current application's CGEventSourceKeyState(¬
        current application's kCGEventSourceStateCombinedSessionState, keyCode)) as boolean
end isKeyDown

on run argv
	-- デフォルト
	set outputParentPosix to POSIX path of (path to downloads folder)
	set isLeftToRight to false -- デフォルト: 右から左
	set cropTop to 0
	set cropBottom to 0

	-- 引数をパース
	repeat with aRef in argv
		set arg to contents of aRef
		if arg = "--left-to-right" then
			set isLeftToRight to true
        else if arg starts with "--pages=" then
            -- = 以降の数字をページ数として読み込む
            set pagesText to text ((offset of "=" in arg) + 1) thru -1 of arg
            set pages to pagesText as number
		else if arg starts with "--crop-top=" then
			set cropTopText to text ((offset of "=" in arg) + 1) thru -1 of arg
			set cropTop to cropTopText as number
		else if arg starts with "--crop-bottom=" then
			set cropBottomText to text ((offset of "=" in arg) + 1) thru -1 of arg
			set cropBottom to cropBottomText as number
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

	-- isLeftToRight フラグに基づいてキーコードを設定
	if isLeftToRight then
		set keychar to (ASCII character 29) -- 右矢印（左から右へのページめくり）
	else
		set keychar to (ASCII character 28) -- 左矢印（デフォルト：右から左へのページめくり）
	end if
	set folderPath to outputParentPosix & "/"

	-- 新規フォルダの作成
	createFolder(folderPath)

	-- Kindleアプリの前面化
	tell application "Amazon Kindle" to activate
	delay 1.0

	-- Kindleのウインドウサイズを取得
	tell application "System Events" to tell process "Amazon Kindle"
		set {xPos, yPos} to value of attribute "AXPosition" of front window
		set {wSize, hSize} to value of attribute "AXSize" of front window

		-- ウインドウヘッダーのサイズ28pxとクロップ量を考慮
		set yPos to yPos + 28 + cropTop
		set hSize to hSize - 28 - cropTop - cropBottom
	end tell

	-- スクリーンショットを取得
	set screenshotPaths to {}
	repeat with i from 1 to pages
		-- .キーが押されていたら中断する
		if isKeyDown(kVK_ANSI_Period) then
			exit repeat
		end if

		set screenshotPath to folderPath & "screenshot_" & text -3 thru -1 of ("000" & i) & ".png"

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
end run
