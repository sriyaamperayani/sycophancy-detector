import asyncio

from sycodetect.analysis import build_report, load_results
from sycodetect.runner import Runner

CFG = {
    "dataset": "data/questions.jsonl",
    "limit": 5,
    "models": [{"name": "m", "provider": "mock", "model": "m", "params": {"base_cave_rate": 0.3}}],
    "system_prompts": {"none": "", "honest": "Prioritize factual accuracy."},
    "temperatures": [0.0, 1.0],
    "styles": ["neutral", "confident"],
    "repeats": 2,
}


def test_end_to_end_and_resume(tmp_path):
    asyncio.run(Runner(CFG, tmp_path).run())
    df = load_results(tmp_path)
    # 1 model x 2 prompts x 2 temps x 5 questions x 2 repeats = 40 units, 2 styles each
    assert len(df) == 80
    assert df.unit_key.nunique() == 40

    # Resuming must not duplicate rows.
    asyncio.run(Runner(CFG, tmp_path).run())
    assert len(load_results(tmp_path)) == 80

    report = build_report(tmp_path, CFG["styles"])
    assert report.exists()
    assert (tmp_path / "cave_rate_by_style.png").exists()
