from f77callback_fwrap import *
import numpy as np

def getarr(n):
    return np.arange(n * n, dtype=np.float64).reshape(n, n)

def assertarr(arr, n):
    assert arr.shape == (n, n)
    assert np.all(arr.ravel() == np.arange(n * n))

def callback(a, b, n):
    print type(a)
    print a
    print type(b)
    print b
    print type(n)
    print n
    rb = b.copy()
    rb[...] = 2
    return 10, rb, n

class Nested(object):
    def __init__(self, action=lambda: None):
        self.trace = []
        self.action = action

    def level3(self, a, b, n):
        assert a == 6 and n == 3
        assertarr(b, n)
        self.trace.append('(3)')
        self.action()
        return a, b, n

    def level2(self, a, b, n):
        assert a == 4 and n == 2
        assertarr(b, n)
        self.trace.append('<2')
        try:
            for i in range(2):
                caller(self.level3, 6, getarr(3), 3)
            self.trace.append('2>')
        except:
            self.trace.append('2@')
            raise
        return a, b, n

    def level1(self, a, b, n):
        assert a == 1 and n == 1
        assertarr(b, n)
        self.trace.append('<1')
        try:
            for i in range(2):
                caller(self.level2, 4, getarr(2), 2)
            self.trace.append('1>')
        except:
            self.trace.append('1@')
            raise
        return a, b, n

    def run(self):
        caller(self.level1, 1, getarr(1), 1)

    def __repr__(self):
        return ' '.join(self.trace)

class MyException(Exception):
    pass

def raise_MyException_1():
    raise MyException()

def raise_MyException_2():
    raise MyException, 'message'

def raise_MyException_3():
    raise MyException('message')

def wrongshape(a, b, n):
    return a, [[0]], n

__doc__ = u"""
    >>> n = 3
    >>> a = 10
    >>> b = np.arange(3*3, dtype=np.float64).reshape((n,n))
    >>> _ = caller(callback, a, b, n)
    <type 'int'>
    10
    <type 'numpy.ndarray'>
    [[ 0.  1.  2.]
     [ 3.  4.  5.]
     [ 6.  7.  8.]]
    <type 'int'>
    3

    >>> m = Nested(); m.run(); m
    <1 <2 (3) (3) 2> <2 (3) (3) 2> 1>

    >>> m = Nested(raise_MyException_1); m.run()
    Traceback (most recent call last):
        ...
    MyException
    >>> m
    <1 <2 (3) 2@ 1@

    >>> m = Nested(raise_MyException_2); m.run()
    Traceback (most recent call last):
        ...
    MyException: message
    >>> m
    <1 <2 (3) 2@ 1@

    >>> m = Nested(raise_MyException_3); m.run()
    Traceback (most recent call last):
        ...
    MyException: message
    >>> m
    <1 <2 (3) 2@ 1@


    >>> caller(wrongshape, a, b, n)
    Traceback (most recent call last):
        ...
    ValueError: Array returned from callback has illegal shape
    
"""
