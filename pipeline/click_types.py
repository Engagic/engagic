"""Click Custom Types for Pipeline CLI

Domain-specific type validators for Click commands.
Provides early validation at CLI parsing time with clear error messages.
"""

import re
import click


class BananaType(click.ParamType):
    """Validates city_banana format: lowercase alphanumeric + uppercase state

    Valid examples:
    - paloaltoCA
    - newyorkNY
    - stlouisMO

    Invalid examples:
    - PaloAltoCA (uppercase letters in city)
    - paloaltoca (lowercase state)
    - palo-alto-CA (special characters)
    """

    name = "banana"

    def convert(self, value, param, ctx):
        """Validate banana format at CLI parse time

        Args:
            value: User-provided banana string
            param: Click parameter object
            ctx: Click context

        Returns:
            Valid banana string

        Raises:
            click.BadParameter: If banana format is invalid
        """
        if not value:
            self.fail("banana cannot be empty", param, ctx)

        # Pattern: lowercase alphanumeric + exactly 2 uppercase letters (state code)
        # Examples: paloaltoCA, newyorkNY, stlouisMO
        if not re.match(r'^[a-z0-9]+[A-Z]{2}$', value):
            self.fail(
                f'{value!r} is not a valid city_banana. '
                f'Format: lowercasealphanumericSTATE (e.g., paloaltoCA, newyorkNY)',
                param,
                ctx
            )

        return value


BANANA = BananaType()
