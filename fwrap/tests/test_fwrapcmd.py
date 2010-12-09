#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

from pprint import pprint
import tempfile
import shutil
import os
from textwrap import dedent
from nose.tools import ok_, eq_, set_trace, assert_raises, with_setup

from fwrap import git
from fwrap import configuration
from fwrap.git import checkout, merge

temprepo = None
reporev = None

def ne_(a, b):
    assert a != b, "%r == %r (expected !=)" % (a, b)

def dump(filename, contents, commit=False, mode='w'):
    with file(filename, mode) as f:
        f.write(dedent(contents))
    if commit:
        git.add([filename])
        git.commit('Changed %s' % filename)

def append(filename, contents, commit=False):
    dump(filename, contents, commit, 'a')

def load(filename):
    with file(filename) as f:
        return f.read()

def ls():
    files = os.listdir('.')
    files.sort()
    return [x for x in files if x not in ('README', '.git')]

def fwrap(args, fail=False):
    args = ['fwrap'] + args.split()
    if fail:
        retcode, result, err = git.execproc_canfail(args)
        ok_(retcode != 0)
    else:
        result, err = git.execproc(args, get_err=True)
    return result + '\n' + err

def dump_f90(name='foo', commit=False):
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
    ''' % dict(name=name), commit=commit)
    
def dump_f(commit=False):
    dump('test.f', '''
    C
           subroutine sfoo(x, y, z)
           implicit none
           real x, y, z
           x = x * 2
           y = y * 3
           z = z * 4
           end subroutine
    ''', commit=commit)

def dump_pyf(commit=False):
    # Reorder x and y arguments and provide default value for z
    dump('test.pyf', '''
    python module test
        interface
            subroutine sfoo(y, x, z)
            callstatement (*f2py_func)(&x, &y, &z)
            real, intent(in,out) :: z = 0
            real, intent(in,out) :: x, y
            end subroutine
        end interface
    end python module
    ''', commit=commit)

def setup_tempdir():
    global temprepo
    temprepo = tempfile.mkdtemp(prefix='fwraptests-')    
    os.chdir(temprepo)

def teardown_tempdir():
    global temprepo
    shutil.rmtree(temprepo)    

def setup_temprepo():
    global temprepo, reporev
    setup_tempdir()
    print git.execproc(['git', 'init'])
    dump('README', 'temporary directory')
    git.add(['README'])
    git.commit('Initial commit (needed to exist for some git commands)')
    reporev = git.cwd_rev()

def teardown_temprepo():
    teardown_tempdir()

def assert_committed():
    global reporev
    new_rev = git.cwd_rev()
    ne_(new_rev, reporev)
    reporev = new_rev

def assert_no_commit():
    global reporev
    new_rev = git.cwd_rev()
    eq_(new_rev, reporev)
    

with_temprepo = with_setup(setup_temprepo, teardown_temprepo)
with_tempdir = with_setup(setup_tempdir, teardown_tempdir)


@with_temprepo
def test_create():
    dump_f90()
    fwrap('create --nocommit test.pyx test.f90')
    assert_no_commit()
    fwrap('create test.pyx test.f90')
    assert_committed()

    eq_(ls(), ['fparser.log', 'fwrap_type_specs.in', 'test.f90', 'test.pxd',
               'test.pyx', 'test_fc.f90', 'test_fc.h', 'test_fc.pxd'])

    fwrap('create test.pyx test.f90') # no files changed, no new commit
    assert_no_commit()
    
    # Check the self-sha1
    pyx = load('test.pyx')
    sha = configuration.get_self_sha1(pyx)
    ok_(sha in pyx)
    eq_(sha, configuration.get_self_sha1(pyx.replace(sha, 'FOO')))

    # Check guard against overwrite on diry
    dump('test.pyx', 'overwrite with this')
    out = fwrap('create test.pyx test.f90', fail=True)
    ok_('state not clean' in out)
    out = fwrap('create -f test.pyx test.f90', fail=True)
    ok_('state not clean' in out)
    out = fwrap('create -f --nocommit test.pyx test.f90')
    eq_(load('test.pyx'), pyx)
    assert_no_commit()
    

@with_tempdir
def test_create_nogit():
    dump_f90()
    fwrap('create test.pyx test.f90')
    pyx = load('test.pyx')
    # Check the self-sha1
    sha = configuration.get_self_sha1(pyx)
    ok_(sha in pyx)
    eq_(sha, configuration.get_self_sha1(pyx.replace(sha, 'FOO')))

    out = fwrap('create test.pyx test.f90', fail=True)
    ok_('use "create -f' in out)

@with_temprepo
def test_templates():
    # Make sure .pyx.in is added, and not .pyx
    dump_f90()
    fwrap('create --detect-templates test.pyx.in test.f90')
    ok_('test.pyx.in' in ls())
    ok_('test.pyx' not in ls())

@with_temprepo
def test_update():
    dump_f90('foo', commit=True)
    fwrap('create test.pyx test.f90')
    assert_committed()

    # Changeless update
    fwrap('update test.pyx')
    assert_no_commit()
    merge('_fwrap')
    ok_('foo' in load('test.pyx'))
    assert_no_commit()

    # Update Fortran file, no changes to pyx
    dump_f90('bar', commit=True)
    out = fwrap('update test.pyx')
    eq_(git.current_branch(), 'master')
    ok_('bar' not in load('test.pyx'))
    merge('_fwrap')
    ok_('bar' in load('test.pyx'))
    assert_committed()

    # Update pyx and Fortran file
    append('test.pyx', 'disruptive manual change', commit=False)
    out = fwrap('update test.pyx', fail=True)
    ok_('git state not clean' in out)
    git.commit('Manual change to test.pyx', ['test.pyx'])
    dump_f90('baz', commit=True)

    # Do the update with existing _fwrap branch
    checkout('_fwrap')
    ok_('baz' not in load('test.f90'))
    checkout('master')
    ok_('baz' in load('test.f90'))
    fwrap('update test.pyx')
    eq_(git.current_branch(), 'master')
    checkout('_fwrap')
    ok_('baz' in load('test.pyx'))    
    checkout('master')
    ok_('baz' not in load('test.pyx'))

    # Delete the _fwrap branch without merging
    git.execproc(['git', 'branch', '-D', '_fwrap'])
    ok_('baz' not in load('test.pyx'))
    
    # ...and do update again, forcing a reconstruct of _fwrap branch
    fwrap('update test.pyx')
    ok_('baz' not in load('test.pyx'))
    merge('_fwrap')
    ok_('baz' in load('test.pyx'))
    
## @with_temprepo
## def test_withpyf():
##     dump_f()
##     dump_pyf()
##     fwrap('create test.pyx test.f')
##     fwrap('')
##     eq_(ls(), ['fparser.log', 'fwrap_type_specs.in', 'test.f90', 'test.pxd',
##                'test.pyx', 'test_fc.f90', 'test_fc.h', 'test_fc.pxd'])
