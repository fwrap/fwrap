from array_errors_fwrap import *

__doc__ = u"""
    >>> func(2, 3, 0, 0)
    Traceback (most recent call last):
        ...
    ValueError: object of too small depth for desired array

    >>> func([2], [3], 0, 0)
    Traceback (most recent call last):
        ...
    ValueError: setting an array element with a sequence.

    >>> func([[]], [[]], 0, 0)
    Traceback (most recent call last):
        ...
    RuntimeError: an error was encountered when calling the 'func' wrapper.
    >>> func([[]], [[]], 1, 0)
    (array([], shape=(1, 0), dtype=float32), array([], shape=(1, 0), dtype=float32))
    >>> func([[2]], [[3]], 1, 1)
    (array([[ 2.]], dtype=float32), array([[ 3.]], dtype=float32))
    >>> func([[2]], [[3]], 0, 0)
    Traceback (most recent call last):
        ...
    RuntimeError: an error was encountered when calling the 'func' wrapper.

"""
