from splitter import split_text


def test_short_text_stays_single():
    assert split_text("привет как дела") == ["привет как дела"]


def test_splits_on_sentence_boundaries():
    parts = split_text("раз. два. три. четыре. пять. шесть.", max_len=15)
    assert len(parts) >= 2
    for p in parts:
        assert len(p) <= 15


def test_merges_small_sentences_up_to_limit():
    parts = split_text("один. два. три.", max_len=30)
    assert parts == ["один. два. три."]


def test_monster_sentence_hard_split_keeps_all_words():
    words = ["слово" + str(i) for i in range(30)]
    text = " ".join(words)
    parts = split_text(text, max_len=50)
    assert len(parts) > 1
    assert all(len(p) <= 50 for p in parts)
    assert " ".join(parts) == text


def test_exclamation_and_question_are_boundaries():
    parts = split_text("что?! ничего! сам ты", max_len=12)
    assert len(parts) >= 2


def test_ellipsis_is_boundary():
    parts = split_text("ну вот… и всё… да", max_len=10)
    assert len(parts) >= 2


def test_result_parts_are_nonempty():
    parts = split_text("Раз. Два! Три?", max_len=10)
    assert all(p.strip() for p in parts)
