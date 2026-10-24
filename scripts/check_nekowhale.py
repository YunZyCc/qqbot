"""验证 nekowhale 图片直链格式。"""

from __future__ import annotations

import urllib.parse

import httpx

SITE = "https://kiriyuki.com"
GIF_BASE = "/media/gif"

CASES = [
    ("大肥鱼", "10N01_猫猫搓手.gif", "4a44767ab58b"),
    ("大肥鱼", "10N01_猫猫搓手.gif", ""),
    ("大肥鱼和GPT娘", "TT11_交个朋友.gif", "ced329347985"),
]


def main() -> None:
    for pack, file, hash_ in CASES:
        path = f"{GIF_BASE}/{urllib.parse.quote(pack)}/{urllib.parse.quote(file)}"
        url = SITE + path + (f"?h={hash_}" if hash_ else "")
        try:
            resp = httpx.head(url, timeout=20, follow_redirects=True)
            print(resp.status_code, resp.headers.get("content-type"), resp.headers.get("content-length"), url)
        except Exception as exc:  # noqa: BLE001
            print("ERR", exc, url)


if __name__ == "__main__":
    main()
