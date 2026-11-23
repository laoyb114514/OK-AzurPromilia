"""配置档（profile）：把 ``configs/`` 下的一份快照存成命名档，随时切换。

为什么不是简单复制 ``configs/``：用户可能有几十个任务配置文件、队列和流程，
切档前必须**先备份当前状态**，否则一次误切就把正在用的配置覆盖掉了。

结构::

    configs/
    ├── profiles/
    │   ├── <档名>/
    │   │   ├── profile.json      # 元信息 + 文件清单（相对路径 + 大小）
    │   │   └── files/…           # 与 configs/ 下相对路径一致的快照
    │   └── .backup_<时间戳>/      # 应用配置档前的自动备份
    ├── DailyTask.json
    └── queues/…

约定：

- 快照范围 = ``configs/`` 下除 ``profiles/`` 以外的全部文件（递归）；
- 应用时只覆盖档里存在的文件，**不删除**档里没有的文件（避免误删用户数据），
  返回值里会如实报告``extra``（当前有、档里没有的文件数）；
- 所有写盘都是 ``.tmp`` + ``os.replace``。
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

PROFILES_FOLDER = "profiles"
BACKUP_PREFIX = ".backup_"
META_NAME = "profile.json"
FILES_FOLDER = "files"


class ProfileError(RuntimeError):
    """配置档操作失败。"""


@dataclass(frozen=True)
class ProfileInfo:
    name: str
    saved_at: float
    files: int
    size: int

    @property
    def saved_text(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.saved_at))

    def label(self) -> str:
        return f"{self.name}  ({self.files} 个文件, {self.size // 1024} KB, {self.saved_text})"


@dataclass
class ApplyResult:
    profile: str
    restored: list[str] = field(default_factory=list)
    backup_dir: Path | None = None
    extra: int = 0

    def summary(self) -> str:
        text = f"已应用配置档 {self.profile}：恢复 {len(self.restored)} 个文件"
        if self.extra:
            text += f"，{self.extra} 个当前文件不在档里（未删除）"
        if self.backup_dir:
            text += f"，原配置备份在 {self.backup_dir.name}"
        return text


class ProfileStore:
    """配置档的保存 / 应用 / 删除。"""

    def __init__(self, config_folder: str | Path = "configs"):
        self.config_folder = Path(config_folder)
        self.profiles_root = self.config_folder / PROFILES_FOLDER

    # ── 路径 ─────────────────────────────────────────────
    def profile_dir(self, name: str) -> Path:
        safe = str(name or "").strip()
        if not safe or safe.startswith(".") or any(ch in safe for ch in '\\/:*?"<>|'):
            raise ProfileError(f"配置档名字不合法: {name!r}")
        return self.profiles_root / safe

    def _config_files(self) -> list[Path]:
        if not self.config_folder.is_dir():
            return []
        files = []
        for path in sorted(self.config_folder.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.config_folder)
            if relative.parts and relative.parts[0] == PROFILES_FOLDER:
                continue
            if relative.name.endswith(".tmp"):
                continue
            files.append(path)
        return files

    # ── 查询 ─────────────────────────────────────────────
    def list(self) -> list[ProfileInfo]:
        if not self.profiles_root.is_dir():
            return []
        infos = []
        for folder in sorted(self.profiles_root.iterdir()):
            if not folder.is_dir() or folder.name.startswith(BACKUP_PREFIX):
                continue
            meta = self._read_meta(folder)
            if meta is None:
                continue
            infos.append(
                ProfileInfo(
                    name=str(meta.get("name", folder.name)),
                    saved_at=float(meta.get("saved_at", 0.0) or 0.0),
                    files=len(meta.get("files", {}) or {}),
                    size=int(meta.get("size", 0) or 0),
                )
            )
        return infos

    def exists(self, name: str) -> bool:
        try:
            return (self.profile_dir(name) / META_NAME).is_file()
        except ProfileError:
            return False

    def _read_meta(self, folder: Path) -> dict | None:
        try:
            return json.loads((folder / META_NAME).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    # ── 保存 ─────────────────────────────────────────────
    def save(self, name: str, overwrite: bool = True) -> ProfileInfo:
        target = self.profile_dir(name)
        if target.exists() and not overwrite:
            raise ProfileError(f"配置档已存在: {name}")
        files_dir = target / FILES_FOLDER
        if files_dir.exists():
            shutil.rmtree(files_dir)
        files_dir.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, dict] = {}
        total = 0
        for source in self._config_files():
            relative = source.relative_to(self.config_folder).as_posix()
            destination = files_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            size = destination.stat().st_size
            total += size
            manifest[relative] = {"size": size}

        saved_at = time.time()
        meta = {
            "name": target.name,
            "saved_at": saved_at,
            "size": total,
            "files": manifest,
        }
        self._write_json(target / META_NAME, meta)
        return ProfileInfo(name=target.name, saved_at=saved_at, files=len(manifest), size=total)

    # ── 应用 ─────────────────────────────────────────────
    def apply(self, name: str) -> ApplyResult:
        target = self.profile_dir(name)
        meta = self._read_meta(target)
        if meta is None:
            raise ProfileError(f"配置档不存在或已损坏: {name}")
        files_dir = target / FILES_FOLDER

        backup_dir = self._backup_current()
        restored: list[str] = []
        for relative in (meta.get("files") or {}):
            source = files_dir / relative
            if not source.is_file():
                continue
            destination = self.config_folder / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            tmp = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copy2(source, tmp)
            os.replace(tmp, destination)
            restored.append(relative)

        current = {
            path.relative_to(self.config_folder).as_posix() for path in self._config_files()
        }
        extra = len(current - set(meta.get("files") or {}))
        return ApplyResult(profile=target.name, restored=restored, backup_dir=backup_dir, extra=extra)

    def _backup_current(self) -> Path | None:
        files = self._config_files()
        if not files:
            return None
        stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        backup_dir = self.profiles_root / f"{BACKUP_PREFIX}{stamp}"
        index = 0
        while backup_dir.exists():
            index += 1
            backup_dir = self.profiles_root / f"{BACKUP_PREFIX}{stamp}_{index}"
        for source in files:
            relative = source.relative_to(self.config_folder)
            destination = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return backup_dir

    # ── 删除 ─────────────────────────────────────────────
    def delete(self, name: str) -> bool:
        target = self.profile_dir(name)
        if not target.is_dir():
            return False
        shutil.rmtree(target, ignore_errors=True)
        return True

    # ── 内部 ─────────────────────────────────────────────
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
