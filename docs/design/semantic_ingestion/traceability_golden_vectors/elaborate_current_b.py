"""Independent current-pin scenario-first closure elaborator B; no imports from elaborator A."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def main() -> None:
    c=argparse.ArgumentParser(); c.add_argument('recipe',type=Path); c.add_argument('design',type=Path); c.add_argument('registry',type=Path); c.add_argument('output',type=Path); x=c.parse_args()
    data=json.loads(x.recipe.read_text(encoding='ascii'))
    if set(data)!= {'authority_use','checked_fixture_outputs','fixed_signers','format','nested_substitution_cases','primitive_authority','primitive_fixtures','vector_cases'}: raise ValueError('roots')
    result=[]
    for item in data['primitive_fixtures']:
        raw=json.dumps(item['body_input'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
        if item['fixture_id']=='fixture-10-structural_manifest': raw=hashlib.sha256(x.design.read_bytes()+x.registry.read_bytes()).digest()
        result.append([item['fixture_id'], hashlib.sha256(raw).hexdigest()])
    x.output.write_text(json.dumps({'members':result,'format':'memorii-sia-spooled-manifest-v1'},sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n',encoding='ascii')
if __name__=='__main__': main()
