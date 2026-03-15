import json
import sys
import re
import os
import time
import random
import hashlib
import pathlib
import shutil
import glob
from collections import deque
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
try:
    from tokenizers import Tokenizer
    _TOKENIZERS_IMPORT_ERROR = None
except Exception as exc:
    Tokenizer = None
    _TOKENIZERS_IMPORT_ERROR = exc
try:
    from huggingface_hub import snapshot_download
    _HF_HUB_IMPORT_ERROR = None
except Exception as exc:
    snapshot_download = None
    _HF_HUB_IMPORT_ERROR = exc

# -------- Settings --------
MODEL_NAME = "qwen/qwen3-4b-fp8"
MAX_TOKENS = 6000  # For remote model, as per API
WINDOW_SIZE = 20
TIME_DELAY = 10
OUTPUT_FILE = "semantic_blocks.json"
NOVITA_API_URL = "https://api.novita.ai/v3/openai"
API_KEY_ENV = "LlmHFKey"
HF_TOKEN_ENV = "HF_API_TOKEN"

# LLM context window size (tokens)
MAX_CONTEXT = 40960  # Set this to your model's context window

MAX_RETRIES = 3           # how many times to try
BASE_DELAY  = 8           # s – exponential back‑off base
RATE_LIMIT_CALLS_PER_MIN = 40
REQUEST_TIMEOUT_SECONDS = 60
ADAPTIVE_WINDOW = True
ADAPTIVE_MIN_FILL_RATIO = 0.16
ADAPTIVE_TARGET_FILL_RATIO = 0.28
ADAPTIVE_MAX_FILL_RATIO = 0.62
ADAPTIVE_MIN_WINDOW = 6
ADAPTIVE_MAX_WINDOW = 80
ADAPTIVE_STEP = 2
ADAPTIVE_TIMEOUT_SHRINK = 0.75
ADAPTIVE_TIMEOUT_RETRIES = 2
MIN_CHAPTER_CONTEXT_TOKENS = 12000
MIN_FRONT_MATTER_CONTEXT_TOKENS = 5000
ADAPTIVE_TARGET_MAX_TOKENS = 22000
ADAPTIVE_MAX_PROMPT_TOKENS = 36000
FRONT_MATTER_TARGET_MAX_TOKENS = 12000
FRONT_MATTER_MAX_PROMPT_TOKENS = 18000
MAX_HEADING_TRANSITIONS_PER_BLOCK = 3
MIN_CHUNKS_BEFORE_HEADING_SPLIT = 6
QUESTION_MAX_INPUT_CHARS = 18000
SUMMARY_MAX_INPUT_CHARS = 22000
GENERATION_RETRIES = 2
GENERATION_DISABLE_AFTER_REASONING_ONLY = 3
ALLOW_GENERATION_FALLBACK = False
CONTENT_CHECK_ENABLED = True
CONTENT_CHECK_MAX_TOKENS = 128
RATE_LIMIT_429_COOLDOWN_SECONDS = 15
RATE_LIMIT_429_COOLDOWN_MAX_SECONDS = 120
RATE_LIMIT_DYNAMIC_SPACING_STEP = 0.5
RATE_LIMIT_DYNAMIC_SPACING_MAX_MULTIPLIER = 4.0
RATE_LIMIT_RECOVERY_SUCCESSES = 6

TOKENIZER_NAME = "Qwen/Qwen3-4B"
DEFAULT_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "semantic_rechunk_config.json")
tokenizer = None
_REQUEST_TIMESTAMPS = deque()
_LAST_REQUEST_TS = 0.0
_RATE_LIMIT_COOLDOWN_UNTIL = 0.0
_RATE_LIMIT_429_STREAK = 0
_RATE_LIMIT_SUCCESS_STREAK = 0
_GENERATION_REASONING_ONLY_STREAK = 0
_GENERATION_LLM_DISABLED = False


class ApproxTokenizer:
    def encode(self, text):
        if not text:
            return []
        return re.findall(r"\w+|[^\w\s]", text, re.UNICODE)

    def decode(self, token_list):
        return " ".join(str(t) for t in token_list)


class HfTokenizerAdapter:
    def __init__(self, tokenizer_impl):
        self._tokenizer = tokenizer_impl

    def encode(self, text):
        return self._tokenizer.encode(text).ids

    def decode(self, token_list):
        return self._tokenizer.decode(token_list)


def normalize_openai_base_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if value.lower().endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value


def _coerce_positive_int(raw_value, default_value, field_name):
    if raw_value is None:
        return default_value
    try:
        value = int(raw_value)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    print(f"[WARN] Invalid integer for '{field_name}': {raw_value!r}. Keeping {default_value}.")
    return default_value


def _coerce_non_negative_int(raw_value, default_value, field_name):
    if raw_value is None:
        return default_value
    try:
        value = int(raw_value)
        if value >= 0:
            return value
    except (TypeError, ValueError):
        pass
    print(f"[WARN] Invalid integer for '{field_name}': {raw_value!r}. Keeping {default_value}.")
    return default_value


def _coerce_bool(raw_value, default_value, field_name):
    if raw_value is None:
        return default_value
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        v = raw_value.strip().lower()
        if v in ("1", "true", "yes", "on"):
            return True
        if v in ("0", "false", "no", "off"):
            return False
    print(f"[WARN] Invalid boolean for '{field_name}': {raw_value!r}. Keeping {default_value}.")
    return default_value


def _coerce_float(raw_value, default_value, field_name, min_value=None, max_value=None):
    if raw_value is None:
        return default_value
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        print(f"[WARN] Invalid float for '{field_name}': {raw_value!r}. Keeping {default_value}.")
        return default_value
    if min_value is not None and value < min_value:
        print(f"[WARN] Float for '{field_name}' below {min_value}: {raw_value!r}. Keeping {default_value}.")
        return default_value
    if max_value is not None and value > max_value:
        print(f"[WARN] Float for '{field_name}' above {max_value}: {raw_value!r}. Keeping {default_value}.")
        return default_value
    return value


def load_runtime_config(config_path: str):
    if not config_path:
        return {}
    if not os.path.exists(config_path):
        print(f"[INFO] Config file not found at {config_path}; using built-in defaults.")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file {config_path} must contain a JSON object.")
    print(f"[INFO] Loaded runtime config from {config_path}")
    return loaded


def apply_runtime_overrides(config: dict):
    global MODEL_NAME, NOVITA_API_URL, TOKENIZER_NAME, MAX_TOKENS, WINDOW_SIZE, TIME_DELAY, MAX_CONTEXT, API_KEY_ENV, RATE_LIMIT_CALLS_PER_MIN, REQUEST_TIMEOUT_SECONDS, ADAPTIVE_WINDOW, tokenizer
    global ADAPTIVE_MIN_FILL_RATIO, ADAPTIVE_TARGET_FILL_RATIO, ADAPTIVE_MAX_FILL_RATIO, ADAPTIVE_MIN_WINDOW, ADAPTIVE_MAX_WINDOW, ADAPTIVE_STEP, ADAPTIVE_TIMEOUT_SHRINK, ADAPTIVE_TIMEOUT_RETRIES, MIN_CHAPTER_CONTEXT_TOKENS, MIN_FRONT_MATTER_CONTEXT_TOKENS
    global ADAPTIVE_TARGET_MAX_TOKENS, ADAPTIVE_MAX_PROMPT_TOKENS, FRONT_MATTER_TARGET_MAX_TOKENS, FRONT_MATTER_MAX_PROMPT_TOKENS, MAX_HEADING_TRANSITIONS_PER_BLOCK, MIN_CHUNKS_BEFORE_HEADING_SPLIT, QUESTION_MAX_INPUT_CHARS, SUMMARY_MAX_INPUT_CHARS, GENERATION_RETRIES, GENERATION_DISABLE_AFTER_REASONING_ONLY, ALLOW_GENERATION_FALLBACK, CONTENT_CHECK_ENABLED, CONTENT_CHECK_MAX_TOKENS
    global RATE_LIMIT_429_COOLDOWN_SECONDS, RATE_LIMIT_429_COOLDOWN_MAX_SECONDS, RATE_LIMIT_DYNAMIC_SPACING_STEP, RATE_LIMIT_DYNAMIC_SPACING_MAX_MULTIPLIER, RATE_LIMIT_RECOVERY_SUCCESSES
    if not config:
        return

    model_name = config.get("model_name") or config.get("LlmHFModelID")
    if isinstance(model_name, str) and model_name.strip():
        MODEL_NAME = model_name.strip()

    api_url = config.get("api_base_url") or config.get("api_url") or config.get("LlmHFUrl")
    if isinstance(api_url, str) and api_url.strip():
        NOVITA_API_URL = normalize_openai_base_url(api_url)

    tokenizer_name = config.get("tokenizer_name") or config.get("TokenizerName")
    if isinstance(tokenizer_name, str) and tokenizer_name.strip() and tokenizer_name.strip() != TOKENIZER_NAME:
        TOKENIZER_NAME = tokenizer_name.strip()
        tokenizer = None

    api_key_env = config.get("api_key_env") or config.get("LlmHFKeyEnv")
    if isinstance(api_key_env, str) and api_key_env.strip():
        API_KEY_ENV = api_key_env.strip()

    MAX_TOKENS = _coerce_positive_int(config.get("max_tokens") or config.get("MaxTokens"), MAX_TOKENS, "max_tokens")
    WINDOW_SIZE = _coerce_positive_int(config.get("window_size") or config.get("WindowSize"), WINDOW_SIZE, "window_size")
    TIME_DELAY = _coerce_positive_int(config.get("time_delay") or config.get("TimeDelay"), TIME_DELAY, "time_delay")
    MAX_CONTEXT = _coerce_positive_int(config.get("max_context") or config.get("MaxContext"), MAX_CONTEXT, "max_context")
    RATE_LIMIT_CALLS_PER_MIN = _coerce_non_negative_int(
        config.get("rate_limit_per_minute") or config.get("RateLimitPerMinute"),
        RATE_LIMIT_CALLS_PER_MIN,
        "rate_limit_per_minute")
    REQUEST_TIMEOUT_SECONDS = _coerce_positive_int(
        config.get("request_timeout_seconds") or config.get("RequestTimeoutSeconds") or config.get("HfRequestTimeoutSeconds"),
        REQUEST_TIMEOUT_SECONDS,
        "request_timeout_seconds")
    ADAPTIVE_WINDOW = _coerce_bool(
        config.get("adaptive_window") or config.get("AdaptiveWindow"),
        ADAPTIVE_WINDOW,
        "adaptive_window")
    ADAPTIVE_MIN_FILL_RATIO = _coerce_float(
        config.get("adaptive_min_fill_ratio") or config.get("AdaptiveMinFillRatio"),
        ADAPTIVE_MIN_FILL_RATIO,
        "adaptive_min_fill_ratio",
        min_value=0.01,
        max_value=0.95)
    ADAPTIVE_TARGET_FILL_RATIO = _coerce_float(
        config.get("adaptive_target_fill_ratio") or config.get("AdaptiveTargetFillRatio"),
        ADAPTIVE_TARGET_FILL_RATIO,
        "adaptive_target_fill_ratio",
        min_value=0.02,
        max_value=0.97)
    ADAPTIVE_MAX_FILL_RATIO = _coerce_float(
        config.get("adaptive_max_fill_ratio") or config.get("AdaptiveMaxFillRatio"),
        ADAPTIVE_MAX_FILL_RATIO,
        "adaptive_max_fill_ratio",
        min_value=0.05,
        max_value=0.99)
    ADAPTIVE_MIN_WINDOW = _coerce_positive_int(
        config.get("adaptive_min_window") or config.get("AdaptiveMinWindow"),
        ADAPTIVE_MIN_WINDOW,
        "adaptive_min_window")
    ADAPTIVE_MAX_WINDOW = _coerce_positive_int(
        config.get("adaptive_max_window") or config.get("AdaptiveMaxWindow"),
        ADAPTIVE_MAX_WINDOW,
        "adaptive_max_window")
    ADAPTIVE_STEP = _coerce_positive_int(
        config.get("adaptive_step") or config.get("AdaptiveStep"),
        ADAPTIVE_STEP,
        "adaptive_step")
    ADAPTIVE_TIMEOUT_SHRINK = _coerce_float(
        config.get("adaptive_timeout_shrink") or config.get("AdaptiveTimeoutShrink"),
        ADAPTIVE_TIMEOUT_SHRINK,
        "adaptive_timeout_shrink",
        min_value=0.1,
        max_value=0.99)
    ADAPTIVE_TIMEOUT_RETRIES = _coerce_non_negative_int(
        config.get("adaptive_timeout_retries") or config.get("AdaptiveTimeoutRetries"),
        ADAPTIVE_TIMEOUT_RETRIES,
        "adaptive_timeout_retries")
    MIN_CHAPTER_CONTEXT_TOKENS = _coerce_positive_int(
        config.get("min_chapter_context_tokens") or config.get("MinChapterContextTokens"),
        MIN_CHAPTER_CONTEXT_TOKENS,
        "min_chapter_context_tokens")
    MIN_FRONT_MATTER_CONTEXT_TOKENS = _coerce_positive_int(
        config.get("min_front_matter_context_tokens") or config.get("MinFrontMatterContextTokens"),
        MIN_FRONT_MATTER_CONTEXT_TOKENS,
        "min_front_matter_context_tokens")
    ADAPTIVE_TARGET_MAX_TOKENS = _coerce_positive_int(
        config.get("adaptive_target_max_tokens") or config.get("AdaptiveTargetMaxTokens"),
        ADAPTIVE_TARGET_MAX_TOKENS,
        "adaptive_target_max_tokens")
    ADAPTIVE_MAX_PROMPT_TOKENS = _coerce_positive_int(
        config.get("adaptive_max_prompt_tokens") or config.get("AdaptiveMaxPromptTokens"),
        ADAPTIVE_MAX_PROMPT_TOKENS,
        "adaptive_max_prompt_tokens")
    FRONT_MATTER_TARGET_MAX_TOKENS = _coerce_positive_int(
        config.get("front_matter_target_max_tokens") or config.get("FrontMatterTargetMaxTokens"),
        FRONT_MATTER_TARGET_MAX_TOKENS,
        "front_matter_target_max_tokens")
    FRONT_MATTER_MAX_PROMPT_TOKENS = _coerce_positive_int(
        config.get("front_matter_max_prompt_tokens") or config.get("FrontMatterMaxPromptTokens"),
        FRONT_MATTER_MAX_PROMPT_TOKENS,
        "front_matter_max_prompt_tokens")
    MAX_HEADING_TRANSITIONS_PER_BLOCK = _coerce_non_negative_int(
        config.get("max_heading_transitions_per_block") or config.get("MaxHeadingTransitionsPerBlock"),
        MAX_HEADING_TRANSITIONS_PER_BLOCK,
        "max_heading_transitions_per_block")
    MIN_CHUNKS_BEFORE_HEADING_SPLIT = _coerce_positive_int(
        config.get("min_chunks_before_heading_split") or config.get("MinChunksBeforeHeadingSplit"),
        MIN_CHUNKS_BEFORE_HEADING_SPLIT,
        "min_chunks_before_heading_split")
    QUESTION_MAX_INPUT_CHARS = _coerce_positive_int(
        config.get("question_max_input_chars") or config.get("QuestionMaxInputChars"),
        QUESTION_MAX_INPUT_CHARS,
        "question_max_input_chars")
    SUMMARY_MAX_INPUT_CHARS = _coerce_positive_int(
        config.get("summary_max_input_chars") or config.get("SummaryMaxInputChars"),
        SUMMARY_MAX_INPUT_CHARS,
        "summary_max_input_chars")
    GENERATION_RETRIES = _coerce_positive_int(
        config.get("generation_retries") or config.get("GenerationRetries"),
        GENERATION_RETRIES,
        "generation_retries")
    GENERATION_DISABLE_AFTER_REASONING_ONLY = _coerce_positive_int(
        config.get("generation_disable_after_reasoning_only") or config.get("GenerationDisableAfterReasoningOnly"),
        GENERATION_DISABLE_AFTER_REASONING_ONLY,
        "generation_disable_after_reasoning_only")
    ALLOW_GENERATION_FALLBACK = _coerce_bool(
        config.get("allow_generation_fallback") or config.get("AllowGenerationFallback"),
        ALLOW_GENERATION_FALLBACK,
        "allow_generation_fallback")
    CONTENT_CHECK_ENABLED = _coerce_bool(
        config.get("content_check_enabled") or config.get("ContentCheckEnabled"),
        CONTENT_CHECK_ENABLED,
        "content_check_enabled")
    CONTENT_CHECK_MAX_TOKENS = _coerce_positive_int(
        config.get("content_check_max_tokens") or config.get("ContentCheckMaxTokens"),
        CONTENT_CHECK_MAX_TOKENS,
        "content_check_max_tokens")
    RATE_LIMIT_429_COOLDOWN_SECONDS = _coerce_non_negative_int(
        config.get("rate_limit_429_cooldown_seconds") or config.get("RateLimit429CooldownSeconds"),
        RATE_LIMIT_429_COOLDOWN_SECONDS,
        "rate_limit_429_cooldown_seconds")
    RATE_LIMIT_429_COOLDOWN_MAX_SECONDS = _coerce_non_negative_int(
        config.get("rate_limit_429_cooldown_max_seconds") or config.get("RateLimit429CooldownMaxSeconds"),
        RATE_LIMIT_429_COOLDOWN_MAX_SECONDS,
        "rate_limit_429_cooldown_max_seconds")
    RATE_LIMIT_DYNAMIC_SPACING_STEP = _coerce_float(
        config.get("rate_limit_dynamic_spacing_step") or config.get("RateLimitDynamicSpacingStep"),
        RATE_LIMIT_DYNAMIC_SPACING_STEP,
        "rate_limit_dynamic_spacing_step",
        min_value=0.0,
        max_value=5.0)
    RATE_LIMIT_DYNAMIC_SPACING_MAX_MULTIPLIER = _coerce_float(
        config.get("rate_limit_dynamic_spacing_max_multiplier") or config.get("RateLimitDynamicSpacingMaxMultiplier"),
        RATE_LIMIT_DYNAMIC_SPACING_MAX_MULTIPLIER,
        "rate_limit_dynamic_spacing_max_multiplier",
        min_value=1.0,
        max_value=20.0)
    RATE_LIMIT_RECOVERY_SUCCESSES = _coerce_positive_int(
        config.get("rate_limit_recovery_successes") or config.get("RateLimitRecoverySuccesses"),
        RATE_LIMIT_RECOVERY_SUCCESSES,
        "rate_limit_recovery_successes")

    if ADAPTIVE_MIN_FILL_RATIO >= ADAPTIVE_MAX_FILL_RATIO:
        print(
            f"[WARN] adaptive_min_fill_ratio ({ADAPTIVE_MIN_FILL_RATIO}) must be < adaptive_max_fill_ratio ({ADAPTIVE_MAX_FILL_RATIO}). "
            "Resetting to defaults."
        )
        ADAPTIVE_MIN_FILL_RATIO = 0.16
        ADAPTIVE_MAX_FILL_RATIO = 0.62

    if not (ADAPTIVE_MIN_FILL_RATIO <= ADAPTIVE_TARGET_FILL_RATIO <= ADAPTIVE_MAX_FILL_RATIO):
        ADAPTIVE_TARGET_FILL_RATIO = min(
            ADAPTIVE_MAX_FILL_RATIO,
            max(ADAPTIVE_MIN_FILL_RATIO, ADAPTIVE_TARGET_FILL_RATIO)
        )

    if ADAPTIVE_MIN_WINDOW > ADAPTIVE_MAX_WINDOW:
        print(
            f"[WARN] adaptive_min_window ({ADAPTIVE_MIN_WINDOW}) > adaptive_max_window ({ADAPTIVE_MAX_WINDOW}). "
            "Swapping values."
        )
        ADAPTIVE_MIN_WINDOW, ADAPTIVE_MAX_WINDOW = ADAPTIVE_MAX_WINDOW, ADAPTIVE_MIN_WINDOW

    if ADAPTIVE_TARGET_MAX_TOKENS > ADAPTIVE_MAX_PROMPT_TOKENS:
        ADAPTIVE_TARGET_MAX_TOKENS = ADAPTIVE_MAX_PROMPT_TOKENS
    if FRONT_MATTER_TARGET_MAX_TOKENS > FRONT_MATTER_MAX_PROMPT_TOKENS:
        FRONT_MATTER_TARGET_MAX_TOKENS = FRONT_MATTER_MAX_PROMPT_TOKENS


def resolve_hf_hub_token():
    env_order = (HF_TOKEN_ENV, "HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")
    for env_name in env_order:
        value = os.getenv(env_name)
        if value:
            return value, env_name
    return None, None


def resolve_tokenizer_json(tokenizer_name: str):
    if os.path.isfile(tokenizer_name):
        return tokenizer_name

    if os.path.isdir(tokenizer_name):
        local_file = os.path.join(tokenizer_name, "tokenizer.json")
        if os.path.exists(local_file):
            return local_file

    if snapshot_download is None:
        raise RuntimeError(
            "huggingface_hub snapshot_download is unavailable. "
            f"Original import error: {_HF_HUB_IMPORT_ERROR!r}"
        )

    hf_token, hf_token_env = resolve_hf_hub_token()
    if hf_token:
        print(f"[INFO] Using Hugging Face token from {hf_token_env} for tokenizer download.")

    cache_path = snapshot_download(
        repo_id=tokenizer_name,
        token=hf_token,
        allow_patterns=[
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.*",
            "merges.txt",
            "*.model",
            "*.txt"
        ]
    )
    tokenizer_file = os.path.join(cache_path, "tokenizer.json")
    if os.path.exists(tokenizer_file):
        return tokenizer_file

    candidates = glob.glob(os.path.join(cache_path, "**", "tokenizer.json"), recursive=True)
    if candidates:
        return candidates[0]

    raise RuntimeError(f"Could not find tokenizer.json for '{tokenizer_name}' in cache path '{cache_path}'.")


def get_tokenizer():
    global tokenizer
    if tokenizer is None:
        if Tokenizer is None:
            print(
                "[WARN] tokenizers package unavailable; using approximate regex tokenizer. "
                f"Original import error: {_TOKENIZERS_IMPORT_ERROR!r}"
            )
            tokenizer = ApproxTokenizer()
            return tokenizer

        tokenizer_path = resolve_tokenizer_json(TOKENIZER_NAME)
        tokenizer = HfTokenizerAdapter(Tokenizer.from_file(tokenizer_path))
        print(f"[INFO] Loaded tokenizer from {tokenizer_path}")
    return tokenizer


def enforce_rate_limit():
    global _LAST_REQUEST_TS
    if RATE_LIMIT_CALLS_PER_MIN <= 0:
        return

    window_seconds = 60.0
    # Smooth request pacing and dynamically increase spacing when recent 429s are seen.
    base_interval = (window_seconds / float(RATE_LIMIT_CALLS_PER_MIN)) + 0.05
    dynamic_multiplier = min(
        RATE_LIMIT_DYNAMIC_SPACING_MAX_MULTIPLIER,
        1.0 + (_RATE_LIMIT_429_STREAK * RATE_LIMIT_DYNAMIC_SPACING_STEP)
    )
    min_interval = base_interval * dynamic_multiplier
    now = time.monotonic()
    since_last = now - _LAST_REQUEST_TS
    if _LAST_REQUEST_TS > 0 and since_last < min_interval:
        spacing_wait = min_interval - since_last
        print(
            f"[RATE] Spacing guard waiting {spacing_wait:.2f}s "
            f"(target {min_interval:.2f}s/request, base {base_interval:.2f}s, x{dynamic_multiplier:.2f}, streak={_RATE_LIMIT_429_STREAK})"
        )
        time.sleep(spacing_wait)
        now = time.monotonic()

    while _REQUEST_TIMESTAMPS and (now - _REQUEST_TIMESTAMPS[0]) >= window_seconds:
        _REQUEST_TIMESTAMPS.popleft()

    if len(_REQUEST_TIMESTAMPS) >= RATE_LIMIT_CALLS_PER_MIN:
        wait_seconds = window_seconds - (now - _REQUEST_TIMESTAMPS[0]) + 0.05
        if wait_seconds > 0:
            print(f"[RATE] Limit {RATE_LIMIT_CALLS_PER_MIN}/min reached, waiting {wait_seconds:.2f}s")
            time.sleep(wait_seconds)
        now = time.monotonic()
        while _REQUEST_TIMESTAMPS and (now - _REQUEST_TIMESTAMPS[0]) >= window_seconds:
            _REQUEST_TIMESTAMPS.popleft()

    request_ts = time.monotonic()
    _REQUEST_TIMESTAMPS.append(request_ts)
    _LAST_REQUEST_TS = request_ts


def is_rate_limit_error(exc):
    if exc is None:
        return False
    text = str(exc)
    if "429" in text:
        return True
    return bool(re.search(r"rate.?limit|too many requests", text, flags=re.IGNORECASE))


def enforce_rate_limit_cooldown():
    now = time.monotonic()
    if _RATE_LIMIT_COOLDOWN_UNTIL <= now:
        return
    wait_seconds = _RATE_LIMIT_COOLDOWN_UNTIL - now
    print(f"[RATE] 429 cooldown waiting {wait_seconds:.2f}s")
    time.sleep(wait_seconds)


def note_rate_limit_error():
    global _RATE_LIMIT_COOLDOWN_UNTIL, _RATE_LIMIT_429_STREAK, _RATE_LIMIT_SUCCESS_STREAK
    _RATE_LIMIT_429_STREAK += 1
    _RATE_LIMIT_SUCCESS_STREAK = 0
    if RATE_LIMIT_429_COOLDOWN_SECONDS <= 0:
        return
    base = float(RATE_LIMIT_429_COOLDOWN_SECONDS)
    cooldown = base * (2 ** (_RATE_LIMIT_429_STREAK - 1))
    if RATE_LIMIT_429_COOLDOWN_MAX_SECONDS > 0:
        cooldown = min(cooldown, float(RATE_LIMIT_429_COOLDOWN_MAX_SECONDS))
    new_until = time.monotonic() + cooldown
    _RATE_LIMIT_COOLDOWN_UNTIL = max(_RATE_LIMIT_COOLDOWN_UNTIL, new_until)
    print(
        f"[RATE] 429 detected streak={_RATE_LIMIT_429_STREAK} "
        f"cooldown={cooldown:.2f}s"
    )


def note_rate_limit_recovery():
    global _RATE_LIMIT_429_STREAK, _RATE_LIMIT_SUCCESS_STREAK
    if _RATE_LIMIT_429_STREAK <= 0:
        return
    _RATE_LIMIT_SUCCESS_STREAK += 1
    if _RATE_LIMIT_SUCCESS_STREAK >= RATE_LIMIT_RECOVERY_SUCCESSES:
        _RATE_LIMIT_429_STREAK = max(0, _RATE_LIMIT_429_STREAK - 1)
        _RATE_LIMIT_SUCCESS_STREAK = 0



def split_text_to_max_tokens(text, max_tokens):
    tok = get_tokenizer()
    tokens = tok.encode(text)
    if len(tokens) <= max_tokens:
        return [text]
    # Split into multiple pieces
    splits = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i+max_tokens]
        chunk_text = tok.decode(chunk_tokens)
        splits.append(chunk_text)
    return splits

FRONT_MATTER_PATTERNS = (
    r"\bcopyright\b",
    r"\btable\s+of\s+contents\b",
    r"\bcontents\b",
    r"\bforeword\b",
    r"\bpreface\b",
    r"\backnowledg(e)?ments?\b",
    r"\babout\s+the\s+author\b",
    r"\bdedication\b",
    r"\bisbn\b",
    r"\bpublisher\b",
    r"\bindex\b"
)

SECTION_HEADING_PATTERNS = (
    r"^\s*(chapter|part|section)\s+\d+",
    r"^\s*\d+(\.\d+){1,3}\s+[A-Za-z]",
    r"^\s*[A-Z][A-Z0-9\s,:&/\-]{8,}$"
)


def is_front_matter_chunk(text):
    if not text:
        return False
    sample = text[:3500].lower()
    hits = sum(1 for pat in FRONT_MATTER_PATTERNS if re.search(pat, sample, flags=re.IGNORECASE))
    return hits >= 2


def looks_like_section_heading(text):
    if not text:
        return False
    head = text[:240].strip()
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
    if not lines:
        return False
    first = lines[0]
    for idx, pat in enumerate(SECTION_HEADING_PATTERNS):
        flags = re.IGNORECASE if idx < 2 else 0
        if re.search(pat, first, flags=flags):
            return True
    return False


def compute_context_targets(max_context, reserved_output_tokens, is_front_matter, has_section_heading):
    usable_context = max(1024, max_context - reserved_output_tokens)
    min_fill = ADAPTIVE_MIN_FILL_RATIO * (0.65 if is_front_matter else 1.0)
    target_fill = ADAPTIVE_TARGET_FILL_RATIO * (0.70 if is_front_matter else 1.0)
    max_fill = ADAPTIVE_MAX_FILL_RATIO

    # Heading chunks benefit from a little extra context so boundary detection sees intro + body.
    if has_section_heading and not is_front_matter:
        target_fill = min(max_fill, target_fill + 0.05)

    floor_tokens = MIN_FRONT_MATTER_CONTEXT_TOKENS if is_front_matter else MIN_CHAPTER_CONTEXT_TOKENS
    min_prompt_tokens = int(max(floor_tokens, usable_context * min_fill))
    target_prompt_tokens = int(max(floor_tokens, usable_context * target_fill))
    max_prompt_tokens = int(usable_context * max_fill)

    if is_front_matter:
        soft_target_cap = min(usable_context, FRONT_MATTER_TARGET_MAX_TOKENS)
        soft_max_cap = min(usable_context, FRONT_MATTER_MAX_PROMPT_TOKENS)
    else:
        soft_target_cap = min(usable_context, ADAPTIVE_TARGET_MAX_TOKENS)
        soft_max_cap = min(usable_context, ADAPTIVE_MAX_PROMPT_TOKENS)
    target_prompt_tokens = min(target_prompt_tokens, soft_target_cap)
    max_prompt_tokens = min(max_prompt_tokens, soft_max_cap)
    if target_prompt_tokens > max_prompt_tokens:
        target_prompt_tokens = max_prompt_tokens
    if min_prompt_tokens > target_prompt_tokens:
        min_prompt_tokens = target_prompt_tokens

    return {
        "usable_context": usable_context,
        "min_prompt_tokens": min(min_prompt_tokens, usable_context),
        "target_prompt_tokens": min(target_prompt_tokens, usable_context),
        "max_prompt_tokens": max(1024, min(max_prompt_tokens, usable_context))
    }


def adjust_adaptive_window_size(current_window_size, prompt_tokens, target_prompt_tokens, max_prompt_tokens):
    if current_window_size <= 0:
        return ADAPTIVE_MIN_WINDOW, "reset_invalid"

    new_size = current_window_size
    reason = "steady"

    if prompt_tokens < target_prompt_tokens:
        deficit_ratio = (target_prompt_tokens - prompt_tokens) / max(1, target_prompt_tokens)
        step = max(1, int(round(ADAPTIVE_STEP * (1 + deficit_ratio))))
        new_size = current_window_size + step
        reason = "grow_for_context"
    elif prompt_tokens > max_prompt_tokens:
        excess_ratio = (prompt_tokens - max_prompt_tokens) / max(1, max_prompt_tokens)
        step = max(1, int(round(ADAPTIVE_STEP * (1 + excess_ratio))))
        new_size = current_window_size - step
        reason = "shrink_for_timeout_risk"

    new_size = max(ADAPTIVE_MIN_WINDOW, min(ADAPTIVE_MAX_WINDOW, new_size))
    return new_size, reason


def is_timeout_like_error(message):
    if not message:
        return False
    return bool(re.search(r"timeout|timed\s*out|readtimeout|apitimeout", str(message), flags=re.IGNORECASE))


def find_major_heading_positions(window_chunks):
    positions = []
    for idx, chunk in enumerate(window_chunks, start=1):
        if looks_like_section_heading(chunk):
            positions.append(idx)
    return positions


def apply_heading_transition_guard(window_chunks, corrected_end):
    if corrected_end <= 1 or MAX_HEADING_TRANSITIONS_PER_BLOCK <= 0:
        return corrected_end

    heading_positions = find_major_heading_positions(window_chunks[:corrected_end])
    if not heading_positions:
        return corrected_end

    # Treat headings after the start as transitions.
    transitions = [pos for pos in heading_positions if pos > 1]
    if len(transitions) <= MAX_HEADING_TRANSITIONS_PER_BLOCK:
        return corrected_end

    split_at = transitions[MAX_HEADING_TRANSITIONS_PER_BLOCK]
    guarded_end = max(1, split_at - 1)
    if guarded_end >= MIN_CHUNKS_BEFORE_HEADING_SPLIT and guarded_end < corrected_end:
        print(
            f"[GUARD] Heading transitions={len(transitions)} > {MAX_HEADING_TRANSITIONS_PER_BLOCK}; "
            f"trimming block end from {corrected_end} to {guarded_end}"
        )
        return guarded_end
    return corrected_end


def apply_front_matter_guard(window_chunks, corrected_end, start_is_front_matter):
    if not start_is_front_matter or corrected_end <= 1:
        return corrected_end
    heading_positions = find_major_heading_positions(window_chunks[:corrected_end])
    next_heading = next((pos for pos in heading_positions if pos > 1), None)
    if next_heading and (next_heading - 1) >= MIN_CHUNKS_BEFORE_HEADING_SPLIT:
        guarded_end = next_heading - 1
        if guarded_end < corrected_end:
            print(
                f"[GUARD] Front matter split at first major heading (chunk {next_heading}); "
                f"trimming block end from {corrected_end} to {guarded_end}"
            )
            return guarded_end
    return corrected_end


def build_adaptive_window(
    chunks,
    pointer,
    adaptive_window_size,
    tokenizer,
    build_boundary_prompt,
    max_context,
    reserved_output_tokens,
    min_prompt_tokens=0,
    max_window_size=None
):
    """
    Dynamically build a window of chunks that fits within the LLM context window.
    Returns (window_chunks, total_tokens, cur_window_size)
    """
    window_chunks = []
    total_tokens = 0
    effective_max_window = max_window_size if max_window_size is not None else adaptive_window_size
    target_window = max(1, adaptive_window_size)
    while True:
        if pointer + len(window_chunks) >= len(chunks):
            break
        if len(window_chunks) >= effective_max_window:
            break
        if len(window_chunks) >= target_window and total_tokens >= max(0, int(min_prompt_tokens or 0)):
            break

        candidate_chunk = chunks[pointer + len(window_chunks)]
        temp_chunks = window_chunks + [candidate_chunk]
        prompt = build_boundary_prompt(temp_chunks)
        prompt_tokens = len(tokenizer.encode(prompt))
        if prompt_tokens > max_context - reserved_output_tokens:
            break
        window_chunks.append(candidate_chunk)
        total_tokens = prompt_tokens
    cur_window_size = len(window_chunks)
    return window_chunks, total_tokens, cur_window_size

def load_chunks(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} chunks from {json_file}")
    return [item["output"] for item in data]
def resume_previous(output_json: str):
    """
    If an output file already exists, read any previously written
    semantic blocks and return (blocks, last_processed_chunk_index).
    Returns ([], 0) if there is nothing to resume.
    """
    if not os.path.exists(output_json):
        return [], 0

    try:
        with open(output_json, "r", encoding="utf-8") as f:
            blocks = json.load(f)
        if isinstance(blocks, list) and blocks:
            last_end = blocks[-1].get("end", 0)
            if isinstance(last_end, int) and last_end >= 0:
                return blocks, last_end          # 1‑based index from the JSON
    except Exception as exc:
        print(f"[WARN] Could not read {output_json}: {exc!r}")

    return [], 0

def build_boundary_prompt(numbered_chunks):
    """
    Return a prompt that asks the LLM for the **index of the first chunk
    that starts the *next* major section** inside the sliding window.
    """
    chunks_json = json.dumps(
        [{"index": i + 1, "text": chunk.strip()}
         for i, chunk in enumerate(numbered_chunks)],
        ensure_ascii=False,
        indent=2
    )
    n_chunks = len(numbered_chunks)

    prompt = (
        # ---------- task ----------
        "Below is a JSON array of document chunks, each with an \"index\" and \"text\".\n\n"
        "★ **Task:** Return the **index of the FIRST CHUNK that begins the NEXT major section / heading / chapter / topic.**\n"
        "That is, imagine the window as `[current‑section … | next‑section …]`; "
        "your answer is the index where the divider `|` sits.\n"
        "⚠️ Do **NOT** return the index of the last chunk in the current section.\n"
        "⚠️ Do **NOT** return the number of chunks.\n\n"
        "Prefer to group *more* chunks rather than splitting on minor transitions (page numbers, pictures, charts etc.).\n"
        "• A heading‑like chunk (ALL‑CAPS line, \"Chapter …\", numbered title) **does not by itself mark a boundary**. "
        "Treat the heading and its immediate introductory paragraph(s) as one unit. "
        "Only mark a boundary when the following chunk clearly shifts topic.\n\n"

        "[BEGIN_EXAMPLES]\n"

        "Example 1:\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Copyright\"},\n"
        "  {\"index\": 2, \"text\": \"Table of Contents\"},\n"
        "  {\"index\": 3, \"text\": \"Preface\"},\n"
        "  {\"index\": 4, \"text\": \"Chapter 1: Getting Started\"},\n"
        "  {\"index\": 5, \"text\": \"Chapter 1 content…\"}\n"
        "]\n"
        "✔ Correct response: **4**  (chunk 4 is the first of Chapter 1)\n\n"

        "Example 2:\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Chapter 1: The Basics\"},\n"
        "  {\"index\": 2, \"text\": \"More on chapter 1\"},\n"
        "  {\"index\": 3, \"text\": \"Still more on chapter 1\"},\n"
        "  {\"index\": 4, \"text\": \"Chapter 2: Advanced Topics\"},\n"
        "  {\"index\": 5, \"text\": \"Content on chapter 2\"}\n"
        "]\n"
        "✔ Correct response: **4**\n\n"

        "Example 3:\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Section 2.4: Analysis of Results\"},\n"
        "  {\"index\": 2, \"text\": \"Detailed explanation of the experimental setup …\"},\n"
        "  {\"index\": 3, \"text\": \"Figure 2‑7: Distribution of sample values\"},\n"
        "  {\"index\": 4, \"text\": \"Continuation of analysis and discussion …\"},\n"
        "  {\"index\": 5, \"text\": \"Section 2.5: Limitations\"}\n"
        "]\n"
        "✔ Correct response: **5**  (chunk 5 is the first chunk of the next real section; the figure caption at chunk 3 does **not** define a boundary)\n\n"
        "✖ Wrong response : **3** (that is figure not a boundary)\n\n"

        "Counter‑example (#4):\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Chapter 1 intro\"},\n"
        "  {\"index\": 2, \"text\": \"Chapter 1 body\"},\n"
        "  {\"index\": 3, \"text\": \"Chapter 1 summary\"},\n"
        "  {\"index\": 4, \"text\": \"Chapter 2: Advanced\"},\n"
        "  {\"index\": 5, \"text\": \"Chapter 2 body\"}\n"
        "]\n"
        "✔ Correct response: **4**\n"
        "✖ Wrong response : **3** (that is the last chunk of Chapter 1, NOT the first of Chapter 2)\n\n"

        "Counter‑example (#5 – heading travels with intro):\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"CHAPTER 2: INTRODUCTION\"},\n"
        "  {\"index\": 2, \"text\": \"This chapter covers the basics of …\"},\n"
        "  {\"index\": 3, \"text\": \"More details on the basics …\"},\n"
        "  {\"index\": 4, \"text\": \"CHAPTER 3: ADVANCED TOPICS\"}\n"
        "]\n"
        "✔ Correct response: **4**\n"
        "✖ Wrong response : **2** or **3** (heading + intro are one unit)\n"

        "[END_EXAMPLES]\n\n"

        # ---------- actual data ----------
        "Now decide the boundary for the real data below. "
        f"Respond with a single integer from **1** to **{n_chunks}** — "
        "no explanation, no extra text.\n\n"
        "[BEGIN_CHUNKS]\n"
        f"{chunks_json}\n"
        "[END_CHUNKS]\n"
        "Reply with the index only:"
    )
    return prompt

def extract_boundary_index(llm_response, n_chunks):
    text = llm_response or ""
    if not text:
        return None

    # Remove explicit reasoning blocks first.
    cleaned = strip_think_tags(text)
    cleaned = re.sub(r"(?is)<think>.*?(?:</think>|$)", " ", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return None

    # Prefer explicit structured/labelled outputs.
    patterns = [
        r'(?is)"index"\s*:\s*(\d{1,3})',
        r"(?is)<answer>\s*(\d{1,3})\s*</answer>",
        r"(?is)\b(?:final answer|answer|boundary|index)\b[^\d]{0,24}(\d{1,3})"
    ]
    for pattern in patterns:
        matches = re.findall(pattern, cleaned)
        if matches:
            value = int(matches[-1])
            if 1 <= value <= n_chunks:
                return value

    # Then check for a standalone final integer line.
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    for line in reversed(lines):
        m = re.fullmatch(r"[^\d]*?(\d{1,3})[^\d]*?", line)
        if m:
            value = int(m.group(1))
            if 1 <= value <= n_chunks:
                return value

    # Last resort: use the last valid integer in cleaned content.
    numbers = re.findall(r"\b(\d{1,3})\b", cleaned)
    for candidate in reversed(numbers):
        value = int(candidate)
        if 1 <= value <= n_chunks:
            return value

    return None


def build_boundary_repair_prompt(raw_response, n_chunks):
    truncated = (raw_response or "")[:16000]
    return (
        "You are a strict parser.\n"
        f"Extract the final boundary index from the text below.\n"
        f"Return ONLY one integer in the range 1..{n_chunks}.\n"
        "If no valid boundary exists, return NONE.\n\n"
        "[BEGIN_RAW_RESPONSE]\n"
        f"{truncated}\n"
        "[END_RAW_RESPONSE]\n"
    )


def try_repair_boundary_index(raw_response, n_chunks, client, model):
    prompt = build_boundary_repair_prompt(raw_response, n_chunks)
    try:
        repair_res = safe_chat_completion(
            client=client,
            prompt_text=prompt,
            model=model,
            stream=False,
            max_tokens=256,
            temperature=0,
            top_p=1,
            presence_penalty=0,
            frequency_penalty=0,
            response_format={"type": "text"}
        )
    except Exception as exc:
        return None, f"[REPAIR-API-ERROR] {exc}"

    if not repair_res.choices:
        return None, "[REPAIR-API-ERROR] 0 choices returned"

    repair_text = (repair_res.choices[0].message.content or "").strip()
    repaired = extract_boundary_index(repair_text, n_chunks)
    if repaired is not None:
        return repaired, repair_text
    if re.search(r"\bnone\b", repair_text, flags=re.IGNORECASE):
        return None, repair_text

    return None, repair_text


def get_semantic_block_end(window_chunks, client, model, max_tokens):
    prompt = build_boundary_prompt(window_chunks)

    try:
        chat_completion_res = safe_chat_completion(
            client=client,
            prompt_text=prompt,
            model=model,
            stream=False,
            max_tokens=max_tokens,
            temperature=0.3,
            top_p=1,
            presence_penalty=0,
            frequency_penalty=0,
            response_format={"type": "text"},
            extra_body={"top_k": 50,
                        "repetition_penalty": 1,
                        "min_p": 0}
        )
    except Exception as e:
        return None, f"[API‑ERROR] {e}"

    time.sleep(TIME_DELAY)

    if not chat_completion_res.choices:
        return None, "[API‑ERROR] 0 choices returned"

    llm_response = (chat_completion_res.choices[0].message.content or "").strip()
    boundary_index = extract_boundary_index(llm_response, len(window_chunks))
    if boundary_index is None:
        repaired_index, repaired_text = try_repair_boundary_index(
            llm_response,
            len(window_chunks),
            client,
            model)
        if repaired_index is not None:
            return repaired_index, repaired_text

        preview = llm_response[:1200]
        return None, f"[PARSE‑ERROR] No integer in response. repair={repaired_text!r}. raw={preview!r}"

    return boundary_index, llm_response

def print_window(pointer, window_chunks):
    print(f"\n[WINDOW] Chunks {pointer+1} to {pointer+len(window_chunks)}:")
    for i, chunk in enumerate(window_chunks):
        chunk_preview = chunk[:100].replace('\n', ' ')
        ellipsis = '...' if len(chunk) > 100 else ''
        print(f"  [{pointer + i + 1}] {chunk_preview}{ellipsis}")

def strip_think_tags(text):
    if not text:
        return ""
    # Remove closed or unclosed reasoning tags.
    return re.sub(r"(?is)<think>.*?(?:</think>|$)", "", text).strip()

def normalize_generated_text(text):
    if not text:
        return ""
    clean = text.strip()
    clean = clean.replace("\r", " ")
    clean = re.sub(r"\s+", " ", clean)
    clean = clean.strip(" \"'")
    return clean

def build_question_prompt(text):
    return (
        "You are creating retrieval questions for a technical RAG index.\n"
        "Write exactly one question that this chunk can answer.\n"
        "Requirements:\n"
        "- Keep it specific to the chunk's concrete topic.\n"
        "- Include key technical terms, acronyms, protocols, tools, APIs, or commands when present.\n"
        "- Avoid vague wording such as 'this section' or 'the topic'.\n"
        "- Keep it under 30 words.\n"
        "- Do not output reasoning, bullets, JSON, or <think> tags.\n"
        "Output format must be exactly:\n"
        "<question>...your question...</question>\n\n"
        f"{text}\n"
    )

def build_summary_prompt(text):
    return (
        "Summarize the following technical text in 2 concise sentences for retrieval context.\n"
        "Include concrete entities (tools, protocols, APIs, commands, versions, constraints) if present.\n"
        "Do not output reasoning, bullets, JSON, or <think> tags.\n"
        "Output format must be exactly:\n"
        "<summary>...2 concise sentences...</summary>\n\n"
        f"{text}\n"
    )

def fallback_question(text):
    headings = _collect_heading_lines(text, limit=12)
    for heading in headings:
        low = heading.lower()
        if any(k in low for k in ("table of contents", "copyright", "preface", "isbn", "acknowledg")):
            continue
        topic = normalize_generated_text(re.sub(r"^[\-\d\.\s]+", "", heading))
        if topic:
            topic_short = " ".join(topic.split()[:18]).strip()
            return f"What does this section explain about {topic_short}?"

    sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    sentence = normalize_generated_text(sentence)
    if not sentence:
        return "What key concept is explained in this section?"
    if sentence.endswith("?"):
        return sentence
    short = " ".join(sentence.split()[:22]).strip()
    return f"What does this section explain about {short}?"

def fallback_summary(text):
    headings = _collect_heading_lines(text, limit=4)
    clean_headings = [
        normalize_generated_text(h)
        for h in headings
        if h and not re.search(r"table\s+of\s+contents|copyright|isbn|acknowledg", h, flags=re.IGNORECASE)
    ]

    context = build_generation_context(text, min(SUMMARY_MAX_INPUT_CHARS, 6000))
    sentences = re.split(r"(?<=[.!?])\s+", context.strip())
    usable = []
    for s in sentences:
        c = normalize_generated_text(s)
        if not c:
            continue
        if len(c) < 40:
            continue
        if re.search(r"copyright|all rights reserved|warranty", c, flags=re.IGNORECASE):
            continue
        usable.append(c)
        if len(usable) >= 2:
            break

    if clean_headings:
        head = "; ".join(clean_headings[:2])
        if usable:
            return normalize_generated_text(f"{head}. {usable[0]}")
        return normalize_generated_text(head)

    if usable:
        return normalize_generated_text(" ".join(usable[:2]))
    return normalize_generated_text(text[:320])

def _collect_heading_lines(text, limit=20):
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if looks_like_section_heading(line) or re.search(r"^\s*(chapter|part|section)\b", line, flags=re.IGNORECASE):
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def build_generation_context(text, max_chars):
    clean = text or ""
    if len(clean) <= max_chars:
        return clean

    heading_lines = _collect_heading_lines(clean, limit=24)
    prefix_len = max_chars // 2
    suffix_len = max_chars // 3
    mid_len = max_chars - prefix_len - suffix_len
    mid_start = max(0, (len(clean) // 2) - (mid_len // 2))

    prefix = clean[:prefix_len]
    mid = clean[mid_start:mid_start + mid_len]
    suffix = clean[-suffix_len:] if suffix_len > 0 else ""

    parts = []
    if heading_lines:
        parts.append("[HEADINGS]\n" + "\n".join(heading_lines))
    parts.append("[CONTENT_START]\n" + prefix)
    parts.append("[CONTENT_MIDDLE]\n" + mid)
    parts.append("[CONTENT_END]\n" + suffix)
    return "\n\n".join(parts)


def extract_tagged_or_clean_text(raw_text, tag_name):
    stripped = strip_think_tags(raw_text or "")
    if not stripped:
        return ""

    m = re.search(
        rf"(?is)<{re.escape(tag_name)}>\s*(.*?)\s*</{re.escape(tag_name)}>",
        stripped
    )
    if m:
        return normalize_generated_text(m.group(1))

    # Accept direct plain-text outputs as fallback.
    plain = normalize_generated_text(stripped)
    plain = re.sub(rf"(?is)^<{re.escape(tag_name)}>\s*|\s*</{re.escape(tag_name)}>$", "", plain).strip()
    return normalize_generated_text(plain)


def _flatten_text_payload(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "value", "output_text"):
                    if key in item and item.get(key):
                        parts.append(str(item.get(key)))
                        break
                else:
                    if item:
                        parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(p for p in parts if p)
    if isinstance(value, dict):
        for key in ("text", "content", "value", "output_text"):
            if key in value and value.get(key):
                return str(value.get(key))
        return str(value)
    return str(value)


def extract_response_text(resp):
    if not getattr(resp, "choices", None):
        return ""
    message = resp.choices[0].message

    candidates = []
    candidates.append(_flatten_text_payload(getattr(message, "content", None)))
    candidates.append(_flatten_text_payload(getattr(message, "reasoning_content", None)))
    candidates.append(_flatten_text_payload(getattr(message, "reasoning", None)))
    candidates.append(_flatten_text_payload(getattr(message, "output_text", None)))

    model_extra = getattr(message, "model_extra", None)
    if isinstance(model_extra, dict):
        for key in ("reasoning_content", "reasoning", "content", "output_text", "text"):
            if key in model_extra:
                candidates.append(_flatten_text_payload(model_extra.get(key)))

    for text in candidates:
        if text and text.strip():
            return text
    return ""


def is_reasoning_only_output(raw_text):
    if not raw_text:
        return False
    return bool(re.search(r"<think>", raw_text, flags=re.IGNORECASE)) and not bool(strip_think_tags(raw_text))


def generate_text_with_retries(client, model, prompt_text, tag_name, max_tokens=256):
    global _GENERATION_REASONING_ONLY_STREAK, _GENERATION_LLM_DISABLED
    if _GENERATION_LLM_DISABLED:
        return ""

    last_candidate = ""
    for attempt in range(1, GENERATION_RETRIES + 1):
        try:
            resp = safe_chat_completion(
                client=client,
                prompt_text=prompt_text,
                model=model,
                stream=False,
                max_tokens=max_tokens,
                temperature=0.3,
                top_p=1,
                presence_penalty=0,
                frequency_penalty=0,
                response_format={"type": "text"},
                extra_body={"top_k": 50, "repetition_penalty": 1, "min_p": 0}
            )
            raw = extract_response_text(resp)
            candidate = extract_tagged_or_clean_text(raw, tag_name)
            if candidate:
                _GENERATION_REASONING_ONLY_STREAK = 0
                return candidate
            last_candidate = candidate
            preview = (raw or "")[:180].replace("\n", " ")
            print(
                f"[GEN] Empty parsed {tag_name} attempt={attempt}/{GENERATION_RETRIES} "
                f"raw_len={len(raw or '')} preview={preview!r}"
            )
            if is_reasoning_only_output(raw):
                _GENERATION_REASONING_ONLY_STREAK += 1
                if _GENERATION_REASONING_ONLY_STREAK >= GENERATION_DISABLE_AFTER_REASONING_ONLY:
                    _GENERATION_LLM_DISABLED = True
                    print(
                        f"[GEN] Disabled LLM generation after {_GENERATION_REASONING_ONLY_STREAK} "
                        "reasoning-only outputs for this run."
                    )
                    return ""
        except Exception as e:
            print(f"[WARN] {tag_name} generation attempt {attempt}/{GENERATION_RETRIES} failed: {e!r}")

        # Retry with a stricter reminder if the output is empty.
        prompt_text = (
            f"{prompt_text}\n\n"
            f"Reminder: return only <{tag_name}>...</{tag_name}> with non-empty content and no reasoning."
        )
        time.sleep(TIME_DELAY)

    return last_candidate or ""


def summarize_text(text, client, model):
    """
    Generate a question and summary for a given text block using the LLM.
    Returns (question, summary).
    """
    print(f"[DEBUG] Generating question for block text (length={len(text)}):")
    print(f"[DEBUG] Text preview: {text[:120].replace(chr(10), ' ')}{'...' if len(text) > 120 else ''}")
    question_context = build_generation_context(text, QUESTION_MAX_INPUT_CHARS)
    question_prompt = build_question_prompt(question_context)
    try:
        question = generate_text_with_retries(
            client=client,
            model=model,
            prompt_text=question_prompt,
            tag_name="question",
            max_tokens=256
        )
        print(f"[DEBUG] Question result: {question[:120]}{'...' if len(question) > 120 else ''}")
    except Exception as e:
        print(f"[WARN] Could not generate question: {e!r}")
        question = ""
    if not question:
        if ALLOW_GENERATION_FALLBACK:
            question = fallback_question(text)
            print(f"[DEBUG] Question fallback used: {question[:120]}{'...' if len(question) > 120 else ''}")
        else:
            raise RuntimeError("Question generation returned empty output and fallbacks are disabled.")
    time.sleep(TIME_DELAY)

    print(f"[DEBUG] Generating summary for block text (length={len(text)}):")
    summary_context = build_generation_context(text, SUMMARY_MAX_INPUT_CHARS)
    summary_prompt = build_summary_prompt(summary_context)
    try:
        summary = generate_text_with_retries(
            client=client,
            model=model,
            prompt_text=summary_prompt,
            tag_name="summary",
            max_tokens=320
        )
        print(f"[DEBUG] Summary result: {summary[:120]}{'...' if len(summary) > 120 else ''}")
    except Exception as e:
        print(f"[WARN] Could not generate summary: {e!r}")
        summary = ""
    if not summary:
        if ALLOW_GENERATION_FALLBACK:
            summary = fallback_summary(text)
            print(f"[DEBUG] Summary fallback used: {summary[:120]}{'...' if len(summary) > 120 else ''}")
        else:
            raise RuntimeError("Summary generation returned empty output and fallbacks are disabled.")
    time.sleep(TIME_DELAY)
    return question, summary


def build_content_check_prompt(text, question, summary):
    context = build_generation_context(text, min(SUMMARY_MAX_INPUT_CHARS, 9000))
    return (
        "You are a strict quality gate for technical-book RAG chunks.\n"
        "Decide whether this block should be indexed for retrieval.\n\n"
        "Output exactly one token: yes or no.\n\n"
        "Decision policy:\n"
        "- no: table of contents, index pages, appendix/tool directories, long URL/link lists,\n"
        "  legal/copyright/publisher/contact pages, acknowledgements, ads, ordering info,\n"
        "  or OCR-garbled text.\n"
        "- yes: real instructional content (concept explanations, procedures, examples,\n"
        "  commands, technical reasoning, security guidance).\n\n"
        "Mixed-content rule:\n"
        "- If most of the block is list/index/directory style with little explanation, choose no.\n"
        "- If substantial instructional explanation is present, choose yes.\n\n"
        "Tie-breaker:\n"
        "- If truly uncertain after applying the rules, choose yes.\n\n"
        f"Question: {question}\n"
        f"Summary: {summary}\n\n"
        f"{context}\n"
    )


def parse_content_check_answer(raw_text):
    stripped = strip_think_tags(raw_text or "").strip().lower()
    if not stripped:
        return True, "empty_default_yes"

    yes_match = re.search(r"\byes\b", stripped)
    no_match = re.search(r"\bno\b", stripped)
    if yes_match and no_match:
        return (yes_match.start() < no_match.start()), stripped
    if yes_match:
        return True, stripped
    if no_match:
        return False, stripped

    if "true" in stripped and "false" not in stripped:
        return True, stripped
    if "false" in stripped and "true" not in stripped:
        return False, stripped

    return True, stripped


def assess_block_book_content(text, question, summary, client, model):
    if not CONTENT_CHECK_ENABLED:
        return True, "disabled"

    prompt = build_content_check_prompt(text, question, summary)
    try:
        resp = safe_chat_completion(
            client,
            prompt_text=prompt,
            model=model,
            max_tokens=CONTENT_CHECK_MAX_TOKENS,
            temperature=0.0,
            top_p=1.0,
            response_format={"type": "text"},
        )
        raw = extract_response_text(resp)
        keep, parsed = parse_content_check_answer(raw)
        decision = "yes" if keep else "no"
        print(f"[FILTER] book_content={decision} parsed={parsed[:120]!r}")
        return keep, parsed
    except Exception as exc:
        print(f"[WARN] Content check failed ({exc!r}); defaulting to yes.")
        return True, f"error_default_yes:{exc!r}"


def sanitize_filename(name):
    # Replace spaces with underscores, remove special characters except dash, underscore, and dot
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w\-.]", "", name)
    return name


def _to_int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_non_empty(chunks, keys):
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for key in keys:
            value = chunk.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
    return ""


def _extract_page_bounds(chunks):
    starts = []
    ends = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        start_val = (
            chunk.get("start_page")
            if chunk.get("start_page") is not None
            else chunk.get("page_start")
        )
        end_val = (
            chunk.get("end_page")
            if chunk.get("end_page") is not None
            else chunk.get("page_end")
        )
        if start_val is None:
            start_val = chunk.get("page")
        if end_val is None:
            end_val = chunk.get("page")

        start_i = _to_int_or_none(start_val)
        end_i = _to_int_or_none(end_val)

        if start_i is not None:
            starts.append(start_i)
        if end_i is not None:
            ends.append(end_i)

    page_start = min(starts) if starts else None
    page_end = max(ends) if ends else None
    return page_start, page_end


def _build_doc_id(input_json, source_title, source_chunk_total):
    src = f"{os.path.basename(input_json)}|{source_title}|{source_chunk_total}"
    return "doc_" + hashlib.sha1(src.encode("utf-8")).hexdigest()[:16]


def build_ingest_records(input_json, blocks):
    source_chunks = []
    if input_json and os.path.exists(input_json):
        try:
            with open(input_json, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                source_chunks = payload
        except Exception as exc:
            print(f"[WARN] Could not read source chunks '{input_json}': {exc!r}")

    source_chunk_total = len(source_chunks)
    source_title = _first_non_empty(source_chunks, ["source_title", "book_title", "title"])
    if not source_title:
        source_title = os.path.splitext(os.path.basename(input_json or "source"))[0]

    def should_keep_block(block):
        value = block.get("is_book_content", True)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("no", "false", "0", "n"):
                return False
            if normalized in ("yes", "true", "1", "y"):
                return True
        return True

    filtered_blocks = [b for b in blocks if isinstance(b, dict) and should_keep_block(b)]
    dropped = len(blocks) - len(filtered_blocks)
    if dropped > 0:
        print(f"[FILTER] Dropping {dropped} non-content blocks from ingest output.")

    doc_id = _build_doc_id(input_json or "source", source_title, source_chunk_total)
    chunk_total = len(filtered_blocks)
    records = []

    for idx, block in enumerate(filtered_blocks, start=1):
        start = _to_int_or_none(block.get("start")) or idx
        end = _to_int_or_none(block.get("end")) or start
        if start < 1:
            start = 1
        if end < start:
            end = start
        if source_chunk_total > 0 and end > source_chunk_total:
            end = source_chunk_total
        if source_chunk_total > 0 and start > source_chunk_total:
            start = source_chunk_total

        covered = source_chunks[start - 1 : end] if source_chunk_total > 0 else []
        page_start, page_end = _extract_page_bounds(covered)
        source_title_local = _first_non_empty(covered, ["source_title", "book_title", "title"])
        if not source_title_local:
            source_title_local = source_title

        chunk_id = f"{doc_id}:chunk_{idx:05d}"
        prev_chunk_id = f"{doc_id}:chunk_{idx - 1:05d}" if idx > 1 else ""
        next_chunk_id = f"{doc_id}:chunk_{idx + 1:05d}" if idx < chunk_total else ""

        record = {
            "input": block.get("question", ""),
            "summary": block.get("summary", ""),
            "output": block.get("text", ""),
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "chunk_index": idx,
            "chunk_count": chunk_total,
            "chunk_start": start,
            "chunk_end": end,
            "semantic_block_index": _to_int_or_none(block.get("semantic_block_index")) or idx,
            "source_title": source_title_local,
            "source_file": os.path.basename(input_json or ""),
            "source_chunk_total": source_chunk_total,
            "page_start": page_start if page_start is not None else "",
            "page_end": page_end if page_end is not None else "",
            "prev_chunk_id": prev_chunk_id,
            "next_chunk_id": next_chunk_id,
        }

        records.append(record)

    return records


def write_second_json_file(input_json, output_json):
    """
    Reads semantic block output and writes an ingest-ready JSON file with
    input/summary/output plus locator metadata for follow-up retrieval.
    """
    new_dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
    output_dir = os.path.dirname(output_json) or "."
    base_name, new_ext = os.path.splitext(os.path.basename(output_json))
    safe_base_name = sanitize_filename(base_name)
    new_filename = os.path.join(output_dir, f"{safe_base_name}_out_{new_dt_str}{new_ext}")

    with open(output_json, "r", encoding="utf-8") as f:
        blocks = json.load(f)

    new_array = build_ingest_records(input_json, blocks)

    with open(new_filename, "w", encoding="utf-8") as f:
        json.dump(new_array, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Created new file: {new_filename}")

def safe_chat_completion(client, prompt_text: str, **kwargs):
    """
    Wrapper that retries on empty‑choice responses / network hiccups.
    If all retries fail it writes the prompt + raw response to disk.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            enforce_rate_limit_cooldown()
            enforce_rate_limit()
            req_started = time.monotonic()
            print(
                f"[API] Attempt {attempt}/{MAX_RETRIES} timeout={REQUEST_TIMEOUT_SECONDS}s "
                f"prompt_chars={len(prompt_text)}"
            )
            request_kwargs = dict(kwargs)
            request_kwargs.setdefault("timeout", REQUEST_TIMEOUT_SECONDS)
            resp = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user",   "content": prompt_text}
                ],
                **request_kwargs
            )

            # ---------- happy path ----------
            if resp.choices:
                elapsed = time.monotonic() - req_started
                print(f"[API] Success attempt={attempt} elapsed={elapsed:.1f}s choices={len(resp.choices)}")
                note_rate_limit_recovery()
                return resp

            # ---------- empty‑choices ----------
            print(f"[WARN] Empty 'choices' (attempt {attempt}/{MAX_RETRIES})")

        except Exception as e:
            print(f"[WARN] API exception {e!r} (attempt {attempt}/{MAX_RETRIES})")
            if is_rate_limit_error(e):
                note_rate_limit_error()

        # back‑off before next try
        sleep_time = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 2)
        time.sleep(sleep_time)

    # ============== all retries failed  ==============
    dump_dir = pathlib.Path("llm_debug")
    dump_dir.mkdir(exist_ok=True)

    with (dump_dir / "failed_prompt.txt").open("w", encoding="utf-8") as f:
        f.write(prompt_text)

    # resp might be undefined if all attempts threw exceptions
    raw = resp.to_dict() if "resp" in locals() else {"error": "no response object"}
    with (dump_dir / "failed_response.json").open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    raise RuntimeError("LLM API kept returning 0 choices (debug written to llm_debug/)")

def main():
    # -------- CLI parsing -------------------------------------------------
    args = sys.argv[1:]
    resume = False
    mode = "single"
    config_path = DEFAULT_CONFIG_FILE

    if "--config" in args:
        idx = args.index("--config")
        if idx + 1 >= len(args):
            print(f"[FATAL ERROR] --config requires a file path.\nUsage: {sys.argv[0]} input_chunks.json [output_file.json] [--resume] [--single|--all] [--config path]")
            sys.exit(1)
        config_path = args[idx + 1]
        del args[idx:idx + 2]

    if "--resume" in args:
        resume = True
        args.remove("--resume")
    if "--all" in args:
        mode = "all"
        args.remove("--all")
    if "--single" in args:
        mode = "single"
        args.remove("--single")

    runtime_config = load_runtime_config(config_path)
    apply_runtime_overrides(runtime_config)

    if mode == "single" and len(args) < 1:
        print(
            f"Usage: {sys.argv[0]} input_chunks.json [output_file.json] [--resume] [--single|--all] [--config path]\n"
            "  --resume   Continue from an existing semantic_blocks.json if present;\n"
            "             without it, any existing output file is backed up (.bak) and overwritten.\n"
            "  --single   (default) Process a single file (input_chunks.json)\n"
            "  --all      Process all .json files in the current directory that do not have a date suffix\n"
            "  --config   Optional runtime model config JSON file"
        )
        sys.exit(1)

    def process_one_file(input_json, output_json, resume):
        global _GENERATION_REASONING_ONLY_STREAK, _GENERATION_LLM_DISABLED
        _GENERATION_REASONING_ONLY_STREAK = 0
        _GENERATION_LLM_DISABLED = False

        # -------- API client --------------------------------------------------
        load_dotenv()
        api_key = os.getenv(API_KEY_ENV)
        if not api_key:
            print(f"[FATAL ERROR] Missing API key environment variable ({API_KEY_ENV}).")
            sys.exit(1)
        client = OpenAI(base_url=NOVITA_API_URL, api_key=api_key)
        print(f"[INFO] Using model={MODEL_NAME}, base_url={NOVITA_API_URL}, tokenizer={TOKENIZER_NAME}, timeout={REQUEST_TIMEOUT_SECONDS}s")

        # -------- Load chunks --------------------------------------------------
        print(f"[INFO] Reading input chunks from {input_json} …")
        all_chunks = load_chunks(input_json)
        tok = get_tokenizer()

        # --------- Check for oversized chunks and fallback to llm_rechunk if needed ---------
        oversized = False
        for idx, chunk in enumerate(all_chunks):
            token_count = len(tok.encode(chunk))
            # MAX_CONTEXT is the LLM's hard limit, MAX_TOKENS is only for output
            if token_count > (MAX_CONTEXT - MAX_TOKENS):
                print(f"[FATAL] Chunk {idx+1} is too large for LLM context window ({token_count} tokens > {MAX_CONTEXT - MAX_TOKENS}). Falling back to llm_rechunk.py.")
                oversized = True
                break

        if oversized:
            import subprocess
            # Compose output file name
            dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
            input_base, _ = os.path.splitext(os.path.basename(input_json))
            output_json = f"{input_base.replace(' ', '_')}_{dt_str}.json"
            print(f"[INFO] Calling llm_rechunk.py on {input_json} ...")
            subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), "llm_rechunk.py"), input_json, output_json],
                check=True
            )
            print(f"[INFO] llm_rechunk.py completed. Output: {output_json}")
            return

        # -------- Resume or start fresh ---------------------------------------
        if resume:
            semantic_blocks, pointer = resume_previous(output_json)
            if semantic_blocks:
                print(f"[INFO] Resuming from chunk {pointer} (next is {pointer + 1})")
            else:
                print("[INFO] No previous progress found – starting fresh.")
                semantic_blocks, pointer = [], 0
        else:
            if os.path.exists(output_json):
                shutil.copy2(output_json, output_json + ".bak")
                print(f"[INFO] Existing output file backed up to {output_json}.bak")
            semantic_blocks, pointer = [], 0
            # create/overwrite with empty list so downstream writes always succeed
            with open(output_json, "w", encoding="utf-8") as f:
                f.write("[]")

        # -------- Main loop ---------------------------------------------------
        SAFETY_BUFFER = 100  # tokens
        reserved_output_tokens = MAX_TOKENS + SAFETY_BUFFER
        adaptive_window_size = max(ADAPTIVE_MIN_WINDOW, min(ADAPTIVE_MAX_WINDOW, WINDOW_SIZE))
        adaptive_mode_logged = False

        while pointer < len(all_chunks):
            current_start_chunk = all_chunks[pointer] if pointer < len(all_chunks) else ""
            front_matter = is_front_matter_chunk(current_start_chunk)
            section_heading = looks_like_section_heading(current_start_chunk)
            targets = compute_context_targets(
                MAX_CONTEXT,
                reserved_output_tokens,
                is_front_matter=front_matter,
                has_section_heading=section_heading
            )

            current_window_size = adaptive_window_size
            timeout_retries_left = ADAPTIVE_TIMEOUT_RETRIES
            end_idx = None
            debug_msg = ""
            window_chunks = []
            total_tokens = 0
            cur_window_size = 0
            next_window_size = adaptive_window_size

            while True:
                window_chunks, total_tokens, cur_window_size = build_adaptive_window(
                    all_chunks,
                    pointer,
                    current_window_size,
                    tok,
                    build_boundary_prompt,
                    MAX_CONTEXT,
                    reserved_output_tokens,
                    min_prompt_tokens=targets["min_prompt_tokens"] if ADAPTIVE_WINDOW else 0,
                    max_window_size=ADAPTIVE_MAX_WINDOW if ADAPTIVE_WINDOW else current_window_size
                )

                if ADAPTIVE_WINDOW:
                    next_window_size, adapt_reason = adjust_adaptive_window_size(
                        current_window_size,
                        total_tokens,
                        targets["target_prompt_tokens"],
                        targets["max_prompt_tokens"]
                    )
                    fill_ratio = total_tokens / max(1, targets["usable_context"])
                    print(
                        f"[ADAPT] mode=on class={'front-matter' if front_matter else 'chapter'} "
                        f"fill={fill_ratio:.2f} window_now={cur_window_size} window_next={next_window_size} "
                        f"reason={adapt_reason} min_tokens={targets['min_prompt_tokens']} "
                        f"target_tokens={targets['target_prompt_tokens']} max_tokens={targets['max_prompt_tokens']}"
                    )
                elif not adaptive_mode_logged:
                    print(f"[ADAPT] Disabled. Using fixed window size {adaptive_window_size}")
                    adaptive_mode_logged = True
                    next_window_size = adaptive_window_size
                else:
                    next_window_size = adaptive_window_size

                # ---- DEBUG PRINTS ----
                print("\n=== BLOCK DEBUG ===")
                print(f"Pointer before: {pointer}")
                print(f"Window size   : {cur_window_size}")
                print(f"Window chunks : {list(range(pointer + 1, pointer + cur_window_size + 1))}")
                print(f"Prompt tokens : {total_tokens}")
                for idx, chunk in enumerate(window_chunks):
                    preview = chunk[:60].replace('\n', ' ')
                    print(f"  [{pointer + idx + 1}] {preview}{'…' if len(chunk) > 60 else ''}")
                # ---- END DEBUG PRINTS ----

                if not window_chunks:
                    print(f"[FATAL] Could not fit any chunks in context window at pointer {pointer}. Skipping file.")
                    return

                available_output_tokens = MAX_CONTEXT - total_tokens
                actual_max_tokens = min(MAX_TOKENS, available_output_tokens)
                if actual_max_tokens < 128:
                    print(f"[FATAL] Not enough room for output tokens (only {actual_max_tokens} left). Skipping file.")
                    return

                end_idx, debug_msg = get_semantic_block_end(
                    window_chunks, client, MODEL_NAME, actual_max_tokens
                )

                if end_idx is None and ADAPTIVE_WINDOW and timeout_retries_left > 0 and is_timeout_like_error(debug_msg):
                    reduced = max(
                        ADAPTIVE_MIN_WINDOW,
                        min(cur_window_size - 1, int(round(cur_window_size * ADAPTIVE_TIMEOUT_SHRINK)))
                    )
                    if reduced < current_window_size:
                        timeout_retries_left -= 1
                        current_window_size = reduced
                        print(
                            f"[ADAPT] Timeout-like response; retrying pointer {pointer + 1} "
                            f"with smaller window {current_window_size} (retries left: {timeout_retries_left})"
                        )
                        continue
                break

            if ADAPTIVE_WINDOW:
                adaptive_window_size = next_window_size

            if end_idx is None:
                print("\n" + "=" * 60 + "\nFATAL segmentation error\n" + "=" * 60)
                print(debug_msg)
                with open(output_json, "w", encoding="utf-8") as f:
                    json.dump(semantic_blocks, f, ensure_ascii=False, indent=2)
                print(f"[ERROR] Skipping file {input_json} due to fatal segmentation error.")
                return

            if end_idx < 1 or end_idx > len(window_chunks):
                print(f"[ERROR] LLM returned invalid index: {end_idx}. Aborting.")
                break

            corrected_end = end_idx - 1 if end_idx > 1 else 1
            corrected_end = apply_front_matter_guard(window_chunks, corrected_end, front_matter)
            corrected_end = apply_heading_transition_guard(window_chunks, corrected_end)
            block_text    = "\n".join(window_chunks[:corrected_end])

            print(f"[DEBUG] LLM response: {end_idx}")
            print(f"[DEBUG] Block: start={pointer + 1}, end={pointer + corrected_end}")
            print("[DEBUG] Chunks added to output:")
            for i in range(corrected_end):
                preview = window_chunks[i][:60].replace('\n', ' ')
                ellipsis = '…' if len(window_chunks[i]) > 60 else ''
                print(f"  [{pointer + i + 1}] {preview}{ellipsis}")

            question, summary = summarize_text(block_text, client, MODEL_NAME)
            is_book_content, content_check = assess_block_book_content(
                block_text,
                question,
                summary,
                client,
                MODEL_NAME
            )
            print(
                f"[FILTER] Block {pointer + 1}-{pointer + corrected_end} "
                f"classified as {'book-content' if is_book_content else 'noise'}"
            )
            semantic_blocks.append(
                {
                    "start": pointer + 1,
                    "end": pointer + corrected_end,
                    "text": block_text,
                    "question": question,
                    "summary": summary,
                    "is_book_content": is_book_content,
                    "content_check": content_check,
                    "semantic_block_index": len(semantic_blocks) + 1,
                }
            )

            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(semantic_blocks, f, ensure_ascii=False, indent=2)

            pointer += corrected_end  # advance to next unprocessed chunk

        print("[INFO] Done.")

        # --------- Write a second JSON file from the first (for reusability) ---------
        write_second_json_file(input_json, output_json)
        print(f"[INFO] Created new file: {output_json}")


    if mode == "all":
        # Find all .json files in the current directory that do NOT have a date suffix
        all_jsons = glob.glob("*.json")
        date_pat = re.compile(r"_\d{14}(\.json)?$")
        to_process = [f for f in all_jsons if not date_pat.search(f)]
        # Only process files that do NOT have a corresponding _out_ file (completed job)
        filtered_to_process = []
        for f in to_process:
            input_base, _ = os.path.splitext(os.path.basename(f))
            # Look for any file with _out_ and the input_base in the name
            out_pattern = f"{input_base}_out_*.json"
            out_files = glob.glob(out_pattern)
            if out_files:
                # Check if the _out_ file is actually complete
                out_file = out_files[0]
                try:
                    with open(f, "r", encoding="utf-8") as fin:
                        input_data = json.load(fin)
                    with open(out_file, "r", encoding="utf-8") as fout:
                        out_data = json.load(fout)
                    if len(out_data) == len(input_data):
                        print(f"[INFO] Skipping {f} (already has complete _out_ file: {out_file})")
                        continue
                    else:
                        print(f"[WARN] _out_ file {out_file} is incomplete ({len(out_data)}/{len(input_data)} records). Will retry.")
                        # Empty the _out_ file so we can retry
                        with open(out_file, "w", encoding="utf-8") as fout:
                            json.dump([], fout)
                except Exception as e:
                    print(f"[WARN] Could not check completeness of {out_file}: {e!r}. Will retry.")
                    # Empty the _out_ file so we can retry
                    try:
                        with open(out_file, "w", encoding="utf-8") as fout:
                            json.dump([], fout)
                    except Exception as e2:
                        print(f"[ERROR] Could not empty {out_file}: {e2!r}")
            filtered_to_process.append(f)
        if not filtered_to_process:
            print("[INFO] No .json files found to process (all jobs completed).")
            sys.exit(0)
        for input_json in filtered_to_process:
            input_base, _ = os.path.splitext(os.path.basename(input_json))
            dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
            output_json = f"{input_base.replace(' ', '_')}_{dt_str}.json"
            print(f"[INFO] Processing {input_json} ...")
            try:
                process_one_file(input_json, output_json, resume)
            except Exception as e:
                print(f"[ERROR] Failed to process {input_json}: {e!r}")
                import traceback
                traceback.print_exc()
                continue
        print("[INFO] Batch processing complete.")
        sys.exit(0)
    else:
        if len(args) < 1:
            print(
                f"Usage: {sys.argv[0]} input_chunks.json [output_file.json] [--resume] [--single|--all] [--config path]\n"
                "  --resume   Continue from an existing semantic_blocks.json if present;\n"
                "             without it, any existing output file is backed up (.bak) and overwritten.\n"
                "  --single   (default) Process a single file (input_chunks.json)\n"
                "  --all      Process all .json files in the current directory that do not have a date suffix\n"
                "  --config   Optional runtime model config JSON file"
            )
            sys.exit(1)
        input_json = args[0]
        dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
        if len(args) > 1:
            base_output = args[1]
            # In single-file mode, honor the caller-provided output path exactly.
            # The batch retry runner depends on this deterministic filename.
            output_json = base_output
        else:
            input_base, _ = os.path.splitext(os.path.basename(input_json))
            output_json = f"{input_base.replace(' ', '_')}_{dt_str}.json"
        process_one_file(input_json, output_json, resume)

if __name__ == "__main__":
    main()
