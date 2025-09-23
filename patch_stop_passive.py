from pathlib import Path
path = Path('app/app/ui_login.py')
text = path.read_text(encoding='utf-8')
needle = "    def _stop_passive_fallback(self) -> None:\n        self._passive_enabled = False\n        self._passive_timer.stop()\n        worker = getattr(self, '_passive_worker', None)\n        if worker:\n            try:\n                worker.stop()\n            except Exception:\n                pass\n        self._passive_worker = None\n"
replacement = "    def _stop_passive_fallback(self) -> None:\n        self._passive_enabled = False\n        self._passive_suspended = False\n        self._passive_timer.stop()\n        worker = getattr(self, '_passive_worker', None)\n        if worker:\n            try:\n                worker.stop()\n            except Exception:\n                pass\n        self._passive_worker = None\n"
if needle not in text:
    raise SystemExit('stop passive block not found')
path.write_text(text.replace(needle, replacement, 1), encoding='utf-8')
