from pgsrip.writers.base import Writer
from pgsrip.writers.srt import SrtWriter

#: the built-in writers. The value of --format is the name of a writer.
WRITERS: tuple[type[Writer], ...] = (SrtWriter,)
