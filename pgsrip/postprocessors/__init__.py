from pgsrip.postprocessors.base import PostProcessorFactory
from pgsrip.postprocessors.cleanit import CleanitPostProcessor

#: the built-in post-processors, by name
POST_PROCESSORS: dict[str, type[PostProcessorFactory]] = {'cleanit': CleanitPostProcessor}
#: other packages add a post-processor with an entry point in this group. See docs/usage.md.
POST_PROCESSOR_ENTRY_POINTS = 'pgsrip.postprocessors'
