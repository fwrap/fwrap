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

            self.env['INPLACE_INSTALL_PATH'] = node.srcpath()
            pyx = node.change_ext('_fwrap.pyx')
            fc_f90 = node.change_ext('_fwrap_fc.f90')
            ktp = node.parent.find_or_declare('fwrap_type_specs.in')
            self.create_task('fwrap', src=[node], tgt=[pyx, ktp, fc_f90])
            self.source.append(pyx)

            typemap_f90 = node.parent.find_or_declare('fwrap_ktp_mod.f90')
            typemap_h = node.parent.find_or_declare('fwrap_ktp_header.h')
            typemap_pxd = node.parent.find_or_declare('fwrap_ktp.pxd')
            typemap_pxi = node.parent.find_or_declare('fwrap_ktp.pxi')

            self.create_task('generate_fwrap_ktp',
                             src=[ktp],
                             tgt=[typemap_f90, typemap_h, typemap_pxd, typemap_pxi])
            self.source.append(typemap_f90)
            self.source.append(fc_f90)

class fwrap(Task.Task):
    "Run fwrap to turn Fortran file to pyx file"
    run_str = '${PYTHON} ${FWRAP} create ${FWRAP_OPTS} ${TGT[0].abspath()} ${SRC}'
    ext_in  = ['.f90', '.f']
    ext_out = ['.pyx']

def configure(conf):
    conf.find_program('fwrap', var='FWRAP')
