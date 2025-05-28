#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写真整理ツール Webアプリケーション版
FlaskベースのWebアプリで、実際のファイル操作が可能です。

使用方法:
1. pip install flask
2. python photo_organizer_webapp.py
3. ブラウザで http://localhost:5000 にアクセス

作成者: AI Assistant
バージョン: 2.0
"""

from flask import Flask, render_template, render_template_string, request, jsonify, send_file
import os
import shutil
import re
from pathlib import Path
import json
import tempfile
import zipfile
from datetime import datetime

app = Flask(__name__)

# グローバル変数
current_analysis = {}

@app.route('/')
def index():
    """メインページ"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/analyze', methods=['POST'])
def analyze_directory():
    """ディレクトリを解析"""
    try:
        data = request.get_json()
        directory_path = data.get('directory_path', '')
        
        if not directory_path or not os.path.exists(directory_path):
            return jsonify({'error': '指定されたディレクトリが存在しません'}), 400
        
        # 画像ファイルを検索
        image_extensions = {
            '.jpg', '.jpeg', '.jfif', '.jpe',  # JPEG系
            '.png', '.gif', '.bmp', '.tiff', '.tif',  # 一般的な形式
            '.webp', '.avif', '.heic', '.heif',  # 新しい形式
            '.raw', '.cr2', '.nef', '.arw', '.dng',  # RAW形式
            '.svg', '.ico'  # その他
        }
        image_files = []
        
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                if Path(file).suffix.lower() in image_extensions:
                    image_files.append({
                        'name': file,
                        'path': os.path.join(root, file),
                        'relative_path': os.path.relpath(os.path.join(root, file), directory_path)
                    })
        
        # ファイルをグループ化
        groups = analyze_file_groups(image_files)
        
        # 既存フォルダを検出
        existing_folders = set()
        for item in os.listdir(directory_path):
            item_path = os.path.join(directory_path, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                existing_folders.add(item)
        
        # デバッグ情報を出力
        print(f"解析結果:")
        print(f"  - 既存フォルダ: {existing_folders}")
        print(f"  - 検出されたグループ: {list(groups.keys())}")
        for name, files in groups.items():
            if len(files) > 1:
                print(f"    複数ファイルグループ '{name}': {len(files)}ファイル")
        
        # まず複数人名ファイルを統合（1ファイルでも統合対象になる）
        groups_after_merge = merge_multiple_names(groups, existing_folders)
        
        # 1ファイルでも既存フォルダと同じ名前なら処理対象に含める
        processed_groups = {}
        single_file_groups = {}
        
        for name, files in groups_after_merge.items():
            if len(files) > 1:
                # 複数ファイルは常に処理対象
                processed_groups[name] = files
            elif len(files) == 1:
                # 1ファイルでも既存フォルダと同じ名前なら処理対象に含める
                if name in existing_folders:
                    processed_groups[name] = files
                    print(f"1ファイルグループ '{name}' を既存フォルダに移動対象として追加")
                else:
                    single_file_groups[name] = files
        
        # 結果を保存
        global current_analysis
        current_analysis = {
            'directory_path': directory_path,
            'groups': processed_groups,
            'single_file_groups': single_file_groups,
            'total_files': len(image_files),
            'existing_folders': list(existing_folders)
        }
        
        return jsonify({
            'success': True,
            'total_files': len(image_files),
            'total_groups': len(processed_groups),
            'groups': {name: len(files) for name, files in processed_groups.items()},
            'skipped_single_files': len(single_file_groups),
            'single_file_examples': list(single_file_groups.keys())[:10],
            'existing_folders': list(existing_folders)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview')
def get_preview():
    """整理プレビューを取得"""
    try:
        if not current_analysis:
            return jsonify({'error': '先にディレクトリを解析してください'}), 400
        
        preview_data = []
        for folder_name, files in current_analysis['groups'].items():
            preview_data.append({
                'folder_name': folder_name,
                'file_count': len(files),
                'files': [f['name'] for f in files[:5]]  # 最初の5ファイルのみ表示
            })
        
        return jsonify({
            'success': True,
            'preview': preview_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/organize', methods=['POST'])
def organize_files():
    """実際にファイルを整理"""
    try:
        if not current_analysis:
            return jsonify({'error': '先にディレクトリを解析してください'}), 400
        
        directory_path = current_analysis['directory_path']
        groups = current_analysis['groups']
        
        results = {
            'moved_files': 0,
            'created_folders': 0,
            'errors': []
        }
        
        for folder_name, files in groups.items():
            # フォルダを作成（既存の場合はスキップ）
            folder_path = os.path.join(directory_path, folder_name)
            folder_existed = os.path.exists(folder_path)
            
            try:
                os.makedirs(folder_path, exist_ok=True)
                if not folder_existed:
                    results['created_folders'] += 1
            except Exception as e:
                results['errors'].append(f"フォルダ作成エラー '{folder_name}': {str(e)}")
                continue
            
            # ファイルを移動
            for file_info in files:
                try:
                    source_path = file_info['path']
                    
                    # 移動元ファイルが存在するかチェック
                    if not os.path.exists(source_path):
                        results['errors'].append(f"移動元ファイルが見つかりません: {file_info['name']}")
                        continue
                    
                    # 移動先のファイル名を決定（重複回避）
                    destination_path = get_unique_filename(folder_path, file_info['name'])
                    
                    # ファイルを移動
                    try:
                        shutil.move(source_path, destination_path)
                        results['moved_files'] += 1
                        
                        # リネームされた場合のみログに記録（情報として）
                        original_name = file_info['name']
                        new_name = os.path.basename(destination_path)
                        if original_name != new_name:
                            # エラーではなく情報として記録
                            print(f"リネーム: {original_name} → {new_name}")
                    
                    except PermissionError:
                        results['errors'].append(f"アクセス権限エラー: {file_info['name']}")
                    except FileExistsError:
                        results['errors'].append(f"ファイル既存エラー: {file_info['name']}")
                    except OSError as e:
                        results['errors'].append(f"OS エラー: {file_info['name']} - {str(e)}")
                    
                except Exception as e:
                    results['errors'].append(f"予期しないエラー: {file_info['name']} - {str(e)}")
        
        # デバッグ情報を追加
        debug_info = {
            'total_groups': len(groups),
            'total_files_in_groups': sum(len(files) for files in groups.values()),
            'groups_processed': list(groups.keys())
        }
        
        return jsonify({
            'success': True,
            'results': results,
            'debug': debug_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_unique_filename(folder_path, filename):
    """重複しないファイル名を生成（シンプルなアプローチ）"""
    destination_path = os.path.join(folder_path, filename)
    
    # ファイルが存在しない場合はそのまま返す
    if not os.path.exists(destination_path):
        return destination_path
    
    # ファイル名と拡張子を分離
    base_name, extension = os.path.splitext(filename)
    
    # 複雑な番号パターンをすべて除去して、クリーンなベース名を取得
    import re
    # 複数の (数字) パターンを除去
    clean_base_name = re.sub(r'\s*\(\d+\)(?:\s*\(\d+\))*\s*$', '', base_name).strip()
    
    # フォルダ内の既存ファイルから最大番号を見つける
    max_number = 0
    if os.path.exists(folder_path):
        try:
            for existing_file in os.listdir(folder_path):
                existing_base, existing_ext = os.path.splitext(existing_file)
                if existing_ext.lower() == extension.lower():
                    # 同じクリーンなベース名で始まるファイルをチェック
                    if existing_base.startswith(clean_base_name):
                        # 番号パターンを抽出
                        remaining = existing_base[len(clean_base_name):].strip()
                        if remaining == '':
                            # 番号なしの同名ファイル
                            max_number = max(max_number, 1)
                        else:
                            # 番号付きファイルから最後の番号を取得
                            numbers = re.findall(r'\((\d+)\)', remaining)
                            if numbers:
                                last_number = int(numbers[-1])
                                max_number = max(max_number, last_number)
        except Exception:
            # エラーが発生した場合は安全な番号から開始
            max_number = 1
    
    # 新しい番号を決定
    counter = max_number + 1
    new_filename = f"{clean_base_name} ({counter}){extension}"
    new_destination_path = os.path.join(folder_path, new_filename)
    
    # 念のため、生成したファイル名が存在しないことを確認
    while os.path.exists(new_destination_path) and counter <= 1000:
        counter += 1
        new_filename = f"{clean_base_name} ({counter}){extension}"
        new_destination_path = os.path.join(folder_path, new_filename)
    
    # 無限ループ防止
    if counter > 1000:
        import time
        timestamp = int(time.time())
        new_filename = f"{clean_base_name}_{timestamp}{extension}"
        new_destination_path = os.path.join(folder_path, new_filename)
    
    return new_destination_path

@app.route('/api/get_folder_path', methods=['POST'])
def get_folder_path():
    """選択されたファイルから実際のフォルダパスを取得"""
    try:
        data = request.get_json()
        file_paths = data.get('file_paths', [])
        
        if not file_paths:
            return jsonify({'error': 'ファイルパスが提供されていません'}), 400
        
        # ブラウザからは相対パスしか取得できないため、
        # ユーザーに手動でパスを入力してもらう必要がある
        first_file_path = file_paths[0]
        
        # webkitRelativePathから基本的な情報を取得
        if '/' in first_file_path:
            folder_name = first_file_path.split('/')[0]
        elif '\\' in first_file_path:
            folder_name = first_file_path.split('\\')[0]
        else:
            folder_name = 'Unknown'
        
        return jsonify({
            'success': True,
            'folder_name': folder_name,
            'file_count': len(file_paths),
            'note': 'ブラウザの制限により、フォルダの完全なパスは取得できません。手動でパスを入力してください。',
            'requires_manual_input': True
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download_plan')
def download_plan():
    """整理計画をダウンロード"""
    try:
        if not current_analysis:
            return jsonify({'error': '先にディレクトリを解析してください'}), 400
        
        # Pythonスクリプトを生成
        script_content = generate_python_script(current_analysis['groups'])
        
        # 一時ファイルに保存
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(script_content)
            temp_path = f.name
        
        return send_file(
            temp_path,
            as_attachment=True,
            download_name=f'photo_organizer_plan_{datetime.now().strftime("%Y%m%d_%H%M%S")}.py',
            mimetype='text/plain'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def analyze_file_groups(files):
    """ファイルをグループ化"""
    groups = {}
    
    for file_info in files:
        file_name = Path(file_info['name']).stem  # 拡張子を除去
        
        # 特殊パターンの除去
        clean_name = re.sub(r'\s*-?\s*コピー$', '', file_name)
        clean_name = re.sub(r'\s*コピー$', '', clean_name)
        clean_name = re.sub(r'photo-\d+\s*\(\d+\)\s*-?\s*コピー$', '', clean_name)
        
        # "名前 (数字)" パターンの処理
        match = re.match(r'^(.+?)\s*\((\d+)\)$', clean_name)
        base_name = match.group(1).strip() if match else clean_name.strip()
        
        if base_name not in groups:
            groups[base_name] = []
        groups[base_name].append(file_info)
    
    return groups

def merge_multiple_names(groups, existing_folders):
    """複数人名ファイルを既存フォルダに統合（1ファイルでも対象）"""
    print(f"\n=== 複数人名統合処理開始 ===")
    print(f"既存フォルダ: {sorted(existing_folders)}")
    
    merged_groups = {}
    
    # すべてのグループをコピー
    for base_name, files in groups.items():
        merged_groups[base_name] = files[:]
    
    # 複数人名ファイルを既存フォルダに統合
    groups_to_merge = {}
    groups_to_remove = []
    
    for base_name in list(merged_groups.keys()):
        print(f"\n'{base_name}' の複数人名チェック:")
        
        # 既存フォルダ名で始まるかチェック（長い名前から順にチェック）
        target_folder = None
        for folder_name in sorted(existing_folders, key=len, reverse=True):
            print(f"  - '{folder_name}' で始まるかチェック: {base_name.startswith(folder_name)}")
            if base_name.startswith(folder_name) and len(base_name) > len(folder_name):
                target_folder = folder_name
                print(f"  ✅ 複数人名検出: '{base_name}' → '{target_folder}' フォルダに統合予定")
                break
        
        if target_folder:
            # 統合先フォルダが処理対象にない場合は作成
            if target_folder not in groups_to_merge:
                groups_to_merge[target_folder] = []
            
            # ファイルを統合先に移動
            groups_to_merge[target_folder].extend(merged_groups[base_name])
            print(f"  → {len(merged_groups[base_name])}ファイルを'{target_folder}'に統合")
            
            # 元のグループを削除対象に追加
            groups_to_remove.append(base_name)
        else:
            print(f"  → 複数人名ではない、そのまま '{base_name}' グループを維持")
    
    # 統合対象グループを削除
    for group_name in groups_to_remove:
        del merged_groups[group_name]
    
    # 統合されたグループを追加
    for folder_name, files in groups_to_merge.items():
        if folder_name in merged_groups:
            merged_groups[folder_name].extend(files)
            print(f"既存グループ '{folder_name}' に {len(files)}ファイル追加")
        else:
            merged_groups[folder_name] = files
            print(f"新規グループ '{folder_name}' に {len(files)}ファイル追加")
    
    print(f"\n=== 複数人名統合処理完了 ===")
    print(f"統合後のグループ: {list(merged_groups.keys())}")
    for name, files in merged_groups.items():
        print(f"  '{name}': {len(files)}ファイル")
    
    return merged_groups

def process_multiple_names(groups, existing_folders):
    """複数人名の処理（1ファイルのグループは除外）"""
    print(f"\n=== 複数人名処理開始 ===")
    print(f"既存フォルダ: {sorted(existing_folders)}")
    
    processed_groups = {}
    
    # まず、すべてのグループから2ファイル以上のものを処理対象に追加
    for base_name, files in groups.items():
        # 1ファイルのグループはスキップ
        if len(files) <= 1:
            print(f"スキップ（1ファイル）: '{base_name}'")
            continue
            
        processed_groups[base_name] = files
        print(f"処理対象: '{base_name}' ({len(files)}ファイル)")
    
    # 次に、複数人名ファイルを既存フォルダに統合
    groups_to_merge = {}
    
    for base_name in list(processed_groups.keys()):
        print(f"\n'{base_name}' の複数人名チェック:")
        
        # 既存フォルダ名で始まるかチェック（長い名前から順にチェック）
        target_folder = None
        for folder_name in sorted(existing_folders, key=len, reverse=True):
            print(f"  - '{folder_name}' で始まるかチェック: {base_name.startswith(folder_name)}")
            if base_name.startswith(folder_name) and len(base_name) > len(folder_name):
                target_folder = folder_name
                print(f"  ✅ 複数人名検出: '{base_name}' → '{target_folder}' フォルダに統合予定")
                break
        
        if target_folder:
            # 統合先フォルダが処理対象にない場合は作成
            if target_folder not in groups_to_merge:
                groups_to_merge[target_folder] = []
            
            # ファイルを統合先に移動
            groups_to_merge[target_folder].extend(processed_groups[base_name])
            print(f"  → {len(processed_groups[base_name])}ファイルを'{target_folder}'に統合")
            
            # 元のグループを削除
            del processed_groups[base_name]
        else:
            print(f"  → 複数人名ではない、そのまま '{base_name}' フォルダを作成")
    
    # 統合されたグループを追加
    for folder_name, files in groups_to_merge.items():
        if folder_name in processed_groups:
            processed_groups[folder_name].extend(files)
            print(f"既存グループ '{folder_name}' に {len(files)}ファイル追加")
        else:
            processed_groups[folder_name] = files
            print(f"新規グループ '{folder_name}' に {len(files)}ファイル追加")
    
    print(f"\n=== 複数人名処理完了 ===")
    print(f"最終的な処理対象グループ: {list(processed_groups.keys())}")
    
    return processed_groups

def generate_python_script(groups):
    """Pythonスクリプトを生成"""
    script = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写真整理スクリプト - Webアプリ版で生成
このスクリプトは写真整理ツールWebアプリ版で生成されました。
"""

import os
import shutil
from pathlib import Path

def get_unique_filename(folder_path, filename):
    """重複しないファイル名を生成（シンプルなアプローチ）"""
    destination_path = folder_path / filename
    
    # ファイルが存在しない場合はそのまま返す
    if not destination_path.exists():
        return destination_path
    
    # ファイル名と拡張子を分離
    base_name = destination_path.stem
    extension = destination_path.suffix
    
    # 複雑な番号パターンをすべて除去して、クリーンなベース名を取得
    import re
    # 複数の (数字) パターンを除去
    clean_base_name = re.sub(r'\\\\s*\\\\(\\\\d+\\\\)(?:\\\\s*\\\\(\\\\d+\\\\))*\\\\s*$', '', base_name).strip()
    
    # フォルダ内の既存ファイルから最大番号を見つける
    max_number = 0
    if folder_path.exists():
        try:
            for existing_file in folder_path.iterdir():
                if existing_file.is_file() and existing_file.suffix.lower() == extension.lower():
                    existing_base = existing_file.stem
                    # 同じクリーンなベース名で始まるファイルをチェック
                    if existing_base.startswith(clean_base_name):
                        # 番号パターンを抽出
                        remaining = existing_base[len(clean_base_name):].strip()
                        if remaining == '':
                            # 番号なしの同名ファイル
                            max_number = max(max_number, 1)
                        else:
                            # 番号付きファイルから最後の番号を取得
                            numbers = re.findall(r'\\\\((\\\\d+)\\\\)', remaining)
                            if numbers:
                                last_number = int(numbers[-1])
                                max_number = max(max_number, last_number)
        except Exception:
            # エラーが発生した場合は安全な番号から開始
            max_number = 1
    
    # 新しい番号を決定
    counter = max_number + 1
    new_filename = f"{clean_base_name} ({counter}){extension}"
    new_destination_path = folder_path / new_filename
    
    # 念のため、生成したファイル名が存在しないことを確認
    while new_destination_path.exists() and counter <= 1000:
        counter += 1
        new_filename = f"{clean_base_name} ({counter}){extension}"
        new_destination_path = folder_path / new_filename
    
    # 無限ループ防止
    if counter > 1000:
        import time
        timestamp = int(time.time())
        new_filename = f"{clean_base_name}_{timestamp}{extension}"
        new_destination_path = folder_path / new_filename
    
    return new_destination_path

def organize_photos():
    """写真ファイルを整理する"""
    current_dir = Path('.')
    
    # 整理計画
    organization_plan = {
'''
    
    for folder_name, files in groups.items():
        script += f'        "{folder_name}": [\n'
        for file_info in files:
            script += f'            "{file_info["name"]}",\n'
        script += f'        ],\n'
    
    script += '''    }
    
    print("写真整理を開始します...")
    
    moved_files = 0
    created_folders = 0
    
    for folder_name, file_names in organization_plan.items():
        print(f"\\n📁 '{folder_name}' フォルダを処理中...")
        folder_path = current_dir / folder_name
        
        # フォルダ作成
        folder_existed = folder_path.exists()
        folder_path.mkdir(exist_ok=True)
        if not folder_existed:
            created_folders += 1
            print(f"  ✅ フォルダを作成しました")
        else:
            print(f"  📂 既存フォルダを使用します")
        
        for file_name in file_names:
            source_file = current_dir / file_name
            if source_file.exists():
                try:
                    # 重複しないファイル名を取得
                    destination = get_unique_filename(folder_path, file_name)
                    
                    # ファイル移動
                    try:
                        shutil.move(str(source_file), str(destination))
                        moved_files += 1
                        
                        # リネームされた場合は通知
                        if destination.name != file_name:
                            print(f"  🔄 名前変更: {file_name} → {destination.name}")
                        else:
                            print(f"  ✅ 移動: {file_name}")
                    
                    except PermissionError:
                        print(f"  ❌ アクセス権限エラー: {file_name}")
                    except FileExistsError:
                        print(f"  ❌ ファイル既存エラー: {file_name}")
                    except OSError as e:
                        print(f"  ❌ OS エラー: {file_name} - {e}")
                        
                except Exception as e:
                    print(f"  ❌ 予期しないエラー: {file_name} - {e}")
            else:
                print(f"  ⚠️  警告: {file_name} が見つかりません")
    
    print(f"\\n🎉 整理完了！")
    print(f"📊 移動ファイル数: {moved_files}")
    print(f"📁 作成フォルダ数: {created_folders}")

if __name__ == "__main__":
    response = input("写真ファイルを整理しますか？ (y/n): ")
    if response.lower() in ['y', 'yes', 'はい']:
        organize_photos()
    else:
        print("キャンセルされました。")
'''
    
    return script

# HTMLテンプレート
HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>写真整理ツール Webアプリ版</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .main-content { padding: 40px; }
        .section {
            margin-bottom: 30px;
            padding: 20px;
            border: 2px dashed #e0e0e0;
            border-radius: 10px;
        }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
        .form-group input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        .btn-primary { background: #4facfe; color: white; }
        .btn-success { background: #28a745; color: white; }
        .btn-warning { background: #ffc107; color: #333; }
        .btn-info { background: #17a2b8; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .btn-group {
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }
        .file-input-wrapper {
            position: relative;
            display: inline-block;
        }
        .file-input {
            position: absolute;
            opacity: 0;
            width: 100%;
            height: 100%;
            cursor: pointer;
        }
        .selected-folder {
            margin-top: 15px;
            padding: 15px;
            background: #e8f5e8;
            border-radius: 8px;
            border-left: 4px solid #4caf50;
            display: none;
        }
        .modal {
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            backdrop-filter: blur(5px);
            display: none;
        }
        .modal-content {
            background-color: white;
            margin: 2% auto;
            padding: 0;
            border-radius: 15px;
            width: 90%;
            max-width: 700px;
            max-height: 90vh;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
            animation: modalSlideIn 0.3s ease;
            display: flex;
            flex-direction: column;
        }
        @keyframes modalSlideIn {
            from { transform: translateY(-50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        .modal-header {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 20px 30px;
            border-radius: 15px 15px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h2 {
            margin: 0;
            font-size: 1.5em;
        }
        .close {
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            opacity: 0.7;
            transition: opacity 0.3s;
        }
        .close:hover {
            opacity: 1;
        }
        .modal-body {
            padding: 30px;
            line-height: 1.6;
            overflow-y: auto;
            flex: 1;
            max-height: calc(90vh - 140px);
        }
        .step {
            margin-bottom: 25px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 10px;
            border-left: 4px solid #4facfe;
        }
        .step h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 1.2em;
        }
        .step h4 {
            color: #4facfe;
            margin: 15px 0 8px 0;
            font-size: 1.1em;
            border-bottom: 1px solid #e0e0e0;
            padding-bottom: 5px;
        }
        .modal-footer {
            padding: 20px 30px;
            text-align: center;
            border-top: 1px solid #e0e0e0;
            flex-shrink: 0;
            background: white;
            border-radius: 0 0 15px 15px;
        }
        .modal-body::-webkit-scrollbar {
            width: 8px;
        }
        .modal-body::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
        }
        .modal-body::-webkit-scrollbar-thumb {
            background: #4facfe;
            border-radius: 4px;
        }
        .modal-body::-webkit-scrollbar-thumb:hover {
            background: #3a8bfe;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-number { font-size: 2em; font-weight: bold; color: #4facfe; }
        .stat-label { color: #666; }
        .preview-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        .folder-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #4facfe;
        }
        .log {
            background: #2d3748;
            color: #e2e8f0;
            padding: 20px;
            border-radius: 10px;
            font-family: monospace;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 20px;
        }
        .hidden { display: none; }
        .error { color: #dc3545; }
        .success { color: #28a745; }
        
        /* レスポンシブ対応 */
        @media (max-width: 768px) {
            .modal-content {
                width: 95%;
                margin: 1% auto;
                max-height: 95vh;
            }
            
            .modal-body {
                padding: 20px;
                max-height: calc(95vh - 120px);
            }
            
            .modal-footer {
                padding: 15px 20px;
            }
            
            .step {
                padding: 15px;
                margin-bottom: 15px;
            }
            
            .modal-header {
                padding: 15px 20px;
            }
            
            .modal-header h2 {
                font-size: 1.3em;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📸 写真整理ツール Webアプリ版</h1>
            <p>実際のファイル操作が可能な高機能版</p>
        </div>
        
        <div class="main-content">
            <div class="section">
                <h2>📁 ディレクトリを指定</h2>
                <div class="form-group">
                    <label for="directoryPath">整理したい写真フォルダのパス:</label>
                    <input type="text" id="directoryPath" placeholder="例: C:/Users/YourName/Pictures">
                    <small style="color: #666; margin-top: 5px; display: block;">
                        💡 「📁 フォルダ選択」ボタンを使うと、フォルダを選択してパスを簡単に入力できます
                    </small>
                </div>
                <div class="btn-group">
                    <button class="btn btn-primary" onclick="analyzeDirectory()">🔍 解析開始</button>
                    <div class="file-input-wrapper">
                        <input type="file" id="folderInput" class="file-input" webkitdirectory multiple accept="image/*">
                        <button class="btn btn-warning">📁 フォルダ選択</button>
                    </div>
                    <button class="btn btn-info" onclick="showUsageModal()">❓ 使い方</button>
                </div>
                <div id="selectedFolder" class="selected-folder">
                    <strong>選択されたフォルダ:</strong> <span id="selectedFolderPath"></span>
                    <br><small style="color: #666;">フォルダ選択後、完全なパスを入力してください</small>
                </div>
            </div>
            
            <div id="statsSection" class="hidden">
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number" id="totalFiles">0</div>
                        <div class="stat-label">画像ファイル</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="totalGroups">0</div>
                        <div class="stat-label">作成予定フォルダ</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number" id="skippedFiles">0</div>
                        <div class="stat-label">スキップファイル</div>
                    </div>
                </div>
            </div>
            
            <div id="previewSection" class="section hidden">
                <h2>📋 整理プレビュー</h2>
                <div id="previewGrid" class="preview-grid"></div>
                <div style="margin-top: 20px;">
                    <button class="btn btn-success" onclick="organizeFiles()">✅ 整理を実行</button>
                    <button class="btn btn-warning" onclick="downloadPlan()">💾 計画をダウンロード</button>
                </div>
            </div>
            
            <div id="logSection" class="log hidden"></div>
        </div>
    </div>

    <!-- 使い方モーダル -->
    <div id="usageModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>📖 写真整理ツールの使い方</h2>
                <span class="close" onclick="closeUsageModal()">&times;</span>
            </div>
            <div class="modal-body">
                <div class="step">
                    <h3>🎯 このツールの目的</h3>
                    <p>同じ名前の写真ファイルを自動的にフォルダ分けして整理し、<strong>フォルダも自動で作成</strong>します。</p>
                    
                    <h4>📋 基本的な整理例</h4>
                    <p><strong>例1：</strong> <code>田中.jpg</code>, <code>田中 (1).jpg</code>, <code>田中 (2).jpg</code><br>
                    → <code>田中</code>フォルダを自動作成してまとめる</p>
                    
                    <p><strong>例2：</strong> <code>佐藤.png</code>, <code>佐藤コピー.png</code>, <code>佐藤 (3).png</code><br>
                    → <code>佐藤</code>フォルダを自動作成してまとめる</p>
                    
                    <h4>🔄 複数人名の自動統合</h4>
                    <p><strong>例：</strong> <code>田中山田.jpg</code>ファイルがある場合<br>
                    → 既存の<code>田中</code>フォルダがあれば、そこに自動移動</p>
                    
                    <p><strong>例：</strong> <code>鈴木田中佐藤.jpg</code>ファイルがある場合<br>
                    → 既存の<code>鈴木</code>フォルダがあれば、そこに自動移動（最長一致）</p>
                    
                    <h4>📁 1ファイルでも移動対象</h4>
                    <p>通常1ファイルのみのグループはスキップされますが、<strong>既存フォルダと同じ名前</strong>なら移動対象になります。</p>
                    <p><strong>例：</strong> <code>田中</code>フォルダが既にあり、<code>田中新.jpg</code>が1ファイルだけでも<code>田中</code>フォルダに移動</p>
                </div>
                
                <div class="step">
                    <h3>📁 フォルダ選択の使い方</h3>
                    <p><strong>⚠️ 重要：</strong> このアプリでは、ブラウザのセキュリティ制限により、<strong>ファイル選択による直接のパス入力ができません</strong>。</p>
                                        <h4>📋 パスの取得方法</h4>
                    <p><strong>1.</strong> 「📁 フォルダ選択」ボタンをクリック</p>
                    <p><strong>2.</strong> フォルダを開き、アドレスバーを右クリック「アドレスをテキストとしてコピー」</p>
                    <p><strong>3.</strong> コピーしたパスを入力欄に貼り付け</p>                    
                    <h4>💡 パス入力例</h4>
                    <p><code>C:\Users\YourName\Pictures\写真フォルダ</code></p>
                    <p><code>D:\Photos\2024年\家族写真</code></p>
                    <p><strong>注意：</strong> 必ず完全なパス（ドライブ文字から）を入力してください</p>
                </div>
                
                <div class="step">
                    <h3>⚙️ 整理の流れ</h3>
                    <p><strong>1.</strong> パスを入力 → 「🔍 解析開始」</p>
                    <p><strong>2.</strong> 検出されたファイルを確認 → 「👁️ 整理プレビュー」</p>
                    <p><strong>3.</strong> 整理計画を確認 → 「✅ 整理を実行」</p>
                </div>
                
                <div class="step">
                    <h3>🔧 特殊機能</h3>
                    <p><strong>• 複数人名対応：</strong> 「田中佐藤.jpg」→ 既存の「田中」フォルダに移動</p>
                    <p><strong>• 1ファイル対応：</strong> 1ファイルでも既存フォルダと同名なら移動</p>
                    <p><strong>• 重複回避：</strong> 同名ファイルは自動的にリネーム</p>
                </div>
                
                <div class="step">
                    <h3>⚠️ 注意事項</h3>
                    <p><strong>• バックアップ推奨：</strong> 実行前に重要なファイルのバックアップを取ってください</p>
                    <p><strong>• 1ファイルスキップ：</strong> 1ファイルのみのグループは基本的にスキップされます</p>
                    <p><strong>• パス入力必須：</strong> フォルダ選択後は必ず完全なパスを入力してください</p>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-primary" onclick="closeUsageModal()">理解しました</button>
            </div>
        </div>
    </div>

    <script>
        function log(message, type = 'info') {
            const logSection = document.getElementById('logSection');
            logSection.classList.remove('hidden');
            const timestamp = new Date().toLocaleTimeString();
            const className = type === 'error' ? 'error' : type === 'success' ? 'success' : '';
            logSection.innerHTML += `<div class="${className}">[${timestamp}] ${message}</div>`;
            logSection.scrollTop = logSection.scrollHeight;
        }

        async function analyzeDirectory() {
            const directoryPath = document.getElementById('directoryPath').value;
            if (!directoryPath) {
                alert('ディレクトリパスを入力してください');
                return;
            }

            log('ディレクトリを解析中...', 'info');

            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ directory_path: directoryPath })
                });

                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('totalFiles').textContent = data.total_files;
                    document.getElementById('totalGroups').textContent = data.total_groups;
                    document.getElementById('skippedFiles').textContent = data.skipped_single_files || 0;
                    document.getElementById('statsSection').classList.remove('hidden');
                    
                    log(`解析完了: ${data.total_files}ファイル、${data.total_groups}グループ、${data.skipped_single_files || 0}ファイルスキップ`, 'success');
                    
                    if (data.single_file_examples && data.single_file_examples.length > 0) {
                        log(`スキップ例: ${data.single_file_examples.slice(0, 5).join(', ')}`, 'info');
                    }
                    
                    // プレビューを取得
                    showPreview();
                } else {
                    log(`エラー: ${data.error}`, 'error');
                }
            } catch (error) {
                log(`エラー: ${error.message}`, 'error');
            }
        }

        async function showPreview() {
            try {
                const response = await fetch('/api/preview');
                const data = await response.json();
                
                if (data.success) {
                    const previewGrid = document.getElementById('previewGrid');
                    previewGrid.innerHTML = '';
                    
                    data.preview.forEach(folder => {
                        const card = document.createElement('div');
                        card.className = 'folder-card';
                        card.innerHTML = `
                            <h4>📁 ${folder.folder_name}</h4>
                            <p>${folder.file_count} ファイル</p>
                            <small>${folder.files.join(', ')}${folder.file_count > 5 ? '...' : ''}</small>
                        `;
                        previewGrid.appendChild(card);
                    });
                    
                    document.getElementById('previewSection').classList.remove('hidden');
                    log('プレビューを表示しました', 'success');
                }
            } catch (error) {
                log(`エラー: ${error.message}`, 'error');
            }
        }

        async function organizeFiles() {
            if (!confirm('ファイルを実際に移動します。よろしいですか？')) {
                return;
            }

            log('ファイル整理を開始...', 'info');

            try {
                const response = await fetch('/api/organize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const data = await response.json();
                
                if (data.success) {
                    const results = data.results;
                    const debug = data.debug;
                    log(`整理完了: ${results.moved_files}ファイル移動、${results.created_folders}フォルダ作成`, 'success');
                    
                    if (debug) {
                        log(`デバッグ: ${debug.total_groups}グループ、${debug.total_files_in_groups}ファイル処理対象`, 'info');
                        if (debug.total_files_in_groups > results.moved_files) {
                            const unmoved = debug.total_files_in_groups - results.moved_files;
                            log(`警告: ${unmoved}ファイルが移動されませんでした`, 'error');
                        }
                    }
                    
                    if (results.errors.length > 0) {
                        results.errors.forEach(error => log(`エラー: ${error}`, 'error'));
                    }
                } else {
                    log(`エラー: ${data.error}`, 'error');
                }
            } catch (error) {
                log(`エラー: ${error.message}`, 'error');
            }
        }

        async function downloadPlan() {
            try {
                const response = await fetch('/api/download_plan');
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'photo_organizer_plan.py';
                    a.click();
                    window.URL.revokeObjectURL(url);
                    log('整理計画をダウンロードしました', 'success');
                }
            } catch (error) {
                log(`エラー: ${error.message}`, 'error');
            }
        }

        // フォルダ選択機能
        document.getElementById('folderInput').addEventListener('change', async function(event) {
            // アップロード確認ダイアログを防ぐ
            event.preventDefault();
            const files = event.target.files;
            if (files.length > 0) {
                log('フォルダパスを取得中...', 'info');
                
                try {
                    // ファイルパスの配列を作成
                    const filePaths = Array.from(files).map(file => {
                        // 可能な限り完全なパスを取得
                        if (file.path) {
                            return file.path; // Electronなどの環境
                        } else if (file.webkitRelativePath) {
                            return file.webkitRelativePath; // 通常のブラウザ
                        } else {
                            return file.name; // フォールバック
                        }
                    });
                    
                    // サーバーにパス解析を依頼
                    const response = await fetch('/api/get_folder_path', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ file_paths: filePaths })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        if (data.requires_manual_input) {
                            // 手動入力が必要な場合
                            const folderName = data.folder_name;
                            const fileCount = data.file_count;
                            
                            // 選択されたフォルダ情報を表示
                            const displayText = `${folderName} (${fileCount}ファイル)`;
                            document.getElementById('selectedFolderPath').textContent = displayText;
                            document.getElementById('selectedFolder').style.display = 'block';
                            
                            log(`フォルダが選択されました: ${folderName} (${fileCount}ファイル)`, 'success');
                            log(data.note, 'info');
                            
                            // ユーザーに完全なパスの入力を促す
                            const userPath = prompt(
                                `📁 フォルダ "${folderName}" が選択されました (${fileCount}ファイル)\\n\\n` +
                                `このフォルダの完全なパスを入力してください:\\n\\n` +
                                `💡 エクスプローラーでフォルダを右クリック → "パスのコピー" で取得できます\\n\\n` +
                                `例: C:/Users/YourName/Pictures/${folderName}\\n` +
                                `例: D:/Photos/${folderName}\\n\\n` +
                                `キャンセルした場合は、手動でパス入力欄に入力してください。`,
                                ``
                            );
                            
                            if (userPath && userPath.trim()) {
                                document.getElementById('directoryPath').value = userPath.trim();
                                log('パスが設定されました。解析を開始してください。', 'success');
                            } else {
                                log('パスが入力されませんでした。手動でパス入力欄に入力してください。', 'info');
                                // パス入力欄にフォーカス
                                document.getElementById('directoryPath').focus();
                            }
                            
                            // ファイル入力をリセットしてアップロードを防ぐ
                            document.getElementById('folderInput').value = '';
                        } else {
                            // 完全なパスが取得できた場合（稀なケース）
                            document.getElementById('directoryPath').value = data.folder_path;
                            
                            const displayText = `${data.folder_path} (${data.file_count}ファイル)`;
                            document.getElementById('selectedFolderPath').textContent = displayText;
                            document.getElementById('selectedFolder').style.display = 'block';
                            
                            log(`フォルダが選択されました: ${data.file_count}ファイル`, 'success');
                            log('パス入力欄に設定されました。解析を開始してください。', 'info');
                        }
                    } else {
                        throw new Error(data.error || 'パス取得に失敗しました');
                    }
                } catch (error) {
                    log(`エラー: ${error.message}`, 'error');
                    
                    // フォールバック: 基本的な情報のみ表示
                    const firstFile = files[0];
                    const folderName = firstFile.webkitRelativePath ? 
                        firstFile.webkitRelativePath.split('/')[0] : 'Unknown';
                    const fallbackPath = `選択されたフォルダ: ${folderName} (${files.length}ファイル)`;
                    
                    document.getElementById('directoryPath').value = fallbackPath;
                    document.getElementById('selectedFolderPath').textContent = fallbackPath;
                    document.getElementById('selectedFolder').style.display = 'block';
                    
                    log('基本情報のみ設定されました。手動でパスを修正してください。', 'info');
                }
                
                // 処理完了後、ファイル入力をリセットしてアップロードを防ぐ
                document.getElementById('folderInput').value = '';
            }
        });

        // アップロード防止の設定
        function preventFileUpload() {
            // ページ全体でファイルドロップを無効化
            document.addEventListener('dragover', function(e) {
                e.preventDefault();
            });
            
            document.addEventListener('drop', function(e) {
                e.preventDefault();
            });
            
            // フォーム送信を無効化
            document.addEventListener('submit', function(e) {
                e.preventDefault();
                return false;
            });
        }
        
        // 使い方モーダル制御
        function showUsageModal() {
            document.getElementById('usageModal').style.display = 'block';
            log('使い方ガイドを表示しました', 'info');
        }
        
        function closeUsageModal() {
            document.getElementById('usageModal').style.display = 'none';
        }
        
        // モーダル外クリックで閉じる
        window.addEventListener('click', function(event) {
            const modal = document.getElementById('usageModal');
            if (event.target === modal) {
                closeUsageModal();
            }
        });

        // 初期化
        preventFileUpload();
        log('写真整理ツール Webアプリ版が起動しました', 'info');
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("=" * 50)
    print("写真整理ツール Webアプリ版")
    print("=" * 50)
    print("ブラウザで http://localhost:5000 にアクセスしてください")
    print("終了するには Ctrl+C を押してください")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000) 