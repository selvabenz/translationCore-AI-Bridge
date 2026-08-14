from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .models import VerseAlignment


@dataclass
class EditSession:
    current: VerseAlignment
    undo_stack: list[VerseAlignment] = field(default_factory=list)
    redo_stack: list[VerseAlignment] = field(default_factory=list)
    dirty: bool = False

    def replace(self, value: VerseAlignment) -> None:
        self.undo_stack.append(copy.deepcopy(self.current))
        self.current = copy.deepcopy(value)
        self.redo_stack.clear()
        self.dirty = True

    def undo(self) -> bool:
        if not self.undo_stack: return False
        self.redo_stack.append(copy.deepcopy(self.current))
        self.current = self.undo_stack.pop()
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self.redo_stack: return False
        self.undo_stack.append(copy.deepcopy(self.current))
        self.current = self.redo_stack.pop()
        self.dirty = True
        return True

    def mark_saved(self) -> None:
        self.dirty = False
