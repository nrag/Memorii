"""Record one exact local gate command and its terminal evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("name")
parser.add_argument("--cwd", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    parser.error("command required")
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
started = time.time()
candidate_path = os.environ.get("SCOPED_CANDIDATE_MANIFEST")
candidate_digest = None
if candidate_path:
    candidate = Path(candidate_path)
    candidate_digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
with (output / (args.name + ".log")).open("w") as log:
    result = subprocess.run(command, cwd=args.cwd, stdout=log, stderr=subprocess.STDOUT, check=False)
log_path = output / (args.name + ".log")
record = {"name": args.name, "argv": command, "cwd": args.cwd,
          "exit_status": result.returncode, "elapsed_seconds": round(time.time() - started, 3),
          "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
          "source_revision_label": os.environ.get("MEMORII_SOURCE_REVISION"),
          "candidate_manifest_sha256": candidate_digest,
          "evidence": "local working-tree execution only"}
(output / (args.name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record), flush=True)
raise SystemExit(result.returncode)
