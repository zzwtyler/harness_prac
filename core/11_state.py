"""Per-run state and atomic, scoped JSON checkpoints; no cross-request memory."""
import json
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from pathlib import Path
from uuid import uuid4
from core import permissions as _permissions
require = _permissions.require


@dataclass
class RunState:
    run_id: str
    source_hash: str
    execution_hash: str
    status: str = 'created'
    step: str = 'extract'
    attempts: int = 0
    resumed: bool = False
    extraction_hash: str | None = None
    error: str | None = None

    @classmethod
    def new(cls, source_hash, execution_hash):
        return cls(uuid4().hex, source_hash, execution_hash)

    def to_dict(self):
        return asdict(self)


class ResultStore:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'[0-9]{2}_[a-z0-9_]+', name):
            raise PermissionError('结果文件名无效，禁止跨目录读写')
        path = self.directory / f'{name}.json'
        if path.is_symlink():
            raise PermissionError('禁止通过结果文件符号链接读写')
        return path

    def write(self, name, value):
        require('save.result')
        target = self.path(name)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.directory, delete=False) as file:
                temporary = file.name
                json.dump(value, file, ensure_ascii=False, indent=2)
                file.write('\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def read(self, name):
        require('load.checkpoint')
        path = self.path(name)
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('检查点过大')
        return json.loads(path.read_text(encoding='utf-8'))

    @contextmanager
    def lock(self):
        require('save.result')
        self.directory.mkdir(parents=True, exist_ok=True)
        lock = self.directory / '.run.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError('结果目录被占用；若进程已退出，请先确认并清理遗留.run.lock再恢复') from exc
        try:
            os.write(fd, str(os.getpid()).encode())
            yield
        finally:
            os.close(fd)
            lock.unlink()
