# -*- coding: utf-8 -*-
"""快捷键测试：验证「声明」「绑定」「设置面板」三者一致。

为什么需要这个测试：
快捷键有两处呈现——一是程序实际绑定的按键，二是设置面板里给用户看的说明。
若只改一处，用户会看到一个「按了没反应」的说明表。本测试让两边都对同一个
模块级常量 SHORTCUTS 校验，任何一边漂移都会立刻失败。

检查项：
1. SHORTCUTS 里每个动作键，在 MainWindow._action_map() 中都有实现
2. 实际绑定数 = 声明数 + 别名数（Ctrl+Enter 同时绑主键盘与小键盘回车）
3. 设置面板展示的条目数与声明数一致
4. 没有重复绑定（同一序列绑给两个动作时，只有一个会生效）

用法：
    .venv\\Scripts\\python.exe test\\test_shortcuts.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtWidgets import QApplication, QGroupBox, QLabel

import main as m


def panel_keycaps(dialog) -> list:
    """取出设置面板里所有按键胶囊的文字，用于与 SHORTCUTS 比对。"""
    caps = []
    for box in dialog.findChildren(QGroupBox):
        for label in box.findChildren(QLabel):
            text = label.text()
            if label.styleSheet() == m.SettingsDialog.KEYCAP_STYLE:
                caps.append(text)
    return caps


def main() -> int:
    app = QApplication.instance() or QApplication([])  # noqa: F841
    win = m.MainWindow()
    fails = []

    # 1. 动作键都有实现
    actions = win._action_map()
    for keys, desc, name in m.SHORTCUTS:
        if name not in actions:
            fails.append(f"[动作缺失] {keys}（{desc}）-> {name} 没有对应槽函数")

    # 2. 绑定数量 = 声明 + 别名
    expected = sum(
        len(m._SHORTCUT_ALIASES.get(keys, (keys,)))
        for keys, _d, _n in m.SHORTCUTS
    )
    actual = len(win._shortcuts)
    if actual != expected:
        fails.append(f"[数量不符] 期望绑定 {expected} 个，实际 {actual} 个")

    # 3. 面板条目与声明一致
    dialog = m.SettingsDialog(win)
    caps = panel_keycaps(dialog)
    declared = [keys for keys, _d, _n in m.SHORTCUTS]
    if caps != declared:
        fails.append(f"[面板不一致] 面板显示 {caps}，声明为 {declared}")

    # 4. 无重复绑定
    seqs = [s.key().toString() for s in win._shortcuts]
    dup = sorted({s for s in seqs if seqs.count(s) > 1})
    if dup:
        fails.append(f"[重复绑定] {', '.join(dup)}")

    print(f"声明 {len(declared)} 项 / 绑定 {actual} 个 / 面板 {len(caps)} 行")
    for keys, desc, _n in m.SHORTCUTS:
        print(f"  {keys:<14} {desc}")
    print(f"  （别名：{', '.join(f'{k} -> {v}' for k, v in m._SHORTCUT_ALIASES.items())}）")

    if fails:
        print("\n失败：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n全部通过：声明、绑定、面板三者一致 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
