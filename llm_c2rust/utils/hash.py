import hashlib

def calculate_md5(string: str) -> str:
    """
    Calculate the MD5 hash of a string.
    
    Args:
        string: The string to calculate the MD5 hash of.

    Returns:
        The MD5 hash of the string.
    """
    md5_hash = hashlib.md5(string.encode())
    md5 = md5_hash.hexdigest()
    return md5
