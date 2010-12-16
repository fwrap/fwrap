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

Out arrays::

    >>> out_arr(2, 3)
    array([[1, 2, 3],
           [4, 5, 6]], dtype=int32)


depend effect on array vs. array size::

    # array_given_n: arr,n
    # array_given_n: n,arr
    # n_given_array: arr,[n]
    # n_given_array_argrev: n, arr

    >>> nodeps(np.zeros(4, dtype=np.int32), 4)
    array([1, 2, 3, 4], dtype=int32)
    >>> nodeps(np.zeros(4, dtype=np.int32), 3)
    array([1, 2, 3, 0], dtype=int32)
    >>> raises_error(nodeps, np.zeros(4, dtype=np.int32), 5)
    True

    # >>> nodeps(np.zeros(4, dtype=np.int32))
    # array([1, 2, 3, 4], dtype=int32)


    >>> array_given_n(np.zeros(4, dtype=np.int32), 4)
    array([1, 2, 3, 4], dtype=int32)

    >>> raises_error(array_given_n, np.zeros(4, dtype=np.int32), 3)
    True

    >>> raises_error(array_given_n, np.zeros(4, dtype=np.int32), 5)
    True

    >>> raises_error(array_given_n, np.zeros(4, dtype=np.int32))
    True

    >>> array_given_n_argrev(4, np.zeros(4, dtype=np.int32))
    array([1, 2, 3, 4], dtype=int32)
    >>> raises_error(array_given_n_argrev, 5, np.zeros(4, dtype=np.int32))
    True
    >>> raises_error(array_given_n_argrev, 3, np.zeros(4, dtype=np.int32))
    True

    >>> raises_error(array_given_n_argrev, np.zeros(4, dtype=np.int32))
    True

    >>> n_given_array(np.zeros(4, dtype=np.int32), 4)
    array([1, 2, 3, 4], dtype=int32)
    >>> n_given_array(np.zeros(4, dtype=np.int32), 3)
    array([1, 2, 3, 0], dtype=int32)
    >>> raises_error(n_given_array, np.zeros(4, dtype=np.int32), 5)
    True
    >>> n_given_array(np.zeros(4, dtype=np.int32))
    array([1, 2, 3, 4], dtype=int32)

    >>> n_given_array_argrev(4, np.zeros(4, dtype=np.int32))
    array([1, 2, 3, 4], dtype=int32)
    >>> n_given_array_argrev(3, np.zeros(4, dtype=np.int32))
    array([1, 2, 3, 0], dtype=int32)

    #>>> raises_error(n_given_array_argrev, np.zeros(4, dtype=np.int32))
    #True

    #>>> n_given_array_argrev(5, np.zeros(4, dtype=np.int32))

##     >>> tricky_case(5, np.zeros(5, dtype=np.int32))
##     array([1, 2, 3, 4, 5], dtype=int32)

##     >>> tricky_case(None, np.zeros(5, dtype=np.int32))
##     array([1, 2, 3, 0, 0], dtype=int32)



    >>> swilk(np.arange(10, dtype=np.float32), np.zeros(5, dtype=np.float32))
    array([  1.,   4.,   7.,  10.,  13.], dtype=float32)

    >>> raises_error(swilk, np.arange(10, dtype=np.float32), np.zeros(4, dtype=np.float32))
    True
    >>> raises_error(swilk, np.arange(10, dtype=np.float32), np.zeros(6, dtype=np.float32))
    True


Type casting::

    >>> array_given_n(np.zeros(4, dtype=np.int16), 4)
    array([1, 2, 3, 4], dtype=int32)
    >>> array_given_n(np.zeros(4, dtype=np.int64), 4)
    array([1, 2, 3, 4], dtype=int32)
    >>> array_given_n(np.zeros(4, dtype=np.float32), 4)
    array([1, 2, 3, 4], dtype=int32)
    >>> array_given_n(np.zeros(4, dtype=np.complex128), 4)
    array([1, 2, 3, 4], dtype=int32)


"""

