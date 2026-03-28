import importlib
import os
import pathlib
import sys
import tempfile


def main() -> None:
    project_root = pathlib.Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="yourshiguan-smoke-") as temp_dir:
        os.environ["CODEX_REGISTER_DATA_DIR"] = temp_dir
        sys.path.insert(0, str(project_root))
        module = importlib.import_module("yourshiguan_register")

        expected_root = pathlib.Path(temp_dir).resolve()
        assert pathlib.Path(module.APP_OUTPUT_DIR).resolve() == expected_root
        assert pathlib.Path(module.ACCOUNTS_DIR).resolve() == expected_root / "accounts"
        assert pathlib.Path(module.TOKEN_JSON_DIR).resolve() == expected_root / "codex_tokens"
        assert pathlib.Path(module.AK_FILE).resolve() == expected_root / "ak.txt"
        assert pathlib.Path(module.RK_FILE).resolve() == expected_root / "rk.txt"
        assert module._as_bool("true") is True
        assert module._as_bool("0") is False

    print("Smoke test passed.")


if __name__ == "__main__":
    main()
