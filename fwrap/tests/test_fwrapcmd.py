#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn, Miguel de Val-Borro
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

from textwrap import dedent
from nose.tools import ok_, eq_, set_trace, assert_raises, with_setup

from fwrap import configuration

def load(filename):
    with file(filename) as f:
        return f.read()

def dump(filename, contents, mode='w'):
    with file(filename, mode) as f:
        f.write(dedent(contents))

def dump_f90(name='foo'):
    dump('test.f90', '''
    subroutine s%(name)s(x)
    implicit none
    real, intent(in) :: x
    x = x * 2
    end subroutine

    subroutine dfoo(x)
    implicit none
    real, intent(in) :: x
    x = x * 2
    end subroutine
    ''' % dict(name=name))

def test_compile():
    dump_f90()
    fwrap('compile test.f90')
    so = load('test.so')
    # Check the self-sha1
    sha = configuration.get_self_sha1(so)
    ok_(sha in so)
    eq_(sha, configuration.get_self_sha1(so.replace(sha, 'FOO')))
