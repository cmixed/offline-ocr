# -*- coding: utf-8 -*-
"""界面模式测试：模式切换、结果页、按钮状态、窗口状态持久化、截图坐标换算。

为什么值得单独测：
「模式」把按钮文字、可用性、结果页、快捷键提示绑在一起，任何一处漏改，
用户就会看到「切到表格模式，复制按钮还能点但复制不出东西」这类错位。

用法：
    .venv\\Scripts\\python.exe test\\test_ui_modes.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QRect, QSettings
from PySide6.QtWidgets import QApplication, QTextEdit, QTableWidget

import main as m

SAMPLE = os.path.join(ROOT, "test", "test_demo.png")
TABLE_SAMPLE = os.path.join(ROOT, "ppocr_img", "ppocr_img", "table", "table.jpg")


def main() -> int:
    app = QApplication.instance() or QApplication([])  # noqa: F841
    store = QSettings(
        os.path.join(tempfile.mkdtemp(prefix="ocr_ui_"), "s.ini"),
        QSettings.Format.IniFormat)
    m._settings = lambda: store

    fails = []
    win = m.MainWindow()

    # 1. 注册表与模式一致性
    for mode in m.MODES:
        for key in ("key", "name", "pick", "result", "on_pick"):
            if key not in mode:
                fails.append(f"[注册表] {mode.get('key')} 缺少字段 {key}")
        if mode["on_pick"] and not hasattr(win, mode["on_pick"]):
            fails.append(f"[注册表] 找不到方法 {mode['on_pick']}")
        if mode.get("on_run") and not hasattr(win, mode["on_run"]):
            fails.append(f"[注册表] 找不到方法 {mode['on_run']}")
        if mode["result"] not in win._result_pages:
            fails.append(f"[注册表] 结果页 {mode['result']} 未注册")

    # 2. 切换模式：按钮文字 / 结果页 / 运行按钮显隐
    for key in ("instant", "table", "basic"):
        win.set_mode(key)
        cfg = m.MODE_BY_KEY[key]
        if win.btn_pick.text() != cfg["pick"]:
            fails.append(f"[{key}] pick 按钮文字 {win.btn_pick.text()}")
        if win.result_stack.currentWidget() is not win._result_pages[cfg["result"]]:
            fails.append(f"[{key}] 结果页未切换")
        if cfg["run"] is None:
            if win.btn_run.isVisible():
                fails.append(f"[{key}] 不应显示运行按钮")
        elif win.btn_run.text() != cfg["run"]:
            fails.append(f"[{key}] run 按钮文字 {win.btn_run.text()}")

    # 3. 载入图片后按钮可用性
    win.set_mode("basic")
    win.load_image(SAMPLE)
    if win.image is None:
        fails.append("[载入] 图片为空")
    if not win.btn_run.isEnabled():
        fails.append("[载入] 普通模式运行按钮应可用")
    if win.btn_copy.isEnabled() or win.btn_export.isEnabled():
        fails.append("[载入] 尚无结果时复制/导出应禁用")

    # 4. 文本结果 -> 复制/导出可用
    win.on_recognized(m.engine.recognize_image(win.image))
    if not win.lines:
        fails.append("[识别] 文本结果为空")
    if not (win.btn_copy.isEnabled() and win.btn_export.isEnabled()):
        fails.append("[识别] 有结果后复制/导出应可用")
    if not isinstance(win.result_stack.currentWidget(), QTextEdit):
        fails.append("[识别] 普通模式应显示文本框")

    # 5. 表格结果 -> 表格页 + 复制/导出可用
    win.set_mode("table")
    if not isinstance(win.result_stack.currentWidget(), QTableWidget):
        fails.append("[模式] 表格模式应显示表格控件")
    if win.btn_copy.isEnabled():
        fails.append("[表格] 尚无表格结果时复制应禁用")
    if os.path.exists(TABLE_SAMPLE):
        win.on_table_recognized(m.table_engine.recognize(TABLE_SAMPLE))
        if not win.table or not win.table.rows:
            fails.append("[表格] 识别结果为空")
        else:
            if win.table_result.rowCount() != win.table.n_rows:
                fails.append("[表格] 控件行数与结果不一致")
            if not (win.btn_copy.isEnabled() and win.btn_export.isEnabled()):
                fails.append("[表格] 有结果后复制/导出应可用")
    else:
        print("（跳过真实表格识别：样例图不存在）")

    # 6. 截图坐标换算（高 DPI 下的缩放）
    rect = QRect(100, 50, 300, 200)
    mapped = m.ScreenCaptureOverlay.map_rect((1536, 864), (1920, 1080), rect)
    if mapped.width() != 375 or mapped.height() != 250:
        fails.append(f"[截图映射] 尺寸应为 375×250，实际 {mapped.width()}×{mapped.height()}")
    if mapped.x() != 125 or mapped.y() not in (62, 63):
        fails.append(f"[截图映射] 起点异常 {mapped.x()},{mapped.y()}")

    # 7. 窗口状态持久化
    win.close()
    win2 = m.MainWindow()
    if win2.mode != "table":
        fails.append(f"[持久化] 恢复的模式是 {win2.mode}，期望 table")
    if win2.splitter.sizes() == [0, 0]:
        fails.append("[持久化] splitter 尺寸未恢复")

    # 8. 关闭记忆后不应恢复
    m.save_ui_prefs(False, store)
    win3 = m.MainWindow()
    if win3.mode != "basic":
        fails.append(f"[关闭记忆] 仍恢复为 {win3.mode}")
    if m.load_ui_prefs(store)["remember"]:
        fails.append("[关闭记忆] remember 仍为 True")

    print("模式:", ", ".join(f"{m2['key']}({m2['name']})" for m2 in m.MODES))
    print("结果页:", {k: type(v).__name__ for k, v in win._result_pages.items()})
    print("截图映射:", mapped.getRect())

    if fails:
        print("\n失败：")
        for f in fails:
            print("  -", f)
        return 1
    print("\n全部通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
