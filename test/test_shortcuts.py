# -*- coding: utf-8 -*-
"""快捷键测试：验证「定义 / 绑定 / 面板 / 持久化」四者一致。

为什么需要这个测试：
快捷键有四处呈现——默认定义、程序实际绑定、设置面板里的输入框、落盘的配置。
只改一处就会出现「面板里写着 A、按下去没反应」这类漂移。本测试全部对着
模块级常量 DEFAULT_SHORTCUTS 校验，任何一边不一致都会立刻失败。

检查项：
1. 默认配置：从未保存过时，加载结果等于 DEFAULT_SHORTCUTS
2. 动作键在 MainWindow._action_map() 里都有实现
3. 启动绑定数 = 配置里的按键总数，且没有重复绑定
4. 设置面板的输入框数量与定义一致，初始值等于当前配置
5. 冲突检测：同一个键绑给两个动作时能报出来；正常配置为 []
6. 持久化往返：改键保存后能读回；清空（解除绑定）也能正确读回
7. 改键后重建绑定，主窗口的 QShortcut 跟着变（无需重启）

用法：
    .venv\\Scripts\\python.exe test\\test_shortcuts.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

import main as m


def _temp_settings() -> QSettings:
    """私有配置，避免测试写入用户真实的快捷键设置。"""
    path = os.path.join(tempfile.mkdtemp(prefix="ocr_shortcut_"), "shortcuts.ini")
    return QSettings(path, QSettings.Format.IniFormat)


def main() -> int:
    app = QApplication.instance() or QApplication([])  # noqa: F841

    # 全程把 _settings 指向临时 ini
    store = _temp_settings()
    m._settings = lambda: store

    fails = []
    defaults = {name: tuple(keys)
                for name, _desc, keys in m.DEFAULT_SHORTCUTS}

    # 1. 默认配置
    loaded = m.load_shortcuts(store)
    if loaded != defaults:
        fails.append(f"[默认值不符] {loaded} != {defaults}")

    # 2. 动作键都有实现
    win = m.MainWindow()
    actions = win._action_map()
    for name, desc, _keys in m.DEFAULT_SHORTCUTS:
        if name not in actions:
            fails.append(f"[动作缺失] {desc}（{name}）没有对应槽函数")

    # 3. 绑定数量与内容
    expected_seqs = [s for seqs in loaded.values() for s in seqs]
    actual_seqs = [s.key().toString() for s in win._shortcuts]
    if len(actual_seqs) != len(expected_seqs):
        fails.append(f"[绑定数量] 期望 {len(expected_seqs)}，实际 {len(actual_seqs)}")
    if sorted(actual_seqs) != sorted(expected_seqs):
        fails.append(f"[绑定内容] 实际 {actual_seqs}，期望 {expected_seqs}")
    dup = sorted({s for s in actual_seqs if actual_seqs.count(s) > 1})
    if dup:
        fails.append(f"[重复绑定] {', '.join(dup)}")

    # 4. 面板
    dialog = m.SettingsDialog(win)
    if len(dialog._edits) != len(m.DEFAULT_SHORTCUTS):
        fails.append(f"[面板行数] {len(dialog._edits)} != {len(m.DEFAULT_SHORTCUTS)}")
    if dialog.collect() != loaded:
        fails.append(f"[面板初值] {dialog.collect()} != {loaded}")

    # 5. 冲突检测
    if dialog.find_conflicts(loaded):
        fails.append(f"[误报冲突] {dialog.find_conflicts(loaded)}")
    clash = dict(loaded)
    clash["copy"] = clash["export"]
    if not dialog.find_conflicts(clash):
        fails.append("[漏报冲突] 同一组合键绑给两个动作却未检出")

    # 5b. 非法按键：无修饰键的普通键会抢走输入，必须拒绝；功能键放行
    bad_map = dict(loaded)
    bad_map["copy"] = ("S",)
    if not dialog.find_invalid(bad_map):
        fails.append("[漏报非法按键] 把复制绑到裸键 S 未被拦下")
    fn_map = dict(loaded)
    fn_map["copy"] = ("F5",)
    if dialog.find_invalid(fn_map):
        fails.append(f"[误报非法按键] F5 不该被拒绝：{dialog.find_invalid(fn_map)}")

    # 6. 持久化往返
    dialog._edits["export"].setKeySequence(QKeySequence("Ctrl+Shift+S"))
    dialog._edits["annot"].clear()               # 解除绑定
    changed = dialog.collect()
    m.save_shortcuts(changed, store)
    reloaded = m.load_shortcuts(store)
    if reloaded["export"] != ("Ctrl+Shift+S",):
        fails.append(f"[改键未保存] export = {reloaded['export']}")
    if reloaded["annot"] != ():
        fails.append(f"[解绑未保存] annot = {reloaded['annot']}")

    # 7. 重建绑定（模拟保存后立即生效）
    win._bind_shortcuts(reloaded)
    rebound = [s.key().toString() for s in win._shortcuts]
    if "Ctrl+Shift+S" not in rebound:
        fails.append(f"[未生效] 重建后没有 Ctrl+Shift+S：{rebound}")
    if "Ctrl+B" in rebound:
        fails.append(f"[解绑未生效] 重建后仍存在 Ctrl+B：{rebound}")
    if "Ctrl+Shift+S" not in win.btn_export.toolTip():
        fails.append(f"[提示未更新] {win.btn_export.toolTip()}")

    # 输出
    print(f"定义 {len(defaults)} 项 / 默认绑定 {len(expected_seqs)} 个 / 面板 {len(dialog._edits)} 行")
    for name, desc, keys in m.DEFAULT_SHORTCUTS:
        print(f"  {m.shortcuts_to_text(keys):<24} {desc}")
    print(f"  改键往返：export -> {reloaded['export']}，"
          f"annot -> {reloaded['annot'] or '（未绑定）'}")

    if fails:
        print("\n失败：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n全部通过：定义、绑定、面板、持久化四者一致 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
