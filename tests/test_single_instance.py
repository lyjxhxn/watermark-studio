"""Process integration checks for instance ownership, activation and recovery."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import json, sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer
from single_instance import SingleInstance
app = QCoreApplication([])
guard = SingleInstance(app, directory=sys.argv[1])
def activated(paths):
    with (Path(sys.argv[1]) / 'notifications.jsonl').open('a', encoding='utf-8') as log:
        log.write(json.dumps(paths, ensure_ascii=False) + '\n')
guard.activation_requested.connect(activated)
primary = guard.acquire(sys.argv[3:])
print(json.dumps({'primary': primary}), flush=True)
if primary and sys.argv[2] == 'hold':
    QTimer.singleShot(30000, app.quit)
    app.exec()
guard.close()
'''


class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = self.temporary.name
        self.processes = []

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        self.temporary.cleanup()

    def start(self, mode, paths=()):
        process = subprocess.Popen([sys.executable, '-c', PROBE, self.directory, mode, *paths],
                                   cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   encoding='utf-8')
        self.processes.append(process)
        return process

    def test_second_process_exits_and_notifies_first(self):
        first = self.start('hold')
        self.assertTrue(json.loads(first.stdout.readline())['primary'])
        second = self.start('notify', ['中文资料.pdf'])
        stdout, stderr = second.communicate(timeout=5)
        self.assertEqual(second.returncode, 0, stderr)
        self.assertFalse(json.loads(stdout)['primary'])
        logfile = Path(self.directory) / 'notifications.jsonl'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not logfile.exists():
            time.sleep(0.02)
        self.assertEqual(json.loads(logfile.read_text(encoding='utf-8').splitlines()[0]), ['中文资料.pdf'])
        self.assertIsNone(first.poll())

    def test_restart_after_abrupt_exit(self):
        first = self.start('hold')
        self.assertTrue(json.loads(first.stdout.readline())['primary'])
        first.kill()
        first.communicate(timeout=5)
        restarted = self.start('notify')
        stdout, stderr = restarted.communicate(timeout=5)
        self.assertEqual(restarted.returncode, 0, stderr)
        self.assertTrue(json.loads(stdout)['primary'])

    def test_restart_after_normal_exit(self):
        for attempt in range(2):
            process = self.start('notify')
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertTrue(json.loads(stdout)['primary'])


if __name__ == '__main__':
    unittest.main()
