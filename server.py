import json
import time
from datetime import date, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nexon_api import NexonApiError, find_character_account, get_character_summary


HOST = "127.0.0.1"
PORT = 8765
REFRESH_COOLDOWN_SECONDS = 5 * 60
LAST_REFRESHES = {}
CACHE_PATH = Path("data/character_cache.json")
APP_ROUTES = {
    "/",
    "/guide",
    "/weekly-boss",
    "/todo",
    "/hunting-profit",
    "/calendar",
    "/goals",
    "/alarm",
    "/updates",
}


def read_character_cache():
    if not CACHE_PATH.exists():
        return {}
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_character_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)


class MapleAlimHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/character":
            self.handle_character(parsed.query)
            return
        if parsed.path in APP_ROUTES:
            self.path = "/index.html"
        super().do_GET()

    def handle_character(self, query):
        params = parse_qs(query)
        name = (params.get("name") or [""])[0].strip()
        lookup_date = (params.get("date") or [""])[0].strip()
        refresh = (params.get("refresh") or [""])[0].strip() in {"1", "true", "yes"}
        if not lookup_date:
            lookup_date = (date.today() - timedelta(days=1)).isoformat()

        if not name:
            self.write_json({"error": "캐릭터명을 입력하세요."}, status=400)
            return

        cache = read_character_cache()
        cache_key = f"{lookup_date}:{name.lower()}"
        now = time.time()
        if refresh:
            retry_after = REFRESH_COOLDOWN_SECONDS - (now - LAST_REFRESHES.get(cache_key, 0))
            if retry_after > 0:
                self.write_json(
                    {"error": f"캐릭터 정보는 {int(retry_after) + 1}초 후 다시 갱신할 수 있습니다.", "retryAfter": int(retry_after) + 1},
                    status=429,
                )
                return
        if not refresh and cache_key in cache:
            cached = cache[cache_key]
            if not cached.get("account_id") and cached.get("ocid"):
                try:
                    account = find_character_account(cached["ocid"])
                    cached = {**cached, **account}
                    cache[cache_key] = cached
                    write_character_cache(cache)
                except NexonApiError:
                    pass
            bonus_stats = cached.get("hunting_bonus_stats")
            if isinstance(cached.get("hunting_equipment_presets"), list) and isinstance(bonus_stats, dict) and "ability_drop" in bonus_stats:
                self.write_json({**cached, "cached": True})
                return

        try:
            data = get_character_summary(name, lookup_date)
        except NexonApiError as exc:
            self.write_json({"error": str(exc)}, status=502)
            return

        cache[cache_key] = {**data, "cached": False}
        write_character_cache(cache)
        if refresh:
            LAST_REFRESHES[cache_key] = now

        self.write_json(data)

    def write_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), MapleAlimHandler)
    print(f"메이플 플랜 서버 실행 중: http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
