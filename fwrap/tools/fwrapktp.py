# fwrap kind-type probing tool for waf
#
# TODO: Get rid of fwrap dependency; bundle necessarry parts of
# gen_config.py as a tool.

from waflib import Logs, Build, Utils
#from waflib.Task import Task
from waflib import TaskGen, Task
from waflib.TaskGen import after_method, before_method, feature, taskgen_method, extension


gc = None

TaskGen.declare_chain(
        name = "cython",
        rule = "${CYTHON} ${CYTHONFLAGS} ${CPPPATH_ST:INCPATHS} ${SRC} -o ${TGT}",
        ext_in = ['.in'],
        ext_out = ['.c'],
        reentrant = True,
        )


def configure(conf):
    # TODO: Get rid of this dependency
    conf.check_python_module('fwrap')
    global gc
    from fwrap import gen_config as gc

def process_typemap(self, **kw):
    return self(rule=_process_typemap_builder, **kw)
Build.BuildContext.process_typemap = process_typemap

def _process_typemap_builder(self):
    # we need another build context, because we cannot really disable the logger here
    import time
    time.sleep(4)
    1/0
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
    print find_by_ext(outputs, '.pxi')

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

