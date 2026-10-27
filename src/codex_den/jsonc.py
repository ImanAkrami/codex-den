"""JSON with comments and trailing commas, as used by editor preferences.

The JSON decoder still enforces string, number, object and array syntax. This
scanner only removes comments and trailing separators outside string literals.
"""

import json


def loads(content: bytes):
    text = content.decode("utf-8-sig")
    cleaned = []
    index, quoted, escaped = 0, False, False
    while index < len(text):
        char = text[index]
        if quoted:
            cleaned.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
            cleaned.append(char)
        elif text.startswith("//", index):
            end = text.find("\n", index + 2)
            index = len(text) if end < 0 else end
            cleaned.append("\n")
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unterminated JSON comment")
            cleaned.append(" ")
            index = end + 2
            continue
        else:
            cleaned.append(char)
        index += 1
    text = "".join(cleaned)
    cleaned = []
    quoted, escaped = False, False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == ",":
            following = index + 1
            while following < len(text) and text[following].isspace():
                following += 1
            previous = index - 1
            while previous >= 0 and text[previous].isspace():
                previous -= 1
            if (
                following < len(text)
                and text[following] in "]}"
                and previous >= 0
                and text[previous] not in "{[,:"
            ):
                continue
        cleaned.append(char)
    return json.loads("".join(cleaned))
