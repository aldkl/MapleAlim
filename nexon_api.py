import argparse
import json
import os
import sys
import re
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://open.api.nexon.com/maplestory/v1"
API_KEY_ENV = "NEXON_OPEN_API_KEY"


class NexonApiError(RuntimeError):
    pass


def load_env_file(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def request_json(path, params=None):
    load_env_file()
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise NexonApiError(f"{API_KEY_ENV} 환경변수를 먼저 설정해야 합니다.")

    query = urlencode(params or {})
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    request = Request(url, headers={"x-nxopen-api-key": api_key})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=15) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return _repair_api_text(json.loads(response.read().decode(charset)))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < 2:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise NexonApiError(f"NEXON API 오류 {exc.code}: {body}") from exc
        except URLError as exc:
            raise NexonApiError(f"NEXON API 연결 실패: {exc.reason}") from exc


def _repair_api_text(value):
    if isinstance(value, dict):
        return {key: _repair_api_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_api_text(item) for item in value]
    if not isinstance(value, str):
        return value
    try:
        repaired = value.encode("latin-1").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return repaired if any("가" <= char <= "힣" for char in repaired) else value


def get_ocid(character_name):
    data = request_json("/id", {"character_name": character_name})
    ocid = data.get("ocid")
    if not ocid:
        raise NexonApiError(f"ocid를 찾지 못했습니다: {character_name}")
    return ocid


def get_character_basic(ocid, lookup_date=None):
    params = {"ocid": ocid}
    if lookup_date:
        params["date"] = lookup_date
    return request_json("/character/basic", params)


def get_character_item_equipment(ocid, lookup_date=None):
    params = {"ocid": ocid}
    if lookup_date:
        params["date"] = lookup_date
    return request_json("/character/item-equipment", params)


def _potential_percent(option, keyword):
    text = str(option or "")
    if keyword not in text:
        return 0
    match = re.search(r"(\d+)\s*%", text)
    return int(match.group(1)) if match else 0


def get_hunting_equipment_presets(ocid, lookup_date=None):
    equipment = get_character_item_equipment(ocid, lookup_date)
    current_preset = int(equipment.get("preset_no") or 1)
    presets = []
    for preset_no in range(1, 4):
        items = equipment.get(f"item_equipment_preset_{preset_no}") or []
        drop_rate = 0
        meso_rate = 0
        sources = []
        for item in items:
            item_drop = 0
            item_meso = 0
            for field in (
                "potential_option_1", "potential_option_2", "potential_option_3",
                "additional_potential_option_1", "additional_potential_option_2", "additional_potential_option_3",
            ):
                option = item.get(field)
                item_drop += _potential_percent(option, "아이템 드롭률")
                item_meso += _potential_percent(option, "메소 획득량")
            drop_rate += item_drop
            meso_rate += item_meso
            if item_drop or item_meso:
                sources.append({
                    "slot": item.get("item_equipment_slot"),
                    "name": item.get("item_name"),
                    "drop_rate": item_drop,
                    "meso_rate": item_meso,
                })
        presets.append({
            "preset_no": preset_no,
            "is_current": preset_no == current_preset,
            "drop_rate": drop_rate,
            "meso_rate": meso_rate,
            "sources": sources,
        })
    return presets


def _percent_from_texts(values, keyword):
    total = 0
    for value in values or []:
        text = value.get("name", "") if isinstance(value, dict) else str(value or "")
        if keyword not in text:
            continue
        matches = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
        if matches:
            total += float(matches[-1])
    return total


def _artifact_effect_percent(level):
    values = [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 12]
    numeric_level = max(0, min(10, int(level or 0)))
    return values[numeric_level]


def get_hunting_bonus_stats(ocid, lookup_date=None):
    ability_loaded = True
    try:
        ability = request_json("/character/ability", {"ocid": ocid})
    except NexonApiError:
        ability = {}
        ability_loaded = False

    beginner_params = {"ocid": ocid, "character_skill_grade": "0"}
    if lookup_date:
        beginner_params["date"] = lookup_date
    challengers_loaded = True
    try:
        beginner_skills = request_json("/character/skill", beginner_params).get("character_skill") or []
    except NexonApiError:
        beginner_skills = []
        challengers_loaded = False
    challengers_skill = next((skill for skill in beginner_skills if str(skill.get("skill_name") or "").startswith("챌린저스") and "패스" not in str(skill.get("skill_name") or "")), None)
    challengers_name = str(challengers_skill.get("skill_name") or "") if challengers_skill else ""
    challengers_sapphire_plus = challengers_name == "챌린저스"

    skill_params = {"ocid": ocid, "character_skill_grade": "5"}
    if lookup_date:
        skill_params["date"] = lookup_date
    try:
        skills = request_json("/character/skill", skill_params).get("character_skill") or []
    except NexonApiError:
        skills = []
    holy_symbol = next((skill for skill in skills if "홀리 심볼" in str(skill.get("skill_name") or "")), None)
    holy_symbol_drop = _percent_from_texts([holy_symbol.get("skill_effect")], "드롭률") if holy_symbol else 0

    try:
        union = request_json("/user/union-raider", {"ocid": ocid})
    except NexonApiError:
        union = {}
    union_stats = union.get("union_raider_stat") or []
    union_drop = _percent_from_texts(union_stats, "아이템 드롭률")
    union_meso = _percent_from_texts(union_stats, "메소 획득량")

    try:
        artifact = request_json("/user/union-artifact", {"ocid": ocid})
    except NexonApiError:
        artifact = {}
    artifact_drop = 0
    artifact_meso = 0
    artifact_effects = artifact.get("union_artifact_effect") or []
    for effect in artifact_effects:
        name = str(effect.get("name") or "")
        value = _artifact_effect_percent(effect.get("level"))
        if "아이템 드롭률" in name:
            artifact_drop += value
        if "메소 획득량" in name:
            artifact_meso += value

    ability_presets = []
    for preset_no in range(1, 4):
        preset = ability.get(f"ability_preset_{preset_no}") or {}
        values = [item.get("ability_value") for item in (preset.get("ability_info") or [])]
        ability_presets.append({
            "preset_no": preset_no,
            "drop_rate": _percent_from_texts(values, "아이템 드롭률"),
            "meso_rate": _percent_from_texts(values, "메소 획득량"),
        })
    best_ability = max(
        ability_presets,
        key=lambda item: (item["drop_rate"] + item["meso_rate"], item["drop_rate"], -item["preset_no"]),
        default={"preset_no": 0, "drop_rate": 0, "meso_rate": 0},
    )

    return {
        "holy_symbol_drop": holy_symbol_drop,
        "union_drop": union_drop,
        "union_meso": union_meso,
        "artifact_drop": artifact_drop,
        "artifact_meso": artifact_meso,
        "artifact_active": bool(artifact_effects),
        "challengers_skill_name": challengers_name,
        "challengers_sapphire_plus": challengers_sapphire_plus,
        "challengers_loaded": challengers_loaded,
        "challengers_drop": 20 if challengers_sapphire_plus else 0,
        "challengers_meso": 20 if challengers_sapphire_plus else 0,
        "ability_preset_no": best_ability["preset_no"],
        "ability_drop": best_ability["drop_rate"],
        "ability_meso": best_ability["meso_rate"],
        "ability_current_preset_no": int(ability.get("preset_no") or best_ability["preset_no"] or 1),
        "ability_presets": ability_presets,
        "ability_loaded": ability_loaded,
    }


def get_character_list():
    data = request_json("/character/list")
    account_list = data.get("account_list")
    return account_list if isinstance(account_list, list) else []


def find_character_account(ocid):
    for account in get_character_list():
        account_id = account.get("account_id")
        characters = account.get("character_list") or []
        for character in characters:
            if character.get("ocid") == ocid:
                return {
                    "account_id": account_id,
                    "account_character_count": len(characters),
                }
    return {
        "account_id": None,
        "account_character_count": None,
    }


def get_character_summary(character_name, lookup_date=None):
    ocid = get_ocid(character_name)
    basic = get_character_basic(ocid, lookup_date)
    account = find_character_account(ocid)
    hunting_presets = get_hunting_equipment_presets(ocid, lookup_date)
    hunting_bonus_stats = get_hunting_bonus_stats(ocid, lookup_date)
    return {
        "ocid": ocid,
        "account_id": account.get("account_id"),
        "account_character_count": account.get("account_character_count"),
        "date": basic.get("date", lookup_date),
        "character_name": basic.get("character_name", character_name),
        "world_name": basic.get("world_name"),
        "character_class": basic.get("character_class"),
        "character_class_level": basic.get("character_class_level"),
        "character_level": basic.get("character_level"),
        "character_exp_rate": basic.get("character_exp_rate"),
        "character_guild_name": basic.get("character_guild_name"),
        "character_image": basic.get("character_image"),
        "hunting_equipment_presets": hunting_presets,
        "hunting_bonus_stats": hunting_bonus_stats,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="NEXON Open API에서 메이플스토리 캐릭터 기본 정보를 가져옵니다."
    )
    parser.add_argument("character_name", help="조회할 캐릭터명")
    parser.add_argument(
        "--date",
        default=(date.today() - timedelta(days=1)).isoformat(),
        help="조회 기준일 YYYY-MM-DD. 기본값은 어제입니다.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="API 응답 JSON 전체를 출력합니다.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        summary = get_character_summary(args.character_name, args.date)
    except NexonApiError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.raw:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"캐릭터명: {summary.get('character_name', args.character_name)}")
    print(f"월드: {summary.get('world_name', '-')}")
    print(f"직업: {summary.get('character_class', '-')}")
    print(f"레벨: {summary.get('character_level', '-')}")
    print(f"경험치: {summary.get('character_exp_rate', '-')}%")
    print(f"길드: {summary.get('character_guild_name') or '-'}")
    print(f"조회일: {summary.get('date', args.date)}")
    print(f"ocid: {summary.get('ocid')}")
    print(f"account_id: {summary.get('account_id') or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
