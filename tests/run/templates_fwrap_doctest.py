from templates import *
import numpy as np
from pprint import pprint

#
# The testcase is very simple and not very exciting;
# the point is what Cython code is generated with
# the --detect-templates switch.
#

__doc__ = u"""
    >>> def call(func, dtype): pprint(func(5, np.arange(5).astype(dtype)))
    >>> call(sfoo, np.float32)
    (array([ 0.,  1.,  2.,  3.,  4.], dtype=float32),
     array([ 0.,  1.,  2.,  3.,  4.], dtype=float32))
    >>> call(dfoo, np.float64)
    (array([ 0.,  2.,  4.,  6.,  8.]), array([ 0.,  2.,  4.,  6.,  8.]))
    >>> call(cfoo, np.complex64)
    (array([  0.+0.j,   3.+0.j,   6.+0.j,   9.+0.j,  12.+0.j], dtype=complex64),
     array([  0.,   3.,   6.,   9.,  12.], dtype=float32))
    >>> call(zfoo, np.complex128)
    (array([  0.+0.j,   4.+0.j,   8.+0.j,  12.+0.j,  16.+0.j]),
     array([  0.,   4.,   8.,  12.,  16.]))

    >>> other(5, np.arange(5))
    array([ 0.,  1.,  2.,  3.,  4.])
    >>> gfoo(5, np.arange(5))
    (array([ 0.,  1.,  2.,  3.,  4.]), array([ 0.,  1.,  2.,  3.,  4.]))


    >>> slass(4, 'a'), dlass(4, 'a'), class__(4, 'a'), zlass(4, 'a')
    (8.0, 8.0, (8+0j), (8+0j))

    >>> apple(2)
    4.0
    >>> orange(2)
    4.0
"""
