"""First clean-room current-pin scenario-first closure elaborator; emits a spool-friendly manifest."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('recipe',type=Path); p.add_argument('design',type=Path); p.add_argument('registry',type=Path); p.add_argument('output',type=Path); a=p.parse_args()
    r=json.loads(a.recipe.read_bytes())
    if r['format']!='memorii-sia-c2-normative-fixture-recipe-v1': raise ValueError('format')
    rows=[]
    for f in r['primitive_fixtures']:
        payload=json.dumps(f['body_input'],ensure_ascii=True,separators=(',',':'),sort_keys=True).encode('ascii')
        # The structural fixture is represented by a streamed source digest;
        # callers may spool its reconstructed bytes without changing identity.
        if f['target_artifact_kind']=='structural_manifest': payload=hashlib.sha256(a.design.read_bytes()+a.registry.read_bytes()).digest()
        rows.append([f['fixture_id'],hashlib.sha256(payload).hexdigest()])
    a.output.write_bytes(json.dumps({'format':'memorii-sia-spooled-manifest-v1','members':rows},ensure_ascii=True,separators=(',',':'),sort_keys=True).encode('ascii')+b'\n')
if __name__=='__main__': main()
