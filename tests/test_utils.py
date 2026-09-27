import numpy as np
import numpy.typing as npt
import pytest

from pgsrip.utils import split_lines


def bitmap(rows: str) -> npt.NDArray[np.uint8]:
    """A subtitle bitmap: one character for each row, '#' is a row with ink."""
    image = np.full((len(rows), 4), 255, dtype=np.uint8)
    image[[index for index, row in enumerate(rows) if row == '#'], 1] = 0
    return image


def ink_rows(image: npt.NDArray[np.uint8]) -> str:
    return ''.join('#' if (row < 128).any() else '.' for row in image)


@pytest.mark.parametrize(
    ('rows', 'lines'),
    [
        pytest.param('#####', ['#####'], id='one line'),
        pytest.param('#####..#####', ['#####', '#####'], id='two lines'),
        pytest.param('#.#####..#####', ['#.#####', '#####'], id='umlaut dots go with the line below'),
        pytest.param('#####..#####..#', ['#####', '#####..#'], id='low part at the bottom goes with the line above'),
        pytest.param('.....', ['.....'], id='empty bitmap'),
    ],
)
def test_split_lines_gives_one_image_for_each_text_line(rows: str, lines: list[str]) -> None:
    assert [ink_rows(line) for line in split_lines(bitmap(rows))] == lines
