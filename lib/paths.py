"""目录落地的唯一入口。

溯源：GitHub #2。`.ratchet/log` 在下游项目里一度不是目录（普通文件），
而 `os.makedirs(..., exist_ok=True)` 的 `exist_ok` **只对「已经是目录」豁免** ——
路径是普通文件或悬空软链时照抛 `FileExistsError`。两个落点各自裸调，于是：

  · ratchet-init   —— 新用户第一步吃一屏 traceback（脚手架最该稳的时刻）
  · ratchet-digest —— hook 模式的兜底 except 把它吞成 `{}`，留痕静默失效

静默比崩溃更危险：崩溃会被看见，静默要等到翻历史时才发现一片空白。

所以把 `os.makedirs` 收进这里，让调用方只需要处理一种异常。
test/run.sh 有一条断言禁止 bin/ 再出现裸 makedirs —— 同类错不能重演。
"""

import os


class PathConflict(Exception):
    """目标路径被非目录占用，或父链上有非目录节点。

    带人话 message：点名冲突路径与它的实际类型，并给出处置建议。
    **绝不代劳删除** —— 那是用户数据，ratchet 没有资格替他决定。
    """

    def __init__(self, path: str, detail: str = ""):
        self.path = path
        self.detail = detail
        super().__init__(self._msg())

    def _kind(self) -> str:
        p = self.path
        if os.path.islink(p):
            tgt = os.path.realpath(p)
            return "软链（悬空）" if not os.path.exists(p) else f"软链 → {tgt}"
        if os.path.isfile(p):
            return "普通文件"
        if os.path.lexists(p):
            return "非目录节点"
        return "无法创建"

    def _msg(self) -> str:
        lines = [
            f"{self.path} 需要是目录，实际是{self._kind()}。",
            "  ratchet 不会替你删除或改名 —— 那是你的数据。请手工确认后处理：",
            f"    mv {self.path} {self.path}.bak   # 保底：先留一份",
            "  处置完重跑即可。",
        ]
        if self.detail:
            lines.append(f"  底层原因：{self.detail}")
        return "\n".join(lines)


def ensure_dir(path: str) -> None:
    """确保 path 是可用目录，冲突时抛 PathConflict（人话），绝不抛裸 OSError。

    指向有效目录的软链视为合法 —— 用户有意为之的布局，不该拦。
    """
    if os.path.lexists(path) and not os.path.isdir(path):
        raise PathConflict(path)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        # 父链上有非目录节点（如 .ratchet 本身是文件），或权限不足。
        # 一样转成人话 —— 这个函数的契约是「不漏 traceback 给用户」。
        raise PathConflict(path, str(e)) from e
