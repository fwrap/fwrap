#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

import os

FWRAP_PATH = os.path.abspath(os.path.dirname(__file__))
RESOURCE_PATH = os.path.join(FWRAP_PATH, 'resources')



def create_singlemodule_build(project_name, target_path):
    with file(os.path.join(target_path, 'wscript'), 'w') as f:
        f.write(WSCRIPT_TEMPLATE)


WSCRIPT_TEMPLATE = '''
top = '.'
out = 'build'

def options(opt):
    opt.load('compiler_c')
    opt.load('compiler_fc')
    opt.load('python')
    opt.load('inplace', tooldir='tools')

def configure(conf):
    cfg = conf.path.find_resource('fwrap.config.py')
    if cfg:
        conf.env.load(cfg.abspath())

    conf.load('compiler_c')
    conf.load('compiler_fc')
    conf.check_fortran()
    conf.check_fortran_verbose_flag()
    conf.check_fortran_clib()

    conf.load('python')
    conf.check_python_version((2,5))
    conf.check_python_headers()

    conf.check_tool('numpy', tooldir='tools')
    conf.check_numpy_version(minver=(1,3))
    conf.check_tool('cython', tooldir='tools')
    conf.check_cython_version(minver=(0,11,1))
    conf.check_tool('fwrapktp', tooldir='tools')
    conf.check_tool('inplace', tooldir='tools')

    conf.add_os_flags('INCLUDES')
    conf.add_os_flags('LIB')
    conf.add_os_flags('LIBPATH')
    conf.add_os_flags('STLIB')
    conf.add_os_flags('STLIBPATH')

def build(bld):
    %(BUILD_BODY)s

# vim:ft=python

'''

