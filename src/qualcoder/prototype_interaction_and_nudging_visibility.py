# -*- coding: utf-8 -*-
"""
PROTOTYPE & VERIFICATION: In-Text Interaction, Unmarking, and Arrow-Key Boundary Nudging Exclusion (Issue 05)

Verifies:
1. unmark() ignores hidden codes:
   - When 1 visible + 1 hidden code overlap, unmarking operates directly on the visible code without DialogSelectItems.
   - Hidden codes are never deleted.
   - When all codes at cursor are hidden, unmark does nothing.
2. display_handles_for_code() ignores hidden codes:
   - Directly attaches handles to the visible code without DialogSelectItems when overlapping codes are hidden.
   - When all codes at cursor are hidden, no handles attach.
3. eventFilter() arrow-key boundary nudging (Alt/Shift + Left/Right):
   - codes_here filters out hidden codes.
   - When 1 visible code is present, DialogSelectItems is NEVER triggered on Alt/Shift+arrows.
   - Consecutive nudges maintain uninterrupted focus on that code.
   - If active handles exist, their positions synchronize with the nudged boundaries.
4. text_edit_menu(), coded_text_memo(), and change_code_to_another_code() filter out hidden codes:
   - Context menu and actions ignore hidden codes at cursor position.
"""

import os
import sys
import datetime
from copy import deepcopy
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QPoint, QEvent
from PyQt6.QtGui import QColor, QBrush, QTextCharFormat, QTextCursor, QKeyEvent

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from qualcoder.color_selector import TextColor
    from qualcoder.helpers import CodeResizeHandle
except ImportError:
    from color_selector import TextColor
    from helpers import CodeResizeHandle


class MockApp:
    def __init__(self):
        self.hidden_cids = set()
        self.pre_solo_hidden_cids = None
        self.settings = {
            'font': 'Arial',
            'fontsize': 10,
            'stylesheet': 'light',
            'showids': True
        }
        self.delete_backup = False


class MockDialog(QtWidgets.QMainWindow):
    """
    Mock DialogCodeText encapsulating the exact logic for:
    - unmark()
    - display_handles_for_code()
    - eventFilter() arrow key boundary nudging
    - text_edit_menu() / coded_text_memo() / change_code_to_another_code()
    """

    def __init__(self):
        super().__init__()
        self.app = MockApp()
        self.file_ = {
            'id': 1,
            'name': 'sample.txt',
            'start': 0,
            'end': 500,
            'memo': ''
        }

        # Sample text: 100 characters
        self.full_text = "The quick brown fox jumps over the lazy dog repeatedly in an emotional outburst of pure energy."
        
        self.plainTextEdit = QtWidgets.QPlainTextEdit(self)
        self.plainTextEdit.setPlainText(self.full_text)
        self.setCentralWidget(self.plainTextEdit)

        # Structure of codes
        self.codes = [
            {'cid': 1, 'name': 'Fox', 'color': '#ff9999'},
            {'cid': 2, 'name': 'Dog', 'color': '#99ff99'},
            {'cid': 3, 'name': 'Emotions', 'color': '#9999ff'},
        ]

        # Initial coded segments
        # Segment 1: Fox (pos0=4, pos1=25) -> "quick brown fox jumps"
        # Segment 2: Dog (pos0=16, pos1=45) -> "fox jumps over the lazy dog" [Overlaps Fox at 16..25]
        # Segment 3: Emotions (pos0=60, pos1=85)
        self.code_text = [
            {
                'ctid': 101, 'cid': 1, 'fid': 1, 'name': 'Fox', 'color': '#ff9999',
                'pos0': 4, 'pos1': 25, 'seltext': self.full_text[4:25], 'owner': 'default',
                'date': '2026-09-30', 'memo': 'Fox memo', 'important': None
            },
            {
                'ctid': 102, 'cid': 2, 'fid': 1, 'name': 'Dog', 'color': '#99ff99',
                'pos0': 16, 'pos1': 45, 'seltext': self.full_text[16:45], 'owner': 'default',
                'date': '2026-09-30', 'memo': 'Dog memo', 'important': None
            },
            {
                'ctid': 103, 'cid': 3, 'fid': 1, 'name': 'Emotions', 'color': '#9999ff',
                'pos0': 60, 'pos1': 85, 'seltext': self.full_text[60:85], 'owner': 'default',
                'date': '2026-09-30', 'memo': 'Emotions memo', 'important': 1
            }
        ]

        self.edit_mode = False
        self.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)
        self.active_handles = []
        self.undo_deleted_codes = []

        # Tracking for test assertions
        self.dialog_select_items_invoked = False
        self.dialog_select_items_candidates = []
        self.last_resized_ctid = None
        self.last_resized_time = datetime.datetime.now() - datetime.timedelta(seconds=10)

        # Alias for self.ui.plainTextEdit compatibility
        self.ui = type('UI', (), {'plainTextEdit': self.plainTextEdit})()

    # --- Tracking & Helpers ---
    def mock_select_items(self, candidates, title, mode="single"):
        self.dialog_select_items_invoked = True
        self.dialog_select_items_candidates = list(candidates)
        # Default mock response: return first candidate
        if mode == "multi":
            return [candidates[0]]
        return candidates[0]

    def clear_edit_variables(self):
        pass

    def hide_resize_handles(self):
        for h in getattr(self, 'active_handles', []):
            h.hide()
            h.deleteLater()
        self.active_handles = []

    def update_handle_positions(self):
        """ Update active resize handle coordinates after keyboard boundary nudging. """
        if not getattr(self, 'active_handles', []):
            return
        code_to_handle = self.active_handles[0].code_item
        live_code = next((c for c in self.code_text if c.get('ctid') == code_to_handle.get('ctid')), code_to_handle)
        cursor_start = self.plainTextEdit.textCursor()
        cursor_start.setPosition(max(0, live_code['pos0'] - self.file_['start']))
        rect_start = self.plainTextEdit.cursorRect(cursor_start)
        cursor_end = self.plainTextEdit.textCursor()
        cursor_end.setPosition(min(len(self.plainTextEdit.toPlainText()), live_code['pos1'] - self.file_['start']))
        rect_end = self.plainTextEdit.cursorRect(cursor_end)
        for h in self.active_handles:
            h.code_item = live_code
            if h.is_start:
                h.move(rect_start.x() - h.width(), rect_start.y())
            else:
                h.move(rect_end.x() - 6, rect_end.y() + 2)

    # --- Issue 05: unmark() with hidden_cids filter ---
    def unmark(self, location):
        """ Remove code marking excluding hidden codes. """
        if self.file_ is None:
            return
        self.clear_edit_variables()
        hidden_cids = getattr(self.app, 'hidden_cids', set())
        unmarked_list = []
        for item in self.code_text:
            if item.get('cid') in hidden_cids:
                continue
            if item['pos0'] <= location + self.file_['start'] <= item['pos1']:
                unmarked_list.append(item)
        if not unmarked_list:
            return
        to_unmark = []
        if len(unmarked_list) == 1:
            to_unmark = [unmarked_list[0]]
        elif len(unmarked_list) > 1:
            selected = self.mock_select_items(unmarked_list, "Select code to unmark", "multi")
            if not selected:
                return
            to_unmark = selected if isinstance(selected, list) else [selected]

        if not to_unmark:
            return
        self.undo_deleted_codes = deepcopy(to_unmark)
        # Delete from code_text list
        delete_ctids = {item['ctid'] for item in to_unmark}
        self.code_text = [c for c in self.code_text if c['ctid'] not in delete_ctids]

    # --- Issue 05: display_handles_for_code() with hidden_cids filter ---
    def display_handles_for_code(self, position):
        """ Display interactive drag handles excluding hidden codes. """
        if self.file_ is None:
            return
        hidden_cids = getattr(self.app, 'hidden_cids', set())
        coded_text_list = []
        for item in self.code_text:
            if item.get('cid') in hidden_cids:
                continue
            if item['pos0'] <= position + self.file_['start'] <= item['pos1']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        code_to_handle = coded_text_list[-1]
        if len(coded_text_list) > 1:
            selected = self.mock_select_items(coded_text_list, "Select code to resize", "single")
            if not selected:
                return
            code_to_handle = selected

        self.hide_resize_handles()

        # Create start handle
        cursor_start = self.plainTextEdit.textCursor()
        cursor_start.setPosition(max(0, code_to_handle['pos0'] - self.file_['start']))
        rect_start = self.plainTextEdit.cursorRect(cursor_start)
        h_start = CodeResizeHandle(self.plainTextEdit, True, code_to_handle, self)
        h_start.move(rect_start.x() - h_start.width(), rect_start.y())
        self.active_handles.append(h_start)

        # Create end handle
        cursor_end = self.plainTextEdit.textCursor()
        cursor_end.setPosition(min(len(self.plainTextEdit.toPlainText()), code_to_handle['pos1'] - self.file_['start']))
        rect_end = self.plainTextEdit.cursorRect(cursor_end)
        h_end = CodeResizeHandle(self.plainTextEdit, False, code_to_handle, self)
        h_end.move(rect_end.x() - 6, rect_end.y() + 2)
        self.active_handles.append(h_end)

    # --- Issue 05: Boundary Nudging Methods ---
    def extend_left(self, code_):
        if not code_ or code_['pos0'] < 1:
            return
        code_['pos0'] -= 1
        code_['seltext'] = self.full_text[code_['pos0']:code_['pos1']]
        self.update_handle_positions()

    def extend_right(self, code_):
        if not code_ or code_['pos1'] + 1 > len(self.full_text):
            return
        code_['pos1'] += 1
        code_['seltext'] = self.full_text[code_['pos0']:code_['pos1']]
        self.update_handle_positions()

    def shrink_to_left(self, code_):
        if not code_ or code_['pos1'] <= code_['pos0'] + 1:
            return
        code_['pos1'] -= 1
        code_['seltext'] = self.full_text[code_['pos0']:code_['pos1']]
        self.update_handle_positions()

    def shrink_to_right(self, code_):
        if not code_ or code_['pos0'] >= code_['pos1'] - 1:
            return
        code_['pos0'] += 1
        code_['seltext'] = self.full_text[code_['pos0']:code_['pos1']]
        self.update_handle_positions()

    # --- Issue 05: eventFilter() with hidden_cids filter and focus preservation ---
    def eventFilter(self, object_, event):
        if type(event) == QtGui.QKeyEvent and object_ is self.plainTextEdit:
            key = event.key()
            mod = event.modifiers()
            now = datetime.datetime.now()
            diff = now - self.code_resize_timer

            # Debounce rapid key triggers (< 100ms)
            if diff.total_seconds() < 0.1:
                if mod in (QtCore.Qt.KeyboardModifier.AltModifier, QtCore.Qt.KeyboardModifier.ShiftModifier) \
                        and key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
                    return True
                return False

            if self.edit_mode:
                return False

            cursor_pos = self.plainTextEdit.textCursor().position()
            hidden_cids = getattr(self.app, 'hidden_cids', set())

            codes_here = []
            for item in self.code_text:
                if item.get('cid') in hidden_cids:
                    continue
                if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1']:
                    codes_here.append(item)

            if len(codes_here) == 0:
                return False

            code_ = None
            # Check if active handles are open and match one of the visible codes at cursor
            if getattr(self, 'active_handles', []):
                h_ctid = self.active_handles[0].code_item.get('ctid')
                for c in codes_here:
                    if c.get('ctid') == h_ctid:
                        code_ = c
                        break

            # Check consecutive nudge session focus: if user nudged within last 2.0s
            time_since_last_nudge = (now - self.last_resized_time).total_seconds()
            if code_ is None and self.last_resized_ctid is not None and time_since_last_nudge < 2.0:
                for c in codes_here:
                    if c.get('ctid') == self.last_resized_ctid:
                        code_ = c
                        break

            # If still not uniquely identified:
            if code_ is None:
                if len(codes_here) > 1 and mod in (
                        QtCore.Qt.KeyboardModifier.AltModifier, QtCore.Qt.KeyboardModifier.ShiftModifier) \
                        and key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
                    selected = self.mock_select_items(codes_here, "Select a code", "single")
                    if not selected:
                        return True
                    code_ = selected
                elif len(codes_here) == 1:
                    code_ = codes_here[0]

            if not code_:
                return False

            self.code_resize_timer = now
            self.last_resized_time = now
            self.last_resized_ctid = code_.get('ctid')

            if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                self.shrink_to_left(code_)
                return True
            if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                self.shrink_to_right(code_)
                return True
            if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.extend_left(code_)
                return True
            if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.extend_right(code_)
                return True

        return False

    # --- Issue 05: Context Menu / Memo / Change Code Filters ---
    def get_context_menu_actions_at_pos(self, cursor_pos):
        hidden_cids = getattr(self.app, 'hidden_cids', set())
        available_actions = []
        for item in self.code_text:
            if item.get('cid') in hidden_cids:
                continue
            if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1']:
                available_actions.append(item)
        return available_actions

    def coded_text_memo(self, position):
        hidden_cids = getattr(self.app, 'hidden_cids', set())
        coded_text_list = []
        for item in self.code_text:
            if item.get('cid') in hidden_cids:
                continue
            if item['pos0'] <= position + self.file_['start'] <= item['pos1']:
                coded_text_list.append(item)
        if not coded_text_list:
            return None
        if len(coded_text_list) == 1:
            return coded_text_list[0]
        return self.mock_select_items(coded_text_list, "Select code to memo", "single")


def run_tests():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    diag = MockDialog()
    diag.show()
    app.processEvents()

    print("=== Running Comprehensive Issue 05 Verification Tests ===")

    # Setup: Pos 20 is within Fox (4..25) AND Dog (16..45).
    # -------------------------------------------------------------
    # TEST 1: All codes visible -> unmark() at Pos 20 triggers DialogSelectItems
    # -------------------------------------------------------------
    diag.dialog_select_items_invoked = False
    diag.unmark(20)
    assert diag.dialog_select_items_invoked, "Expected DialogSelectItems when both Fox and Dog are visible"
    assert len(diag.dialog_select_items_candidates) == 2, "Both Fox and Dog should be candidates"
    print("PASS 1: All codes visible -> unmark() prompts DialogSelectItems with all overlapping codes.")

    # Reset code_text
    diag.code_text = [
        {'ctid': 101, 'cid': 1, 'name': 'Fox', 'pos0': 4, 'pos1': 25, 'seltext': diag.full_text[4:25]},
        {'ctid': 102, 'cid': 2, 'name': 'Dog', 'pos0': 16, 'pos1': 45, 'seltext': diag.full_text[16:45]},
        {'ctid': 103, 'cid': 3, 'name': 'Emotions', 'pos0': 60, 'pos1': 85, 'seltext': diag.full_text[60:85]}
    ]

    # -------------------------------------------------------------
    # TEST 2: Dog hidden -> unmark() at Pos 20 immediately unmarks Fox without prompt
    # -------------------------------------------------------------
    diag.app.hidden_cids.add(2)  # Hide Dog
    diag.dialog_select_items_invoked = False
    diag.unmark(20)
    assert not diag.dialog_select_items_invoked, "DialogSelectItems MUST NOT be invoked when Dog is hidden!"
    assert len(diag.undo_deleted_codes) == 1 and diag.undo_deleted_codes[0]['cid'] == 1, "Fox should be unmarked"
    # Verify Dog is still in code_text!
    remaining_cids = [c['cid'] for c in diag.code_text]
    assert 2 in remaining_cids, "Dog MUST remain in code_text after Fox is unmarked"
    assert 1 not in remaining_cids, "Fox MUST be removed from code_text"
    print("PASS 2: Dog hidden -> unmark() deletes Fox immediately without DialogSelectItems; Dog is preserved.")

    # Reset code_text and unhide
    diag.app.hidden_cids.clear()
    diag.code_text = [
        {'ctid': 101, 'cid': 1, 'name': 'Fox', 'pos0': 4, 'pos1': 25, 'seltext': diag.full_text[4:25]},
        {'ctid': 102, 'cid': 2, 'name': 'Dog', 'pos0': 16, 'pos1': 45, 'seltext': diag.full_text[16:45]},
        {'ctid': 103, 'cid': 3, 'name': 'Emotions', 'pos0': 60, 'pos1': 85, 'seltext': diag.full_text[60:85]}
    ]

    # -------------------------------------------------------------
    # TEST 3: All codes at location hidden -> unmark() does nothing
    # -------------------------------------------------------------
    diag.app.hidden_cids = {1, 2}  # Hide both Fox and Dog
    diag.dialog_select_items_invoked = False
    diag.unmark(20)
    assert not diag.dialog_select_items_invoked
    assert len(diag.code_text) == 3, "No codes should be deleted when all at position are hidden"
    print("PASS 3: All codes hidden at location -> unmark() safely does nothing.")

    # -------------------------------------------------------------
    # TEST 4: display_handles_for_code() with hidden codes
    # -------------------------------------------------------------
    diag.app.hidden_cids = {2}  # Hide Dog, Fox visible
    diag.dialog_select_items_invoked = False
    diag.display_handles_for_code(20)
    assert not diag.dialog_select_items_invoked, "display_handles_for_code MUST NOT prompt when only Fox is visible!"
    assert len(diag.active_handles) == 2, "Start and End handles must be created"
    assert diag.active_handles[0].code_item['cid'] == 1, "Handles must be bound to Fox"
    print("PASS 4: Dog hidden -> display_handles_for_code() attaches directly to Fox without DialogSelectItems.")

    diag.hide_resize_handles()
    diag.app.hidden_cids = {1, 2}  # Hide both
    diag.display_handles_for_code(20)
    assert len(diag.active_handles) == 0, "No handles when all codes at position are hidden"
    print("PASS 5: All codes hidden -> display_handles_for_code() attaches no handles.")

    # -------------------------------------------------------------
    # TEST 6: Arrow key boundary nudging in eventFilter() with hidden codes
    # -------------------------------------------------------------
    diag.app.hidden_cids = {2}  # Dog hidden, Fox visible (pos0=4, pos1=25)
    cursor = diag.plainTextEdit.textCursor()
    cursor.setPosition(20)
    diag.plainTextEdit.setTextCursor(cursor)

    diag.dialog_select_items_invoked = False
    diag.last_resized_ctid = None
    diag.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)

    # Nudge 1: Shift + Right (extend right, pos1: 25 -> 26)
    event1 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    consumed = diag.eventFilter(diag.plainTextEdit, event1)
    assert consumed is True, "Event should be consumed by boundary nudging"
    assert not diag.dialog_select_items_invoked, "DialogSelectItems MUST NOT be prompted for single visible code!"
    fox_code = next(c for c in diag.code_text if c['cid'] == 1)
    assert fox_code['pos1'] == 26, f"Expected pos1=26, got {fox_code['pos1']}"
    print("PASS 6: Shift+Right boundary nudge extends pos1 to 26 without DialogSelectItems.")

    # Nudge 2: Consecutive Shift + Right (pos1: 26 -> 27)
    diag.dialog_select_items_invoked = False
    diag.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)
    event2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    consumed = diag.eventFilter(diag.plainTextEdit, event2)
    assert consumed is True
    assert not diag.dialog_select_items_invoked, "Consecutive nudge MUST NOT trigger DialogSelectItems"
    assert fox_code['pos1'] == 27, f"Expected pos1=27, got {fox_code['pos1']}"
    print("PASS 7: Consecutive Shift+Right maintains uninterrupted focus and nudges pos1 to 27.")

    # Nudge 3: Alt + Left (shrink to left, pos1: 27 -> 26)
    diag.dialog_select_items_invoked = False
    diag.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)
    event3 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
    consumed = diag.eventFilter(diag.plainTextEdit, event3)
    assert consumed is True
    assert not diag.dialog_select_items_invoked
    assert fox_code['pos1'] == 26, f"Expected pos1=26, got {fox_code['pos1']}"
    print("PASS 8: Alt+Left shrinks pos1 to 26 without DialogSelectItems.")

    # -------------------------------------------------------------
    # TEST 9: Handle synchronization during keyboard nudging
    # -------------------------------------------------------------
    diag.display_handles_for_code(20)
    assert len(diag.active_handles) == 2
    # Nudge while handles are active
    diag.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)
    event4 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    diag.eventFilter(diag.plainTextEdit, event4)
    assert fox_code['pos1'] == 27
    assert diag.active_handles[0].code_item['pos1'] == 27, "Handle code_item must synchronize with nudged pos1"
    print("PASS 9: Active resize handles synchronize dynamically with keyboard boundary nudges.")
    diag.hide_resize_handles()

    # -------------------------------------------------------------
    # TEST 10: Both visible -> consecutive nudges maintain focus after initial selection
    # -------------------------------------------------------------
    diag.app.hidden_cids.clear()  # Both Fox and Dog visible
    diag.last_resized_ctid = None
    diag.dialog_select_items_invoked = False
    diag.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)
    
    # First press when both are visible prompts DialogSelectItems
    event_both_1 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    diag.eventFilter(diag.plainTextEdit, event_both_1)
    assert diag.dialog_select_items_invoked, "Initial press with multiple visible codes prompts selection"
    print("PASS 10a: First nudge with multiple visible codes prompts user selection.")

    # Second press within 2s session window maintains focus without re-prompting!
    diag.dialog_select_items_invoked = False
    diag.code_resize_timer = datetime.datetime.now() - datetime.timedelta(seconds=1)
    event_both_2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    diag.eventFilter(diag.plainTextEdit, event_both_2)
    assert not diag.dialog_select_items_invoked, "Consecutive nudge on multiple visible codes must NOT re-prompt!"
    print("PASS 10b: Consecutive nudge on multiple visible codes remembers focus and bypasses DialogSelectItems.")

    # -------------------------------------------------------------
    # TEST 11: Context menu and coded_text_memo() filter hidden codes
    # -------------------------------------------------------------
    diag.app.hidden_cids = {2}  # Hide Dog
    actions_at_20 = diag.get_context_menu_actions_at_pos(20)
    assert len(actions_at_20) == 1 and actions_at_20[0]['cid'] == 1, "Only Fox should be in context actions"

    diag.dialog_select_items_invoked = False
    memo_target = diag.coded_text_memo(20)
    assert not diag.dialog_select_items_invoked, "coded_text_memo MUST NOT prompt when only Fox is visible"
    assert memo_target['cid'] == 1
    print("PASS 11: Context actions and coded_text_memo() filter out hidden codes.")

    print("\nALL 11 ISSUE 05 VERIFICATION TESTS PASSED!\n")


if __name__ == "__main__":
    run_tests()
