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
    """複数ディレクトリを解析"""
    try:
        data = request.get_json()
        directory_paths = data.get('directory_paths', [])
        mode = data.get('mode', 'normal')  # モードを取得、デフォルトは'normal'
        
        # 空のパスを除外
        directory_paths = [path.strip() for path in directory_paths if path and path.strip()]
        
        if not directory_paths:
            return jsonify({'error': '有効なディレクトリパスが入力されていません'}), 400
        
        # 存在しないディレクトリをチェック
        invalid_paths = []
        for path in directory_paths:
            if not os.path.exists(path):
                invalid_paths.append(path)
        
        if invalid_paths:
            return jsonify({
                'error': f'次のディレクトリが存在しません: {", ".join(invalid_paths)}'
            }), 400
        
        # 画像ファイルを検索
        image_extensions = {
            '.jpg', '.jpeg', '.jfif', '.jpe',  # JPEG系
            '.png', '.gif', '.bmp', '.tiff', '.tif',  # 一般的な形式
            '.webp', '.avif', '.heic', '.heif',  # 新しい形式
            '.raw', '.cr2', '.nef', '.arw', '.dng',  # RAW形式
            '.svg', '.ico'  # その他
        }
        
        all_image_files = []
        directory_results = {}
        
        for directory_path in directory_paths:
            image_files = []
            
            if mode == 'normal':
                # 通常モード: 指定されたディレクトリの直下にあるファイルのみをスキャン
                print(f"通常モードでスキャン: {directory_path}")
                try:
                    for item in os.listdir(directory_path):
                        item_path = os.path.join(directory_path, item)
                        if os.path.isfile(item_path) and Path(item).suffix.lower() in image_extensions:
                            image_files.append({
                                'name': item,
                                'path': item_path,
                                'relative_path': item,
                                'source_directory': directory_path
                            })
                except Exception as e:
                    print(f"ディレクトリのスキャンエラー {directory_path}: {e}")
            else:
                # 親フォルダモード: サブフォルダを含めて再帰的にスキャン
                print(f"親フォルダモードでスキャン: {directory_path}")
                for root, dirs, files in os.walk(directory_path):
                    for file in files:
                        if Path(file).suffix.lower() in image_extensions:
                            image_files.append({
                                'name': file,
                                'path': os.path.join(root, file),
                                'relative_path': os.path.relpath(os.path.join(root, file), directory_path),
                                'source_directory': root # ファイルの実際の親フォルダを記録
                            })
            
            all_image_files.extend(image_files)
            directory_results[directory_path] = {
                'file_count': len(image_files),
                'files': image_files
            }
        
        # 全ファイルをまとめてグループ化
        groups = analyze_file_groups(all_image_files)
        
        # 全ディレクトリの既存フォルダを収集
        all_existing_folders = set()
        for directory_path in directory_paths:
            for item in os.listdir(directory_path):
                item_path = os.path.join(directory_path, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    all_existing_folders.add(item)
        
        # デバッグ情報を出力
        print(f"複数フォルダ解析結果:")
        print(f"  - 対象ディレクトリ: {directory_paths}")
        print(f"  - 実行モード: {mode}")
        print(f"  - 総ファイル数: {len(all_image_files)}")
        print(f"  - 既存フォルダ: {all_existing_folders}")
        print(f"  - 検出されたグループ: {list(groups.keys())}")
        for name, files in groups.items():
            if len(files) > 1:
                print(f"    複数ファイルグループ '{name}': {len(files)}ファイル")
        
        # まず複数人名ファイルを統合（1ファイルでも統合対象になる）
        groups_after_merge = merge_multiple_names(groups, all_existing_folders)
        
        # 1ファイルでも既存フォルダと同じ名前なら処理対象に含める
        processed_groups = {}
        single_file_groups = {}
        
        for name, files in groups_after_merge.items():
            if len(files) > 1:
                # 複数ファイルは常に処理対象
                processed_groups[name] = files
            elif len(files) == 1:
                # 1ファイルでも既存フォルダと同じ名前なら処理対象に含める
                if name in all_existing_folders:
                    processed_groups[name] = files
                    print(f"1ファイルグループ '{name}' を既存フォルダに移動対象として追加")
                else:
                    single_file_groups[name] = files
        
        # 結果を保存
        global current_analysis
        current_analysis = {
            'directory_paths': directory_paths,
            'groups': processed_groups,
            'single_file_groups': single_file_groups,
            'total_files': len(all_image_files),
            'existing_folders': list(all_existing_folders),
            'directory_results': directory_results,
            'mode': mode  # 実行モードを保存
        }
        
        return jsonify({
            'success': True,
            'total_files': len(all_image_files),
            'total_groups': len(processed_groups),
            'groups': {name: len(files) for name, files in processed_groups.items()},
            'skipped_single_files': len(single_file_groups),
            'single_file_examples': list(single_file_groups.keys())[:10],
            'existing_folders': list(all_existing_folders),
            'directory_count': len(directory_paths),
            'directory_summary': [
                {
                    'path': path,
                    'file_count': result['file_count']
                } for path, result in directory_results.items()
            ]
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
    """複数ディレクトリのファイルを実際に整理"""
    try:
        if not current_analysis:
            return jsonify({'error': '先にディレクトリを解析してください'}), 400
        
        directory_paths = current_analysis['directory_paths']
        groups = current_analysis['groups']
        mode = current_analysis.get('mode', 'normal') # 保存したモードを取得
        
        results = {
            'moved_files': 0,
            'created_folders': 0,
            'errors': []
        }
        
        # 各グループについて処理
        for folder_name, files in groups.items():
            # ファイルの元ディレクトリごとにグループ化
            files_by_directory = {}
            for file_info in files:
                source_dir = file_info['source_directory']
                if source_dir not in files_by_directory:
                    files_by_directory[source_dir] = []
                files_by_directory[source_dir].append(file_info)
            
            # 各ディレクトリでフォルダを作成し、ファイルを移動
            for source_directory, dir_files in files_by_directory.items():
                
                destination_folder_path = None
                if mode == 'normal':
                    # 通常モード: サブフォルダを含めて既存の同名フォルダを探す
                    existing_path = find_existing_folder_recursive(source_directory, folder_name)
                    if existing_path:
                        destination_folder_path = existing_path
                        print(f"通常モード: 既存フォルダ '{existing_path}' に移動します")
                    else:
                        # 見つからなければ、指定ディレクトリ直下に作成
                        destination_folder_path = os.path.join(source_directory, folder_name)
                        print(f"通常モード: 新規フォルダ '{destination_folder_path}' を作成します")
                else: # parent mode
                    # 親フォルダモード: 従来通り source_directory 直下に作成
                    destination_folder_path = os.path.join(source_directory, folder_name)

                # フォルダを作成（既存の場合はスキップ）
                folder_existed = os.path.exists(destination_folder_path)
                
                try:
                    os.makedirs(destination_folder_path, exist_ok=True)
                    if not folder_existed:
                        results['created_folders'] += 1
                        print(f"フォルダを作成: {destination_folder_path}")
                except Exception as e:
                    error_msg = f"フォルダ作成エラー '{folder_name}' in {source_directory}: {str(e)}"
                    results['errors'].append(error_msg)
                    print(error_msg)
                    continue
                
                # ファイルを移動
                for file_info in dir_files:
                    try:
                        source_path = file_info['path']
                        
                        # 移動元ファイルが存在するかチェック
                        if not os.path.exists(source_path):
                            error_msg = f"移動元ファイルが見つかりません: {file_info['name']} in {source_directory}"
                            results['errors'].append(error_msg)
                            print(error_msg)
                            continue
                        
                        # 移動先のファイル名を決定（重複回避）
                        destination_path = get_unique_filename(destination_folder_path, file_info['name'])
                        
                        # ファイルを移動
                        try:
                            shutil.move(source_path, destination_path)
                            results['moved_files'] += 1
                            
                            # リネームされた場合のみログに記録（情報として）
                            original_name = file_info['name']
                            new_name = os.path.basename(destination_path)
                            if original_name != new_name:
                                # エラーではなく情報として記録
                                print(f"リネーム: {original_name} → {new_name} in {destination_folder_path}")
                            else:
                                print(f"移動: {original_name} → {destination_folder_path}")
                            
                        except PermissionError as e:
                            error_msg = f"ファイル移動権限エラー '{file_info['name']}': {str(e)}"
                            results['errors'].append(error_msg)
                            print(error_msg)
                        except OSError as e:
                            error_msg = f"ファイル移動OSエラー '{file_info['name']}': {str(e)}"
                            results['errors'].append(error_msg)
                            print(error_msg)
                        except Exception as e:
                            error_msg = f"ファイル移動エラー '{file_info['name']}': {str(e)}"
                            results['errors'].append(error_msg)
                            print(error_msg)
                    
                    except Exception as e:
                        error_msg = f"ファイル処理エラー '{file_info['name']}': {str(e)}"
                        results['errors'].append(error_msg)
                        print(error_msg)
        
        # デバッグ情報
        debug_info = {
            'total_groups': len(groups),
            'total_files_in_groups': sum(len(files) for files in groups.values()),
            'directories_processed': len(directory_paths)
        }
        
        print(f"整理完了:")
        print(f"  - 処理ディレクトリ数: {debug_info['directories_processed']}")
        print(f"  - 移動ファイル数: {results['moved_files']}")
        print(f"  - 作成フォルダ数: {results['created_folders']}")
        print(f"  - エラー数: {len(results['errors'])}")
        
        return jsonify({
            'success': True,
            'results': results,
            'debug': debug_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def find_existing_folder_recursive(root_path, folder_name_to_find):
    """指定されたパス内で、特定の名前のフォルダを再帰的に検索する"""
    print(f"'{root_path}'内で'{folder_name_to_find}'を再帰的に検索中...")
    for root, dirs, files in os.walk(root_path):
        if folder_name_to_find in dirs:
            found_path = os.path.join(root, folder_name_to_find)
            print(f"  -> 発見: {found_path}")
            return found_path
    print(f"  -> 見つかりませんでした")
    return None

def get_unique_filename(folder_path, filename):
    """重複しないファイル名を生成（(1)から順番に連続した番号）"""
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
    
    # フォルダ内の既存ファイルから使用済み番号を収集
    used_numbers = set()
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
                            # 番号なしの同名ファイル（これは (1) として扱う）
                            used_numbers.add(1)
                        else:
                            # 番号付きファイルから番号を取得
                            numbers = re.findall(r'\((\d+)\)', remaining)
                            if numbers:
                                # 最後の番号のみを使用済みとして記録
                                last_number = int(numbers[-1])
                                used_numbers.add(last_number)
        except Exception:
            # エラーが発生した場合は安全に処理
            pass
    
    # (1)から順番に空いている番号を見つける
    counter = 1
    while counter in used_numbers and counter <= 1000:
        counter += 1
    
    # 無限ループ防止
    if counter > 1000:
        import time
        timestamp = int(time.time())
        new_filename = f"{clean_base_name}_{timestamp}{extension}"
        new_destination_path = os.path.join(folder_path, new_filename)
    else:
        new_filename = f"{clean_base_name} ({counter}){extension}"
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

@app.route('/api/scan_subfolders', methods=['POST'])
def scan_subfolders():
    """親フォルダからサブフォルダを検出"""
    try:
        data = request.get_json()
        parent_folder_path = data.get('parent_folder_path', '').strip()
        
        if not parent_folder_path:
            return jsonify({'error': '親フォルダのパスが入力されていません'}), 400
        
        if not os.path.exists(parent_folder_path):
            return jsonify({'error': '指定された親フォルダが存在しません'}), 400
        
        if not os.path.isdir(parent_folder_path):
            return jsonify({'error': '指定されたパスはフォルダではありません'}), 400
        
        # サブフォルダを検出
        subfolders = []
        try:
            for item in os.listdir(parent_folder_path):
                item_path = os.path.join(parent_folder_path, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    # 画像ファイル数を数える
                    image_count = count_images_in_folder(item_path)
                    
                    subfolders.append({
                        'name': item,
                        'path': item_path,
                        'image_count': image_count,
                        'selected': True  # デフォルトで選択状態
                    })
        except PermissionError:
            return jsonify({'error': '親フォルダへのアクセス権限がありません'}), 403
        
        # サブフォルダを名前順でソート
        subfolders.sort(key=lambda x: x['name'])
        
        # 結果をログ出力
        print(f"親フォルダ検出結果:")
        print(f"  - 親フォルダ: {parent_folder_path}")
        print(f"  - 検出されたサブフォルダ: {len(subfolders)}")
        for folder in subfolders:
            print(f"    {folder['name']}: {folder['image_count']}画像")
        
        return jsonify({
            'success': True,
            'parent_folder': parent_folder_path,
            'subfolders': subfolders,
            'total_subfolders': len(subfolders)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def count_images_in_folder(folder_path):
    """フォルダ内の画像ファイル数を数える"""
    image_extensions = {
        '.jpg', '.jpeg', '.jfif', '.jpe',  # JPEG系
        '.png', '.gif', '.bmp', '.tiff', '.tif',  # 一般的な形式
        '.webp', '.avif', '.heic', '.heif',  # 新しい形式
        '.raw', '.cr2', '.nef', '.arw', '.dng',  # RAW形式
        '.svg', '.ico'  # その他
    }
    
    count = 0
    try:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if Path(file).suffix.lower() in image_extensions:
                    count += 1
    except Exception:
        pass  # エラーが発生した場合は0を返す
    
    return count

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
        .btn-warning { background: #ffca28; color: #333; }
        .btn-info { background: #17a2b8; color: white; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        
        /* フォルダ選択ボタンの特別なスタイル */
        .file-input-wrapper .btn-warning {
            background: #ffca28;
            color: #333;
            transition: all 0.3s ease;
        }
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
            z-index: 1;
        }
        .file-input-wrapper .btn {
            position: relative;
            z-index: 2;
            pointer-events: none;
        }
        .file-input-wrapper:hover .btn {
            opacity: 0.9;
            transform: translateY(-1px);
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
        
        /* 保存されたパス一覧のスタイル */
        .saved-paths-section {
            background: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 15px;
        }
        .saved-paths-section h3 {
            margin-bottom: 15px;
            color: #495057;
            font-size: 1.1em;
        }
        .saved-paths-list {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 10px;
        }
        .saved-path-item {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 8px 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            max-width: 300px;
        }
        .saved-path-item:hover {
            background: #e9ecef;
            border-color: #4facfe;
            transform: translateY(-1px);
        }
        .saved-path-name {
            font-weight: bold;
            color: #495057;
        }
        .saved-path-path {
            color: #6c757d;
            font-size: 0.9em;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            flex: 1;
        }
        .saved-path-delete {
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            font-size: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0.7;
            transition: opacity 0.2s ease;
        }
        .saved-path-delete:hover {
            opacity: 1;
        }
        
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
        
        /* モード選択のスタイル */
        .mode-selection {
            background: #f8f9fa;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 20px;
        }
        .mode-selection h3 {
            margin-bottom: 15px;
            color: #495057;
            font-size: 1.2em;
        }
        .mode-buttons {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .mode-btn {
            background: white;
            border: 2px solid #dee2e6;
            color: #495057;
            font-weight: bold;
            transition: all 0.3s ease;
        }
        .mode-btn:hover {
            border-color: #4facfe;
            background: #e9f4ff;
        }
        .mode-btn.active {
            background: #4facfe;
            border-color: #4facfe;
            color: white;
        }
        .mode-description {
            position: relative;
            min-height: 60px;
        }
        .mode-desc {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            opacity: 0;
            transition: opacity 0.3s ease;
            color: #666;
            line-height: 1.6;
        }
        .mode-desc.active {
            opacity: 1;
        }
        
        /* 親フォルダモード用スタイル */
        .parent-folder-section {
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            padding: 20px;
            background: white;
            margin-bottom: 20px;
        }
        .parent-folder-section h3 {
            margin-bottom: 15px;
            color: #495057;
            font-size: 1.1em;
        }
        .subfolder-section {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .subfolder-section h4 {
            margin-bottom: 15px;
            color: #495057;
            font-size: 1.0em;
        }
        .subfolder-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .subfolder-item {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 12px;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        .subfolder-item:hover {
            border-color: #4facfe;
            background: #f0f8ff;
        }
        .subfolder-item.selected {
            border-color: #28a745;
            background: #d4edda;
        }
        .subfolder-checkbox {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        .subfolder-info {
            flex: 1;
        }
        .subfolder-name {
            font-weight: bold;
            color: #495057;
            margin-bottom: 2px;
        }
        .subfolder-details {
            color: #6c757d;
            font-size: 0.9em;
        }
        .subfolder-controls {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
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
                
                <!-- モード選択 -->
                <div class="mode-selection" style="margin-bottom: 20px;">
                    <h3>🔧 整理モード選択</h3>
                    <div class="mode-buttons">
                        <button type="button" class="btn mode-btn active" id="normalModeBtn" onclick="switchMode('normal')">
                            📂 通常モード
                        </button>
                        <button type="button" class="btn mode-btn" id="parentModeBtn" onclick="switchMode('parent')">
                            🗂️ 親フォルダモード
                        </button>
                    </div>
                    <div class="mode-description">
                        <div id="normalModeDesc" class="mode-desc active">
                            複数のフォルダを直接指定して整理します。各フォルダのパスを個別に入力してください。
                        </div>
                        <div id="parentModeDesc" class="mode-desc">
                            親フォルダを指定すると、その中のサブフォルダを自動検出して選択的に整理できます。
                        </div>
                    </div>
                </div>
                
                <!-- 親フォルダモード用UI -->
                <div id="parentFolderSection" class="parent-folder-section" style="display: none;">
                    <h3>🗂️ 親フォルダを指定</h3>
                    <div class="form-group">
                        <label for="parentFolderPath">親フォルダのパス:</label>
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <input type="text" id="parentFolderPath" placeholder="例: C:/Users/YourName/Pictures/動物フォルダ" style="flex: 1;">
                            <button type="button" class="btn btn-warning" onclick="selectParentFolder()">📁</button>
                            <button type="button" class="btn btn-info" onclick="saveParentPath()">💾</button>
                            <button type="button" class="btn btn-primary" onclick="scanSubfolders()">🔍 サブフォルダ検出</button>
                        </div>
                        <small style="color: #666; margin-top: 5px; display: block;">
                            親フォルダを指定してサブフォルダを自動検出します
                        </small>
                    </div>
                    
                    <!-- サブフォルダ一覧 -->
                    <div id="subfolderSection" class="subfolder-section" style="display: none;">
                        <h4>📋 検出されたサブフォルダ</h4>
                        <div id="subfolderList" class="subfolder-list"></div>
                        <div class="subfolder-controls" style="margin-top: 15px;">
                            <button type="button" class="btn btn-success" onclick="selectAllSubfolders()">✅ 全選択</button>
                            <button type="button" class="btn btn-secondary" onclick="deselectAllSubfolders()">❌ 全解除</button>
                            <button type="button" class="btn btn-primary" onclick="analyzeSelectedSubfolders()">🔍 選択したフォルダを解析</button>
                        </div>
                    </div>
                </div>
                
                <!-- 通常モード用UI -->
                <div id="normalFolderSection" class="normal-folder-section">
                    <p style="margin-bottom: 20px; color: #666;">
                        複数のフォルダを同時に整理できます。パスを追加/削除してから「🔍 解析開始」をクリックしてください。
                    </p>
                    
                    <!-- 保存されたパス一覧 -->
                    <div id="savedPathsSection" class="saved-paths-section" style="margin-bottom: 20px; display: none;">
                        <h3>💾 保存されたパス</h3>
                        <div id="savedPathsList" class="saved-paths-list"></div>
                        <button type="button" class="btn btn-secondary" onclick="clearAllSavedPaths()" style="margin-top: 10px;">🗑️ 全削除</button>
                    </div>
                    
                    <div id="pathInputs">
                        <div class="path-input-group" data-index="0">
                            <div class="form-group">
                                <label for="directoryPath0">フォルダ 1 のパス:</label>
                                <div style="display: flex; gap: 10px; align-items: center;">
                                    <input type="text" id="directoryPath0" class="directory-path" placeholder="例: C:/Users/YourName/Pictures" style="flex: 1;">
                                    <button type="button" class="btn btn-warning folder-select-btn" data-target="directoryPath0">📁</button>
                                    <button type="button" class="btn btn-info" onclick="saveCurrentPath(0)">💾</button>
                                    <button type="button" class="btn btn-secondary remove-path-btn" onclick="removePath(0)" style="display: none;">❌</button>
                                </div>
                                <small style="color: #666; margin-top: 5px; display: block;">
                                    💡 「📁」でフォルダ選択、「💾」でパス保存、保存済みパスをクリックで呼び出し
                                </small>
                            </div>
                            <div class="selected-folder" id="selectedFolder0" style="display: none;">
                                <strong>選択されたフォルダ:</strong> <span class="selected-folder-path"></span>
                                <br><small style="color: #666;">フォルダ選択後、完全なパスを入力してください</small>
                            </div>
                        </div>
                    </div>
                    
                    <div class="btn-group" style="margin-top: 15px;">
                        <button class="btn btn-success" onclick="addPath()">➕ フォルダを追加</button>
                        <button class="btn btn-primary" onclick="analyzeDirectories()">🔍 解析開始</button>
                        <button class="btn btn-info" onclick="showUsageModal()">❓ 使い方</button>
                    </div>
                </div>
                
                <!-- 隠しファイル入力（フォルダ選択用） -->
                <input type="file" id="folderInput" style="display: none;" webkitdirectory multiple accept="image/*">
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
                    
                    <h4>💾 パス記憶機能</h4>
                    <p><strong>パス保存：</strong> 「💾」ボタンをクリックして頻繁に使うパスを保存</p>
                    <p><strong>パス呼び出し：</strong> 保存済みパスをクリックして簡単に入力</p>
                    <p><strong>パス管理：</strong> 保存済みパスの「×」ボタンで個別削除、「🗑️ 全削除」で一括削除</p>
                    <p><strong>自動命名：</strong> パス保存時にフォルダ名を自動提案、カスタム名も設定可能</p>
                    
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
                
                <div class="step">
                    <h3>🗂️ 親フォルダモードの使い方</h3>
                    <p><strong>🎯 こんな時に便利：</strong> 大きな親フォルダの中に複数のサブフォルダがあり、それぞれを個別に整理したい場合</p>
                    
                    <h4>📋 使用例</h4>
                    <p><strong>フォルダ構造例：</strong></p>
                    <p><code>📁 動物フォルダ/</code></p>
                    <p><code>  ├── 📁 犬/</code></p>
                    <p><code>  ├── 📁 猫/</code></p>
                    <p><code>  └── 📁 ペンギン/</code></p>
                    
                    <h4>⚙️ 操作手順</h4>
                    <p><strong>1.</strong> 「🗂️ 親フォルダモード」を選択</p>
                    <p><strong>2.</strong> 親フォルダ（例：動物フォルダ）のパスを入力</p>
                    <p><strong>3.</strong> 「🔍 サブフォルダ検出」でサブフォルダを自動検出</p>
                    <p><strong>4.</strong> 整理したいサブフォルダを選択（チェックボックス）</p>
                    <p><strong>5.</strong> 「🔍 選択したフォルダを解析」で一括解析</p>
                    
                    <h4>✨ 便利機能</h4>
                    <p><strong>• 画像数表示：</strong> 各サブフォルダの画像ファイル数を表示</p>
                    <p><strong>• 選択的処理：</strong> 必要なサブフォルダのみを選択して処理</p>
                    <p><strong>• 一括操作：</strong> 「✅ 全選択」「❌ 全解除」で効率的な選択</p>
                    <p><strong>• パス保存：</strong> 親フォルダパスも保存・呼び出し可能</p>
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

        // グローバル変数宣言（初期化エラー回避）
        var currentMode = 'normal'; // 'normal' または 'parent'
        var detectedSubfolders = []; // 検出されたサブフォルダ一覧

        async function analyzeDirectories() {
            const directoryPaths = Array.from(document.querySelectorAll('.directory-path'))
                .map(input => input.value.trim())
                .filter(path => path.length > 0);
            
            if (directoryPaths.length === 0) {
                alert('少なくとも1つのディレクトリパスを入力してください');
                return;
            }

            log(`${directoryPaths.length}個のディレクトリを解析中...`, 'info');
            
            // 入力されたディレクトリをログに表示
            directoryPaths.forEach((path, index) => {
                log(`フォルダ ${index + 1}: ${path}`, 'info');
            });

            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        directory_paths: directoryPaths,
                        mode: currentMode
                    })
                });

                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('totalFiles').textContent = data.total_files;
                    document.getElementById('totalGroups').textContent = data.total_groups;
                    document.getElementById('skippedFiles').textContent = data.skipped_single_files || 0;
                    document.getElementById('statsSection').classList.remove('hidden');
                    
                    // 複数フォルダの詳細情報をログに表示
                    log(`解析完了: ${data.directory_count}フォルダ、${data.total_files}ファイル、${data.total_groups}グループ、${data.skipped_single_files || 0}ファイルスキップ`, 'success');
                    
                    // 各ディレクトリの詳細
                    if (data.directory_summary) {
                        data.directory_summary.forEach((dir, index) => {
                            log(`  - フォルダ ${index + 1}: ${dir.file_count}ファイル`, 'info');
                        });
                    }
                    
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

        // フォルダ選択機能（複数対応）
        let currentTargetInput = null;
        
        // フォルダ選択ボタンのイベントリスナー
        document.addEventListener('click', function(event) {
            if (event.target.classList.contains('folder-select-btn')) {
                currentTargetInput = event.target.getAttribute('data-target');
                document.getElementById('folderInput').click();
            }
        });
        
        // パス追加機能
        function addPath() {
            const pathInputs = document.getElementById('pathInputs');
            const currentCount = pathInputs.children.length;
            const newIndex = currentCount;
            
            const newPathGroup = document.createElement('div');
            newPathGroup.className = 'path-input-group';
            newPathGroup.setAttribute('data-index', newIndex);
            newPathGroup.innerHTML = `
                <div class="form-group">
                    <label for="directoryPath${newIndex}">フォルダ ${newIndex + 1} のパス:</label>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <input type="text" id="directoryPath${newIndex}" class="directory-path" placeholder="例: C:/Users/YourName/Pictures" style="flex: 1;">
                        <button type="button" class="btn btn-warning folder-select-btn" data-target="directoryPath${newIndex}">📁</button>
                        <button type="button" class="btn btn-info" onclick="saveCurrentPath(${newIndex})">💾</button>
                        <button type="button" class="btn btn-secondary remove-path-btn" onclick="removePath(${newIndex})">❌</button>
                    </div>
                    <small style="color: #666; margin-top: 5px; display: block;">
                        💡 「📁」でフォルダ選択、「💾」でパス保存、保存済みパスをクリックで呼び出し
                    </small>
                </div>
                <div class="selected-folder" id="selectedFolder${newIndex}" style="display: none;">
                    <strong>選択されたフォルダ:</strong> <span class="selected-folder-path"></span>
                    <br><small style="color: #666;">フォルダ選択後、完全なパスを入力してください</small>
                </div>
            `;
            
            pathInputs.appendChild(newPathGroup);
            updateRemoveButtons();
            log(`フォルダ ${newIndex + 1} の入力欄を追加しました`, 'info');
        }
        
        // パス削除機能
        function removePath(index) {
            const pathGroup = document.querySelector(`[data-index="${index}"]`);
            if (pathGroup) {
                pathGroup.remove();
                updateRemoveButtons();
                log(`フォルダ ${index + 1} の入力欄を削除しました`, 'info');
            }
        }
        
        // 削除ボタンの表示/非表示を更新
        function updateRemoveButtons() {
            const pathGroups = document.querySelectorAll('.path-input-group');
            pathGroups.forEach((group, index) => {
                const removeBtn = group.querySelector('.remove-path-btn');
                if (pathGroups.length > 1) {
                    removeBtn.style.display = 'inline-block';
                } else {
                    removeBtn.style.display = 'none';
                }
            });
        }
        
        document.getElementById('folderInput').addEventListener('change', async function(event) {
            // アップロード確認ダイアログを防ぐ
            event.preventDefault();
            event.stopPropagation();
            
            const files = event.target.files;
            
            // 即座にファイル入力をリセットしてアップロードを防ぐ
            setTimeout(() => {
                document.getElementById('folderInput').value = '';
            }, 0);
            
            if (files.length > 0 && currentTargetInput) {
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
                        let targetInput, selectedFolderDiv, selectedFolderSpan;
                        
                        if (currentTargetInput === 'parentFolderPath') {
                            // 親フォルダモードの場合
                            targetInput = document.getElementById('parentFolderPath');
                            selectedFolderDiv = null; // 親フォルダモードでは選択フォルダ表示なし
                        } else {
                            // 通常モードの場合
                            targetInput = document.getElementById(currentTargetInput);
                            const targetIndex = currentTargetInput.replace('directoryPath', '');
                            selectedFolderDiv = document.getElementById('selectedFolder' + targetIndex);
                            selectedFolderSpan = selectedFolderDiv ? selectedFolderDiv.querySelector('.selected-folder-path') : null;
                        }
                        
                        if (data.requires_manual_input) {
                            // 手動入力が必要な場合
                            const folderName = data.folder_name;
                            const fileCount = data.file_count;
                            
                            // 選択されたフォルダ情報を表示（通常モードのみ）
                            if (selectedFolderDiv && selectedFolderSpan) {
                                const displayText = `${folderName} (${fileCount}ファイル)`;
                                selectedFolderSpan.textContent = displayText;
                                selectedFolderDiv.style.display = 'block';
                            }
                            
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
                                targetInput.value = userPath.trim();
                                log('パスが設定されました。解析を開始してください。', 'success');
                            } else {
                                log('パスが入力されませんでした。手動でパス入力欄に入力してください。', 'info');
                                // パス入力欄にフォーカス
                                targetInput.focus();
                            }
                        } else {
                            // 完全なパスが取得できた場合（稀なケース）
                            targetInput.value = data.folder_path;
                            
                            if (selectedFolderDiv && selectedFolderSpan) {
                                const displayText = `${data.folder_path} (${data.file_count}ファイル)`;
                                selectedFolderSpan.textContent = displayText;
                                selectedFolderDiv.style.display = 'block';
                            }
                            
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
                    
                    if (currentTargetInput) {
                        const targetInput = document.getElementById(currentTargetInput);
                        
                        if (currentTargetInput === 'parentFolderPath') {
                            // 親フォルダモードの場合
                            targetInput.value = fallbackPath;
                        } else {
                            // 通常モードの場合
                            const targetIndex = currentTargetInput.replace('directoryPath', '');
                            const selectedFolderDiv = document.getElementById('selectedFolder' + targetIndex);
                            const selectedFolderSpan = selectedFolderDiv ? selectedFolderDiv.querySelector('.selected-folder-path') : null;
                            
                            targetInput.value = fallbackPath;
                            if (selectedFolderSpan) {
                                selectedFolderSpan.textContent = fallbackPath;
                                selectedFolderDiv.style.display = 'block';
                            }
                        }
                    }
                    
                    log('基本情報のみ設定されました。手動でパスを修正してください。', 'info');
                }
            }
            
            // 処理完了後、必ずファイル入力をリセットしてアップロードを防ぐ
            setTimeout(() => {
                document.getElementById('folderInput').value = '';
            }, 500);
        });

        // アップロード防止の設定
        function preventFileUpload() {
            // ページ全体でファイルドロップを無効化
            document.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.stopPropagation();
            });
            
            document.addEventListener('drop', function(e) {
                e.preventDefault();
                e.stopPropagation();
            });
            
            // フォーム送信を無効化
            document.addEventListener('submit', function(e) {
                e.preventDefault();
                e.stopPropagation();
                return false;
            });
            
            // beforeunload イベントでアップロードを防ぐ
            window.addEventListener('beforeunload', function(e) {
                // ファイル入力をクリア
                const fileInputs = document.querySelectorAll('input[type="file"]');
                fileInputs.forEach(input => input.value = '');
            });
            
            // ファイル入力の変更を監視してアップロードを防ぐ
            document.addEventListener('change', function(e) {
                if (e.target.type === 'file' && e.target.id === 'folderInput') {
                    // フォルダ選択以外のファイル操作を防ぐ
                    setTimeout(() => {
                        e.target.value = '';
                    }, 100);
                }
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
        updateRemoveButtons(); // 削除ボタンの初期状態を設定
        loadSavedPaths(); // 保存されたパスを読み込み
        initializeMode(); // モードを初期化
        log('写真整理ツール Webアプリ版が起動しました（複数フォルダ対応）', 'info');
        
        // === モード管理機能 ===
        
        // モード初期化
        function initializeMode() {
            switchMode('normal');
        }
        
        // モード切り替え
        function switchMode(mode) {
            console.log('switchMode called with mode:', mode); // デバッグ用
            currentMode = mode;
            
            // ボタンの状態更新
            document.getElementById('normalModeBtn').classList.toggle('active', mode === 'normal');
            document.getElementById('parentModeBtn').classList.toggle('active', mode === 'parent');
            
            // 説明文の状態更新
            document.getElementById('normalModeDesc').classList.toggle('active', mode === 'normal');
            document.getElementById('parentModeDesc').classList.toggle('active', mode === 'parent');
            
            // UI表示切り替え
            document.getElementById('normalFolderSection').style.display = mode === 'normal' ? 'block' : 'none';
            document.getElementById('parentFolderSection').style.display = mode === 'parent' ? 'block' : 'none';
            
            // 結果表示をリセット
            resetAnalysisResults();
            
            log(`${mode === 'normal' ? '通常' : '親フォルダ'}モードに切り替えました`, 'info');
        }
        
        // 解析結果をリセット
        function resetAnalysisResults() {
            document.getElementById('statsSection').classList.add('hidden');
            document.getElementById('previewSection').classList.add('hidden');
        }
        
        // === 親フォルダモード機能 ===
        
        // 親フォルダ選択
        function selectParentFolder() {
            currentTargetInput = 'parentFolderPath';
            document.getElementById('folderInput').click();
        }
        
        // 親フォルダパス保存
        function saveParentPath() {
            const pathInput = document.getElementById('parentFolderPath');
            const path = pathInput.value.trim();
            
            if (!path) {
                alert('親フォルダのパスが入力されていません');
                return;
            }
            
            // パス名の入力を促す
            const pathName = prompt(`親フォルダパスに名前を付けてください:\n\n${path}`, getDefaultPathName(path) + '（親フォルダ）');
            
            if (pathName === null) return;
            if (!pathName.trim()) {
                alert('名前を入力してください');
                return;
            }
            
            // 保存済みパスを取得
            let savedPaths = [];
            try {
                savedPaths = JSON.parse(localStorage.getItem('photoOrganizerPaths') || '[]');
            } catch (error) {
                savedPaths = [];
            }
            
            // 同じパスが既に存在するかチェック
            const existingIndex = savedPaths.findIndex(p => p.path === path);
            if (existingIndex !== -1) {
                if (confirm(`このパスは既に「${savedPaths[existingIndex].name}」として保存されています。\n上書きしますか？`)) {
                    savedPaths[existingIndex].name = pathName.trim();
                } else {
                    return;
                }
            } else {
                savedPaths.push({
                    name: pathName.trim(),
                    path: path,
                    savedAt: new Date().toISOString(),
                    type: 'parent' // 親フォルダとしてマーク
                });
            }
            
            try {
                localStorage.setItem('photoOrganizerPaths', JSON.stringify(savedPaths));
                displaySavedPaths(savedPaths);
                log(`親フォルダパスを保存しました: ${pathName.trim()}`, 'success');
            } catch (error) {
                alert('パスの保存に失敗しました');
            }
        }
        
        // サブフォルダ検出
        async function scanSubfolders() {
            const parentPath = document.getElementById('parentFolderPath').value.trim();
            
            if (!parentPath) {
                alert('親フォルダのパスを入力してください');
                return;
            }
            
            log('サブフォルダを検出中...', 'info');
            
            try {
                const response = await fetch('/api/scan_subfolders', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ parent_folder_path: parentPath })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    detectedSubfolders = data.subfolders;
                    displaySubfolders(detectedSubfolders);
                    
                    log(`サブフォルダ検出完了: ${data.total_subfolders}個のフォルダを発見`, 'success');
                    data.subfolders.forEach(folder => {
                        log(`  - ${folder.name}: ${folder.image_count}画像`, 'info');
                    });
                } else {
                    log(`エラー: ${data.error}`, 'error');
                }
            } catch (error) {
                log(`エラー: ${error.message}`, 'error');
            }
        }
        
        // サブフォルダ一覧表示
        function displaySubfolders(subfolders) {
            const subfolderSection = document.getElementById('subfolderSection');
            const subfolderList = document.getElementById('subfolderList');
            
            if (subfolders.length === 0) {
                subfolderSection.style.display = 'none';
                return;
            }
            
            subfolderSection.style.display = 'block';
            subfolderList.innerHTML = '';
            
            subfolders.forEach((folder, index) => {
                const item = document.createElement('div');
                item.className = `subfolder-item ${folder.selected ? 'selected' : ''}`;
                item.innerHTML = `
                    <input type="checkbox" class="subfolder-checkbox" 
                           ${folder.selected ? 'checked' : ''} 
                           onchange="toggleSubfolder(${index})">
                    <div class="subfolder-info">
                        <div class="subfolder-name">${folder.name}</div>
                        <div class="subfolder-details">${folder.image_count} 画像ファイル</div>
                    </div>
                `;
                
                // クリックで選択状態を切り替え
                item.addEventListener('click', function(e) {
                    if (e.target.type !== 'checkbox') {
                        toggleSubfolder(index);
                    }
                });
                
                subfolderList.appendChild(item);
            });
        }
        
        // サブフォルダの選択状態を切り替え
        function toggleSubfolder(index) {
            if (index >= 0 && index < detectedSubfolders.length) {
                detectedSubfolders[index].selected = !detectedSubfolders[index].selected;
                displaySubfolders(detectedSubfolders);
                
                const selectedCount = detectedSubfolders.filter(f => f.selected).length;
                log(`フォルダ選択更新: ${selectedCount}/${detectedSubfolders.length}個選択中`, 'info');
            }
        }
        
        // 全サブフォルダ選択
        function selectAllSubfolders() {
            detectedSubfolders.forEach(folder => folder.selected = true);
            displaySubfolders(detectedSubfolders);
            log(`全サブフォルダを選択しました: ${detectedSubfolders.length}個`, 'info');
        }
        
        // 全サブフォルダ選択解除
        function deselectAllSubfolders() {
            detectedSubfolders.forEach(folder => folder.selected = false);
            displaySubfolders(detectedSubfolders);
            log('全サブフォルダの選択を解除しました', 'info');
        }
        
        // 選択されたサブフォルダを解析
        async function analyzeSelectedSubfolders() {
            const selectedFolders = detectedSubfolders.filter(f => f.selected);
            
            if (selectedFolders.length === 0) {
                alert('解析するサブフォルダを選択してください');
                return;
            }
            
            // 選択されたサブフォルダのパスを抽出
            const directoryPaths = selectedFolders.map(f => f.path);
            
            log(`${selectedFolders.length}個の選択されたサブフォルダを解析中...`, 'info');
            selectedFolders.forEach((folder, index) => {
                log(`  ${index + 1}. ${folder.name}`, 'info');
            });
            
            try {
                const response = await fetch('/api/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        directory_paths: directoryPaths,
                        mode: currentMode
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('totalFiles').textContent = data.total_files;
                    document.getElementById('totalGroups').textContent = data.total_groups;
                    document.getElementById('skippedFiles').textContent = data.skipped_single_files || 0;
                    document.getElementById('statsSection').classList.remove('hidden');
                    
                    log(`解析完了: ${selectedFolders.length}サブフォルダ、${data.total_files}ファイル、${data.total_groups}グループ、${data.skipped_single_files || 0}ファイルスキップ`, 'success');
                    
                    if (data.directory_summary) {
                        data.directory_summary.forEach((dir, index) => {
                            const folderName = selectedFolders.find(f => f.path === dir.path)?.name || `フォルダ${index + 1}`;
                            log(`  - ${folderName}: ${dir.file_count}ファイル`, 'info');
                        });
                    }
                    
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
        
        // === パス記憶機能 ===
        
        // 保存されたパスを読み込み
        function loadSavedPaths() {
            try {
                const savedPaths = JSON.parse(localStorage.getItem('photoOrganizerPaths') || '[]');
                displaySavedPaths(savedPaths);
            } catch (error) {
                console.error('保存されたパスの読み込みエラー:', error);
                localStorage.removeItem('photoOrganizerPaths');
            }
        }
        
        // 保存されたパスを表示
        function displaySavedPaths(savedPaths) {
            const savedPathsSection = document.getElementById('savedPathsSection');
            const savedPathsList = document.getElementById('savedPathsList');
            
            if (savedPaths.length === 0) {
                savedPathsSection.style.display = 'none';
                return;
            }
            
            savedPathsSection.style.display = 'block';
            savedPathsList.innerHTML = '';
            
            savedPaths.forEach((pathData, index) => {
                const pathItem = document.createElement('div');
                pathItem.className = 'saved-path-item';
                pathItem.innerHTML = `
                    <div class="saved-path-name">${pathData.name}</div>
                    <div class="saved-path-path" title="${pathData.path}">${pathData.path}</div>
                    <button class="saved-path-delete" onclick="deleteSavedPath(${index})" title="削除">×</button>
                `;
                
                // パス部分をクリックしたときに呼び出し
                pathItem.addEventListener('click', function(e) {
                    if (!e.target.classList.contains('saved-path-delete')) {
                        callSavedPath(pathData.path);
                    }
                });
                
                savedPathsList.appendChild(pathItem);
            });
        }
        
        // 現在のパスを保存
        function saveCurrentPath(inputIndex) {
            const pathInput = document.getElementById(`directoryPath${inputIndex}`);
            const path = pathInput.value.trim();
            
            if (!path) {
                alert('パスが入力されていません');
                return;
            }
            
            // パス名の入力を促す
            const pathName = prompt(`パスに名前を付けてください:\n\n${path}`, getDefaultPathName(path));
            
            if (pathName === null) {
                return; // キャンセル
            }
            
            if (!pathName.trim()) {
                alert('名前を入力してください');
                return;
            }
            
            // 保存済みパスを取得
            let savedPaths = [];
            try {
                savedPaths = JSON.parse(localStorage.getItem('photoOrganizerPaths') || '[]');
            } catch (error) {
                console.error('保存されたパスの読み込みエラー:', error);
                savedPaths = [];
            }
            
            // 同じパスが既に存在するかチェック
            const existingIndex = savedPaths.findIndex(p => p.path === path);
            if (existingIndex !== -1) {
                if (confirm(`このパスは既に「${savedPaths[existingIndex].name}」として保存されています。\n上書きしますか？`)) {
                    savedPaths[existingIndex].name = pathName.trim();
                } else {
                    return;
                }
            } else {
                // 新規追加
                savedPaths.push({
                    name: pathName.trim(),
                    path: path,
                    savedAt: new Date().toISOString()
                });
            }
            
            // localStorage に保存
            try {
                localStorage.setItem('photoOrganizerPaths', JSON.stringify(savedPaths));
                displaySavedPaths(savedPaths);
                log(`パスを保存しました: ${pathName.trim()}`, 'success');
            } catch (error) {
                console.error('パス保存エラー:', error);
                alert('パスの保存に失敗しました。ストレージ容量を確認してください。');
            }
        }
        
        // デフォルトのパス名を生成
        function getDefaultPathName(path) {
            // パスの最後のフォルダ名を取得
            const pathParts = path.replace(/\\/g, '/').split('/');
            const folderName = pathParts[pathParts.length - 1] || pathParts[pathParts.length - 2] || 'フォルダ';
            return folderName;
        }
        
        // 保存されたパスを呼び出し
        function callSavedPath(path) {
            if (currentMode === 'parent') {
                // 親フォルダモードの場合は親フォルダ入力欄に設定
                document.getElementById('parentFolderPath').value = path;
                log(`保存されたパスを親フォルダに設定しました: ${path}`, 'success');
            } else {
                // 通常モードの場合は既存の処理
                const pathInputs = document.querySelectorAll('.directory-path');
                let targetInput = null;
                
                for (let input of pathInputs) {
                    if (!input.value.trim()) {
                        targetInput = input;
                        break;
                    }
                }
                
                // 空の入力欄がない場合は新しく追加
                if (!targetInput) {
                    addPath();
                    // 新しく追加された入力欄を取得
                    const newInputs = document.querySelectorAll('.directory-path');
                    targetInput = newInputs[newInputs.length - 1];
                }
                
                if (targetInput) {
                    targetInput.value = path;
                    targetInput.focus();
                    log(`保存されたパスを呼び出しました: ${path}`, 'success');
                }
            }
        }
        
        // 保存されたパスを削除
        function deleteSavedPath(index) {
            try {
                let savedPaths = JSON.parse(localStorage.getItem('photoOrganizerPaths') || '[]');
                
                if (index < 0 || index >= savedPaths.length) {
                    return;
                }
                
                const pathName = savedPaths[index].name;
                
                if (confirm(`「${pathName}」を削除しますか？`)) {
                    savedPaths.splice(index, 1);
                    localStorage.setItem('photoOrganizerPaths', JSON.stringify(savedPaths));
                    displaySavedPaths(savedPaths);
                    log(`保存されたパスを削除しました: ${pathName}`, 'info');
                }
            } catch (error) {
                console.error('パス削除エラー:', error);
                alert('パスの削除に失敗しました');
            }
        }
        
        // 全ての保存されたパスを削除
        function clearAllSavedPaths() {
            if (confirm('保存されたパスを全て削除しますか？\nこの操作は取り消せません。')) {
                try {
                    localStorage.removeItem('photoOrganizerPaths');
                    displaySavedPaths([]);
                    log('保存されたパスを全て削除しました', 'info');
                } catch (error) {
                    console.error('パス全削除エラー:', error);
                    alert('パスの削除に失敗しました');
                }
            }
        }
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