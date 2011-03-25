from pyf_support import *
import numpy as np

#
# Check that the 4 arguments (see pyf_support.f)
# are turned into 2
#


def aligned_zeros(align, size, dtype):
    a = np.zeros(((size + align) * dtype().itemsize), dtype=np.uint8)
    z = np.frombuffer(a.data, offset=align, count=size, dtype=dtype)
    return z

__doc__ = ur"""
    >>> m, n = 2, 4
    >>> testone(m, n)
    array([[  0.,   1.,   2.,   3.],
           [  4.,   5.,   6.,   7.],
           [  8.,   9.,  10.,  11.]])
    >>> testone(m)
    array([[ 0.,  1.],
           [ 2.,  3.],
           [ 4.,  5.]])

    >>> testone(10, n) # m_hidden == m+1
    Traceback (most recent call last):
        ...
    ValueError: Condition on arguments not satisfied: (m >= 1) and (m_hidden <= 10)

    >>> testone(4, 1)
    Traceback (most recent call last):
        ...
    ValueError: Condition on arguments not satisfied: n >= 2

    >>> reorders(1, 3, np.arange(4).astype(np.int32))
    (3, 1, array([2, 2, 2, 2], dtype=int32))

Test truncating array and playing with bounds of explicit-shape array::

    >>> r = np.arange(10)
    >>> fort_sum_simple(r, 10)
    45.0
    >>> fort_sum_simple(r)
    45.0
    >>> fort_sum_simple(r, 5)
    10.0
    
    >>> fort_sum_simple(r, -1)
    Traceback (most recent call last):
    ...
    ValueError: (0 <= n <= arr.shape[0]) not satisifed
    >>> fort_sum_simple(r, 11)
    Traceback (most recent call last):
    ...
    ValueError: (0 <= n <= arr.shape[0]) not satisifed
    
    >>> fort_sum(r)
    45.0
    >>> fort_sum(r, 5)
    10.0
    >>> fort_sum(r, 10)
    45.0
    
Test offx argument::

    >>> fort_sum(r, 10, 0)
    45.0
    >>> fort_sum(r, 10, -1)
    Traceback (most recent call last):
        ...
    ValueError: Condition on arguments not satisfied: (offx >= 0) and (offx < arr.shape[0])
    >>> fort_sum(r, 10, 11)
    Traceback (most recent call last):
        ...
    ValueError: Condition on arguments not satisfied: (offx >= 0) and (offx < arr.shape[0])
    >>> fort_sum(r, 5, 5)
    35.0
    >>> fort_sum(r, 5, 6)
    Traceback (most recent call last):
        ...
    ValueError: (0 <= n <= arr.shape[0] - offx) not satisifed
    >>> fort_sum(r, 0, 9)
    0.0
    >>> fort_sum(r, 1, 9)
    9.0
    >>> fort_sum(r, 2, 9)
    Traceback (most recent call last):
        ...
    ValueError: (0 <= n <= arr.shape[0] - offx) not satisifed


    >>> fort_sum(r, offx=5)
    35.0
    >>> fort_sum(r, offx=9)
    9.0

docstring::

    >>> fort_sum.__doc__.split('\n')[0]
    'fort_sum(arr[, n, offx]) -> fw_ret_arg'
  
intent(copy) and intent(overwrite) tests::

    >>> r = np.zeros(10)
    >>> intent_copy_arange(r, 10)
    array([  1.,   2.,   3.,   4.,   5.,   6.,   7.,   8.,   9.,  10.])
    >>> r
    array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.])
    >>> _ = intent_copy_arange(r, 10, overwrite_x=True)
    >>> r
    array([  1.,   2.,   3.,   4.,   5.,   6.,   7.,   8.,   9.,  10.])

    >>> r[:] = 0
    >>> _ = intent_copy_arange(r[::2], 5, overwrite_x=True)
    >>> r
    array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.])
    >>> intent_overwrite_arange(r, 10)
    array([  1.,   2.,   3.,   4.,   5.,   6.,   7.,   8.,   9.,  10.])
    >>> r
    array([  1.,   2.,   3.,   4.,   5.,   6.,   7.,   8.,   9.,  10.])
    >>> r[:] = 0
    >>> _ = intent_overwrite_arange(r, 10, overwrite_x=False)
    >>> r
    array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.])
    >>> intent_copy_arange([0, 0, 0], 3)
    array([ 1.,  2.,  3.])
    >>> intent_copy_arange([0, 0, 1], 3, overwrite_x=True)
    array([ 1.,  2.,  3.])

Default values for arrays::

    >>> r = np.arange(10).reshape(2,5)
    >>> s, x, y, z = sum_and_fill_optional_arrays(2, 5, r.astype(np.float64))
    >>> s
    (45+0j)
    >>> x
    array([[ 1.,  1.,  1.,  1.,  1.],
           [ 1.,  1.,  1.,  1.,  1.]])
    >>> y
    array([[ 2.+3.j,  2.+3.j,  2.+3.j,  2.+3.j,  2.+3.j],
           [ 2.+3.j,  2.+3.j,  2.+3.j,  2.+3.j,  2.+3.j]])
    >>> z
    array([[4, 4, 4, 4, 4],
           [4, 4, 4, 4, 4]], dtype=int32)


    >>> s, x, y, z = sum_and_fill_optional_arrays(2, 5, r.astype(np.float64),
    ...     r.astype(np.complex128), r.astype(np.int32)); s
    (135+0j)


Auxiliary arguments::

    >>> aux_arg(10)
    12

Function masquerading as subroutine:

    >>> a_function(-1)
    (-1, 12)

Default arguments:

    >>> sdefault()
    2.0
    >>> cdefault()
    (2+0j)

Temporary array:

    >>> temparray(3, np.ones((3,), dtype=np.int32))
    array([2, 2, 2], dtype=int32)
    

alignment:

    >>> n = 3
    >>> def align_test(align):
    ...     a, b, c = [aligned_zeros(align, n, np.int32) for x in range(3)]
    ...     ap, bp, cp = alignment(n, a, b, c)
    ...     return a is ap, b is bp, c is cp
    ...
    >>> align_test(16)
    (True, True, True)
    >>> align_test(24)
    (True, True, False)
    >>> align_test(8)
    (True, True, False)
    >>> align_test(5)
    (True, False, False)

intent(inout):

    >>> x = np.zeros(4)
    >>> intent_inout_arange(x, 4) # no return value
    >>> x
    array([ 1.,  2.,  3.,  4.])

initialization of scalars:

    >>> scalars_initialized_to_zero()
    (0, 0.0, 0j, 1)

"""

