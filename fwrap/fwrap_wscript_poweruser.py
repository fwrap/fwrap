#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

top = '.'
out = 'build'

def options(opt):
    opt.load('compiler_c')
    opt.load('compiler_fc')
    opt.load('python')

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

    conf.add_os_flags('INCLUDES')
    conf.add_os_flags('LIB')
    conf.add_os_flags('LIBPATH')
    conf.add_os_flags('STLIB')
    conf.add_os_flags('STLIBPATH')

def foo(task):
    1/0

def build(bld):
    y =bld(
        name='wrapperbld',
        features = 'c pyext cshlib',
        source = (bld.srcnode.ant_glob(incl=['basic_package_fwrap/*.pyx'])),
#        typemap = 'basic_package_fwrap/fwrap_type_specs.in',
#        wrapper = 
#        typemap = 'fwrap_type_specs.in',
        target = 'basic_package_fwrap',
        use = 'fcshlib CLIB NUMPY myfortranlib',
        includes = ['.', 'basic_package_fwrap'],
        install_path = bld.srcnode.abspath(),
#        after = 'typemap'
    )

    x = bld.process_typemap(
#        rule=foo,
        name='typemap',
        source = ['basic_package_fwrap/fwrap_type_specs.in'],
        target = [
             'basic_package_fwrap/fwrap_ktp_mod.f90',
             'basic_package_fwrap/fwrap_ktp_header.h',
             'basic_package_fwrap/fwrap_ktp.pxd',
             'basic_package_fwrap/fwrap_ktp.pxi'],
#        before='wrapperbld'
         )
    x.set_after(y)
    bld(
        features = 'fc fcshlib',
        source = bld.srcnode.ant_glob(incl=['src/*.f', 'src/*.F', 'src/*.f90', 'src/*.F90']),
        target = 'myfortranlib',
#        use = 'fcshlib',
        includes = ['.', 'basic_package_fwrap'],
        install_path = bld.srcnode.abspath(),
    )


    bld(
        rule = 'touch ${TGT}',
        target = '__init__.py',
        install_path = bld.srcnode.abspath(),
        )


# vim:ft=python
