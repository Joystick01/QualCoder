# -*- coding: utf-8 -*-
"""
PROTOTYPE & VERIFICATION: Text Highlighting and Coding Margin Filtering for Hidden Codes (Issue 04)

Verifies:
1. Segments belonging to hidden codes receive no background or underline text formatting in plainTextEdit.
2. CodingMargin lane packing (_compute_lane_layout) only allocates lanes for visible codes, eliminating gaps.
3. CodingMargin drawing (draw_code_bars) skips hidden codes completely.
4. CodingMargin hit-testing (_code_at_position) ignores hidden codes for both left-click selection and right-click context menu.
5. Overlapping formatting (apply_underline_to_overlaps and overlapping_codes_in_text) recalculates strictly among visible codes.
"""

import os
import sys
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QBrush, QTextCharFormat, QTextCursor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from qualcoder.color_selector import TextColor
    from qualcoder.code_text_coding_margin import CodingMargin, MINIMUM_CODING_MARGIN_WIDTH
except ImportError:
    from color_selector import TextColor
    from code_text_coding_margin import CodingMargin, MINIMUM_CODING_MARGIN_WIDTH


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


class VisibilityAwareCodingMargin(CodingMargin):
    """ Subclass implementing the Issue 04 hidden_cids filtering for CodingMargin. """

    def _compute_lane_layout(self):
        """ Track-packing algorithm excluding hidden codes. """
        if not self.dialog.file_ or not self.dialog.code_text:
            return None, [], None
        if getattr(self.dialog, 'ai_search_message_shown', False):
            return None, [], None

        current_fid = self.dialog.file_['id']
        important_only = getattr(self.dialog, 'important', False)
        hidden_cids = getattr(self.dialog.app, 'hidden_cids', set())

        sorted_codes = sorted(
            [c for c in self.dialog.code_text
             if c.get('fid') == current_fid
             and c.get('cid') not in hidden_cids
             and (not important_only or c.get('important') == 1)],
            key=lambda x: x.get('pos0', 0)
        )

        ctid_columns = {}
        tracks = []
        for code in sorted_codes:
            ctid = code.get('ctid')
            if ctid is None:
                continue
            placed = False
            for i, track_end in enumerate(tracks):
                if track_end <= code['pos0']:
                    tracks[i] = code['pos1']
                    ctid_columns[ctid] = i
                    placed = True
                    break
            if not placed:
                tracks.append(code['pos1'])
                ctid_columns[ctid] = len(tracks) - 1

        return ctid_columns, sorted_codes, current_fid

    def draw_code_bars(self, painter, block, rect, drawn_ctids, current_fid, ctid_columns):
        """ Draws stripes and labels skipping hidden codes. """
        file_start = self.dialog.file_.get('start', 0)
        block_start = block.position() + file_start
        block_end = block_start + block.length()

        names_drawn_by_line = {}
        margin_width = self.width()
        show_labels = margin_width >= 60
        background_color = self.editor.viewport().palette().color(QtGui.QPalette.ColorRole.Base)

        important_only = getattr(self.dialog, 'important', False)
        hidden_cids = getattr(self.dialog.app, 'hidden_cids', set())
        layout = block.layout()

        bar_w = 3
        lane_step = 10

        for code in self.dialog.code_text:
            if code.get('fid') != current_fid:
                continue
            if code.get('cid') in hidden_cids:
                continue
            if important_only and code.get('important') != 1:
                continue
            ctid = code.get('ctid')
            if ctid is None:
                continue

            if code['pos0'] < block_end and code['pos1'] > block_start:
                col_index = ctid_columns.get(ctid, 0)
                if self.side == 'right':
                    offset_x = 12 + (col_index * lane_step)
                else:
                    offset_x = margin_width - 15 - (col_index * lane_step)

                color_hex = code.get('color', '#cccccc')
                color = QtGui.QColor(color_hex)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)

                start_rel = max(code['pos0'], block_start) - block_start
                end_rel = min(code['pos1'], block_end) - block_start
                start_rel = max(0, min(start_rel, max(0, block.length() - 1)))
                end_rel = max(start_rel + 1, min(end_rel, block.length()))
                start_line = layout.lineForTextPosition(start_rel)
                end_line = layout.lineForTextPosition(max(start_rel, end_rel - 1))

                if start_line.isValid() and end_line.isValid():
                    first_line = start_line.lineNumber()
                    last_line = end_line.lineNumber()
                    for line_number in range(first_line, last_line + 1):
                        line = layout.lineAt(line_number)
                        if not line.isValid():
                            continue
                        painter.drawRect(
                            offset_x,
                            int(rect.top() + line.y()),
                            bar_w,
                            max(1, int(line.height()))
                        )
                else:
                    painter.drawRect(offset_x, int(rect.top()), bar_w, int(rect.height()))

                if show_labels and ctid not in drawn_ctids and code['pos0'] >= block_start:
                    painter.setPen(self._label_color_for_background(color, background_color))
                    raw_name = code.get('name', '')
                    _fm = painter.fontMetrics()
                    if self.side == 'right':
                        _lanes_end_x = 12 + (col_index + 1) * lane_step
                        _available_w = max(0, margin_width - _lanes_end_x - 5)
                    else:
                        _lanes_start_x = margin_width - 15 - (col_index + 1) * lane_step
                        _available_w = max(0, _lanes_start_x - 5 - 5)
                    name = _fm.elidedText(raw_name, QtCore.Qt.TextElideMode.ElideRight, _available_w)

                    if start_line.isValid():
                        line_number = start_line.lineNumber()
                        names_on_line = names_drawn_by_line.get(line_number, 0)
                        y_pos = int(rect.top() + start_line.y()
                                    + painter.fontMetrics().ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[line_number] = names_on_line + 1
                    else:
                        names_on_line = names_drawn_by_line.get(-1, 0)
                        y_pos = int(rect.top() + painter.fontMetrics().ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[-1] = names_on_line + 1

                    if self.side == 'right':
                        name_w = painter.fontMetrics().horizontalAdvance(name)
                        x_pos = max(margin_width - name_w - 5, 18)
                    else:
                        x_pos = 5

                    painter.drawText(x_pos, y_pos, name)
                    drawn_ctids.add(ctid)

    def _code_at_position(self, pos):
        """ Hit-test returning code_text item under QPoint, ignoring hidden codes. """
        if not self.dialog.file_ or not self.dialog.code_text:
            return None
        if getattr(self.dialog, 'ai_search_message_shown', False):
            return None

        ctid_columns, _sorted, current_fid = self._compute_lane_layout()
        if current_fid is None:
            return None

        margin_width = self.width()
        show_labels = margin_width >= 60
        bar_w = 3
        lane_step = 10

        offset = self.editor.contentOffset()
        block = self.editor.firstVisibleBlock()
        file_start = self.dialog.file_.get('start', 0)
        important_only = getattr(self.dialog, 'important', False)
        hidden_cids = getattr(self.dialog.app, 'hidden_cids', set())

        stripe_hit = None
        label_hit = None

        font = QtGui.QFont(self.dialog.app.settings['font'], 9)
        fm = QtGui.QFontMetrics(font)

        while block.isValid():
            rect = self.editor.blockBoundingGeometry(block).translated(offset)
            if rect.top() > self.height():
                break
            if rect.bottom() < 0:
                block = block.next()
                continue

            block_start = block.position() + file_start
            block_end = block_start + block.length()
            layout = block.layout()

            seen_ctids_in_block = set()
            names_drawn_by_line = {}

            for code in self.dialog.code_text:
                if code.get('fid') != current_fid:
                    continue
                if code.get('cid') in hidden_cids:
                    continue
                if important_only and code.get('important') != 1:
                    continue
                ctid = code.get('ctid')
                if ctid is None:
                    continue
                if not (code['pos0'] < block_end and code['pos1'] > block_start):
                    continue

                col_index = ctid_columns.get(ctid, 0)
                if self.side == 'right':
                    offset_x = 12 + (col_index * lane_step)
                else:
                    offset_x = margin_width - 15 - (col_index * lane_step)

                start_rel = max(code['pos0'], block_start) - block_start
                end_rel = min(code['pos1'], block_end) - block_start
                start_rel = max(0, min(start_rel, max(0, block.length() - 1)))
                end_rel = max(start_rel + 1, min(end_rel, block.length()))
                start_line = layout.lineForTextPosition(start_rel)
                end_line = layout.lineForTextPosition(max(start_rel, end_rel - 1))

                if start_line.isValid() and end_line.isValid():
                    first_line = start_line.lineNumber()
                    last_line = end_line.lineNumber()
                    for line_number in range(first_line, last_line + 1):
                        line = layout.lineAt(line_number)
                        if not line.isValid():
                            continue
                        stripe_rect = QtCore.QRect(
                            offset_x,
                            int(rect.top() + line.y()),
                            bar_w,
                            max(1, int(line.height())))
                        if stripe_rect.contains(pos):
                            stripe_hit = code

                if show_labels and ctid not in seen_ctids_in_block and code['pos0'] >= block_start:
                    raw_name = code.get('name', '')
                    if self.side == 'right':
                        _lanes_end_x = 12 + (col_index + 1) * lane_step
                        _available_w = max(0, margin_width - _lanes_end_x - 5)
                    else:
                        _lanes_start_x = margin_width - 15 - (col_index + 1) * lane_step
                        _available_w = max(0, _lanes_start_x - 5 - 5)
                    name = fm.elidedText(raw_name, QtCore.Qt.TextElideMode.ElideRight, _available_w)
                    if start_line.isValid():
                        line_number = start_line.lineNumber()
                        names_on_line = names_drawn_by_line.get(line_number, 0)
                        y_pos = int(rect.top() + start_line.y()
                                    + fm.ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[line_number] = names_on_line + 1
                    else:
                        names_on_line = names_drawn_by_line.get(-1, 0)
                        y_pos = int(rect.top() + fm.ascent() + (names_on_line * 12))
                        names_drawn_by_line[-1] = names_on_line + 1

                    name_w = fm.horizontalAdvance(name)
                    if self.side == 'right':
                        x_pos = max(margin_width - name_w - 5, 18)
                    else:
                        x_pos = 5

                    label_rect = QtCore.QRect(x_pos, y_pos - fm.ascent(), name_w, fm.height())
                    if label_rect.contains(pos):
                        label_hit = code
                    seen_ctids_in_block.add(ctid)

            block = block.next()

        return stripe_hit if stripe_hit is not None else label_hit


class MockDialog(QtWidgets.QWidget):
    def __init__(self, app=None):
        super().__init__()
        self.app = app or MockApp()
        self.highlight_style = 'marker'
        self.important = False
        self.ai_search_message_shown = False
        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0
        self.context_menu_invoked_with_code = None

        self.file_ = {'id': 1, 'start': 0, 'end': 300, 'name': 'sample.txt'}
        self.text = "The quick brown fox jumps over the lazy dog. A second sentence discusses emotions and feelings in depth."
        
        self.codes = [
            {'cid': 1, 'name': 'Fox', 'color': '#ff9999'},
            {'cid': 2, 'name': 'Dog', 'color': '#99ff99'},
            {'cid': 3, 'name': 'Emotions', 'color': '#9999ff'},
        ]
        
        # Segment 1: Fox (cid: 1, pos 10 to 45) -> "brown fox jumps over the"
        # Segment 2: Dog (cid: 2, pos 35 to 60) -> "over the lazy dog." (Overlaps Fox at 35..45)
        # Segment 3: Emotions (cid: 3, pos 70 to 100) -> non-overlapping
        self.code_text = [
            {'ctid': 101, 'cid': 1, 'fid': 1, 'pos0': 10, 'pos1': 45, 'seltext': self.text[10:45], 'memo': '', 'important': 0, 'name': 'Fox', 'color': '#ff9999'},
            {'ctid': 102, 'cid': 2, 'fid': 1, 'pos0': 35, 'pos1': 60, 'seltext': self.text[35:60], 'memo': '', 'important': 0, 'name': 'Dog', 'color': '#99ff99'},
            {'ctid': 103, 'cid': 3, 'fid': 1, 'pos0': 70, 'pos1': 100, 'seltext': self.text[70:100], 'memo': '', 'important': 0, 'name': 'Emotions', 'color': '#9999ff'},
        ]
        self.annotations = []

        # PlainTextEdit
        self.plainTextEdit = QtWidgets.QPlainTextEdit(self)
        self.plainTextEdit.setPlainText(self.text)
        self.plainTextEdit.resize(500, 400)
        
        # Mock UI container
        class MockUI:
            pass
        self.ui = MockUI()
        self.ui.plainTextEdit = self.plainTextEdit

        # Visibility Aware Margin
        self.coding_margin = VisibilityAwareCodingMargin(self.plainTextEdit, self, side='left')
        self.coding_margin.resize(100, 400)

    def coding_margin_context_menu(self, position, source_widget):
        clicked_code = source_widget._code_at_position(position)
        self.context_menu_invoked_with_code = clicked_code

    def _build_code_tooltip_html(self, code):
        return f"<b>{code.get('name')}</b>"

    def unlight(self):
        """ Remove all text highlighting from current file. """
        if self.text is None or self.text == "":
            return
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(0, QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.text), QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QTextCharFormat())

    def highlight(self):
        """ Filter out hidden codes when highlighting. """
        if self.file_ is None or self.ai_search_message_shown or self.ui.plainTextEdit.toPlainText() == "":
            if hasattr(self, 'coding_margin') and self.coding_margin is not None:
                self.coding_margin.update()
            return

        codes = {x['cid']: x for x in self.codes}
        hidden_cids = getattr(self.app, 'hidden_cids', set())

        for item in self.code_text:
            if item['cid'] in hidden_cids:
                continue

            fmt = QTextCharFormat()
            cursor = self.ui.plainTextEdit.textCursor()
            cursor.setPosition(int(item['pos0'] - self.file_['start']), QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(int(item['pos1'] - self.file_['start']), QTextCursor.MoveMode.KeepAnchor)
            color = codes.get(item['cid'], {}).get('color', "#777777")

            if self.highlight_style == 'underline':
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.DashUnderline)
                fmt.setUnderlineColor(QColor(color))
            else:
                brush = QBrush(QColor(color))
                fmt.setBackground(brush)
                text_brush = QBrush(QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)

            if item['memo'] != "":
                fmt.setFontItalic(True)
            else:
                fmt.setFontItalic(False)

            if item['important']:
                fmt.setFontWeight(QtGui.QFont.Weight.Bold)

            if not self.important or (self.important and item['important'] == 1):
                cursor.mergeCharFormat(fmt)

        self.apply_underline_to_overlaps()
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def apply_underline_to_overlaps(self):
        """ Filter out hidden codes from overlap calculations. """
        if self.important:
            return
        if getattr(self, 'highlight_style', 'marker') == 'underline':
            return

        hidden_cids = getattr(self.app, 'hidden_cids', set())
        visible_codes = [c for c in self.code_text if c.get('cid') not in hidden_cids]

        overlaps = []
        for i in visible_codes:
            for j in visible_codes:
                if j != i:
                    if j['pos0'] <= i['pos0'] <= j['pos1']:
                        if (j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']) and (j['pos0'] != j['pos1']):
                            overlaps.append([j['pos0'], j['pos1']])
                        elif (i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']) and (i['pos0'] != i['pos1']):
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0'] and (j['pos0'] != i['pos1']):
                            overlaps.append([j['pos0'], i['pos1']])
                        elif j['pos1'] != i['pos0']:
                            overlaps.append([j['pos1'], i['pos0']])

        cursor = self.ui.plainTextEdit.textCursor()
        for o in overlaps:
            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            if self.app.settings['stylesheet'] == 'dark':
                fmt.setUnderlineColor(QColor("#000000"))
            else:
                fmt.setUnderlineColor(QColor("#FFFFFF"))
            cursor.setPosition(o[0] - self.file_['start'], QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(o[1] - self.file_['start'], QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def overlapping_codes_in_text(self):
        """ When cursor moves, only visible codes count toward overlaps. """
        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0
        if self.ai_search_message_shown:
            return
        pos = self.ui.plainTextEdit.textCursor().position()
        hidden_cids = getattr(self.app, 'hidden_cids', set())
        for item in self.code_text:
            if item.get('cid') in hidden_cids:
                continue
            if item['pos0'] <= pos + self.file_['start'] <= item['pos1']:
                self.overlaps_at_pos.append(item)
        if len(self.overlaps_at_pos) < 2:
            self.overlaps_at_pos = []
            self.overlaps_at_pos_idx = 0

    def on_code_visibility_changed(self):
        """ Respond to code visibility changes. """
        if self.file_ is None or self.ui.plainTextEdit.toPlainText() == "":
            if hasattr(self, 'coding_margin') and self.coding_margin is not None:
                self.coding_margin.update()
            return
        self.ui.plainTextEdit.setUpdatesEnabled(False)
        try:
            self.unlight()
            self.highlight()
        finally:
            self.ui.plainTextEdit.setUpdatesEnabled(True)
        self.overlapping_codes_in_text()


def run_tests():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    diag = MockDialog()
    diag.show()
    app.processEvents()

    print("=== Running Comprehensive Issue 04 Verification Tests ===")

    # 1. Initial State: All codes visible
    diag.highlight()

    # Verify Fox background at pos 20
    cursor = diag.plainTextEdit.textCursor()
    cursor.setPosition(20)
    assert cursor.charFormat().background().color().name() == "#ff9999"

    # Verify Overlap underline at pos 40
    cursor.setPosition(40)
    assert cursor.charFormat().underlineStyle() == QTextCharFormat.UnderlineStyle.SingleUnderline
    print("PASS 1: All codes visible -> formatting & overlap underlines active.")

    # Verify Margin lane computation with all visible
    ctid_cols, sorted_codes, cur_fid = diag.coding_margin._compute_lane_layout()
    assert len(sorted_codes) == 3
    assert ctid_cols[101] == 0, "Fox lane 0"
    assert ctid_cols[102] == 1, "Dog lane 1"
    assert ctid_cols[103] == 0, "Emotions lane 0"
    print("PASS 2: Margin lane packing uses 2 lanes (Dog packed in lane 1).")

    # Verify hit testing on margin
    # Lane 0 offset for left margin (width 100): 100 - 15 - 0 = 85. Lane 1 offset: 100 - 15 - 10 = 75.
    pos_fox = QPoint(85, 20)
    hit_fox = diag.coding_margin._code_at_position(pos_fox)
    assert hit_fox is not None and hit_fox['cid'] == 1, f"Expected Fox hit, got {hit_fox}"

    pos_dog = QPoint(75, 20)
    hit_dog = diag.coding_margin._code_at_position(pos_dog)
    assert hit_dog is not None and hit_dog['cid'] == 2, f"Expected Dog hit, got {hit_dog}"
    print("PASS 3: CodingMargin hit-tests both Fox and Dog when visible.")

    # 2. Hide Dog (cid: 2)
    diag.app.hidden_cids.add(2)
    diag.on_code_visibility_changed()
    app.processEvents()

    # Verify Pos 50 (Dog only) has NO background formatting
    cursor.setPosition(50)
    bg50 = cursor.charFormat().background()
    assert bg50.style() == Qt.BrushStyle.NoBrush or bg50.color().name() not in ["#99ff99", "#ff9999"]

    # Verify Pos 40 (Fox + Dog) now has Fox background but NO underline
    cursor.setPosition(40)
    fmt40 = cursor.charFormat()
    assert fmt40.background().color().name() == "#ff9999"
    assert fmt40.underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline
    print("PASS 4: Dog hidden -> Pos 50 cleared, Pos 40 Fox background preserved with NoUnderline.")

    # 3. Margin lane layout when Dog is hidden
    ctid_cols, sorted_codes, cur_fid = diag.coding_margin._compute_lane_layout()
    assert len(sorted_codes) == 2, f"Expected 2 sorted codes, got {len(sorted_codes)}"
    assert 102 not in ctid_cols, "Dog should NOT have a lane allocated"
    assert ctid_cols[101] == 0, "Fox lane 0"
    assert ctid_cols[103] == 0, "Emotions lane 0"
    print("PASS 5: Margin lane packing excludes Dog; only 1 lane used total (zero gaps).")

    # 4. Margin hit-testing when Dog is hidden
    hit_at_dog_spot = diag.coding_margin._code_at_position(pos_dog)
    assert hit_at_dog_spot is None, f"Expected None at Dog lane position when Dog is hidden, got {hit_at_dog_spot}"
    
    # Hit test at Fox position still works
    hit_at_fox_spot = diag.coding_margin._code_at_position(pos_fox)
    assert hit_at_fox_spot is not None and hit_at_fox_spot['cid'] == 1
    print("PASS 6: Margin hit-test returns None at hidden code location and Fox at visible location.")

    # 5. Right-click context menu delegation
    diag.coding_margin._emit_context_menu_to_dialog(pos_dog)
    assert diag.context_menu_invoked_with_code is None, "Right-click over hidden code should yield None (general margin menu)"

    diag.coding_margin._emit_context_menu_to_dialog(pos_fox)
    assert diag.context_menu_invoked_with_code is not None and diag.context_menu_invoked_with_code['cid'] == 1, "Right-click over visible code should yield Fox"
    print("PASS 7: Right-click context menu correctly discriminates visible vs hidden code.")

    # 6. PaintEvent executes cleanly with hidden code
    # Render into a QPixmap
    pix = QtGui.QPixmap(diag.coding_margin.size())
    diag.coding_margin.render(pix)
    assert not pix.isNull()
    print("PASS 8: CodingMargin paintEvent renders successfully with hidden codes.")

    print("\nALL 8 ISSUE 04 VERIFICATION TESTS PASSED!\n")


if __name__ == "__main__":
    run_tests()
