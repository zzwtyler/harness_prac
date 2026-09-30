"""Guard independent intent ownership, routing gates and scoped extraction."""
import copy
import json
import unittest
from unittest.mock import patch
from harness.main import execute_task as _execute_task
from test_harness import response


def execute_task(*args, **kwargs):
    """Isolate source/unit validation from the separately tested cascade."""
    kwargs.setdefault('cascade_enabled', False)
    return _execute_task(*args, **kwargs)


def route(*units, kind='request'):
    return {'input_kind': kind, 'intents': [{'intent': name, 'clause_indices': indices} for name, indices in units]}


def details(*units):
    return {'intents': [{'intent_index': i, 'subtype': subtype, 'selections': [
        {'category': category, 'clause_index': index} for category, index in selections]}
        for i, (subtype, selections) in enumerate(units)]}


def protocol_response(req, plan):
    return response(plan)


def protocol_sequence(*answers):
    """Transport old explicit semantic fixtures through the new public wire."""
    routing = answers[0]
    letters = {'store_info': 'A', 'menu_advice': 'B', 'order_support': 'C', 'group_order': 'D',
               'complaint': 'E', 'membership_help': 'F', 'campaign_brief': 'G', 'sales_analysis': 'H',
               'other_request': 'I'}
    if routing['input_kind'] != 'request':
        yield {'social': 'K', 'background': 'L', 'unclear': 'M'}[routing['input_kind']]
        return
    yield 'J' if len(routing['intents']) > 1 else letters[routing['intents'][0]['intent']]
    for details in answers[1:]:
        units = []
        for index, detail in enumerate(details['intents']):
            owned = routing['intents'][index]
            unit = {'intent': owned['intent'], 'subtype': detail['subtype'],
                    'clause_ids': [f'clause_{i}' for i in owned['clause_indices']],
                    'request': [f"clause_{s['clause_index']}" for s in detail['selections'] if s['category'] == 'request'],
                    'selections': [{'category': s['category'], 'clause_id': f"clause_{s['clause_index']}"}
                                   for s in detail['selections'] if s['category'] != 'request']}
            if detail['intent_index'] != index:
                # The new wire has no model-chosen unit index; this is an extra field.
                unit['intent_index'] = detail['intent_index']
            units.append(unit)
        yield {'intents': units}


class IntentLayerTests(unittest.TestCase):
    def run_model(self, source, *answers, **kwargs):
        replies = protocol_sequence(*answers)
        with patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(replies))):
            try:
                return execute_task(source, max_attempts=1, **kwargs)
            except ValueError as exc:
                self.fail(f'分层协议应被接受：{exc}')

    def test_supplement_prefix_does_not_suppress_explicit_new_request(self):
        output = self.run_model('补充说明：请取消订单 E-621',
            route(('order_support', [0])), details(('cancel', [('request', 0), ('order_id', 0)])))
        self.assertEqual(output['intent']['input_kind'], 'request')
        self.assertEqual(output['result']['order_id'], ['补充说明：请取消订单 E-621'])

    def test_supplement_prefix_never_erases_a_model_identified_goal(self):
        for source, intent, subtype in [('补充一下，我要二十杯奶茶', 'group_order', 'new_order'),
                                        ('更正一下，我要退掉订单 HX-726', 'order_support', 'cancel')]:
            output = self.run_model(source, route((intent, [0, 1])), details((subtype, [('request', 1)])))
            self.assertEqual(output['intent']['input_kind'], 'request')
            self.assertEqual(output['intent']['intents'][0]['intent'], intent)

    def test_explicit_fields_reach_information_and_task(self):
        output = self.run_model('订单 Z-507 改为后天11点',
            route(('order_support', [0])), details(('modify', [('time', 0), ('date', 0), ('order_id', 0), ('request', 0)])))
        self.assertEqual({k['category'] for k in output['intent']['keywords']},
                         {'date', 'time', 'order_id', 'request'})
        self.assertEqual(output['result']['requested_change'], ['订单 Z-507 改为后天11点'])
        self.assertEqual(output['intent']['intents'][0]['not_observed'], [])

    def test_campaign_objective_excludes_generic_request(self):
        output = self.run_model('我是运营，请策划活动，目标是提高复购',
            route(('campaign_brief', [0, 1, 2])),
            details(('planning', [('request', 1), ('objective', 2)])))
        self.assertEqual(output['result']['objective'], ['目标是提高复购'])

    def test_empty_request_details_trigger_bounded_retry_without_invented_fields(self):
        replies = protocol_sequence(route(('store_info', [0])), details(('general', [])),
                                    details(('general', [('request', 0)])))
        with patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(replies))):
            output = execute_task('请查门店信息', max_attempts=2)
        self.assertEqual(output['state']['attempts'], 2)
        self.assertEqual({k['category'] for k in output['intent']['keywords']}, {'request'})
        self.assertEqual(output['result']['location'], [])
        self.assertEqual(output['result']['opening_hours'], [])

    def test_exhausted_empty_request_is_reported_as_incomplete(self):
        replies = protocol_sequence(route(('store_info', [0])), details(('general', [])), details(('general', [])))
        with patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(replies))) as network:
            with self.assertRaisesRegex(ValueError, '未提取任何字段'):
                execute_task('请查门店信息', max_attempts=2)
        self.assertEqual(network.call_count, 3)

    def test_non_request_stops_before_detail_extraction(self):
        output = self.run_model('你好，谢谢', route(kind='social'))
        self.assertEqual(output['intent']['intent'], 'no_intent')
        self.assertEqual(output['intent']['input_kind'], 'social')
        self.assertEqual(output['intent']['intents'], [])
        self.assertEqual(output['result']['keywords'], [])

    def test_multi_preserves_business_types_and_disjoint_ownership_in_task(self):
        output = self.run_model('会员M789积分没到，取消订单A123',
            route(('membership_help', [0]), ('order_support', [1])),
            details(('points', [('issue', 0), ('account_id', 0), ('request', 0)]), ('cancel', [('request', 1), ('order_id', 1)])))
        self.assertEqual(output['intent']['intent'], 'multi_intent')
        units = output['intent']['intents']
        self.assertEqual([u['intent'] for u in units], ['membership_help', 'order_support'])
        self.assertEqual(units[0]['keywords'][0]['text'], '会员M789积分没到')
        self.assertTrue(all(k['text'] == '取消订单A123' for k in units[1]['keywords']))
        self.assertEqual(output['result']['intents'], units)
        self.assertEqual(units[1]['not_observed'], [])
        self.assertIn('order_status', units[1]['verification_needed'])

    def test_other_can_coexist_and_same_business_can_have_two_goals(self):
        for second in ('other_request', 'order_support'):
            with self.subTest(second=second):
                output = self.run_model('取消订单A123，另外处理一件事',
                    route(('order_support', [0]), (second, [1])),
                    details(('cancel', [('request', 0)]), ('unspecified', [('request', 1)])))
                self.assertEqual(output['intent']['intent'], 'multi_intent')
                self.assertEqual([u['intent'] for u in output['intent']['intents']], ['order_support', second])

    def test_information_has_levels_and_unobserved_is_not_a_fabricated_fact(self):
        output = self.run_model('帮我取消订单', route(('order_support', [0])),
                                details(('cancel', [('request', 0)])))
        unit = output['intent']['intents'][0]
        self.assertEqual(unit['not_observed'], ['order_id'])
        self.assertEqual(unit['information']['common'][0]['text'], '帮我取消订单')
        self.assertEqual(unit['information']['business'], [])
        self.assertEqual(unit['information']['operation'], [])
        self.assertEqual(output['result']['order_id'], [])

    def test_invalid_scope_category_or_subtype_is_rejected(self):
        routing = route(('membership_help', [0]), ('order_support', [1]))
        valid = details(('points', [('issue', 0), ('request', 0)]), ('cancel', [('request', 1)]))
        variants = []
        for field, value in [('clause_index', 1), ('category', 'offer')]:
            bad = copy.deepcopy(valid)
            bad['intents'][0]['selections'][0][field] = value
            variants.append(bad)
        bad = copy.deepcopy(valid)
        bad['intents'][0]['subtype'] = 'cancel'
        variants.append(bad)
        bad = copy.deepcopy(valid)
        bad['intents'][1]['intent_index'] = 0
        variants.append(bad)
        for bad in variants:
            replies = protocol_sequence(routing, bad)
            with self.subTest(bad=bad), patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(replies))):
                with self.assertRaises((ValueError, TypeError)):
                    execute_task('积分没到，取消订单', max_attempts=1)

    def test_routing_contradictions_and_boolean_indices_are_rejected(self):
        for bad in [route(kind='request'), route(('store_info', [True])),
                    route(('store_info', [8])), route(('store_info', [0]), kind='social')]:
            with self.subTest(bad=bad), patch('core.runtime.open_model_request', return_value=response(bad)):
                with self.assertRaises(ValueError):
                    execute_task('你好', max_attempts=1)

    def test_second_call_only_receives_routed_categories_and_preserves_shared_evidence(self):
        sent = []
        replies = protocol_sequence(route(('order_support', [0, 1]), ('other_request', [1])),
                        details(('cancel', [('order_id', 0), ('request', 0), ('constraint', 1)]), ('unspecified', [('request', 1)])))
        def upstream(req, timeout):
            sent.append(json.loads(req.data))
            return protocol_response(req, next(replies))
        with patch('core.runtime.open_model_request', side_effect=upstream):
            try:
                output = execute_task('取消订单A123，今天也帮我修打印机', max_attempts=1)
            except ValueError as exc:
                self.fail(f'分层协议应被接受：{exc}')
        self.assertEqual(len(sent), 2)
        detail_input = json.loads(sent[1]['messages'][1]['content'])
        self.assertEqual(detail_input.get('source_text'), '取消订单A123，今天也帮我修打印机')
        self.assertNotIn('offer', detail_input['businesses']['order_support']['allowed_categories'])
        self.assertEqual(output['intent']['intents'][0]['evidence'][1]['text'], '今天也帮我修打印机')
        self.assertEqual(output['intent']['intents'][1]['evidence'][0]['text'], '今天也帮我修打印机')

    def test_detail_schema_covers_each_owned_clause_and_excludes_other_businesses(self):
        sent = []
        replies = protocol_sequence(route(('order_support', [0])), details(('cancel', [('request', 0)])))
        def upstream(req, timeout):
            sent.append(json.loads(req.data))
            return protocol_response(req, next(replies))
        with patch('core.runtime.open_model_request', side_effect=upstream):
            execute_task('取消订单', max_attempts=1)
        detail_input = json.loads(sent[1]['messages'][1]['content'])
        self.assertEqual(detail_input['decision']['routing'], 'order_support')
        self.assertEqual(detail_input['clauses'][0].get('id'), 'clause_0')
        slots = sent[1]['format']['properties']
        self.assertIn('intents', slots, '第二阶段必须使用按当前业务收窄的字段清单')
        item = slots['intents']['items']
        selection = item['properties']['selections']['items']['properties']
        self.assertIn('order_id', selection['category']['enum'])
        self.assertEqual(selection['clause_id']['enum'], ['clause_0'])
        self.assertNotIn('offer', selection['category']['enum'])
        self.assertEqual(item['properties']['intent']['enum'], ['order_support'])
        self.assertEqual(item['properties']['subtype']['enum'], ['query', 'modify', 'cancel', 'unspecified'])

    def test_group_dietary_information_and_order_quantity_keep_dedicated_categories(self):
        output = self.run_model('团订20杯，其中5杯不要奶，另一个订单改12杯',
            route(('group_order', [0, 1]), ('order_support', [2])),
            details(('new_order', [('quantity', 0), ('request', 0), ('dietary_constraint', 1)]),
                    ('modify', [('quantity', 2), ('request', 2)])))
        group, order = output['intent']['intents']
        self.assertEqual(group['information']['business'][1]['category'], 'dietary_constraint')
        self.assertEqual(order['information']['operation'][0]['text'], '另一个订单改12杯')
        self.assertEqual(order['not_observed'], ['order_id'])

    def test_bool_detail_index_is_not_accepted_as_integer(self):
        replies = protocol_sequence(route(('order_support', [1])), details(('cancel', [('request', True)])))
        with patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(replies))):
            with self.assertRaises(ValueError):
                execute_task('你好，取消订单', max_attempts=1)

    def test_verifier_rejects_forged_intent_ownership(self):
        from core import schema, models, verification
        output = self.run_model('积分没到，取消订单A123',
            route(('membership_help', [0]), ('order_support', [1])),
            details(('points', [('issue', 0), ('request', 0)]), ('cancel', [('order_id', 1), ('request', 1)])))
        data = output['intent']
        data['intents'][0]['keywords'].append(data['intents'][1]['keywords'][0])
        with self.assertRaises(ValueError):
            verification.verify_extraction(schema.model_from_dict(models.ExtractedInput, data))
