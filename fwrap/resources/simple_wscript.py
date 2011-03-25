#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

top = '.'
out = 'build'

def options(opt):
    opt.add_option('--name', action='store', default='fwproj')
    opt.add_option('--outdir', action='store', default='fwproj')
    opt.add_option('--pyf', action='store')
    opt.add_option('--f77binding', action='store_true', default=False)
    opt.add_option('--detect-templates', action='store_true', default=False)
    opt.add_option('--template', action='append')
    opt.add_option('--emulate-f2py', action='store_true')
    opt.add_option('--no-cpdef', action='store_true')
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
    conf.check_tool('fwraptool', tooldir='tools')
    conf.check_tool('fwrapktp', tooldir='tools')
    conf.check_tool('inplace', tooldir='tools')
     
    conf.add_os_flags('INCLUDES')
    conf.add_os_flags('LIB')
    conf.add_os_flags('LIBPATH')
    conf.add_os_flags('STLIB')
    conf.add_os_flags('STLIBPATH')
    conf.add_os_flags('FWRAPFLAGS')

def build(bld):

    bld(
        features = 'c fc pyext fwrap cshlib',
        source = bld.srcnode.ant_glob(incl=['*.f', '*.F', '*.f90', '*.F90']),
        use = 'fcshlib CLIB NUMPY',
        includes = ['.'],
        )

# vim:ft=python
