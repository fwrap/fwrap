# fwrap kind-type probing tool for waf
#
# TODO: Get rid of fwrap dependency; bundle necessarry parts of
# gen_config.py as a tool.

from waflib import Logs, Build, Utils
#from waflib.Task import Task
from waflib import TaskGen, Task
from waflib.TaskGen import after_method, before_method, feature, taskgen_method, extension
import os

gc = None

@TaskGen.feature('fwrapktp')
@TaskGen.after('process_source')
@TaskGen.before('apply_link')
def generate_fwrap_ktp_headers(self):
    node = self.path.find_or_declare(getattr(self, 'typemap', generate_fwrap_ktp.typemap_in))

    typemap_f90 = self.path.find_or_declare(generate_fwrap_ktp.typemap_f90)
    typemap_h = self.path.find_or_declare(generate_fwrap_ktp.typemap_h)
    typemap_pxd = self.path.find_or_declare(generate_fwrap_ktp.typemap_pxd)
    typemap_pxi = self.path.find_or_declare(generate_fwrap_ktp.typemap_pxi)

    inputs = [node]
    outputs = [typemap_f90, typemap_h, typemap_pxd, typemap_pxi]

    gen_task = self.create_task("generate_fwrap_ktp", inputs, outputs)

    fc_task = self.create_compiled_task('fc', typemap_f90)
    self.includes_nodes = [] # *shrug*
    fc_task.nomod = True # the fortran files won't compile unless all the .mod files are set, ick

    
class generate_fwrap_ktp(Task.Task):
    before = ['c', 'fc', 'cython']
    
    typemap_in = 'fwrap_type_specs.in'
    typemap_f90 = 'fwrap_ktp_mod.f90'
    typemap_h = 'fwrap_ktp_header.h'
    typemap_pxd = 'fwrap_ktp.pxd'
    typemap_pxi = 'fwrap_ktp.pxi'

    def run(self):
        obld = self.generator.bld
        bld = Build.BuildContext(top_dir=obld.srcnode.abspath(), out_dir=obld.bldnode.abspath())
        bld.init_dirs()
        bld.in_msg = 1 # disable all that comes from bld.msg(..), bld.start_msg(..) and bld.end_msg(...)
        bld.env = self.env.derive()
        ktp_in, = self.inputs
        bld.logger = Logs.make_logger(bld.bldnode.abspath() + os.sep + ktp_in.name + '.log', 'build')

        ctps = gc.read_type_spec(ktp_in.abspath())
        find_types(bld, ctps)

        typemap_f90, typemap_h, typemap_pxd, typemap_pxi = self.outputs

        def genfile(generator, node, *args):
            generator(ctps, node, *args)

        genfile(gc.write_f_mod, typemap_f90)
        genfile(gc.write_header, typemap_h)
        genfile(gc.write_pxd, typemap_pxd, self.typemap_h)
        genfile(gc.write_pxi, typemap_pxi)
        

def configure(conf):
    # TODO: Get rid of this dependency
    conf.check_python_module('fwrap')
    global gc
    from fwrap import gen_config as gc

def process_typemap(self, **kw):
    return self(rule=_process_typemap_builder, **kw)
Build.BuildContext.process_typemap = process_typemap


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

