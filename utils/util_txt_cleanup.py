import os
import re
from pathlib import Path


def sanitize_name(name: str) -> str:
    """
    清洗文件或文件夹名，移除 Windows 非法字符，并处理多余标点
    """
    # Windows 非法字符：\ / : * ? " < > |
    # 注意：中文标点如 ？ " " 等虽合法，但为安全可替换或保留
    # 这里我们只处理真正非法的英文符号 + 过多的点/空格

    # 替换非法字符为空格（或你可以用下划线 _）
    name = re.sub(r'[\\/:*?"<>|]', ' ', name)

    # 处理连续的点、空格、破折号等，避免 "...." 或 "   "
    name = re.sub(r'[\.]{2,}', '.', name)  # 多个点 → 单个点
    name = re.sub(r'[-]{2,}', '-', name)  # 多个破折号 → 单个
    name = re.sub(r'[ ]{2,}', ' ', name)  # 多个空格 → 单个空格

    # 去除首尾空格和点（Windows 不允许文件名以空格或点结尾）
    name = name.strip(' .')

    # 防止名字变空
    if not name:
        name = "unnamed"

    return name


def delete_small_txt_files(root_path: str, size_limit: int = 3072) -> int:
    """
    删除指定路径下小于指定大小（字节）的txt文件
    默认删除小于3KB（3072字节）的txt文件
    返回删除的文件数量
    """
    root = Path(root_path).resolve()
    if not root.exists():
        print(f"❌ 路径不存在: {root}")
        return 0

    deleted_count = 0

    # 遍历所有txt文件
    for txt_file in root.rglob("*.txt"):
        try:
            file_size = txt_file.stat().st_size
            if file_size < size_limit:
                print(f"🗑️  删除小文件: {txt_file} (大小: {file_size} 字节)")
                txt_file.unlink()  # 删除文件
                deleted_count += 1
        except Exception as e:
            print(f"❌ 删除文件失败 {txt_file}: {e}")

    return deleted_count


def rename_safe_dirs_and_files(root_path: str):
    """
    递归清洗并重命名 root_path 下所有文件夹和文件名
    """
    root = Path(root_path).resolve()
    if not root.exists():
        print(f"❌ 路径不存在: {root}")
        return

    # 使用 os.walk(topdown=False) 从最深层开始处理（先子后父）
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        current_dir = Path(dirpath)

        # 1. 先重命名该目录下的所有文件
        for filename in filenames:
            old_file = current_dir / filename
            new_filename = sanitize_name(filename)
            new_file = current_dir / new_filename

            if new_file != old_file:
                try:
                    if not new_file.exists():  # 避免覆盖
                        old_file.rename(new_file)
                        print(f"📄 重命名文件: {old_file} → {new_file}")
                    else:
                        print(f"⚠️  跳过（目标已存在）: {new_file}")
                except Exception as e:
                    print(f"❌ 文件重命名失败: {old_file} → {e}")

        # 2. 再重命名该目录本身（因为子项已处理完）
        old_dirname = current_dir.name
        new_dirname = sanitize_name(old_dirname)
        new_dir = current_dir.parent / new_dirname

        if new_dir != current_dir:
            try:
                if not new_dir.exists():
                    current_dir.rename(new_dir)
                    print(f"📁 重命名文件夹: {current_dir} → {new_dir}")
                else:
                    print(f"⚠️  跳过（目标文件夹已存在）: {new_dir}")
            except Exception as e:
                print(f"❌ 文件夹重命名失败: {current_dir} → {e}")


# ===== 主程序 =====
if __name__ == "__main__":
    # 脚本在 utils/，目标是 ../reports/novels/
    reports_novels = Path(__file__).parent.parent / "novels"
    print(f"🔧 开始清洗路径: {reports_novels.resolve()}")

    # 先删除小txt文件
    print("\n🔍 开始删除小于3KB的txt文件...")
    deleted_count = delete_small_txt_files(str(reports_novels), size_limit=3072)
    print(f"✅ 删除了 {deleted_count} 个小txt文件")

    # 再进行文件名清洗
    print("\n🔍 开始清洗文件名...")
    rename_safe_dirs_and_files(str(reports_novels))
    print("✅ 全部操作完成！")