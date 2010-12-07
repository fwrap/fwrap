#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

from fwrap import git

from pprint import pprint
import tempfile
import shutil
import os
from textwrap import dedent
from nose.tools import ok_, eq_, set_trace, assert_raises, with_setup

temprepo = None

def dump(filename, contents):
    with file(filename, 'w') as f:
        f.write(dedent(contents))

def fwrap(args):
    git.execproc(['fwrap'] + args.split())

def dump_f():
    dump('test.f', '''
    C
           subroutine sfoo(x)
           implicit none
           real x
           x = x * 2
           end subroutine

           subroutine dfoo(x)
           implicit none
           real*8 x
           x = x * 2
           end subroutine
    ''')

def setup_temprepo():
    global temprepo
    temprepo = tempfile.mkdtemp(prefix='fwraptests-')    
    os.chdir(temprepo)
    print git.execproc(['git', 'init'])
    dump('README', 'temporary directory')
    git.add(['README'])
    git.commit('Initial commit (needed to exist for some git commands)')


def teardown_temprepo():
    global temprepo
    shutil.rmtree(temprepo)

with_temprepo = with_setup(setup_temprepo, teardown_temprepo)

@with_temprepo
def test_templates():
    # Make sure .pyx.in is added, and not .pyx
    dump_f()
    print fwrap('create --f77binding --detect-templates --versioned '
                'test.pyx.in test.f')
    print git.execproc(['ls'])


