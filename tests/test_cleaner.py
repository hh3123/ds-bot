import pytest

from cleaner import clean_message


def test_removes_http_urls():
    assert clean_message("смотри https://example.com/page?q=1 прикол") == "смотри прикол"


def test_removes_www_urls():
    assert clean_message("зайди на www.тест.рф срочно") == "зайди на срочно"


def test_custom_emoji_spoken_by_name():
    assert clean_message("привет <:pepe_sad:123456789> мир") == "привет pepe sad мир"
    assert clean_message("<a:volna:987654321> всем") == "volna всем"


def test_gibberish_custom_emoji_names_dropped_silently():
    assert clean_message("лол <:asdfgh:1>") == "лол"            # набор букв
    assert clean_message("лол <:x1:1>") == "лол"                # короткое и с цифрой
    assert clean_message("лол <:ччщщ:1>") == "лол"              # кластер согласных
    assert clean_message("лол <:kekw:1>") == "лол kekw"         # мем, но читаемое слово


def test_removes_mentions_and_channel_refs_but_keeps_text():
    assert clean_message("<@12345> и <#67890> тут") == "и тут"


def test_mentions_replaced_with_nickname_when_available():
    # mentions map: id -> имя, чтобы слышать "Миша", а не тишину
    assert clean_message("<@42> привет", mentions={"42": "Миша"}) == "Миша привет"


def test_unicode_emoji_spoken_by_russian_name():
    assert clean_message("хаха 😂 смешно 🔥") == "хаха смеется до слез смешно огонь"
    assert clean_message("😊") == "довольно улыбается"


def test_repeated_same_emoji_spoken_once():
    assert clean_message("ахах 😂😂😂 жесть") == "ахах смеется до слез жесть"


def test_strips_markdown():
    assert clean_message("**жирный** и _курсив_ ~~зачерк~~ `код`") == "жирный и курсив зачерк код"
    assert clean_message("|| спойлер ||") == "спойлер"
    assert clean_message("> цитата") == "цитата"
    assert clean_message("# заголовок") == "заголовок"


def test_code_block_removed_entirely():
    assert clean_message("и вот код:\n```py\nprint('hi')\n```\nконец") == "и вот код: конец"


def test_collapses_whitespace_and_newlines():
    assert clean_message("раз   два\n\n\nтри") == "раз два три"


def test_truncates_long_text_at_word_boundary():
    text = "слово " * 100  # 600 символов
    result = clean_message(text, max_length=60)
    assert len(result) <= 60
    assert not result.endswith(("с", "сло", "слов"))  # не рубим слово посередине
    assert result.endswith("…")


def test_empty_after_cleaning_returns_empty():
    assert clean_message("https://example.com") == ""
    assert clean_message("   ") == ""


def test_keeps_russian_text_intact():
    assert clean_message("Привет, как дела? Всё хорошо!") == "Привет, как дела? Всё хорошо!"
