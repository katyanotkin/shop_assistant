from core.brand import APP_MOTTO, APP_NAME
from web.main import _inject_brand


def test_inject_brand_replaces_name():
    result = _inject_brand("Hello __APP_NAME__")
    assert APP_NAME in result
    assert "__APP_NAME__" not in result


def test_inject_brand_replaces_motto():
    result = _inject_brand("__APP_MOTTO__")
    assert APP_MOTTO in result
    assert "__APP_MOTTO__" not in result


def test_inject_brand_both():
    result = _inject_brand("__APP_NAME__ — __APP_MOTTO__")
    assert "__APP_NAME__" not in result
    assert "__APP_MOTTO__" not in result
    assert APP_NAME in result
    assert APP_MOTTO in result


def test_inject_brand_no_placeholders():
    html = "<html><body>nothing here</body></html>"
    assert _inject_brand(html) == html
