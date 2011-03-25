from outarrays import *

#
# Check that explicit-shape intent(out) arrays can be
# created automatically
#



__doc__ = u'''
    >>> explicit_shape(2, 3)
    array([[ 0.,  1.,  2.],
           [ 3.,  4.,  5.]])
    >>> explicit_shape(2, 3, None)
    array([[ 0.,  1.,  2.],
           [ 3.,  4.,  5.]])
    >>> arr = np.zeros((2, 3), order='F')
    >>> explicit_shape(2, 3, arr) is arr
    True

Check that auto-allocated array is zeroed out (following
the behaviour of f2py):

    >>> noop(10)
    array([ 0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.,  0.])
'''
