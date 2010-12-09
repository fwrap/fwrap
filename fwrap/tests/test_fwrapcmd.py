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

def ne_(a, b):
    assert a != b, "%r == %r (expected !=)" % (a, b)

def dump(filename, contents):
    with file(filename, 'w') as f:
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

def dump_f90():
    dump('test.f90', '''
    subroutine sfoo(x)
    implicit none
    real, intent(in) :: x
    x = x * 2
    end subroutine

    subroutine dfoo(x)
    implicit none
    real, intent(in) :: x
    x = x * 2
    end subroutine
    ''')

def setup_tempdir():
    global temprepo
    temprepo = tempfile.mkdtemp(prefix='fwraptests-')    
    os.chdir(temprepo)

def teardown_tempdir():
    global temprepo
    shutil.rmtree(temprepo)    

def setup_temprepo():
    global temprepo
    setup_tempdir()
    print git.execproc(['git', 'init'])
    dump('README', 'temporary directory')
    git.add(['README'])
    git.commit('Initial commit (needed to exist for some git commands)')


def teardown_temprepo():
    teardown_tempdir()

with_temprepo = with_setup(setup_temprepo, teardown_temprepo)
with_tempdir = with_setup(setup_tempdir, teardown_tempdir)


@with_temprepo
def test_create():
    dump_f90()
    rev1 = git.cwd_rev()
    fwrap('create --nocommit test.pyx test.f90')
    eq_(rev1, git.cwd_rev())    
    fwrap('create test.pyx test.f90')
    rev2 = git.cwd_rev()
    ne_(rev2, rev1)

    eq_(ls(), ['fparser.log', 'fwrap_type_specs.in', 'test.f90', 'test.pxd',
               'test.pyx', 'test_fc.f90', 'test_fc.h', 'test_fc.pxd'])

    fwrap('create test.pyx test.f90') # no files changed, no new commit
    eq_(rev2, git.cwd_rev())
    
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
    eq_(rev2, git.cwd_rev())
    

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
    print fwrap('create --detect-templates test.pyx.in test.f90')
    ok_('test.pyx.in' in ls())
    ok_('test.pyx' not in ls())
