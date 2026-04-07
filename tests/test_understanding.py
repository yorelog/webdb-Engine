"""Tests for the page understanding layer."""

from __future__ import annotations

from webdb.database.models import ElementRole, PageType
from webdb.understanding.dom_parser import DOMParser
from webdb.understanding.element_recognizer import ElementRecognizer
from webdb.understanding.page_classifier import PageClassifier

LOGIN_HTML = """
<html><head><title>Login</title></head><body>
  <form action="/login" method="post">
    <input type="text" name="username" placeholder="Username" />
    <input type="password" name="password" placeholder="Password" />
    <button type="submit">Sign In</button>
  </form>
</body></html>
"""

LIST_HTML = """
<html><head><title>Data List</title></head><body>
  <table>
    <tr><th>Name</th><th>Date</th><th>Value</th></tr>
    <tr><td>Alice</td><td>2024-01-01</td><td>100</td></tr>
    <tr><td>Bob</td><td>2024-01-02</td><td>200</td></tr>
  </table>
  <div class="pagination"><a href="?page=2">Next</a></div>
</body></html>
"""

FORM_HTML = """
<html><head><title>Register</title></head><body>
  <form action="/register" method="post">
    <input type="text" name="first_name" />
    <input type="text" name="last_name" />
    <input type="email" name="email" />
    <input type="text" name="phone" />
    <input type="submit" value="Submit" />
  </form>
</body></html>
"""

SEARCH_HTML = """
<html><head><title>Search</title></head><body>
  <form>
    <input type="search" name="q" placeholder="Search..." />
    <button type="submit">Go</button>
  </form>
  <ul>
    <li>Result 1</li><li>Result 2</li><li>Result 3</li><li>Result 4</li>
    <li>Result 5</li><li>Result 6</li>
  </ul>
</body></html>
"""


class TestDOMParser:
    def test_title(self):
        parser = DOMParser(LOGIN_HTML)
        assert parser.title == "Login"

    def test_get_interactive_elements_login(self):
        parser = DOMParser(LOGIN_HTML)
        elements = parser.get_interactive_elements()
        tags = [e.tag for e in elements]
        assert "input" in tags
        assert "button" in tags

    def test_get_forms(self):
        parser = DOMParser(LOGIN_HTML)
        forms = parser.get_forms()
        assert len(forms) == 1
        assert forms[0]["method"] == "post"
        types = [i["type"] for i in forms[0]["inputs"]]
        assert "password" in types

    def test_get_links(self):
        parser = DOMParser(LIST_HTML)
        links = parser.get_links()
        assert any(link["text"] == "Next" for link in links)

    def test_get_text(self):
        parser = DOMParser(LOGIN_HTML)
        text = parser.get_text()
        assert "Sign In" in text


class TestPageClassifier:
    def test_classify_login(self):
        result = PageClassifier(LOGIN_HTML, title="Login", url="/login").classify()
        assert result.page_type == PageType.LOGIN
        assert result.confidence > 0

    def test_classify_list(self):
        result = PageClassifier(LIST_HTML, title="Data List").classify()
        assert result.page_type == PageType.LIST

    def test_classify_search(self):
        result = PageClassifier(SEARCH_HTML, title="Search").classify()
        assert result.page_type in (PageType.SEARCH, PageType.LIST)

    def test_classify_form(self):
        result = PageClassifier(FORM_HTML, title="Register").classify()
        assert result.page_type == PageType.FORM

    def test_unknown_page(self):
        result = PageClassifier("<html><body><p>Hello</p></body></html>").classify()
        assert result.page_type == PageType.UNKNOWN

    def test_signals_structure(self):
        result = PageClassifier(LOGIN_HTML).classify()
        assert isinstance(result.signals, dict)
        assert "has_password_field" in result.signals


class TestElementRecognizer:
    def test_recognise_login_elements(self):
        parser = DOMParser(LOGIN_HTML)
        raw = parser.get_interactive_elements()
        recognizer = ElementRecognizer()
        recognized = recognizer.recognize(raw)
        roles = {e.role for e in recognized}
        assert ElementRole.FIELD in roles
        assert ElementRole.ACTION in roles

    def test_confidence_range(self):
        parser = DOMParser(LOGIN_HTML)
        raw = parser.get_interactive_elements()
        recognizer = ElementRecognizer()
        recognized = recognizer.recognize(raw)
        for el in recognized:
            assert 0.0 <= el.confidence <= 1.0

    def test_is_interactive_flag(self):
        parser = DOMParser(LOGIN_HTML)
        raw = parser.get_interactive_elements()
        recognizer = ElementRecognizer()
        recognized = recognizer.recognize(raw)
        assert all(el.is_interactive for el in recognized)
