import typing


class TsvDataItem:
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

    @property
    def h_center(self) -> int:
        return self.top + self.height // 2

    @property
    def w_center(self) -> int:
        return self.left + self.width // 2

    def matches(self, shape: tuple[int, int, int, int]) -> bool:
        h_start, w_start, h_end, w_end = shape
        return h_start <= self.h_center <= h_end and w_start <= self.w_center <= w_end


class TsvData:
    def __init__(self, data: dict[str, list[typing.Any]], confidence: int):
        self.confidence = confidence
        keys = data.keys()
        items = [
            TsvDataItem(**{k: values[i] for (i, k) in enumerate(keys)})
            for values in (zip(*[data[key] for key in keys], strict=True))
        ]
        items.sort(key=lambda x: x.word_num)
        items.sort(key=lambda x: x.line_num)
        items.sort(key=lambda x: x.par_num)
        items.sort(key=lambda x: x.block_num)
        items.sort(key=lambda x: x.page_num)
        self.items = items
        self.words = {item.text for item in items if item.text and item.conf >= confidence}

    def select(self, shape: tuple[int, int, int, int]) -> list[TsvDataItem]:
        return [item for item in self.items if item.level == 5 and item.matches(shape)]

    def has_word(self, word: str) -> bool:
        return word in self.words
