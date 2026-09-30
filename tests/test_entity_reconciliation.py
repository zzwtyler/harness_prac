"""Model semantic judgments must not be overwritten by lexical guesses.

HTTP fixtures isolate the semantic boundary; public live-model runs judge whether
those judgments are correct. These tests catch destruction or invention by code.
"""
import unittest
from unittest.mock import patch
from harness.main import execute_task
from test_intent_layers import route, details, protocol_response, protocol_sequence


class SemanticBoundaryTests(unittest.TestCase):
    def extract(self, intent, subtype, source, selected):
        replies = (protocol_sequence(route((intent, [0])), details((subtype, [(k, 0) for k in selected])))
                   if selected else protocol_sequence(route(kind='background')))
        with patch('core.runtime.open_model_request', side_effect=lambda req, timeout: protocol_response(req, next(replies))):
            return execute_task(source, max_attempts=1)

    def test_valid_source_labels_are_preserved_without_lexical_whitelist(self):
        examples = [
            ('group_order', 'new_order', '5号要二十杯', {'date', 'quantity', 'request'}),
            ('order_support', 'modify', '订单 HX-726 改到半小时后', {'order_id', 'time', 'request'}),
            ('group_order', 'new_order', '请团订且这次没有预算限制', {'budget', 'request'}),
            ('store_info', 'location', '北京的店在哪里', {'location', 'request'}),
            ('group_order', 'new_order', '请订饮品明天六点半自提', {'date', 'time', 'pickup_or_delivery', 'request'}),
            ('group_order', 'new_order', '八杯分开装', {'quantity', 'constraint', 'request'}),
            ('group_order', 'new_order', '八杯别放在一个袋子里', {'quantity', 'constraint', 'request'}),
            ('group_order', 'new_order', '请订十杯总价低于$60', {'quantity', 'budget', 'request'}),
            ('membership_help', 'points', '规则说满百送十积分但我只收到五个积分', {'policy', 'issue', 'request'}),
        ]
        for intent, subtype, source, selected in examples:
            with self.subTest(source=source):
                output = self.extract(intent, subtype, source, selected)
                self.assertEqual({k['category'] for k in output['intent']['keywords']}, selected)
                for keyword in output['intent']['keywords']:
                    self.assertEqual(source[keyword['start']:keyword['end']], source)
                self.assertEqual(output['verification']['semantic_verification'], 'not_performed')

    def test_surface_matches_do_not_invent_semantic_fields(self):
        examples = [
            ('campaign_brief', 'planning', '请策划每杯立减5元活动', {'offer', 'request'}),
            ('membership_help', 'benefits', '会员3级可以享受哪些权益', {'request'}),
            ('group_order', 'new_order', '请团订甜一些的饮品', {'preference', 'request'}),
            ('membership_help', 'benefits', '请解释规则：积分未到账时联系客服', {'policy', 'request'}),
            ('order_support', 'modify', '这个订单3杯都要少糖', {'quantity', 'preference', 'request'}),
            ('membership_help', 'account', '账号2天后注销', {'request'}),
            ('membership_help', 'account', '我的账户没有故障', set()),
            ('other_request', 'unspecified', '我是平面设计师', set()),
            ('group_order', 'new_order', '补充偏好：甜一些', set()),
            ('group_order', 'new_order', '这次没有预算限制', set()),
        ]
        for intent, subtype, source, selected in examples:
            with self.subTest(source=source):
                output = self.extract(intent, subtype, source, selected)
                self.assertEqual({k['category'] for k in output['intent']['keywords']}, selected)
