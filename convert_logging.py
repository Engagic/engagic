#!/usr/bin/env python3
"""
Convert f-string logging to structured logging format.

Usage:
    python3 convert_logging.py <file_path>

This script converts patterns like:
    logger.info(f"message {variable}")
to:
    logger.info("message", variable=variable)
"""

import re
import sys
from pathlib import Path


def convert_fstring_logging(content: str) -> tuple[str, int]:
    """
    Convert f-string logging calls to structured format.

    Returns:
        (converted_content, num_conversions)
    """
    conversions = 0

    # Pattern to match f-string logging calls
    # Matches: logger.level(f"...")
    pattern = r'logger\.(info|debug|warning|error)\(f"([^"]*)"(?:,\s*[^)]+)?\)'

    def replace_fstring(match):
        nonlocal conversions
        log_level = match.group(1)
        fstring = match.group(2)

        # Extract variables from f-string
        # Pattern: {variable} or {expression}
        var_pattern = r'\{([^}]+)\}'
        variables = re.findall(var_pattern, fstring)

        # Remove f-string formatting to get plain message
        message = re.sub(var_pattern, '', fstring)
        # Clean up extra spaces
        message = re.sub(r'\s+', ' ', message).strip()
        # Remove common prefixes
        message = re.sub(r'^\[[\w:]+\]\s*', '', message)
        message = message.lower()

        # Build kwargs
        kwargs = []
        for var_expr in variables:
            # Simple variable names
            if var_expr.isidentifier() or '.' in var_expr or '[' in var_expr:
                # Extract clean variable name for kwarg
                clean_name = var_expr.split('.')[0].split('[')[0]
                if ':' in var_expr:  # Format specifier like {count:,}
                    var_name = var_expr.split(':')[0]
                    kwargs.append(f"{var_name}={var_name}")
                else:
                    kwargs.append(f"{clean_name}={var_expr}")
            # Expressions like len(x), str(e), etc.
            elif '(' in var_expr:
                if 'len(' in var_expr:
                    inner = var_expr.replace('len(', '').replace(')', '')
                    kwargs.append(f"{inner}_length=len({inner})")
                elif 'str(' in var_expr:
                    inner = var_expr.replace('str(', '').replace(')', '')
                    kwargs.append(f"error=str({inner})")
                elif 'type(' in var_expr and ').__name__' in var_expr:
                    inner = var_expr.replace('type(', '').replace(').__name__', '')
                    kwargs.append(f"error_type=type({inner}).__name__")
                else:
                    # Generic expression
                    kwargs.append(f"value={var_expr}")

        # Build new logging call
        kwargs_str = ', '.join(kwargs)
        if kwargs_str:
            result = f'logger.{log_level}("{message}", {kwargs_str})'
        else:
            result = f'logger.{log_level}("{message}")'

        conversions += 1
        return result

    # Apply replacements
    converted = re.sub(pattern, replace_fstring, content, flags=re.MULTILINE)

    return converted, conversions


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 convert_logging.py <file_path>")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Read file
    content = file_path.read_text()

    # Convert
    converted, num_conversions = convert_fstring_logging(content)

    if num_conversions > 0:
        # Write back
        file_path.write_text(converted)
        print(f"Converted {num_conversions} f-string logging calls in {file_path}")
    else:
        print(f"No f-string logging calls found in {file_path}")


if __name__ == "__main__":
    main()
