"""子进程执行封装。

这里重建的是 bash 版 ``run_timed`` 的两项价值，缺一项就会付出代价：

1. **心跳**：超过 10s 的步骤每 15s 输出一行进度。
   pip 装 190MB torch、pnpm 解析依赖树时可能数十秒无输出 ——
   没有心跳，运维会直接判定卡死并杀掉进程，然后得到一个半安装状态。

2. **实时流式输出**：日志不是命令结束后才 dump 出来。长命令跑了一小时，
   中途看不到任何东西跟"挂了"没有区别。

另外两条是 Python 相对 bash 的天然优势，但它们对应的 bash 陷阱值得记下来，
以便在审阅旧脚本时能认出同源问题：

- `set -e` 下 `wait "$pid"` 会让子进程失败静默杀掉整个脚本、**无任何报错**；
- **不能在 if 之后再取退出码** —— 那时拿到的是 if 语句自身的状态，
  会把失败伪造成成功，让后续步骤带着半成品环境继续跑。

Python 里退出码就是返回值，这两个问题不存在。
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import IO

__all__ = ["CommandError", "Result", "run", "which", "stream"]


HEARTBEAT_AFTER: float = 10.0   # 静默多久后开始心跳
HEARTBEAT_EVERY: float = 15.0
_POLL_INTERVAL: float = 0.2


class CommandError(RuntimeError):
    """命令以非零状态退出。"""

    def __init__(self, cmd: Sequence[str], code: int, tail: str = "") -> None:
        self.cmd = list(cmd)
        self.code = code
        self.tail = tail
        display = " ".join(str(c) for c in self.cmd)
        super().__init__(f"命令失败（退出码 {code}）: {display}" + (f"\n{tail}" if tail else ""))


@dataclass
class Result:
    """命令执行结果。"""

    cmd: list[str]
    code: int
    stdout: str = ""
    stderr: str = ""
    elapsed: float = 0.0
    timed_out: bool = False
    _lines: list[str] = field(default_factory=list, repr=False)

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out

    @property
    def lines(self) -> list[str]:
        return self._lines


def which(name: str) -> str | None:
    """查找可执行文件路径。

    注意：发现二进制**不代表它可用** —— corepack 会留下"可执行但一跑就崩"的
    pnpm shim。对这类工具必须额外做一次 `--version` 冒烟（见 act/frontend.py）。
    """
    from shutil import which as _which

    return _which(name)


def run(
    cmd: Sequence[str],
    *,
    check: bool = False,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    label: str | None = None,
    heartbeat: bool = True,
    echo: bool = True,
    quiet_tail: int = 0,
    stdin: str | Path | None = None,
    stdin_text: str | None = None,
    on_line: Callable[[str], None] | None = None,
) -> Result:
    """执行一条命令，流式转发输出，可选超时与心跳。

    :param check:       非 0 退出码时抛 :class:`CommandError`
    :param timeout:     超时秒数；超时会**杀整个进程树**并置 ``timed_out``
    :param label:       心跳行里显示的名字，默认用命令首个 token
    :param echo:        是否把子进程 stdout/stderr 实时转出
    :param quiet_tail:  >0 时只保留末 N 行，避免长时间安装的日志撑爆内存
    :param stdin:       喂给子进程的文件路径或句柄。**默认 DEVNULL**，而不是
                        继承父进程 —— 这条默认值得单独说：像 ``mysql`` 这类
                        命令在没给输入时会从 stdin 读脚本，继承父 stdin 时要么
                        挂起等输入，要么静默空跑后以 0 退出（见 act/db.py 事故五）。
    :param stdin_text:  直接以管道写入的文本（写完即关闭 stdin）。
                        用于把 SQL 等敏感内容送进子进程——**必须走这条而不是
                        ``bash -c`` heredoc**：后者会让内容出现在 argv 里，
                        ``/proc/<pid>/cmdline`` 对所有用户可读（评审 P0-3）。
                        仅适合小文本（<64KB 管道缓冲），写完即关不阻塞读循环。

    ⚠️ 读取模型（评审 P0-2 的修复，别改回直读）：
    stdout 由**泵线程**读入队列，主循环 ``q.get(timeout=0.2)`` 带超时取行。
    直读版的 ``readline()`` 是阻塞调用——子进程静默挂起（网络黑洞、mysql
    导入卡死、pip 的 ``\\r`` 进度条无换行）时它永不返回，timeout 与心跳的
    检查**永远执行不到**，最被依赖的两个安全网在最需要时同时失效。
    """
    argv = [str(c) for c in cmd]
    name = label or (argv[0] if argv else "?")
    started = time.monotonic()

    handle = None
    if stdin_text is not None:
        stdin_arg: object = subprocess.PIPE
    elif stdin is None:
        stdin_arg = subprocess.DEVNULL
    elif isinstance(stdin, (str, Path)):
        handle = open(stdin, "r", encoding="utf-8", errors="replace")
        stdin_arg = handle
    else:
        stdin_arg = stdin

    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=stdin_arg,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    finally:
        if handle is not None:
            handle.close()

    if stdin_text is not None and proc.stdin:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.flush()
        except BrokenPipeError:
            pass                        # 子进程提前退出，错误由退出码呈现
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    q: Queue[str | None] = Queue()
    import threading

    def _pump() -> None:
        try:
            if proc.stdout is None:
                return
            for raw in proc.stdout:
                q.put(raw)
        finally:
            q.put(None)                 # EOF 哨兵

    pump = threading.Thread(target=_pump, daemon=True)
    pump.start()

    lines: list[str] = []
    last_output = time.monotonic()
    next_beat = last_output + HEARTBEAT_AFTER
    timed_out = False

    try:
        while True:
            try:
                item = q.get(timeout=_POLL_INTERVAL)
            except Empty:
                item = ""
            if item is None:            # EOF：所有行都已被消费
                break
            if item:
                line = item.rstrip("\n")
                lines.append(line)
                if quiet_tail:
                    lines = lines[-quiet_tail:]
                if echo:
                    print(line, flush=True)
                if on_line is not None:
                    on_line(line)
                last_output = time.monotonic()

            now = time.monotonic()
            if timeout is not None and now - started > timeout:
                timed_out = True
                _kill_tree(proc)
                break
            if heartbeat and now >= next_beat:
                print(f"  … {name} 进行中（{int(now - started)}s）", flush=True)
                next_beat = now + HEARTBEAT_EVERY
            if proc.poll() is not None and q.empty():
                break
    finally:
        if proc.stdout:
            proc.stdout.close()  # type: ignore[union-attr]
        pump.join(timeout=1.0)
        proc.wait()

    elapsed = time.monotonic() - started
    result = Result(
        cmd=argv,
        code=proc.returncode if proc.returncode is not None else -1,
        stdout="\n".join(lines),
        timed_out=timed_out,
        elapsed=elapsed,
        _lines=lines,
    )
    result.timed_out = timed_out

    if timed_out:
        if check:
            raise CommandError(argv, -1, f"{name} 执行超时（>{timeout}s）")
        return result
    if check and not result.ok:
        raise CommandError(argv, result.code, "\n".join(lines[-20:]))
    return result


def _kill_tree(proc: subprocess.Popen) -> None:
    """杀掉子进程及其全部后代（评审 P1-14）。

    不用 ``start_new_session`` + ``killpg``：那会把子进程挪出我们的进程组，
    交互安装时用户按 Ctrl-C（SIGINT 发给前台进程组）就再也杀不到子进程。
    改为遍历 /proc 的 ppid 链收集后代，逐个 SIGKILL。
    """
    def _descendants(pid: int) -> list[int]:
        kids: dict[int, list[int]] = {}
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat", "rb") as fh:
                    stat = fh.read().decode("utf-8", "replace")
                ppid = int(stat.rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                continue
            kids.setdefault(ppid, []).append(int(entry))
        out: list[int] = []
        stack = [pid]
        while stack:
            cur = stack.pop()
            for child in kids.get(cur, ()):
                out.append(child)
                stack.append(child)
        return out

    for victim in _descendants(proc.pid):
        try:
            os.kill(victim, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def stream(cmd: Sequence[str], *, sink: IO[str] | None = None, **kw) -> Result:
    """便捷别名：把输出实时写到一个 sink（如日志文件句柄）。

    ⚠️ 此前 ``sink`` 参数被静默丢弃（评审 P1-14）——调用方以为在写日志，
    实际什么都没写。经 ``run`` 的 ``on_line`` 钩子逐行落盘。
    """
    if sink is not None:
        def _to_sink(line: str) -> None:
            sink.write(line + "\n")
            sink.flush()
        kw["on_line"] = _to_sink
    return run(cmd, **kw)
