#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

from fwrap import pyf_iface as pyf
from fwrap import constants
from fwrap import f77_config
from fwrap.pyf_iface import _py_kw_mangler

class Generator(object):
    def set_buffer(self, buf):
        self.buf = buf
        
    def putln(self, *args):
        self.buf.putln(*args)

    def write(self, *args):
        self.buf.write(*args)

    def indent(self):
        self.buf.indent()

    def dedent(self):
        self.buf.dedent()
    

#
# Turn an pyf_iface tree into a cy_wrap tree, skipping the
# intermediary fc_wrap tree and calling the Fortran code
# directly.
#
def fortran_ast_to_cython_ast(ast):
    ret = []
    for proc in ast:
        ret.append(iface_proc_to_cy_proc(proc))
    return ret

def iface_proc_to_cy_proc(proc):
    from cy_wrap import (cy_arg_factory, CyProcedure, get_in_args,
                         get_out_args, get_aux_args)
    
    call_args = [cy_arg_factory(arg, arg.dimension is not None)
                 for arg in proc.args]
    if proc.kind == 'function':
        if proc.return_arg.dimension is not None:
            raise AssertionError()
        return_arg = cy_arg_factory(proc.return_arg, False)
        return_arg.update(intent='out',
                          cy_name=constants.RETURN_ARG_NAME)
        return_args = [return_arg]
    else:
        return_arg = None
        return_args = []
        
    in_args = get_in_args(call_args)
    out_args = return_args + get_out_args(call_args)
    aux_args = get_aux_args(call_args)
    
    all_dtypes_list = [arg.dtype for arg in call_args]

    return CyProcedure.create_node_from(
        proc,
        name=proc.name,
        fc_name=proc.name,
        cy_name=_py_kw_mangler(proc.name),
        call_args=call_args,
        in_args=in_args,
        out_args=out_args,
        aux_args=aux_args,
        all_dtypes_list=all_dtypes_list,
        return_arg=return_arg)
    



#
# _fc.h generation
#

def generate_fc_h(ast, ktp_header_name, buf, cfg):
    GenerateFcHeader(ast, ktp_header_name, buf, cfg).generate()

class GenerateFcHeader(Generator):
    def __init__(self, ast, ktp_header_name, buf, cfg):
        self.procs = ast
        self.ktp_header_name = ktp_header_name
        self.cfg = cfg
        self.set_buffer(buf)

    def generate(self):
        self.putln('#include "%s"' % self.ktp_header_name)
        self.putln('')
        self.putln('#if !defined(FORTRAN_CALLSPEC)')
        self.putln('#define FORTRAN_CALLSPEC')
        self.putln('#endif')
        self.putln('')
        self.write(f77_config.name_mangling_utility_code)
        self.putln('')
        self.putln('#if defined(__cplusplus)')
        self.putln('extern "C" {')    
        self.putln('#endif')
        for proc in self.procs:
            self.procedure_declaration(proc)
        self.putln('#if defined(__cplusplus)')
        self.putln('} /* extern "C" */')
        self.putln('#endif')
        self.putln('')
        self.putln('#if !defined(NO_FORTRAN_MANGLING)')
        for proc in self.procs:
            self.putln('#define %s F_FUNC(%s,%s)' % (proc.name.lower(),
                                                     proc.name.lower(),
                                                     proc.name.upper()))
        self.putln('#endif')

    def procedure_declaration(self, proc):
        decls = ["%s %s" % (arg.c_type(), arg.name)
                 for arg in proc.args]        
        self.putln("FORTRAN_CALLSPEC %s F_FUNC(%s,%s)(%s);" % (
            proc.get_return_c_type(),
            proc.name.lower(),
            proc.name.upper(),
            ", ".join(decls) if len(decls) > 0 else 'void'))


#
# _fc.pxd generation
#
def generate_fc_pxd(ast, fc_header_name, buf, cfg):
    GenerateFcPxd(ast, fc_header_name, buf, cfg).generate()

class GenerateFcPxd(Generator):
    
    def __init__(self, ast, fc_header_name, buf, cfg):
        self.procs = ast
        self.fc_header_name = fc_header_name
        self.set_buffer(buf)
        self.cfg = cfg

    def generate(self):
        self.putln("from %s cimport *" %
                   constants.KTP_PXD_HEADER_SRC.split('.')[0])
        self.putln('')
        self.putln('cdef extern from "%s":' % self.fc_header_name)
        self.indent()
        for proc in self.procs:
            self.procedure_declaration(proc)
        self.dedent()

    def procedure_declaration(self, proc):
        decls = ["%s %s" % (arg.c_type(), _py_kw_mangler(arg.name))
                 for arg in proc.args]        
        self.putln("%s %s(%s)" % (
            proc.get_return_c_type(),
            proc.name,
            ", ".join(decls)))
