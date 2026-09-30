# -*- coding: utf-8 -*-
"""
PROTOTYPE: Code Tree Visibility Toggle (Issue 02)
Throwaway prototype testing Column 0 eye icon interactions in QTreeWidget:
- Dedicated Column 0 with eye icons (mdi6.eye-outline / mdi6.eye-off-outline)
- tree.setTreePosition(1) so hierarchy and disclosure arrows stay on Column 1 (Name)
- Column 0 fixed width (~28px)
- Normal click on code toggles visibility
- Normal click on category cascades to all descendant codes
- Alt-click (or Ctrl-click) solos code/category, second Alt-click restores prior state
- Sorting by Name (Column 1)
- Live state inspection

Run interactively:
    python3 src/qualcoder/prototype_code_tree_visibility.py
Run automated verification:
    python3 src/qualcoder/prototype_code_tree_visibility.py --test
"""

import os
import sys
import qtawesome as qta
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from qualcoder.color_selector import TextColor
except ImportError:
    from color_selector import TextColor


class MockApp:
    def __init__(self):
        self.hidden_cids = set()
        self.pre_solo_hidden_cids = None
        self.settings = {'showids': True, 'fontsize': 11}
        self.collapsed_categories = []

    def is_code_visible(self, cid: int) -> bool:
        return cid not in self.hidden_cids


class PrototypeCodeTree(QtWidgets.QWidget):
    # Signals
    code_visibility_changed = QtCore.pyqtSignal()

    # Column constants
    COL_VIS = 0
    COL_NAME = 1
    COL_ID = 2
    COL_MEMO = 3
    COL_COUNT = 4

    def __init__(self, app=None, parent=None):
        super().__init__(parent)
        self.app = app or MockApp()
        self.categories = [
            {'catid': 1, 'name': 'Emotions', 'supercatid': None, 'memo': 'Emotional responses'},
            {'catid': 2, 'name': 'Positive', 'supercatid': 1, 'memo': 'Positive emotions'},
            {'catid': 3, 'name': 'Negative', 'supercatid': 1, 'memo': 'Negative emotions'},
            {'catid': 4, 'name': 'Actions', 'supercatid': None, 'memo': 'Observed actions'},
        ]
        self.codes = [
            {'cid': 101, 'name': 'Joy', 'catid': 2, 'supercid': None, 'color': '#99ff99', 'memo': 'Feeling joy'},
            {'cid': 102, 'name': 'Hope', 'catid': 2, 'supercid': None, 'color': '#b3ffb3', 'memo': 'Feeling hope'},
            {'cid': 103, 'name': 'Anger', 'catid': 3, 'supercid': None, 'color': '#ff9999', 'memo': 'Feeling anger'},
            {'cid': 104, 'name': 'Fear', 'catid': 3, 'supercid': None, 'color': '#ffb3b3', 'memo': 'Feeling fear'},
            {'cid': 105, 'name': 'Walking', 'catid': 4, 'supercid': None, 'color': '#99ccff', 'memo': 'Walking action'},
            {'cid': 106, 'name': 'Running', 'catid': 4, 'supercid': None, 'color': '#80bfff', 'memo': 'Running action'},
            {'cid': 107, 'name': 'Sprint', 'catid': None, 'supercid': 106, 'color': '#66b3ff', 'memo': 'Fast running'},
            {'cid': 108, 'name': 'Free Code', 'catid': None, 'supercid': None, 'color': '#ffff99', 'memo': 'Uncategorized'},
        ]

        self.icon_visible = qta.icon('mdi6.eye-outline', color='#444444')
        self.icon_hidden = qta.icon('mdi6.eye-off-outline', color='#bbbbbb')
        self.icon_partial = qta.icon('mdi6.eye-minus-outline', color='#888888')

        self.last_solo_target = None  # (type: 'cid'|'catid', id: int)
        self._init_ui()
        self.fill_tree()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Header info
        self.info_label = QtWidgets.QLabel("<b>Prototype: Code Tree Visibility Toggle</b><br>"
                                           "Click Col 0 eye to toggle. Alt-click (or Ctrl-click) to solo.")
        layout.addWidget(self.info_label)

        # Tree widget
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["", "Name", "Id", "Memo", "Count"])
        self.tree.setTreePosition(self.COL_NAME)

        # Header configuration for Column 0 (Eye)
        header = self.tree.header()
        header.setSectionResizeMode(self.COL_VIS, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(self.COL_VIS, 28)
        header.resizeSection(self.COL_VIS, 28)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self.on_header_section_clicked)
        header.setSectionResizeMode(self.COL_NAME, QtWidgets.QHeaderView.ResizeMode.Interactive)
        header.resizeSection(self.COL_NAME, 200)

        self.tree.itemClicked.connect(self.on_tree_item_clicked)
        layout.addWidget(self.tree)

        # State display
        self.state_label = QtWidgets.QLabel()
        self.state_label.setStyleSheet("background: #f0f0f0; padding: 6px; font-family: monospace;")
        layout.addWidget(self.state_label)

        # Control buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_toggle_all = QtWidgets.QPushButton()
        self.btn_toggle_all.setIcon(self.icon_visible)
        self.btn_toggle_all.setToolTip("Toggle all codes visibility")
        self.btn_toggle_all.clicked.connect(self.toggle_all_visibility)
        btn_layout.addWidget(self.btn_toggle_all)

        btn_sort_asc = QtWidgets.QPushButton("Sort Asc")
        btn_sort_asc.clicked.connect(lambda: self.tree.sortByColumn(self.COL_NAME, Qt.SortOrder.AscendingOrder))
        btn_layout.addWidget(btn_sort_asc)

        btn_sort_desc = QtWidgets.QPushButton("Sort Desc")
        btn_sort_desc.clicked.connect(lambda: self.tree.sortByColumn(self.COL_NAME, Qt.SortOrder.DescendingOrder))
        btn_layout.addWidget(btn_sort_desc)

        layout.addLayout(btn_layout)
        self.code_visibility_changed.connect(self.update_state_display)

    def fill_tree(self):
        self.tree.clear()
        node_index = {}

        # 1. Add categories
        for c in self.categories:
            if c['supercatid'] is None:
                item = QtWidgets.QTreeWidgetItem(["", c['name'], f"catid:{c['catid']}", c['memo'], ""])
                self.tree.addTopLevelItem(item)
                node_index[f"catid:{c['catid']}"] = item

        for c in self.categories:
            if c['supercatid'] is not None:
                parent = node_index.get(f"catid:{c['supercatid']}")
                item = QtWidgets.QTreeWidgetItem(["", c['name'], f"catid:{c['catid']}", c['memo'], ""])
                if parent:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                node_index[f"catid:{c['catid']}"] = item

        # 2. Add codes
        for c in self.codes:
            item = QtWidgets.QTreeWidgetItem(["", c['name'], f"cid:{c['cid']}", c['memo'], "0"])
            item.setBackground(self.COL_NAME, QtGui.QBrush(QtGui.QColor(c['color'])))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

            if c['supercid'] is not None:
                parent = node_index.get(f"cid:{c['supercid']}")
            elif c['catid'] is not None:
                parent = node_index.get(f"catid:{c['catid']}")
            else:
                parent = None

            if parent:
                parent.addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            node_index[f"cid:{c['cid']}"] = item

        self.tree.expandAll()
        self.update_all_eye_icons()
        self.update_state_display()

    def get_descendant_cids(self, item: QtWidgets.QTreeWidgetItem) -> list[int]:
        """Recursively gather all code IDs (cids) under this item (or item's own cid)."""
        id_str = item.text(self.COL_ID)
        cids = []
        if id_str.startswith("cid:"):
            cids.append(int(id_str[4:]))
        for i in range(item.childCount()):
            cids.extend(self.get_descendant_cids(item.child(i)))
        return cids

    def get_all_cids(self) -> list[int]:
        """Return all cids currently defined."""
        return [c['cid'] for c in self.codes]

    def dim_color(self, hex_color: str) -> QtGui.QColor:
        """Produce a washed-out, muted tint for hidden code backgrounds."""
        c = QtGui.QColor(hex_color)
        return QtGui.QColor(
            int(c.red() * 0.25 + 235 * 0.75),
            int(c.green() * 0.25 + 235 * 0.75),
            int(c.blue() * 0.25 + 235 * 0.75),
        )

    def update_item_visual_state(self, item: QtWidgets.QTreeWidgetItem):
        """Update eye icon and greyed-out visual state for a specific item."""
        id_str = item.text(self.COL_ID)
        grey_text_brush = QtGui.QBrush(QtGui.QColor('#888888'))
        muted_text_brush = QtGui.QBrush(QtGui.QColor('#aaaaaa'))
        default_text_brush = QtGui.QBrush(QtGui.QColor('#000000'))

        if id_str.startswith("cid:"):
            cid = int(id_str[4:])
            is_vis = self.app.is_code_visible(cid)
            item.setIcon(self.COL_VIS, self.icon_visible if is_vis else self.icon_hidden)
            item.setToolTip(self.COL_VIS, _("Visible (Click to hide)") if is_vis else _("Hidden (Click to show)"))

            # Find code dict for color
            code_dict = next((c for c in self.codes if c['cid'] == cid), None)
            if code_dict:
                if is_vis:
                    # Normal vibrant styling
                    item.setBackground(self.COL_NAME, QtGui.QBrush(QtGui.QColor(code_dict['color'])))
                    item.setForeground(self.COL_NAME, QtGui.QBrush(QtGui.QColor(TextColor(code_dict['color']).recommendation)))
                    for col in (self.COL_ID, self.COL_MEMO, self.COL_COUNT):
                        item.setForeground(col, default_text_brush)
                else:
                    # Greyed out styling
                    dimmed_bg = self.dim_color(code_dict['color'])
                    item.setBackground(self.COL_NAME, QtGui.QBrush(dimmed_bg))
                    item.setForeground(self.COL_NAME, grey_text_brush)
                    for col in (self.COL_ID, self.COL_MEMO, self.COL_COUNT):
                        item.setForeground(col, muted_text_brush)

        elif id_str.startswith("catid:"):
            desc_cids = self.get_descendant_cids(item)
            if not desc_cids:
                item.setIcon(self.COL_VIS, self.icon_visible)
                item.setToolTip(self.COL_VIS, "")
                for col in range(self.tree.columnCount()):
                    item.setForeground(col, default_text_brush)
            else:
                visible_count = sum(1 for cid in desc_cids if self.app.is_code_visible(cid))
                if visible_count == len(desc_cids):
                    # Fully visible
                    item.setIcon(self.COL_VIS, self.icon_visible)
                    item.setToolTip(self.COL_VIS, "All visible (Click to hide branch)")
                    for col in range(self.tree.columnCount()):
                        item.setForeground(col, default_text_brush)
                elif visible_count == 0:
                    # Fully hidden -> grey out category text
                    item.setIcon(self.COL_VIS, self.icon_hidden)
                    item.setToolTip(self.COL_VIS, "All hidden (Click to show branch)")
                    for col in range(self.tree.columnCount()):
                        item.setForeground(col, grey_text_brush)
                else:
                    # Partially visible
                    item.setIcon(self.COL_VIS, self.icon_partial)
                    item.setToolTip(self.COL_VIS, f"Partially visible ({visible_count}/{len(desc_cids)}) (Click to hide branch)")
                    for col in range(self.tree.columnCount()):
                        item.setForeground(col, default_text_brush)

    def update_all_eye_icons(self):
        """Update eye icons and greyed-out visual states across the entire tree in-place without rebuilding."""
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            self.update_item_visual_state(it.value())
            it += 1

    def on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """Handle clicks on the tree. If Column 0 is clicked, handle visibility toggle/solo."""
        if column != self.COL_VIS:
            # Clicking other columns behaves as normal item selection
            return

        modifiers = QtWidgets.QApplication.keyboardModifiers()
        is_alt = bool(modifiers & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier))

        id_str = item.text(self.COL_ID)
        if is_alt:
            self.handle_solo_click(item)
        else:
            self.handle_toggle_click(item)

    def handle_toggle_click(self, item: QtWidgets.QTreeWidgetItem):
        """Normal click on eye: toggle single code or cascade toggle category."""
        id_str = item.text(self.COL_ID)
        self.app.pre_solo_hidden_cids = None  # Any manual toggle clears solo restore snapshot
        self.last_solo_target = None

        if id_str.startswith("cid:"):
            cid = int(id_str[4:])
            if cid in self.app.hidden_cids:
                self.app.hidden_cids.remove(cid)
            else:
                self.app.hidden_cids.add(cid)
        elif id_str.startswith("catid:"):
            desc_cids = self.get_descendant_cids(item)
            # If any are visible, hide all; if all are hidden, show all
            any_visible = any(self.app.is_code_visible(c) for c in desc_cids)
            if any_visible:
                self.app.hidden_cids.update(desc_cids)
            else:
                self.app.hidden_cids.difference_update(desc_cids)

        self.update_all_eye_icons()
        self.code_visibility_changed.emit()

    def handle_solo_click(self, item: QtWidgets.QTreeWidgetItem):
        """Alt-click: solo code or category. Second Alt-click on same item restores prior state."""
        id_str = item.text(self.COL_ID)
        all_cids = set(self.get_all_cids())
        target_cids = set(self.get_descendant_cids(item))

        target_key = (id_str[:3], int(id_str.split(':')[1]))

        # Check if already soloed on this exact target
        if self.app.pre_solo_hidden_cids is not None and self.last_solo_target == target_key:
            # Restore previous state
            self.app.hidden_cids = set(self.app.pre_solo_hidden_cids)
            self.app.pre_solo_hidden_cids = None
            self.last_solo_target = None
        else:
            # Save current state for undo
            self.app.pre_solo_hidden_cids = set(self.app.hidden_cids)
            self.last_solo_target = target_key
            # Hide all codes except target cids
            self.app.hidden_cids = all_cids - target_cids

        self.update_all_eye_icons()
        self.code_visibility_changed.emit()

    def toggle_all_visibility(self):
        """Toggle all codes between all visible and all hidden."""
        all_cids = set(self.get_all_cids())
        if len(self.app.hidden_cids) == 0:
            # All are visible -> hide all
            self.app.hidden_cids = set(all_cids)
        else:
            # Some or all are hidden -> make all visible
            self.app.hidden_cids.clear()
        self.app.pre_solo_hidden_cids = None
        self.last_solo_target = None
        self.update_all_eye_icons()
        self.code_visibility_changed.emit()

    def on_header_section_clicked(self, logical_index: int):
        """Header click on Column 0 (Eye) toggles all codes visibility."""
        if logical_index == self.COL_VIS:
            self.toggle_all_visibility()

    def update_state_display(self):
        total = len(self.codes)
        hidden = len(self.app.hidden_cids)
        visible = total - hidden

        # Update header icon and tooltip for Column 0 (Eye)
        header_icon = self.icon_visible if hidden == 0 else self.icon_hidden
        header_tip = "Hide all codes" if hidden == 0 else "Show all codes"
        self.tree.headerItem().setIcon(self.COL_VIS, header_icon)
        self.tree.headerItem().setToolTip(self.COL_VIS, header_tip)

        # Update toggle all button icon and tooltip if present
        if hasattr(self, 'btn_toggle_all'):
            self.btn_toggle_all.setIcon(header_icon)
            self.btn_toggle_all.setToolTip(header_tip)

        solo_info = f"Solo active (prior: {len(self.app.pre_solo_hidden_cids)} hidden)" if self.app.pre_solo_hidden_cids is not None else "None"
        text = (f"Codes total: {total} | Visible: {visible} | Hidden: {hidden}\n"
                f"Hidden CIDs: {sorted(list(self.app.hidden_cids))}\n"
                f"Pre-solo snapshot: {solo_info}")
        self.state_label.setText(text)


def _(text):
    return text


def run_tests():
    """Automated verification of Column 0 eye toggles, cascading, and soloing."""
    print("=== Running Automated Prototype Verification ===")
    app = QtWidgets.QApplication(sys.argv)
    proto = PrototypeCodeTree()

    all_cids = set(proto.get_all_cids())
    print(f"Total codes initialized: {len(all_cids)}")

    # 1. Verify Column 0 setup and tree position
    assert proto.tree.columnCount() == 5, f"Expected 5 columns, got {proto.tree.columnCount()}"
    assert proto.tree.treePosition() == proto.COL_NAME, f"Tree position must be Column 1 (Name)"
    assert proto.tree.columnWidth(proto.COL_VIS) == 28, f"Column 0 width must be 28px"
    print("PASS: Tree configuration & Column 0 fixed width verified.")

    # 2. Verify initial visibility (all visible by default)
    assert len(proto.app.hidden_cids) == 0, "All codes must be visible by default"
    for cid in all_cids:
        assert proto.app.is_code_visible(cid), f"Code {cid} should be visible"
    print("PASS: Default-visible state verified.")

    # 3. Test clicking Column 0 on single code (e.g. Joy, cid: 101)
    # Find item for Joy
    it = QtWidgets.QTreeWidgetItemIterator(proto.tree)
    joy_item = None
    pos_cat_item = None
    while it.value():
        if it.value().text(proto.COL_ID) == "cid:101":
            joy_item = it.value()
        if it.value().text(proto.COL_ID) == "catid:2":
            pos_cat_item = it.value()
        it += 1
    assert joy_item is not None, "Joy item not found"
    assert pos_cat_item is not None, "Positive category item not found"

    # Simulate click on Col 0 for Joy
    proto.on_tree_item_clicked(joy_item, proto.COL_VIS)
    assert 101 in proto.app.hidden_cids, "Joy (101) should now be hidden"
    assert not proto.app.is_code_visible(101)
    print("PASS: Single code visibility toggle hide verified.")

    # Category 'Positive' has codes 101 (hidden) and 102 (visible) -> partial
    desc_pos = proto.get_descendant_cids(pos_cat_item)
    assert set(desc_pos) == {101, 102}
    # Click Col 0 on Positive category -> should cascade hide all descendants
    proto.on_tree_item_clicked(pos_cat_item, proto.COL_VIS)
    assert 101 in proto.app.hidden_cids and 102 in proto.app.hidden_cids, "All positive codes should now be hidden"
    print("PASS: Category cascade hide verified.")

    # Click Col 0 on Positive category again -> since all are hidden, should cascade show all descendants
    proto.on_tree_item_clicked(pos_cat_item, proto.COL_VIS)
    assert 101 not in proto.app.hidden_cids and 102 not in proto.app.hidden_cids, "All positive codes should now be visible"
    print("PASS: Category cascade show verified.")

    # 4. Test Alt-click solo on Joy (101)
    proto.handle_solo_click(joy_item)
    assert proto.app.is_code_visible(101), "Joy should be visible when soloed"
    assert len(proto.app.hidden_cids) == len(all_cids) - 1, "All other codes should be hidden"
    assert all_cids - {101} == proto.app.hidden_cids
    assert proto.app.pre_solo_hidden_cids == set(), "Pre-solo snapshot should record empty set"
    print("PASS: Alt-click solo single code verified.")

    # Second Alt-click on Joy -> restores prior state
    proto.handle_solo_click(joy_item)
    assert len(proto.app.hidden_cids) == 0, "Prior visibility state should be restored on second Alt-click"
    assert proto.app.pre_solo_hidden_cids is None, "Solo state should be cleared"
    print("PASS: Second Alt-click restores prior visibility verified.")

    # 5. Test Alt-click solo on Category 'Negative' (catid: 3, codes 103, 104)
    neg_cat_item = None
    it = QtWidgets.QTreeWidgetItemIterator(proto.tree)
    while it.value():
        if it.value().text(proto.COL_ID) == "catid:3":
            neg_cat_item = it.value()
        it += 1
    assert neg_cat_item is not None

    proto.handle_solo_click(neg_cat_item)
    assert proto.app.is_code_visible(103) and proto.app.is_code_visible(104), "Negative codes should be visible"
    assert not proto.app.is_code_visible(101) and not proto.app.is_code_visible(105), "Other codes should be hidden"
    assert proto.app.hidden_cids == all_cids - {103, 104}
    print("PASS: Alt-click solo category verified.")

    # Restore
    proto.handle_solo_click(neg_cat_item)
    assert len(proto.app.hidden_cids) == 0
    print("PASS: Alt-click restore category verified.")

    # 6. Test Toggle All
    proto.toggle_all_visibility()
    assert len(proto.app.hidden_cids) == len(all_cids), "Toggle all should hide all codes"
    proto.toggle_all_visibility()
    assert len(proto.app.hidden_cids) == 0, "Toggle all again should show all codes"
    print("PASS: Toggle all visibility verified.")

    # 7. Test sorting by Name (Column 1)
    proto.tree.sortByColumn(proto.COL_NAME, Qt.SortOrder.AscendingOrder)
    top_items = [proto.tree.topLevelItem(i).text(proto.COL_NAME) for i in range(proto.tree.topLevelItemCount())]
    assert top_items == sorted(top_items), f"Top items should be sorted alphabetically: {top_items}"
    print("PASS: Sorting by Column 1 (Name) verified.")

    # 8. Test Header Section 0 click triggers toggle_all_visibility
    assert len(proto.app.hidden_cids) == 0
    # Simulate clicking header section 0
    proto.on_header_section_clicked(proto.COL_VIS)
    assert len(proto.app.hidden_cids) == len(all_cids), "Header click should hide all codes"
    assert proto.tree.headerItem().toolTip(proto.COL_VIS) == "Show all codes"

    # Simulate clicking header section 0 again
    proto.on_header_section_clicked(proto.COL_VIS)
    assert len(proto.app.hidden_cids) == 0, "Second header click should show all codes"
    assert proto.tree.headerItem().toolTip(proto.COL_VIS) == "Hide all codes"
    print("PASS: Column 0 Header section click toggle-all verified.")

    print("\nALL 8 PROTOTYPE VERIFICATION TESTS PASSED!\n")


if __name__ == "__main__":
    if "--test" in sys.argv or not QtCore.QCoreApplication.instance():
        run_tests()
    if "--gui" in sys.argv:
        app = QtWidgets.QApplication(sys.argv)
        proto = PrototypeCodeTree()
        proto.resize(450, 500)
        proto.show()
        sys.exit(app.exec())
