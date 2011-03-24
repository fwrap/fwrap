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
     
    conf.env['FW_PROJ_NAME'] = conf.options.name
    conf.env['FW_F77_BINDING'] = conf.options.f77binding
    conf.env['FW_DETECT_TEMPLATES'] = conf.options.detect_templates
    conf.env['FW_TEMPLATE'] = conf.options.template
    conf.env['FW_EMULATE_F2PY'] = conf.options.emulate_f2py
    conf.env['FW_NO_CPDEF'] = conf.options.no_cpdef
#    conf.env['FWRAP_OPTS'] = ''
    conf.env['FW_PYF'] = conf.options.pyf

    conf.add_os_flags('INCLUDES')
    conf.add_os_flags('LIB')
    conf.add_os_flags('LIBPATH')
    conf.add_os_flags('STLIB')
    conf.add_os_flags('STLIBPATH')
    conf.add_os_flags('FWRAPFLAGS')

def build(bld):
    want_f77 = bld.env['FW_F77_BINDING']
    detect_templates = bld.env['FW_DETECT_TEMPLATES']

    wrapper = '%s_fc.%s' % (bld.env['FW_PROJ_NAME'],
                            'f' if want_f77 else 'f90')
    cy_src = '%s.pyx' % bld.env['FW_PROJ_NAME']
    cy_in_src = '%s.in' % cy_src if detect_templates else cy_src

    if want_f77:
        target = [cy_in_src]
    else:
        target = ['fwrap_type_specs.in', '%s_fc.f90' % bld.env['FW_PROJ_NAME'],
                  cy_in_src]

    flags = []
    if want_f77:
        flags.append('--f77binding')
    if detect_templates:
        flags.append('--detect-templates')
    if bld.env['FW_EMULATE_F2PY']:
        flags.append('--emulate-f2py')
    if bld.env['FW_NO_CPDEF']:
        flags.append('--no-cpdef')
    flags.extend('--template=%s' % x for x in bld.env['FW_TEMPLATE'])
    if bld.env['FW_PYF']:
        flags.append('--pyf=%s' % bld.env['FW_PYF'])
        
    if detect_templates:
        bld(
            name = 'tempita',
            rule = run_tempita,
            source = [cy_in_src],
            target = [cy_src]
            )

    if not want_f77:
        bld(
            features = 'c fc pyext fwrap cshlib',
            source = bld.srcnode.ant_glob(incl=['*.f', '*.F', '*.f90', '*.F90']),
            target = bld.env['FW_PROJ_NAME'],
            use = 'fcshlib CLIB NUMPY',
            includes = ['.'],
            )
    else:
        bld(
            name = 'generate_typemap',
            rule = task_generate_typemap_f77binding,
            target = [modmap.typemap_h, modmap.typemap_pxd]
            )
        bld(
            after = 'generate_typemap',
            features = 'c fc pyext cshlib',
            source = bld.srcnode.ant_glob(incl=['src/*.f', 'src/*.F', 'src/*.f90', 'src/*.F90']) +
                     [cy_src],
            target = bld.env['FW_PROJ_NAME'],
            use = 'fcshlib CLIB NUMPY',
            includes = ['.'],
            install_path = bld.srcnode.abspath(),
            )


import os
from waflib import Logs, Build, Utils

from waflib import TaskGen, Task

#
# Typemaps
#

@TaskGen.feature('typemap')
@TaskGen.after('process_source')
@TaskGen.before('apply_link')
def process_typemaps(self):
    """
    modmap: *.f90 + foo.in -> foo.h + foo.f90 + foo.pxd + foo.pxi
    compile foo.f90 like the others
    """
    node = self.path.find_or_declare(getattr(self, 'typemap', modmap.typemap_in))
    if not node:
        raise self.bld.errors.WafError('no typemap file declared for %r' % self)

    typemap_f90 = self.path.find_or_declare(modmap.typemap_f90)
    typemap_h = self.path.find_or_declare(modmap.typemap_h)
    typemap_pxd = self.path.find_or_declare(modmap.typemap_pxd)
    typemap_pxi = self.path.find_or_declare(modmap.typemap_pxi)

    outputs = [typemap_f90, typemap_h, typemap_pxd, typemap_pxi]

    inputs = [node]
    for x in self.tasks:
        if x.inputs and x.inputs[0].name.endswith('.f90'):
            inputs.append(x.inputs[0])

    tmtsk = self.typemap_task = self.create_task(
                                    'modmap',
                                    inputs,
                                    outputs)

    for x in self.tasks:
        if x.inputs and x.inputs[0].name.endswith('.f90'):
            tmtsk.set_run_after(x)

    wrapper = self.path.find_resource(getattr(self, 'wrapper', None))

    tsk = self.create_compiled_task('fc', typemap_f90)
    tsk.nomod = True # the fortran files won't compile unless all the .mod files are set, ick

    wrap_tsk = self.create_compiled_task('fc', wrapper)
    wrap_tsk.set_run_after(tsk)
    wrap_tsk.nomod = True

class modmap(Task.Task):
    """
    create .h and .f90 files, so this must run be executed before any c task
    """
    ext_out = ['.h'] # before any c task is not mandatory since #732 but i want to be sure (ita)
    typemap_in = 'fwrap_type_specs.in'
    typemap_f90 = 'fwrap_ktp_mod.f90'
    typemap_h = 'fwrap_ktp_header.h'
    typemap_pxd = 'fwrap_ktp.pxd'
    typemap_pxi = 'fwrap_ktp.pxi'
    def run(self):
        """
        we need another build context, because we cannot really disable the logger here
        """
        from fwrap import gen_config as gc

        obld = self.generator.bld
        bld = Build.BuildContext(top_dir=obld.srcnode.abspath(), out_dir=obld.bldnode.abspath())
        bld.init_dirs()
        bld.in_msg = 1 # disable all that comes from bld.msg(..), bld.start_msg(..) and bld.end_msg(...)
        bld.env = self.env.derive()
        node = self.inputs[0]
        bld.logger = Logs.make_logger(node.parent.get_bld().abspath() + os.sep + node.name + '.log', 'build')

        ktp_in = [ip for ip in self.inputs if ip.name.endswith('.in')][0]
        ctps = gc.read_type_spec(ktp_in.abspath())
        find_types(bld, ctps)
        gen_type_map_files(ctps, self.outputs, write_f90_mod=True,
                           write_pxi=True)

def gen_type_map_files(ctps, outputs, write_f90_mod, write_pxi):
    from fwrap import gen_config as gc

    def find_by_ext(lst, ext):
        newlst = [x for x in lst if x.name.endswith(ext)]
        if len(newlst) != 1:
            return
        return newlst[0]

    header_name = find_by_ext(outputs, '.h').name
    if write_f90_mod:
        gc.write_f_mod(ctps, find_by_ext(outputs, '.f90'))
    gc.write_header(ctps, find_by_ext(outputs, '.h'))
    gc.write_pxd(ctps, find_by_ext(outputs, '.pxd'), header_name)
    if write_pxi:
        gc.write_pxi(ctps, find_by_ext(outputs, '.pxi'))

def find_types(bld, ctps):
    for ctp in ctps:
        fc_type = None
        if ctp.lang == 'fortran':
            fc_type = find_fc_type(bld, ctp.basetype,
                        ctp.odecl, ctp.possible_modules)
        elif ctp.lang == 'c':
            fc_type = find_c_type(bld, ctp)
        if not fc_type:
            raise bld.errors.WafError(
                    "unable to find C type for type %s" % ctp.odecl)
        ctp.fc_type = fc_type


fc_type_memo = {}
def find_fc_type(bld, basetype, decl, possible_modules):
    from fwrap import gen_config as gc

    res = fc_type_memo.get((basetype, decl), None)
    if res is not None:
        return res

    MODULES = '\n'.join('use %s' % x for x in possible_modules)

    if basetype == 'logical':
        basetype = 'integer'
        decl = decl.replace('logical', 'integer')

    fsrc_tmpl = '''\
subroutine outer(a)
  use, intrinsic :: iso_c_binding
  %(MODULES)s
  implicit none
  %(TEST_DECL)s, intent(inout) :: a
  interface
    subroutine inner(a)
      use, intrinsic :: iso_c_binding
      %(MODULES)s
      implicit none
      %(TYPE_DECL)s, intent(inout) :: a
    end subroutine inner
  end interface
  call inner(a)
end subroutine outer
'''
    for ctype in gc.type_dict[basetype]:
        test_decl = '%s(kind=%s)' % (basetype, ctype)
        fsrc = fsrc_tmpl % {'TYPE_DECL' : decl,
                            'TEST_DECL' : test_decl,
                            'MODULES' : MODULES}
        try:
            bld.check_cc(
                    fragment=fsrc,
                    compile_filename='test.f90',
                    features='fc',
                    includes = bld.bldnode.abspath())
        except bld.errors.ConfigurationError:
            pass
        else:
            res = ctype
            break
    else:
        res = ''
    fc_type_memo[basetype, decl] = res
    return res

def find_c_type(bld, ctp):
    if ctp.lang != 'c':
        raise ValueError("wrong language, given %s, expected 'c'" % ctp.lang)
    if ctp.basetype != 'integer':
        raise ValueError(
                "only integer basetype supported for C type discovery.")

    tmpl = r'''
#include "Python.h"
#include "numpy/arrayobject.h"

typedef %(type)s npy_check_sizeof_type;
int main(int argc, char **argv)
{
    static int test_array [1 - 2 * !(((long) (sizeof (npy_check_sizeof_type))) == sizeof(%(ctype)s))];
    test_array [0] = 0

    ;
    return 0;
}
'''
    ctypes = ('signed char', 'short int',
                    'int', 'long int', 'long long int')
    for ctype in ctypes:
        cfrag = tmpl % {'type' : ctp.odecl, 'ctype' : ctype}
        try:
            bld.check_cc(
                    fragment=cfrag,
                    features = 'c',
                    compile_filename='test.c',
                    use='NUMPY pyext')
        except bld.errors.ConfigurationError:
            pass
        else:
            res = ctype
            break
    else:
        res = ''
    return gc.c2f[res]

def task_generate_typemap_f77binding(task):
    from fwrap.f77_config import get_f77_ctps
    ctps = get_f77_ctps()
    gen_type_map_files(ctps, task.outputs, write_f90_mod=False,
                       write_pxi=False)

#
# Templates
#
def run_tempita(task):
    import tempita
    assert len(task.inputs) == len(task.outputs) == 1
    tmpl = task.inputs[0].read()
    result = tempita.sub(tmpl)
    task.outputs[0].write(result)



# vim:ft=python
