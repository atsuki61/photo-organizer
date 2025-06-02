@echo off
chcp 65001 > nul
echo ==========================================
echo 写真整理ツール - Webアプリ版起動
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

REM Flaskがインストールされているかチェック
python -c "import flask" > nul 2>&1
if errorlevel 1 (
    echo Flaskがインストールされていません。インストールしています...
    echo.
    pip install flask
    if errorlevel 1 (
        echo エラー: Flaskのインストールに失敗しました。
        echo 手動で 'pip install flask' を実行してください。
        echo.
        pause
        exit /b 1
    )
    echo Flaskがインストールされました。
    echo.
)

echo Webアプリケーションを起動します...
echo.
echo 5秒後にブラウザが自動的に開きます。
echo もし開かない場合は、手動で http://localhost:5000 にアクセスしてください。
echo.
echo 終了するには Ctrl+C を押してください
echo.

REM ブラウザを遅延実行で自動オープン（バックグラウンド）
start /B cmd /c "timeout /t 5 /nobreak > nul && start http://localhost:5000"

REM Webアプリを実行（フォアグラウンド）
python photo_organizer_webapp.py 