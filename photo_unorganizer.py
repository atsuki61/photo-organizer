#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写真逆整理ツール (Photo Unorganizer)
写真整理ツールで作成されたフォルダから写真ファイルを取り出して、
元の状態（フラットな構造）に戻します。

機能:
- フォルダ内の画像ファイルを親ディレクトリに移動
- 重複ファイル名の自動処理
- 空になったフォルダの削除オプション
- 多様な画像形式に対応
- 安全な実行前プレビュー

使用方法:
1. python photo_unorganizer.py                    # 現在のディレクトリを処理
2. python photo_unorganizer.py "C:\Photos"        # 指定したディレクトリを処理
3. python photo_unorganizer.py --help             # ヘルプを表示

作成者: AI Assistant
バージョン: 1.0
"""

import os
import sys
import shutil
import re
from pathlib import Path
import argparse

def get_unique_filename(target_dir, filename):
    """重複しないファイル名を生成"""
    destination_path = Path(target_dir) / filename
    
    # ファイルが存在しない場合はそのまま返す
    if not destination_path.exists():
        return destination_path
    
    # ファイル名と拡張子を分離
    base_name, extension = destination_path.stem, destination_path.suffix
    
    # 既存の番号パターンを検出して除去
    clean_base_name = re.sub(r'\s*\(\d+\)(?:\s*\(\d+\))*\s*$', '', base_name).strip()
    
    # フォルダ内の既存ファイルから最大番号を見つける
    max_number = 0
    if Path(target_dir).exists():
        try:
            for existing_file in Path(target_dir).iterdir():
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
    new_destination_path = Path(target_dir) / new_filename
    
    # 念のため、生成したファイル名が存在しないことを確認
    while new_destination_path.exists() and counter <= 1000:
        counter += 1
        new_filename = f"{clean_base_name} ({counter}){extension}"
        new_destination_path = Path(target_dir) / new_filename
    
    # 無限ループ防止
    if counter > 1000:
        import time
        timestamp = int(time.time())
        new_filename = f"{clean_base_name}_{timestamp}{extension}"
        new_destination_path = Path(target_dir) / new_filename
    
    return new_destination_path

def unorganize_photos(target_dir=None, remove_empty_folders=True):
    """
    写真ファイルの逆整理を実行する関数
    
    Args:
        target_dir (str): 処理対象のディレクトリパス。Noneの場合は現在のディレクトリ
        remove_empty_folders (bool): 空になったフォルダを削除するかどうか
    """
    
    # 対象ディレクトリを決定
    if target_dir:
        current_dir = Path(target_dir)
        if not current_dir.exists():
            print(f"❌ エラー: 指定されたディレクトリが存在しません: {target_dir}")
            return False
        if not current_dir.is_dir():
            print(f"❌ エラー: 指定されたパスはディレクトリではありません: {target_dir}")
            return False
    else:
        current_dir = Path('.')
    
    print(f"📂 処理対象ディレクトリ: {current_dir.absolute()}")
    
    # 画像ファイルの拡張子
    image_extensions = {
        '.jpg', '.jpeg', '.jfif', '.jpe',  # JPEG系
        '.png', '.gif', '.bmp', '.tiff', '.tif',  # 一般的な形式
        '.webp', '.avif', '.heic', '.heif',  # 新しい形式
        '.raw', '.cr2', '.nef', '.arw', '.dng',  # RAW形式
        '.svg', '.ico'  # その他
    }
    
    # サブフォルダ内の画像ファイルを検索
    folders_with_images = {}
    total_images = 0
    
    for item in current_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name != '__pycache__':
            image_files = []
            for file_path in item.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                    image_files.append(file_path)
            
            if image_files:
                folders_with_images[item.name] = image_files
                total_images += len(image_files)
    
    print(f"🖼️  見つかった画像ファイル数: {total_images}")
    print(f"📁 画像を含むフォルダ数: {len(folders_with_images)}")
    
    if total_images == 0:
        print("❌ 処理対象の画像ファイルが見つかりませんでした。")
        return False
    
    # 移動予定の表示
    print("\n" + "="*50)
    print("📋 逆整理プレビュー")
    print("="*50)
    
    for folder_name, files in folders_with_images.items():
        print(f"📁 '{folder_name}' フォルダ: {len(files)}個のファイル")
        # ファイル名の例を表示
        if len(files) <= 3:
            for file_path in files:
                print(f"  • {file_path.name}")
        else:
            for file_path in files[:3]:
                print(f"  • {file_path.name}")
            print(f"  • ... 他{len(files)-3}個")
    
    print(f"\n📊 合計 {total_images} 個のファイルを親ディレクトリに移動します")
    if remove_empty_folders:
        print("🗑️  空になったフォルダは削除されます")
    else:
        print("📁 空になったフォルダは残されます")
    
    # 実行確認
    print("\n" + "="*50)
    try:
        response = input("🤔 逆整理を実行しますか？ (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n❌ キャンセルされました。")
        return False
    
    if response not in ['y', 'yes', 'はい']:
        print("❌ キャンセルされました。")
        return False
    
    # ファイル移動を実行
    print("\n" + "="*50)
    print("🚀 写真逆整理を開始します...")
    print("="*50)
    
    moved_count = 0
    error_count = 0
    removed_folders = 0
    
    for folder_name, files in folders_with_images.items():
        folder_path = current_dir / folder_name
        print(f"\n📁 '{folder_name}' フォルダを処理中...")
        
        # ファイルを移動
        for file_path in files:
            try:
                # 移動先のファイル名を決定（重複回避）
                destination = get_unique_filename(current_dir, file_path.name)
                
                # ファイルを移動
                shutil.move(str(file_path), str(destination))
                moved_count += 1
                
                # リネームされた場合は通知
                if destination.name != file_path.name:
                    print(f"  🔄 名前変更: {file_path.name} → {destination.name}")
                else:
                    print(f"  ✅ 移動: {file_path.name}")
                
            except Exception as e:
                print(f"  ❌ エラー: {file_path.name} の移動に失敗 - {e}")
                error_count += 1
        
        # 空になったフォルダを削除
        if remove_empty_folders:
            try:
                # フォルダが空かチェック
                remaining_files = list(folder_path.iterdir())
                if not remaining_files:
                    folder_path.rmdir()
                    removed_folders += 1
                    print(f"  🗑️  空フォルダを削除: {folder_name}/")
                else:
                    print(f"  📁 フォルダに他のファイルが残っています: {folder_name}/ ({len(remaining_files)}個)")
            except Exception as e:
                print(f"  ⚠️  フォルダ削除エラー: {folder_name}/ - {e}")
    
    # 結果表示
    print("\n" + "="*50)
    print("✅ 逆整理完了！")
    print("="*50)
    print(f"✅ 移動成功: {moved_count}個のファイル")
    if error_count > 0:
        print(f"❌ 移動失敗: {error_count}個のファイル")
    if remove_empty_folders:
        print(f"🗑️  削除されたフォルダ: {removed_folders}個")
    
    return True

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description='写真整理ツールで作成されたフォルダから写真ファイルを取り出します',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
使用例:
  python photo_unorganizer.py                    # 現在のディレクトリを処理
  python photo_unorganizer.py "C:\Photos"        # 指定したディレクトリを処理
  python photo_unorganizer.py --keep-folders     # 空フォルダを残す
        """
    )
    
    parser.add_argument(
        'directory',
        nargs='?',
        help='処理対象のディレクトリパス（省略時は現在のディレクトリ）'
    )
    
    parser.add_argument(
        '--keep-folders',
        action='store_true',
        help='空になったフォルダを削除しない'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='Photo Unorganizer 1.0'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("📸 写真逆整理ツール (Photo Unorganizer) v1.0")
    print("=" * 60)
    print("🎯 機能:")
    print("  • フォルダ内の写真ファイルを親ディレクトリに移動")
    print("  • 重複ファイル名の自動処理")
    print("  • 空フォルダの削除オプション")
    print("  • 多様な画像形式に対応")
    print("=" * 60)
    
    try:
        success = unorganize_photos(
            target_dir=args.directory,
            remove_empty_folders=not args.keep_folders
        )
        if success:
            print("\n🎉 逆整理が完了しました！")
        else:
            print("\n❌ 逆整理を中止しました。")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  ユーザーによって中断されました。")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 