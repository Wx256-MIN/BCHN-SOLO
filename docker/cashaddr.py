"""Validate Bitcoin Cash CashAddr addresses without external dependencies."""

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_CHARSET_MAP = {char: value for value, char in enumerate(_CHARSET)}
_HASH_LENGTHS = (20, 24, 28, 32, 40, 48, 56, 64)
_GENERATORS = (
    0x98F2BC8E61,
    0x79B76D99E2,
    0xF33E5FB3C4,
    0xAE2EABE2A8,
    0x1E4F43E470,
)


def is_valid_cashaddr(address, expected_prefix="bitcoincash"):
    """Validate prefix, alphabet, checksum, version and encoded hash length."""
    if not isinstance(address, str) or not address:
        return False
    if address.lower() != address and address.upper() != address:
        return False
    address = address.lower()
    if ":" not in address:
        return False
    prefix, encoded = address.split(":", 1)
    if prefix != expected_prefix or len(encoded) < 9 or encoded[0] not in ("q", "p"):
        return False
    try:
        payload = [_CHARSET_MAP[ch] for ch in encoded]
    except KeyError:
        return False

    # CashAddr polymod returns zero after its final XOR with one for valid strings.
    checksum = 1
    for value in [ord(ch) & 0x1F for ch in prefix] + [0] + payload:
        top = checksum >> 35
        checksum = ((checksum & 0x07FFFFFFFF) << 5) ^ value
        for bit, generator in enumerate(_GENERATORS):
            if (top >> bit) & 1:
                checksum ^= generator
    if (checksum ^ 1) != 0:
        return False

    # Decode the payload (excluding the eight 5-bit checksum symbols) into bytes.
    accumulator = 0
    bit_count = 0
    decoded = bytearray()
    for value in payload[:-8]:
        accumulator = (accumulator << 5) | value
        bit_count += 5
        while bit_count >= 8:
            bit_count -= 8
            decoded.append((accumulator >> bit_count) & 0xFF)
    if bit_count >= 5 or (bit_count and ((accumulator << (8 - bit_count)) & 0xFF)):
        return False
    if not decoded:
        return False

    version = decoded[0]
    if version & 0x80:  # Reserved version bit must be clear.
        return False
    return len(decoded) == 1 + _HASH_LENGTHS[version & 0x07]
