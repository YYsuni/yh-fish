# -*- coding: utf-8 -*-
"""钢琴执行器：按 `images/piano/page.json` 识别当前页，再执行各页处理函数（与超强音结构类似，暂以页面轮询为主）。"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from capture_service import CaptureService

import tools.exec_msg as exec_msg
import tools.game_input as game_input
from features.manager.manager_tick import CooldownGate

_log = logging.getLogger(__name__)

DEFAULT_POLL_S = 0.05
DEFAULT_BEAT_SECONDS = 1.0
MIN_BEAT_SECONDS = 0.05
MAX_BEAT_SECONDS = 120.0

PIANO_SCORES_DIR = Path(__file__).resolve().parent / "scores"
LEGACY_SCORE_PATH = Path(__file__).with_name("default.json")

NOTE_KEYS = {
    **{f"low{i}": key for i, key in enumerate("zxcvbnm", start=1)},
    **{f"mid{i}": key for i, key in enumerate("asdfghj", start=1)},
    **{f"high{i}": key for i, key in enumerate("qwertyu", start=1)},
}
NOTE_ALIASES = {
    "低": "low",
    "低音": "low",
    "中": "mid",
    "中音": "mid",
    "高": "high",
    "高音": "high",
}


@dataclass
class PianoTickContext:
    hwnd: int
    page_match: dict[str, object]
    monotonic: float
    capture: CaptureService
    cooldown: CooldownGate
    executor: "PianoExecutor"


def _noop_page(ctx: PianoTickContext) -> None:
    _ = ctx


def _page_21_key(ctx: PianoTickContext) -> None:
    ctx.executor.play_due_note(ctx.hwnd, ctx.monotonic)


PIANO_PAGE_HANDLERS: dict[str, Callable[[PianoTickContext], None]] = {
    "21-key": _page_21_key,
}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_scores_dir() -> None:
    PIANO_SCORES_DIR.mkdir(parents=True, exist_ok=True)


def _file_times_iso(path: Path) -> tuple[str, str]:
    st = path.stat()
    birth = getattr(st, "st_birthtime", None)
    if birth is None:
        birth = st.st_ctime
    c = datetime.fromtimestamp(birth, tz=timezone.utc).replace(microsecond=0)
    u = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).replace(microsecond=0)
    fmt = lambda d: d.isoformat().replace("+00:00", "Z")
    return fmt(c), fmt(u)


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent="\t")
        f.write("\n")
    tmp.replace(path)


def _migrate_legacy_default_json() -> None:
    _ensure_scores_dir()
    if any(PIANO_SCORES_DIR.glob("*.json")):
        return
    if not LEGACY_SCORE_PATH.is_file():
        return
    try:
        with LEGACY_SCORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        _log.exception("legacy piano score migrate failed")
        return
    if not isinstance(data, dict):
        return
    now = _utc_iso_now()
    data.setdefault("createAt", now)
    data["updateAt"] = now
    dest = PIANO_SCORES_DIR / "欢乐颂.json"
    try:
        _atomic_write_json(dest, data)
    except Exception:
        _log.exception("failed writing migrated score to %s", dest)


def _resolve_score_path(score_id: str) -> Path | None:
    if not score_id or "/" in score_id or "\\" in score_id or score_id.strip() != score_id:
        return None
    base = PIANO_SCORES_DIR.resolve()
    p = (PIANO_SCORES_DIR / f"{score_id}.json").resolve()
    try:
        p.relative_to(base)
    except ValueError:
        return None
    return p


def _update_sort_key(path: Path, data: dict[str, object]) -> float:
    raw = data.get("updateAt")
    if isinstance(raw, str) and raw.strip():
        try:
            return datetime.fromisoformat(raw.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return path.stat().st_mtime


def _load_score(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        _log.exception("failed to load piano score path=%s", path)
        return {"title": "", "notes": []}
    return data if isinstance(data, dict) else {"title": "", "notes": []}


def _normalize_pitch_value(raw: object) -> str:
    """将音符 pitch 规范为 low / mid / high。"""
    if raw is None:
        return "mid"
    s = str(raw).strip().replace(" ", "").replace("-", "").replace("_", "").lower()
    if not s:
        return "mid"
    for zh, prefix in sorted(NOTE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if s == zh.lower():
            return prefix
    if s in ("low", "mid", "high"):
        return s
    raise ValueError(f"pitch must be low/mid/high or 低/中/高等别名，当前: {raw!r}")


def _validate_and_normalize_notes(raw_notes: object) -> list[dict[str, object]]:
    if not isinstance(raw_notes, list):
        raise ValueError("notes must be a list")
    out: list[dict[str, object]] = []
    for i, it in enumerate(raw_notes):
        if not isinstance(it, dict):
            raise ValueError(f"notes[{i}] must be an object")
        beat_raw = it.get("beat", 1)
        try:
            beat_f = float(beat_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"notes[{i}].beat invalid") from None
        if beat_f <= 0:
            raise ValueError(f"notes[{i}].beat must be positive")
        raw_keys = it.get("keys")
        if isinstance(raw_keys, list):
            keys: list[dict[str, object]] = []
            for j, raw_key in enumerate(raw_keys):
                if not isinstance(raw_key, dict):
                    raise ValueError(f"notes[{i}].keys[{j}] must be an object")
                n_raw = raw_key.get("num", 0)
                if isinstance(n_raw, bool):
                    raise ValueError(f"notes[{i}].keys[{j}].num invalid")
                keys.append({"num": str(n_raw).strip(), "pitch": _normalize_pitch_value(raw_key.get("pitch", "mid"))})
            out.append({"keys": keys, "beat": beat_f})
            continue
        n_raw = it.get("num", 0)
        if isinstance(n_raw, bool):
            raise ValueError(f"notes[{i}].num invalid")
        num_s = str(n_raw).strip()
        pitch_s = _normalize_pitch_value(it.get("pitch", "mid"))
        out.append({"num": num_s, "pitch": pitch_s, "beat": beat_f})
    return out


def _empty_score() -> dict[str, object]:
    return {"title": "", "notes": [], "beatSeconds": DEFAULT_BEAT_SECONDS}


class PianoExecutor:
    """与 `CaptureService` 同进程：轮询 `page_match`（钢琴模式下由捕获管线按 piano/page.json 填充）。"""

    def __init__(self, capture: CaptureService) -> None:
        self._capture = capture
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_page_id: str | None = None
        self._cooldown = CooldownGate()
        _migrate_legacy_default_json()
        self._selected_score_id = ""
        self._score: dict[str, object] = _empty_score()
        self._note_index = 0
        self._next_note_at = 0.0
        self._bootstrap_selected_score()

    def _bootstrap_selected_score(self) -> None:
        summaries = self.list_score_summaries_unlocked()
        if not summaries:
            return
        first_id = summaries[0]["id"]
        assert isinstance(first_id, str)
        path = _resolve_score_path(first_id)
        if path and path.is_file():
            self._selected_score_id = first_id
            self._score = _load_score(path)

    def is_running(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def list_score_summaries_unlocked(self) -> list[dict[str, object]]:
        _ensure_scores_dir()
        paths = list(PIANO_SCORES_DIR.glob("*.json"))
        enriched: list[tuple[float, Path, dict[str, object]]] = []
        for path in paths:
            data = _load_score(path)
            create_at, update_at = _file_times_iso(path)
            ca = data.get("createAt")
            ua = data.get("updateAt")
            if isinstance(ca, str) and ca.strip():
                create_at = ca.strip()
            if isinstance(ua, str) and ua.strip():
                update_at = ua.strip()
            title = str(data.get("title", "")).strip() or path.stem
            notes = _score_notes(data)
            enriched.append((_update_sort_key(path, data), path, {"id": path.stem, "title": title, "createAt": create_at, "updateAt": update_at, "note_count": len(notes)}))
        enriched.sort(key=lambda x: x[0], reverse=True)
        return [item[2] for item in enriched]

    def list_score_summaries(self) -> list[dict[str, object]]:
        with self._lock:
            return self.list_score_summaries_unlocked()

    def status_dict(self) -> dict[str, object]:
        with self._lock:
            last = self._last_page_id
            note_index = self._note_index
            score = self._score
            sid = self._selected_score_id
        return {
            "running": self.is_running(),
            "last_page_id": last,
            "beat_seconds": _score_beat_seconds(score),
            "score_title": str(score.get("title", "")),
            "score_id": sid,
            "note_index": note_index,
            "note_count": len(_score_notes(score)),
        }

    def set_selected_score(self, score_id: str) -> dict[str, object]:
        path = _resolve_score_path(score_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(score_id)
        data = _load_score(path)
        with self._lock:
            self._selected_score_id = score_id
            self._score = data
            self._note_index = 0
            self._next_note_at = 0.0
        return {"score_id": score_id}

    def get_score(self, score_id: str) -> dict[str, object]:
        path = _resolve_score_path(score_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(score_id)
        data = _load_score(path)
        create_at, update_at = _file_times_iso(path)
        ca = data.get("createAt")
        ua = data.get("updateAt")
        data["id"] = score_id
        data["createAt"] = ca.strip() if isinstance(ca, str) and ca.strip() else create_at
        data["updateAt"] = ua.strip() if isinstance(ua, str) and ua.strip() else update_at
        return data

    def update_score(self, score_id: str, title: str, beat_seconds: float, notes: list[dict[str, object]]) -> dict[str, object]:
        path = _resolve_score_path(score_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(score_id)
        cur = _load_score(path)
        created = cur.get("createAt")
        if not (isinstance(created, str) and created.strip()):
            created, _ = _file_times_iso(path)
        bs = min(MAX_BEAT_SECONDS, max(MIN_BEAT_SECONDS, float(beat_seconds)))
        norm_notes = _validate_and_normalize_notes(notes)
        now = _utc_iso_now()
        body: dict[str, object] = {
            "title": title.strip() or "未命名",
            "beatSeconds": bs,
            "notes": norm_notes,
            "createAt": str(created).strip(),
            "updateAt": now,
        }
        _atomic_write_json(path, body)
        with self._lock:
            if self._selected_score_id == score_id:
                self._score = body
                self._note_index = 0
                self._next_note_at = 0.0
        return {"id": score_id, "title": body["title"], "createAt": body["createAt"], "updateAt": now, "note_count": len(norm_notes)}

    def update_score_from_raw_dict(self, score_id: str, raw: dict[str, object]) -> dict[str, object]:
        path = _resolve_score_path(score_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(score_id)
        if not isinstance(raw.get("notes"), list):
            raise ValueError("missing notes")
        cur = _load_score(path)
        created = raw.get("createAt")
        if not (isinstance(created, str) and created.strip()):
            created = cur.get("createAt")
        if not (isinstance(created, str) and created.strip()):
            created, _ = _file_times_iso(path)
        title = str(raw.get("title", "")).strip() or "未命名"
        beat_seconds = _score_beat_seconds(raw)
        norm_notes = _validate_and_normalize_notes(raw.get("notes"))
        now = _utc_iso_now()
        body: dict[str, object] = {
            "title": title,
            "beatSeconds": beat_seconds,
            "notes": norm_notes,
            "createAt": str(created).strip(),
            "updateAt": now,
        }
        _atomic_write_json(path, body)
        with self._lock:
            if self._selected_score_id == score_id:
                self._score = body
                self._note_index = 0
                self._next_note_at = 0.0
        return {"id": score_id, "title": title, "createAt": body["createAt"], "updateAt": now, "note_count": len(norm_notes)}

    def delete_score(self, score_id: str) -> dict[str, object]:
        path = _resolve_score_path(score_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(score_id)
        path.unlink()

        next_score_id = ""
        next_score = _empty_score()
        summaries = self.list_score_summaries_unlocked()
        if summaries:
            raw_id = summaries[0].get("id")
            if isinstance(raw_id, str):
                next_path = _resolve_score_path(raw_id)
                if next_path is not None and next_path.is_file():
                    next_score_id = raw_id
                    next_score = _load_score(next_path)

        with self._lock:
            if self._selected_score_id == score_id:
                self._selected_score_id = next_score_id
                self._score = next_score
                self._note_index = 0
                self._next_note_at = 0.0
        return {"deleted": True, "score_id": score_id, "selected_id": next_score_id}

    def create_score(self, title: str, beat_seconds: float, notes: list[dict[str, object]]) -> dict[str, object]:
        bs = min(MAX_BEAT_SECONDS, max(MIN_BEAT_SECONDS, float(beat_seconds)))
        norm_notes = _validate_and_normalize_notes(notes)
        now = _utc_iso_now()
        score_id = secrets.token_hex(8)
        path = _resolve_score_path(score_id)
        if path is None:
            raise ValueError("invalid score id")
        body: dict[str, object] = {
            "title": title.strip() or "未命名",
            "beatSeconds": bs,
            "notes": norm_notes,
            "createAt": now,
            "updateAt": now,
        }
        _atomic_write_json(path, body)
        with self._lock:
            self._selected_score_id = score_id
            self._score = body
            self._note_index = 0
            self._next_note_at = 0.0
        return {"id": score_id, "title": body["title"], "createAt": now, "updateAt": now, "note_count": len(norm_notes)}

    def create_score_from_raw_dict(self, raw: dict[str, object]) -> dict[str, object]:
        if not isinstance(raw.get("notes"), list):
            raise ValueError("missing notes")
        title = str(raw.get("title", "")).strip() or "未命名"
        beat_seconds = _score_beat_seconds(raw)
        notes_list = raw.get("notes")
        norm_notes = _validate_and_normalize_notes(notes_list)
        now = _utc_iso_now()
        score_id = secrets.token_hex(8)
        path = _resolve_score_path(score_id)
        if path is None:
            raise ValueError("invalid score id")
        created = raw.get("createAt")
        created_s = now
        if isinstance(created, str) and created.strip():
            created_s = created.strip()
        body: dict[str, object] = {
            "title": title,
            "beatSeconds": beat_seconds,
            "notes": norm_notes,
            "createAt": created_s,
            "updateAt": now,
        }
        _atomic_write_json(path, body)
        with self._lock:
            self._selected_score_id = score_id
            self._score = body
            self._note_index = 0
            self._next_note_at = 0.0
        return {"id": score_id, "title": title, "createAt": created_s, "updateAt": now, "note_count": len(norm_notes)}

    def start(self) -> dict[str, object]:
        if self.is_running():
            return {"running": True, "started": False}
        self._stop.clear()
        with self._lock:
            self._note_index = 0
            self._next_note_at = 0.0
        exec_msg.msg_out("钢琴启动")
        self._thread = threading.Thread(target=self._loop, name="piano", daemon=True)
        self._thread.start()
        return {"running": True, "started": True}

    def stop(self) -> dict[str, object]:
        was_running = self.is_running()
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3.0)
        self._thread = None
        if was_running:
            exec_msg.msg_out("钢琴停止")
        return {"running": False}

    def play_due_note(self, hwnd: int, now: float) -> None:
        note: dict[str, object] | None = None
        note_index = 0
        note_count = 0
        beat_seconds = DEFAULT_BEAT_SECONDS
        with self._lock:
            if self._next_note_at > 0 and now < self._next_note_at:
                return
            notes = _score_notes(self._score)
            note_count = len(notes)
            if self._note_index >= note_count:
                if self._next_note_at > 0:
                    exec_msg.msg_out("钢琴曲谱结束，已停止")
                    self._next_note_at = 0.0
                    self._stop.set()
                return
            note_index = self._note_index
            note = notes[note_index]
            beat_seconds = _score_beat_seconds(self._score)
            self._note_index += 1
            self._next_note_at = now + _note_beat(note) * beat_seconds

        keys = _note_keys(note)
        if not keys:
            exec_msg.msg_out(f"钢琴休止 {_note_label(note)} {note_index + 1}/{note_count}")
            return

        down_ok = [game_input.send_key_down(hwnd, ord(key.upper())) for key in keys]
        up_ok = [game_input.send_key_up(hwnd, ord(key.upper())) for key in reversed(keys)]
        ok = all(down_ok) and all(up_ok)
        label = _note_label(note)
        suffix = "" if ok else "（发送失败）"
        exec_msg.msg_out(f"钢琴 {label} -> {'+'.join(keys)} {note_index + 1}/{note_count}{suffix}")

    def _loop(self) -> None:
        me = threading.current_thread()
        try:
            while not self._stop.is_set():
                if self._capture.get_capture_context() != "piano":
                    with self._lock:
                        self._last_page_id = None
                    time.sleep(0.05)
                    continue

                s = self._capture.get_status()
                pm = s.page_match
                page_id: str | None = None
                if isinstance(pm, dict):
                    pid = pm.get("page_id")
                    if isinstance(pid, str):
                        page_id = pid
                with self._lock:
                    self._last_page_id = page_id

                if not s.ok or s.hwnd is None:
                    time.sleep(0.2)
                    continue
                if not isinstance(pm, dict):
                    time.sleep(0.05)
                    continue

                hwnd = s.hwnd
                now = time.monotonic()
                ctx = PianoTickContext(
                    hwnd=hwnd,
                    page_match=dict(pm),
                    monotonic=now,
                    capture=self._capture,
                    cooldown=self._cooldown,
                    executor=self,
                )
                try:
                    if page_id:
                        PIANO_PAGE_HANDLERS.get(page_id, _noop_page)(ctx)
                except Exception:
                    _log.exception("piano page handler failed page_id=%s", page_id)

                time.sleep(DEFAULT_POLL_S)
        finally:
            if self._thread is me:
                self._thread = None


def _score_notes(score: dict[str, object]) -> list[dict[str, object]]:
    raw = score.get("notes")
    if not isinstance(raw, list):
        return []
    return [it for it in raw if isinstance(it, dict)]


def _score_beat_seconds(score: dict[str, object]) -> float:
    """一拍时长优先读曲谱根字段 ``beatSeconds``（或兼容 ``beat_seconds``），否则可由 ``bpm`` 推导。"""
    for key in ("beatSeconds", "beat_seconds"):
        raw = score.get(key)
        if raw is None:
            continue
        try:
            v = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if v > 0:
            return min(MAX_BEAT_SECONDS, max(MIN_BEAT_SECONDS, v))

    raw_bpm = score.get("bpm")
    if raw_bpm is None:
        return DEFAULT_BEAT_SECONDS
    try:
        bpm = float(raw_bpm)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_BEAT_SECONDS
    if bpm <= 0:
        return DEFAULT_BEAT_SECONDS
    derived = 60.0 / bpm
    return min(MAX_BEAT_SECONDS, max(MIN_BEAT_SECONDS, derived))


def _note_label(note: dict[str, object]) -> str:
    """用于日志展示的音符标签。"""
    tones = _note_tones(note)
    if len(tones) > 1:
        beat = _note_beat(note)
        return f"{'+'.join(_tone_label(t) for t in tones)} beat={beat:g}"
    pitch = _note_pitch(note)
    num = _note_num_value(note)
    beat = _note_beat(note)
    if num is None:
        return f"rest beat={beat:g}"
    if pitch:
        return f"{pitch}{num} beat={beat:g}"
    raw = note.get("num", "0")
    return f"{str(raw).strip()} beat={beat:g}"


def _tone_label(tone: dict[str, object]) -> str:
    pitch = _note_pitch(tone)
    num = _note_num_value(tone)
    if num is None:
        return "rest"
    return f"{pitch or 'mid'}{num}"


def _note_tones(note: dict[str, object]) -> list[dict[str, object]]:
    raw = note.get("keys")
    if isinstance(raw, list):
        return [it for it in raw if isinstance(it, dict)]
    return [note]


def _note_pitch(note: dict[str, object]) -> str | None:
    raw = note.get("pitch")
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "").replace("-", "").replace("_", "").lower()
    if not s:
        return None
    for zh, prefix in sorted(NOTE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if s == zh:
            return prefix
    if s in ("low", "mid", "high"):
        return s
    return None


def _note_num_value(note: dict[str, object]) -> int | None:
    raw = note.get("num", 0)
    if isinstance(raw, (int, float)):
        n = int(raw)
        return None if n == 0 else n
    s = str(raw).strip()
    if s in ("", "0"):
        return None
    if s.isdigit():
        n = int(s)
        return None if n == 0 else n
    return None


def _note_beat(note: dict[str, object]) -> float:
    raw = note.get("beat", 1)
    try:
        beat = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1.0
    return beat if beat > 0 else 1.0


def _note_key(note: dict[str, object]) -> str | None:
    # 新格式：{ num: 1-7/0, beat: ..., pitch: low/mid/high }
    num = _note_num_value(note)
    if num is None:
        return None
    pitch = _note_pitch(note)
    if pitch in ("low", "mid", "high"):
        return NOTE_KEYS.get(f"{pitch}{num}")

    # 兼容旧格式：num 直接写 "mid5"/"低音5"/"5"
    raw = note.get("num", "0")
    n = str(raw).strip().replace(" ", "").replace("-", "").replace("_", "").lower()
    if n in ("", "0", "rest", "pause"):
        return None
    if n and n[0].isdigit():
        return NOTE_KEYS.get(f"mid{n[0]}")
    for zh, prefix in sorted(NOTE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if n.startswith(zh):
            digit = n[len(zh) :]
            if digit and digit[0].isdigit():
                return NOTE_KEYS.get(f"{prefix}{digit[0]}")
            return None
    return NOTE_KEYS.get(n)


def _note_keys(note: dict[str, object]) -> list[str]:
    out: list[str] = []
    for tone in _note_tones(note):
        key = _note_key(tone)
        if key is not None and key not in out:
            out.append(key)
    return out
