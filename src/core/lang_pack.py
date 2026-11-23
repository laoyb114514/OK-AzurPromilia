"""语言包：扫描「语言包<代码>\\」目录，一键应用 / 还原。

游戏改语言后，识别用的 OCR 文本和 UI 文案都要跟着换。手工覆盖 `i18n/` 与
`assets/lang/` 容易漏、也容易改坏，所以做成：

```text
语言包EN/
├── i18n/                  # 可选：整体或部分覆盖 i18n/<locale>/LC_MESSAGES/ok.po
│   └── en_US/LC_MESSAGES/ok.po
└── assets/lang/           # 可选：覆盖 OCR 匹配文本
    └── home.json
```

规则：

- **只允许写 `i18n/` 与 `assets/lang/` 两个前缀** —— 语言包不该改代码；
- 应用前把当前这两个目录备份到 `backups/langpack_<时间戳>/`；
- ``restore`` 按备份还原，还原本身也做一份备份（防止二次误操作丢东西）；
- 拒绝绝对路径、``..``、盘符（zip slip 同款检查）。
"""

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

PACK_PREFIX = "语言包"
ALLOWED_PREFIXES = ("i18n/", "assets/lang/")
BACKUP_PREFIX = "langpack_"
BACKUP_ROOT = Path("backups")

_SAFE = re.compile(r"[^0-9A-Za-z_.\u4e00-\u9fff-]+")


class LangPackError(ValueError):
    """语言包不合法。"""


def normalize_member(name: str) -> str:
    """把相对路径规范成 posix，越界则报错。"""
    raw = str(name or "").replace("\\", "/").strip()
    if not raw:
        raise LangPackError("空路径")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise LangPackError(f"不允许绝对路径: {raw}")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise LangPackError(f"路径越界: {raw}")
    return "/".join(parts)


def is_allowed(member: str) -> bool:
    return any(member.startswith(prefix) for prefix in ALLOWED_PREFIXES)


@dataclass(frozen=True)
class LanguagePack:
    """扫描到的一个语言包。"""

    path: Path
    code: str
    files: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.path.name

    def label(self) -> str:
        return f"{self.name}（{self.code}，{len(self.files)} 个文件）"


def pack_code(name: str) -> str:
    """从目录名里取语言代码：``语言包EN`` → ``EN``。"""
    text = str(name or "")
    if text.startswith(PACK_PREFIX):
        text = text[len(PACK_PREFIX):]
    return text.strip() or text


def scan_packs(root: str | Path = ".") -> list[LanguagePack]:
    """扫描根目录下所有 ``语言包<代码>`` 目录。"""
    base = Path(root)
    if not base.is_dir():
        return []
    packs = []
    for folder in sorted(base.iterdir()):
        if not folder.is_dir() or not folder.name.startswith(PACK_PREFIX):
            continue
        files = []
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(folder).as_posix()
            try:
                member = normalize_member(relative)
            except LangPackError:
                continue
            if is_allowed(member):
                files.append(member)
        packs.append(LanguagePack(path=folder, code=pack_code(folder.name), files=tuple(files)))
    return packs


@dataclass
class ApplyResult:
    ok: bool = False
    message: str = ""
    pack: str = ""
    applied: list[str] = field(default_factory=list)
    backup_dir: Path | None = None

    def summary(self) -> str:
        if not self.ok:
            return f"应用失败：{self.message}"
        backup = f"，原文件已备份到 {self.backup_dir}" if self.backup_dir else ""
        return f"已应用语言包 {self.pack}：{len(self.applied)} 个文件{backup}"


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def _backup_targets(target_root: Path, backup_root: Path, stamp: str) -> Path | None:
    """备份 i18n/ 与 assets/lang/；两个都不存在时返回 None。"""
    existing = [target_root / prefix.rstrip("/") for prefix in ALLOWED_PREFIXES]
    existing = [path for path in existing if path.is_dir()]
    if not existing:
        return None
    backup_dir = backup_root / f"{BACKUP_PREFIX}{stamp}"
    index = 0
    while backup_dir.exists():
        index += 1
        backup_dir = backup_root / f"{BACKUP_PREFIX}{stamp}_{index}"
    for source in existing:
        relative = source.relative_to(target_root)
        shutil.copytree(source, backup_dir / relative)
    return backup_dir


def apply_pack(
    pack: str | Path,
    target_root: str | Path = ".",
    backup_root: str | Path | None = None,
) -> ApplyResult:
    """应用语言包：备份 → 覆盖允许的前缀。"""
    pack_path = Path(pack)
    target = Path(target_root)
    if not pack_path.is_dir():
        return ApplyResult(ok=False, message=f"语言包目录不存在: {pack_path}", pack=pack_path.name)

    entries: list[str] = []
    for path in sorted(pack_path.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(pack_path).as_posix()
        try:
            member = normalize_member(relative)
        except LangPackError as exc:
            return ApplyResult(ok=False, message=str(exc), pack=pack_path.name)
        if not is_allowed(member):
            return ApplyResult(
                ok=False,
                message=f"语言包里有不允许的路径：{member}（只允许 {', '.join(ALLOWED_PREFIXES)}）",
                pack=pack_path.name,
            )
        entries.append(member)

    if not entries:
        return ApplyResult(ok=False, message="语言包里没有任何可用文件", pack=pack_path.name)

    backup_dir = _backup_targets(target, Path(backup_root) if backup_root else BACKUP_ROOT, _timestamp())
    applied: list[str] = []
    for member in entries:
        source = pack_path / member
        destination = target / member
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source, tmp)
        os.replace(tmp, destination)
        applied.append(member)
    return ApplyResult(ok=True, message="", pack=pack_path.name, applied=applied, backup_dir=backup_dir)


def list_backups(backup_root: str | Path | None = None) -> list[Path]:
    root = Path(backup_root) if backup_root else BACKUP_ROOT
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.startswith(BACKUP_PREFIX)),
        reverse=True,
    )


def restore_backup(
    backup_dir: str | Path,
    target_root: str | Path = ".",
    backup_root: str | Path | None = None,
) -> ApplyResult:
    """从备份还原（还原前也先备份当前状态）。"""
    source_dir = Path(backup_dir)
    target = Path(target_root)
    if not source_dir.is_dir():
        return ApplyResult(ok=False, message=f"备份目录不存在: {source_dir}")

    entries: list[str] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        try:
            member = normalize_member(relative)
        except LangPackError as exc:
            return ApplyResult(ok=False, message=str(exc))
        if not is_allowed(member):
            continue
        entries.append(member)
    if not entries:
        return ApplyResult(ok=False, message="备份里没有可还原的文件")

    new_backup = _backup_targets(target, Path(backup_root) if backup_root else BACKUP_ROOT, _timestamp())
    restored: list[str] = []
    for member in entries:
        destination = target / member
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copy2(source_dir / member, tmp)
        os.replace(tmp, destination)
        restored.append(member)
    return ApplyResult(
        ok=True,
        message="",
        pack=source_dir.name,
        applied=restored,
        backup_dir=new_backup,
    )
