import typing

from pgsrip.formats.pgs import Box

#: the level of a word in the TSV output of tesseract
WORD_LEVEL = 5


class TsvWord:
    """One row of the TSV output of tesseract. A row of level WORD_LEVEL is a word."""

    def __init__(
        self,
        level: int | str,
        page_num: int | str,
        block_num: int | str,
        par_num: int | str,
        line_num: int | str,
        word_num: int | str,
        left: int | str,
        top: int | str,
        width: int | str,
        height: int | str,
        conf: int | str | float,
        text: str,
    ):
        self.level = int(level)
        self.page_num = int(page_num)
        self.block_num = int(block_num)
        self.par_num = int(par_num)
        self.line_num = int(line_num)
        self.word_num = int(word_num)
        self.left = int(left)
        self.top = int(top)
        self.width = int(width)
        self.height = int(height)
        self.conf = int(float(conf))  # cast to float first to handle strings passed by pytesseract<0.3.10
        self.text = text

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self) -> str:
        return f'{(self.top, self.left)}{self.text}'

    def matches(self, box: Box) -> bool:
        """True when the middle of the word is in the box."""
        return (
            box.top <= self.top + self.height // 2 <= box.bottom
            and box.left <= self.left + self.width // 2 <= box.right
        )


class TsvResult:
    """The result of one tesseract call on a composite, in reading order."""

    def __init__(self, data: dict[str, list[typing.Any]], confidence: int):
        keys = data.keys()
        words = [
            TsvWord(**{k: values[i] for (i, k) in enumerate(keys)})
            for values in (zip(*[data[key] for key in keys], strict=True))
        ]
        words.sort(key=lambda x: (x.page_num, x.block_num, x.par_num, x.line_num, x.word_num))
        self.words = words
        #: the texts that the composite has at least one time with the confidence of the pass
        self.confident_texts = {word.text for word in words if word.text and word.conf >= confidence}

    def select(self, box: Box) -> list[TsvWord]:
        """The words in the box, in reading order."""
        return [word for word in self.words if word.level == WORD_LEVEL and word.matches(box)]

    def has_word(self, text: str) -> bool:
        return text in self.confident_texts
