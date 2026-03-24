import json
import os
import re
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

POSTPROCESS_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "postprocess_config.json")
LEGACY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "semantic_rechunk_config.json")


class RateController:
    def __init__(
        self,
        rate_limit_per_minute: int,
        request_timeout_seconds: int,
        max_retries: int = 3,
        base_delay_seconds: float = 8.0,
        cooldown_seconds: float = 15.0,
        cooldown_max_seconds: float = 120.0,
        dynamic_step: float = 0.5,
        dynamic_max_multiplier: float = 4.0,
        recovery_successes: int = 6,
    ) -> None:
        self.rate_limit_per_minute = max(1, int(rate_limit_per_minute))
        self.request_timeout_seconds = max(5, int(request_timeout_seconds))
        self.max_retries = max(1, int(max_retries))
        self.base_delay_seconds = max(0.1, float(base_delay_seconds))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.cooldown_max_seconds = max(self.cooldown_seconds, float(cooldown_max_seconds))
        self.dynamic_step = max(0.0, float(dynamic_step))
        self.dynamic_max_multiplier = max(1.0, float(dynamic_max_multiplier))
        self.recovery_successes = max(1, int(recovery_successes))

        self._request_timestamps: deque[float] = deque()
        self._last_request_ts = 0.0
        self._cooldown_until = 0.0
        self._streak_429 = 0
        self._success_streak = 0
        self._multiplier = 1.0

    def _target_interval_seconds(self) -> float:
        return 60.0 / float(self.rate_limit_per_minute)

    def wait_before_call(self) -> None:
        now = time.time()

        # Respect explicit cooldown after 429 bursts.
        if now < self._cooldown_until:
            wait = self._cooldown_until - now
            print(f"[RATE] 429 cooldown waiting {wait:.2f}s")
            time.sleep(wait)
            now = time.time()

        # Sliding-window guard.
        while self._request_timestamps and (now - self._request_timestamps[0]) >= 60.0:
            self._request_timestamps.popleft()
        if len(self._request_timestamps) >= self.rate_limit_per_minute:
            wait = 60.0 - (now - self._request_timestamps[0])
            if wait > 0:
                print(f"[RATE] Minute-window guard waiting {wait:.2f}s")
                time.sleep(wait)
                now = time.time()

        target = self._target_interval_seconds() * self._multiplier
        since_last = now - self._last_request_ts if self._last_request_ts > 0 else 1e9
        if since_last < target:
            wait = target - since_last
            print(
                f"[RATE] Spacing guard waiting {wait:.2f}s "
                f"(target {target:.2f}s/request, base {self._target_interval_seconds():.2f}s, x{self._multiplier:.2f}, streak={self._streak_429})"
            )
            time.sleep(wait)

    def mark_request_sent(self) -> None:
        now = time.time()
        self._last_request_ts = now
        self._request_timestamps.append(now)

    def on_success(self) -> None:
        self._streak_429 = 0
        self._success_streak += 1
        if self._success_streak >= self.recovery_successes and self._multiplier > 1.0:
            self._multiplier = max(1.0, self._multiplier - self.dynamic_step)
            self._success_streak = 0

    def on_429(self) -> None:
        self._success_streak = 0
        self._streak_429 += 1

        # Escalate spacing multiplier slowly.
        self._multiplier = min(self.dynamic_max_multiplier, self._multiplier + self.dynamic_step)

        # Cooldown grows with streak.
        cooldown = min(self.cooldown_max_seconds, self.cooldown_seconds * (2 ** max(0, self._streak_429 - 1)))
        self._cooldown_until = max(self._cooldown_until, time.time() + cooldown)
        print(f"[RATE] 429 detected streak={self._streak_429} cooldown={cooldown:.2f}s")


def normalize_openai_base_url(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if value.lower().endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value


def load_runtime_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    if not config_path:
        config_path = POSTPROCESS_CONFIG_FILE if os.path.exists(POSTPROCESS_CONFIG_FILE) else LEGACY_CONFIG_FILE
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Config file {config_path} must contain a JSON object")
    return payload


def _env_key_name(config: Dict[str, Any]) -> str:
    val = config.get("LlmHFKeyEnv") or config.get("api_key_env") or "LlmHFKey"
    return str(val).strip() if val else "LlmHFKey"


def create_client_from_config(config: Dict[str, Any]) -> tuple[OpenAI, str, int, RateController]:
    load_dotenv()

    model = str(config.get("LlmHFModelID") or config.get("model_name") or "meta/llama-3.3-70b-instruct").strip()
    raw_url = str(config.get("LlmHFUrl") or config.get("api_url") or config.get("api_base_url") or "https://integrate.api.nvidia.com/v1/chat/completions")
    base_url = normalize_openai_base_url(raw_url)

    api_key_env = _env_key_name(config)
    api_key = os.getenv(api_key_env) or os.getenv("LlmHFKey")
    if not api_key:
        raise RuntimeError(f"Missing API key env var '{api_key_env}' (or fallback 'LlmHFKey').")

    timeout_seconds = int(config.get("RequestTimeoutSeconds") or config.get("request_timeout_seconds") or 240)
    rate_limit = int(config.get("RateLimitPerMinute") or config.get("rate_limit_per_minute") or 15)

    controller = RateController(
        rate_limit_per_minute=rate_limit,
        request_timeout_seconds=timeout_seconds,
        max_retries=int(config.get("HfRetryMaxAttempts") or 3),
        base_delay_seconds=float(config.get("HfRetryDelaySeconds") or 8),
        cooldown_seconds=float(config.get("RateLimit429CooldownSeconds") or 15),
        cooldown_max_seconds=float(config.get("RateLimit429CooldownMaxSeconds") or 120),
        dynamic_step=float(config.get("RateLimitDynamicSpacingStep") or 0.5),
        dynamic_max_multiplier=float(config.get("RateLimitDynamicSpacingMaxMultiplier") or 4.0),
        recovery_successes=int(config.get("RateLimitRecoverySuccesses") or 6),
    )

    client = OpenAI(base_url=base_url, api_key=api_key)
    return client, model, timeout_seconds, controller


def strip_think_tags(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"(?is)<think>.*?(?:</think>|$)", "", text).strip()


def extract_text_from_response(resp: Any) -> str:
    if not getattr(resp, "choices", None):
        return ""
    msg = resp.choices[0].message
    content = getattr(msg, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text") or item.get("content") or item.get("value")
                if txt:
                    parts.append(str(txt))
        return "\n".join(parts)
    return str(content or "")


def estimate_prompt_tokens(text: str) -> int:
    # Lightweight estimate suitable for logging only.
    # Counts words and punctuation-like symbols as token units.
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))


def ts_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_chat_completion(
    client: OpenAI,
    controller: RateController,
    model: str,
    prompt_text: str,
    max_tokens: int,
    temperature: float = 0.0,
    call_label: str = "",
    call_meta: Optional[Dict[str, Any]] = None,
) -> str:
    last_error: Optional[Exception] = None
    max_retries = controller.max_retries

    prompt_tokens = estimate_prompt_tokens(prompt_text)
    call_id = uuid.uuid4().hex[:8]
    label = (call_label or "").strip() or "llm_call"
    meta_text = ""
    if isinstance(call_meta, dict) and call_meta:
        parts = []
        for k in sorted(call_meta.keys()):
            try:
                v = call_meta.get(k)
                parts.append(f"{k}={v}")
            except Exception:
                continue
        if parts:
            meta_text = " " + " ".join(parts)
    for attempt in range(1, max_retries + 1):
        try:
            controller.wait_before_call()
            print(
                f"[{ts_utc()}] [API] Attempt {attempt}/{max_retries} "
                f"call_id={call_id} label={label}"
                f"{meta_text} "
                f"timeout={controller.request_timeout_seconds}s "
                f"prompt_tokens={prompt_tokens}"
            )
            start = time.time()
            controller.mark_request_sent()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=1,
                stream=False,
                timeout=controller.request_timeout_seconds,
                response_format={"type": "text"},
            )
            elapsed = time.time() - start
            print(
                f"[{ts_utc()}] [API] Success attempt={attempt} call_id={call_id} "
                f"label={label}{meta_text} elapsed={elapsed:.1f}s choices={len(resp.choices or [])}"
            )
            controller.on_success()
            return extract_text_from_response(resp)
        except Exception as exc:  # keep broad for provider-specific error classes
            last_error = exc
            txt = repr(exc)
            if "429" in txt or "RateLimit" in txt or "Too Many Requests" in txt:
                controller.on_429()
            print(
                f"[{ts_utc()}] [WARN] API exception call_id={call_id} label={label}{meta_text} "
                f"{txt} (attempt {attempt}/{max_retries})"
            )
            if attempt < max_retries:
                delay = controller.base_delay_seconds * (2 ** (attempt - 1))
                time.sleep(delay)

    raise RuntimeError(f"API failed after {max_retries} attempts: {last_error!r}")
