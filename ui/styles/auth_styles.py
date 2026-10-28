"""Stylesheets for the authentication screen."""
AUTH_DARK_QSS = r"""
            * {
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            }
            QWidget {
                background-color: #1E1E1E;
                margin: 0px;
                padding: 0px;
            }
            QLabel#welcome_label {
                font-size: 22px;
                font-weight: 700;
                margin-bottom: 20px;
                color: #fff;
                transition: all 0.25s ease;
            }
            QLabel#welcome_label:hover {
                color: #80c0ff;
                font-size: 26px;
                text-shadow: 0 0 12px #80c0ffaa;
            }
            QLabel#error_label {
                background-color: #e74c3c;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: 600;
                color: white;
                margin-top: 15px;
                box-shadow: 0 3px 7px rgba(0,0,0,0.4);
            }
            QLineEdit {
                background-color: #2A2A2A;
                color: #fff;
                border: 2px solid #555;
                border-radius: 14px;
                padding: 14px 20px;
                font-size: 17px;
                selection-background-color: #3f51b5;
                selection-color: white;
                transition: border-color 0.3s ease, background-color 0.3s ease;
            }
            QLineEdit::placeholder {
                color: #aaa;
            }
            QLineEdit:focus {
                border-color: #3f51b5;
                box-shadow: 0 0 6px #3f51b5aa;
            }
            QPushButton#login_button {
                background-color: #3f51b5;
                color: white;
                font-weight: 700;
                border-radius: 18px;
                padding: 14px 32px;
                min-width: 110px;
                min-height: 48px;
                box-shadow: 0 5px 16px rgba(63,81,181,0.6);
                transition: background-color 0.3s ease, box-shadow 0.3s ease;
            }
            QPushButton#login_button:hover {
                background-color: #2c387e;
                box-shadow: 0 8px 28px rgba(44,56,126,0.8);
            }
            QPushButton#close_button {
                background-color: #555;
                color: #ddd;
                font-weight: 600;
                border-radius: 18px;
                padding: 14px 28px;
                min-width: 100px;
                min-height: 48px;
                box-shadow: none;
                transition: background-color 0.3s ease;
            }
            QPushButton#close_button:hover {
                background-color: #777;
            }
            QLabel[focused="true"] {
                font-size: 19px;
                color: #80c0ff;
                font-weight: 700;
                text-shadow: 0 0 8px #80c0ffcc;
                transition: all 0.3s ease;
            }
            QLabel {
                font-weight: 600;
                min-width: 90px;
                color: #ddd;
                transition: all 0.3s ease;
            }
        """

AUTH_LIGHT_QSS = r"""
            * {
                font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            }
            QWidget {
                background-color: #f5f5f5;
                margin: 0px;
                padding: 0px;
            }
            QLabel#welcome_label {
                font-size: 32px;
                font-weight: 700;
                margin-bottom: 20px;
                color: #222;
                transition: all 0.25s ease;
            }
            QLabel#welcome_label:hover {
                color: #3f51b5;
                font-size: 36px;
                text-shadow: 0 0 10px #3f51b544;
            }
            QLabel#error_label {
                background-color: #e74c3c;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: 600;
                color: white;
                margin-top: 15px;
                box-shadow: 0 3px 7px rgba(0,0,0,0.3);
            }
            QLineEdit {
                background-color: #ffffff;
                color: #222;
                border: 2px solid #aaa;
                border-radius: 14px;
                padding: 14px 20px;
                font-size: 17px;
                selection-background-color: #3f51b5;
                selection-color: white;
                transition: border-color 0.3s ease, background-color 0.3s ease;
            }
            QLineEdit::placeholder {
                color: #999;
            }
            QLineEdit:focus {
                border-color: #3f51b5;
                box-shadow: 0 0 6px #3f51b5aa;
            }
            QPushButton#login_button {
                background-color: #3f51b5;
                color: white;
                font-weight: 700;
                border-radius: 18px;
                padding: 14px 32px;
                min-width: 110px;
                min-height: 48px;
                box-shadow: 0 5px 16px rgba(63,81,181,0.4);
                transition: background-color 0.3s ease, box-shadow 0.3s ease;
            }
            QPushButton#login_button:hover {
                background-color: #2c387e;
                box-shadow: 0 8px 28px rgba(44,56,126,0.6);
            }
            QPushButton#close_button {
                background-color: #bbb;
                color: #333;
                font-weight: 600;
                border-radius: 18px;
                padding: 14px 28px;
                min-width: 100px;
                min-height: 48px;
                box-shadow: none;
                transition: background-color 0.3s ease;
            }
            QPushButton#close_button:hover {
                background-color: #999;
            }
            QLabel[focused="true"] {
                font-size: 19px;
                color: #3f51b5;
                font-weight: 700;
                text-shadow: 0 0 8px #3f51b566;
                transition: all 0.3s ease;
            }
            QLabel {
                font-weight: 600;
                min-width: 90px;
                color: #222;
                transition: all 0.3s ease;
            }
        """
