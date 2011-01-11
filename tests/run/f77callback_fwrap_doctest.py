from f77callback_fwrap import *

def callback(a, b):
    print type(a), a, type(b), b

__doc__ = u"""
    >>> caller(callback)
"""
