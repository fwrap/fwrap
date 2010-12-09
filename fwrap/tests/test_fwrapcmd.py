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

temprepo = None
reporev = None

def ne_(a, b):
    assert a != b, "%r == %r (expected !=)" % (a, b)

def dump(filename, contents):
    with file(filename, 'w') as f:
        f.write(dedent(contents))

def append(filename, contents):
    with file(filename, 'a') as f:
        f.write(dedent(contents))

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
    ok_('try -f switch' in out)

@with_temprepo
def test_templates():
    # Make sure .pyx.in is added, and not .pyx
    dump_f90()
    fwrap('create --detect-templates test.pyx.in test.f90')
    ok_('test.pyx.in' in ls())
    ok_('test.pyx' not in ls())

@with_temprepo
def test_update():
    dump_f90('foo')
    fwrap('create test.pyx test.f90')
    assert_committed()

    # Changeless update
    fwrap('update test.pyx')
    assert_no_commit()
    git.merge('_fwrap')
    assert_no_commit()

    # Update Fortran file, no changes to pyx
    dump_f90('bar')
    out = fwrap('update test.pyx')
    eq_(git.current_branch(), 'master')
    git.merge('_fwrap')
    assert_committed()

    # Update pyx and Fortran file
    append('test.pyx', 'disruptive manual change')
    out = fwrap('update test.pyx', fail=True)
    ok_('git state not clean' in out)
    git.add(['test.pyx'])
    git.commit('Manual change to test.pyx')
    dump_f90('baz')
    fwrap('update test.pyx')
    eq_(git.current_branch(), 'master')
    git.merge('_fwrap')
    git.checkout('_fwrap')
    dump('test.pyx', 'wipe out test.pyx')
    git.add(['test.pyx'])
    git.commit('Wiped out test.pyx')
    git.checkout('master')
    #os.system('git diff -U0 --raw HEAD^1 | grep -v @ | grep -v "+++" | grep -v -e "---"')
