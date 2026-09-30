"""Scorer checks are independent of production classifiers and formatters."""
import copy
import unittest
from evaluation.strict_intent import check


class StrictScorerTests(unittest.TestCase):
    def fixture(self):
        span={'text':'取消订单','start':0,'end':4}
        keyword={'category':'request',**span}
        unit={'intent':'order_support','subtype':'cancel','evidence':[span],'keywords':[keyword],
              'information':{'common':[keyword],'business':[],'operation':[]}}
        case={'source':'取消订单','units':[{'intent':'order_support','subtypes':['cancel'],'required':{'0':['request']}}],
              'task_required':{'order_id':[],'requested_change':[0]}}
        output={'intent':{'source_text':'取消订单','input_kind':'request','intent':'order_support','intents':[unit],'keywords':[keyword]},
                'result':{'source_text':'取消订单','intents':[unit],'keywords':[keyword],'order_id':[],'requested_change':['取消订单']},
                'verification':{'schema_valid':True,'source_grounded':True,'mapping_valid':True}}
        return case,output

    def test_exact_correct_case_passes(self):
        case,output=self.fixture()
        self.assertEqual(check(case,output),[])

    def test_extra_order_id_is_rejected_even_when_request_is_present(self):
        case,output=self.fixture()
        extra={'category':'order_id','text':'取消订单','start':0,'end':4}
        output['intent']['intents'][0]['keywords'].append(extra)
        output['result']['order_id']=['取消订单']
        self.assertIn('extra_label',{e['kind'] for e in check(case,output)})
        self.assertIn('task_extra',{e['kind'] for e in check(case,output)})

    def test_missing_field_is_rejected(self):
        case,output=self.fixture()
        output['intent']['intents'][0]['keywords']=[]
        self.assertIn('missing_label',{e['kind'] for e in check(case,output)})

    def test_wrong_final_mapping_is_rejected_with_correct_keywords(self):
        case,output=self.fixture()
        output['result']['requested_change']=[]
        self.assertIn('task_missing',{e['kind'] for e in check(case,output)})

    def test_scope_or_projection_cannot_be_hidden_by_verification_booleans(self):
        case,output=self.fixture()
        output=copy.deepcopy(output)
        output['intent']['intents'][0]['evidence']=[{'text':'订单','start':2,'end':4}]
        self.assertIn('evidence_source',{e['kind'] for e in check(case,output)})
