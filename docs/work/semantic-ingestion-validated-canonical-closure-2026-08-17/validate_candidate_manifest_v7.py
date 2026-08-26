from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
MANIFEST = Path(__file__).with_name("candidate-manifest-v7.json")
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--expected-candidate-lock",required=True); args=parser.parse_args()
    failures=[]
    if sha(MANIFEST)!=args.expected_candidate_lock: failures.append("candidate_lock_mismatch")
    manifest=json.loads(MANIFEST.read_text()); tracked={item["path"]:item for item in manifest["tracked_files"]}
    for relative,item in tracked.items():
        path=ROOT/relative
        if not path.is_file() or sha(path)!=item["sha256"]: failures.append(f"tracked_artifact_mismatch:{relative}")
    print(json.dumps({"schema":"memorii.design-candidate-validation.v7","passed":not failures,"candidate_lock":args.expected_candidate_lock,"tracked_artifact_count":len(tracked),"failures":failures},sort_keys=True))
    if failures: raise SystemExit(1)
if __name__=="__main__": main()
