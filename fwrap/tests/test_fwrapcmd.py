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

def fwrap(args, fail=False):
    args = ['fwrap'] + args.split()
    if fail:
        retcode, result, err = git.execproc_canfail(args)
        ok_(retcode != 0)
    else:
        result, err = git.execproc(args, get_err=True)
    return result + '\n' + err

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

def setup_tempdir():
    global temprepo, _keeprepo
    _keeprepo = False
    temprepo = tempfile.mkdtemp(prefix='fwraptests-')    
    os.chdir(temprepo)

def teardown_tempdir():
    global temprepo, _keeprepo
    if not _keeprepo:
        shutil.rmtree(temprepo)
    else:
        print 'Please inspect and remove %s' % temprepo

with_tempdir = with_setup(setup_tempdir, teardown_tempdir)

@with_tempdir
def test_compile():
    dump_f90()
    fwrap('compile test.f90')
    so = load('test.so')
