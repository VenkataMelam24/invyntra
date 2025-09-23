# app/ui_login.py

# app/ui_login.py
import sys, os
from PySide6 import QtCore, QtWidgets, QtGui


from app.inventory_utils import parse_inventory_command, _normalize_unit as _inv_normalize_unit, _clean_item as _inv_clean_item
import csv, datetime
from app.core.config import settings
import os, shutil, json
from app.auth_service import (
    create_user,
    authenticate_credentials,
    generate_otp_for,
    verify_otp,
    find_user_by_email_or_phone,
    reset_password,
    update_business_name,
)
 
COUNTRY_CHOICES = [
    ("+1",  "United States"),
    ("+44", "United Kingdom"),
    ("+61", "Australia"),
    ("+65", "Singapore"),
    ("+81", "Japan"),
    ("+82", "South Korea"),
    ("+86", "China"),
    ("+91", "India"),
    ("+971","UAE"),
    ("+94", "Sri Lanka"),
    ("+880","Bangladesh"),
    ("+92", "Pakistan"),
    ("+60", "Malaysia"),
    ("+62", "Indonesia"),
    ("+63", "Philippines"),
    ("+233","Ghana"),
    ("+234","Nigeria"),
    ("+254","Kenya"),
]

PWD_HINT = "Password must be â‰¥ 8 chars, include at least 1 uppercase and 1 special character."

class LoginCard(QtWidgets.QFrame):
    request_signup = QtCore.Signal()
    request_forgot = QtCore.Signal(str)
    login_success = QtCore.Signal(str)  # identifier

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setStyleSheet("""
            QFrame#Card { background:white; border-radius:16px; }
            QLabel { color:#111; }
            QLineEdit { height:34px; padding:4px 10px; border:1px solid #ddd; border-radius:8px; }
            QPushButton { height:40px; border-radius:8px; background:#111; color:white; }
            QPushButton[flat="true"] { background:transparent; color:#111; text-decoration:underline; }
            QMessageBox { background:white; }
        """)

        title = QtWidgets.QLabel("Log in")
        title.setStyleSheet("font-size:20px;font-weight:700;")

        self.identifier = QtWidgets.QLineEdit()
        self.identifier.setPlaceholderText("Email or Phone")
        self.password = QtWidgets.QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        # Show/Hide toggle for password
        self.show_pw = QtWidgets.QToolButton(); self.show_pw.setText("Show"); self.show_pw.setFixedWidth(56)

        self.info = QtWidgets.QLabel("Enter your email/phone and password. Weâ€™ll send a 6-digit OTP.")
        self.info.setStyleSheet("color:#666; font-size:12px;")
        # Ensure clean text (fix encoding artifacts)
        self.info.setText("Enter your email/phone and password. We'll send a 6-digit OTP.")

        # Primary button with flow: Get OTP -> Submit OTP
        self.primary_btn = QtWidgets.QPushButton("Get OTP")
        self.primary_btn.setMinimumHeight(40)
        self.primary_btn.setMinimumWidth(180)
        # Resend timer/link
        self.resend_btn = QtWidgets.QPushButton("Resend OTP (30)")
        self.resend_btn.setFlat(True)
        self.resend_btn.setEnabled(False)
        self._resend_timer = QtCore.QTimer(self)
        self._resend_timer.setInterval(1000)
        self._resend_timer.timeout.connect(self._tick_resend)
        self._resend_remaining = 30
        self._awaiting_otp = False
        # Slightly wider OTP field for clarity (set after creation below)
        goto_signup = QtWidgets.QPushButton("New here? Sign up")
        goto_signup.setFlat(True)
        forgot = QtWidgets.QPushButton("Forgot password?")
        forgot.setFlat(True)

        self.primary_btn.clicked.connect(self.on_primary_click)
        self.resend_btn.clicked.connect(self.on_resend_otp)
        goto_signup.clicked.connect(self.request_signup.emit)
        forgot.clicked.connect(lambda: self.request_forgot.emit(self.identifier.text().strip()))

        self.otp = QtWidgets.QLineEdit()
        self.otp.setPlaceholderText("Enter 6-digit OTP")
        self.otp.setMaxLength(6)
        self.otp.setAlignment(QtCore.Qt.AlignCenter)
        # Allow OTP to grow but keep a sensible max
        self.otp.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.otp.setMaximumWidth(280)

        # Make fields expand to fill card width
        for w in (self.identifier, self.password):
            w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("Email/Phone", self.identifier)
        pw_row = QtWidgets.QHBoxLayout(); pw_row.addWidget(self.password); pw_row.addWidget(self.show_pw)
        form.addRow("Password", pw_row)
        form.addRow("", self.info)
        form.addRow("OTP", self.otp)

        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(24,24,24,24)
        col.setSpacing(12)
        col.addWidget(title)
        col.addLayout(form)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(self.primary_btn)
        row.addStretch(1)
        row.addWidget(self.resend_btn)
        col.addLayout(row)
        links = QtWidgets.QHBoxLayout()
        links.addStretch(1)
        links.addWidget(forgot)
        links.addSpacing(24)
        links.addWidget(goto_signup)
        links.addStretch(1)
        col.addLayout(links)

        # Toggle hook
        self.show_pw.clicked.connect(lambda: self._toggle_pw(self.password, self.show_pw))

    def _msg(self, kind: str, title: str, text: str):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.setStyleSheet(
            "QMessageBox{background:white;padding:16px;}"
            "QMessageBox QLabel{min-width:280px;color:#111;font-size:14px;}"
            "QMessageBox QPushButton{min-width:96px;padding:8px 14px;border:1px solid #000;border-radius:6px;background:#fff;color:#000;}"
            "QMessageBox QPushButton:hover{background:#f2f2f2;}"
        )
        if kind == "info":
            box.setIcon(QtWidgets.QMessageBox.Information)
        elif kind == "warn":
            box.setIcon(QtWidgets.QMessageBox.Warning)
        elif kind == "error":
            box.setIcon(QtWidgets.QMessageBox.Critical)
        box.exec()

    def _toggle_pw(self, field: QtWidgets.QLineEdit, btn: QtWidgets.QToolButton):
        if field.echoMode() == QtWidgets.QLineEdit.Password:
            field.setEchoMode(QtWidgets.QLineEdit.Normal)
            btn.setText("Hide")
        else:
            field.setEchoMode(QtWidgets.QLineEdit.Password)
            btn.setText("Show")

    def on_primary_click(self):
        if not self._awaiting_otp:
            self.on_get_otp()
        else:
            self.on_submit_otp()

    def on_get_otp(self):
        ident = self.identifier.text().strip()
        pwd = self.password.text().strip()
        if not ident or not pwd:
            self._msg("warn", "Missing", "Enter email/phone and password.")
            return
        ok, user, msg = authenticate_credentials(ident, pwd)
        if not ok:
            self._msg("warn", "Login failed", msg)
            return
        generate_otp_for(user, purpose="login")
        self._msg("info", "OTP sent", "A 6-digit OTP was sent to your registered email/phone.\n(Shown in console in dev mode.)")
        # switch button to submit mode and start 30s resend timer
        self._awaiting_otp = True
        self.primary_btn.setText("Submit OTP")
        self._start_resend_timer()

    def on_submit_otp(self):
        ident = self.identifier.text().strip()
        code = self.otp.text().strip()
        if not ident or not code:
            self._msg("warn", "Missing", "Enter email/phone and OTP.")
            return
        ok, msg = verify_otp(ident, code, purpose="login")
        if not ok:
            self._msg("warn", "Invalid OTP", msg)
            return
        self.login_success.emit(ident)

    def on_resend_otp(self):
        if not self._awaiting_otp or not self.resend_btn.isEnabled():
            return
        ident = self.identifier.text().strip()
        pwd = self.password.text().strip()
        ok, user, msg = authenticate_credentials(ident, pwd)
        if not ok:
            self._msg("warn", "Login failed", msg)
            return
        generate_otp_for(user, purpose="login")
        self._msg("info", "OTP sent", "A new 6-digit OTP was sent.")
        self._start_resend_timer()

    def _start_resend_timer(self):
        self._resend_remaining = 30
        self.resend_btn.setText(f"Resend OTP ({self._resend_remaining})")
        self.resend_btn.setEnabled(False)
        self._resend_timer.start()

    def _tick_resend(self):
        self._resend_remaining -= 1
        if self._resend_remaining <= 0:
            self._resend_timer.stop()
            self.resend_btn.setText("Resend OTP")
            self.resend_btn.setEnabled(True)
        else:
            self.resend_btn.setText(f"Resend OTP ({self._resend_remaining})")

    def reset(self):
        """Clear all fields and restore initial login state."""
        try:
            self._resend_timer.stop()
        except Exception:
            pass
        self.identifier.clear()
        self.password.clear()
        self.otp.clear()
        self._awaiting_otp = False
        self.primary_btn.setText("Get OTP")
        self.resend_btn.setText("Resend OTP (30)")
        self.resend_btn.setEnabled(False)
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        if hasattr(self, 'show_pw'):
            self.show_pw.setText("Show")

class SignupCard(QtWidgets.QFrame):
    request_login = QtCore.Signal()
    signup_success = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setStyleSheet("""
            QFrame#Card { background:white; border-radius:16px; }
            QLabel { color:#111; }
            .hint { color:#666; font-size:12px; }
            QLineEdit, QComboBox { height:34px; padding:4px 10px; border:1px solid #ddd; border-radius:8px; }
            QPushButton { height:40px; border-radius:8px; background:#111; color:white; }
            QPushButton[flat="true"] { background:transparent; color:#111; text-decoration:underline; }
        """)

        title = QtWidgets.QLabel("Sign up")
        title.setStyleSheet("font-size:20px;font-weight:700;")

        self.first = QtWidgets.QLineEdit();  self.first.setPlaceholderText("First Name")
        self.last  = QtWidgets.QLineEdit();  self.last.setPlaceholderText("Last Name")
        self.biz   = QtWidgets.QLineEdit();  self.biz.setPlaceholderText("Business Name")
        self.email = QtWidgets.QLineEdit();  self.email.setPlaceholderText("Email")

        self.cc    = QtWidgets.QComboBox()
        for cc, name in COUNTRY_CHOICES:
            self.cc.addItem(f"{cc}  {name}", userData=cc)
        self.phone = QtWidgets.QLineEdit();  self.phone.setPlaceholderText("Phone number")

        self.pwd   = QtWidgets.QLineEdit();  self.pwd.setPlaceholderText("Password")
        self.pwd.setEchoMode(QtWidgets.QLineEdit.Password)
        self.pwd2  = QtWidgets.QLineEdit();  self.pwd2.setPlaceholderText("Password Re-Enter")
        self.pwd2.setEchoMode(QtWidgets.QLineEdit.Password)
        # Add show/hide buttons
        self.show_pw = QtWidgets.QToolButton(); self.show_pw.setText("Show"); self.show_pw.setFixedWidth(56)
        self.show_pw2 = QtWidgets.QToolButton(); self.show_pw2.setText("Show"); self.show_pw2.setFixedWidth(56)

        # Make inputs expand with the available width while keeping reasonable minimums
        for w in (self.first, self.last, self.biz, self.email, self.phone, self.pwd, self.pwd2):
            w.setMinimumWidth(280)
            w.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.cc.setMinimumWidth(120)

        # Use a clean, explicit hint string and allow wrapping so it never cuts off
        hint = QtWidgets.QLabel("Password must be at least 8 characters, include at least 1 uppercase and 1 special character.")
        hint.setProperty("class","hint")
        hint.setWordWrap(True)
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)

        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form.addRow("First Name", self.first)
        form.addRow("Last Name", self.last)
        form.addRow("Business Name", self.biz)
        form.addRow("Email", self.email)

        phone_row = QtWidgets.QHBoxLayout()
        phone_row.setSpacing(10)
        phone_row.addWidget(self.cc)
        phone_row.addWidget(self.phone, 1)
        form.addRow("Phone", phone_row)

        pw_row = QtWidgets.QHBoxLayout(); pw_row.addWidget(self.pwd); pw_row.addWidget(self.show_pw)
        form.addRow("Password", pw_row)
        pw2_row = QtWidgets.QHBoxLayout(); pw2_row.addWidget(self.pwd2); pw2_row.addWidget(self.show_pw2)
        form.addRow("Password Re-Enter", pw2_row)
        form.addRow("", hint)

        submit = QtWidgets.QPushButton("Submit")
        submit.setMinimumHeight(40)
        submit.setMinimumWidth(160)
        submit.setMaximumWidth(220)
        goto_login = QtWidgets.QPushButton("Already have an account? Log in")
        goto_login.setFlat(True)

        submit.clicked.connect(self.on_submit)
        goto_login.clicked.connect(self.request_login.emit)

        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(24,24,24,24)
        col.setSpacing(12)
        col.addWidget(title)
        col.addLayout(form)
        col.addWidget(submit, 0, QtCore.Qt.AlignCenter)
        col.addWidget(goto_login, 0, QtCore.Qt.AlignCenter)

        # validators and toggles
        self.phone.setValidator(QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"^\d{0,15}$")))
        self.phone.textChanged.connect(self._on_phone_text)
        self.show_pw.clicked.connect(lambda: self._toggle_pw(self.pwd, self.show_pw))
        self.show_pw2.clicked.connect(lambda: self._toggle_pw(self.pwd2, self.show_pw2))

    def on_submit(self):
        first = self.first.text().strip()
        last  = self.last.text().strip()
        biz   = self.biz.text().strip()
        email = self.email.text().strip()
        cc    = self.cc.currentData()
        phone = self.phone.text().strip()
        pwd   = self.pwd.text()
        pwd2  = self.pwd2.text()

        if not all([first,last,biz,email,cc,phone,pwd,pwd2]):
            self._msg("warn", "Missing", "All fields are mandatory.")
            return
        if pwd != pwd2:
            self._msg("warn", "Password", "Passwords do not match.")
            return

        ok, msg = create_user(first, last, biz, email, cc, phone, pwd)
        if not ok:
            self._msg("warn", "Sign up", msg)
            return
        self._msg("info", "Success", "Account created. Please log in.")
        self.signup_success.emit()

    def reset(self):
        for w in (self.first, self.last, self.biz, self.email, self.phone, self.pwd, self.pwd2):
            w.clear()
        self.pwd.setEchoMode(QtWidgets.QLineEdit.Password)
        self.pwd2.setEchoMode(QtWidgets.QLineEdit.Password)
        self.show_pw.setText("Show"); self.show_pw2.setText("Show")

    def _msg(self, kind: str, title: str, text: str):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        box.setStyleSheet(
            "QMessageBox{background:white;padding:16px;}"
            "QMessageBox QLabel{min-width:280px;color:#111;font-size:14px;}"
            "QMessageBox QPushButton{min-width:96px;padding:8px 14px;border:1px solid #000;border-radius:6px;background:#fff;color:#000;}"
            "QMessageBox QPushButton:hover{background:#f2f2f2;}"
        )
        if kind == "info":
            box.setIcon(QtWidgets.QMessageBox.Information)
        elif kind == "warn":
            box.setIcon(QtWidgets.QMessageBox.Warning)
        elif kind == "error":
            box.setIcon(QtWidgets.QMessageBox.Critical)
        box.exec()

    # helper methods
    def _toggle_pw(self, field: QtWidgets.QLineEdit, btn: QtWidgets.QToolButton):
        if field.echoMode() == QtWidgets.QLineEdit.Password:
            field.setEchoMode(QtWidgets.QLineEdit.Normal)
            btn.setText("Hide")
        else:
            field.setEchoMode(QtWidgets.QLineEdit.Password)
            btn.setText("Show")

    def _on_phone_text(self, s: str):
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits != s:
            pos = self.phone.cursorPosition()
            self.phone.blockSignals(True)
            self.phone.setText(digits)
            self.phone.setCursorPosition(min(pos - (len(s) - len(digits)), len(digits)))
        self.phone.blockSignals(False)




class InventorySheetTab(QtWidgets.QWidget):
    rows_changed = QtCore.Signal()
    def __init__(self):
        super().__init__()
        self._csv_path = None
        self._default_by = ""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12,12,12,12)
        layout.setSpacing(8)

        # Toolbar
        bar = QtWidgets.QHBoxLayout()
        self.path_lbl = QtWidgets.QLabel("")
        self.export_btn = QtWidgets.QPushButton("Export CSV")
        self.reload_btn = QtWidgets.QPushButton("Reload")
        self.del_btn = QtWidgets.QPushButton("Delete")
        self.clear_btn = QtWidgets.QPushButton("Clear All")
        # Filter by item (populated from Summary)
        self.filter_lbl = QtWidgets.QLabel("Filter:")
        self.filter_cb = QtWidgets.QComboBox(); self.filter_cb.addItem("All items")
        bar.addWidget(self.path_lbl)
        bar.addSpacing(12)
        bar.addWidget(self.filter_lbl)
        bar.addWidget(self.filter_cb)
        bar.addStretch(1)
        bar.addWidget(self.reload_btn)
        bar.addWidget(self.export_btn)
        bar.addWidget(self.del_btn)
        bar.addWidget(self.clear_btn)

        # Manual entry form removed by request

        # Table
        # Columns: Date, Time, Action, Item, Quantity, Unit, Location, Note, By
        self.table = QtWidgets.QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Date", "Time", "Action", "Item", "Quantity", "Unit", "Location", "Note", "By"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setStyleSheet("QTableWidget{background:#fff;border:1px solid #e5e7eb;border-radius:8px;}")
        # Better selection + context menu
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        layout.addLayout(bar)
        # no manual form row here
        layout.addWidget(self.table, 1)
        # Optional natural-language command input (moved below the table)
        cmd_row = QtWidgets.QHBoxLayout()
        self.cmd_input = QtWidgets.QLineEdit(); self.cmd_input.setPlaceholderText("Type a command, e.g. 'add 5 apples to pantry'")
        self.cmd_submit = QtWidgets.QPushButton("Submit")
        self.cmd_submit.clicked.connect(self._on_submit_cmd)
        # Pressing Enter submits
        try:
            self.cmd_input.returnPressed.connect(self._on_submit_cmd)
        except Exception:
            pass
        cmd_row.addWidget(self.cmd_input, 1)
        cmd_row.addWidget(self.cmd_submit)
        layout.addLayout(cmd_row)

        self.export_btn.clicked.connect(self.export_csv)
        self.reload_btn.clicked.connect(self.load_csv)
        self.del_btn.clicked.connect(self._delete_selected)
        self.clear_btn.clicked.connect(self._clear_all)
        self.filter_cb.currentIndexChanged.connect(self._apply_filter)
        # Delete key shortcut
        try:
            QtGui.QShortcut(QtGui.QKeySequence.Delete, self.table, activated=self._delete_selected)
        except Exception:
            pass

    def set_default_by(self, name: str):
        self._default_by = (name or "").strip()

    def set_path(self, csv_path: str):
        self._csv_path = csv_path
        self.path_lbl.setText(csv_path or "")

    def add_log(self, row: dict):
        # Validate removals against current stock
        try:
            action = (row.get('action', '') or '').strip().lower()
            item_n = _inv_clean_item(row.get('item', '')).lower()
            unit_n = _inv_normalize_unit(row.get('unit', ''))
            loc_n  = (row.get('location', '') or '').strip().lower()
            qty = row.get('quantity')
            if isinstance(qty, str):
                qty = qty.strip()
                qty = float(qty) if qty else None
            if action in ('remove', 'deduct', 'subtract', 'reduce', 'delete'):
                if qty is None or qty <= 0:
                    QtWidgets.QMessageBox.information(self, "Missing quantity", "Please specify a positive quantity to remove.")
                    return
                available = self._net_available(item_n, unit_n, loc_n)
                if available <= 0:
                    msg = f"No {item_n or 'item'} in stock to remove."
                    if unit_n:
                        msg = f"No {unit_n} of {item_n or 'item'} in stock to remove."
                    if loc_n:
                        msg += f" (Location: {loc_n})"
                    QtWidgets.QMessageBox.information(self, "Not enough stock", msg)
                    return
                if qty > available + 1e-9:
                    disp_avail = f"{available:g} {unit_n} " if unit_n else f"{available:g} "
                    QtWidgets.QMessageBox.information(self, "Not enough stock", f"Only {disp_avail}of {item_n} available. Can't remove {qty:g}.")
                    return
        except Exception:
            # If validation fails unexpectedly, fall back to adding the row
            pass

        ts = (row.get('timestamp','') or '').strip()
        d, t = self._split_timestamp(ts)
        vals = [
            d,
            t,
            row.get('action',''),
            row.get('item',''),
            str(row.get('quantity','')),
            row.get('unit',''),
            row.get('location',''),
            row.get('note',''),
            row.get('by',''),
        ]
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, v in enumerate(vals):
            item = QtWidgets.QTableWidgetItem(v)
            self.table.setItem(r, c, item)
        # autosave
        try:
            self.save_csv()
        except Exception:
            pass
        try:
            self.rows_changed.emit()
        except Exception:
            pass
        self._apply_filter()

    def _net_available(self, item_n: str, unit_n: str, loc_n: str) -> float:
        """Compute current net quantity for a normalized (item, unit, location)."""
        total = 0.0
        try:
            for r in range(self.table.rowCount()):
                item = _inv_clean_item((self.table.item(r, 3).text() if self.table.item(r, 3) else '')).lower()
                unit = _inv_normalize_unit((self.table.item(r, 5).text() if self.table.item(r, 5) else ''))
                loc  = ((self.table.item(r, 6).text() if self.table.item(r, 6) else '')).strip().lower()
                if item != item_n or unit != unit_n or loc != loc_n:
                    continue
                qtxt = self.table.item(r, 4).text() if self.table.item(r, 4) else ''
                try:
                    qval = float(qtxt) if qtxt != '' else None
                except Exception:
                    qval = None
                if qval is None:
                    continue
                act = (self.table.item(r, 2).text() if self.table.item(r, 2) else '').strip().lower()
                if act in ('remove', 'deduct', 'subtract', 'reduce', 'delete'):
                    total -= qval
                else:
                    total += qval
        except Exception:
            return 0.0
        return total

    def _on_submit_cmd(self):
        text = (self.cmd_input.text() or "").strip()
        if not text:
            return
        row = self._parse_inventory_command(text)
        if not row:
            QtWidgets.QMessageBox.information(self, "Not understood", "Couldn't parse that command. Try e.g. 'add 5 apples to pantry'.")
            return
        row['by'] = self._default_by
        self.add_log(row)
        self.cmd_input.clear()
        try:
            self.cmd_input.setFocus()
        except Exception:
            pass

    def _selected_row_indices(self):
        sel = self.table.selectionModel().selectedRows()
        rows = sorted({ix.row() for ix in sel}, reverse=True)
        return rows

    def _delete_selected(self):
        rows = self._selected_row_indices()
        if not rows:
            QtWidgets.QMessageBox.information(self, "Nothing selected", "Select one or more rows to delete.")
            return
        if QtWidgets.QMessageBox.question(self, "Delete", f"Delete {len(rows)} selected row(s)?") != QtWidgets.QMessageBox.Yes:
            return
        for r in rows:
            if 0 <= r < self.table.rowCount():
                self.table.removeRow(r)
        try:
            self.save_csv()
        except Exception:
            pass
        try:
            self.rows_changed.emit()
        except Exception:
            pass

    def _clear_all(self):
        if self.table.rowCount() == 0:
            return
        if QtWidgets.QMessageBox.question(self, "Clear all", "Delete ALL rows from the inventory log?") != QtWidgets.QMessageBox.Yes:
            return
        self.table.setRowCount(0)
        try:
            self.save_csv()
        except Exception:
            pass
        try:
            self.rows_changed.emit()
        except Exception:
            pass

    def _on_table_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        act_del = menu.addAction("Delete selected")
        act_clear = menu.addAction("Clear all")
        if not self._selected_row_indices():
            act_del.setEnabled(False)
        if self.table.rowCount() == 0:
            act_clear.setEnabled(False)
        action = menu.exec(self.table.mapToGlobal(pos))
        if action == act_del:
            self._delete_selected()
        elif action == act_clear:
            self._clear_all()

    def _parse_inventory_command(self, text: str) -> dict | None:
        return parse_inventory_command(text)

    # manual add feature removed

    # --- Filtering and utils ---
    def set_filter_items(self, items):
        """Populate the filter combobox with items from Summary.
        Keeps the current selection if possible."""
        current = self.filter_cb.currentText() if self.filter_cb.count() else "All items"
        seen = set()
        opts = ["All items"]
        for i in items or []:
            if not i:
                continue
            val = str(i)
            if val not in seen:
                seen.add(val)
                opts.append(val)
        self.filter_cb.blockSignals(True)
        self.filter_cb.clear()
        self.filter_cb.addItems(opts)
        # restore selection
        idx = self.filter_cb.findText(current)
        self.filter_cb.setCurrentIndex(idx if idx >= 0 else 0)
        self.filter_cb.blockSignals(False)
        self._apply_filter()

    def _apply_filter(self):
        sel = self.filter_cb.currentText() if self.filter_cb.count() else "All items"
        item_col = 3  # Item column index in table
        for r in range(self.table.rowCount()):
            show = True
            if sel and sel != "All items":
                it = self.table.item(r, item_col)
                val = it.text() if it else ""
                show = (val.strip().lower() == sel.strip().lower())
            self.table.setRowHidden(r, not show)

    def _split_timestamp(self, ts: str) -> tuple[str, str]:
        s = (ts or '').strip()
        if not s:
            return '', ''
        # handle ISO-like 'YYYY-MM-DDTHH:MM:SS' or 'YYYY-MM-DD HH:MM:SS'
        if 'T' in s:
            d, t = s.split('T', 1)
            t = t.split()[0]
            return d, t
        parts = s.split()
        if len(parts) >= 4:
            return ' '.join(parts[:3]), parts[3]
        if len(parts) == 2:
            return parts[0], parts[1]
        return s, ''

    def load_csv(self):
        path = self._csv_path
        if not path or not os.path.exists(path):
            return
        self.table.setRowCount(0)
        try:
            with open(path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                hdr0 = (header[0].strip().lower() if header else '')
                for vals in reader:
                    if hdr0 == 'timestamp' or len(vals) == 8:
                        # Old format: [timestamp, action, item, quantity, unit, location, note, by]
                        vals = (vals + [""]*8)[:8]
                        d, t = self._split_timestamp(vals[0])
                        row_vals = [d, t] + vals[1:]
                    else:
                        # New format: [date, time, action, item, quantity, unit, location, note, by]
                        vals = (vals + [""]*9)[:9]
                        row_vals = vals
                    r = self.table.rowCount()
                    self.table.insertRow(r)
                    for c, v in enumerate(row_vals):
                        self.table.setItem(r, c, QtWidgets.QTableWidgetItem(v))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to load CSV: {e}")
        try:
            self.rows_changed.emit()
        except Exception:
            pass
        self._apply_filter()

    def get_all_rows(self) -> list:
        rows = []
        for r in range(self.table.rowCount()):
            def cell(c):
                it = self.table.item(r, c)
                return it.text() if it else ""
            qtxt = cell(4)
            try:
                qval = float(qtxt) if qtxt != "" else None
            except Exception:
                qval = None
            rows.append({
                'timestamp': (cell(0) + ' ' + cell(1)).strip(),
                'action': cell(2),
                'item': cell(3),
                'quantity': qval,
                'unit': cell(5),
                'location': cell(6),
                'note': cell(7),
                'by': cell(8),
            })
        return rows

    def save_csv(self):
        path = self._csv_path
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["date","time","action","item","quantity","unit","location","note","by"])
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        it = self.table.item(r, c)
                        row.append(it.text() if it else "")
                    writer.writerow(row)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save CSV: {e}")

    def export_csv(self):
        """Prompt the user for a location and export the current table there."""
        default = self._csv_path or os.path.join(os.getcwd(), 'inventory.csv')
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export inventory CSV", default, "CSV Files (*.csv)")
        if not fn:
            return
        try:
            # Write to chosen path
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            with open(fn, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["date","time","action","item","quantity","unit","location","note","by"])
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        it = self.table.item(r, c)
                        row.append(it.text() if it else "")
                    writer.writerow(row)
            QtWidgets.QMessageBox.information(self, "Exported", f"Saved to:\n{fn}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to export CSV: {e}")


class SummarySheetTab(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self._csv_path = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12,12,12,12)
        layout.setSpacing(8)

        # Toolbar
        bar = QtWidgets.QHBoxLayout()
        self.path_lbl = QtWidgets.QLabel("")
        self.recompute_btn = QtWidgets.QPushButton("Recompute")
        self.export_btn = QtWidgets.QPushButton("Export CSV")
        bar.addWidget(self.path_lbl)
        bar.addStretch(1)
        bar.addWidget(self.recompute_btn)
        bar.addWidget(self.export_btn)

        # Table
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Item", "Net Quantity", "Unit", "Location"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.setStyleSheet("QTableWidget{background:#fff;border:1px solid #e5e7eb;border-radius:8px;}")

        layout.addLayout(bar)
        layout.addWidget(self.table, 1)

        self.recompute_btn.clicked.connect(self._request_recompute)
        self.export_btn.clicked.connect(self.export_csv)

        self._last_rows = []
        self._recompute_callback = None

    def set_path(self, csv_path: str):
        self._csv_path = csv_path
        self.path_lbl.setText(csv_path or "")

    def set_recompute_callback(self, cb):
        """Provide a callable to fetch current inventory rows when user clicks Recompute."""
        self._recompute_callback = cb

    def _request_recompute(self):
        if callable(self._recompute_callback):
            try:
                rows = self._recompute_callback()
                self.update_from_rows(rows or [])
            except Exception:
                pass

    def update_from_rows(self, rows: list):
        self._last_rows = rows or []
        # Aggregate by normalized (item, unit, location)
        from collections import defaultdict
        totals = defaultdict(float)
        for r in self._last_rows:
            try:
                item_raw = (r.get('item','') or '').strip()
                unit_raw = (r.get('unit','') or '').strip()
                loc_raw  = (r.get('location','') or '').strip()
                qty = r.get('quantity')
                if qty in (None, ""):
                    continue
                q = float(qty)
                act = (r.get('action','') or '').strip().lower()
                if act in ('remove', 'deduct', 'subtract', 'reduce', 'delete'):
                    q = -q
                # Normalize item and unit for grouping
                item = _inv_clean_item(item_raw).lower()
                unit = _inv_normalize_unit(unit_raw)
                loc = loc_raw.lower()
                key = (item, unit, loc)
                totals[key] += q
            except Exception:
                continue
        # Populate table
        self.table.setRowCount(0)
        for (item, unit, loc), net in sorted(totals.items(), key=lambda kv: (kv[0][0], kv[0][2], kv[0][1])):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(item))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(str(net)))
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(unit))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(loc))
    
    def get_items(self) -> list[str]:
        items = []
        seen = set()
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            val = it.text() if it else ""
            if val and val not in seen:
                seen.add(val); items.append(val)
        return items

    def save_csv(self):
        path = self._csv_path
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["item","net_quantity","unit","location"])
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        it = self.table.item(r, c)
                        row.append(it.text() if it else "")
                    writer.writerow(row)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save CSV: {e}")

    def export_csv(self):
        """Prompt the user for a location and export the summary there."""
        default = self._csv_path or os.path.join(os.getcwd(), 'summary.csv')
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export summary CSV", default, "CSV Files (*.csv)")
        if not fn:
            return
        try:
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            with open(fn, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["item","net_quantity","unit","location"])
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        it = self.table.item(r, c)
                        row.append(it.text() if it else "")
                    writer.writerow(row)
            QtWidgets.QMessageBox.information(self, "Exported", f"Saved to:\n{fn}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to export CSV: {e}")

class HomeView(QtWidgets.QWidget):
    request_logout = QtCore.Signal()
    request_setup = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._ident = ""
        self._user = None

        # Root layout: sidebar + main
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)

        # Sidebar with three tabs
        sidebar = QtWidgets.QFrame(); sidebar.setFixedWidth(140)
        sidebar.setStyleSheet("QFrame{background:#fafafa;border-right:1px solid #e5e7eb;}")
        s = QtWidgets.QVBoxLayout(sidebar)
        s.setContentsMargins(10,12,10,12); s.setSpacing(8)
        # Sidebar avatar (logo) - big circular
        self.side_avatar = QtWidgets.QPushButton()
        self.side_avatar.setFixedSize(72,72)
        self.side_avatar.setFlat(True)
        self.side_avatar.setFocusPolicy(QtCore.Qt.NoFocus)
        self.side_avatar.setStyleSheet("QPushButton{border-radius:36px;border:2px solid #000;background:#fff;padding:0;}")
        self.side_avatar.setCursor(QtCore.Qt.PointingHandCursor)
        self.side_avatar.clicked.connect(self._open_profile)
        s.addWidget(self.side_avatar, 0, QtCore.Qt.AlignLeft)
        s.addSpacing(12)
        self.btn_inv = QtWidgets.QPushButton("Inventory sheet")
        self.btn_summary = QtWidgets.QPushButton("Summary")
        for b in (self.btn_inv, self.btn_summary):
            b.setCheckable(True); b.setStyleSheet("QPushButton{padding:8px;border:1px solid #e5e7eb;border-radius:8px;text-align:left;} QPushButton:checked{background:#111;color:#fff;border-color:#111;}")
        self.btn_inv.setChecked(True) # Set Inventory as default checked
        # center the buttons vertically (after avatar)
        s.addStretch(1)
        s.addWidget(self.btn_inv)
        s.addWidget(self.btn_summary)
        s.addStretch(2)

        # Main area with top bar and content stack
        main = QtWidgets.QWidget(); m = QtWidgets.QVBoxLayout(main)
        m.setContentsMargins(16,12,16,16); m.setSpacing(12)

        # Top bar (like a header bar): avatar + big business name (centered)
        topbar = QtWidgets.QFrame()
        topbar.setStyleSheet("QFrame{background:#fafafa;border-bottom:1px solid #e5e7eb;}")
        topbar.setFixedHeight(64)
        top = QtWidgets.QHBoxLayout(topbar); top.setContentsMargins(0,0,0,0); top.setSpacing(0)
        # Business name (no hover edit)
        self.name_lbl = QtWidgets.QLabel("Business Name")
        self.name_lbl.setObjectName("NameLbl")
        # Ensure fully transparent background (no white patch)
        self.name_lbl.setAutoFillBackground(False)
        self.name_lbl.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        pal = self.name_lbl.palette(); pal.setColor(self.name_lbl.backgroundRole(), QtCore.Qt.transparent); self.name_lbl.setPalette(pal)
        self.name_lbl.setStyleSheet("#NameLbl{font-size:25px;font-weight:800;color:#111;background:transparent;border:0;margin:0;padding:0;}")
        self.name_lbl.setContentsMargins(0,0,0,0)
        self.name_container = QtWidgets.QWidget()
        self.name_container.setAutoFillBackground(False)
        self.name_container.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        name_row = QtWidgets.QHBoxLayout(self.name_container)
        self.name_container.setStyleSheet("background:transparent;border:0;margin:0;padding:0;")
        name_row.setContentsMargins(0,0,0,0)
        name_row.setSpacing(0)
        name_row.addWidget(self.name_lbl)
        name_row.addStretch(1)
        # Center the title in the top bar (no logout here)
        center_box = QtWidgets.QWidget();
        center_box.setAutoFillBackground(False)
        center_box.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        center_box.setStyleSheet("background:transparent;border:0;margin:0;padding:0;")
        cb = QtWidgets.QHBoxLayout(center_box)
        cb.setContentsMargins(0,0,0,0)
        cb.setSpacing(0)
        cb.addStretch(1)
        cb.addWidget(self.name_container, 0, QtCore.Qt.AlignCenter)
        cb.addStretch(1)
        top.addWidget(center_box, 1)
        # removed logout button from top bar

        # Content stack
        self.pages = QtWidgets.QStackedWidget()
        self.page_inv = InventorySheetTab()
        self.page_summary = SummarySheetTab()
        
        # keep summary in sync with inventory rows
        self.page_inv.rows_changed.connect(self._refresh_summary)
        self.pages.addWidget(self.page_inv)
        self.pages.addWidget(self.page_summary)

        m.addWidget(topbar)
        m.addWidget(self.pages)

        root.addWidget(sidebar)
        root.addWidget(main, 1)

        self.btn_inv.clicked.connect(lambda: self._set_page(0))
        self.btn_summary.clicked.connect(lambda: self._set_page(1))
        # avatar now lives in sidebar

    def _set_page(self, idx: int):
        self.btn_inv.setChecked(idx==0)
        self.btn_summary.setChecked(idx==1)
        self.pages.setCurrentIndex(idx)

    def set_identity(self, ident: str):
        self._ident = ident
        # fetch user to display business name
        try:
            self._user = find_user_by_email_or_phone(ident)
        except Exception:
            self._user = None
        if self._user and getattr(self._user, 'business_name', None):
            bn = self._user.business_name
        else:
            bn = "Business Name"
        self.name_lbl.setText(bn)
        self._load_avatar()
        # Sync assistant-tab label and page with stored assistant name
        
        # Wire inventory CSV storage and load existing
        try:
            inv_path = self._inventory_csv_path()
            sum_path = self._summary_csv_path()
            self.page_inv.set_path(inv_path)
            self.page_inv.load_csv()
            self.page_summary.set_path(sum_path)
            # allow recompute button to pull fresh rows from inventory table
            self.page_summary.set_recompute_callback(self.page_inv.get_all_rows)
            # initial summary compute
            self._refresh_summary()
        except Exception:
            pass

        

    def _current_user_name(self) -> str:
        if not self._user:
            return self._ident or "there"
        parts = []
        for attr in ("first_name", "last_name"):
            val = getattr(self._user, attr, "")
            if val:
                parts.append(str(val).strip())
        name = " ".join(p for p in parts if p).strip()
        return name or (self._ident or "there")

    def _profile_dir(self) -> str:
        base = os.path.abspath(os.path.join(os.getcwd(), 'app', 'assets', 'profiles'))
        os.makedirs(base, exist_ok=True)
        return base

    def _avatar_path(self) -> str:
        uid = getattr(self._user, 'id', None)
        if uid is None:
            uid = "default"
        return os.path.join(self._profile_dir(), f"user_{uid}.png")

    def _inventory_csv_path(self) -> str:
        uid = getattr(self._user, 'id', None) or "default"
        folder = os.path.join(self._profile_dir(), "inventory")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"user_{uid}_inventory.csv")

    def _summary_csv_path(self) -> str:
        uid = getattr(self._user, 'id', None) or "default"
        folder = os.path.join(self._profile_dir(), "inventory")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"user_{uid}_summary.csv")

    def _load_avatar(self):
        path = self._avatar_path()
        if os.path.exists(path):
            base = QtGui.QPixmap(path)
        else:
            base = QtGui.QPixmap(72,72); base.fill(QtGui.QColor('#f3f4f6'))
        pm = self._circle_pixmap(base, 72)
        self.side_avatar.setIcon(QtGui.QIcon(pm))
        self.side_avatar.setIconSize(QtCore.QSize(72,72))

    def _refresh_summary(self):
        try:
            rows = self.page_inv.get_all_rows()
            self.page_summary.update_from_rows(rows)
            try:
                self.page_inv.set_filter_items(self.page_summary.get_items())
            except Exception:
                pass
        except Exception:
            pass

    def _change_avatar(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose profile image", "", "Images (*.png *.jpg *.jpeg)")
        if not fn:
            return
        try:
            shutil.copyfile(fn, self._avatar_path())
            self._load_avatar()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save image: {e}")

    def _open_profile(self):
        self._ensure_profile_panel()
        self._populate_profile_panel()
        self._slide_in_profile()

    # --- Profile side panel (drawer) --------------------------------------
    def _ensure_profile_panel(self):
        if hasattr(self, "_profile_drawer"):
            return
        panel = QtWidgets.QFrame(self)
        panel.setObjectName("ProfileDrawer")
        panel.setStyleSheet("#ProfileDrawer{background:#ffffff;border-right:1px solid #e5e7eb;}")
        panel.setFixedWidth(360)

        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(16,16,16,16)
        lay.setSpacing(12)

        hdr = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Profile")
        title.setStyleSheet("font-size:18px;font-weight:700;")
        close_btn = QtWidgets.QToolButton(); close_btn.setText('Close'); close_btn.clicked.connect(self._slide_out_profile)
        hdr.addWidget(title); hdr.addStretch(1); hdr.addWidget(close_btn)

        # Avatar preview + button
        self._drawer_avatar = QtWidgets.QPushButton()
        self._drawer_avatar.setFixedSize(120,120)
        self._drawer_avatar.setFlat(True)
        self._drawer_avatar.setStyleSheet("QPushButton{border-radius:60px;border:2px solid #000;background:#fff;}")

        change_photo = QtWidgets.QPushButton("Change photo")
        change_photo.clicked.connect(self._drawer_change_photo)

        # Business + assistant names
        self._bn_edit = QtWidgets.QLineEdit(); self._bn_edit.setPlaceholderText("Business Name")
        save_btn = QtWidgets.QPushButton("Save")
        logout_btn = QtWidgets.QPushButton("Log out")
        logout_btn.clicked.connect(self.request_logout.emit)
        save_btn.clicked.connect(self._drawer_save)

        lay.addLayout(hdr)
        lay.addWidget(self._drawer_avatar, 0, QtCore.Qt.AlignHCenter)
        lay.addWidget(change_photo, 0, QtCore.Qt.AlignLeft)
        lay.addSpacing(4)
        form = QtWidgets.QFormLayout(); form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.addRow("Business:", self._bn_edit)
        lay.addLayout(form)
        lay.addStretch(1)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(logout_btn)
        bottom.addStretch(1)
        bottom.addWidget(save_btn)
        lay.addLayout(bottom)
        self._profile_drawer = panel
        self._drawer_anim = QtCore.QPropertyAnimation(panel, b"geometry", self)
        self._drawer_anim.setDuration(220)
        self._drawer_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        # Enable click/double-click behavior on the drawer avatar
        try:
            self._drawer_avatar.installEventFilter(self)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_profile_drawer'):
            h = self.height()
            w = self._profile_drawer.width()
            if not self._profile_drawer.isVisible():
                self._profile_drawer.setGeometry(-w, 0, w, h)
            else:
                g = self._profile_drawer.geometry()
                self._profile_drawer.setGeometry(g.x(), 0, w, h)

    def _populate_profile_panel(self):
        # avatar
        path = self._avatar_path()
        if os.path.exists(path):
            base = QtGui.QPixmap(path)
        else:
            base = QtGui.QPixmap(110,110); base.fill(QtGui.QColor('#f3f4f6'))
        pm = self._circle_pixmap(base, 110)
        self._drawer_avatar.setIcon(QtGui.QIcon(pm)); self._drawer_avatar.setIconSize(QtCore.QSize(110,110))
        # fields
        # Only set the business name
        current_bn = None
        try:
            if self._user and getattr(self._user, 'business_name', None):
                current_bn = self._user.business_name
        except Exception:
            current_bn = None
        if not current_bn:
            # Fallback to label text
            lbl = (self.name_lbl.text() or "").strip()
            current_bn = lbl or "Business Name"
        self._bn_edit.setText(current_bn)

    def _slide_in_profile(self):
        # ensure no lingering 'finished->hide' from slide-out
        try:
            self._drawer_anim.finished.disconnect(self._profile_drawer.hide)
        except Exception:
            pass
        self._profile_drawer.show()
        w = self._profile_drawer.width(); h = self.height()
        self._profile_drawer.setGeometry(-w, 0, w, h)
        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(QtCore.QRect(-w, 0, w, h))
        self._drawer_anim.setEndValue(QtCore.QRect(0, 0, w, h))
        self._drawer_anim.start()

    def _slide_out_profile(self):
        if not hasattr(self, '_profile_drawer'): return
        w = self._profile_drawer.width(); h = self.height()
        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(QtCore.QRect(0, 0, w, h))
        self._drawer_anim.setEndValue(QtCore.QRect(-w, 0, w, h))
        # avoid duplicate connections
        try:
            self._drawer_anim.finished.disconnect(self._profile_drawer.hide)
        except Exception:
            pass
        self._drawer_anim.finished.connect(self._profile_drawer.hide)
        self._drawer_anim.start()

    def _drawer_change_photo(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose profile image", "", "Images (*.png *.jpg *.jpeg)")
        if not fn: return
        try:
            shutil.copyfile(fn, self._avatar_path())
            self._load_avatar(); self._populate_profile_panel()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to save image: {e}")

    def _drawer_save(self):
        # save business name
        new_bn = self._bn_edit.text().strip() or "Business Name"
        self.name_lbl.setText(new_bn)
        if self._ident:
            update_business_name(self._ident, new_bn)
        self._slide_out_profile()

    def _profile_json_path(self) -> str:
        uid = getattr(self._user, 'id', None) or "default"
        return os.path.join(self._profile_dir(), f"user_{uid}.json")

    # --- Avatar helpers and interactions ---
    def _circle_pixmap(self, source: QtGui.QPixmap, diameter: int) -> QtGui.QPixmap:
        """Return a circularly cropped pixmap of the given diameter."""
        if source.isNull():
            source = QtGui.QPixmap(diameter, diameter)
            source.fill(QtGui.QColor('#f3f4f6'))
        sp = source.scaled(diameter, diameter, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
        result = QtGui.QPixmap(diameter, diameter)
        result.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(result)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        path = QtGui.QPainterPath()
        path.addEllipse(0, 0, diameter, diameter)
        painter.setClipPath(path)
        x = (diameter - sp.width()) // 2
        y = (diameter - sp.height()) // 2
        painter.drawPixmap(x, y, sp)
        painter.end()
        return result

    def _preview_current_avatar(self):
        """Show an enlarged, circular preview of the current avatar image."""
        path = self._avatar_path()
        if os.path.exists(path):
            base = QtGui.QPixmap(path)
        else:
            base = QtGui.QPixmap(360, 360)
            base.fill(QtGui.QColor('#f3f4f6'))
        pm = self._circle_pixmap(base, 360)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Profile Photo")
        dlg.setModal(True)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.setContentsMargins(16,16,16,16)
        lay.setSpacing(12)
        lbl = QtWidgets.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lbl.setPixmap(pm)
        lay.addWidget(lbl)
        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, 0, QtCore.Qt.AlignCenter)
        dlg.resize(420, 440)
        dlg.exec()

    def _edit_business_name(self):
        # Only edit the business name
        existing_lbl = (self.name_lbl.text() or "").strip()
        text, ok = QtWidgets.QInputDialog.getText(self, "Business Name", "Enter business name:", text=existing_lbl)
        if not ok:
            return
        bn = text.strip() or "Business Name"
        self.name_lbl.setText(bn)
        if self._ident:
            ok2, msg = update_business_name(self._ident, bn)
            if not ok2:
                QtWidgets.QMessageBox.information(self, "Note", msg)

    # show edit icon on hover + handle avatar click/double-click in drawer
    def eventFilter(self, obj, event):
        try:
            if obj in (self.name_container, self.name_lbl):
                if event.type() == QtCore.QEvent.Enter:
                    if hasattr(self, 'edit_name'):
                        self.edit_name.setVisible(True)
                elif event.type() == QtCore.QEvent.Leave:
                    if hasattr(self, 'edit_name'):
                        QtCore.QTimer.singleShot(150, lambda: self.edit_name.setVisible(False))
                return False
            # Drawer avatar: single click -> preview; double click -> upload
            if hasattr(self, '_drawer_avatar') and obj is self._drawer_avatar:
                if event.type() == QtCore.QEvent.MouseButtonDblClick:
                    self._drawer_change_photo()
                    return True
                elif event.type() == QtCore.QEvent.MouseButtonPress:
                    if isinstance(event, QtGui.QMouseEvent) and event.button() == QtCore.Qt.LeftButton:
                        self._preview_current_avatar()
                        return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


class ForgotPasswordView(QtWidgets.QWidget):
    request_login = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._awaiting = False
        self._ident = ""

        title = QtWidgets.QLabel("Reset password")
        title.setStyleSheet("font-size:20px;font-weight:700;")

        self.ident = QtWidgets.QLineEdit(); self.ident.setPlaceholderText("Email or phone")
        self.otp = QtWidgets.QLineEdit(); self.otp.setPlaceholderText("6-digit OTP"); self.otp.setMaxLength(6); self.otp.setAlignment(QtCore.Qt.AlignCenter)
        self.new1 = QtWidgets.QLineEdit(); self.new1.setPlaceholderText("New password"); self.new1.setEchoMode(QtWidgets.QLineEdit.Password)
        self.new2 = QtWidgets.QLineEdit(); self.new2.setPlaceholderText("Re-enter password"); self.new2.setEchoMode(QtWidgets.QLineEdit.Password)
        self.tgl1 = QtWidgets.QToolButton(); self.tgl1.setText("Show"); self.tgl1.setFixedWidth(56)
        self.tgl2 = QtWidgets.QToolButton(); self.tgl2.setText("Show"); self.tgl2.setFixedWidth(56)

        self.primary = QtWidgets.QPushButton("Send OTP")
        back = QtWidgets.QPushButton("Back to login")

        form = QtWidgets.QFormLayout()
        form.addRow("Email/Phone", self.ident)
        form.addRow("OTP", self.otp)
        row1 = QtWidgets.QHBoxLayout(); row1.addWidget(self.new1); row1.addWidget(self.tgl1)
        row2 = QtWidgets.QHBoxLayout(); row2.addWidget(self.new2); row2.addWidget(self.tgl2)
        form.addRow("New password", row1)
        form.addRow("Confirm password", row2)

        col = QtWidgets.QVBoxLayout(self)
        col.setContentsMargins(24,24,24,24)
        col.setSpacing(10)
        col.addWidget(title)
        col.addLayout(form)
        actions = QtWidgets.QHBoxLayout(); actions.addWidget(self.primary); actions.addStretch(1); actions.addWidget(back)
        col.addLayout(actions)

        self._sync_state()

        # signals
        self.primary.clicked.connect(self.on_primary)
        back.clicked.connect(self.request_login.emit)
        self.tgl1.clicked.connect(lambda: self._toggle(self.new1, self.tgl1))
        self.tgl2.clicked.connect(lambda: self._toggle(self.new2, self.tgl2))

    def set_identifier(self, ident: str):
        if ident:
            self.ident.setText(ident)

    def _toggle(self, field: QtWidgets.QLineEdit, btn: QtWidgets.QToolButton):
        if field.echoMode() == QtWidgets.QLineEdit.Password:
            field.setEchoMode(QtWidgets.QLineEdit.Normal)
            btn.setText("Hide")
        else:
            field.setEchoMode(QtWidgets.QLineEdit.Password)
            btn.setText("Show")

    def _msg(self, kind: str, title: str, text: str):
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title); box.setText(text); box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        if kind == "info": box.setIcon(QtWidgets.QMessageBox.Information)
        elif kind == "warn": box.setIcon(QtWidgets.QMessageBox.Warning)
        else: box.setIcon(QtWidgets.QMessageBox.Critical)
        box.exec()

    def _sync_state(self):
        awaiting = self._awaiting
        self.otp.setEnabled(awaiting)
        for w in (self.new1, self.new2, self.tgl1, self.tgl2):
            w.setEnabled(awaiting)
        self.primary.setText("Reset Password" if awaiting else "Send OTP")
    
    def reset(self):
        self._awaiting = False
        self.ident.clear(); self.otp.clear(); self.new1.clear(); self.new2.clear()
        self.new1.setEchoMode(QtWidgets.QLineEdit.Password)
        self.new2.setEchoMode(QtWidgets.QLineEdit.Password)
        self.tgl1.setText("Show"); self.tgl2.setText("Show")
        self._sync_state()

    def on_primary(self):
        if not self._awaiting:
            ident = self.ident.text().strip()
            if not ident:
                self._msg("warn", "Missing", "Enter your email or phone.")
                return
            user = find_user_by_email_or_phone(ident)
            if not user:
                self._msg("warn", "Not found", "No account found for this identifier.")
                return
            generate_otp_for(user, purpose="reset")
            self._msg("info", "OTP sent", "We sent a 6-digit code for password reset.")
            self._ident = ident
            self._awaiting = True
            self._sync_state()
        else:
            code = self.otp.text().strip()
            n1 = self.new1.text(); n2 = self.new2.text()
            if not code or not n1 or not n2:
                self._msg("warn", "Missing", "Enter OTP and your new password twice.")
                return
            if n1 != n2:
                self._msg("warn", "Mismatch", "Passwords do not match.")
                return
            ok, msg = reset_password(self._ident, code, n1)
            if not ok:
                self._msg("warn", "Reset failed", msg)
                return
            self._msg("info", "Done", "Password updated. Please log in.")
            self.request_login.emit()

class Shell(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invyntra" if settings.ENV.lower()=="prod" else f"Invyntra ({settings.ENV.upper()})")
        self.setMinimumSize(960, 560)
        self.setStyleSheet("QMainWindow{background:#f5f5f5;}")

        # Root stack: Welcome page -> Auth page (login/signup)
        self.stacked = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stacked)

        # Build Welcome page
        self.welcome = QtWidgets.QWidget()
        wlay = QtWidgets.QVBoxLayout(self.welcome)
        wlay.setContentsMargins(32, 48, 32, 48)
        wlay.setSpacing(10)
        # No logo on welcome page per request
        title = QtWidgets.QLabel("Welcome to Invyntra")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size:36px;font-weight:800;color:#111;")
        caption = QtWidgets.QLabel("One stop vocal solution")
        caption.setAlignment(QtCore.Qt.AlignCenter)
        caption.setStyleSheet("font-size:14px;color:#444;font-style:italic;margin-top:2px;")
        btn_row = QtWidgets.QHBoxLayout()
        signup_btn = QtWidgets.QPushButton("Sign up")
        login_btn = QtWidgets.QPushButton("Log in")
        for b in (signup_btn, login_btn):
            b.setFlat(True)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.setStyleSheet("background:transparent;border:0;color:#1976d2;text-decoration: underline;font-size:14px;")
        btn_row.addStretch(1); btn_row.addWidget(signup_btn); btn_row.addSpacing(24); btn_row.addWidget(login_btn); btn_row.addStretch(1)
        wlay.addStretch(2)
        wlay.addWidget(title)
        wlay.addWidget(caption)
        wlay.addSpacing(2)
        wlay.addLayout(btn_row)
        wlay.addStretch(3)

        # Build Auth page container (back arrow + side-by-side login/signup)
        self.auth_page = QtWidgets.QWidget()
        self.vbox = QtWidgets.QVBoxLayout(self.auth_page); self.vbox.setContentsMargins(32,32,32,32); self.vbox.setSpacing(16)
        # Top bar with back arrow
        topbar = QtWidgets.QHBoxLayout()
        back = QtWidgets.QToolButton(); back.setText("\u2190"); back.setToolTip("Back")
        back.setStyleSheet("font-size:18px; padding:2px 6px; border:0; color:#111;")
        back.clicked.connect(self.goto_welcome)
        topbar.addWidget(back, 0, QtCore.Qt.AlignLeft)
        topbar.addStretch(1)
        self.vbox.addLayout(topbar)
        # Row with cards
        self.row = QtWidgets.QHBoxLayout(); self.row.setSpacing(24)

        # Left: Login card; Right: Signup card (like Netflix)
        self.login = LoginCard()
        self.signup = SignupCard()
        self.forgot = ForgotPasswordView()
        # Let cards expand to utilize full width
        self.login.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.signup.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        # vertical divider
        self.spacer = QtWidgets.QFrame(); self.spacer.setFrameShape(QtWidgets.QFrame.VLine); self.spacer.setStyleSheet("color:#eaeaea;")

        # Index layout: 0=left stretch, 1=login, 2=spacer, 3=signup, 4=right stretch
        self.row.addStretch(1)
        self.row.addWidget(self.login, 1)
        self.row.addWidget(self.spacer)
        self.row.addWidget(self.signup, 1)
        self.row.addStretch(1)
        self.vbox.addLayout(self.row)

        # Home page
        self.home = HomeView()

        # Assemble stack
        self.stacked.addWidget(self.welcome)
        self.stacked.addWidget(self.auth_page)
        self.stacked.addWidget(self.home)
        self.stacked.addWidget(self.forgot)
        self.stacked.setCurrentWidget(self.welcome)

        # Wire actions
        signup_btn.clicked.connect(self.goto_signup)
        login_btn.clicked.connect(self.goto_login)

        self.login.request_signup.connect(self.goto_signup)
        self.login.request_forgot.connect(self._goto_forgot)
        self.login.login_success.connect(self._enter_home)

        self.signup.request_login.connect(self.goto_login)
        self.signup.signup_success.connect(self.goto_login)

        self.home.request_logout.connect(self.goto_welcome)
        self.home.request_setup.connect(self._start_setup)
        self.forgot.request_login.connect(self.goto_login)

    def _show_both(self):
        self._configure_layout_mode("both")

    def _show_signup_only(self):
        self._configure_layout_mode("signup")

    def _show_login_only(self):
        self._configure_layout_mode("login")

    def goto_signup(self):
        # Clear other auth forms when switching pages
        if hasattr(self, 'login') and hasattr(self.login, 'reset'):
            self.login.reset()
        if hasattr(self, 'forgot') and hasattr(self.forgot, 'reset'):
            self.forgot.reset()
        self.stacked.setCurrentWidget(self.auth_page)
        self._show_signup_only()

    def goto_login(self):
        # Clear other auth forms when switching pages
        if hasattr(self, 'signup') and hasattr(self.signup, 'reset'):
            self.signup.reset()
        if hasattr(self, 'forgot') and hasattr(self.forgot, 'reset'):
            self.forgot.reset()
        self.stacked.setCurrentWidget(self.auth_page)
        self._show_login_only()

    def goto_welcome(self):
        # clear sensitive data when exiting auth pages (privacy)
        if hasattr(self, 'login') and hasattr(self.login, 'reset'):
            self.login.reset()
        if hasattr(self, 'signup') and hasattr(self.signup, 'reset'):
            self.signup.reset()
        if hasattr(self, 'forgot') and hasattr(self.forgot, 'reset'):
            self.forgot.reset()
        self.stacked.setCurrentWidget(self.welcome)

    def _configure_layout_mode(self, mode: str):
        # Reset stretches
        for i in range(self.row.count()):
            try:
                self.row.setStretch(i, 0)
            except Exception:
                pass
        if mode == "both":
            self.login.show(); self.signup.show(); self.spacer.show()
            self.vbox.setContentsMargins(32,32,32,32)
            # side stretches
            self.row.setStretch(0, 1)
            self.row.setStretch(1, 1)  # login
            self.row.setStretch(3, 1)  # signup
            self.row.setStretch(4, 1)
        elif mode == "signup":
            self.login.hide(); self.signup.show(); self.spacer.hide()
            self.vbox.setContentsMargins(16,24,16,24)
            # let signup take full width
            self.row.setStretch(3, 1)
        elif mode == "login":
            self.signup.hide(); self.login.show(); self.spacer.hide()
            self.vbox.setContentsMargins(16,24,16,24)
            # let login take full width
            self.row.setStretch(1, 1)

    def _enter_home(self, ident: str):
        # Clear auth forms after successful login
        if hasattr(self, 'login') and hasattr(self.login, 'reset'):
            self.login.reset()
        if hasattr(self, 'signup') and hasattr(self.signup, 'reset'):
            self.signup.reset()
        if hasattr(self, 'forgot') and hasattr(self.forgot, 'reset'):
            self.forgot.reset()
        self.home.set_identity(ident)
        self.stacked.setCurrentWidget(self.home)

    def _start_setup(self):
        QtWidgets.QMessageBox.information(self, "Inventory Setup", "Setup wizard coming next.")

    def _goto_forgot(self, ident: str):
        self.forgot.set_identifier(ident)
        self.stacked.setCurrentWidget(self.forgot)

def main():
    app = QtWidgets.QApplication(sys.argv)
    w = Shell()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
