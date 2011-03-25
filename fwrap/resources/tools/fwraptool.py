from waflib.Configure import conf
from waflib import TaskGen
from waflib import Task

@TaskGen.feature('fwrap')
@TaskGen.before('process_source')
def fwrap_fortran_sources(self):
    input_sources = list(self.source)
    f90_wrapped = False
    for node in input_sources:
        if node.suffix() in ('.f90', '.f'): 
            if f90_wrapped:
                raise ValueError('fwrap feature only works with a single Fortran source')
            f90_wrapped = True

            if node.suffix() == '.f':
                f77binding = True
                self.env['FWRAP_F77BINDING'] = '--f77binding'
                suffix = '.f'
            else:
                f77binding = False
                suffix = '.f90'

            # Automatically set target name if not provided
            name = node.name[:-len(node.suffix())]
            if not getattr(self, 'target', None):
                self.target = name + '_fwrap'

            pyx = node.change_ext('_fwrap.pyx')
            typemap_h = node.parent.find_or_declare('fwrap_ktp_header.h')
            typemap_pxd = node.parent.find_or_declare('fwrap_ktp.pxd')
            typemap_pxi = node.parent.find_or_declare('fwrap_ktp.pxi')

            if not f77binding:
                fc_f = node.change_ext('_fwrap_fc' + suffix)
                ktp = node.parent.find_or_declare('fwrap_type_specs.in')
                typemap_f = node.parent.find_or_declare('fwrap_ktp_mod' + suffix)

                self.create_task('fwrap', src=[node], tgt=[pyx, fc_f, ktp])
                self.create_task('generate_fwrap_ktp',
                                 src=[ktp],
                                 tgt=[typemap_f, typemap_h, typemap_pxd, typemap_pxi])
                self.source.append(typemap_f)
                self.source.append(fc_f)
            else:
                self.create_task('fwrap', src=[node], tgt=[pyx])
                self.create_task('generate_fwrap_ktp_f77',
                                 tgt=[typemap_h, typemap_pxd, typemap_pxi])
            self.source.append(pyx)

class fwrap(Task.Task):
    "Run fwrap to turn Fortran file to pyx file"
    run_str = '${PYTHON} ${FWRAP} create ${FWRAP_F77BINDING} ${FWRAPFLAGS} ${TGT[0].abspath()} ${SRC}'
    ext_in  = ['.f90', '.f']
    before = ['cython', 'c', 'fc']

class generate_fwrap_ktp_f77(Task.Task):
    "Run fwrap to turn Fortran file to pyx file"
    run_str = '${PYTHON} ${FWRAP} genktp --f77binding --output-directory ${TGT[0].parent.abspath()}'
    before = ['cython', 'c', 'fc']

def configure(conf):
    conf.find_program('fwrap', var='FWRAP')
