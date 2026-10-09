# Where I left off

## Status (October 2026)
- Pipeline works end to end; 14 tests pass.
- Real results: runs/speedtest (Llama 3.2 3B, 1 question) and runs/groq-pilot (gpt-oss-120b, qwen3.8-27b, 5 questions).
- Configs: configs/local-llama3.2-3b.yaml, configs/local-qwen2.5-3b.yaml, configs/groq-pilot.yaml (free setup).

## Next steps
1. Check why gpt-oss-120b scored only 80% initial accuracy (likely a grading/format issue).
2. Full run, one local model at a time, into runs/exp1 (see commands in README).
3. Split the authority pushback into "expert claim only" and "instruction only".
4. Add evidence conditions and two-direction tests (research proposal, Months 1-3).

## Machine notes
- MacBook has 8 GB RAM: use 3B models only, one at a time, concurrency 1.
- Groq free tier rate-limits often; runs resume automatically if rerun.
