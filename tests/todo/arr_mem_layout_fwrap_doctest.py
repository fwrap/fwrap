from arr_mem_layout import mem_layout
import numpy as np

__doc__ = u'''
>>> a = np.arange(10).reshape(5,2).copy()
>>> mem_layout(a.T)
>>> mem_layout(a.T.copy())
'''
