# utils/util_async_executor.py
import asyncio
import time
from typing import List, Callable, Any, Optional
from tqdm.asyncio import tqdm


_RATE_LIMIT_LOCKS = {}
_LAST_REQUEST_TIMES = {}


async def run_limited_async_tasks(
    tasks: List[Any],
    task_func: Callable[[Any], asyncio.Future],
    skip_if_exists: Optional[Callable[[Any], bool]] = None,
    max_concurrent: int = 3,
    min_interval: float = 0.0,
    rate_limit_key: str = "default",
    desc: str = "Processing"
) -> List[bool]:
    if not tasks:
        return []

    # 预处理：分离跳过项
    non_skipped = []
    results = []
    for task in tasks:
        if skip_if_exists and skip_if_exists(task):
            results.append(True)
        else:
            non_skipped.append(task)
            results.append(None)

    if not non_skipped:
        return [True] * len(tasks)

    semaphore = asyncio.Semaphore(max_concurrent)
    lock_key = f"lock_{rate_limit_key}"
    time_key = f"time_{rate_limit_key}"
    if lock_key not in _RATE_LIMIT_LOCKS:
        _RATE_LIMIT_LOCKS[lock_key] = asyncio.Lock()
        _LAST_REQUEST_TIMES[time_key] = 0.0

    lock = _RATE_LIMIT_LOCKS[lock_key]

    # 获取原始索引映射
    orig_indices = [i for i, r in enumerate(results) if r is None]

    pbar = tqdm(total=len(non_skipped), desc=desc, unit="task")

    async def _run_single(task_item, orig_idx):
        # 设置当前任务信息到进度条后缀
        task_info = f"{task_item.get('novel_name', '')} | {task_item.get('chapter_filename', '')} | {task_item.get('prompt_name', '')}"
        pbar.set_postfix_str(task_info[:50] + "..." if len(task_info) > 50 else task_info)

        # 限速
        if min_interval > 0:
            async with lock:
                last = _LAST_REQUEST_TIMES[time_key]
                now = time.time()
                if now - last < min_interval:
                    wait = min_interval - (now - last)
                    # 注意：这里不再 print 限速日志！
                    await asyncio.sleep(wait)
                    now = time.time()
                _LAST_REQUEST_TIMES[time_key] = now

        # 执行
        async with semaphore:
            try:
                result = await task_func(task_item)
                success = bool(result)
            except Exception as e:
                # 只保留关键错误（可选是否输出）
                tqdm.write(f"[错误] {task_info}: {e}")
                success = False

        results[orig_idx] = success
        pbar.update(1)
        return success

    coros = [_run_single(task, idx) for task, idx in zip(non_skipped, orig_indices)]
    await asyncio.gather(*coros)
    pbar.close()

    return results