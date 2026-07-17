import json
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from nexon_api import NexonApiError, get_character_summary


ALLOWED_ORIGINS = {
    "https://aldkl.github.io",
    "http://127.0.0.1:8765",
    "http://localhost:8765",
}
CACHE_TTL_SECONDS = 6 * 60 * 60
REFRESH_COOLDOWN_SECONDS = 5 * 60
_character_cache = {}
_last_refreshes = {}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._write_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        name = (params.get("name") or [""])[0].strip()
        lookup_date = (params.get("date") or [""])[0].strip()
        refresh = (params.get("refresh") or [""])[0].strip().lower() in {
            "1",
            "true",
            "yes",
        }

        if not name:
            self._write_json({"error": "캐릭터명을 입력하세요."}, status=400)
            return
        if len(name) > 20:
            self._write_json({"error": "캐릭터명이 너무 깁니다."}, status=400)
            return
        if not lookup_date:
            lookup_date = (date.today() - timedelta(days=1)).isoformat()

        cache_key = f"{lookup_date}:{name.casefold()}"
        now = time.time()
        if refresh:
            retry_after = REFRESH_COOLDOWN_SECONDS - (now - _last_refreshes.get(cache_key, 0))
            if retry_after > 0:
                self._write_json(
                    {"error": f"캐릭터 정보는 {int(retry_after) + 1}초 후 다시 갱신할 수 있습니다.", "retryAfter": int(retry_after) + 1},
                    status=429,
                )
                return
        cached = _character_cache.get(cache_key)
        if not refresh and cached and time.time() - cached["stored_at"] < CACHE_TTL_SECONDS:
            self._write_json({**cached["payload"], "cached": True})
            return

        try:
            payload = get_character_summary(name, lookup_date)
        except NexonApiError as exc:
            self._write_json({"error": str(exc)}, status=502)
            return

        if payload.get("hunting_bonus_stats", {}).get("ability_loaded") is True and payload.get("hunting_bonus_stats", {}).get("challengers_loaded") is True:
            _character_cache[cache_key] = {
                "stored_at": time.time(),
                "payload": payload,
            }
        if refresh:
            _last_refreshes[cache_key] = now
        self._write_json({**payload, "cached": False})

    def _write_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")

    def _write_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
