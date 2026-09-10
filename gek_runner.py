# -*- coding: utf-8 -*-

import os
import sys
import importlib.util
import traceback


CONVERTER_NAMES = (
    "jp.py",
    "gek.py",
    "converter.py",
)


def reconfigure_stdio():
    for name in ("stdout", "stderr", "stdin"):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def find_converter(start_dir: str):
    current = os.path.abspath(start_dir)

    while True:
        for name in CONVERTER_NAMES:
            path = os.path.join(current, name)
            if os.path.isfile(path):
                return path

        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    here = os.path.dirname(os.path.abspath(__file__))
    for name in CONVERTER_NAMES:
        path = os.path.join(here, name)
        if os.path.isfile(path):
            return path
            
    # PyInstaller で凍結したときの同梱変換器
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        for name in CONVERTER_NAMES:
            path = os.path.join(meipass, name)
            if os.path.isfile(path):
                return path
    
    return None


def load_converter(path: str):
    spec = importlib.util.spec_from_file_location("gek_converter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compute_pause(converter, source: str) -> bool:
    """
    設定.待機(止める)   → True
    設定.待機(止めない) → False
    指定なし           → ダブルクリックなら True / コマンド(gecko)なら False
    """
    cli = os.environ.get("GECKO_CLI") == "1"

    try:
        norm = converter.normalize_spaces(source)
        mode, pause = converter.scan_settings(norm)
    except SyntaxError:
        return not cli

    if pause is None:
        return not cli

    return pause


def pause_if_needed(enabled: bool):
    if not enabled:
        return

    try:
        print()
        input("押すと終了します...")
    except Exception:
        pass


def main():
    reconfigure_stdio()

    if len(sys.argv) < 2:
        print("このアプリは .gek ファイルをダブルクリックして使います。")
        print("使い方: gek_runner.py <file.gek>")

        try:
            input("押すと終了します...")
        except Exception:
            pass

        return 1

    target = os.path.abspath(sys.argv[1])

    if not os.path.isfile(target):
        print(f"ファイルが見つかりません: {target}")

        try:
            input("押すと終了します...")
        except Exception:
            pass

        return 1

    try:
        with open(target, encoding="utf-8-sig") as f:
            source = f.read()
    except Exception as e:
        print(f"ファイルを開けませんでした: {e}")

        try:
            input("押すと終了します...")
        except Exception:
            pass

        return 1

    converter_path = find_converter(os.path.dirname(target))

    if not converter_path:
        print("変換器が見つかりません。")
        print("jp.py / gek.py / converter.py を .gek ファイルの近くかランチャーのフォルダに置いてください。")
        pause_if_needed(True)
        return 1

    try:
        converter = load_converter(converter_path)
    except Exception:
        print("変換器の読み込み中にエラーが起きました。")
        traceback.print_exc()
        pause_if_needed(True)
        return 1

    if not hasattr(converter, "run_source"):
        print("変換器に run_source 関数が必要です。")
        pause_if_needed(True)
        return 1

    pause = compute_pause(converter, source)

    sys.argv = [target] + sys.argv[2:]

    exit_code = 0

    try:
        converter.run_source(
            source,
            filename=target,
            debug=False,
        )

    except SystemExit as e:
        try:
            exit_code = int(e.code)
        except Exception:
            exit_code = 0

    except SyntaxError as e:
        print("構文エラーが起きました。")
        print(f"ファイル: {getattr(e, 'filename', None) or target}")
        print(f"行番号: {getattr(e, 'lineno', '?')}")
        print(f"内容: {getattr(e, 'msg', str(e))}")

        text = getattr(e, "text", None)
        if text:
            print()
            print(text.rstrip())

            offset = getattr(e, "offset", None)
            if offset:
                print(" " * max(0, offset - 1) + "^")

        exit_code = 1

    except Exception:
        traceback.print_exc()
        exit_code = 1

    finally:
        pause_if_needed(pause)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
