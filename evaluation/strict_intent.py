"""Controller-owned acceptance runner: exact source labels, exclusions, scope and Task fields.

Only request text reaches production. Gold annotations are never part of model input.
Implementation agents must not change this scorer or gold cases.
"""
import argparse
import hashlib
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.main import execute_task
from core import context, paths, runtime


def fingerprint():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.execution_sources()}


def _pairs(mapping):
    return {(int(index), category) for index, categories in mapping.items() for category in categories}


def check(case, output):
    clauses = context.source_clauses(case['source'])
    span_to_index = {(c['text'], c['start'], c['end']): i for i, c in enumerate(clauses)}
    data = output['intent']
    errors = []
    if data.get('input_kind') not in case.get('input_kinds', ['request']):
        errors.append({'kind': 'input_kind', 'expected': case.get('input_kinds',['request']), 'actual':data.get('input_kind')})
    expected_units = case['units']; actual_units = data.get('intents', [])
    summary = 'no_intent' if not expected_units else expected_units[0]['intent'] if len(expected_units)==1 else 'multi_intent'
    if data.get('intent') != summary:
        errors.append({'kind':'routing_summary','expected':summary,'actual':data.get('intent')})
    if data.get('source_text') != case['source']:
        errors.append({'kind':'source_text'})
    def unit_errors(expected, actual):
        result=[]
        if actual.get('intent') != expected['intent']:
            result.append({'kind':'business_type','expected':expected['intent'],'actual':actual.get('intent')})
        if actual.get('subtype') not in expected.get('subtypes', [actual.get('subtype')]):
            result.append({'kind':'subtype','expected':expected['subtypes'],'actual':actual.get('subtype')})
        required = _pairs(expected['required']); allowed = required | _pairs(expected.get('optional',{}))
        found=set()
        for k in actual.get('keywords',[]):
            idx=span_to_index.get((k.get('text'),k.get('start'),k.get('end')))
            if idx is None:
                result.append({'kind':'source_span','actual':k})
            else:
                found.add((idx,k['category']))
        for idx, cat in sorted(required-found):
            result.append({'kind':'missing_label','intent':expected['intent'],'category':cat,'clause':idx,'text':clauses[idx]['text']})
        for idx, cat in sorted(found-allowed):
            result.append({'kind':'extra_label','intent':expected['intent'],'category':cat,'clause':idx,'text':clauses[idx]['text']})
        return result
    if len(actual_units)!=len(expected_units):
        errors.append({'kind':'intent_count','expected':len(expected_units),'actual':len(actual_units)})
    else:
        # Ordering is not a business constraint. Find the best one-to-one match.
        permutations=itertools.permutations(actual_units) if len(actual_units)<=5 else [actual_units]
        candidates=([e for exp,act in zip(expected_units,perm) for e in unit_errors(exp,act)] for perm in permutations)
        errors.extend(min(candidates,key=len,default=[]))
    # Independently reject broken projections, even if production declares verification true.
    def keyword_key(k):
        return (k.get('category'),k.get('text'),k.get('start'),k.get('end'))
    root_keys={keyword_key(k) for k in data.get('keywords',[])}
    unit_keys={keyword_key(k) for u in actual_units for k in u.get('keywords',[])}
    if root_keys != unit_keys:
        errors.append({'kind':'keyword_projection'})
    for unit in actual_units:
        evidence={(e.get('text'),e.get('start'),e.get('end')) for e in unit.get('evidence',[])}
        if not evidence or not evidence.issubset(span_to_index):
            errors.append({'kind':'evidence_source'})
        if any((k.get('text'),k.get('start'),k.get('end')) not in evidence for k in unit.get('keywords',[])):
            errors.append({'kind':'keyword_scope'})
        levels=[keyword_key(k) for level in ('common','business','operation') for k in unit.get('information',{}).get(level,[])]
        if sorted(levels) != sorted(keyword_key(k) for k in unit.get('keywords',[])):
            errors.append({'kind':'information_projection'})
    if output['result'].get('keywords') != data.get('keywords') or output['result'].get('intents') != actual_units:
        errors.append({'kind':'task_intent_projection'})
    # Check final business projection independently of production mapping helpers.
    result=output['result']
    if result.get('source_text') != case['source']:
        errors.append({'kind':'task_source'})
    for field, indices in case.get('task_required',{}).items():
        required={clauses[i]['text'] for i in indices}
        allowed=required | {clauses[i]['text'] for i in case.get('task_optional',{}).get(field,[])}
        values=result.get(field)
        if not isinstance(values,list) or any(not isinstance(v,str) for v in values):
            errors.append({'kind':'task_field_type','field':field,'actual':values});continue
        if required-set(values):
            errors.append({'kind':'task_missing','field':field,'expected':sorted(required),'actual':values})
        if set(values)-allowed:
            errors.append({'kind':'task_extra','field':field,'expected':sorted(allowed),'actual':values})
    if not expected_units and (data.get('keywords') or result.get('keywords') or result.get('intents')):
        errors.append({'kind':'non_request_extraction'})
    if not all(output.get('verification',{}).get(k) for k in ('schema_valid','source_grounded','mapping_valid')):
        errors.append({'kind':'verification'})
    return errors


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--model',default='qwen3:4b')
    parser.add_argument('--think',action='store_true')
    parser.add_argument('--repeats',type=int,default=1)
    parser.add_argument('--timeout',type=float,default=120)
    args=parser.parse_args()
    if args.output.exists():parser.error('output exists; preserve prior results')
    cases=json.loads(args.cases.read_text())
    report={'model':args.model,'think':args.think,'repeats':args.repeats,'started_at':datetime.now(timezone.utc).isoformat(),
            'case_hash':hashlib.sha256(args.cases.read_bytes()).hexdigest(),'source_hashes':fingerprint(),
            'planned':len(cases)*args.repeats,'cases':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    original=runtime.read_model_response
    for repeat in range(args.repeats):
        for case in cases:
            if fingerprint()!=report['source_hashes']:
                raise RuntimeError('Production code changed during acceptance; freeze before testing')
            metrics=[]
            def measured(req,timeout):
                payload=json.loads(req.data)
                raw=original(req,timeout)
                metrics.append({'model':payload.get('model'),'think':payload.get('think'),
                                **{k:raw.get(k) for k in ('prompt_eval_count','eval_count','total_duration')}})
                return raw
            started=perf_counter()
            try:
                with patch.object(runtime,'read_model_response',side_effect=measured):
                    output=execute_task(case['source'],model=args.model,think=args.think,timeout_seconds=args.timeout)
                errors=check(case,output)
                item={'id':case['id'],'repeat':repeat,'source':case['source'],'output':output,'errors':errors}
            except (ValueError,TypeError,OSError,KeyError) as exc:
                item={'id':case['id'],'repeat':repeat,'source':case['source'],'errors':[{'kind':'runtime','message':str(exc)}]}
            item.update(passed=not item['errors'],elapsed_seconds=round(perf_counter()-started,3),model_calls=len(metrics),metrics=metrics)
            report['cases'].append(item)
            report['passed']=sum(c['passed'] for c in report['cases'])
            report['completed']=len(report['cases'])
            report['status']='complete' if report['completed']==report['planned'] else 'partial'
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            kinds=sorted({e['kind'] for e in item['errors']})
            print(f"{case['id']} round={repeat+1} {'PASS' if item['passed'] else 'FAIL'} {kinds} {item['elapsed_seconds']}s",flush=True)
    print(f"TOTAL {report['passed']}/{report['completed']}",flush=True)
    raise SystemExit(0 if report['passed']==report['planned'] else 2)


if __name__=='__main__':main()
