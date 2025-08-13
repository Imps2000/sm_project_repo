import re
_pat = re.compile(r"(?<!\w)#([\w가-힣]+)")

def extract_hashtags(text: str) -> list[str]:
    if not text:
        return []
    tags = {m.group(1).lower() for m in _pat.finditer(text)}
    return sorted(tags)
