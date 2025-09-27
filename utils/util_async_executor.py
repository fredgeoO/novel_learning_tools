import asyncio
import time
import signal
import sys
from typing import List, Callable, Any, Optional, Awaitable
from tqdm.asyncio import tqdm


_RATE_LIMIT_LOCKS = {}
_LAST_REQUEST_TIMES = {}


# 全局变量用于保存原始信号处理器（用于恢复）
_original_sigint_handler = None
_original_sigterm_handler = None


async def run_limited_async_tasks(
    tasks: List[Any],
    task_func: Callable[[Any], Awaitable[Any]],
    skip_if_exists: Optional[Callable[[Any], bool]] = None,
    max_concurrent: int = 3,
    min_interval: float = 0.0,
    rate_limit_key: str = "default",
    desc: str = "Processing",
) -> List[bool]:
    """
    自动支持 Ctrl+C 优雅关闭：收到 SIGINT 后，跳过未开始的任务，等待已开始的任务完成。
    """
    if not tasks:
        return []

    shutdown_event = asyncio.Event()

    def _signal_handler(sig, frame):
        if not shutdown_event.is_set():
            tqdm.write("\n\n⚠️  收到中断信号（Ctrl+C），后续任务将跳过，正在等待当前任务完成...\n")
            shutdown_event.set()

    # 保存并设置信号处理器
    global _original_sigint_handler, _original_sigterm_handler
    if sys.platform == "win32":
        _original_sigint_handler = signal.signal(signal.SIGINT, _signal_handler)
        # Windows 无 SIGTERM，忽略
    else:
        loop = asyncio.get_running_loop()
        _original_sigint_handler = loop._signal_handlers.get(signal.SIGINT, signal.default_int_handler)
        _original_sigterm_handler = loop._signal_handlers.get(signal.SIGTERM, signal.SIG_DFL)
        loop.add_signal_handler(signal.SIGINT, lambda: _signal_handler(signal.SIGINT, None))
        loop.add_signal_handler(signal.SIGTERM, lambda: _signal_handler(signal.SIGTERM, None))

    try:
        # === 原有逻辑开始 ===
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
        orig_indices = [i for i, r in enumerate(results) if r is None]

        pbar = tqdm(total=len(non_skipped), desc=desc, unit="task")

        async def _run_single(task_item, orig_idx):
            task_info = str(task_item).replace('\n', ' ').replace('\r', ' ')
            if len(task_info) > 80:
                task_info = task_info[:77] + "..."
            # 检查是否已请求关闭
            if shutdown_event.is_set():
                tqdm.write(f"[跳过] 因中断请求跳过任务: {task_info}")
                results[orig_idx] = False
                pbar.update(1)
                pbar.set_postfix_str(f"✗ (跳过) {task_info[:50]}")
                return False

            # 限速
            if min_interval > 0:
                async with lock:
                    last = _LAST_REQUEST_TIMES[time_key]
                    now = time.time()
                    if now - last < min_interval:
                        wait = min_interval - (now - last)
                        await asyncio.sleep(wait)
                        now = time.time()
                    _LAST_REQUEST_TIMES[time_key] = now

            # 再次检查（防止在限速等待期间收到信号）
            if shutdown_event.is_set():
                tqdm.write(f"[跳过] 因中断请求跳过任务: {task_info}")
                success = False
            else:
                async with semaphore:
                    try:
                        result = await task_func(task_item)
                        success = bool(result)
                    except Exception as e:
                        tqdm.write(f"[错误] {task_info}: {e}")
                        success = False

            status = "✓" if success else "✗"
            pbar.set_postfix_str(f"{status} {task_info[:50]}")
            results[orig_idx] = success
            pbar.update(1)
            return success

        coros = [_run_single(task, idx) for task, idx in zip(non_skipped, orig_indices)]
        await asyncio.gather(*coros)
        pbar.close()
        # === 原有逻辑结束 ===

        return results

    finally:
        # 恢复原始信号处理器
        if sys.platform == "win32":
            if _original_sigint_handler is not None:
                signal.signal(signal.SIGINT, _original_sigint_handler)
        else:
            loop = asyncio.get_running_loop()
            loop.remove_signal_handler(signal.SIGINT)
            loop.remove_signal_handler(signal.SIGTERM)
            if callable(_original_sigint_handler):
                loop.add_signal_handler(signal.SIGINT, _original_sigint_handler)
            if _original_sigterm_handler != signal.SIG_DFL and callable(_original_sigterm_handler):
                loop.add_signal_handler(signal.SIGTERM, _original_sigterm_handler)