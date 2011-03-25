from array_types import *
import numpy as np

real64 = np.empty((2,2), dtype=np.float64, order='F')
real32 = np.empty((2,2), dtype=np.float32, order='F')

__doc__ = u'''\
>>> np.all(array_types(real64)[0] == np.array([[ 1.,  1.], [ 1.,  1.]]))
True
>>> np.all(array_types(real32)[0] == np.array([[ 1.,  1.], [ 1.,  1.]]))
True
'''
