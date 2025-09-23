"""PySide6 UI: Netflix-like login + signup with OTP second factor.

Black & white theme. Signup captures First/Last/Business/Email/Country Code + Phone/Password.
Login accepts email or phone + password, then sends an OTP to SMS + Email (printed in dev).
"""

import sys, random, string, datetime, re, os
from PySide6 import QtCore, QtWidgets, QtGui
from app.core.config import settings
from app.db import SessionLocal
from app.models import User
from app.security import hash_password, verify_password


# In-memory OTPs keyed by user_id
_otp_store = {}  # {user_id: (otp_code, expires_at)}


def _gen_otp():
    return "".join(random.choices(string.digits, k=6))


def _set_otp(user_id: int) -> str:
    code = _gen_otp()
    _otp_store[user_id] = (code, datetime.datetime.utcnow() + datetime.timedelta(minutes=10))
    return code


def _verify_otp(user_id: int, code: str) -> bool:
    if user_id not in _otp_store:
        return False
    saved, exp = _otp_store[user_id]
    if datetime.datetime.utcnow() > exp:
        del _otp_store[user_id]
        return False
    ok = (saved == code.strip())
    if ok:
        del _otp_store[user_id]
    return ok


def _send_otp_sms(phone_full: str, code: str):
    print(f"[DEV] SMS OTP to {phone_full}: {code}")


def _send_otp_email(email: str, code: str):
    print(f"[DEV] Email OTP to {email}: {code}")


class WelcomePage(QtWidgets.QWidget):
    go_login = QtCore.Signal()
    go_signup = QtCore.Signal()

    def __init__(self):
        super().__init__()
        # Optional logo above app name
        logo_label = QtWidgets.QLabel()
        logo_label.setAlignment(QtCore.Qt.AlignCenter)
        env_logo = os.getenv("INVYNTRA_LOGO")
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        logo_candidates = ([env_logo] if env_logo else []) + [
            os.path.join(project_root, "app", "assets", "welcome_logo.png"),
            os.path.join(os.path.dirname(__file__), "assets", "invyntra_logo.png"),
            os.path.join(os.path.dirname(__file__), "..", "assets", "invyntra_logo.png"),
            os.path.join(os.getcwd(), "app", "assets", "invyntra_logo.png"),
            os.path.join(project_root, "assets", "invyntra_logo.png"),
            os.path.join(project_root, "invyntra_logo.png"),
        ]
        # try jpg/jpeg too
        extra = []
        for base in list(logo_candidates):
            if base:
                for ext in (".jpg", ".jpeg"):
                    extra.append(os.path.splitext(base)[0] + ext)
        extra += [
            os.path.join(project_root, "app", "assets", f)
            for f in ("brand_logo.png", "brand_logo.jpg", "brand_logo.jpeg")
        ]
        logo_candidates += extra
        pix = None
        tried = []
        for p in logo_candidates:
            if not p:
                continue
            p = os.path.abspath(p)
            tried.append(p)
            if os.path.exists(p):
                pm = QtGui.QPixmap(p)
                if not pm.isNull():
                    pix = pm.scaledToWidth(120, QtCore.Qt.SmoothTransformation)
                    break
        if pix:
            logo_label.setPixmap(pix)
        else:
            # Try scanning assets folder for any image
            img_dirs = [
                os.path.join(project_root, "app", "assets"),
                os.path.join(project_root, "assets"),
            ]
            picked = None
            for d in img_dirs:
                d = os.path.abspath(d)
                if os.path.isdir(d):
                    for name in sorted(os.listdir(d)):
                        if name.lower().endswith((".png", ".jpg", ".jpeg")):
                            candidate = os.path.join(d, name)
                            pm = QtGui.QPixmap(candidate)
                            if not pm.isNull():
                                pix = pm.scaledToWidth(120, QtCore.Qt.SmoothTransformation)
                                picked = candidate
                                break
                if pix:
                    break
            if pix:
                print(f"[UI] Using logo discovered at: {picked}")
                logo_label.setPixmap(pix)
            else:
                # Fallback: simple vector logo (circle + M)
                def _make_fallback_logo(w: int = 120) -> QtGui.QPixmap:
                    pm = QtGui.QPixmap(w, w)
                    pm.fill(QtCore.Qt.transparent)
                    painter = QtGui.QPainter(pm)
                    painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
                    pen = QtGui.QPen(QtGui.QColor(0, 0, 0))
                    pen.setWidth(max(2, w // 18))
                    painter.setPen(pen)
                    painter.drawEllipse(QtCore.QRectF(pen.widthF(), pen.widthF(), w - 2*pen.widthF(), w - 2*pen.widthF()))
                    inset = w * 0.28
                    bottom = w * 0.72
                    left = w * 0.33
                    right = w * 0.67
                    midx = w * 0.50
                    mpen = QtGui.QPen(QtGui.QColor(0, 0, 0))
                    mpen.setCapStyle(QtCore.Qt.RoundCap)
                    mpen.setJoinStyle(QtCore.Qt.RoundJoin)
                    mpen.setWidth(max(4, w // 12))
                    painter.setPen(mpen)
                    painter.drawLine(QtCore.QPointF(left, inset), QtCore.QPointF(midx, bottom))
                    painter.drawLine(QtCore.QPointF(midx, bottom), QtCore.QPointF(right, inset))
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0)))
                    tri = QtGui.QPolygonF([
                        QtCore.QPointF(left + w*0.01, inset + w*0.10),
                        QtCore.QPointF(left + w*0.09, inset + w*0.36),
                        QtCore.QPointF(left + w*0.01, inset + w*0.36),
                    ])
                    painter.drawPolygon(tri)
                    painter.end()
                    return pm

                logo_label.setPixmap(_make_fallback_logo(140))
                print("[UI] Logo not found. Tried:")
                for t in tried:
                    print(" -", t)

        title = QtWidgets.QLabel(f"{settings.APP_NAME}")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size:28px;font-weight:700;margin:12px 0;")

        env_chip = QtWidgets.QLabel(settings.ENV.upper())
        env_chip.setAlignment(QtCore.Qt.AlignCenter)
        env_chip.setStyleSheet(
            "padding:2px 8px;border:1px solid #000;border-radius:10px;"
            "color:#000;font-weight:600;font-size:12px;"
        )

        header = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(header)
        h.addStretch(1)
        h.addWidget(title)
        h.addSpacing(8)
        h.addWidget(env_chip)
        h.addStretch(1)
        h.setContentsMargins(0, 0, 0, 0)

        subtitle = QtWidgets.QLabel("Welcome! Please log in or sign up to continue.")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet("color:#000;margin-bottom:24px;")

        login_btn = QtWidgets.QPushButton("Log in")
        signup_btn = QtWidgets.QPushButton("Sign up")
        for b in (login_btn, signup_btn):
            b.setFixedHeight(44)
            b.setMinimumWidth(140)
            b.setStyleSheet("font-size:16px;")

        login_btn.clicked.connect(self.go_login.emit)
        signup_btn.clicked.connect(self.go_signup.emit)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(login_btn)
        row.addSpacing(16)
        row.addWidget(signup_btn)
        row.addStretch(1)

        col = QtWidgets.QVBoxLayout(self)
        col.addStretch(1)
        col.addWidget(logo_label)
        col.addWidget(header)
        col.addWidget(subtitle)
        col.addLayout(row)
        col.addStretch(2)
        col.setContentsMargins(32, 24, 32, 24)
        col.setSpacing(12)


class SignupPage(QtWidgets.QWidget):
    go_back = QtCore.Signal()

    def __init__(self):
        super().__init__()
        # Inputs
        self.first_name = QtWidgets.QLineEdit()
        self.last_name = QtWidgets.QLineEdit()
        self.business = QtWidgets.QLineEdit()
        self.email = QtWidgets.QLineEdit()
        self.country_code = QtWidgets.QComboBox()
        self.phone = QtWidgets.QLineEdit()
        self.password = QtWidgets.QLineEdit(); self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password2 = QtWidgets.QLineEdit(); self.password2.setEchoMode(QtWidgets.QLineEdit.Password)

        self.first_name.setPlaceholderText("First Name")
        self.last_name.setPlaceholderText("Last Name")
        self.business.setPlaceholderText("Business Name")
        self.email.setPlaceholderText("Email")
        self.phone.setPlaceholderText("Phone Number")
        self.password.setPlaceholderText("Password")
        self.password2.setPlaceholderText("Re-enter Password")

        cc_list = ["+1", "+44", "+61", "+81", "+33", "+49", "+91", "+65", "+971", "+86"]
        self.country_code.addItems(cc_list)
        self.country_code.setCurrentText("+91")

        rules = QtWidgets.QLabel("At least 8 characters,Contains at least 1 uppercase letter,Contains at least 1 special character (!@#$%^&* etc.)")
        rules.setStyleSheet("color:#666;font-size:12px;")

        form = QtWidgets.QFormLayout()
        form.addRow("First Name", self.first_name)
        form.addRow("Last Name", self.last_name)
        form.addRow("Business Name", self.business)
        form.addRow("Email", self.email)
        phone_row = QtWidgets.QHBoxLayout()
        phone_row.addWidget(self.country_code)
        phone_row.addWidget(self.phone)
        form.addRow("Phone", phone_row)
        form.addRow("Password", self.password)
        form.addRow("Password Re-Enter", self.password2)

        back_btn = QtWidgets.QPushButton("Back")
        submit_btn = QtWidgets.QPushButton("Submit")
        back_btn.clicked.connect(self.go_back.emit)
        submit_btn.clicked.connect(self.on_submit)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(back_btn)
        btns.addStretch(1)
        btns.addWidget(submit_btn)

        lay = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Sign up")
        title.setStyleSheet("font-weight:600;font-size:18px;")
        lay.addWidget(title, 0, QtCore.Qt.AlignLeft)
        lay.addLayout(form)
        lay.addWidget(rules)
        lay.addStretch(1)
        lay.addLayout(btns)
        lay.setContentsMargins(24, 24, 24, 24)

    def _valid_email(self, email: str) -> bool:
        return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

    def _valid_password(self, pw: str) -> bool:
        if len(pw) < 8:
            return False
        if not re.search(r"[A-Z]", pw):
            return False
        if not re.search(r"[^A-Za-z0-9]", pw):
            return False
        return True

    def on_submit(self):
        first = self.first_name.text().strip()
        last = self.last_name.text().strip()
        biz = self.business.text().strip()
        email = self.email.text().strip().lower()
        cc = self.country_code.currentText().strip()
        phone = self.phone.text().strip()
        pw = self.password.text()
        pw2 = self.password2.text()

        if not all([first, last, biz, email, cc, phone, pw, pw2]):
            QtWidgets.QMessageBox.warning(self, "Missing info", "Please fill all fields.")
            return
        if not self._valid_email(email):
            QtWidgets.QMessageBox.warning(self, "Invalid email", "Please enter a valid email address.")
            return
        if pw != pw2:
            QtWidgets.QMessageBox.warning(self, "Password mismatch", "Passwords do not match.")
            return
        if not self._valid_password(pw):
            QtWidgets.QMessageBox.warning(self, "Weak password", "Follow the password rules shown.")
            return

        s = SessionLocal()
        try:
            exists_phone = s.query(User).filter_by(country_code=cc, phone=phone).one_or_none()
            if exists_phone:
                QtWidgets.QMessageBox.information(self, "Account exists", "An account with this phone number already exists.")
                return
            exists_email = s.query(User).filter_by(email=email).one_or_none()
            if exists_email:
                QtWidgets.QMessageBox.information(self, "Email in use", "This email is already registered. Try logging in.")
                return

            u = User(
                business=biz,
                first_name=first,
                last_name=last,
                email=email,
                country_code=cc,
                phone=phone,
                password_h=hash_password(pw),
                is_verified=True,
            )
            s.add(u)
            s.commit()
            QtWidgets.QMessageBox.information(self, "Success", "Account created. You can log in now.")
            self.go_back.emit()
        finally:
            s.close()


class VerifyPage(QtWidgets.QWidget):
    go_back = QtCore.Signal()
    go_success = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._user_id = None
        self.otp = QtWidgets.QLineEdit()
        self.otp.setPlaceholderText("Enter 6-digit OTP")
        self.otp.setMaxLength(6)
        self.otp.setAlignment(QtCore.Qt.AlignCenter)
        self.otp.setFixedWidth(160)

        label = QtWidgets.QLabel("Two-step verification")
        label.setStyleSheet("font-weight:600;font-size:18px;")

        back_btn = QtWidgets.QPushButton("Back")
        verify_btn = QtWidgets.QPushButton("Submit")
        back_btn.clicked.connect(self.go_back.emit)
        verify_btn.clicked.connect(self.on_verify)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.otp)
        row.addStretch(1)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(label)
        lay.addSpacing(12)
        lay.addLayout(row)
        lay.addSpacing(12)
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(back_btn)
        btns.addStretch(1)
        btns.addWidget(verify_btn)
        lay.addLayout(btns)
        lay.addStretch(1)
        lay.setContentsMargins(24, 24, 24, 24)

    def set_user(self, user_id: int):
        self._user_id = user_id

    def on_verify(self):
        uid = self._user_id
        code = self.otp.text().strip()
        if not uid:
            QtWidgets.QMessageBox.warning(self, "Error", "No user set to verify.")
            return
        if not code or len(code) != 6:
            QtWidgets.QMessageBox.warning(self, "Invalid", "Please enter the 6-digit OTP.")
            return
        if not _verify_otp(uid, code):
            QtWidgets.QMessageBox.warning(self, "Invalid", "OTP is wrong or expired.")
            return
        self.go_success.emit()


class LoginPage(QtWidgets.QWidget):
    go_back = QtCore.Signal()
    go_verify = QtCore.Signal(int)  # user_id

    def __init__(self):
        super().__init__()
        self.identifier = QtWidgets.QLineEdit()
        self.identifier.setPlaceholderText("Email or phone number")
        self.password = QtWidgets.QLineEdit()
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password.setPlaceholderText("Password")

        info = QtWidgets.QLabel("Use your email or phone number, then your password. You'll receive a 6-digit code via SMS and email.")
        info.setStyleSheet("color:#666;")

        back_btn = QtWidgets.QPushButton("Back")
        login_btn = QtWidgets.QPushButton("Log in")

        back_btn.clicked.connect(self.go_back.emit)
        login_btn.clicked.connect(self.on_login)

        form = QtWidgets.QFormLayout()
        form.addRow("Email/Phone", self.identifier)
        form.addRow("Password", self.password)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Log in"))
        lay.addWidget(info)
        lay.addLayout(form)
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(back_btn)
        btns.addStretch(1)
        btns.addWidget(login_btn)
        lay.addLayout(btns)
        lay.setContentsMargins(24, 24, 24, 24)

    def on_login(self):
        ident = self.identifier.text().strip()
        pw = self.password.text()
        if not ident or not pw:
            QtWidgets.QMessageBox.warning(self, "Missing", "Enter email/phone and password.")
            return
        s = SessionLocal()
        try:
            if "@" in ident:
                u = s.query(User).filter_by(email=ident.lower()).one_or_none()
            else:
                u = s.query(User).filter_by(phone=ident).one_or_none()
                if not u:
                    for cc_try in ["+1", "+44", "+61", "+81", "+33", "+49", "+91", "+65", "+971", "+86"]:
                        num = ident.removeprefix(cc_try)
                        if num != ident:
                            u = s.query(User).filter_by(country_code=cc_try, phone=num).one_or_none()
                            if u:
                                break
            if not u:
                QtWidgets.QMessageBox.warning(self, "Not found", "Account not found. Please sign up.")
                return
            if not verify_password(pw, u.password_h):
                QtWidgets.QMessageBox.warning(self, "Invalid", "Incorrect password.")
                return
            code = _set_otp(u.id)
            phone_full = f"{u.country_code}{u.phone}"
            _send_otp_sms(phone_full, code)
            _send_otp_email(u.email, code)
            QtWidgets.QMessageBox.information(self, "OTP sent", "We sent a 6-digit code to your phone and email.")
            self.go_verify.emit(u.id)
        finally:
            s.close()


class HomePage(QtWidgets.QWidget):
    go_logout = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.label = QtWidgets.QLabel("Welcome to Invyntra")
        self.label.setStyleSheet("font-size:20px;font-weight:600;")
        self.sub = QtWidgets.QLabel("Voice-first inventory will live here.")
        self.env = QtWidgets.QLabel("")
        logout = QtWidgets.QPushButton("Log out")
        logout.clicked.connect(self.go_logout.emit)

        col = QtWidgets.QVBoxLayout(self)
        col.addWidget(self.label)
        col.addWidget(self.sub)
        col.addWidget(self.env)
        col.addStretch(1)
        col.addWidget(logout)
        col.setContentsMargins(24, 24, 24, 24)


class AppWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invyntra")
        self.setMinimumSize(720, 480)

        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)

        self.welcome = WelcomePage()
        self.signup = SignupPage()
        self.verify = VerifyPage()
        self.login = LoginPage()
        self.home = HomePage()

        self.welcome.go_login.connect(lambda: self.stack.setCurrentWidget(self.login))
        self.welcome.go_signup.connect(lambda: self.stack.setCurrentWidget(self.signup))

        self.signup.go_back.connect(lambda: self.stack.setCurrentWidget(self.welcome))

        self.verify.go_back.connect(lambda: self.stack.setCurrentWidget(self.login))
        self.verify.go_success.connect(lambda: self.stack.setCurrentWidget(self.home))

        self.login.go_back.connect(lambda: self.stack.setCurrentWidget(self.welcome))
        self.login.go_verify.connect(self._to_verify)

        self.home.go_logout.connect(lambda: self.stack.setCurrentWidget(self.welcome))

        for w in (self.welcome, self.signup, self.verify, self.login, self.home):
            page = QtWidgets.QWidget()
            box = QtWidgets.QVBoxLayout(page)
            card = QtWidgets.QFrame()
            card.setStyleSheet("QFrame{background:white;border:1px solid #000;border-radius:8px;padding:16px;}")
            inner = QtWidgets.QVBoxLayout(card)
            inner.addWidget(w)
            box.addStretch(1)
            box.addWidget(card)
            box.addStretch(1)
            box.setContentsMargins(32, 32, 32, 32)
            self.stack.addWidget(page)

        self._set_bw_theme()

    def _set_bw_theme(self):
        self.setStyleSheet(
            "QMainWindow{background:white;}"
            "QLabel{font-size:14px;color:#000;}"
            "QPushButton{padding:8px 14px;border:1px solid #000;border-radius:6px;background:#fff;color:#000;}"
            "QPushButton:hover{background:#f2f2f2;}"
            "QLineEdit{height:36px;padding:4px 8px;border:1px solid #000;border-radius:4px;color:#000;background:#fff;}"
            "QComboBox{height:36px;padding:4px 8px;border:1px solid #000;border-radius:4px;color:#000;background:#fff;}"
        )

    def _to_verify(self, user_id: int):
        self.verify.set_user(user_id)
        self.home.env.setText(f"Environment: {settings.ENV}")
        self.stack.setCurrentWidget(self.verify)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = AppWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
