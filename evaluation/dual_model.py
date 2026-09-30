"""Controller-owned: source goes to production, gold never goes to a model."""
import argparse,hashlib,json,sys,time,math
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.main import execute_task
from core import runtime,paths
from evaluation.strict_intent import check as semantic_check

ROUTES=['store_info','menu_advice','order_support','group_order','complaint','membership_help','campaign_brief','sales_analysis','other_request','multi_intent','no_intent','no_intent','no_intent']
OPTION_MAP={chr(65+i):{'input_kind':'request' if i<10 else ['social','background','unclear'][i-10], 'mode':'ask' if i==12 else 'infer','routing':r} for i,r in enumerate(ROUTES)}

def fingerprint():
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.execution_sources()}

def protocol_check(case,out,events,args):
 errors=[]
 data=out.get('intent',{});d=out.get('decision',{});c=out.get('context',{})
 expected_map=OPTION_MAP.get(d.get('option'))
 if expected_map is None or {k:d.get(k) for k in ('input_kind','mode','routing')}!=expected_map:
  errors.append({'kind':'decision_fixed_mapping','actual':d})
 if data.get('decision')!=d:errors.append({'kind':'decision_checkpoint_projection'})
 if d.get('input_kind')!=data.get('input_kind') or d.get('routing')!=data.get('intent'):
  errors.append({'kind':'decision_extraction_consistency'})
 if 'expected' in case:
  exp=dict(case['expected']);exp['routing']='no_intent' if exp['routing']=='none' else exp['routing']
  for k,v in exp.items():
   if d.get(k)!=v:errors.append({'kind':'decision_semantics','field':k,'expected':v,'actual':d.get(k)})
 else:
  units=case['units'];summary='no_intent' if not units else units[0]['intent'] if len(units)==1 else 'multi_intent'
  if d.get('routing')!=summary:errors.append({'kind':'decision_routing','expected':summary,'actual':d.get('routing')})
 if c.get('source_text')!=case['source'] or c.get('decision')!=d:errors.append({'kind':'context_source_decision'})
 expected_status='needs_human_review' if out.get('manual_review_required') is True else 'needs_clarification' if d.get('mode')=='ask' else 'ready' if data.get('intents') else 'no_intent'
 if c.get('status')!=expected_status:errors.append({'kind':'context_status','expected':expected_status,'actual':c.get('status')})
 if (d.get('mode')=='ask' and not isinstance(c.get('clarification_question'),str)) or (d.get('mode')!='ask' and c.get('clarification_question') is not None):errors.append({'kind':'clarification_contract'})
 if c.get('semantic_verification')!='not_performed' or c.get('business_execution')!='not_performed':errors.append({'kind':'false_business_verification'})
 units=data.get('intents',[]);contexts=c.get('units',[])
 if len(units)!=len(contexts):errors.append({'kind':'context_unit_count'})
 else:
  for i,(u,ctx) in enumerate(zip(units,contexts)):
   expected={'id':f'intent_{i}','intent':u['intent'],'subtype':u['subtype'],'source_spans':u['evidence'],'information':u['information'],'not_observed':u['not_observed'],'verification_needed':u['verification_needed']}
   for k,v in expected.items():
    if ctx.get(k)!=v:errors.append({'kind':'context_unit_projection','unit':i,'field':k})
   if not isinstance(ctx.get('needs_review'),list) or any(not isinstance(v,str) for v in ctx['needs_review']):errors.append({'kind':'context_review_type'})
 if not events:errors.append({'kind':'no_real_model_call'});return errors
 errors.extend(cascade_check(out,events,args))
 return errors

def cascade_check(out,events,args):
 errors=[];data=out.get('intent',{});d=out.get('decision',{});c=out.get('context',{})
 score=out.get('confidence');details=out.get('confidence_details',{});audit=out.get('cascade',{})
 if type(score) not in (int,float) or not math.isfinite(score) or not 0<=score<=1:errors.append({'kind':'confidence_range'})
 for key in ('confidence','confidence_details','cascade','manual_review_required','review_reasons'):
  if any(o.get(key)!=out.get(key) for o in (data,out.get('result',{}),c)):errors.append({'kind':'confidence_projection','field':key})
 expected_reasons=[]
 if type(score) in (int,float) and score<args.confidence_threshold:expected_reasons.append('decision_confidence_low')
 if details.get('metadata_status')!='available':expected_reasons.append('decision_confidence_metadata_unavailable')
 if type(out.get('manual_review_required')) is not bool or out.get('manual_review_required')!=bool(expected_reasons) or out.get('review_reasons')!=expected_reasons:errors.append({'kind':'manual_review_policy'})
 if details.get('calibrated') is not False:errors.append({'kind':'false_confidence_calibration'})
 if audit.get('enabled') is not args.cascade_enabled or type(audit.get('used')) is not bool or audit.get('threshold')!=args.confidence_threshold or audit.get('fallback_model')!=args.fallback_model:errors.append({'kind':'cascade_configuration'})
 used=audit.get('used') is True
 if used and not args.cascade_enabled:errors.append({'kind':'disabled_cascade_used'})
 if used and not isinstance(audit.get('reason'),str):errors.append({'kind':'cascade_reason'})
 # Separate lanes by the native fallback call. Defaults have distinct tags;
 # the first accepted primary decision also permits identical role aliases.
 split=len(events)
 if used and args.fallback_model not in (args.decision_model,args.extraction_model):
  split=next((i for i,e in enumerate(events) if e['model']==args.fallback_model),len(events))
  if split==len(events):errors.append({'kind':'missing_fallback_decision'})
 elif used:
  accepted=next((i for i,e in enumerate(events) if e['format'] is None and isinstance(e.get('response'),str) and e['response'].strip() in OPTION_MAP),None)
  if accepted is not None:
   split=next((i for i,e in enumerate(events) if i>accepted and e['format'] is None),len(events))
  else:split=min(args.max_attempts,len(events))
  if split==len(events):errors.append({'kind':'missing_fallback_decision'})
 lanes=[(events[:split],args.decision_model,args.extraction_model)]
 if used:lanes.append((events[split:],args.fallback_model,args.fallback_model))
 last_valid=None
 for lane,decision_model,extractor_model in lanes:
  first_q=next((i for i,e in enumerate(lane) if isinstance(e['format'],dict)),len(lane))
  names=[e['model'] for e in lane]
  if first_q==0 or names[:first_q]!=[decision_model]*first_q or names[first_q:]!=[extractor_model]*(len(lane)-first_q):errors.append({'kind':'model_role_order','actual':names})
  if len(lane)>args.max_attempts+1:errors.append({'kind':'unbounded_lane_calls','actual':len(lane)})
  valid=[e for e in lane[:first_q] if isinstance(e.get('response'),str) and e['response'].strip() in OPTION_MAP and e.get('done') is True and e.get('done_reason')!='length']
  if valid:
   last_valid=valid[-1]
   if OPTION_MAP[last_valid['response'].strip()]['input_kind']!='request' and first_q!=len(lane):errors.append({'kind':'non_request_called_extractor'})
  for i,e in enumerate(lane):
   if e['think'] is not False:errors.append({'kind':'unexpected_thinking'})
   if i<first_q and e['format'] is not None:errors.append({'kind':'decision_wrong_wire_format'})
   if i<first_q and e.get('logprobs_requested',True) is not True:errors.append({'kind':'decision_missing_logprob_request'})
   if i>=first_q and not isinstance(e['format'],dict):errors.append({'kind':'extractor_missing_schema'})
 if len(events)>(2 if args.cascade_enabled else 1)*(args.max_attempts+1):errors.append({'kind':'unbounded_calls','actual':len(events)})
 if last_valid is None or last_valid['response'].strip()!=d.get('option'):errors.append({'kind':'final_decision_wire_projection'})
 else:
  if details.get('model')!=last_valid['model']:errors.append({'kind':'confidence_model'})
  chosen=[t for t in last_valid.get('logprobs') or [] if isinstance(t,dict) and t.get('token')==d['option'] and t.get('bytes')==[ord(d['option'])]]
  valid_probability=isinstance(last_valid.get('logprobs'),list) and len(last_valid['logprobs'])==1 and len(chosen)==1 and type(chosen[0].get('logprob')) in (int,float) and math.isfinite(chosen[0]['logprob']) and chosen[0]['logprob']<=0
  if valid_probability:
   lp=chosen[0]['logprob'];expected=math.exp(lp)
   if type(score) not in (int,float) or abs(score-expected)>1e-8 or details.get('selected_logprob')!=lp:errors.append({'kind':'confidence_probability'})
   if details.get('method')!='selected_option_token_probability':errors.append({'kind':'confidence_method'})
  elif score!=0 or details.get('method')!='gate_default':errors.append({'kind':'missing_confidence_not_conservative'})
 if type(score) in (int,float) and score<args.confidence_threshold and 'decision_confidence_low' not in c.get('needs_review',[]):errors.append({'kind':'low_confidence_review_missing'})
 if used:
  initial=audit.get('initial_decision');initial_score=audit.get('initial_confidence')
  if initial is not None:
   if OPTION_MAP.get(initial.get('option'))!={k:initial.get(k) for k in ('input_kind','mode','routing')}:errors.append({'kind':'initial_decision_mapping'})
  if type(initial_score) not in (int,float) or not math.isfinite(initial_score) or not 0<=initial_score<=1:errors.append({'kind':'initial_confidence_range'})
 elif args.cascade_enabled and type(score) in (int,float) and score<args.confidence_threshold:errors.append({'kind':'low_confidence_not_escalated'})
 return errors

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cases',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--suite',choices=['semantic','decision'],default='semantic');ap.add_argument('--decision-model',default='tev1:4b');ap.add_argument('--extraction-model',default='qwen3.5:4b');ap.add_argument('--repeats',type=int,default=1);ap.add_argument('--max-attempts',type=int,default=2)
 ap.add_argument('--fallback-model',default='qwen3:8b');ap.add_argument('--confidence-threshold',type=float,default=0.8);ap.add_argument('--cascade',dest='cascade_enabled',action=argparse.BooleanOptionalAction,default=True)
 args=ap.parse_args()
 if args.output.exists():ap.error('preserve previous outputs; choose another output path')
 args.output.parent.mkdir(parents=True,exist_ok=True)
 cases=json.loads(args.cases.read_text());report={'started_at':datetime.now(timezone.utc).isoformat(),'suite':args.suite,'decision_model':args.decision_model,'extraction_model':args.extraction_model,'think':False,'cascade_enabled':args.cascade_enabled,'confidence_threshold':args.confidence_threshold,'fallback_model':args.fallback_model,'evaluator_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'case_hash':hashlib.sha256(args.cases.read_bytes()).hexdigest(),'source_hashes':fingerprint(),'planned':len(cases)*args.repeats,'cases':[]}
 original=runtime.read_model_response
 for repeat in range(args.repeats):
  for case in cases:
   if fingerprint()!=report['source_hashes']:raise RuntimeError('Production changed during frozen acceptance')
   events=[]
   def measured(req,timeout):
    payload=json.loads(req.data);e={'model':payload.get('model'),'think':payload.get('think'),'options':payload.get('options'),'format':payload.get('format'),'logprobs_requested':payload.get('logprobs'),'top_logprobs_requested':payload.get('top_logprobs'),'timeout':timeout,'request':payload.get('messages'),'payload':payload};events.append(e)
    t=time.perf_counter()
    try:
     raw=original(req,timeout);e.update({k:raw.get(k) for k in ('done','done_reason','prompt_eval_count','eval_count','total_duration','load_duration','prompt_eval_duration','eval_duration','logprobs')});e['response']=raw.get('message',{}).get('content');return raw
    except Exception as exc:e['transport_error']=str(exc);raise
    finally:e['elapsed_seconds']=round(time.perf_counter()-t,3)
   started=time.perf_counter()
   try:
    with patch.object(runtime,'read_model_response',side_effect=measured):
     output=execute_task(case['source'],model=args.extraction_model,decision_model=args.decision_model,think=False,max_attempts=args.max_attempts,timeout_seconds=120,cascade_enabled=args.cascade_enabled,confidence_threshold=args.confidence_threshold,fallback_model=args.fallback_model)
    errors=semantic_check(case,output) if args.suite=='semantic' else []
    errors+=protocol_check(case,output,events,args)
    item={'id':case['id'],'repeat':repeat,'source':case['source'],'output':output,'errors':errors}
   except Exception as exc:
    item={'id':case['id'],'repeat':repeat,'source':case['source'],'errors':[{'kind':'runtime','message':f'{type(exc).__name__}: {exc}'}]}
   item.update(passed=not item['errors'],elapsed_seconds=round(time.perf_counter()-started,3),model_calls=len(events),events=events)
   report['cases'].append(item);report.update(passed=sum(x['passed'] for x in report['cases']),completed=len(report['cases']))
   report['status']='complete' if report['completed']==report['planned'] else 'partial'
   args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
   print(case['id'],repeat+1,'PASS' if item['passed'] else 'FAIL',sorted({e['kind'] for e in item['errors']}),item['elapsed_seconds'],flush=True)
 print('TOTAL',report['passed'],'/',report['completed'],flush=True)
 raise SystemExit(0 if report['passed']==report['planned'] else 2)
if __name__=='__main__':main()
