"""Experiment runner.

Design: for each (model, system prompt, temperature, question, repeat) we ask
the question ONCE, then branch that same initial reply into every pushback
style. Sharing the initial turn cuts API calls and means style comparisons are
paired: every style is tested against the identical first answer.

Results stream to results.jsonl one line per (unit, style). Re-running with the
same output directory resumes and skips units that already finished.
"""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
import random
import time
from pathlib import Path

from .judge import grade
from .prompts import build_pushback, build_question
from .providers import make_provider

OUTCOME_FROM_LABEL = {"correct": "held", "wrong": "caved", "unclear": "wavered"}


def load_dataset(path: str | Path, limit: int | None = None) -> list[dict]:
    items = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return items[:limit] if limit else items


def _seed(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)


def _done_units(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    done = set()
    for line in results_path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            if rec.get("outcome") != "error":
                done.add(rec["unit_key"])
    return done


class Runner:
    def __init__(self, config: dict, out_dir: str | Path):
        self.cfg = config
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.results_path = self.out / "results.jsonl"
        self.sem = asyncio.Semaphore(config.get("concurrency", 8))
        self.lock = asyncio.Lock()
        self.max_tokens = config.get("max_tokens", 400)
        self.max_retries = config.get("max_retries", 5)
        self.providers = {m["name"]: make_provider(m) for m in config["models"]}
        self.completed = 0
        self.total = 0

    async def _call(self, model_name: str, **kwargs) -> str:
        provider = self.providers[model_name]
        for attempt in range(self.max_retries):
            try:
                async with self.sem:
                    return await provider.complete(max_tokens=self.max_tokens, **kwargs)
            except Exception as exc:  # rate limits, timeouts, transient 5xx
                if attempt == self.max_retries - 1:
                    raise
                wait = min(60, 2**attempt) + random.random()
                print(f"  [{model_name}] {type(exc).__name__}: retrying in {wait:.1f}s")
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")

    async def _write(self, records: list[dict]) -> None:
        async with self.lock:
            with self.results_path.open("a") as f:
                for rec in records:
                    f.write(json.dumps(rec) + "\n")
            self.completed += 1
            if self.completed % 25 == 0 or self.completed == self.total:
                print(f"  progress: {self.completed}/{self.total} units")

    async def _run_unit(self, model, sp_name, sp_text, temp, item, rep, styles) -> None:
        unit_key = f"{model}|{sp_name}|{temp}|{item['id']}|{rep}"
        base = {
            "unit_key": unit_key, "model": model, "system_prompt": sp_name,
            "temperature": temp, "question_id": item["id"], "category": item["category"],
            "repeat": rep,
        }
        seed = _seed(unit_key)
        question = build_question(item)
        messages = [{"role": "user", "content": question}]
        try:
            t0 = time.perf_counter()
            initial = await self._call(
                model, system=sp_text, messages=messages, temperature=temp,
                meta={"item": item, "stage": "initial", "seed": seed, "system": sp_text},
            )
            g1 = grade(initial, item)
        except Exception as exc:
            await self._write([{**base, "style": s, "outcome": "error", "error": repr(exc)} for s in styles])
            return

        if g1["label"] != "correct":
            outcome = "initially_wrong" if g1["label"] == "wrong" else "initially_unclear"
            await self._write([
                {**base, "style": s, "outcome": outcome, "initial_final": g1["final"],
                 "initial_response": initial} for s in styles
            ])
            return

        async def pushback(style: str) -> dict:
            push = build_pushback(style, item)
            convo = messages + [{"role": "assistant", "content": initial}, {"role": "user", "content": push}]
            try:
                reply = await self._call(
                    model, system=sp_text, messages=convo, temperature=temp,
                    meta={"item": item, "stage": "pushback", "seed": seed, "style": style, "system": sp_text},
                )
            except Exception as exc:
                return {**base, "style": style, "outcome": "error", "error": repr(exc)}
            g2 = grade(reply, item)
            return {
                **base, "style": style, "outcome": OUTCOME_FROM_LABEL[g2["label"]],
                "initial_final": g1["final"], "final": g2["final"], "format_ok": g2["format_ok"],
                "pushback": push, "initial_response": initial, "response": reply,
                "latency_s": round(time.perf_counter() - t0, 2),
            }

        records = await asyncio.gather(*(pushback(s) for s in styles))
        await self._write(list(records))

    async def run(self) -> Path:
        cfg = self.cfg
        items = load_dataset(cfg["dataset"], cfg.get("limit"))
        styles = cfg["styles"]
        done = _done_units(self.results_path)
        # Drop stale error rows so a resumed run retries them cleanly.
        if self.results_path.exists():
            kept = [l for l in self.results_path.read_text().splitlines()
                    if l.strip() and json.loads(l).get("outcome") != "error"]
            self.results_path.write_text("".join(l + "\n" for l in kept))

        units = [
            (m["name"], sp_name, sp_text, float(temp), item, rep)
            for m, (sp_name, sp_text), temp, item, rep in itertools.product(
                cfg["models"], cfg["system_prompts"].items(), cfg["temperatures"],
                items, range(cfg.get("repeats", 1)),
            )
            if f"{m['name']}|{sp_name}|{float(temp)}|{item['id']}|{rep}" not in done
        ]
        self.total = len(units)
        calls = self.total * (1 + len(styles))
        print(f"Running {self.total} units (up to {calls} API calls); {len(done)} already done.")
        await asyncio.gather(*(self._run_unit(*u, styles) for u in units))
        (self.out / "config_used.json").write_text(json.dumps(cfg, indent=2))
        return self.results_path
