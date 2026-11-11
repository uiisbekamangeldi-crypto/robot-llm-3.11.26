from app.modules.dialog.language import detect_text_language


def test_text_language_routing() -> None:
    assert detect_text_language("Кітапхана қайда?") == "kk"
    assert detect_text_language("Где библиотека?") == "ru"
    assert detect_text_language("Where is the library?") == "en"
