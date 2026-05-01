from __future__ import annotations
import argparse, json
from datetime import UTC, datetime
from pathlib import Path
from memorii.core.llm_config import LLMLiveTestConfig, LLMRuntimeConfig
from memorii.core.llm_decision.adapters import LLMBeliefUpdateAdapter, LLMPromotionDecisionAdapter
from memorii.core.llm_decision.models import EvalSnapshot, LLMDecisionMode
from memorii.core.llm_eval.golden import belief_golden_v1, promotion_golden_v1
from memorii.core.llm_eval.models import EvalRunReport
from memorii.core.llm_eval.runner import OfflineLLMEvalRunner
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry

class EvalFakeClient:
    provider_name = "fake"
    def complete_structured(self, request: LLMStructuredRequest, *, config: LLMRuntimeConfig) -> LLMStructuredResponse:
        del config
        if request.prompt_ref == "promotion_decision:v1":
            raw = '{"promote":false,"target_plane":null,"confidence":0.5,"rationale":"dry run","failure_mode":null,"requires_judge_review":true}'
        elif request.prompt_ref == "belief_update:v1":
            raw = '{"belief":0.5,"confidence":0.5,"rationale":"dry run","failure_mode":null,"requires_judge_review":true}'
        else:
            raw = "{}"
        return LLMStructuredResponse(request_id=request.request_id, provider=self.provider_name, raw_text=raw, valid_json=False, schema_valid=False)

def _load_snapshots(name:str)->list[EvalSnapshot]:
    if name=="promotion": return promotion_golden_v1()
    if name=="belief": return belief_golden_v1()
    return [*promotion_golden_v1(), *belief_golden_v1()]

def _check_live(mode:str,dry:bool,allow:bool,runtime:LLMRuntimeConfig,live:LLMLiveTestConfig)->None:
    if mode=="rule" or dry: return
    if runtime.provider.strip().lower() in {"none","fake"}:
        raise SystemExit("LLM/HYBRID mode requires non-none/fake provider unless --dry-run.")
    if not allow:
        raise SystemExit("LLM/HYBRID live eval blocked: pass --allow-live.")
    if not live.should_run_live_llm_tests(runtime):
        raise SystemExit("Live eval not permitted by env. Require MEMORII_ENABLE_LIVE_LLM_TESTS=true and API key.")

def _wjsonl(path:Path,rows:list[dict[str,object]])->None:
    path.write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows),encoding="utf-8")

def _safe(s:str)->str: return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)

def _write(storage:Path, report:EvalRunReport, snapshots:list[EvalSnapshot], provider:str, model:str|None, golden_set:str, mode:str)->Path:
    run_dir=storage/"eval_runs"/"llm"/datetime.now(UTC).strftime("%Y-%m-%d")/_safe(report.run_id)
    (run_dir/"inputs").mkdir(parents=True,exist_ok=True)
    (run_dir/"report.json").write_text(json.dumps(report.model_dump(mode="json"),indent=2,sort_keys=True)+"\n",encoding="utf-8")
    _wjsonl(run_dir/"results.jsonl",[r.model_dump(mode="json") for r in report.results])
    _wjsonl(run_dir/"failures.jsonl",[r.model_dump(mode="json") for r in report.results if not r.passed])
    _wjsonl(run_dir/"fallbacks.jsonl",[r.model_dump(mode="json") for r in report.results if r.fallback_used])
    _wjsonl(run_dir/"disagreements.jsonl",[r.model_dump(mode="json") for r in report.results if r.disagreement])
    _wjsonl(run_dir/"inputs"/"snapshots.jsonl",[s.model_dump(mode="json") for s in snapshots])
    req=sum(1 for r in report.results if r.requires_judge_review); fb=sum(1 for r in report.results if r.fallback_used); dg=sum(1 for r in report.results if r.disagreement)
    (run_dir/"summary.txt").write_text(f"run_id: {report.run_id}\nprovider: {provider}\nmodel: {model}\ngolden_set: {golden_set}\nmode: {mode}\ntotal_cases: {report.total_cases}\npassed_cases: {report.passed_cases}\nfailed_cases: {report.failed_cases}\nfallback_cases: {fb}\ndisagreement_cases: {dg}\nrequires_judge_review_cases: {req}\n",encoding="utf-8")
    return run_dir

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser()
    p.add_argument("--golden-set",choices=["promotion","belief","all"],default="all")
    p.add_argument("--mode",choices=["rule","llm","hybrid","all"],default="all")
    p.add_argument("--storage-root",default=".memorii")
    p.add_argument("--prompt-root",default=None)
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--allow-live",action="store_true")
    a=p.parse_args(argv)
    runtime=LLMRuntimeConfig.from_env(); live=LLMLiveTestConfig.from_env(); print(f"runtime_config={runtime.redacted_dict()}")
    _check_live(a.mode,a.dry_run,a.allow_live,runtime,live)
    prompt_root=Path(a.prompt_root) if a.prompt_root else Path(__file__).resolve().parents[2]/"prompts"
    client=EvalFakeClient() if a.dry_run else LLMClientFactory.from_config(runtime)
    runner=PromptLLMRunner(client=client,config=runtime); reg=PromptRegistry(prompt_root=prompt_root)
    eval_runner=OfflineLLMEvalRunner(promotion_llm_adapter=LLMPromotionDecisionAdapter(runner=runner,registry=reg),belief_llm_adapter=LLMBeliefUpdateAdapter(runner=runner,registry=reg))
    snapshots=_load_snapshots(a.golden_set)
    for mode in ([a.mode] if a.mode!="all" else ["rule","llm","hybrid"]):
        report=OfflineLLMEvalRunner(promotion_llm_adapter=eval_runner._promotion_llm_adapter,belief_llm_adapter=eval_runner._belief_llm_adapter,decision_mode=LLMDecisionMode(mode)).run_snapshots(snapshots)
        assert isinstance(report,EvalRunReport)
        out=_write(Path(a.storage_root),report,snapshots,runtime.provider,runtime.model,a.golden_set,mode)
        print(f"mode={mode} total_cases={report.total_cases} passed={report.passed_cases} failed={report.failed_cases} artifacts={out}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
