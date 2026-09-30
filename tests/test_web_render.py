"""Nested intent data must remain readable in the existing schema renderer."""
import shutil
import subprocess
import unittest
from pathlib import Path


class WebRenderTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is needed for role readiness check')
    def test_fallback_role_is_required_only_when_cascade_is_enabled(self):
        script = r'''
const fs = require('node:fs'); const vm = require('node:vm'); const assert = require('node:assert/strict');
const source = fs.readFileSync('web/static/app.js', 'utf8');
const start = source.indexOf('function areModelRolesReady(');
const end = source.indexOf('async function checkStatus(', start);
assert.ok(start >= 0);
const context = vm.createContext({}); vm.runInContext(source.slice(start, end), context);
const installed = new Set(['tev1:4b', 'qwen3.5:4b']);
assert.equal(context.areModelRolesReady(installed, 'qwen3.5:4b', 'tev1:4b', 'qwen3:8b', true), false);
assert.equal(context.areModelRolesReady(installed, 'qwen3.5:4b', 'tev1:4b', 'qwen3:8b', false), true);
installed.add('chosen:8b');
assert.equal(context.areModelRolesReady(installed, 'qwen3.5:4b', 'tev1:4b', 'chosen:8b', true), true);
'''
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for role selection check')
    def test_missing_role_model_is_preserved_until_explicit_selection(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/static/app.js', 'utf8');
const start = source.indexOf('function populateRoleModelSelect(');
const end = source.indexOf('async function checkStatus(', start);
assert.ok(start >= 0, 'Missing role models need an explicit selection policy');
const context = vm.createContext({document: {createElement: () => ({})}});
vm.runInContext(source.slice(start, end), context);
const select = {value: 'tev1:4b', options: [],
  replaceChildren() { this.options = []; this.value = ''; },
  append(option) { this.options.push(option); if (!this.value) this.value = option.value; }};
assert.equal(context.populateRoleModelSelect(select, [{name:'qwen3.5:4b'}], 'tev1:4b'), false);
assert.equal(select.value, 'tev1:4b', 'Do not silently use the first installed model for this role');
assert.ok(select.options.find(option => option.value === 'tev1:4b').disabled);
assert.equal(context.populateRoleModelSelect(select, [{name:'qwen3.5:4b'}], 'qwen3.5:4b'), true);
assert.equal(select.value, 'qwen3.5:4b', 'An explicitly chosen installed replacement is accepted');
'''
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the browser formatter check')
    def test_nested_intent_values_are_not_coerced_to_object_object(self):
        script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('web/static/app.js', 'utf8');
const start = source.indexOf('function humanValue(');
const end = source.indexOf('function makeSimpleList(', start);
const context = vm.createContext({});
vm.runInContext(source.slice(start, end), context);
const text = context.humanValue({business: [{text: '订单A123', category: 'order_id'}]});
assert.ok(text.includes('订单A123'));
assert.ok(!text.includes('[object Object]'));
assert.equal(context.humanValue(false), '否');
'''
        result = subprocess.run(['node', '-e', script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
