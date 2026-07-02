from core.slug import slugify


def test_basic_lowercasing_and_spaces():
    assert slugify("Bathroom Cabinet") == "bathroom_cabinet"


def test_punctuation_and_whitespace_collapse():
    assert slugify("bathroom  cabinet!!") == "bathroom_cabinet"


def test_leading_trailing_symbols_stripped():
    assert slugify("--Wool Coat--") == "wool_coat"


def test_unicode_diacritics_degrade_to_ascii():
    assert slugify("Café Chaïr") == "cafe_chair"


def test_all_symbol_input_falls_back_to_default():
    assert slugify("!!!") == "search"


def test_empty_input_falls_back_to_default():
    assert slugify("") == "search"


def test_truncation_boundary():
    long_title = "a" * 100
    result = slugify(long_title, max_length=64)
    assert result == "a" * 64
    assert len(result) == 64


def test_truncation_does_not_leave_trailing_underscore():
    title = "a" * 63 + " b"
    result = slugify(title, max_length=64)
    assert not result.endswith("_")
