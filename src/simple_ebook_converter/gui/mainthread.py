"""主线程调度器：后台线程投递回调，主线程定时取出来执行。

**为什么不能直接 `root.after(0, cb)`**：那也是一次 Tk 调用。Tkinter 的 `after`
从非主线程调用会抛 `RuntimeError: main thread is not in main loop`（Windows 上
必现），或者在某些平台上随机崩。原以为「`after` 算安全的」，其实它和
`widget.configure()` 一样危险。

所以分成两半：

- `post()` —— 后台线程**只**往 `queue.SimpleQueue` 里塞，队列是纯 Python 对象，
  不碰 Tcl，因此线程安全。
- `_tick()` —— 主线程上由 `after()` 反复触发的取件口，把队列排干并逐个执行。

20ms 一次轮询换来最坏 20ms 的界面延迟，代价可以忽略；换来的是**没有第二个线程
碰 Tcl** 这条硬约束 —— 线程安全的 Tk 程序基本都长这样。

回调抛异常只打印不断轮询：一个坏回调不该让整个界面停止响应。
"""

from __future__ import annotations

import queue
import traceback
from collections.abc import Callable

import tkinter as tk

#: 轮询间隔（ms）。越小界面越跟手，越费 CPU；20ms 约 50Hz，肉眼看不出差别。
POLL_MS = 20


class MainThread:
    """把后台线程的回调搬到主线程执行。

    必须在主线程上构造（`__init__` 会立刻排第一次轮询）。
    """

    def __init__(self, root: tk.Misc, *, poll_ms: int = POLL_MS) -> None:
        self._root = root
        self._poll_ms = poll_ms
        self._queue: queue.SimpleQueue[Callable[[], None]] = queue.SimpleQueue()
        self._alive = True
        self._after_id: str | None = root.after(poll_ms, self._tick)

    def post(self, callback: Callable[[], None]) -> None:
        """后台线程调用。**不做任何 Tk 操作**，所以线程安全。"""
        if self._alive:
            self._queue.put(callback)

    def _tick(self) -> None:
        # 一次排干而不是每轮取一个：积压时（比如规则多、回调多）不至于越排越慢。
        while True:
            try:
                callback = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception:  # noqa: BLE001 - 坏回调不该拖垮整个调度
                traceback.print_exc()
        if self._alive:
            self._after_id = self._root.after(self._poll_ms, self._tick)

    def stop(self) -> None:
        """停掉轮询并丢弃排队中的回调。窗口关闭时调。"""
        self._alive = False
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except tk.TclError:
                pass  # root 已经没了
            self._after_id = None
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
