# utils/util_async_executor.py
import asyncio
import time
from typing import List, Callable, Any, Optional

# 全局限速状态（按命名空间隔离）
_RATE_LIMIT_LOCKS = {}
_LAST_REQUEST_TIMES = {}


async def run_limited_async_tasks(
    tasks: List[Any],
    task_func: Callable[[Any], asyncio.Future],
    skip_if_exists: Optional[Callable[[Any], bool]] = None,
    max_concurrent: int = 3,
    min_interval: float = 0.0,
    rate_limit_key: str = "default"
) -> List[bool]:
    """
    通用异步任务执行器，支持跳过、并发控制与全局限速。

    参数:
        tasks: 任务项列表（任意类型）
        task_func: 异步函数，接收一个任务项并执行，应返回可判断真假的结果（如 True/False）
        skip_if_exists: 可选函数，接收任务项，返回 True 表示跳过该任务
        max_concurrent: 最大并发数（控制同时活跃的任务数）
        min_interval: 最小请求间隔（秒），仅对实际执行的任务生效
        rate_limit_key: 限速命名空间，用于隔离不同类型的任务（如 "qwen_web", "api_xxx"）

    返回:
        List[bool]：每个任务是否成功（跳过视为成功）
    """
    if not tasks:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    # 初始化限速锁和时间戳（按 key 隔离）
    lock_key = f"lock_{rate_limit_key}"
    time_key = f"time_{rate_limit_key}"
    if lock_key not in _RATE_LIMIT_LOCKS:
        _RATE_LIMIT_LOCKS[lock_key] = asyncio.Lock()
        _LAST_REQUEST_TIMES[time_key] = 0.0

    lock = _RATE_LIMIT_LOCKS[lock_key]

    async def _run_single(task_item):
        # 1. 跳过检查
        if skip_if_exists and skip_if_exists(task_item):
            return True

        # 2. 限速控制（仅对实际执行的任务）
        if min_interval > 0:
            async with lock:
                last_time = _LAST_REQUEST_TIMES[time_key]
                now = time.time()
                elapsed = now - last_time
                if elapsed < min_interval:
                    wait_sec = min_interval - elapsed
                    print(f"[限速 {rate_limit_key}] 等待 {wait_sec:.1f} 秒...")
                    await asyncio.sleep(wait_sec)
                    now = time.time()
                _LAST_REQUEST_TIMES[time_key] = now

        # 3. 执行任务（受并发数限制）
        async with semaphore:
            try:
                result = await task_func(task_item)
                return bool(result)
            except Exception as e:
                print(f"[任务执行错误] {task_item}: {e}")
                return False

    # 并发执行
    return await asyncio.gather(*[_run_single(task) for task in tasks])