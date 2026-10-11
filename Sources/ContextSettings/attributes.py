"""Bounded macOS metadata preservation; unknown attributes fail closed."""
import ctypes
import sys
from .config_file import Refused

def system():
    if sys.platform != 'darwin':
        raise Refused('unsupported_platform')
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    lib.flistxattr.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    lib.flistxattr.restype = ctypes.c_ssize_t
    lib.fgetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.fgetxattr.restype = ctypes.c_ssize_t
    lib.fsetxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.fsetxattr.restype = ctypes.c_int
    return lib

def capture(fd):
    lib = system()
    size = lib.flistxattr(fd, None, 0, 0)
    if not 0 <= size <= 4096:
        raise Refused('unsupported_file_attributes')
    names = ctypes.create_string_buffer(size or 1)
    if lib.flistxattr(fd, names, size, 0) != size:
        raise Refused('attributes_changed')
    result = {}
    for name in names.raw[:size].split(b'\0'):
        if not name:
            continue
        if name != b'com.apple.provenance':
            raise Refused('unsupported_file_attributes')
        length = lib.fgetxattr(fd, name, None, 0, 0, 0)
        if not 0 <= length <= 4096:
            raise Refused('unsupported_file_attributes')
        value = ctypes.create_string_buffer(length or 1)
        if lib.fgetxattr(fd, name, value, length, 0, 0) != length:
            raise Refused('attributes_changed')
        result[name.decode()] = value.raw[:length].hex()
    return result

def restore(fd, attributes):
    lib = system()
    for name, value in attributes.items():
        if name != 'com.apple.provenance' or not isinstance(value, str) or len(value) > 8192:
            raise Refused('unsupported_file_attributes')
        raw = bytes.fromhex(value)
        if lib.fsetxattr(fd, name.encode(), raw, len(raw), 0, 0):
            raise Refused('attributes_not_preserved')
    if capture(fd) != attributes:
        raise Refused('attributes_not_preserved')
