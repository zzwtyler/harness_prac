"""Catalog for stage 02 task models and display order."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from core import task_loader as _task_loader
load_task = _task_loader.load_task
from core import paths as _paths
TASK_CLASSES = _paths.TASK_CLASSES



@dataclass(frozen=True)
class TaskDefinition:
    id: str
    order: int
    title: str
    model_type: type
    module: ModuleType

    def as_stage(self):
        from core import stage as _stage
        HarnessStage = _stage.HarnessStage
        return HarnessStage(id=self.id, order=self.order,
                            title=f'{self.order:02d} · {self.title}',
                            description='只整理当前用户输入，缺失项留空。',
                            model_type=self.model_type, system_prompt=self.module.SYSTEM_PROMPT,
                            runner=self.module.analyze_task)


class TaskRegistry:
    def __init__(self, directory: Path = TASK_CLASSES):
        self.directory = directory.resolve()

    def all(self):
        entries = json.loads((self.directory / 'index.json').read_text(encoding='utf-8'))
        result, ids, orders = [], set(), set()
        for item in entries:
            name, order = item['id'], item['order']
            if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', name):
                raise ValueError('intent名称无效')
            if name in ids or type(order) is not int or order < 2 or order in orders:
                raise ValueError('intent名称或显示序号重复/无效')
            path = self.directory / f'{name}.py'
            if path.is_symlink():
                raise ValueError('intent模块必须位于本地intent目录内')
            module = load_task(path)
            model = getattr(module, item['model'])
            result.append(TaskDefinition(name, order, item['title'], model, module))
            ids.add(name)
            orders.add(order)
        return sorted(result, key=lambda d: d.order)

    def get(self, intent):
        for definition in self.all():
            if definition.id == intent:
                return definition
        raise ValueError(f'未注册的intent：{intent}')
