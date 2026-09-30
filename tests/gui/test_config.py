"""`gui.config`：配置文件的读写。

不做 UI、不碰 customtkinter，所以不需要 mock Tk 就能测。
"""

from simple_ebook_converter.gui import config


def test_load_missing_file_is_empty(tmp_path):
    assert config.load(tmp_path) == {}


def test_load_corrupt_json_is_empty(tmp_path):
    (tmp_path / config.FILENAME).write_text("{ not json", encoding="utf-8")
    assert config.load(tmp_path) == {}


def test_load_non_object_is_empty(tmp_path):
    (tmp_path / config.FILENAME).write_text("[1, 2]", encoding="utf-8")
    assert config.load(tmp_path) == {}


def test_load_non_utf8_is_empty(tmp_path):
    """用户手改文件存成别的编码时，不该让启动崩掉。"""
    (tmp_path / config.FILENAME).write_bytes(b"\xff\xfe bad bytes")
    assert config.load(tmp_path) == {}


def test_roundtrip(tmp_path):
    data = {"indent": "3", "volume_align": "center", "replacements": []}
    config.save(tmp_path, data)
    assert config.load(tmp_path) == data


def test_save_creates_dir_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "sub"
    config.save(target, {"indent": 2})
    assert (target / config.FILENAME).is_file()
    assert list(target.glob("*.tmp")) == []


def test_default_dir_ends_with_config_name():
    assert config.default_dir().name == config.DIR_NAME
