"""
 注册机 - 完整反风控版
opsusapi.online + yourshiguan workers.dev
改进：随机化 UA / impersonate / cookies / headers / 延迟
"""

import sys

import os
import re
import uuid
import json
import random
import string
import time
import math
import secrets
import hashlib
import base64
import argparse
import builtins
import shutil
import threading
import traceback
import requests as std_requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, urlencode, quote, unquote
from curl_cffi import requests


APP_NAME = "YOURSHIGUAN Register"


def _configure_console_streams() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if not stream or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass


_configure_console_streams()


def _get_bundle_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def _get_runtime_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _get_user_data_dir() -> str:
    override = str(os.environ.get("CODEX_REGISTER_DATA_DIR", "")).strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))

    home_dir = os.path.expanduser("~")
    if sys.platform == "win32":
        base_dir = os.environ.get("LOCALAPPDATA") or os.path.join(home_dir, "AppData", "Local")
    elif sys.platform == "darwin":
        base_dir = os.path.join(home_dir, "Library", "Application Support")
    else:
        base_dir = os.environ.get("XDG_DATA_HOME") or os.path.join(home_dir, ".local", "share")
    return os.path.join(base_dir, APP_NAME)


def _get_output_root_dir() -> str:
    if getattr(sys, "frozen", False) or str(os.environ.get("CODEX_REGISTER_DATA_DIR", "")).strip():
        return _get_user_data_dir()
    return os.path.dirname(os.path.abspath(__file__))


APP_BUNDLE_DIR = _get_bundle_dir()
APP_RUNTIME_DIR = _get_runtime_dir()
APP_OUTPUT_DIR = _get_output_root_dir()


def _resolve_input_path(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        return APP_OUTPUT_DIR
    if os.path.isabs(value):
        return value
    output_path = os.path.join(APP_OUTPUT_DIR, value)
    if os.path.exists(output_path):
        return output_path
    runtime_path = os.path.join(APP_RUNTIME_DIR, value)
    if os.path.exists(runtime_path):
        return runtime_path
    bundle_path = os.path.join(APP_BUNDLE_DIR, value)
    if os.path.exists(bundle_path):
        return bundle_path
    return output_path


def _resolve_output_path(path: str) -> str:
    value = str(path or "").strip()
    if not value:
        return APP_OUTPUT_DIR
    if os.path.isabs(value):
        return value
    return os.path.join(APP_OUTPUT_DIR, value)


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _load_config():
    config = {
        "proxy": "http://127.0.0.1:7897",
        "enable_oauth": True,
        "oauth_required": True,
        "oauth_issuer": "https://auth.openai.com",
        "oauth_client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
        "oauth_redirect_uri": "http://localhost:1455/auth/callback",
        "ak_file": "ak.txt",
        "rk_file": "rk.txt",
        "token_json_dir": "codex_tokens",
    }
    config_path = _resolve_input_path("config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                file_config = json.load(f)
            if isinstance(file_config, dict):
                for key in list(config.keys()):
                    if key in file_config:
                        config[key] = file_config[key]
        except Exception as exc:
            print(f"[Config] load config.json failed: {exc}")
    config["proxy"] = os.environ.get("PROXY", config["proxy"])
    config["enable_oauth"] = os.environ.get("ENABLE_OAUTH", config["enable_oauth"])
    config["oauth_required"] = os.environ.get("OAUTH_REQUIRED", config["oauth_required"])
    config["oauth_issuer"] = os.environ.get("OAUTH_ISSUER", config["oauth_issuer"])
    config["oauth_client_id"] = os.environ.get("OAUTH_CLIENT_ID", config["oauth_client_id"])
    config["oauth_redirect_uri"] = os.environ.get("OAUTH_REDIRECT_URI", config["oauth_redirect_uri"])
    config["ak_file"] = os.environ.get("AK_FILE", config["ak_file"])
    config["rk_file"] = os.environ.get("RK_FILE", config["rk_file"])
    config["token_json_dir"] = os.environ.get("TOKEN_JSON_DIR", config["token_json_dir"])
    return config


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


_CONFIG = _load_config()


# ================= 配置 =================
VERIFY_API_URL = "https://openaicodes.yourshiguan.workers.dev/?email="
DOMAIN = "opsusapi.online"
PROXY = _CONFIG["proxy"]
ENABLE_OAUTH = _as_bool(_CONFIG.get("enable_oauth", True))
OAUTH_REQUIRED = _as_bool(_CONFIG.get("oauth_required", True))
OAUTH_ISSUER = str(_CONFIG["oauth_issuer"]).rstrip("/")
OAUTH_CLIENT_ID = _CONFIG["oauth_client_id"]
OAUTH_REDIRECT_URI = _CONFIG["oauth_redirect_uri"]
BASE = "https://chatgpt.com"
ACCOUNTS_DIR = _resolve_output_path("accounts")
ACCOUNTS_WITH_TOKEN_DIR = _resolve_output_path("accounts/with_token")
ACCOUNTS_WITHOUT_TOKEN_DIR = _resolve_output_path("accounts/without_token")
TOKEN_JSON_DIR = _resolve_output_path(_CONFIG["token_json_dir"])
AK_FILE = _resolve_output_path(_CONFIG["ak_file"])
RK_FILE = _resolve_output_path(_CONFIG["rk_file"])

_current_proxy = PROXY
_current_domain = DOMAIN

_print_lock = threading.RLock()
_file_lock = threading.Lock()
_original_print = builtins.print

_progress_state = {
    "active": False,
    "done": 0,
    "total": 1,
    "success": 0,
    "fail": 0,
    "start_time": 0.0,
}


def _clear_progress_line_unlocked():
    cols = shutil.get_terminal_size((110, 20)).columns
    _original_print("\r" + " " * max(10, cols - 1) + "\r", end="", flush=True)


def _render_apt_like_progress(done: int, total: int, success: int, fail: int, start_time: float):
    total = max(1, int(total or 1))
    done = max(0, min(int(done or 0), total))
    success = max(0, int(success or 0))
    fail = max(0, int(fail or 0))

    with _print_lock:
        _progress_state.update({
            "active": done < total,
            "done": done,
            "total": total,
            "success": success,
            "fail": fail,
            "start_time": float(start_time or time.time()),
        })

        percent = (done / total) * 100
        cols = shutil.get_terminal_size((110, 20)).columns
        elapsed = max(0.0, time.time() - _progress_state["start_time"])
        speed = (done / elapsed) if elapsed > 0 else 0.0
        right_text = f" {percent:6.2f}% [{done}/{total}] 成功:{success} 失败:{fail} 速率:{speed:.2f}/s"
        bar_width = max(12, min(50, cols - len(right_text) - 8))
        filled = int((done / total) * bar_width)

        if done >= total:
            bar = "=" * bar_width
        elif filled <= 0:
            bar = ">" + " " * (bar_width - 1)
        else:
            bar = "=" * (filled - 1) + ">" + " " * (bar_width - filled)

        line = f"\r进度: [{bar}]" + right_text
        _original_print(line, end="", flush=True)


def _print_with_progress(*args, **kwargs):
    with _print_lock:
        if _progress_state["active"]:
            _clear_progress_line_unlocked()

        _original_print(*args, **kwargs)

        if _progress_state["active"]:
            _render_apt_like_progress(
                _progress_state["done"],
                _progress_state["total"],
                _progress_state["success"],
                _progress_state["fail"],
                _progress_state["start_time"],
            )


builtins.print = _print_with_progress

def _proxies():
    if not _current_proxy:
        return None
    return {"http": _current_proxy, "https": _current_proxy}

# ================= 高级浏览器指纹 =================
_CHROME_PROFILES = [
    {"major": 99, "impersonate": "chrome99", "build": 5708, "patch_range": (80, 260)},
    {"major": 100, "impersonate": "chrome100", "build": 5724, "patch_range": (40, 220)},
    {"major": 101, "impersonate": "chrome101", "build": 5758, "patch_range": (35, 200)},
    {"major": 104, "impersonate": "chrome104", "build": 5874, "patch_range": (45, 180)},
    {"major": 107, "impersonate": "chrome107", "build": 6015, "patch_range": (40, 165)},
    {"major": 110, "impersonate": "chrome110", "build": 6135, "patch_range": (35, 160)},
    {"major": 116, "impersonate": "chrome116", "build": 6254, "patch_range": (30, 155)},
    {"major": 119, "impersonate": "chrome119", "build": 6345, "patch_range": (25, 148)},
    {"major": 120, "impersonate": "chrome120", "build": 6435, "patch_range": (20, 140)},
    {"major": 123, "impersonate": "chrome123", "build": 6575, "patch_range": (18, 135)},
    {"major": 124, "impersonate": "chrome124", "build": 6635, "patch_range": (15, 130)},
    {"major": 131, "impersonate": "chrome131", "build": 6878, "patch_range": (12, 125)},
    {"major": 133, "impersonate": "chrome133a", "build": 7128, "patch_range": (10, 120)},
    {"major": 136, "impersonate": "chrome136", "build": 7305, "patch_range": (8, 115)},
    {"major": 142, "impersonate": "chrome142", "build": 7540, "patch_range": (5, 110)},
]
_CHROME_ANDROID_PROFILES = [
    {"major": 99, "impersonate": "chrome99_android", "build": 5708, "patch_range": (80, 260)},
    {"major": 131, "impersonate": "chrome131_android", "build": 6878, "patch_range": (12, 125)},
]
_IMPERSONATE_TARGETS = [profile["impersonate"] for profile in _CHROME_PROFILES]
_LANGUAGE_PROFILES = [
    ("en-US,en;q=0.9", "en-US", "en-US,en"),
    ("en-GB,en;q=0.9", "en-GB", "en-GB,en"),
    ("en-US,en;q=0.95,en-GB;q=0.9", "en-US", "en-US,en;q=0.95,en-GB;q=0.9"),
    ("en,en-US;q=0.9", "en", "en,en-US;q=0.9"),
    ("en-US,en;q=0.9,zh-CN;q=0.7", "en-US", "en-US,en;q=0.9,zh-CN;q=0.7"),
    ("en-US,en;q=0.9,zh;q=0.8", "en-US", "en-US,en;q=0.9,zh;q=0.8"),
    ("en-GB,en;q=0.9,de;q=0.7", "en-GB", "en-GB,en;q=0.9,de;q=0.7"),
    ("en-US,en;q=0.9,es;q=0.7", "en-US", "en-US,en;q=0.9,es;q=0.7"),
    ("en;q=0.8", "en", "en;q=0.8"),
    ("en-US,en;q=0.8,en-GB;q=0.7", "en-US", "en-US,en;q=0.8,en-GB;q=0.7"),
]
_SCREEN_PROFILES = [
    ("1920x1080", 1, 40),
    ("1366x768", 1, 18),
    ("1536x864", 1, 12),
    ("2560x1440", 1, 10),
    ("1600x900", 1, 8),
    ("3840x2160", 1, 4),
    ("3440x1440", 1, 3),
    ("1280x720", 1, 2),
    ("1680x1050", 1, 2),
    ("1440x900", 1, 1),
]
_SCREEN_WEIGHTED = []
for _screen_res, _device_pixel_ratio, _weight in _SCREEN_PROFILES:
    _SCREEN_WEIGHTED.extend([(_screen_res, _device_pixel_ratio)] * _weight)


def _random_chrome_version(android=False):
    pool = _CHROME_ANDROID_PROFILES if android else _CHROME_PROFILES
    profile = random.choice(pool)
    major = profile["major"]
    build = profile["build"]
    patch = random.randint(*profile["patch_range"])
    full_ver = f"{major}.0.{build}.{patch}"
    if android:
        ua = (
            f"Mozilla/5.0 (Linux; Android 13; Pixel 7) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{full_ver} Mobile Safari/537.36"
        )
    else:
        ua = (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{full_ver} Safari/537.36"
        )
    sec_ch_ua = (
        f'"Not_A Brand";v="99", '
        f'"Google Chrome";v="{major}", '
        f'"Chromium";v="{major}"'
    )
    return profile["impersonate"], major, full_ver, ua, sec_ch_ua


def _random_ua(android=False):
    return _random_chrome_version(android=android)[3]


def _build_sec_ch_ua(major, android=False):
    brands = [
        ("Not_A Brand", "99"),
        ("Google Chrome", str(major)),
        ("Chromium", str(major)),
    ]
    if random.random() < 0.3:
        random.shuffle(brands)
    parts = [f'"{brand}";v="{version}"' for brand, version in brands]
    if android:
        return ", ".join(parts) + ', "Mobile Safari";v="605.1"'
    return ", ".join(parts)


def _random_sec_ch_ua(ua=None):
    if ua is None:
        ua = _random_ua()
    m = re.search(r"Chrome/(\d+)", ua)
    major = int(m.group(1)) if m else 120
    return _build_sec_ch_ua(major, android=("Android" in ua))


def _random_sec_ch_ua_platform(android=False):
    if android:
        return '"Android"'
    return random.choice(['"Windows"', '"Windows NT 10.0"'])


def _random_accept_lang():
    return random.choice(_LANGUAGE_PROFILES)[0]


class AdvancedFingerprint:
    def __init__(self, chrome_full, chrome_major, impersonate, android=False):
        self.impersonate = impersonate
        self.chrome_major = chrome_major
        self.chrome_full = chrome_full
        self.is_android = android

        lang_choice = random.choice(_LANGUAGE_PROFILES)
        self.accept_language = lang_choice[0]
        self.navigator_language = lang_choice[1]
        self.navigator_languages = lang_choice[2]

        if android:
            self.screen_resolution = random.choice(["390x844", "414x896", "360x780", "412x915", "393x852"])
            self.device_pixel_ratio = random.choice([2.0, 2.5, 3.0, 2.625, 3.5])
            self.touch_support = True
            self.max_touch_points = random.randint(5, 10)
            self.hardware_concurrency = random.choice([6, 8, 12])
            self.device_memory = random.choice([4, 6, 8])
        else:
            screen_res, device_pixel_ratio = random.choice(_SCREEN_WEIGHTED)
            self.screen_resolution = screen_res
            self.device_pixel_ratio = device_pixel_ratio
            self.touch_support = random.randint(0, 10) < 2
            self.max_touch_points = self.touch_support and random.randint(1, 10) or 0
            self.hardware_concurrency = random.choice([2, 4, 8, 12, 16])
            self.device_memory = random.choice([2, 4, 8])

        self.screen_color_depth = random.choice([24, 30, 32])
        self.screen_width = int(self.screen_resolution.split("x")[0])
        self.screen_height = int(self.screen_resolution.split("x")[1])
        self.dnt = random.choice(["1", "1", "1", "0"])
        self.sec_ch_ua_mobile = "?1" if android else "?0"
        self.sec_ch_ua_platform = '"Android"' if android else random.choice(['"Windows"', '"Windows NT 10.0"'])
        self.sec_ch_ua_platform_version = f'"{random.randint(10, 15)}.0.0"'
        self.sec_ch_ua_arch = random.choice(['"x86"', '"x64"'])
        self.sec_ch_ua_bitness = random.choice(['"64"', '"32"'])
        self.sec_ch_ua_full_version = f'"{chrome_full}"'
        self.nav_properties = [
            "vendorSub", "productSub", "vendor", "maxTouchPoints",
            "scheduling", "userActivation", "doNotTrack", "geolocation",
            "connection", "plugins", "mimeTypes", "pdfViewerEnabled",
            "webkitTemporaryStorage", "webkitPersistentStorage",
            "hardwareConcurrency", "cookieEnabled", "credentials",
            "mediaDevices", "permissions", "locks", "ink",
            "bluetooth", "clipboard", "keyboardLock",
        ]
        self.nav_property = random.choice(self.nav_properties)
        self.nav_value = f"{self.nav_property}-undefined"
        self.doc_prop = random.choice([
            "location", "implementation", "URL", "documentURI", "compatMode",
            "visibilityState", "readyState", "charset", "referrer",
        ])
        self.win_prop = random.choice([
            "Object", "Function", "Array", "Number", "parseFloat",
            "undefined", "parseInt", "Boolean", "Symbol",
        ])


def _build_random_browser_fingerprint(chrome_full, chrome_major=None, impersonate=None, android=False):
    if chrome_major is None or impersonate is None:
        profile = random.choice(_CHROME_ANDROID_PROFILES if android else _CHROME_PROFILES)
        chrome_major = profile["major"]
        impersonate = profile["impersonate"]
    return AdvancedFingerprint(chrome_full, chrome_major, impersonate, android=android)


def _human_delay(low=0.5, high=2.0, jitter=True):
    base = random.uniform(low, high)
    if jitter:
        base += random.uniform(-0.15, 0.15)
    time.sleep(max(0.1, base))


# ================= Sentinel Token Generator =================
class SentinelTokenGenerator:
    MAX_ATTEMPTS = 500000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(self, device_id=None, user_agent=None, fingerprint=None):
        self.device_id = device_id or str(uuid.uuid4())
        self.user_agent = user_agent or _random_ua()
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())
        self.fingerprint = fingerprint

    @staticmethod
    def _fnv1a_32(text: str):
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= (h >> 16)
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= (h >> 16)
        h &= 0xFFFFFFFF
        return format(h, "08x")

    def _get_config(self):
        now_str = time.strftime(
            "%a %b %d %Y %H:%M:%S GMT+0000 (Coordinated Universal Time)",
            time.gmtime(),
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        if self.fingerprint:
            screen_res = self.fingerprint.screen_resolution
            nav_lang = self.fingerprint.navigator_language
            nav_langs = self.fingerprint.navigator_languages
            nav_val = self.fingerprint.nav_value
            doc_prop = self.fingerprint.doc_prop
            win_prop = self.fingerprint.win_prop
            hw_conc = self.fingerprint.hardware_concurrency
        else:
            screen_res = "1920x1080"
            nav_lang = "en-US"
            nav_langs = "en-US,en"
            nav_prop = random.choice([
                "vendorSub", "productSub", "vendor", "maxTouchPoints",
                "scheduling", "userActivation", "doNotTrack", "geolocation",
            ])
            nav_val = f"{nav_prop}-undefined"
            doc_prop = random.choice(["location", "implementation", "URL", "documentURI"])
            win_prop = random.choice(["Object", "Function", "Array", "Number", "parseFloat"])
            hw_conc = random.choice([4, 8, 12, 16])
        return [
            screen_res,
            now_str,
            4294705152,
            random.random(),
            self.user_agent,
            "https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js",
            None,
            None,
            nav_lang,
            nav_langs,
            random.random(),
            nav_val,
            doc_prop,
            win_prop,
            perf_now,
            self.sid,
            "",
            hw_conc,
            time_origin,
        ]

    @staticmethod
    def _base64_encode(data):
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _run_check(self, start_time, seed, difficulty, config, nonce):
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        data = self._base64_encode(config)
        hash_hex = self._fnv1a_32(seed + data)
        diff_len = len(difficulty)
        if hash_hex[:diff_len] <= difficulty:
            return data + "~S"
        return None

    def generate_token(self, seed=None, difficulty=None):
        seed = seed if seed is not None else self.requirements_seed
        difficulty = str(difficulty or "0")
        start_time = time.time()
        config = self._get_config()
        for i in range(self.MAX_ATTEMPTS):
            result = self._run_check(start_time, seed, difficulty, config, i)
            if result:
                return "gAAAAAB" + result
        return "gAAAAAB" + self.ERROR_PREFIX + self._base64_encode(str(None))

    def generate_requirements_token(self):
        config = self._get_config()
        config[3] = 0
        return "gAAAAAB" + self._base64_encode(config) + "~S"


def _make_trace_headers():
    trace_id = random.randint(10**17, 10**18 - 1)
    parent_id = random.randint(10**17, 10**18 - 1)
    tp = f"00-{uuid.uuid4().hex}-{format(parent_id, '016x')}-01"
    tracestate_parts = [
        f"dd=s:{(1 if random.random() > 0.05 else 2)}",
        f"o:{'rum' if random.random() > 0.1 else 'launcher'}",
        f"up:{'1' if random.random() > 0.1 else '0'}",
    ]
    tracestate = ";".join(tracestate_parts[:random.randint(1, 3)])
    return {
        "traceparent": tp,
        "tracestate": tracestate,
        "x-datadog-origin": random.choice(["rum", "appsec", "ci-visibility"]),
        "x-datadog-sampling-priority": random.choice(["0", "1", "2"]),
        "x-datadog-trace-id": str(trace_id),
        "x-datadog-parent-id": str(parent_id),
        "cf-ray": f"{random.randint(10**11, 10**12):x}-{random.choice(['SEA', 'LAX', 'SFO', 'NYC', 'DFW', 'ORD'])}",
        "cf-cache-status": random.choice(["DYNAMIC", "BYPASS", "HIT", "MISS"]),
        "cf-request-id": uuid.uuid4().hex,
    }


def _generate_pkce():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _extract_code_from_url(url: str):
    if not url or "code=" not in url:
        return None
    try:
        return parse_qs(urlparse(url).query).get("code", [None])[0]
    except Exception:
        return None


def _decode_jwt_payload(token: str):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def fetch_sentinel_challenge(session, device_id, flow="authorize_continue", user_agent=None,
                             sec_ch_ua=None, impersonate=None, fingerprint=None):
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent, fingerprint=fingerprint)
    req_body = {"p": generator.generate_requirements_token(), "id": device_id, "flow": flow}
    if fingerprint and not sec_ch_ua:
        sec_ch_ua = _build_sec_ch_ua(fingerprint.chrome_major, android=(fingerprint.sec_ch_ua_mobile == "?1"))
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Referer": "https://sentinel.openai.com/backend-api/sentinel/frame.html",
        "Origin": "https://sentinel.openai.com",
        "User-Agent": user_agent or _random_ua(),
        "sec-ch-ua": sec_ch_ua or _random_sec_ch_ua(user_agent),
        "sec-ch-ua-mobile": fingerprint.sec_ch_ua_mobile if fingerprint else "?0",
        "sec-ch-ua-platform": fingerprint.sec_ch_ua_platform if fingerprint else _random_sec_ch_ua_platform(),
    }
    kwargs = {"data": json.dumps(req_body), "headers": headers, "timeout": 25}
    if impersonate:
        kwargs["impersonate"] = impersonate
    try:
        resp = session.post("https://sentinel.openai.com/backend-api/sentinel/req", **kwargs)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json()
    except Exception:
        return None


def build_sentinel_token(session, device_id, flow="authorize_continue", user_agent=None,
                         sec_ch_ua=None, impersonate=None, fingerprint=None):
    generator = SentinelTokenGenerator(device_id=device_id, user_agent=user_agent, fingerprint=fingerprint)
    challenge = fetch_sentinel_challenge(
        session,
        device_id,
        flow=flow,
        user_agent=user_agent,
        sec_ch_ua=sec_ch_ua,
        impersonate=impersonate,
        fingerprint=fingerprint,
    )
    if not challenge:
        return ""
    c_val = challenge.get("token", "")
    pow_data = challenge.get("proofofwork") or {}
    if pow_data.get("required") and pow_data.get("seed"):
        p_val = generator.generate_token(seed=pow_data.get("seed"), difficulty=pow_data.get("difficulty", "0"))
    else:
        p_val = generator.generate_requirements_token()
    return json.dumps({"p": p_val, "t": "", "c": c_val, "id": device_id, "flow": flow}, separators=(",", ":"))

# ================= 邮箱相关 =================
def generate_email():
    prefix = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(8))
    return f"{prefix}@{_current_domain}"

def generate_password():
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%&*"
    password_chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    all_chars = lower + upper + digits + special
    password_chars.extend(secrets.choice(all_chars) for _ in range(10))
    random.shuffle(password_chars)
    return "".join(password_chars)

def _build_verify_lookup_url(email_key: str) -> str:
    encoded_email = quote(email_key, safe="")
    base = str(VERIFY_API_URL or "").strip()
    if "{email}" in base:
        url = base.replace("{email}", encoded_email)
    elif base.endswith("email="):
        url = f"{base}{encoded_email}"
    else:
        separator = "&" if "?" in base else "?"
        url = f"{base}{separator}email={encoded_email}"
    if "t=" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}t={int(time.time() * 1000)}"
    return url

def wait_code(email, max_wait=120, interval=3):
    print(f"[*] 等待验证码...", end="", flush=True)
    email_key = (email or "").strip().lower()
    for _ in range(max_wait):
        print(".", end="", flush=True)
        try:
            # 每次轮询换随机 UA，模拟不同浏览器查询
            ua = _random_ua()
            # Worker 直连，不走代理
            r = std_requests.get(
                _build_verify_lookup_url(email_key),
                timeout=10,
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                    "User-Agent": ua,
                },
            )
            if r.status_code == 200 and r.json().get("code"):
                code = re.sub(r'\D', '', str(r.json()["code"]))[:6]
                print(f" -> {code}")
                return code
        except Exception as e:
            if _ == 0:
                print(f"\n[!] Worker 异常(将重试): {e}", flush=True)
        time.sleep(interval + random.uniform(-0.5, 0.5))
    return None

# ================= 注册类 =================
class OpenAIRegister:
    def __init__(self):
        # 随机 UA
        self.ua = _random_ua()
        m = re.search(r"Chrome/(\d+)", self.ua)
        ver = m.group(1) if m else "120"
        # 随机 sec-ch-ua
        self.sec_ch_ua = _random_sec_ch_ua(self.ua)
        self.sec_ch_ua_mobile = "?0"
        self.sec_ch_ua_platform = _random_sec_ch_ua_platform()
        # 随机 impersonate 目标
        self.impersonate = random.choice(_IMPERSONATE_TARGETS)
        self.session = requests.Session(impersonate=self.impersonate)
        if _current_proxy:
            self.session.proxies = _proxies()
        self.device_id = str(uuid.uuid4())
        # 初始 cookies
        self._init_cookies()

    def _init_cookies(self):
        """设置逼真的初始 cookies，模拟已有浏览器会话"""
        did = self.device_id
        ts = int(time.time())
        # Cloudflare bot management
        self.session.cookies.set("__cf_bm", f"fake_{secrets.token_hex(16)}-{ts}", domain=".openai.com")
        self.session.cookies.set("_cfuvid", f"fake_{secrets.token_hex(20)}-{ts}", domain=".openai.com")
        # OpenAI related
        self.session.cookies.set("oai-did", did, domain=".openai.com")
        self.session.cookies.set("oai-did", did, domain="chatgpt.com")
        self.session.cookies.set("oai-did", did, domain=".auth.openai.com")
        # Next-auth session cookies
        self.session.cookies.set("__Secure-next-auth.callback-url", BASE, domain=".auth.openai.com")
        self.session.cookies.set("__Secure-next-auth.session-token", secrets.token_hex(32), domain=".auth.openai.com")
        # Context cookies
        self.session.cookies.set("rg_context", "prim", domain=".openai.com")
        self.session.cookies.set("iss_context", "default", domain=".openai.com")
        # Cloudflare load balancer
        self.session.cookies.set("__cflb", f"0H{secrets.token_hex(16)}", domain=".openai.com")
        # dclid (fake)
        self.session.cookies.set("dclid", secrets.token_hex(16), domain=".openai.com")
        # g_state (Google one-tap)
        g_state = f"0_l:{ts}"
        self.session.cookies.set("g_state", g_state, domain=".openai.com")

    def _random_delay(self, lo=0.5, hi=1.5):
        time.sleep(random.uniform(lo, hi))

    def _headers_base(self, referer=None, extra_accept=None):
        """生成固定化的基础请求头，模拟真实浏览器行为"""
        h = {
            "Accept": extra_accept or "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Sec-Ch-Ua": self.sec_ch_ua,
            "Sec-Ch-Ua-Mobile": self.sec_ch_ua_mobile,
            "Sec-Ch-Ua-Platform": self.sec_ch_ua_platform,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": self.ua,
        }
        if referer:
            h["Referer"] = referer
        return h

    def _decode_oauth_session_cookie(self):
        jar = getattr(self.session.cookies, "jar", None)
        if jar is not None:
            cookie_items = list(jar)
        else:
            cookie_items = []
        for c in cookie_items:
            name = getattr(c, "name", "") or ""
            if "oai-client-auth-session" not in name:
                continue
            raw_val = (getattr(c, "value", "") or "").strip()
            if not raw_val:
                continue
            candidates = [raw_val]
            try:
                decoded = unquote(raw_val)
                if decoded != raw_val:
                    candidates.append(decoded)
            except:
                pass
            for val in candidates:
                try:
                    if (val.startswith('"') and val.endswith('"')) or \
                       (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    part = val.split(".")[0] if "." in val else val
                    pad = 4 - len(part) % 4
                    if pad != 4:
                        part += "=" * pad
                    raw = base64.urlsafe_b64decode(part)
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        return data
                except:
                    continue
        return None

    def _oauth_allow_redirect_extract_code(self, url: str, referer: str = None):
        headers = self._headers_base(referer, "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        headers["Upgrade-Insecure-Requests"] = "1"
        try:
            resp = self.session.get(url, headers=headers, allow_redirects=True,
                                    timeout=30, impersonate=self.impersonate)
            final_url = str(resp.url)
            code = _extract_code_from_url(final_url)
            if code:
                return code
            for r in getattr(resp, "history", []) or []:
                loc = r.headers.get("Location", "")
                code = _extract_code_from_url(loc)
                if code:
                    return code
                code = _extract_code_from_url(str(r.url))
                if code:
                    return code
        except Exception as e:
            maybe_localhost = re.search(r'(https?://localhost[^\s\'"]+)', str(e))
            if maybe_localhost:
                code = _extract_code_from_url(maybe_localhost.group(1))
                if code:
                    return code
        return None

    def _oauth_follow_for_code(self, start_url: str, referer: str = None, max_hops: int = 16):
        headers = self._headers_base(referer, "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
        headers["Upgrade-Insecure-Requests"] = "1"
        current_url = start_url
        last_url = start_url
        for hop in range(max_hops):
            try:
                resp = self.session.get(current_url, headers=headers, allow_redirects=False,
                                        timeout=30, impersonate=self.impersonate)
            except Exception as e:
                maybe_localhost = re.search(r'(https?://localhost[^\s\'"]+)', str(e))
                if maybe_localhost:
                    code = _extract_code_from_url(maybe_localhost.group(1))
                    if code:
                        return code, maybe_localhost.group(1)
                return None, last_url
            last_url = str(resp.url)
            code = _extract_code_from_url(last_url)
            if code:
                return code, last_url
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("Location", "")
                if not loc:
                    return None, last_url
                if loc.startswith("/"):
                    loc = f"{OAUTH_ISSUER}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code, loc
                current_url = loc
                headers["Referer"] = last_url
                self._random_delay(0.3, 0.8)
                continue
            return None, last_url
        return None, last_url

    def _oauth_submit_workspace_and_org(self, consent_url: str):
        session_data = self._decode_oauth_session_cookie()
        if not session_data:
            return None
        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            return None
        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            return None

        h = self._headers_base(consent_url, "application/json")
        h["Content-Type"] = "application/json"
        h["Origin"] = OAUTH_ISSUER
        h["oai-device-id"] = self.device_id
        h.update(_make_trace_headers())

        resp = self.session.post(
            f"{OAUTH_ISSUER}/api/accounts/workspace/select",
            json={"workspace_id": workspace_id}, headers=h,
            allow_redirects=False, timeout=30, impersonate=self.impersonate,
        )
        print(f"[*] workspace/select -> {resp.status_code}")

        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if loc.startswith("/"):
                loc = f"{OAUTH_ISSUER}{loc}"
            code = _extract_code_from_url(loc)
            if code:
                return code
            code, _ = self._oauth_follow_for_code(loc, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(loc, referer=consent_url)
            return code

        if resp.status_code != 200:
            return None

        try:
            ws_data = resp.json()
        except:
            return None

        ws_next = ws_data.get("continue_url", "")
        orgs = ws_data.get("data", {}).get("orgs", [])

        org_id = None
        project_id = None
        if orgs:
            org_id = (orgs[0] or {}).get("id")
            projects = (orgs[0] or {}).get("projects", [])
            if projects:
                project_id = (projects[0] or {}).get("id")

        if org_id:
            org_body = {"org_id": org_id}
            if project_id:
                org_body["project_id"] = project_id
            h_org = dict(h)
            if ws_next:
                h_org["Referer"] = ws_next if ws_next.startswith("http") else f"{OAUTH_ISSUER}{ws_next}"
            resp_org = self.session.post(
                f"{OAUTH_ISSUER}/api/accounts/organization/select",
                json=org_body, headers=h_org, allow_redirects=False,
                timeout=30, impersonate=self.impersonate,
            )
            print(f"[*] organization/select -> {resp_org.status_code}")
            if resp_org.status_code in (301, 302, 303, 307, 308):
                loc = resp_org.headers.get("Location", "")
                if loc.startswith("/"):
                    loc = f"{OAUTH_ISSUER}{loc}"
                code = _extract_code_from_url(loc)
                if code:
                    return code
                code, _ = self._oauth_follow_for_code(loc, referer=h_org.get("Referer"))
                if not code:
                    code = self._oauth_allow_redirect_extract_code(loc, referer=h_org.get("Referer"))
                return code
            if resp_org.status_code == 200:
                try:
                    org_data = resp_org.json()
                except:
                    return None
                org_next = org_data.get("continue_url", "")
                if org_next:
                    if org_next.startswith("/"):
                        org_next = f"{OAUTH_ISSUER}{org_next}"
                    code, _ = self._oauth_follow_for_code(org_next, referer=h_org.get("Referer"))
                    if not code:
                        code = self._oauth_allow_redirect_extract_code(org_next, referer=h_org.get("Referer"))
                    return code

        if ws_next:
            if ws_next.startswith("/"):
                ws_next = f"{OAUTH_ISSUER}{ws_next}"
            code, _ = self._oauth_follow_for_code(ws_next, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(ws_next, referer=consent_url)
            return code

        return None

    def perform_codex_oauth_login_http(self, email: str, password: str, name: str = "OpenAI User", birthdate: str = "1995-01-01"):
        print("[*] 开始执行 Codex OAuth 纯协议流程...")
        self.session.cookies.set("oai-did", self.device_id, domain=".auth.openai.com")
        self.session.cookies.set("oai-did", self.device_id, domain="auth.openai.com")

        code_verifier, code_challenge = _generate_pkce()
        state = secrets.token_urlsafe(24)

        authorize_params = {
            "response_type": "code", "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge, "code_challenge_method": "S256",
            "state": state,
            "prompt": "login",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        }
        authorize_url = f"{OAUTH_ISSUER}/oauth/authorize?{urlencode(authorize_params)}"

        def _oauth_json_headers(referer: str):
            h = self._headers_base(referer, "application/json")
            h["Content-Type"] = "application/json"
            h["Origin"] = OAUTH_ISSUER
            h["oai-device-id"] = self.device_id
            h.update(_make_trace_headers())
            return h

        def _bootstrap_oauth_session():
            print("[*] 1/7 GET /oauth/authorize")
            h = self._headers_base(f"{BASE}/", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            h["Upgrade-Insecure-Requests"] = "1"
            try:
                r = self.session.get(authorize_url, headers=h,
                    allow_redirects=True, timeout=30, impersonate=self.impersonate)
            except Exception as e:
                print(f"[*] /oauth/authorize 异常: {e}")
                return False, ""

            final_url = str(r.url)
            has_login = any(getattr(c, "name", "") == "login_session" for c in self.session.cookies)

            if not has_login:
                oauth2_url = f"{OAUTH_ISSUER}/api/oauth/oauth2/auth"
                h2 = self._headers_base(authorize_url, "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                h2["Upgrade-Insecure-Requests"] = "1"
                try:
                    r2 = self.session.get(oauth2_url, headers=h2, params=authorize_params,
                        allow_redirects=True, timeout=30, impersonate=self.impersonate)
                    final_url = str(r2.url)
                except Exception as e:
                    print(f"[*] /api/oauth/oauth2/auth 异常: {e}")
                has_login = any(getattr(c, "name", "") == "login_session" for c in self.session.cookies)

            return has_login, final_url

        def _post_authorize_continue(referer_url: str):
            sentinel_authorize = build_sentinel_token(
                self.session, self.device_id, flow="authorize_continue",
                user_agent=self.ua, sec_ch_ua=self.sec_ch_ua, impersonate=self.impersonate,
            )
            if not sentinel_authorize:
                print("[*] sentinel authorize token 生成失败")
                return None
            headers_continue = _oauth_json_headers(referer_url)
            headers_continue["openai-sentinel-token"] = sentinel_authorize
            try:
                return self.session.post(
                    f"{OAUTH_ISSUER}/api/accounts/authorize/continue",
                    json={"username": {"kind": "email", "value": email}},
                    headers=headers_continue, timeout=30,
                    allow_redirects=False, impersonate=self.impersonate,
                )
            except Exception as e:
                print(f"[*] authorize/continue 异常: {e}")
                return None

        has_login_session, authorize_final_url = _bootstrap_oauth_session()
        if not authorize_final_url:
            return None

        self._random_delay(1.0, 2.0)

        continue_referer = (authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER)
                            else f"{OAUTH_ISSUER}/log-in")

        print("[*] 2/7 POST /api/accounts/authorize/continue")
        resp_continue = _post_authorize_continue(continue_referer)
        if resp_continue is None:
            print("[*] authorize/continue 请求未发出或失败")
            return None

        print(f"[*] /authorize/continue -> {resp_continue.status_code}")
        if resp_continue.status_code == 400 and "invalid_auth_step" in (resp_continue.text or ""):
            self._random_delay(1.0, 2.0)
            has_login_session, authorize_final_url = _bootstrap_oauth_session()
            if not authorize_final_url:
                return None
            continue_referer = (authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER)
                                else f"{OAUTH_ISSUER}/log-in")
            resp_continue = _post_authorize_continue(continue_referer)
            if resp_continue is None:
                print("[*] authorize/continue 重试失败")
                return None

        if resp_continue.status_code != 200:
            print(f"[*] authorize/continue 非200: {resp_continue.status_code}, body={resp_continue.text[:220]}")
            return None

        try:
            continue_data = resp_continue.json()
        except:
            print(f"[*] authorize/continue JSON 解析失败: {resp_continue.text[:220]}")
            return None

        continue_url = continue_data.get("continue_url", "")
        page_type = (continue_data.get("page") or {}).get("type", "")

        self._random_delay(0.8, 1.5)

        print("[*] 3/7 POST /api/accounts/password/verify")
        sentinel_pwd = build_sentinel_token(
            self.session, self.device_id, flow="password_verify",
            user_agent=self.ua, sec_ch_ua=self.sec_ch_ua, impersonate=self.impersonate,
        )
        if not sentinel_pwd:
            print("[*] sentinel password token 生成失败")
            return None

        headers_verify = _oauth_json_headers(f"{OAUTH_ISSUER}/log-in/password")
        headers_verify["openai-sentinel-token"] = sentinel_pwd

        try:
            resp_verify = self.session.post(
                f"{OAUTH_ISSUER}/api/accounts/password/verify",
                json={"password": password}, headers=headers_verify,
                timeout=30, allow_redirects=False, impersonate=self.impersonate,
            )
        except Exception as e:
            print(f"[*] password/verify 异常: {e}")
            return None

        if resp_verify.status_code != 200:
            print(f"[*] password/verify 非200: {resp_verify.status_code}, body={resp_verify.text[:220]}")
            return None

        try:
            verify_data = resp_verify.json()
        except:
            print(f"[*] password/verify JSON 解析失败: {resp_verify.text[:220]}")
            return None

        continue_url = verify_data.get("continue_url", "") or continue_url
        page_type = (verify_data.get("page") or {}).get("type", "") or page_type

        need_oauth_otp = (
            page_type == "email_otp_verification"
            or "email-verification" in (continue_url or "")
            or "email-otp" in (continue_url or "")
        )

        if need_oauth_otp:
            self._random_delay(1.0, 2.0)
            print("[*] 4/7 检测到邮箱 OTP 验证")
            headers_otp = _oauth_json_headers(f"{OAUTH_ISSUER}/email-verification")
            tried_codes = set()
            otp_success = False
            otp_deadline = time.time() + 120

            while time.time() < otp_deadline and not otp_success:
                candidate_codes = []
                code = wait_code(email, max_wait=60, interval=3)
                if code and code not in tried_codes:
                    candidate_codes.append(code)

                if not candidate_codes:
                    elapsed = int(120 - max(0, otp_deadline - time.time()))
                    print(f"[*] OTP 等待中... ({elapsed}s/120s)")
                    self._random_delay(1.5, 2.5)
                    continue

                for otp_code in candidate_codes:
                    tried_codes.add(otp_code)
                    print(f"[*] 尝试 OTP: {otp_code}")
                    self._random_delay(0.5, 1.0)
                    try:
                        resp_otp = self.session.post(
                            f"{OAUTH_ISSUER}/api/accounts/email-otp/validate",
                            json={"code": otp_code}, headers=headers_otp,
                            timeout=30, allow_redirects=False, impersonate=self.impersonate,
                        )
                    except Exception as e:
                        print(f"[*] email-otp/validate 异常: {e}")
                        self._random_delay(1.0, 2.0)
                        continue
                    if resp_otp.status_code != 200:
                        self._random_delay(1.0, 2.0)
                        continue
                    try:
                        otp_data = resp_otp.json()
                    except:
                        continue
                    continue_url = otp_data.get("continue_url", "") or continue_url
                    page_type = (otp_data.get("page") or {}).get("type", "") or page_type
                    otp_success = True
                    break

                if not otp_success:
                    self._random_delay(1.5, 2.5)

            if not otp_success:
                print("[*] OAuth 阶段 OTP 验证失败")
                return None

        needs_about_you = (
            page_type == "about_you"
            or "/about-you" in (continue_url or "")
        )
        if needs_about_you:
            self._random_delay(0.5, 1.0)
            print("[*] 4b/7 检测到 about-you，需提交账户信息")
            for ay_retry in range(3):
                h_ay = _oauth_json_headers(f"{OAUTH_ISSUER}/about-you")
                sen_ay = build_sentinel_token(
                    self.session, self.device_id, flow="about_you",
                    user_agent=self.ua, sec_ch_ua=self.sec_ch_ua, impersonate=self.impersonate,
                )
                if sen_ay:
                    h_ay["openai-sentinel-token"] = sen_ay
                body_ay = {"name": name, "birthdate": birthdate}
                try:
                    resp_ay = self.session.post(
                        f"{OAUTH_ISSUER}/api/accounts/create_account",
                        json=body_ay,
                        headers=h_ay, timeout=30, allow_redirects=False,
                        impersonate=self.impersonate,
                    )
                    print(f"[*] about-you POST -> {resp_ay.status_code}")
                    if resp_ay.status_code == 200:
                        try:
                            ay_d = resp_ay.json()
                            new_cont = ay_d.get("continue_url", "")
                            new_page = (ay_d.get("page") or {}).get("type", "")
                            print(f"[*] about-you JSON: continue_url={str(new_cont)[:60]}, page={new_page}")
                            if new_cont:
                                continue_url = new_cont
                                if new_cont.startswith("/"):
                                    new_cont = f"{OAUTH_ISSUER}{new_cont}"
                                self._oauth_follow_for_code(new_cont, referer=f"{OAUTH_ISSUER}/about-you")
                            if new_page:
                                page_type = new_page
                        except:
                            pass
                        break
                    elif resp_ay.status_code in (301, 302, 303, 307, 308):
                        loc = resp_ay.headers.get("Location", "")
                        if loc.startswith("/"):
                            loc = f"{OAUTH_ISSUER}{loc}"
                        print(f"[*] about-you redirect: {str(loc)[:100]}")
                        self._oauth_follow_for_code(loc, referer=f"{OAUTH_ISSUER}/about-you")
                        if loc:
                            continue_url = loc
                            page_type = ""
                        break
                    else:
                        print(f"[*] about-you 非200: {resp_ay.text[:150]}")
                        if "already" in resp_ay.text.lower():
                            print("[*] about-you: 账号已存在，视为成功，继续")
                            break
                        if ay_retry < 2:
                            self._random_delay(1.5, 2.5)
                            continue
                except Exception as e:
                    print(f"[*] about-you POST 异常: {e}")
                    if ay_retry < 2:
                        self._random_delay(1.5, 2.5)
                        continue
                break
            self._random_delay(0.5, 1.0)

        code = None
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{OAUTH_ISSUER}{consent_url}"
        if not consent_url and "consent" in page_type:
            consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
        if consent_url:
            code = _extract_code_from_url(consent_url)

        if not code and consent_url:
            print("[*] 5/7 跟随 continue_url 提取 code")
            self._random_delay(0.5, 1.0)
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{OAUTH_ISSUER}/log-in/password")

        consent_hint = (
                ("consent" in (consent_url or ""))
                or ("sign-in-with-chatgpt" in (consent_url or ""))
                or ("workspace" in (consent_url or ""))
                or ("organization" in (consent_url or ""))
                or ("consent" in page_type)
                or ("organization" in page_type)
        )

        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            print("[*] 6/7 执行 workspace/org 选择")
            self._random_delay(0.5, 1.0)
            code = self._oauth_submit_workspace_and_org(consent_url)

        if not code:
            fallback_consent = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            print("[*] 6/7 回退 consent 路径重试")
            self._random_delay(0.5, 1.0)
            code = self._oauth_submit_workspace_and_org(fallback_consent)
            if not code:
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{OAUTH_ISSUER}/log-in/password")

        if not code:
            print("[*] 未获取到 authorization code")
            return None

        self._random_delay(0.5, 1.0)
        print("[*] 7/7 POST /oauth/token")
        h_token = self._headers_base(OAUTH_ISSUER)
        h_token["Content-Type"] = "application/x-www-form-urlencoded"
        token_resp = self.session.post(
            f"{OAUTH_ISSUER}/oauth/token",
            headers=h_token,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "client_id": OAUTH_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            timeout=60,
            impersonate=self.impersonate,
        )
        print(f"[*] /oauth/token -> {token_resp.status_code}")

        if token_resp.status_code != 200:
            print(f"[*] token 交换失败: {token_resp.status_code} {token_resp.text[:200]}")
            return None

        try:
            data = token_resp.json()
        except:
            print("[*] token 响应解析失败")
            return None

        if not data.get("access_token"):
            print("[*] token 响应缺少 access_token")
            return None

        print("[*] Codex Token 获取成功")
        return data

    def register(self, email: str, password: str, name: str = "OpenAI User", birthdate: str = "1995-01-01"):
        """完整注册流程"""
        print(f"\n[*] 邮箱: {email}")
        print(f"[*] 密码: {password}")
        print(f"[*] 姓名: {name}, 生日: {birthdate}")
        print(f"[*] UA: {self.ua}")
        print(f"[*] impersonate: {self.impersonate}")

        # Step 0: Visit homepage
        print("\n[*] Step 0: Visit homepage...")
        self._random_delay(1.0, 2.0)
        try:
            h0 = self._headers_base(BASE, "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            h0["Upgrade-Insecure-Requests"] = "1"
            self.session.get(BASE, headers=h0, timeout=15)
        except:
            pass
        self._random_delay(1.0, 2.0)

        # Step 1: Get CSRF
        print("[*] Step 1: Get CSRF...")
        h1 = self._headers_base(BASE, "application/json")
        h1["Referer"] = BASE + "/"
        try:
            r = self.session.get(
                f"{BASE}/api/auth/csrf",
                headers=h1,
                timeout=15
            )
            csrf = r.json().get("csrfToken", "") if r.status_code == 200 else ""
        except:
            csrf = ""
        self._random_delay(0.8, 1.5)

        # Step 2: Signin
        print("[*] Step 2: Signin...")
        v, c = _generate_pkce()
        params = {
            "prompt": "login", "ext-oai-did": self.device_id,
            "auth_session_logging_id": str(uuid.uuid4()),
            "screen_hint": "login_or_signup", "login_hint": email,
        }
        form_data = {"callbackUrl": f"{BASE}/", "csrfToken": csrf, "json": "true"}
        h2 = self._headers_base(BASE)
        h2["Content-Type"] = "application/x-www-form-urlencoded"
        h2["Origin"] = BASE
        try:
            r = self.session.post(
                f"{BASE}/api/auth/signin/openai",
                params=params, data=form_data,
                headers=h2,
            )
            print(f"[*] Signin status: {r.status_code}")
            data = r.json()
            print(f"[*] Signin response: {json.dumps(data, indent=2)[:500]}")
            url = data.get("url", "") if isinstance(data, dict) else ""
            print(f"[*] Signin URL: {url}")
        except Exception as e:
            print(f"[!] Signin exception: {e}")
            url = ""
        self._random_delay(1.0, 2.0)

        need_otp = False
        authorize_retry = 3
        while authorize_retry > 0:
            print("[*] Step 3: Authorize...")
            h3 = self._headers_base(f"{BASE}/", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            h3["Upgrade-Insecure-Requests"] = "1"
            try:
                r = self.session.get(url if url else f"{OAUTH_ISSUER}/authorize", headers=h3,
                    allow_redirects=True, timeout=15)
                final_url = str(r.url)
            except:
                final_url = url
            final_path = urlparse(final_url).path
            print(f"[*] 跳转: {final_path}")
            self._random_delay(1.0, 2.0)

            if "create-account/password" in final_path:
                print("[*] 全新注册流程...")
                # Register
                h = self._headers_base(OAUTH_ISSUER, "application/json")
                h["Content-Type"] = "application/json"
                h["Origin"] = OAUTH_ISSUER
                h.update(_make_trace_headers())
                try:
                    r = self.session.post(
                        f"{OAUTH_ISSUER}/api/accounts/user/register",
                        json={"username": email, "password": password},
                        headers=h, timeout=15
                    )
                    print(f"[*] Register: {r.status_code}")
                    if r.status_code == 200:
                        need_otp = True
                        break
                    else:
                        print(f"[!] 注册失败: {r.text[:200]}")
                except Exception as e:
                    print(f"[!] 注册异常: {e}")
                authorize_retry -= 1
                if authorize_retry > 0:
                    print(f"[*] 等待 10 秒后重试 Step 3 ({authorize_retry} 次)...\n")
                    time.sleep(10)
                continue
            elif "email-verification" in final_path or "email-otp" in final_path:
                print("[*] 跳到 OTP 验证阶段")
                need_otp = True
                break
            else:
                print(f"[*] 未知跳转: {final_path}, 重试中 ({authorize_retry-1} 次)...\n")
                authorize_retry -= 1
                if authorize_retry > 0:
                    time.sleep(10)
                continue

        if authorize_retry == 0 or not need_otp:
            print("[FAIL] Step 3 重试耗尽")
            return None

        if need_otp:
            self._random_delay(1.0, 2.0)
            print("\n[*] Step 5: Send OTP...")
            h_otp_send = self._headers_base(f"{OAUTH_ISSUER}/create-account/password",
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            h_otp_send["Upgrade-Insecure-Requests"] = "1"
            try:
                self.session.get(
                    f"{OAUTH_ISSUER}/api/accounts/email-otp/send",
                    headers=h_otp_send,
                    allow_redirects=True, timeout=15
                )
            except:
                pass
            self._random_delay(2.0, 4.0)

            print("\n[*] Step 6: Validate OTP...")
            code = wait_code(email)
            if not code:
                return None
            self._random_delay(0.8, 1.5)

            h = self._headers_base(OAUTH_ISSUER, "application/json")
            h["Content-Type"] = "application/json"
            h["Origin"] = OAUTH_ISSUER
            h.update(_make_trace_headers())
            try:
                r = self.session.post(
                    f"{OAUTH_ISSUER}/api/accounts/email-otp/validate",
                    json={"code": code}, headers=h, timeout=15
                )
                print(f"[*] Validate OTP: {r.status_code}")
                if r.status_code != 200:
                    return None
            except Exception as e:
                print(f"[!] OTP 验证异常: {e}")
                return None

        self._random_delay(1.0, 2.0)
        print("\n[*] Step 7: Create Account...")
        for create_retry in range(4):
            h = self._headers_base(OAUTH_ISSUER, "application/json")
            h["Content-Type"] = "application/json"
            h["Origin"] = OAUTH_ISSUER
            h.update(_make_trace_headers())
            # 生成 sentinel token
            sen = build_sentinel_token(
                self.session, self.device_id, flow="signup",
                user_agent=self.ua, sec_ch_ua=self.sec_ch_ua,
                impersonate=self.impersonate,
            )
            if sen:
                h["openai-sentinel-token"] = sen
            body = {"name": name, "birthdate": birthdate}
            try:
                r = self.session.post(
                    f"{OAUTH_ISSUER}/api/accounts/create_account",
                    json=body,
                    headers=h, timeout=15
                )
                print(f"[*] Create Account: {r.status_code}")
                if r.status_code == 200:
                    print("[*] 创建账户成功!")
                    break
                if "already" in (r.text or "").lower():
                    print("[*] 账号已存在，视为成功")
                    break
                if create_retry < 2:
                    self._random_delay(1.5, 2.5)
                    continue
            except Exception as e:
                print(f"[!] Create Account 异常: {e}")
                if create_retry < 2:
                    self._random_delay(1.5, 2.5)
                    continue
                return None

        self._random_delay(1.0, 2.0)
        # Step 8: OAuth
        print("\n[*] Step 8: OAuth 获取 Token...")
        tokens = self.perform_codex_oauth_login_http(email, password, name, birthdate) or {}

        return {"email": email, "password": password, "tokens": tokens}


class SyncedOpenAIRegister(OpenAIRegister):
    def __init__(self):
        self.BASE = BASE.rstrip("/")
        self.AUTH = OAUTH_ISSUER.rstrip("/")
        self._is_android = random.random() < 0.12
        (
            self.impersonate,
            self.chrome_major,
            self.chrome_full,
            self.ua,
            default_sec_ch_ua,
        ) = _random_chrome_version(android=self._is_android)
        self.sec_ch_ua = default_sec_ch_ua or _build_sec_ch_ua(self.chrome_major, android=self._is_android)
        self.fingerprint = _build_random_browser_fingerprint(
            self.chrome_full,
            chrome_major=self.chrome_major,
            impersonate=self.impersonate,
            android=self._is_android,
        )
        self.device_id = str(uuid.uuid4())
        self.auth_session_logging_id = str(uuid.uuid4())
        self._callback_url = None
        self._referer_chain = [f"{self.BASE}/"]
        self.session = self._create_browser_session()

    def _print(self, msg):
        with _print_lock:
            print(msg)

    def _log(self, step, method, url, status, body=None):
        lines = [
            "",
            "=" * 60,
            f"[Step] {step}",
            f"[{method}] {url}",
            f"[Status] {status}",
        ]
        if body is not None:
            try:
                lines.append(f"[Response] {json.dumps(body, indent=2, ensure_ascii=False)[:1000]}")
            except Exception:
                lines.append(f"[Response] {str(body)[:1000]}")
        lines.append("=" * 60)
        with _print_lock:
            print("\n".join(lines))

    @staticmethod
    def _response_payload(response):
        try:
            return response.json()
        except Exception:
            return {"text": (response.text or "")[:500]}

    def _set_cookie_for_domains(self, name, value, domains, session=None):
        target_session = session or self.session
        for domain in domains:
            try:
                target_session.cookies.set(name, value, domain=domain)
            except Exception:
                pass

    def _init_cookies(self, session=None):
        target_session = session or self.session
        ts = int(time.time())
        self._set_cookie_for_domains("__cf_bm", f"fake_{secrets.token_hex(16)}-{ts}", [".openai.com", ".auth.openai.com", "auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("_cfuvid", f"fake_{secrets.token_hex(20)}-{ts}", [".openai.com", ".auth.openai.com", "auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("oai-did", self.device_id, [".openai.com", "chatgpt.com", ".chatgpt.com", ".auth.openai.com", "auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("rg_context", "prim", [".openai.com", ".auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("iss_context", "default", [".openai.com", ".auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("__cflb", f"0H{secrets.token_hex(16)}", [".openai.com", ".auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("dclid", secrets.token_hex(16), [".openai.com"], session=target_session)
        self._set_cookie_for_domains("g_state", f"0_l:{ts}", [".openai.com"], session=target_session)
        self._set_cookie_for_domains("__Secure-next-auth.callback-url", self.BASE, [".auth.openai.com", "auth.openai.com"], session=target_session)
        self._set_cookie_for_domains("__Secure-next-auth.session-token", secrets.token_hex(32), [".auth.openai.com", "auth.openai.com"], session=target_session)

    def _random_delay(self, lo=0.5, hi=1.5):
        _human_delay(lo, hi)

    def _client_hint_headers(self):
        fp = self.fingerprint
        vw = max(320, int(getattr(fp, "screen_width", 1366)))
        vh = max(240, int(getattr(fp, "screen_height", 768)))
        dpr = max(0.5, min(4.0, float(getattr(fp, "device_pixel_ratio", 1.0))))
        mem = max(0.25, float(getattr(fp, "device_memory", 4)))
        headers = {
            "Sec-CH-Viewport-Width": str(vw),
            "Sec-CH-Viewport-Height": str(vh),
            "Sec-CH-DPR": str(dpr),
            "Sec-CH-Device-Memory": str(int(mem)),
        }
        if not getattr(fp, "is_android", False):
            headers["Sec-CH-UA-Form-Factors"] = '"Desktop"'
        if random.random() < 0.32:
            headers["Priority"] = "u=0, i"
        return headers

    def _headers_base(self, referer=None, extra_accept=None):
        headers = {
            "Accept": extra_accept or "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": self.fingerprint.accept_language,
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": self.fingerprint.dnt,
            "Sec-Ch-Ua": self.sec_ch_ua,
            "Sec-Ch-Ua-Mobile": self.fingerprint.sec_ch_ua_mobile,
            "Sec-Ch-Ua-Platform": self.fingerprint.sec_ch_ua_platform,
            "Sec-Ch-Ua-Platform-Version": self.fingerprint.sec_ch_ua_platform_version,
            "Sec-Ch-Ua-Arch": self.fingerprint.sec_ch_ua_arch,
            "Sec-Ch-Ua-Bitness": self.fingerprint.sec_ch_ua_bitness,
            "Sec-Ch-Ua-Full-Version": self.fingerprint.sec_ch_ua_full_version,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": self.ua,
        }
        if self.fingerprint.dnt in ("0", "1"):
            headers["DNT"] = self.fingerprint.dnt
        headers.update(self._client_hint_headers())
        if referer:
            headers["Referer"] = referer
        return headers

    def _build_request_headers(self, *, referer=None, origin=None, accept=None,
                               content_type=None, upgrade_insecure=False,
                               fetch_dest=None, fetch_mode=None, fetch_site=None,
                               include_trace=False, include_device_id=False,
                               extra=None):
        headers = self._headers_base(referer=referer, extra_accept=accept)
        if content_type:
            headers["Content-Type"] = content_type
        if origin:
            headers["Origin"] = origin
        if upgrade_insecure:
            headers["Upgrade-Insecure-Requests"] = "1"
        if fetch_dest:
            headers["Sec-Fetch-Dest"] = fetch_dest
        if fetch_mode:
            headers["Sec-Fetch-Mode"] = fetch_mode
        if fetch_site:
            headers["Sec-Fetch-Site"] = fetch_site
        if include_device_id:
            headers["oai-device-id"] = self.device_id
        if include_trace:
            headers.update(_make_trace_headers())
        if extra:
            headers.update(extra)
        return {k: v for k, v in headers.items() if v is not None}

    def _create_browser_session(self):
        session = requests.Session(impersonate=self.impersonate)
        if _current_proxy:
            session.proxies = _proxies()
        session.headers.update(self._build_request_headers())
        self._init_cookies(session=session)
        return session

    def _update_referer(self, url):
        if not url:
            return
        self._referer_chain.append(url)
        if len(self._referer_chain) > 5:
            self._referer_chain.pop(0)

    def _warm_cookies(self):
        self._random_delay(0.3, 0.8)
        try:
            self.session.get(
                "https://www.google.com/",
                headers={"User-Agent": self.ua, "Accept": "text/html"},
                timeout=8,
                impersonate=self.impersonate,
            )
        except Exception:
            pass

    def _pre_auth_sequence(self):
        pages = [
            (f"{self.BASE}/", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            (f"{self.BASE}/models", "application/json"),
            (f"{self.BASE}/", "text/html"),
        ]
        for page_url, accept in pages:
            self._random_delay(0.4, 1.2)
            try:
                self.session.get(
                    page_url,
                    headers=self._headers_base(
                        referer=self._referer_chain[-1] if self._referer_chain else None,
                        extra_accept=accept,
                    ),
                    timeout=10,
                    impersonate=self.impersonate,
                )
            except Exception:
                pass
            self._update_referer(page_url)

    def _reset_oauth_session(self):
        self.session = self._create_browser_session()
        self._callback_url = None
        self._referer_chain = [f"{self.BASE}/"]
        self._warm_cookies()

    def _reset_session(self):
        self.session = self._create_browser_session()
        self._callback_url = None
        self._referer_chain = [f"{self.BASE}/"]
        self._warm_cookies()

    @staticmethod
    def _is_transient_tls_error(exc):
        text = str(exc or "").lower()
        return any(
            marker in text
            for marker in (
                "curl: (35)",
                "tls connect error",
                "ssl connect error",
                "openssl_internal",
                "failed to perform",
            )
        )

    def _session_get_with_retry(self, url, *, step, max_attempts=3, **kwargs):
        last_exc = None
        for attempt in range(1, max_attempts + 1):
            try:
                return self.session.get(url, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt >= max_attempts or not self._is_transient_tls_error(exc):
                    raise
                self._print(f"[{step}] transient TLS error, retry {attempt}/{max_attempts - 1}")
                time.sleep(min(2.5, 0.6 * attempt + random.uniform(0.2, 0.5)))
        raise last_exc

    def visit_homepage(self):
        url = f"{self.BASE}/"
        headers = self._build_request_headers(
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            referer=self._referer_chain[-1] if self._referer_chain else None,
            upgrade_insecure=True,
            fetch_dest="document",
            fetch_mode="navigate",
            fetch_site="none",
        )
        response = self.session.get(url, headers=headers, allow_redirects=True, timeout=20, impersonate=self.impersonate)
        self._log("Visit homepage", "GET", url, response.status_code, {"final_url": str(response.url)})
        self._update_referer(str(response.url) or url)

    def get_csrf(self):
        url = f"{self.BASE}/api/auth/csrf"
        headers = self._build_request_headers(
            accept="application/json",
            referer=f"{self.BASE}/",
            fetch_dest="empty",
            fetch_mode="cors",
            fetch_site="same-origin",
        )
        for attempt in range(2):
            response = self.session.get(url, headers=headers, timeout=20, impersonate=self.impersonate)
            data = self._response_payload(response)
            token = data.get("csrfToken", "") if isinstance(data, dict) else ""
            if token:
                self._log("Get CSRF", "GET", url, response.status_code, data)
                self._update_referer(url)
                return token
            if attempt == 0:
                self._print("[CSRF] retry after homepage refresh")
                self._random_delay(0.4, 1.0)
                try:
                    self.visit_homepage()
                except Exception:
                    pass
                continue
            raise Exception(f"failed to get csrf token: {data}")
        raise Exception("failed to get csrf token")

    def signin(self, email, csrf):
        url = f"{self.BASE}/api/auth/signin/openai"
        params = {
            "prompt": "login",
            "ext-oai-did": self.device_id,
            "auth_session_logging_id": self.auth_session_logging_id,
            "screen_hint": "login_or_signup",
            "login_hint": email,
        }
        form_data = {"callbackUrl": f"{self.BASE}/", "csrfToken": csrf, "json": "true"}
        headers = self._build_request_headers(
            accept="application/json",
            content_type="application/x-www-form-urlencoded",
            referer=f"{self.BASE}/",
            origin=self.BASE,
            fetch_dest="empty",
            fetch_mode="cors",
            fetch_site="same-origin",
        )
        response = self.session.post(url, params=params, data=form_data, headers=headers, timeout=20, impersonate=self.impersonate)
        data = self._response_payload(response)
        authorize_url = data.get("url", "") if isinstance(data, dict) else ""
        self._log("Signin", "POST", url, response.status_code, data)
        if not authorize_url:
            raise Exception(f"failed to get authorize url: {data}")
        self._update_referer(authorize_url)
        return authorize_url

    def authorize(self, url):
        headers = self._build_request_headers(
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            referer=self._referer_chain[-1] if self._referer_chain else f"{self.BASE}/",
            upgrade_insecure=True,
            fetch_dest="document",
            fetch_mode="navigate",
            fetch_site="cross-site",
        )
        response = self._session_get_with_retry(url, step="Authorize", headers=headers, allow_redirects=True, timeout=30, impersonate=self.impersonate)
        final_url = str(response.url)
        self._log("Authorize", "GET", url, response.status_code, {"final_url": final_url})
        self._update_referer(final_url)
        return final_url

    def register_request(self, email, password):
        url = f"{self.AUTH}/api/accounts/user/register"
        headers = self._build_request_headers(
            accept="application/json",
            content_type="application/json",
            referer=f"{self.AUTH}/create-account/password",
            origin=self.AUTH,
            fetch_dest="empty",
            fetch_mode="cors",
            fetch_site="same-origin",
            include_trace=True,
        )
        response = self.session.post(url, json={"username": email, "password": password}, headers=headers, timeout=20, impersonate=self.impersonate)
        data = self._response_payload(response)
        self._log("Register", "POST", url, response.status_code, data)
        if isinstance(data, dict):
            callback_url = data.get("continue_url") or data.get("url") or data.get("redirect_url")
            if callback_url:
                self._callback_url = callback_url
        return response.status_code, data

    def send_otp(self):
        url = f"{self.AUTH}/api/accounts/email-otp/send"
        headers = self._build_request_headers(
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            referer=f"{self.AUTH}/create-account/password",
            upgrade_insecure=True,
            fetch_dest="document",
            fetch_mode="navigate",
            fetch_site="same-origin",
        )
        response = self.session.get(url, headers=headers, allow_redirects=True, timeout=20, impersonate=self.impersonate)
        data = self._response_payload(response)
        self._log("Send OTP", "GET", url, response.status_code, data)
        return response.status_code, data

    def validate_otp(self, code):
        url = f"{self.AUTH}/api/accounts/email-otp/validate"
        headers = self._build_request_headers(
            accept="application/json",
            content_type="application/json",
            referer=f"{self.AUTH}/email-verification",
            origin=self.AUTH,
            fetch_dest="empty",
            fetch_mode="cors",
            fetch_site="same-origin",
            include_trace=True,
        )
        response = self.session.post(url, json={"code": code}, headers=headers, timeout=20, impersonate=self.impersonate)
        data = self._response_payload(response)
        self._log("Validate OTP", "POST", url, response.status_code, data)
        if isinstance(data, dict):
            callback_url = data.get("continue_url") or data.get("url") or data.get("redirect_url")
            if callback_url:
                self._callback_url = callback_url
        return response.status_code, data

    def create_account(self, name, birthdate):
        url = f"{self.AUTH}/api/accounts/create_account"
        last_status = 0
        last_data = {}
        for create_retry in range(4):
            headers = self._build_request_headers(
                accept="application/json",
                content_type="application/json",
                referer=f"{self.AUTH}/about-you",
                origin=self.AUTH,
                fetch_dest="empty",
                fetch_mode="cors",
                fetch_site="same-origin",
                include_trace=True,
            )
            sentinel_token = build_sentinel_token(
                self.session,
                self.device_id,
                flow="signup",
                user_agent=self.ua,
                sec_ch_ua=self.sec_ch_ua,
                impersonate=self.impersonate,
                fingerprint=self.fingerprint,
            )
            if sentinel_token:
                headers["openai-sentinel-token"] = sentinel_token
            try:
                response = self.session.post(url, json={"name": name, "birthdate": birthdate}, headers=headers, timeout=20, impersonate=self.impersonate)
            except Exception as exc:
                last_status = 0
                last_data = {"text": f"create_account exception: {exc}"}
                self._print(f"[Register] create_account exception: {exc}")
                if create_retry < 2:
                    self._random_delay(1.5, 2.5)
                    continue
                break
            data = self._response_payload(response)
            self._log("Create Account", "POST", url, response.status_code, data)
            last_status = response.status_code
            last_data = data
            if isinstance(data, dict):
                callback_url = data.get("continue_url") or data.get("url") or data.get("redirect_url")
                if callback_url:
                    self._callback_url = callback_url
            if response.status_code == 200:
                return response.status_code, data
            if "already" in (response.text or "").lower():
                self._print("[Register] account already exists, treat as success")
                return 200, data
            if create_retry < 2:
                self._random_delay(1.5, 2.5)
        return last_status, last_data

    def callback(self, url=None):
        url = url or self._callback_url
        if not url:
            return None, None
        headers = self._build_request_headers(
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            referer=self._referer_chain[-1] if self._referer_chain else f"{self.BASE}/",
            upgrade_insecure=True,
            fetch_dest="document",
            fetch_mode="navigate",
            fetch_site="same-origin",
        )
        response = self.session.get(url, headers=headers, allow_redirects=True, timeout=20, impersonate=self.impersonate)
        data = {"final_url": str(response.url)}
        self._log("Callback", "GET", url, response.status_code, data)
        self._update_referer(str(response.url) or url)
        return response.status_code, data

    @staticmethod
    def _oauth_requires_password_verify(continue_url, page_type):
        page = str(page_type or "").strip().lower()
        url = str(continue_url or "").strip().lower()
        later_step_page_hints = ("email_otp_verification", "about_you", "consent", "organization", "workspace")
        later_step_url_hints = ("/email-verification", "/email-otp", "/about-you", "/sign-in-with-chatgpt", "/workspace", "/organization", "/consent")
        if any(hint in page for hint in later_step_page_hints):
            return False
        if any(hint in url for hint in later_step_url_hints):
            return False
        if "password" in page:
            return True
        if "/log-in/password" in url or "/password" in url:
            return True
        return True

    def _oauth_follow_for_code(self, start_url, referer=None, max_hops=16):
        headers = self._build_request_headers(
            accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            referer=referer,
            upgrade_insecure=True,
            fetch_dest="document",
            fetch_mode="navigate",
            fetch_site="same-origin",
        )
        current_url = start_url
        last_url = start_url
        for _ in range(max_hops):
            try:
                response = self._session_get_with_retry(current_url, step="OAuth Follow", headers=headers, allow_redirects=False, timeout=30, impersonate=self.impersonate)
            except Exception as exc:
                maybe_localhost = re.search(r'(https?://localhost[^\s\'"]+)', str(exc))
                if maybe_localhost:
                    code = _extract_code_from_url(maybe_localhost.group(1))
                    if code:
                        return code, maybe_localhost.group(1)
                return None, last_url
            last_url = str(response.url)
            self._update_referer(last_url)
            code = _extract_code_from_url(last_url)
            if code:
                return code, last_url
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location", "")
                if not location:
                    return None, last_url
                if location.startswith("/"):
                    location = f"{OAUTH_ISSUER}{location}"
                code = _extract_code_from_url(location)
                if code:
                    return code, location
                current_url = location
                headers["Referer"] = last_url
                self._random_delay(0.3, 0.8)
                continue
            return None, last_url
        return None, last_url

    def _oauth_submit_workspace_and_org(self, consent_url):
        session_data = self._decode_oauth_session_cookie()
        if not session_data:
            return None
        workspaces = session_data.get("workspaces", [])
        if not workspaces:
            return None
        workspace_id = (workspaces[0] or {}).get("id")
        if not workspace_id:
            return None
        headers = self._build_request_headers(
            accept="application/json",
            content_type="application/json",
            origin=OAUTH_ISSUER,
            referer=consent_url,
            fetch_dest="empty",
            fetch_mode="cors",
            fetch_site="same-origin",
            include_trace=True,
            include_device_id=True,
        )
        response = self.session.post(
            f"{OAUTH_ISSUER}/api/accounts/workspace/select",
            json={"workspace_id": workspace_id},
            headers=headers,
            allow_redirects=False,
            timeout=30,
            impersonate=self.impersonate,
        )
        self._print(f"[OAuth] workspace/select -> {response.status_code}")
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            if location.startswith("/"):
                location = f"{OAUTH_ISSUER}{location}"
            code = _extract_code_from_url(location)
            if code:
                return code
            code, _ = self._oauth_follow_for_code(location, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(location, referer=consent_url)
            return code
        if response.status_code != 200:
            return None
        ws_data = self._response_payload(response)
        if not isinstance(ws_data, dict):
            return None
        ws_next = ws_data.get("continue_url", "")
        orgs = ws_data.get("data", {}).get("orgs", [])
        org_id = None
        project_id = None
        if orgs:
            org_id = (orgs[0] or {}).get("id")
            projects = (orgs[0] or {}).get("projects", [])
            if projects:
                project_id = (projects[0] or {}).get("id")
        if org_id:
            org_body = {"org_id": org_id}
            if project_id:
                org_body["project_id"] = project_id
            org_headers = dict(headers)
            if ws_next:
                org_headers["Referer"] = ws_next if ws_next.startswith("http") else f"{OAUTH_ISSUER}{ws_next}"
            response_org = self.session.post(
                f"{OAUTH_ISSUER}/api/accounts/organization/select",
                json=org_body,
                headers=org_headers,
                allow_redirects=False,
                timeout=30,
                impersonate=self.impersonate,
            )
            self._print(f"[OAuth] organization/select -> {response_org.status_code}")
            if response_org.status_code in (301, 302, 303, 307, 308):
                location = response_org.headers.get("Location", "")
                if location.startswith("/"):
                    location = f"{OAUTH_ISSUER}{location}"
                code = _extract_code_from_url(location)
                if code:
                    return code
                code, _ = self._oauth_follow_for_code(location, referer=org_headers.get("Referer"))
                if not code:
                    code = self._oauth_allow_redirect_extract_code(location, referer=org_headers.get("Referer"))
                return code
            if response_org.status_code == 200:
                org_data = self._response_payload(response_org)
                if not isinstance(org_data, dict):
                    return None
                org_next = org_data.get("continue_url", "")
                if org_next:
                    if org_next.startswith("/"):
                        org_next = f"{OAUTH_ISSUER}{org_next}"
                    code, _ = self._oauth_follow_for_code(org_next, referer=org_headers.get("Referer"))
                    if not code:
                        code = self._oauth_allow_redirect_extract_code(org_next, referer=org_headers.get("Referer"))
                    return code
        if ws_next:
            if ws_next.startswith("/"):
                ws_next = f"{OAUTH_ISSUER}{ws_next}"
            code, _ = self._oauth_follow_for_code(ws_next, referer=consent_url)
            if not code:
                code = self._oauth_allow_redirect_extract_code(ws_next, referer=consent_url)
            return code
        return None

    def perform_codex_oauth_login_http(self, email, password, name="OpenAI User",
                                        birthdate="1995-01-01", _allow_restart=True):
        self._print("[OAuth] start Codex OAuth flow")
        self._reset_oauth_session()
        try:
            self._pre_auth_sequence()
        except Exception:
            pass
        code_verifier, code_challenge = _generate_pkce()
        state = secrets.token_urlsafe(24)
        authorize_params = {
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": "openid profile email offline_access",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "prompt": "login",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        }
        authorize_url = f"{OAUTH_ISSUER}/oauth/authorize?{urlencode(authorize_params)}"

        def _oauth_json_headers(referer):
            return self._build_request_headers(
                accept="application/json",
                content_type="application/json",
                origin=OAUTH_ISSUER,
                referer=referer,
                fetch_dest="empty",
                fetch_mode="cors",
                fetch_site="same-origin",
                include_trace=True,
                include_device_id=True,
            )

        def _bootstrap_oauth_session():
            self._print("[OAuth] 1/7 GET /oauth/authorize")
            try:
                headers = self._build_request_headers(
                    accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    referer=f"{self.BASE}/",
                    upgrade_insecure=True,
                    fetch_dest="document",
                    fetch_mode="navigate",
                    fetch_site="cross-site",
                )
                response = self._session_get_with_retry(authorize_url, step="OAuth Authorize", headers=headers, allow_redirects=True, timeout=30, impersonate=self.impersonate)
            except Exception as exc:
                self._print(f"[OAuth] /oauth/authorize exception: {exc}")
                return False, ""
            final_url = str(response.url)
            has_login = any(getattr(cookie, "name", "") == "login_session" for cookie in self.session.cookies)
            if not has_login:
                oauth2_url = f"{OAUTH_ISSUER}/api/oauth/oauth2/auth"
                try:
                    headers_oauth2 = self._build_request_headers(
                        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        referer=authorize_url,
                        upgrade_insecure=True,
                        fetch_dest="document",
                        fetch_mode="navigate",
                        fetch_site="same-origin",
                    )
                    response_oauth2 = self._session_get_with_retry(oauth2_url, step="OAuth OAuth2", headers=headers_oauth2, params=authorize_params, allow_redirects=True, timeout=30, impersonate=self.impersonate)
                    final_url = str(response_oauth2.url)
                except Exception as exc:
                    self._print(f"[OAuth] /api/oauth/oauth2/auth exception: {exc}")
                has_login = any(getattr(cookie, "name", "") == "login_session" for cookie in self.session.cookies)
            if final_url:
                self._update_referer(final_url)
            return has_login, final_url

        def _post_authorize_continue(referer_url):
            sentinel_authorize = build_sentinel_token(
                self.session,
                self.device_id,
                flow="authorize_continue",
                user_agent=self.ua,
                sec_ch_ua=self.sec_ch_ua,
                impersonate=self.impersonate,
                fingerprint=self.fingerprint,
            )
            if not sentinel_authorize:
                self._print("[OAuth] failed to build authorize sentinel token")
                return None
            headers_continue = _oauth_json_headers(referer_url)
            headers_continue["openai-sentinel-token"] = sentinel_authorize
            try:
                return self.session.post(
                    f"{OAUTH_ISSUER}/api/accounts/authorize/continue",
                    json={"username": {"kind": "email", "value": email}},
                    headers=headers_continue,
                    timeout=30,
                    allow_redirects=False,
                    impersonate=self.impersonate,
                )
            except Exception as exc:
                self._print(f"[OAuth] authorize/continue exception: {exc}")
                return None

        _, authorize_final_url = _bootstrap_oauth_session()
        if not authorize_final_url:
            return None
        self._random_delay(1.0, 2.0)
        continue_referer = authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER) else f"{OAUTH_ISSUER}/log-in"
        self._print("[OAuth] 2/7 POST /api/accounts/authorize/continue")
        response_continue = _post_authorize_continue(continue_referer)
        if response_continue is None:
            return None
        self._print(f"[OAuth] /authorize/continue -> {response_continue.status_code}")
        if response_continue.status_code == 400 and "invalid_auth_step" in (response_continue.text or ""):
            self._random_delay(1.0, 2.0)
            _, authorize_final_url = _bootstrap_oauth_session()
            if not authorize_final_url:
                return None
            continue_referer = authorize_final_url if authorize_final_url.startswith(OAUTH_ISSUER) else f"{OAUTH_ISSUER}/log-in"
            response_continue = _post_authorize_continue(continue_referer)
            if response_continue is None:
                return None
        if response_continue.status_code != 200:
            self._print(f"[OAuth] authorize/continue failed: {response_continue.status_code}")
            return None
        continue_data = self._response_payload(response_continue)
        if not isinstance(continue_data, dict):
            return None
        continue_url = continue_data.get("continue_url", "")
        page_type = (continue_data.get("page") or {}).get("type", "")
        if self._oauth_requires_password_verify(continue_url, page_type):
            self._print("[OAuth] 3/7 POST /api/accounts/password/verify")
            sentinel_pwd = build_sentinel_token(
                self.session,
                self.device_id,
                flow="password_verify",
                user_agent=self.ua,
                sec_ch_ua=self.sec_ch_ua,
                impersonate=self.impersonate,
                fingerprint=self.fingerprint,
            )
            if not sentinel_pwd:
                return None
            headers_verify = _oauth_json_headers(f"{OAUTH_ISSUER}/log-in/password")
            headers_verify["openai-sentinel-token"] = sentinel_pwd
            try:
                response_verify = self.session.post(
                    f"{OAUTH_ISSUER}/api/accounts/password/verify",
                    json={"password": password},
                    headers=headers_verify,
                    timeout=30,
                    allow_redirects=False,
                    impersonate=self.impersonate,
                )
            except Exception as exc:
                self._print(f"[OAuth] password/verify exception: {exc}")
                return None
            if response_verify.status_code == 409 and "invalid_state" in (response_verify.text or "").lower():
                self._print("[OAuth] password/verify invalid_state, restart once")
                if _allow_restart:
                    self._random_delay(0.8, 1.4)
                    return self.perform_codex_oauth_login_http(email, password, name=name, birthdate=birthdate, _allow_restart=False)
                return None
            if response_verify.status_code != 200:
                self._print(f"[OAuth] password/verify failed: {response_verify.status_code}")
                return None
            verify_data = self._response_payload(response_verify)
            if not isinstance(verify_data, dict):
                return None
            continue_url = verify_data.get("continue_url", "") or continue_url
            page_type = (verify_data.get("page") or {}).get("type", "") or page_type
        else:
            self._print(f"[OAuth] 3/7 skip password/verify, page={page_type or '-'}")

        need_oauth_otp = (
            page_type == "email_otp_verification"
            or "email-verification" in (continue_url or "")
            or "email-otp" in (continue_url or "")
        )
        if need_oauth_otp:
            self._print("[OAuth] 4/7 email OTP detected")
            headers_otp = _oauth_json_headers(f"{OAUTH_ISSUER}/email-verification")
            tried_codes = set()
            otp_success = False
            otp_deadline = time.time() + 120
            while time.time() < otp_deadline and not otp_success:
                otp_code = wait_code(email, max_wait=60, interval=3)
                if not otp_code or otp_code in tried_codes:
                    self._random_delay(1.0, 2.0)
                    continue
                tried_codes.add(otp_code)
                self._print(f"[OAuth] trying OTP: {otp_code}")
                try:
                    response_otp = self.session.post(
                        f"{OAUTH_ISSUER}/api/accounts/email-otp/validate",
                        json={"code": otp_code},
                        headers=headers_otp,
                        timeout=30,
                        allow_redirects=False,
                        impersonate=self.impersonate,
                    )
                except Exception as exc:
                    self._print(f"[OAuth] email-otp/validate exception: {exc}")
                    self._random_delay(1.0, 2.0)
                    continue
                if response_otp.status_code != 200:
                    self._random_delay(1.0, 2.0)
                    continue
                otp_data = self._response_payload(response_otp)
                if not isinstance(otp_data, dict):
                    continue
                continue_url = otp_data.get("continue_url", "") or continue_url
                page_type = (otp_data.get("page") or {}).get("type", "") or page_type
                otp_success = True
            if not otp_success:
                self._print("[OAuth] email OTP validation failed")
                return None

        return self._finalize_oauth_flow(continue_url, page_type, code_verifier, name, birthdate)

    def _finalize_oauth_flow(self, continue_url, page_type, code_verifier, name, birthdate):
        needs_about_you = page_type == "about_you" or "/about-you" in (continue_url or "")
        if needs_about_you:
            self._print("[OAuth] 4b/7 submit about-you")
            for about_retry in range(3):
                headers_about = self._build_request_headers(
                    accept="application/json",
                    content_type="application/json",
                    origin=OAUTH_ISSUER,
                    referer=f"{OAUTH_ISSUER}/about-you",
                    fetch_dest="empty",
                    fetch_mode="cors",
                    fetch_site="same-origin",
                    include_trace=True,
                    include_device_id=True,
                )
                sentinel_about = build_sentinel_token(
                    self.session,
                    self.device_id,
                    flow="about_you",
                    user_agent=self.ua,
                    sec_ch_ua=self.sec_ch_ua,
                    impersonate=self.impersonate,
                    fingerprint=self.fingerprint,
                )
                if sentinel_about:
                    headers_about["openai-sentinel-token"] = sentinel_about
                try:
                    response_about = self.session.post(
                        f"{OAUTH_ISSUER}/api/accounts/create_account",
                        json={"name": name, "birthdate": birthdate},
                        headers=headers_about,
                        timeout=30,
                        allow_redirects=False,
                        impersonate=self.impersonate,
                    )
                except Exception as exc:
                    self._print(f"[OAuth] about-you exception: {exc}")
                    if about_retry < 2:
                        self._random_delay(1.5, 2.5)
                        continue
                    break
                self._print(f"[OAuth] about-you -> {response_about.status_code}")
                if response_about.status_code == 200:
                    about_data = self._response_payload(response_about)
                    if isinstance(about_data, dict):
                        new_continue = about_data.get("continue_url", "")
                        new_page = (about_data.get("page") or {}).get("type", "")
                        if new_continue:
                            continue_url = new_continue
                            if new_continue.startswith("/"):
                                new_continue = f"{OAUTH_ISSUER}{new_continue}"
                            self._oauth_follow_for_code(new_continue, referer=f"{OAUTH_ISSUER}/about-you")
                        if new_page:
                            page_type = new_page
                    break
                if response_about.status_code in (301, 302, 303, 307, 308):
                    location = response_about.headers.get("Location", "")
                    if location.startswith("/"):
                        location = f"{OAUTH_ISSUER}{location}"
                    if location:
                        continue_url = location
                        page_type = ""
                    self._oauth_follow_for_code(location, referer=f"{OAUTH_ISSUER}/about-you")
                    break
                if "already" in (response_about.text or "").lower():
                    break
                if about_retry < 2:
                    self._random_delay(1.5, 2.5)

        code = None
        consent_url = continue_url
        if consent_url and consent_url.startswith("/"):
            consent_url = f"{OAUTH_ISSUER}{consent_url}"
        if not consent_url and "consent" in page_type:
            consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
        if consent_url:
            code = _extract_code_from_url(consent_url)
        if not code and consent_url:
            self._print("[OAuth] 5/7 follow continue_url for code")
            code, _ = self._oauth_follow_for_code(consent_url, referer=f"{OAUTH_ISSUER}/log-in/password")
        consent_hint = (
            ("consent" in (consent_url or ""))
            or ("sign-in-with-chatgpt" in (consent_url or ""))
            or ("workspace" in (consent_url or ""))
            or ("organization" in (consent_url or ""))
            or ("consent" in page_type)
            or ("organization" in page_type)
        )
        if not code and consent_hint:
            if not consent_url:
                consent_url = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            self._print("[OAuth] 6/7 workspace/org selection")
            code = self._oauth_submit_workspace_and_org(consent_url)
        if not code:
            fallback_consent = f"{OAUTH_ISSUER}/sign-in-with-chatgpt/codex/consent"
            self._print("[OAuth] 6/7 fallback consent path")
            code = self._oauth_submit_workspace_and_org(fallback_consent)
            if not code:
                code, _ = self._oauth_follow_for_code(fallback_consent, referer=f"{OAUTH_ISSUER}/log-in/password")
        if not code:
            self._print("[OAuth] failed to get authorization code")
            return None
        self._random_delay(0.5, 1.0)
        self._print("[OAuth] 7/7 POST /oauth/token")
        token_headers = self._headers_base(OAUTH_ISSUER)
        token_headers["Content-Type"] = "application/x-www-form-urlencoded"
        token_response = self.session.post(
            f"{OAUTH_ISSUER}/oauth/token",
            headers=token_headers,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "client_id": OAUTH_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            timeout=60,
            impersonate=self.impersonate,
        )
        self._print(f"[OAuth] /oauth/token -> {token_response.status_code}")
        if token_response.status_code != 200:
            self._print(f"[OAuth] token exchange failed: {token_response.status_code}")
            return None
        token_data = self._response_payload(token_response)
        if not isinstance(token_data, dict) or not token_data.get("access_token"):
            return None
        self._print("[OAuth] Codex token acquired")
        return token_data

    def register(self, email, password, name="OpenAI User", birthdate="1995-01-01"):
        self._print(f"\n[*] email: {email}")
        self._print(f"[*] password: {password}")
        self._print(f"[*] name: {name}, birthdate: {birthdate}")
        self._print(f"[*] ua: {self.ua}")
        self._print(f"[*] impersonate: {self.impersonate}")
        self._reset_session()
        try:
            self._pre_auth_sequence()
        except Exception:
            pass
        self._random_delay(0.8, 1.5)
        self._print("\n[*] Step 0: Visit homepage")
        try:
            self.visit_homepage()
        except Exception as exc:
            self._print(f"[Homepage] best-effort failure: {exc}")
        self._random_delay(0.8, 1.5)
        self._print("[*] Step 1: Get CSRF")
        try:
            csrf = self.get_csrf()
        except Exception as exc:
            self._print(f"[FAIL] csrf error: {exc}")
            return None
        self._random_delay(0.8, 1.5)
        self._print("[*] Step 2: Signin")
        try:
            authorize_url = self.signin(email, csrf)
        except Exception as exc:
            self._print(f"[FAIL] signin error: {exc}")
            return None
        need_otp = False
        ready_for_create_account = False
        registration_completed = False
        authorize_retry = 3
        while authorize_retry > 0:
            self._print("[*] Step 3: Authorize")
            try:
                final_url = self.authorize(authorize_url)
            except Exception as exc:
                self._print(f"[Authorize] error: {exc}")
                final_url = authorize_url
            final_path = urlparse(final_url).path
            self._print(f"[*] final path: {final_path}")
            self._random_delay(1.0, 2.0)
            if "create-account/password" in final_path:
                status, data = self.register_request(email, password)
                text_blob = json.dumps(data, ensure_ascii=False).lower() if isinstance(data, dict) else str(data).lower()
                if status == 200 or "already" in text_blob:
                    need_otp = True
                    break
                authorize_retry -= 1
                if authorize_retry > 0:
                    self._print(f"[*] retry Step 3 after register miss ({authorize_retry} left)")
                    time.sleep(10)
                continue
            if "email-verification" in final_path or "email-otp" in final_path:
                need_otp = True
                break
            if "callback" in final_path or "chatgpt.com" in final_url:
                self._print("[*] account already completed registration")
                registration_completed = True
                break
            if "about-you" in final_path:
                ready_for_create_account = True
                break
            authorize_retry -= 1
            if authorize_retry > 0:
                self._print(f"[*] retry Step 3 for unexpected path ({authorize_retry} left)")
                time.sleep(10)
        if authorize_retry == 0 and not (need_otp or ready_for_create_account or registration_completed):
            self._print("[FAIL] authorize retries exhausted")
            return None
        if need_otp:
            self._random_delay(1.0, 2.0)
            self._print("\n[*] Step 5: Send OTP")
            try:
                self.send_otp()
            except Exception:
                pass
            self._random_delay(2.0, 4.0)
            self._print("\n[*] Step 6: Validate OTP")
            code = wait_code(email)
            if not code:
                return None
            self._random_delay(0.8, 1.5)
            status, _ = self.validate_otp(code)
            if status != 200:
                self._print("[*] OTP validation failed, resend once")
                try:
                    self.send_otp()
                except Exception:
                    pass
                self._random_delay(1.0, 2.0)
                code = wait_code(email, max_wait=60, interval=3)
                if not code:
                    return None
                self._random_delay(0.8, 1.5)
                status, _ = self.validate_otp(code)
                if status != 200:
                    self._print("[FAIL] OTP validation failed")
                    return None
            ready_for_create_account = True
        if ready_for_create_account:
            self._random_delay(1.0, 2.0)
            self._print("\n[*] Step 7: Create Account")
            status, _ = self.create_account(name, birthdate)
            if status != 200:
                return None
            if self._callback_url:
                try:
                    self.callback()
                except Exception:
                    pass
        tokens = {}
        if ENABLE_OAUTH:
            self._random_delay(1.0, 2.0)
            self._print("\n[*] Step 8: OAuth token")
            tokens = self.perform_codex_oauth_login_http(email, password, name, birthdate) or {}
            if OAUTH_REQUIRED and not tokens.get("access_token"):
                self._print("[FAIL] OAuth required but token acquisition failed")
                return None
        else:
            self._print("[*] Step 8: OAuth disabled by config")
        return {"email": email, "password": password, "tokens": tokens}


OpenAIRegister = SyncedOpenAIRegister


def save_account(email, password, tokens=None):
    tokens = tokens or {}
    has_token = bool(tokens.get("access_token"))
    target_dir = ACCOUNTS_WITH_TOKEN_DIR if has_token else ACCOUNTS_WITHOUT_TOKEN_DIR
    os.makedirs(target_dir, exist_ok=True)
    ts = int(time.time())
    path = os.path.join(target_dir, f"account_{email.replace('@', '_')}_{ts}.json")

    data = {"email": email, "password": password}

    with _file_lock:
        if has_token:
            from datetime import datetime, timedelta, timezone

            access_token = tokens.get("access_token", "")
            refresh_token = tokens.get("refresh_token", "")
            id_token = tokens.get("id_token", "")
            payload = _decode_jwt_payload(access_token) if access_token else {}
            auth_info = payload.get("https://api.openai.com/auth", {}) if isinstance(payload, dict) else {}
            account_id = auth_info.get("chatgpt_account_id", "") if isinstance(auth_info, dict) else ""
            expired = ""
            exp_timestamp = payload.get("exp") if isinstance(payload, dict) else None
            if isinstance(exp_timestamp, int) and exp_timestamp > 0:
                exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone(timedelta(hours=8)))
                expired = exp_dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
            now = datetime.now(tz=timezone(timedelta(hours=8)))
            os.makedirs(TOKEN_JSON_DIR, exist_ok=True)
            token_data = {
                "type": "codex",
                "email": email,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "id_token": id_token,
                "account_id": account_id,
                "expired": expired,
                "last_refresh": now.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            }
            token_file = os.path.join(TOKEN_JSON_DIR, f"{email}.json")
            with open(token_file, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2, ensure_ascii=False)
            print(f"[*] Token 保存: {token_file}")

            at = access_token
            rt = refresh_token
            if at:
                _ensure_parent_dir(AK_FILE)
                with open(AK_FILE, "a", encoding="utf-8") as f:
                    f.write(at + "\n")
                print(f"[*] AK 追加: {AK_FILE}")
            if rt:
                _ensure_parent_dir(RK_FILE)
                with open(RK_FILE, "a", encoding="utf-8") as f:
                    f.write(rt + "\n")
                print(f"[*] RK 追加: {RK_FILE}")
            data["access_token"] = at

        _ensure_parent_dir(path)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[*] 账号保存: {path}")
    return path

def run(domain=None, proxy=None, show_header=True):
    """单账号注册，支持外部覆盖域名和代理"""
    global _current_proxy, _current_domain
    if domain is not None:
        _current_domain = domain
    if proxy is not None:
        _current_proxy = proxy

    if show_header:
        print("\n" + "=" * 50)
        print("[*] 注册 (反风控版)")
        print(f"[*] 域名: {_current_domain}")
        print("=" * 50)

    # 启动前随机等待，模拟真人启动浏览器
    time.sleep(random.uniform(2.0, 6.0))

    names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie", "Skyler"]
    surnames = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson"]
    name = random.choice(names) + " " + random.choice(surnames)
    birthdate = f"{random.randint(1994, 2004)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    email = generate_email()
    password = generate_password()

    reg = OpenAIRegister()
    result = reg.register(email, password, name, birthdate)

    if result:
        save_account(result["email"], result["password"], result.get("tokens"))
        if show_header:
            print(f"\n{'=' * 50}")
            print("[SUCCESS] 注册完成!")
            print(f"[*] 邮箱: {result['email']}")
            print(f"[*] 密码: {result['password']}")
            if result.get("tokens", {}).get("access_token"):
                print("[*] Codex Token: 获取成功!")
            print(f"{'=' * 50}")
    else:
        if show_header:
            print(f"\n{'=' * 50}")
            print("[FAIL] 注册失败")
            print(f"{'=' * 50}")

    return result

def _should_pause(no_pause: bool = False) -> bool:
    if no_pause or _as_bool(os.environ.get("CODEX_REGISTER_NO_PAUSE")):
        return False
    if getattr(sys, "frozen", False):
        return False
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _pause_before_exit_if_needed() -> None:
    if not getattr(sys, "frozen", False):
        return
    if "--no-pause" in sys.argv:
        return
    if _as_bool(os.environ.get("CODEX_REGISTER_NO_PAUSE")):
        return
    try:
        input("\n按 Enter 键退出...")
    except EOFError:
        pass
    except KeyboardInterrupt:
        pass


def _is_interactive() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _prompt_positive_int(prompt: str, default: int) -> int:
    raw = input(prompt).strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


def _choose_proxy_interactively(default_proxy):
    proxy = default_proxy
    if proxy:
        print(f"[Info] 检测到默认代理: {proxy}")
        use_default = input("使用此代理? (Y/n): ").strip().lower()
        if use_default == "n":
            proxy = input("输入代理地址 (留空=不使用代理): ").strip() or None
    else:
        env_proxy = (
            os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
        )
        if env_proxy:
            print(f"[Info] 检测到环境变量代理: {env_proxy}")
            use_env = input("使用此代理? (Y/n): ").strip().lower()
            proxy = None if use_env == "n" else env_proxy
            if use_env == "n":
                proxy = input("输入代理地址 (留空=不使用代理): ").strip() or None
        else:
            proxy = input("输入代理地址 (如 http://127.0.0.1:7890，留空=不使用代理): ").strip() or None

    print(f"[Info] {'使用代理: ' + proxy if proxy else '不使用代理'}")
    return proxy


def _quick_preflight(proxy: str = None) -> bool:
    print("\n[Preflight] 开始连通性检查...")
    sess = requests.Session(impersonate="chrome131")
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}

    checks = []

    def _record(name: str, ok: bool, detail: str):
        checks.append((name, ok, detail))
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}: {detail}")

    try:
        r = sess.get(f"{BASE}/", timeout=20, allow_redirects=True)
        _record("chatgpt.com", r.status_code != 403, f"status={r.status_code}")
    except Exception as e:
        _record("chatgpt.com", False, f"异常: {e}")

    try:
        r = sess.get(
            f"{BASE}/api/auth/csrf",
            headers={"Accept": "application/json", "Referer": f"{BASE}/"},
            timeout=20,
        )
        data = r.json()
        token = data.get("csrfToken", "") if isinstance(data, dict) else ""
        _record("chatgpt csrf", bool(token), f"status={r.status_code}, token={'yes' if token else 'no'}")
    except Exception as e:
        _record("chatgpt csrf", False, f"非 JSON 或异常: {e}")

    try:
        r = sess.get(f"{OAUTH_ISSUER}/", timeout=20, allow_redirects=True)
        _record("auth.openai.com", r.status_code < 500, f"status={r.status_code}")
    except Exception as e:
        _record("auth.openai.com", False, f"异常: {e}")

    try:
        r = std_requests.get(
            _build_verify_lookup_url(f"preflight@{_current_domain}"),
            timeout=15,
            headers={"Accept": "application/json", "User-Agent": _random_ua()},
        )
        _record("verify api", r.status_code < 500, f"status={r.status_code}")
    except Exception as e:
        _record("verify api", False, f"异常: {e}")

    all_ok = all(ok for _, ok, _ in checks)
    if all_ok:
        print("[Preflight] 通过，开始注册。")
    else:
        print("[Preflight] 未通过，建议先更换代理或降低并发后再试。")
    return all_ok


def _run_one(idx, total, domain=None, proxy=None):
    try:
        with _print_lock:
            print(f"\n{'=' * 60}")
            print(f"  [{idx}/{total}] 开始注册")
            print(f"  域名: {domain or _current_domain}")
            print(f"  代理: {proxy or '不使用代理'}")
            print(f"{'=' * 60}")
        result = run(domain=domain, proxy=proxy, show_header=(total == 1))
        if result:
            return True, result.get("email"), None
        return False, None, "注册流程返回空结果"
    except Exception as e:
        with _print_lock:
            print(f"\n[FAIL] [{idx}] 注册异常: {e}")
            traceback.print_exc()
        return False, None, str(e)


def run_batch(total_accounts: int = 1, max_workers: int = 1, domain=None, proxy=None):
    total_accounts = max(1, int(total_accounts or 1))
    actual_workers = max(1, min(int(max_workers or 1), total_accounts))

    print(f"\n{'#' * 60}")
    print("  OpenAI 批量注册 (完整反风控版)")
    print(f"  注册数量: {total_accounts} | 并发数: {actual_workers}")
    print(f"  域名: {domain or _current_domain}")
    print(f"  代理: {proxy or '不使用代理'}")
    print(f"  验证码接口: {VERIFY_API_URL}")
    print(f"  OAuth: {'开启' if ENABLE_OAUTH else '关闭'} | required: {'是' if OAUTH_REQUIRED else '否'}")
    print(f"  Token目录: {TOKEN_JSON_DIR}")
    print(f"{'#' * 60}\n")

    success_count = 0
    fail_count = 0
    completed_count = 0
    start_time = time.time()
    _render_apt_like_progress(completed_count, total_accounts, success_count, fail_count, start_time)

    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = {
            executor.submit(_run_one, idx, total_accounts, domain, proxy): idx
            for idx in range(1, total_accounts + 1)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                ok, email, err = future.result()
                if ok:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"  [账号 {idx}] 失败: {err}")
            except Exception as e:
                fail_count += 1
                print(f"[FAIL] 账号 {idx} 线程异常: {e}")
            finally:
                completed_count += 1
                _render_apt_like_progress(completed_count, total_accounts, success_count, fail_count, start_time)

    with _print_lock:
        print()

    elapsed = time.time() - start_time
    avg = elapsed / total_accounts if total_accounts else 0
    print(f"\n{'#' * 60}")
    print(f"  注册完成! 耗时 {elapsed:.1f} 秒")
    print(f"  总数: {total_accounts} | 成功: {success_count} | 失败: {fail_count}")
    print(f"  平均速度: {avg:.1f} 秒/个")
    print(f"{'#' * 60}")
    return success_count, fail_count


def main():
    global _current_proxy, _current_domain

    parser = argparse.ArgumentParser(description="OpenAI 注册器 - 完整反风控版")
    parser.add_argument("-n", "--count", type=int, default=None, help="注册账号数量")
    parser.add_argument("-w", "--workers", type=int, default=None, help="并发数")
    parser.add_argument("--domain", type=str, default=None, help="邮箱域名")
    parser.add_argument("--proxy", type=str, default=None, help="代理地址")
    parser.add_argument("--no-proxy", action="store_true", help="禁用代理")
    parser.add_argument("--skip-preflight", action="store_true", help="跳过启动前连通性预检")
    parser.add_argument("--force", action="store_true", help="预检失败也继续执行")
    parser.add_argument("--no-pause", action="store_true", help="完成后不等待回车")
    args = parser.parse_args()

    if args.count is not None and args.count < 1:
        parser.error("--count 必须大于 0")
    if args.workers is not None and args.workers < 1:
        parser.error("--workers 必须大于 0")
    if args.proxy is not None and args.no_proxy:
        parser.error("--proxy 和 --no-proxy 不能同时使用")

    interactive = _is_interactive()
    if args.domain:
        _current_domain = args.domain.strip() or DOMAIN

    print("=" * 60)
    print("  OpenAI 注册器 - 完整反风控版")
    print(f"  默认域名: {_current_domain}")
    print("=" * 60)

    if args.no_proxy:
        proxy = None
        print("[Info] 已通过参数禁用代理")
    elif args.proxy is not None:
        proxy = args.proxy.strip() or None
        print(f"[Info] 已通过参数指定代理: {proxy or '不使用代理'}")
    elif interactive:
        proxy = _choose_proxy_interactively(_current_proxy)
    else:
        proxy = _current_proxy
        print(f"[Info] {'使用默认代理: ' + proxy if proxy else '不使用代理'}")

    _current_proxy = proxy

    do_preflight = not args.skip_preflight
    if interactive and not args.skip_preflight:
        preflight_input = input("\n执行启动前连通性预检? (Y/n): ").strip().lower()
        do_preflight = preflight_input != "n"

    if do_preflight and not _quick_preflight(proxy=proxy):
        if args.force:
            print("[Preflight] 已通过 --force 忽略失败，继续执行。")
        elif interactive:
            print("\n⚠️  预检失败，按 Enter 退出；输入 c 可继续强制运行")
            action = input("继续? (c/Enter): ").strip().lower()
            if action != "c":
                return
        else:
            print("[Preflight] 失败，使用 --force 可忽略并继续。")
            return

    if args.count is not None:
        total_accounts = args.count
        print(f"[Info] 已通过参数指定注册数量: {total_accounts}")
    elif interactive:
        total_accounts = _prompt_positive_int("\n注册账号数量 (默认 1): ", 1)
    else:
        total_accounts = 1

    if args.workers is not None:
        max_workers = args.workers
        print(f"[Info] 已通过参数指定并发数: {max_workers}")
    elif interactive:
        max_workers = _prompt_positive_int("并发数 (默认 1): ", 1)
    else:
        max_workers = 1

    run_batch(total_accounts=total_accounts, max_workers=max_workers, domain=_current_domain, proxy=proxy)

    if total_accounts == 1 and _should_pause(args.no_pause):
        input("\n按回车键退出...")


if __name__ == "__main__":
    try:
        main()
    finally:
        _pause_before_exit_if_needed()
