from pathlib import Path

from file_transfer.config import load_config


def test_load_config_creates_dict_correctly(test_config: Path) -> None:
    # given & when
    config = load_config(test_config)

    # then
    assert isinstance(config, dict)
    tmp_dir = test_config.parent  # This is tmp_path
    assert config["source_dir"] == str(tmp_dir / "source")
    assert config["dest_dir"] == str(tmp_dir / "dest")
    assert config["transferred_dir"] == str(tmp_dir / "transferred")
    assert config["log_file"] == str(tmp_dir / "log.log")
    assert config["valid_extensions"] == [".mp3", ".wav"]
    assert config["ignored_files"] == [".DS_Store"]
    assert config["debug"] is True
