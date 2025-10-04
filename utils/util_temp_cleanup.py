import os
import shutil
import stat
import time
from typing import List, Optional
from tqdm import tqdm


def remove_readonly(func, path, _):
    """清除只读属性后重试删除"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass  # 忽略无法删除的错误，避免中断


def clean_temp_folders_by_keywords_and_age(
        temp_dir: str = 'C:\\Users\\zgw31\\AppData\\Local\\Temp',
        keywords: List[str] = ['selenium', 'chrome'],
        age_minutes: int = 30,
        show_details: bool = False
):
    if not os.path.exists(temp_dir):
        print(f"⚠️  目录不存在: {temp_dir}")
        return

    keywords_lower = [kw.lower() for kw in keywords]
    current_time = time.time()
    candidates = []

    # 第一步：扫描符合条件的文件夹
    try:
        for name in os.listdir(temp_dir):
            folder_path = os.path.join(temp_dir, name)
            if not os.path.isdir(folder_path):
                continue
            if not any(kw in name.lower() for kw in keywords_lower):
                continue
            try:
                create_time = os.path.getctime(folder_path)
                age_in_minutes = (current_time - create_time) / 60
            except (OSError, ValueError):
                continue
            if age_in_minutes >= age_minutes:
                candidates.append((folder_path, age_in_minutes))
    except Exception as e:
        print(f"❌ 遍历目录时出错: {e}")
        return

    if not candidates:
        print("✅ 未发现符合条件的临时文件夹。")
        return

    deleted_count = 0
    failed_list = []

    # 第二步：使用手动控制的 tqdm 进度条
    pbar = tqdm(total=len(candidates), desc="清理临时文件夹", unit="个")
    try:
        for folder_path, age_in_minutes in candidates:
            try:
                shutil.rmtree(folder_path, onerror=remove_readonly)
                deleted_count += 1
                if show_details:
                    tqdm.write(f"✅ 已删除 ({age_in_minutes:.1f} 分钟前): {folder_path}")
            except PermissionError:
                failed_list.append(folder_path)
                if show_details:
                    tqdm.write(f"⚠️  权限不足或被占用: {folder_path}")
            except Exception as e:
                failed_list.append(folder_path)
                if show_details:
                    tqdm.write(f"❌ 删除失败 {folder_path}: {e}")
            finally:
                pbar.update(1)  # 每次循环结束更新进度
    finally:
        pbar.close()  # 确保进度条关闭

    # 可选：最后汇总结果
    if show_details or failed_list:
        print(f"\n📊 清理完成：成功 {deleted_count} 个，失败 {len(failed_list)} 个。")
        if failed_list:
            print("❌ 以下文件夹未能删除：")
            for f in failed_list:
                print(f"  - {f}")



def clean_selenium_chrome_temp_folders():
    """兼容旧调用方式"""
    clean_temp_folders_by_keywords_and_age()


if __name__ == "__main__":
    # 默认：只显示进度条，不逐个打印
    clean_temp_folders_by_keywords_and_age()

    # 如果你想看每个删除项的详情，可设 show_details=True
    # clean_temp_folders_by_keywords_and_age(show_details=True)