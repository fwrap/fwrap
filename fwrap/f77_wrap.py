#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

# ABI used: We basically do the same as f2py. Incomplete list of
# what that means:
#
# Strings: Add trailing length arguments for all string
# arguments. Also the ones with fixed size (we simply copy what f2py
# does here for optimal compiler compatability; some additional
# arguments on the stack apparently does not hurt)


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

    cy_name = _py_kw_mangler(proc.name)
    
    call_args = [cy_arg_factory(arg, arg.dimension is not None, cy_name)
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
        cy_name=cy_name,
        call_args=call_args,
        in_args=in_args,
        out_args=out_args,
        aux_args=aux_args,
        all_dtypes_list=all_dtypes_list,
        return_arg=return_arg)
    
#
# Common utils
#
def get_arg_decl(arg):
    if arg.pyf_by_value and arg.dimension is None:
        return arg.c_type_byval(arg.name)
    else:
        return arg.c_type(arg.name)

def get_arg_declarations(proc):
    decls = [get_arg_decl(arg) for arg in proc.args]
    decls += ["size_t %s_len_" % arg.name
              for arg in proc.args
              if isinstance(arg.dtype, pyf.CharacterType)]
    return ", ".join(decls)

#
# _fc.h generation
#

def generate_fc_h(ast, ktp_header_name, buf, cfg):
    if all(proc.pyf_wraps_c for proc in ast):
        # All procs are intent(c), so do not need name-mangling header
        return
    else:
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
        argstr = get_arg_declarations(proc)
        if len(argstr) == 0:
            argstr = 'void'
        if proc.pyf_wraps_c:
            self.putln("FORTRAN_CALLSPEC %s %s(%s);" % (
                proc.get_return_c_type(),
                proc.name,
                argstr))            
        else:
            self.putln("FORTRAN_CALLSPEC %s F_FUNC(%s,%s)(%s);" % (
                proc.get_return_c_type(),
                proc.name.lower(),
                proc.name.upper(),
                argstr))



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
        self.use_header = not all(proc.pyf_wraps_c for proc in ast)

    def generate(self):
        self.putln("from %s cimport *" %
                   constants.KTP_PXD_HEADER_SRC.split('.')[0])
        self.putln('')
        if self.use_header:
            self.putln('cdef extern from "%s":' % self.fc_header_name)
        else:
            self.putln('cdef extern:')
        self.indent()
        for proc in self.procs:
            self.procedure_declaration(proc)
        self.dedent()

    def procedure_declaration(self, proc):
        argstr = get_arg_declarations(proc)
        self.putln("%s %s(%s)" % (
            proc.get_return_c_type(),
            proc.name,
            argstr))
