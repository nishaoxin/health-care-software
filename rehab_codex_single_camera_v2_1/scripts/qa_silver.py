"""Native synthetic-layout evidence; no cameras, real profiles, audio or network."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.ui.main_window import MainWindow
from app.silver_store import SilverStore
from app.silver_service import execute
from app.storage import Storage
from app.ui.family_demo import FamilyDemoDialog
from test_product_navigation import PassiveRuntime


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    for font in ('msyh.ttc', 'msyhbd.ttc'):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts'/font))
    output = ROOT/'.runtime/qa-silver-v016'
    output.mkdir(parents=True, exist_ok=True)
    runtime = PassiveRuntime()
    w = MainWindow(runtime=runtime)
    w.show()
    w._show_silver()
    d = w.silver_dialog
    d.timer.stop()
    scope = dict(participant_id='demo-only', source_kind='SYNTHETIC', usage_context='TEST')
    with tempfile.TemporaryDirectory() as folder:
        care, clinical = SilverStore(Path(folder)/'support.sqlite3'), Storage(Path(folder)/'clinical.sqlite3')
        try:
            care.consent(scope, '演示家人', ['summary', 'requests', 'safety', 'changes', 'checklist'], 0)
            care.create_request(scope, 'help', 'TEST：本人主动希望联系；不是视觉检出', 'demo-help')
            care.create_request(scope, 'checklist', '人工核查：清理模拟通道上的轻小物品', 'demo-check')
            data = execute(care, clinical, None, scope)
            d.render(data)
            for size in ((1040, 760), (800, 600)):
                d.resize(*size)
                for index, name in enumerate(('today', 'changes', 'family', 'sharing')):
                    d.tabs.setCurrentIndex(index)
                    for _ in range(3): app.processEvents()
                    path = output/f'{name}-{size[0]}.png'
                    assert d.grab().save(str(path))
                    print(path.name, d.width(), d.height())
            d.role.setCurrentIndex(1)
            d.render(execute(care, clinical, None, scope, family=True))
            d.tabs.setCurrentIndex(2)
            app.processEvents()
            assert d.grab().save(str(output/'family-role.png'))
            phone = FamilyDemoDialog(w)
            phone.timer.stop()
            phone.render(dict(running=False))
            phone.show()
            app.processEvents()
            assert phone.grab().save(str(output/'phone-control.png'))
            phone.close()
        finally:
            clinical.close()
            d.close()
            w._allow_close = True
            w.close()


if __name__ == '__main__':
    main()
