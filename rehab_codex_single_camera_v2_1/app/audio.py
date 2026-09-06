from __future__ import annotations

import sys
from pathlib import Path


class AudioGate:
    """No queued speech. One local WAV at a time, with context + cooldown guards."""
    def __init__(self):
        self.context = None
        self.last_time = None
        self.last_priority = 99

    def reset(self, context=None):
        self.context, self.last_time, self.last_priority = context, None, 99
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(None, 0)

    def play(self, context, time_s, path, priority=3, cooldown=8):
        if context != self.context or context is None or not Path(path).is_file():
            return False
        if self.last_time is not None and time_s-self.last_time < cooldown and priority >= self.last_priority:
            return False
        if sys.platform == 'win32':
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:
            return False
        self.last_time, self.last_priority = time_s, priority
        return True
