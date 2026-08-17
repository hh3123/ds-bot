from gate import can_speak


def test_speaks_when_author_in_same_voice_channel_as_bot():
    assert can_speak(bot_channel_id=100, author_channel_id=100) is True


def test_silent_when_author_not_in_voice():
    assert can_speak(bot_channel_id=100, author_channel_id=None) is False


def test_silent_when_author_in_other_voice_channel():
    assert can_speak(bot_channel_id=100, author_channel_id=200) is False


def test_silent_when_bot_not_in_voice():
    assert can_speak(bot_channel_id=None, author_channel_id=100) is False
