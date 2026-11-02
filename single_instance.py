"""Per-user instance lock and local IPC to activate the existing window."""
import hashlib
import json
import os
from pathlib import Path
import time

from PySide6.QtCore import QObject, Signal, QLockFile, QStandardPaths
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activation_requested = Signal(object)

    def __init__(self, parent=None, directory=None):
        super().__init__(parent)
        folder = Path(directory or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        folder.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(str(folder.resolve()).casefold().encode('utf-8')).hexdigest()[:24]
        self.server_name = 'WatermarkStudio-' + identity
        self.lock = QLockFile(str(folder / 'instance.lock'))
        # Age alone must never invalidate a lock held by a live process.
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept_connection)
        self.owned = False

    def acquire(self, paths=()):
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise RuntimeError('无法创建软件运行锁，请检查用户数据目录的写入权限。')
            # Let the first process take focus under Windows' foreground rules.
            if os.name == 'nt':
                try:
                    import ctypes
                    valid, pid, host, process_name = self.lock.getLockInfo()
                    if valid:
                        ctypes.windll.user32.AllowSetForegroundWindow(int(pid))
                except (OSError, AttributeError, TypeError, ValueError):
                    pass
            self._notify_existing(paths)
            return False
        self.owned = True
        # Removing a stale socket is safe only while holding the instance lock.
        QLocalServer.removeServer(self.server_name)
        if not self.server.listen(self.server_name):
            detail = self.server.errorString()
            self.close()
            raise RuntimeError('无法初始化单实例通信：' + detail)
        return True

    def _notify_existing(self, paths):
        payload = (json.dumps({'paths': list(paths)}, ensure_ascii=False) + '\n').encode('utf-8')
        for attempt in range(10):
            socket = QLocalSocket()
            socket.connectToServer(self.server_name)
            if socket.waitForConnected(150):
                socket.write(payload)
                socket.flush()
                if socket.bytesToWrite():
                    socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
                return
            socket.abort()
            time.sleep(0.08)

    def _accept_connection(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            state = bytearray()

            def receive(socket=socket, state=state):
                state.extend(bytes(socket.readAll()))
                if len(state) > 1024 * 1024:
                    socket.abort()
                    return
                if b'\n' not in state:
                    return
                try:
                    message = json.loads(bytes(state).split(b'\n', 1)[0])
                    paths = message.get('paths', [])
                    if isinstance(paths, list) and all(isinstance(path, str) for path in paths):
                        self.activation_requested.emit(paths)
                except (ValueError, TypeError, AttributeError):
                    pass
                socket.disconnectFromServer()

            socket.readyRead.connect(receive)
            socket.disconnected.connect(socket.deleteLater)
            receive()

    def close(self):
        if self.owned:
            self.server.close()
            self.lock.unlock()
            self.owned = False
