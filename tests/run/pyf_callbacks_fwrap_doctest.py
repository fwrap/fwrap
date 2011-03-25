from pyf_callbacks import *
import numpy as np

def twice(x, extra=None):
    if extra is not None:
        assert np.all(x == extra)
    return 2 * x

def twice_with_extra(x, a, b, c):
    assert (a, b, c) == (1, 2, 3)
    return 2 * x

__doc__ = u'''

    >>> foo(twice, 3)
    6

#    >>> foo(twice_with_extra, 3, callback_extra_args=(1, 2, 3))
#    6

    >>> array2d(twice, np.ones((3, 3)), 3, 3)
    array([[ 2.,  2.,  2.],
           [ 2.,  2.,  2.],
           [ 2.,  2.,  2.]])

'''
