import re
from typing import Literal

Language = Literal["kk", "ru", "en"]


def detect_text_language(text: str) -> Language:
    if re.search(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]", text):
        return "kk"
    if re.search(r"[а-яёА-ЯЁ]", text):
        return "ru"
    return "en"
