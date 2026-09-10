# -*- coding: utf-8 -*-

import io
import os
import re
import sys
import tokenize


# =========================================================
# 設定
# =========================================================

# 裸の日本語単語を自動で文字列として扱うかどうか。
AUTO_STRING_BARE_JAPANESE = False

# カウントモード: "0" / "1" / "1all"
COUNT_MODE = "0"          # 変換時(コード生成)用
CURRENT_COUNT_MODE = "0"  # 実行時(ランタイム関数)用


# =========================================================
# 設定行のパース
# =========================================================

LP = "[（(]"
RP = "[)）]"

RE_WAIT = re.compile(
    r"^設定\s*\.\s*待機\s*" + LP + r"\s*(止める|止めない)\s*" + RP + r"$"
)

RE_COUNT = re.compile(
    r"^設定\s*\.\s*カウント\s*" + LP
    + r"\s*(0|1|0から|1から)\s*(?:[,\uFF0C]\s*(全部)\s*)?\s*" + RP + r"$"
)


def scan_settings(source: str):
    """
    ファイル先頭の設定行を読む。
    戻り値: (count_mode, pause)
      pause は None なら「指定なし」。
    設定が先頭以外にあれば SyntaxError。
    """
    mode = "0"
    pause = None
    seen_code = False

    for lineno, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if line.startswith("設定"):
            if seen_code:
                raise SyntaxError(
                    "設定はファイルの先頭に書いてください",
                    (None, lineno, 1, line),
                )

            m_wait = RE_WAIT.match(line)
            if m_wait:
                pause = (m_wait.group(1) == "止める")
                continue

            m_count = RE_COUNT.match(line)
            if m_count:
                base = m_count.group(1)
                zenbu = (m_count.group(2) == "全部")

                if base in ("0", "0から"):
                    mode = "0"
                else:
                    mode = "1all" if zenbu else "1"
                continue

            raise SyntaxError(
                f"未知の設定です: {line}",
                (None, lineno, 1, line),
            )

        seen_code = True

    return mode, pause


# =========================================================
# 全角スペースを半角スペースに正規化する
# ただし文字列の中とコメントの中はそのままにする
# =========================================================

def normalize_spaces(source: str) -> str:
    out = []
    in_string = None
    escape = False
    in_comment = False

    for ch in source:
        if in_comment:
            out.append(ch)
            if ch == "\n":
                in_comment = False
            continue

        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
            continue

        if ch in ("\"", "'"):
            in_string = ch
            out.append(ch)
        elif ch == "#":
            in_comment = True
            out.append(ch)
        elif ch == "　":
            out.append(" ")
        else:
            out.append(ch)

    return "".join(out)


# =========================================================
# 日本語 → Python 変換テーブル
# =========================================================

CONST_MAP = {
    "真": "True",
    "偽": "False",
    "なし": "None",
}

FUNC_MAP = {
    "表示する": "print",
    "表示": "print",
    "入力": "input",
    "入力する": "input",
    "長さ": "len",
    "整数": "int",
    "実数": "float",
    "文字列": "str",
    "開く": "open",
}

LOGIC_MAP = {
    "そして": "and",
    "かつ": "and",
    "または": "or",
    "でない": "not",
}

KEYWORD_MAP = {
    "関数": "def",
    "クラス": "class",
    "戻り値": "return",
    "繰り返し": "for",
    "ながら": "while",
    "読み込む": "import",
    "として": "as",

    # 制御構文パック
    "抜ける": "break",
    "続ける": "continue",
    "何もしない": "pass",
    "試す": "try",
    "捕まえる": "except",
    "最終": "finally",
    "一緒に": "with",

    # 例外クラスの日本語別名
    "値エラー": "ValueError",
    "型エラー": "TypeError",
    "零除算エラー": "ZeroDivisionError",
    "ファイルエラー": "FileNotFoundError",
    "インデックスエラー": "IndexError",
    "キーエラー": "KeyError",

    **CONST_MAP,
    **LOGIC_MAP,
}

EXPR_NAME_MAP = {
    **CONST_MAP,
    **FUNC_MAP,
    **LOGIC_MAP,
}

COMP_MAP = {
    "以上": ">=",
    "以下": "<=",
    "超": ">",
    "未満": "<",
    "より大きい": ">",
    "より小さい": "<",
    "等しい": "==",
    "等しくない": "!=",
    "と等しい": "==",
    "と等しくない": "!=",
    "大きい": ">",
    "小さい": "<",
    "ではない": "!=",
    "じゃない": "!=",
}

# 左右を入れ替える包含演算子
# A が B を含む → B in A
SWAP_COMP = {
    "を含む": "in",
    "を含まない": "not in",
}

ELSE_WORDS = {
    "でなければ",
    "それ以外",
    "違えば",
}

ELIF_CONTIGUOUS = {
    "ではなくて",
    "ではなく",
    "それ以外もし",
    "違えばもし",
    "でなければもし",
    "もしでなければ",
    "もし違えば",
}

ELIF_STARTERS = {
    "ではなくて",
    "ではなく",
    "それ以外",
    "それ以外で",
    "違えば",
    "でなければ",
}

RESERVED_LINE_START = {
    "もし",
    "関数",
    "クラス",
    "戻り値",
    "繰り返し",
    "ながら",
    "読み込む",
    "ループ",
    "設定",
} | ELSE_WORDS | ELIF_CONTIGUOUS | ELIF_STARTERS

# 助詞など「識別子ではない」日本語トークン
PARTICLE_WORDS = {
    "は", "を", "が", "に", "へ", "と",
    "から", "より", "まで", "なら", "しか", "や",
}

NON_IDENTIFIER_WORDS = (
    PARTICLE_WORDS
    | set(KEYWORD_MAP)
    | set(FUNC_MAP)
    | set(COMP_MAP)
    | set(SWAP_COMP)
    | ELSE_WORDS
    | ELIF_CONTIGUOUS
    | ELIF_STARTERS
    | {"変数", "設定", "ループ", "もし", "繰り返し", "ながら"}
)

SKIP_TYPES = {
    tokenize.NEWLINE,
    tokenize.NL,
    tokenize.INDENT,
    tokenize.DEDENT,
    tokenize.COMMENT,
    tokenize.ENCODING,
    tokenize.ENDMARKER,
}


# =========================================================
# 日本語っぽいかどうかの簡易判定
# =========================================================

def looks_japanese(s: str) -> bool:
    for ch in s:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x30FF
            or 0x3400 <= cp <= 0x4DBF
            or 0x4E00 <= cp <= 0x9FFF
        ):
            return True
    return False


# =========================================================
# トークンを式として組み立てる
# =========================================================

def map_expr_token(tok):
    if tok.type == tokenize.NAME and tok.string in EXPR_NAME_MAP:
        return (tok.type, EXPR_NAME_MAP[tok.string])
    return (tok.type, tok.string)


def expr_of(tokens):
    if not tokens:
        return ""
    return tokenize.untokenize([map_expr_token(t) for t in tokens]).strip()


def value_expr(tokens):
    if not tokens:
        return "None"

    while tokens and tokens[-1].type == tokenize.OP and tokens[-1].string == ":":
        tokens = tokens[:-1]

    if (
        len(tokens) >= 2
        and tokens[0].type == tokenize.NAME
        and tokens[0].string == "変数"
    ):
        return expr_of(tokens[1:])

    if (
        AUTO_STRING_BARE_JAPANESE
        and len(tokens) == 1
        and tokens[0].type == tokenize.NAME
    ):
        s = tokens[0].string

        if s in CONST_MAP:
            return CONST_MAP[s]

        if looks_japanese(s):
            return repr(s)

    return expr_of(tokens)


# =========================================================
# 比較表現を探す
# =========================================================

def find_comparison(tokens):
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME:
            continue

        if tok.string == "より" and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.type == tokenize.NAME and nxt.string == "大きい":
                return (i, i + 1), ">"
            if nxt.type == tokenize.NAME and nxt.string == "小さい":
                return (i, i + 1), "<"

        if tok.string == "と" and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.type == tokenize.NAME and nxt.string == "等しい":
                return (i, i + 1), "=="
            if nxt.type == tokenize.NAME and nxt.string == "等しくない":
                return (i, i + 1), "!="

        if tok.string in ("では", "じゃ") and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt.type == tokenize.NAME and nxt.string == "ない":
                return (i, i + 1), "!="

        if tok.string in SWAP_COMP:
            return (i,), "SWAP:" + SWAP_COMP[tok.string]

        if tok.string in COMP_MAP:
            return (i,), COMP_MAP[tok.string]

    return None, None


def split_tokens_by(tokens, word):
    segments = []
    current = []

    for tok in tokens:
        if tok.type == tokenize.NAME and tok.string == word:
            segments.append(current)
            current = []
        else:
            current.append(tok)

    segments.append(current)

    return [seg for seg in segments if seg]


# =========================================================
# 1つの条件を作る
# =========================================================

def build_single_condition(tokens, carried_left=None):
    while tokens and tokens[-1].type == tokenize.OP and tokens[-1].string == ":":
        tokens = tokens[:-1]

    comp_indices, op = find_comparison(tokens)

    swap = False
    if op is not None and op.startswith("SWAP:"):
        swap = True
        op = op[5:]

    ga_idx = None
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.NAME and tok.string == "が":
            ga_idx = i
            break

    if ga_idx is not None:
        comp_set = set(comp_indices) if comp_indices else set()

        left = [
            t for i, t in enumerate(tokens)
            if i < ga_idx and i not in comp_set
        ]
        right = [
            t for i, t in enumerate(tokens)
            if i > ga_idx and i not in comp_set
        ]

        left_s = expr_of(left)
        right_s = value_expr(right)

        if op is None:
            op = "=="

        if swap:
            return f"{right_s} {op} {left_s}", left_s

        return f"{left_s} {op} {right_s}", left_s

    if comp_indices:
        comp_set = set(comp_indices)
        last_comp = max(comp_indices)
        rest = [t for i, t in enumerate(tokens) if i not in comp_set]

        if last_comp == len(tokens) - 1 and rest:
            rest_s = value_expr(rest)

            if carried_left:
                if swap:
                    return f"{rest_s} {op} {carried_left}", carried_left

                return f"{carried_left} {op} {rest_s}", carried_left

            return rest_s, None

        new_tokens = []
        inserted = False

        for i, tok in enumerate(tokens):
            if i in comp_set:
                if not inserted:
                    new_tokens.append((tokenize.OP, op))
                    inserted = True
                continue

            new_tokens.append(map_expr_token(tok))

        return tokenize.untokenize(new_tokens).strip(), None

    return expr_of(tokens), None


def build_condition(tokens):
    while tokens and tokens[-1].type == tokenize.OP and tokens[-1].string == ":":
        tokens = tokens[:-1]

    or_segments = split_tokens_by(tokens, "または")
    or_parts = []

    for or_seg in or_segments:
        and_segments = split_tokens_by(or_seg, "かつ")

        carried = None
        and_parts = []

        for seg in and_segments:
            expr, left_s = build_single_condition(seg, carried)

            if left_s:
                carried = left_s

            and_parts.append(expr)

        or_parts.append(" and ".join(and_parts))

    if not or_parts:
        return "True"

    return " or ".join(or_parts)


# =========================================================
# if / elif / while / for
# =========================================================

def build_if(indent, tokens, comment):
    nara_indices = [
        i for i, tok in enumerate(tokens)
        if tok.type == tokenize.NAME and tok.string == "なら"
    ]

    if nara_indices:
        cond_tokens = tokens[1:nara_indices[-1]]
    else:
        cond_tokens = tokens[1:]

    expr = build_condition(cond_tokens)
    line = f"{indent}if {expr}:"

    if comment:
        line += "  " + comment

    return line


def build_elif(indent, tokens, comment, start_idx=1):
    nara_indices = [
        i for i, tok in enumerate(tokens)
        if tok.type == tokenize.NAME and tok.string == "なら"
    ]

    if nara_indices:
        cond_tokens = tokens[start_idx:nara_indices[-1]]
    else:
        cond_tokens = tokens[start_idx:]

    expr = build_condition(cond_tokens)
    line = f"{indent}elif {expr}:"

    if comment:
        line += "  " + comment

    return line


def build_while(indent, tokens, comment):
    nara_indices = [
        i for i, tok in enumerate(tokens)
        if tok.type == tokenize.NAME and tok.string == "なら"
    ]

    if nara_indices:
        cond_tokens = tokens[1:nara_indices[-1]]
    else:
        cond_tokens = tokens[1:]

    expr = build_condition(cond_tokens)
    line = f"{indent}while {expr}:"

    if comment:
        line += "  " + comment

    return line


def build_for(indent, tokens, comment):
    wo_idx = None
    for i, tok in enumerate(tokens):
        if tok.type == tokenize.NAME and tok.string == "を":
            wo_idx = i
            break

    if wo_idx is None:
        return simple_map_line(indent, tokens, comment)

    var_tokens = tokens[1:wo_idx]
    iter_tokens = tokens[wo_idx + 1:]

    while iter_tokens and iter_tokens[-1].type == tokenize.OP and iter_tokens[-1].string == ":":
        iter_tokens = iter_tokens[:-1]

    # 「i と 商品」→「i, 商品」
    var_mapped = []
    for tok in var_tokens:
        if tok.type == tokenize.NAME and tok.string == "と":
            var_mapped.append((tokenize.OP, ","))
        else:
            var_mapped.append(map_expr_token(tok))
    var_s = tokenize.untokenize(var_mapped).strip()

    kara_idx = None
    made_idx = None
    for i, tok in enumerate(iter_tokens):
        if tok.type == tokenize.NAME and tok.string == "から":
            kara_idx = i
        if tok.type == tokenize.NAME and tok.string == "まで":
            made_idx = i

    if (
        kara_idx is not None
        and made_idx is not None
        and made_idx == len(iter_tokens) - 1
        and kara_idx >= 1
    ):
        no_idx = None
        for i, tok in enumerate(iter_tokens[:kara_idx]):
            if tok.type == tokenize.NAME and tok.string == "の":
                no_idx = i
                break

        if no_idx is not None and no_idx >= 1 and kara_idx >= no_idx + 2:
            base_s = expr_of(iter_tokens[:no_idx])
            a_s = expr_of(iter_tokens[no_idx + 1:kara_idx])
            b_s = expr_of(iter_tokens[kara_idx + 1:made_idx])

            if COUNT_MODE == "0":
                iter_s = f"{base_s}[{a_s}:{b_s} + 1]"
            else:
                iter_s = f"{base_s}[{a_s} - 1:{b_s}]"
        else:
            a_s = expr_of(iter_tokens[:kara_idx])
            b_s = expr_of(iter_tokens[kara_idx + 1:made_idx])
            iter_s = f"range({a_s}, {b_s} + 1)"
    else:
        iter_s = expr_of(iter_tokens)

    line = f"{indent}for {var_s} in {iter_s}:"

    if comment:
        line += "  " + comment

    return line


# =========================================================
# 代入 / 通常行
# =========================================================

def build_assign(indent, tokens, comment):
    name = tokens[0].string
    value_tokens = tokens[2:]
    expr = value_expr(value_tokens)

    line = f"{indent}{name} = {expr}"

    if comment:
        line += "  " + comment

    return line


def simple_map_line(indent, tokens, comment):
    mapped = []

    for tok in tokens:
        if tok.type == tokenize.NAME:
            if tok.string in KEYWORD_MAP:
                mapped.append((tok.type, KEYWORD_MAP[tok.string]))
                continue

            if tok.string in FUNC_MAP:
                mapped.append((tok.type, FUNC_MAP[tok.string]))
                continue

        mapped.append((tok.type, tok.string))

    text = tokenize.untokenize(mapped).strip()
    line = indent + text

    if comment:
        line += "  " + comment

    return line


# =========================================================
# 全部モード用の添字シフト
# リスト[i]   → リスト[(i) - 1]
# リスト[a:b] → リスト[(a) - 1:(b)]
# =========================================================

def _fab(typ, s):
    return tokenize.TokenInfo(typ, s, (0, 0), (0, 0), "")


def shift_subscripts(tokens):
    out = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        if tok.type == tokenize.OP and tok.string == "[":
            prev = out[-1] if out else None

            if prev is None:
                is_sub = False
            elif prev.type == tokenize.OP:
                is_sub = prev.string in (")", "]")
            elif prev.type == tokenize.NAME:
                # 「は [ ... 」のようなリストリテラルを添字と誤認しない
                is_sub = prev.string not in NON_IDENTIFIER_WORDS
            else:
                is_sub = False

            if not is_sub:
                out.append(tok)
                i += 1
                continue

            depth = 0
            j = i
            while j < n:
                if tokens[j].type == tokenize.OP and tokens[j].string in ("[", "(", "{"):
                    depth += 1
                elif tokens[j].type == tokenize.OP and tokens[j].string in ("]", ")", "}"):
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            close = j

            inner = tokens[i + 1:close]

            colon_idx = None
            d = 0
            for k, t in enumerate(inner):
                if t.type == tokenize.OP and t.string in ("[", "(", "{"):
                    d += 1
                elif t.type == tokenize.OP and t.string in ("]", ")", "}"):
                    d -= 1
                elif t.type == tokenize.OP and t.string == ":" and d == 0:
                    colon_idx = k
                    break

            new = [tok]

            if colon_idx is None:
                if inner:
                    new.append(_fab(tokenize.OP, "("))
                    new.extend(inner)
                    new.append(_fab(tokenize.OP, ")"))
                    new.append(_fab(tokenize.OP, "-"))
                    new.append(_fab(tokenize.NUMBER, "1"))
            else:
                a = inner[:colon_idx]
                b = inner[colon_idx + 1:]

                if a:
                    new.append(_fab(tokenize.OP, "("))
                    new.extend(a)
                    new.append(_fab(tokenize.OP, ")"))
                    new.append(_fab(tokenize.OP, "-"))
                    new.append(_fab(tokenize.NUMBER, "1"))

                new.append(_fab(tokenize.OP, ":"))

                if b:
                    new.append(_fab(tokenize.OP, "("))
                    new.extend(b)
                    new.append(_fab(tokenize.OP, ")"))

            if close < n:
                new.append(tokens[close])

            out.extend(new)
            i = close + 1
            continue

        out.append(tok)
        i += 1

    return out


# =========================================================
# 1行を変換する
# =========================================================

def convert_line(raw_line):
    indent = raw_line[:len(raw_line) - len(raw_line.lstrip())]
    stripped = raw_line.strip()

    if not stripped or stripped.startswith("#"):
        return raw_line

    try:
        toks = list(tokenize.generate_tokens(io.StringIO(stripped + "\n").readline))
    except (tokenize.TokenError, SyntaxError):
        return raw_line

    comment = ""
    meaningful = []

    for tok in toks:
        if tok.type == tokenize.COMMENT:
            comment = tok.string
            continue

        if tok.type in SKIP_TYPES:
            continue

        meaningful.append(tok)

    if not meaningful:
        return raw_line

    # 全部モードなら生の添字をシフト
    if COUNT_MODE == "1all":
        meaningful = shift_subscripts(meaningful)

    first = meaningful[0]

    # ---------------------------------------------------
    # elif / else
    # ---------------------------------------------------
    if first.type == tokenize.NAME:
        elif_start_idx = None

        if first.string in ELIF_CONTIGUOUS:
            elif_start_idx = 1

        if (
            len(meaningful) >= 2
            and meaningful[1].type == tokenize.NAME
            and meaningful[1].string == "もし"
            and (
                first.string in ELIF_STARTERS
                or first.string in ELIF_CONTIGUOUS
            )
        ):
            elif_start_idx = 2

        if elif_start_idx is not None:
            return build_elif(indent, meaningful, comment, start_idx=elif_start_idx)

        if first.string in ELSE_WORDS:
            line = indent + "else:"
            if comment:
                line += "  " + comment
            return line

    # ---------------------------------------------------
    # ループ → while True:
    # ---------------------------------------------------
    if first.type == tokenize.NAME and first.string == "ループ":
        line = indent + "while True:"
        if comment:
            line += "  " + comment
        return line

    # ---------------------------------------------------
    # if / while / for
    # ---------------------------------------------------
    if first.type == tokenize.NAME and first.string == "もし":
        return build_if(indent, meaningful, comment)

    if first.type == tokenize.NAME and first.string == "ながら":
        return build_while(indent, meaningful, comment)

    if first.type == tokenize.NAME and first.string == "繰り返し":
        return build_for(indent, meaningful, comment)

    # ---------------------------------------------------
    # 代入
    # ---------------------------------------------------
    if (
        len(meaningful) >= 3
        and meaningful[0].type == tokenize.NAME
        and meaningful[1].type == tokenize.NAME
        and meaningful[1].string == "は"
        and meaningful[0].string not in RESERVED_LINE_START
    ):
        return build_assign(indent, meaningful, comment)

    return simple_map_line(indent, meaningful, comment)


# =========================================================
# ソース全体を変換する
# =========================================================

def transpile(source: str) -> str:
    global COUNT_MODE

    source = normalize_spaces(source)

    mode, pause = scan_settings(source)
    COUNT_MODE = mode

    lines = source.splitlines()
    converted = []

    for line in lines:
        # 設定行は空行にして行番号を保つ
        if line.strip().startswith("設定"):
            converted.append("")
            continue

        converted.append(convert_line(line))

    result = "\n".join(converted)

    if source.endswith("\n"):
        result += "\n"

    return result


# =========================================================
# ランタイム: モード対応ヘルパー
# =========================================================

def _is1():
    return CURRENT_COUNT_MODE in ("1", "1all")


def 範囲(*args):
    if len(args) == 1:
        n = args[0]
        if _is1():
            return range(1, n + 1)
        return range(n)

    a, b = args[0], args[1]
    if _is1():
        return range(a, b + 1)
    return range(a, b)


def 列挙(lst):
    start = 1 if _is1() else 0
    return enumerate(lst, start)


def 追加(lst, value):
    lst.append(value)


def 挿入(lst, index, value):
    if _is1():
        index = index - 1
    lst.insert(index, value)


def 消す(lst, value):
    lst.remove(value)


def 取り出す(lst, index=None):
    if index is None:
        return lst.pop()
    if _is1():
        index = index - 1
    return lst.pop(index)


def 並び替え(lst):
    lst.sort()


def 逆順(lst):
    lst.reverse()


def 何番目(lst, value):
    i = lst.index(value)
    if _is1():
        return i + 1
    return i


def 部分(lst, a, b):
    if _is1():
        return lst[a - 1:b]
    return lst[a:b + 1]


def 拡張(lst, other):
    lst.extend(other)


def 結合(lst, sep=""):
    return sep.join(lst)


def 最大(lst):
    return max(lst)


def 最小(lst):
    return min(lst)


def 合計(lst):
    return sum(lst)


# =========================================================
# 実行
# =========================================================

def run_source(source: str, filename="<日本語コード>", debug: bool = False):
    global CURRENT_COUNT_MODE

    norm = normalize_spaces(source)
    mode, pause = scan_settings(norm)
    CURRENT_COUNT_MODE = mode

    py = transpile(source)

    if debug:
        print("--- 変換後の Python コード ---")
        print(py)
        print("--- 実行結果 ---")

    code = compile(py, filename, "exec")

    runtime_globals = {
        "__name__": "__main__",
        "表示": print,
        "表示する": print,
        "入力": input,
        "入力する": input,

        "範囲": 範囲,
        "列挙": 列挙,
        "追加": 追加,
        "挿入": 挿入,
        "消す": 消す,
        "取り出す": 取り出す,
        "並び替え": 並び替え,
        "逆順": 逆順,
        "何番目": 何番目,
        "部分": 部分,
        "拡張": 拡張,
        "結合": 結合,
        "最大": 最大,
        "最小": 最小,
        "合計": 合計,
    }

    if filename != "<日本語コード>":
        runtime_globals["__file__"] = os.path.abspath(filename)

    exec(code, runtime_globals)


# =========================================================
# CLI
# =========================================================

def main():
    args = sys.argv[1:]

    debug_flags = {"--debug", "-d", "--show"}
    debug = bool(debug_flags & set(args))
    args = [a for a in args if a not in debug_flags]

    if not args:
        print("使い方:")
        print("  python jp.py <日本語コードファイル>")
        print()
        print("例:")
        print("  python jp.py main.gek")
        return

    path = args[0]

    if not os.path.isfile(path):
        print(f"ファイルが見つかりません: {path}")
        return

    with open(path, encoding="utf-8-sig") as f:
        source = f.read()

    run_source(source, filename=path, debug=debug)


if __name__ == "__main__":
    main()