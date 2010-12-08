import os
if int(os.environ['F2PY']):
    from f2py_comparison_f2py import *
else:
    from f2py_comparison_fwrap import *
import numpy as np

#
# TODO: 2D -- are 1 inserted on the right end?
#

__doc__ = u"""
    >>> func([[0,0,0]])
    array([[1, 2, 3]], dtype=int32)
    >>> func([0,0,0])
    array([1, 2, 3], dtype=int32)
    >>> a = np.array([[[
    ...    [[  [[0]],  [[0]],  [[0]]  ]],
    ...    [[  [[0]],  [[0]],  [[0]]  ]],
    ... ]]], dtype=np.int32, order='F')
    >>> r = func(a)
    >>> a.shape
    (1, 1, 2, 1, 3, 1, 1)
    >>> r.shape
    (1, 1, 2, 1, 3, 1, 1)
    >>> a.ravel()
    array([1, 2, 3, 4, 5, 6], dtype=int32)
    >>> r.ravel()
    array([1, 2, 3, 4, 5, 6], dtype=int32)

"""
