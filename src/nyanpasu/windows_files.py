from __future__ import annotations

import ctypes
import msvcrt
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

import pywintypes
import win32con
import win32file

if TYPE_CHECKING:
    from collections.abc import Generator


@contextmanager
def open_windows_file(root: Path, relative: Path) -> Generator[BinaryIO]:
    """Pin each directory against rename and reject every reparse point.

    Omitting FILE_SHARE_DELETE keeps validated ancestors in place until the
    stream closes. OPEN_REPARSE_POINT opens the link itself, never its target.
    """
    with ExitStack() as stack:
        value = str(root.absolute())
        if not value.startswith("\\\\?\\"):
            value = "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value
        path = Path(value)
        for index, component in enumerate((None, *relative.parts)):
            if component is not None:
                path = path / component
            try:
                handle = win32file.CreateFile(
                    str(path),
                    win32con.GENERIC_READ,
                    # Pin directories against reparse-point conversion as well as rename.
                    win32con.FILE_SHARE_READ | (win32con.FILE_SHARE_WRITE if index == len(relative.parts) else 0),
                    None,
                    win32con.OPEN_EXISTING,
                    win32file.FILE_FLAG_OPEN_REPARSE_POINT | win32con.FILE_FLAG_BACKUP_SEMANTICS,
                    None,
                )
            except pywintypes.error as exc:
                # History readers rely on FileNotFoundError for compressed-file fallback.
                raise ctypes.WinError(exc.winerror) from exc
            stack.callback(handle.Close)
            attributes = win32file.GetFileInformationByHandle(int(handle))[0]
            if attributes & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
                raise OSError("reparse points are not allowed")
            directory = bool(attributes & win32con.FILE_ATTRIBUTE_DIRECTORY)
            if index < len(relative.parts):
                if not directory:
                    raise NotADirectoryError(str(path))
            elif directory or win32file.GetFileType(int(handle)) != win32con.FILE_TYPE_DISK:
                raise ValueError("file must be a regular file")
        # The CRT descriptor takes ownership; the PyHANDLE becomes invalid.
        descriptor = msvcrt.open_osfhandle(int(handle.Detach()), os.O_RDONLY | os.O_BINARY)
        stream = stack.enter_context(os.fdopen(descriptor, "rb"))
        yield stream
