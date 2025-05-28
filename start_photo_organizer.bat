@echo off
chcp 65001 > nul
echo ==========================================
echo 写真整理ツール - GUI版起動
echo ==========================================
echo.

REM Pythonがインストールされているかチェック
python --version > nul 2>&1
if errorlevel 1 (
    echo エラー: Pythonがインストールされていません。
    echo https://www.python.org/ からPythonをダウンロードしてインストールしてください。
    echo.
    pause
    exit /b 1
)

echo Pythonが見つかりました。
echo ローカルWebサーバーを起動します...
echo.
echo ブラウザで http://localhost:8000/photo_organizer_gui.html にアクセスしてください
echo 終了するには Ctrl+C を押してください
echo.

REM サーバーを起動
python photo_organizer_server.py

echo.
echo サーバーが停止しました。
pause 