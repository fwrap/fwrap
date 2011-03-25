from f77 import *
import numpy as np

n1, n2 = 3, 4
ain = np.empty((n1,n2), dtype=np.float32, order='F')
aout = ain.copy('F')
ainout = ain.copy('F')
ano = ain.copy('F')

aout_ = aout.copy('F')
ainout_ = ainout.copy('F')
ano_ = ano.copy('F')

def init():
    ain.fill(2.0)
    aout.fill(0.0)
    ainout.fill(34.0)
    ano.fill(0.0)

    aout_[...] = ain
    ano_[...] = ainout
    ainout_[...] = ain + ano_


def test_results(func, args, results):
    res_ = func(*args)
    for r1, r2 in zip(res_, results):
        if not np.all(r1 == r2):
            print r1
            print r2
            return False
    return True


class MyTrue(object):
    def __nonzero__(self):
        return True

class MyFalse(object):
    def __nonzero__(self):
        return False

__doc__ = u'''
    >>> int_default(1,2) == (6, 2)
    True
    >>> int_x_len(1,2,4,5,7,8,10,11) == (2, 3, 5, 9, 8, 15, 11L, 21L)
    True
    >>> int_kind_x(1,2,4,5,7,8,10,11) == (2, 3, 5, 9, 8, 15, 11L, 21L)
    True


    >>> init()
    >>> test_results(explicit_shape, (n1, n2, ain, aout, ainout, ano), (aout_, ainout_, ano_))
    True
    >>> init()
    >>> test_results(assumed_size, (n1, n2, ain, aout, ainout, ano), (aout_, ainout_, ano_))
    True

    >>> double_if_a('B', 8), double_if_a('A', 8)  # TODO Python 3
    (8, 16)
    
    >>> emit_f() # TODO Python 3
    'F'

    >>> explicit_shape(n1 + 1, n2, ain, aout, ainout, ano)
    Traceback (most recent call last):
        ...
    ValueError: (n1 == ain.shape[0]) not satisifed

    >>> explicit_shape(n1, n2 + 1, ain, aout, ainout, ano)
    Traceback (most recent call last):
        ...
    ValueError: (0 <= n2 <= ain.shape[1]) not satisifed

    >>> r1, r2, r3 = explicit_shape(n1, n2 - 1, ain, aout, ainout, ano)
    >>> np.all(r1[:, :n2-1] == ain[:, :n2-1])
    True
    >>> np.all(r2[:, :n2-1] == ain[:, :n2-1] + ainout_[:, :n2-1])
    True
    >>> np.all(r3[:, :n2-1] == ainout_[:, :n2-1])
    True
    
    >>> onedee(4, np.zeros(4, dtype=np.int32))
    (4, array([1, 2, 3, 4], dtype=int32))
    >>> onedee(3, np.zeros(4, dtype=np.int32))
    (3, array([1, 2, 3, 0], dtype=int32))
    >>> onedee(4, np.zeros(3, dtype=np.int32))
    Traceback (most recent call last):
        ...
    ValueError: (0 <= n <= x.shape[0]) not satisifed


    >>> logicalfunc(True)
    (10, 1)
    >>> logicalfunc(False)
    (0, 0)
    >>> logicalfunc(MyTrue())
    (10, 1)
    >>> logicalfunc(MyFalse())
    (0, 0)


Strings::

    >>> withstring(10, 'a' * 10)
    (10, 'aaaaaaaaaa')
    >>> withstring(10, 'a' * 8)[0]
    10
'''
