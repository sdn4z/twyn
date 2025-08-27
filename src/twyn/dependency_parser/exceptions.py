from twyn.base.exceptions import TwynError


class NoMatchingParserError(TwynError):
    """
    Exception raised when no suitable dependency file parser can be automatically determined.

    This error occurs when the dependency parser cannot identify the correct parser
    for a given dependency file format, requiring manual specification via command line.
    """

    message = "Could not assign a dependency file parser. Please specify it with --dependency-file"


class MultipleParsersError(TwynError):
    """
    Exception raised when multiple dependency file parsers are detected.

    This error occurs when the system cannot automatically determine which
    dependency file format to use because multiple valid formats are found
    in the same context (e.g., both requirements.txt and pyproject.toml
    are present).

    """

    message = "Can't auto detect dependencies file to parse. More than one format was found."
