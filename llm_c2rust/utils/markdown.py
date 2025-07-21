import re
from typing import List, Tuple


def extract_code_blocks(markdown_string: str) -> List[str]:
    """
    Extract all the code blocks from the markdown string.

    Args:
        markdown_string: The markdown string to extract the code blocks from.

    Returns:
        A list of code blocks from the markdown string.
    """
    pattern = r"```[a-zA-Z]*\n([\s\S]*?)\n```"
    matches = re.findall(pattern, markdown_string)
    return [match.strip() for match in matches]


def extract_code_blocks_with_language(markdown_string: str) -> List[Tuple[str, str]]:
    """
    Extract all the code blocks with language from the markdown string.

    Args:
        markdown_string: The markdown string to extract the code blocks with language from.

    Returns:
        A list of code blocks with language from the markdown string.
    """
    code_blocks = []
    block = None
    lang = None
    for line in markdown_string.splitlines():
        if m := re.match(r"\s*```([a-zA-Z]*)$", line):
            if block is not None:
                code_blocks.append((lang, block))
                block = None
                lang = None
            else:
                lang = m.group(1)
                block = ""
        else:
            if block is not None:
                block += line + "\n"
    # append the last partial block
    if block is not None:
        code_blocks.append((lang, block))
    return code_blocks
