#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写真整理ツール (Photo Organizer)
同じ名前の写真ファイルを各々のフォルダにまとめます。
複数人名が含まれる場合は、先頭の名前のフォルダに移動します。

使用方法:
1. このスクリプトを整理したい写真フォルダにコピー
2. コマンドプロンプトまたはターミナルで実行: python photo_organizer.py
3. または、引数でフォルダパスを指定: python photo_organizer.py "C:\Photos"

作成者: AI Assistant
バージョン: 2.0
"""

import os
import sys
import shutil
import re
from pathlib import Path
import argparse

def organize_photos(target_dir=None):
    """
    写真ファイルを整理する関数
    
    Args:
        target_dir (str): 整理対象のディレクトリパス。Noneの場合は現在のディレクトリ
    """
    
    # 対象ディレクトリを決定
    if target_dir:
        current_dir = Path(target_dir)
        if not current_dir.exists():
            print(f"エラー: 指定されたディレクトリが存在しません: {target_dir}")
            return False
        if not current_dir.is_dir():
            print(f"エラー: 指定されたパスはディレクトリではありません: {target_dir}")
            return False
    else:
        current_dir = Path('.')
    
    print(f"整理対象ディレクトリ: {current_dir.absolute()}")
    
    # 画像ファイルの拡張子
    image_extensions = {
        '.jpg', '.jpeg', '.jfif', '.jpe',  # JPEG系
        '.png', '.gif', '.bmp', '.tiff', '.tif',  # 一般的な形式
        '.webp', '.avif', '.heic', '.heif',  # 新しい形式
        '.raw', '.cr2', '.nef', '.arw', '.dng',  # RAW形式
        '.svg', '.ico'  # その他
    }
    
    # 既存のフォルダ名を取得（既に作成されたフォルダを確認）
    existing_folders = set()
    for item in current_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name != '__pycache__':
            existing_folders.add(item.name)
    
    print(f"既存のフォルダ数: {len(existing_folders)}")
    if existing_folders:
        print(f"既存フォルダの例: {list(sorted(existing_folders))[:5]}")
    
    # ファイル名のパターンを解析するための辞書
    base_names = {}
    
    # 全ての画像ファイルを取得
    image_files = []
    for file_path in current_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            image_files.append(file_path)
    
    print(f"見つかった画像ファイル数: {len(image_files)}")
    
    if len(image_files) == 0:
        print("整理対象の画像ファイルが見つかりませんでした。")
        return False
    
    # ファイル名を解析してベース名を抽出
    for file_path in image_files:
        file_name = file_path.stem  # 拡張子を除いたファイル名
        
        # 特殊パターンの除去（コピー、photo-1など）
        clean_name = re.sub(r'\s*-\s*コピー$', '', file_name)
        clean_name = re.sub(r'\s*コピー$', '', clean_name)
        clean_name = re.sub(r'photo-\d+\s*\(\d+\)\s*-\s*コピー$', '', clean_name)
        
        # パターン1: "名前 (数字)" の形式
        match = re.match(r'^(.+?)\s*\((\d+)\)$', clean_name)
        if match:
            base_name = match.group(1).strip()
        else:
            # パターン2: 数字が付いていない場合
            base_name = clean_name.strip()
        
        # 複数人名の処理: 既存フォルダ名で始まるかチェック
        target_folder = None
        # 長い名前から順にチェック（より具体的なマッチを優先）
        for folder_name in sorted(existing_folders, key=len, reverse=True):
            if base_name.startswith(folder_name) and len(base_name) > len(folder_name):
                target_folder = folder_name
                print(f"複数人名検出: '{base_name}' → '{target_folder}' フォルダに移動予定")
                break
        
        # 移動先フォルダを決定
        if target_folder:
            final_base_name = target_folder
        else:
            final_base_name = base_name
        
        # ベース名でグループ化
        if final_base_name not in base_names:
            base_names[final_base_name] = []
        base_names[final_base_name].append(file_path)
    
    print(f"グループ化されたベース名数: {len(base_names)}")
    
    # 移動予定の確認
    print("\n=== 移動予定 ===")
    total_files = 0
    groups_to_process = {}
    
    for base_name, files in base_names.items():
        if len(files) > 1:  # 2ファイル以上の場合は常に処理対象
            print(f"'{base_name}' フォルダ: {len(files)}個のファイル")
            total_files += len(files)
            groups_to_process[base_name] = files
        elif len(files) == 1:
            # 1ファイルでも既存フォルダと同じ名前なら処理対象に含める
            if base_name in existing_folders:
                print(f"'{base_name}' フォルダ: {len(files)}個のファイル（既存フォルダに移動）")
                total_files += len(files)
                groups_to_process[base_name] = files
            else:
                print(f"'{base_name}': 1個のファイルのみ（スキップします）")
    
    if len(groups_to_process) == 0:
        print("\n整理対象のファイルグループがありません。")
        print("（2個以上の同名ファイルがある場合のみ整理します）")
        return False
    
    print(f"\n合計 {total_files} 個のファイルを {len(groups_to_process)} 個のフォルダに整理します。")
    
    # 実行確認
    response = input("\n実行しますか？ (y/n): ")
    if response.lower() not in ['y', 'yes', 'はい']:
        print("キャンセルされました。")
        return False
    
    # 各グループについて処理（1ファイルのグループは除外）
    moved_count = 0
    error_count = 0
    
    for base_name, files in groups_to_process.items():
            print(f"\n'{base_name}' グループを処理中...")
            
            # フォルダを作成
            folder_path = current_dir / base_name
            folder_path.mkdir(exist_ok=True)
            
            # ファイルを移動
            for file_path in files:
                destination = folder_path / file_path.name
                try:
                    # 同名ファイルが既に存在する場合の処理
                    if destination.exists():
                        base_stem = destination.stem
                        extension = destination.suffix
                        counter = 1
                        while destination.exists():
                            new_name = f"{base_stem}_copy{counter}{extension}"
                            destination = folder_path / new_name
                            counter += 1
                        print(f"  名前変更: {file_path.name} → {destination.name}")
                    
                    shutil.move(str(file_path), str(destination))
                    print(f"  移動: {file_path.name} → {base_name}/")
                    moved_count += 1
                except Exception as e:
                    print(f"  エラー: {file_path.name} の移動に失敗 - {e}")
                    error_count += 1
    
    print(f"\n=== 整理完了 ===")
    print(f"移動成功: {moved_count} ファイル")
    if error_count > 0:
        print(f"移動失敗: {error_count} ファイル")
    
    return True

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='写真ファイルを名前ごとにフォルダに整理します',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
使用例:
  python photo_organizer.py                    # 現在のディレクトリを整理
  python photo_organizer.py "C:\Photos"        # 指定したディレクトリを整理
  python photo_organizer.py "/home/user/pics"  # Linuxの場合
        """
    )
    
    parser.add_argument(
        'directory',
        nargs='?',
        help='整理対象のディレクトリパス（省略時は現在のディレクトリ）'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Photo Organizer 2.0'
    )
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("写真整理ツール (Photo Organizer) v2.0")
    print("=" * 50)
    
    try:
        success = organize_photos(args.directory)
        if success:
            print("\n整理が完了しました！")
        else:
            print("\n整理を中止しました。")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nユーザーによって中断されました。")
        sys.exit(1)
    except Exception as e:
        print(f"\n予期しないエラーが発生しました: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 