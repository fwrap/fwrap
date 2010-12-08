import os
if int(os.environ['F2PY']):
    from f2py_comparison_f2py import *
else:
    from f2py_comparison_fwrap import *
import numpy as np

def raises_error(func, *args, **kw):
    try:
        func(*args)
        return False
    except:
        return True

def func_nocopy(in_, n=None, m=None):
    answer_from_input = func(in_, n, m) # just make sure this works
    in_as_arr = np.asarray(in_, dtype=np.int32, order='F')
    result = func(in_as_arr, n, m)
    assert np.all(result == answer_from_input)
    assert result.shape == answer_from_input.shape
    if result is not in_as_arr:
        # Known difference for scalars in f2py
        assert int(os.environ['F2PY']) and result.ndim == in_as_arr.ndim == 0
    return result        

__doc__ = u"""

Basic case, 2D-to-2D::

    >>> func_nocopy([[0,0,0]])
    array([[1, 2, 3]], dtype=int32)
    >>> func_nocopy([[0,0],[0,0]])
    array([[1, 2],
           [3, 4]], dtype=int32)


Pass scalar and 0-len arrays:

    >>> func_nocopy(3, 1, 1)
    array(1, dtype=int32)
    >>> func_nocopy([])
    array([], dtype=int32)
    >>> func_nocopy([], 1, 0)
    array([], dtype=int32)

    
Pass 1D arrays; shape gets padded with 1-dims on right side::
    
    >>> func_nocopy([0,0,0])
    array([1, 2, 3], dtype=int32)
    >>> func_nocopy([0,0,0], 3, 1)
    array([1, 2, 3], dtype=int32)
    >>> raises_error(func, [0,0,0], 1, 3)
    True

Pass array > 2D, temporarily viewed as (2,3) internally::
    
    >>> a = np.array([[[
    ...    [[  [[0]],  [[0]],  [[0]]  ]],
    ...    [[  [[0]],  [[0]],  [[0]]  ]],
    ... ]]], dtype=np.int32, order='F')
    >>> r = func_nocopy(a)
    >>> a.shape
    (1, 1, 2, 1, 3, 1, 1)
    >>> r.shape
    (1, 1, 2, 1, 3, 1, 1)
    >>> a.ravel()
    array([1, 2, 3, 4, 5, 6], dtype=int32)
    >>> r.ravel()
    array([1, 2, 3, 4, 5, 6], dtype=int32)


Require flattening of dimension; (2,2,2) treated as (2,2,4)::

    >>> a = [[0,0],[0,0]]
    >>> b = [a, a]
    >>> func_nocopy(b)
    array([[[1, 3],
            [2, 4]],
    <BLANKLINE>
           [[5, 7],
            [6, 8]]], dtype=int32)
    >>> func_nocopy(b, 2, 4)
    array([[[1, 3],
            [2, 4]],
    <BLANKLINE>
           [[5, 7],
            [6, 8]]], dtype=int32)

    >>> raises_error(func, b, 2, 3)
    True
    >>> raises_error(func, b, 4, 2)
    True
"""
