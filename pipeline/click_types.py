"""Click Custom Types for Pipeline CLI

Domain-specific type validators for Click commands.
Provides early validation at CLI parsing time with clear error messages.
"""

import re
import click


class BananaType(click.ParamType):
    """Validates banana format: lowercase alphanumeric (with optional hyphens) + uppercase state

    Valid examples:
    - paloaltoCA          (city)
    - newyorkNY           (city)
    - alamedacountyCA     (county)
    - bartCA              (transit authority)
    - ebmudCA             (utility)

    Invalid examples:
    - PaloAltoCA (uppercase letters in name)
    - paloaltoca (lowercase state)
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

        # Pattern: lowercase alphanumeric (with optional hyphens) + exactly 2 uppercase letters (state code)
        # Covers cities (paloaltoCA), counties (alamedacountyCA), utilities (ebmudCA)
        if not re.match(r'^[a-z0-9-]+[A-Z]{2}$', value):
            self.fail(
                f'{value!r} is not a valid banana. '
                f'Format: lowercasenameSTATE (e.g., paloaltoCA, alamedacountyCA)',
                param,
                ctx
            )

        return value


BANANA = BananaType()
