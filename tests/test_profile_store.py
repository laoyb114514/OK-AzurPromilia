"""配置档测试：快照、应用前备份、不删除档外文件、名字校验。"""

import json
import tempfile
import unittest
from pathlib import Path

from src.core.profile_store import PROFILES_FOLDER, ProfileError, ProfileStore


def write(path: Path, payload: dict | str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class ProfileTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.configs = Path(self._tmp.name) / "configs"
        self.configs.mkdir(parents=True)
        write(self.configs / "DailyTask.json", {"多账户模式": True})
        write(self.configs / "queues" / "早上.json", {"name": "早上", "items": []})
        self.store = ProfileStore(self.configs)

    def tearDown(self):
        self._tmp.cleanup()


class TestSaveList(ProfileTestBase):
    def test_save_snapshots_all_config_files(self):
        info = self.store.save("工作")
        self.assertEqual(info.files, 2)
        self.assertTrue((self.configs / PROFILES_FOLDER / "工作" / "profile.json").is_file())
        snapshot = self.configs / PROFILES_FOLDER / "工作" / "files" / "queues" / "早上.json"
        self.assertTrue(snapshot.is_file())

    def test_profiles_are_not_snapshotted_into_themselves(self):
        self.store.save("工作")
        self.store.save("工作")
        meta = json.loads((self.configs / PROFILES_FOLDER / "工作" / "profile.json").read_text(encoding="utf-8"))
        self.assertFalse(any(path.startswith(PROFILES_FOLDER) for path in meta["files"]))

    def test_list(self):
        self.store.save("工作")
        self.store.save("娱乐")
        names = [info.name for info in self.store.list()]
        self.assertEqual(names, ["娱乐", "工作"])

    def test_list_ignores_corrupt_meta(self):
        self.store.save("工作")
        broken = self.configs / PROFILES_FOLDER / "坏的"
        broken.mkdir(parents=True)
        (broken / "profile.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual([info.name for info in self.store.list()], ["工作"])

    def test_exists(self):
        self.store.save("工作")
        self.assertTrue(self.store.exists("工作"))
        self.assertFalse(self.store.exists("不存在"))

    def test_overwrite_flag(self):
        self.store.save("工作")
        with self.assertRaises(ProfileError):
            self.store.save("工作", overwrite=False)

    def test_invalid_names(self):
        for name in ("", "  ", "../evil", "a/b", "a\\b", ".hidden"):
            with self.subTest(name=name), self.assertRaises(ProfileError):
                self.store.save(name)

    def test_saved_label(self):
        info = self.store.save("工作")
        self.assertIn("工作", info.label())
        self.assertIn("2 个文件", info.label())


class TestApply(ProfileTestBase):
    def test_apply_restores_files(self):
        self.store.save("工作")
        write(self.configs / "DailyTask.json", {"多账户模式": False})
        result = self.store.apply("工作")

        self.assertEqual((self.configs / "DailyTask.json").read_text(encoding="utf-8"), '{"多账户模式": true}')
        self.assertEqual(len(result.restored), 2)
        self.assertIn("已应用", result.summary())

    def test_apply_backs_up_current_files(self):
        self.store.save("工作")
        write(self.configs / "DailyTask.json", {"多账户模式": False})
        result = self.store.apply("工作")

        self.assertIsNotNone(result.backup_dir)
        self.assertTrue(result.backup_dir.name.startswith(".backup_"))
        backup = result.backup_dir / "DailyTask.json"
        self.assertIn("false", backup.read_text(encoding="utf-8"))

    def test_apply_does_not_delete_extra_files(self):
        self.store.save("工作")
        write(self.configs / "NewTask.json", {"键": 1})
        result = self.store.apply("工作")
        self.assertTrue((self.configs / "NewTask.json").exists())
        self.assertEqual(result.extra, 1)
        self.assertIn("未删除", result.summary())

    def test_apply_missing_profile(self):
        with self.assertRaises(ProfileError):
            self.store.apply("不存在")

    def test_apply_skips_missing_snapshot_files(self):
        self.store.save("工作")
        snapshot = self.configs / PROFILES_FOLDER / "工作" / "files" / "DailyTask.json"
        snapshot.unlink()
        result = self.store.apply("工作")
        self.assertNotIn("DailyTask.json", result.restored)

    def test_backup_dirs_are_not_listed_as_profiles(self):
        self.store.save("工作")
        self.store.apply("工作")
        names = [info.name for info in self.store.list()]
        self.assertEqual(names, ["工作"])

    def test_repeated_apply_uses_distinct_backup_dirs(self):
        self.store.save("工作")
        first = self.store.apply("工作")
        second = self.store.apply("工作")
        self.assertNotEqual(first.backup_dir, second.backup_dir)


class TestDelete(ProfileTestBase):
    def test_delete(self):
        self.store.save("工作")
        self.assertTrue(self.store.delete("工作"))
        self.assertEqual(self.store.list(), [])

    def test_delete_missing(self):
        self.assertFalse(self.store.delete("不存在"))


class TestEdgeCases(unittest.TestCase):
    def test_empty_config_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProfileStore(Path(tmp) / "configs")
            info = store.save("空档")
            self.assertEqual(info.files, 0)
            result = store.apply("空档")
            self.assertEqual(result.restored, [])
            self.assertIsNone(result.backup_dir)


if __name__ == "__main__":
    unittest.main()
