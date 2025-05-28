#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写真整理ツール - ローカルWebサーバー
HTMLから直接Pythonスクリプトを実行するためのローカルサーバー

使用方法:
1. python photo_organizer_server.py
2. ブラウザで http://localhost:8000 にアクセス
3. HTMLから直接写真整理を実行

作成者: AI Assistant
"""

import http.server
import socketserver
import json
import os
import shutil
import re
from pathlib import Path
import urllib.parse
from datetime import datetime

class PhotoOrganizerHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/execute-organizer':
            self.handle_organize_request()
        else:
            self.send_error(404)
    
    def handle_organize_request(self):
        try:
            # リクエストデータを取得
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            organization_plan = data.get('organizationPlan', {})
            folder_path = data.get('folderPath', '')
            
            if not organization_plan:
                self.send_json_response({'error': '整理計画がありません'}, 400)
                return
            
            # 写真整理を実行
            result = self.organize_photos(organization_plan, folder_path)
            
            # 結果を返す
            self.send_json_response(result)
            
        except Exception as e:
            self.send_json_response({'error': str(e)}, 500)
    
    def organize_photos(self, organization_plan, folder_path):
        """写真ファイルを整理する"""
        # 現在のディレクトリを基準にフォルダパスを解決
        if folder_path:
            # ブラウザから送られてくるフォルダパスを処理
            # 通常は相対パスなので、絶対パスに変換する必要がある場合がある
            target_dir = Path(folder_path) if os.path.isabs(folder_path) else Path('.') / folder_path
        else:
            target_dir = Path('.')
        
        if not target_dir.exists():
            return {'error': f'指定されたディレクトリが存在しません: {target_dir}'}
        
        results = {
            'moved_files': 0,
            'created_folders': 0,
            'errors': []
        }
        
        # 画像ファイルの拡張子
        image_extensions = {
            '.jpg', '.jpeg', '.jfif', '.jpe',
            '.png', '.gif', '.bmp', '.tiff', '.tif',
            '.webp', '.avif', '.heic', '.heif',
            '.raw', '.cr2', '.nef', '.arw', '.dng',
            '.svg', '.ico'
        }
        
        # 既存フォルダを検出
        existing_folders = set()
        for item in target_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.') and item.name != '__pycache__':
                existing_folders.add(item.name)
        
        # 実際のファイルを検索してマッピング
        actual_files = {}
        for file_path in target_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                actual_files[file_path.name] = file_path
        
        # 整理計画に基づいてファイルを移動
        for folder_name, file_names in organization_plan.items():
            # フォルダを作成
            folder_path = target_dir / folder_name
            folder_existed = folder_path.exists()
            
            try:
                folder_path.mkdir(exist_ok=True)
                if not folder_existed:
                    results['created_folders'] += 1
            except Exception as e:
                results['errors'].append(f"フォルダ作成エラー '{folder_name}': {str(e)}")
                continue
            
            # ファイルを移動
            for file_name in file_names:
                if file_name in actual_files:
                    source_path = actual_files[file_name]
                    try:
                        # 重複しないファイル名を取得
                        destination_path = self.get_unique_filename(folder_path, file_name)
                        
                        # ファイルを移動
                        shutil.move(str(source_path), str(destination_path))
                        results['moved_files'] += 1
                        
                        # リネームされた場合の記録
                        if destination_path.name != file_name:
                            print(f"リネーム: {file_name} → {destination_path.name}")
                        
                    except Exception as e:
                        results['errors'].append(f"ファイル移動エラー '{file_name}': {str(e)}")
                else:
                    results['errors'].append(f"ファイルが見つかりません: {file_name}")
        
        return results
    
    def get_unique_filename(self, folder_path, filename):
        """重複しないファイル名を生成"""
        destination_path = folder_path / filename
        
        if not destination_path.exists():
            return destination_path
        
        base_name = destination_path.stem
        extension = destination_path.suffix
        
        # 複雑な番号パターンをすべて除去
        clean_base_name = re.sub(r'\s*\(\d+\)(?:\s*\(\d+\))*\s*$', '', base_name).strip()
        
        # フォルダ内の既存ファイルから最大番号を見つける
        max_number = 0
        if folder_path.exists():
            try:
                for existing_file in folder_path.iterdir():
                    if existing_file.is_file() and existing_file.suffix.lower() == extension.lower():
                        existing_base = existing_file.stem
                        if existing_base.startswith(clean_base_name):
                            remaining = existing_base[len(clean_base_name):].strip()
                            if remaining == '':
                                max_number = max(max_number, 1)
                            else:
                                numbers = re.findall(r'\((\d+)\)', remaining)
                                if numbers:
                                    last_number = int(numbers[-1])
                                    max_number = max(max_number, last_number)
            except Exception:
                max_number = 1
        
        counter = max_number + 1
        new_filename = f"{clean_base_name} ({counter}){extension}"
        new_destination_path = folder_path / new_filename
        
        while new_destination_path.exists() and counter <= 1000:
            counter += 1
            new_filename = f"{clean_base_name} ({counter}){extension}"
            new_destination_path = folder_path / new_filename
        
        if counter > 1000:
            import time
            timestamp = int(time.time())
            new_filename = f"{clean_base_name}_{timestamp}{extension}"
            new_destination_path = folder_path / new_filename
        
        return new_destination_path
    
    def send_json_response(self, data, status_code=200):
        """JSON レスポンスを送信"""
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        response_data = json.dumps(data, ensure_ascii=False, indent=2)
        self.wfile.write(response_data.encode('utf-8'))
    
    def do_OPTIONS(self):
        """CORS プリフライトリクエストを処理"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def main():
    PORT = 8000
    
    print("=" * 50)
    print("写真整理ツール - ローカルWebサーバー")
    print("=" * 50)
    print(f"サーバーを起動中... ポート: {PORT}")
    print(f"ブラウザで http://localhost:{PORT}/photo_organizer_gui.html にアクセスしてください")
    print("終了するには Ctrl+C を押してください")
    print("=" * 50)
    
    try:
        with socketserver.TCPServer(("", PORT), PhotoOrganizerHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しました。")
    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main() 