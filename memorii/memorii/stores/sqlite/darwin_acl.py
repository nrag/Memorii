"""Check Darwin extended ACLs, which POSIX mode bits do not describe."""

from __future__ import annotations

import ctypes
import errno
import os
import sys
from pathlib import Path

_ACL_TYPE_EXTENDED = 0x00000100  # Darwin sys/acl.h

if sys.platform == "darwin":
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _LIBC.acl_get_fd_np.argtypes = (ctypes.c_int, ctypes.c_int)
    _LIBC.acl_get_fd_np.restype = ctypes.c_void_p
    _LIBC.acl_get_link_np.argtypes = (ctypes.c_char_p, ctypes.c_int)
    _LIBC.acl_get_link_np.restype = ctypes.c_void_p
    _LIBC.acl_free.argtypes = (ctypes.c_void_p,)
    _LIBC.acl_free.restype = ctypes.c_int


def require_no_extended_acl(target: Path | int) -> None:
    if sys.platform != "darwin":
        return
    if isinstance(target, int):
        acl = _LIBC.acl_get_fd_np(target, _ACL_TYPE_EXTENDED)
    else:
        acl = _LIBC.acl_get_link_np(os.fsencode(target), _ACL_TYPE_EXTENDED)
    if acl:
        _LIBC.acl_free(acl)
        raise PermissionError("extended ACL is incompatible with owner-only storage")
    # Darwin reports ENOENT when the checked object has no extended ACL.
    if ctypes.get_errno() != errno.ENOENT:
        raise PermissionError("could not verify extended ACL")
