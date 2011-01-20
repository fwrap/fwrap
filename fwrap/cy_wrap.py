#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

from fwrap import pyf_iface
from fwrap import constants
from fwrap.code import CodeBuffer, CodeSnippet
from fwrap import code
from fwrap.pyf_iface import _py_kw_mangler
from fwrap.astnode import AstNode

import re
from warnings import warn

plain_sizeexpr_re = re.compile(r'\(([a-zA-Z0-9_]+)\)')
default_array_value_re = re.compile(r'^[()0.,\s]+$') # variations of zero...
literal_re = re.compile(r'^[0-9.e\-]+$')

class CythonCodeGenerationContext:
    def __init__(self, cfg):
        from fwrap.configuration import Configuration
        assert isinstance(cfg, Configuration)
        self.utility_codes = set()
        self.language = None
        self.cfg = cfg

    def use_utility_code(self, snippet):
        self.utility_codes.add(snippet)

def wrap_fc(ast):
    ret = []
    for proc in ast:
        ret.append(fc_proc_to_cy_proc(proc))
    return ret

def fc_proc_to_cy_proc(fc_proc):
    name = fc_proc.wrapped_name()
    cy_name = _py_kw_mangler(name)

    fw_arg_man = fc_proc.arg_man
    args = []
    for fw_arg in fw_arg_man.arg_wrappers:
        args.append(cy_arg_factory(fw_arg, fw_arg.is_array, cy_name))

    all_dtypes_list = fc_proc.all_dtypes()

    return CyProcedure.create_node_from(
        fc_proc,
        name=fc_proc.wrapped_name(), # remove when FcProcedure is refactored
        fc_name=fc_proc.name, # ditto
        cy_name=cy_name,
        call_args=get_call_args(args),
        in_args=get_in_args(args),
        out_args=get_out_args(args),
        aux_args=get_aux_args(args),
        all_dtypes_list=all_dtypes_list)

def cy_arg_factory(arg, is_array, proc_name):
    # Is passed both fc_wrap arguments and pyf_iface arguments;
    # their attributes mostly overlap
    import fc_wrap
    attrs = {}
    attrs['cy_name'] = _py_kw_mangler(arg.name)
    if is_array:
        if arg.dtype.type == 'character':
            cls = CyCharArrayArg
        else:
            cls = _CyArrayArg
        if isinstance(arg, fc_wrap.FcArgBase):
            attrs['dimension'] = arg.orig_arg.dimension
        else:
            attrs['dimension'] = arg.dimension
            attrs['ndims'] = len(arg.dimension.dims)
    else:
        if isinstance(arg, fc_wrap.FcErrStrArg):
            cls = _CyErrStrArg
        elif isinstance(arg.dtype, pyf_iface.ComplexType):
            cls = _CyCmplxArg
        elif isinstance(arg.dtype, pyf_iface.CharacterType):
            if arg.dtype.length == '1':
                # Handle common flag-case with nicer code
                cls = _CySingleCharArg
            else:
                cls = _CyStringArg
        elif isinstance(arg.dtype, pyf_iface.CallbackType):
            cls = CyCallbackArg
            attrs['callback_wrapper_basename'] = '%s_%s_cb_' % (proc_name, attrs['cy_name'])
        else:
            cls = _CyArg
        if arg.name == constants.ERR_NAME:
            attrs['pyf_hide'] = True
    return cls.create_node_from(arg, **attrs)

def get_call_args(args):
    return args

def get_in_args(args):
    # Arrays with intent(out) is still present in case user wants
    # to input a buffer
    result = [arg for arg in args
              if (not arg.pyf_hide and
                  (arg.is_array or
                   arg.intent in ('in', 'inout', None)) and
                  not isinstance(arg, _CyErrStrArg))]
    return result

def get_out_args(args):
    return [arg for arg in args
            if (not arg.pyf_hide and
                arg.intent in ('out', 'inout', None) and
                not arg.pyf_no_return and
                not isinstance(arg, _CyErrStrArg))]

def get_aux_args(args):
    return [arg for arg in args if arg.pyf_hide]

def generate_cy_pxd(ast, fc_pxd_name, buf, cfg):
    buf.putln('cimport numpy as np')
    buf.putln("from %s cimport *" %
                constants.KTP_PXD_HEADER_SRC.split('.')[0])
    buf.putln("cimport %s as fc" % fc_pxd_name)
    buf.putln('')
    for proc in ast:
        buf.putln(proc.cy_prototype(cfg))

def gen_cimport_decls(buf):
    for dtype in pyf_iface.intrinsic_types:
        buf.putlines(dtype.cimport_decls)

def gen_cdef_extern_decls(buf):
    for dtype in pyf_iface.intrinsic_types:
        buf.putlines(dtype.cdef_extern_decls)

def generate_cy_pyx(ast, name, buf, cfg):
    from fwrap.deduplicator import cy_deduplify
    ctx = CythonCodeGenerationContext(cfg)
    if cfg.detect_templates:
        ast = cy_deduplify(ast, cfg)    
    buf.putln("#cython: ccomplex=True")
    buf.putln(' ')
    put_cymod_docstring(ast, name, buf, cfg)
    buf.putln("np.import_array()")
    if not cfg.f77binding:
        buf.putln("include 'fwrap_ktp.pxi'")
    gen_cimport_decls(buf)
    gen_cdef_extern_decls(buf)
    if cfg.f77binding:
        buf.putln('__all__ = %s' % repr([proc.cy_name for proc in ast]))
    for proc in ast:
        ctx.language = proc.language
        assert ctx.language in ('fortran', 'pyf')
        proc.generate_wrapper(ctx, buf)
        buf.putln(' ')
        buf.putln(' ')
    for utilcode in ctx.utility_codes:
        buf.putblock(utilcode)
    buf.putln('')
    buf.putln('# Fwrap configuration:')
    cfg.serialize_to_pyx(buf)
    buf.putln('')

def put_cymod_docstring(ast, modname, buf, cfg):
    dstring = get_cymod_docstring(ast, modname, cfg)
    buf.putln('"""' + dstring[0])
    buf.putlines(dstring[1:])
    buf.putempty()
    buf.putln('"""')

# XXX:  Put this in a cymodule class?
def get_cymod_docstring(ast, modname, cfg):
    from fwrap.version import get_version
    from fwrap.gen_config import all_dtypes
    dstring = ("""\
The %s module was generated with Fwrap v%s.

Below is a listing of functions and data types.
For usage information see the function docstrings.

""" % (modname, get_version())).splitlines()
    dstring += ["Functions",
                "---------"]
    # Functions
    names = []
    for proc in ast:
        names.append(', '.join(proc.get_names()))
    names.sort()
    names = ["%s(...)" % name for name in names]
    dstring += names

    if not cfg.f77binding:
        dstring += [""]
        dstring += ["Data Types",
                "----------"]
        # Datatypes
        dts = all_dtypes(ast)
        names = sorted([dt.py_type_name() for dt in dts if dt.fw_ktp is not None])
        dstring += names

    return dstring


class _CyArgBase(AstNode):
    mandatory = ('name', 'cy_name', 'intent', 'dtype', 'ktp')

    # Optional:
    pyf_hide = False
    pyf_default_value = None
    pyf_check = []
    pyf_depend = []
    pyf_overwrite_flag = False
    pyf_overwrite_flag_default = None
    pyf_optional = False
    pyf_align = None
    pyf_by_value = False
    pyf_no_return = False
    
    cy_default_value = None # or CythonExpression

    # Set by mergepyf
    defer_init_to_body = False
    overwrite_flag_cy_name = None

    def _update(self):
        self.intern_name = self.cy_name

    def equal_up_to_type(self, other_arg):
        type_a = type(self)
        type_b = type(other_arg)
        if type_a is not type_b:
            # Character arguments are currently not
            # "equal up to type", handled too differently
            if not (type_a in (_CyArg, _CyCmplxArg) and
                    type_b in (_CyArg, _CyCmplxArg)):
                return False
        result = self.equal_attributes(other_arg,
                                       [x for x in self.attributes
                                        if x not in ('dtype', 'ktp', 'npy_enum',
                                                     'name', 'cy_name')])
        return result

    def trailing_call_arg_list(self, ctx):
        return []

    def is_optional(self):
        return (self.cy_default_value is not None or self.pyf_default_value is not None)

    def get_code_snippets(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name,
                          is_in_arg, is_return_arg):
        yield CodeSnippet(('init', self.intern_name))

class _CyArg(_CyArgBase):

    # Internal:
    is_array = False

    def _update(self):
        self.cy_dtype_name = self._get_cy_dtype_name()
        if self.cy_default_value is not None:
            assert isinstance(self.cy_default_value, CythonExpression)

        self.intern_name = self.cy_name
        if self.defer_init_to_body:
            self.extern_typedecl = 'object'
            self.intern_typedecl = self.cy_dtype_name
            if not self.pyf_hide:
                self.intern_name = '%s_' % self.cy_name
        elif (self.dtype is not None and self.dtype.type == 'logical'
              and self.intent in ('in', 'inout', None)):
            self.extern_typedecl = 'bint'
            self.intern_typedecl = self.cy_dtype_name
            self.intern_name = '%s_' % self.cy_name
        else:
            self.extern_typedecl = self.cy_dtype_name
            self.intern_typedecl = None

    def _get_cy_dtype_name(self):
        return self.ktp

    def _get_py_dtype_name(self):
        from fwrap.gen_config import py_type_name_from_type
        if isinstance(self.dtype, pyf_iface.CharacterType):
            return 'bytes'
        elif isinstance(self.dtype, pyf_iface.CallbackType):
            return 'object'
        else:
            return py_type_name_from_type(self.cy_dtype_name)

    def extern_declarations(self):
        """
        Returns a list [(decl, default)] of argument declarations
        needed. "decl" is the declaration string and default is a
        string representation of possible default value (normally
        either None or 'None')
        """
        assert not self.pyf_hide and self.intent in ('in', 'inout', None)
        if self.cy_default_value is not None:
            if self.defer_init_to_body:
                default = 'None'
            else:
                default = self.cy_default_value.as_literal()
        else:
            default = None
        return [("%s %s" % (self.extern_typedecl, self.cy_name), default)]

    def docstring_extern_arg_list(self):
        assert not self.pyf_hide and self.intent in ('in', 'inout', None)
        return [self.cy_name]

    def intern_declarations(self, ctx, extern_decl_made):
        result = []
        if not extern_decl_made and self.intern_typedecl is None:
            typedecl = self.extern_typedecl
        else:
            typedecl = self.intern_typedecl
        if self.intern_typedecl is not None or not extern_decl_made:
            return [(typedecl, self.intern_name)]
        else:
            return []

    def call_arg_list(self, ctx):
        if self.pyf_by_value and not self.is_array:
            return [self.intern_name]
        else:
            return ["&%s" % self.intern_name]

    def post_call_code(self, ctx):
        return []

    def pre_call_code(self, ctx):
        return []
    
    def get_code_snippets(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name,
                          is_in_arg, is_return_arg):
        # Initialization code
        initcs = CodeSnippet(('init', self.intern_name))
        empty = True
        if (self.dtype is not None and self.dtype.type == 'logical' and
            self.intent in ('in', 'inout', None)):
            # emulates PyObject_IsTrue used by f2py:
            initcs.put('%s = 1 if %s else 0' % (self.intern_name, self.cy_name))
            empty = False
        if self.cy_default_value is not None:
            value, requires, doc = self.cy_default_value.substitute(fc_name_to_intern_name,
                                                                    fc_name_to_cy_name)
            initcs.add_requires(('init', r) for r in requires)
            if self.pyf_hide:
                initcs.putln("%s = %s", self.intern_name, value)
                empty = False
            elif self.defer_init_to_body:
                initcs.putln("%s = %s if (%s is not None) else %s",
                             self.intern_name, self.cy_name, self.cy_name,
                             value)
                empty = False
            else:
                pass
        if empty and not is_in_arg and not is_return_arg and ctx.cfg.f77binding:
            initcs.putln("%s = 0" % self.intern_name)
        return [initcs]

    def return_tuple_list(self, ctx):
        assert self.cy_name != constants.ERR_NAME
        assert self.intent in ('out', 'inout', None)
        return [self.intern_name]

    def docstring_return_tuple_list(self):
        return [self.cy_name]

    def _gen_dstring(self):
        dstring = ("%s : %s" %
                    (self.cy_name, self._get_py_dtype_name()))
        if self.intent is not None:
            dstring += ", intent %s" % (self.intent)
        return [dstring]

    def in_dstring(self):
        if self.intent not in ('in', 'inout', None):
            return []
        return self._gen_dstring()

    def out_dstring(self):
        if self.cy_name == constants.ERR_NAME:
            return []
        if self.intent not in ('out', 'inout', None):
            return []
        return self._gen_dstring()

class _CySingleCharArg(_CyArg):
    def _update(self):
        super(_CySingleCharArg, self)._update()
        self.buf_name = 'fw_%s' % self.cy_name
    
    def _get_cy_dtype_name(self):
        return "object"

    def intern_declarations(self, ctx, extern_decl_made):
        return [('char', '*%s = [0, 0]' % self.buf_name)]

    def pre_call_code(self, ctx):
        ctx.use_utility_code(as_char_utility_code)        
        if self.intent in ('in', 'inout', None):
            return ['%s[0] = fw_aschar(%s)' % (self.buf_name, self.cy_name),
                    'if %s[0] == 0:' % self.buf_name,
                    '    raise ValueError("len(%s) != 1")' % self.cy_name]
        else:
            return []

    def call_arg_list(self, ctx):
        return ["%s" % self.buf_name]

    def trailing_call_arg_list(self, ctx):
        if ctx.cfg.f77binding:
            # See f77_wrap.py
            return ["1"]
        else:
            return []

    def return_tuple_list(self, ctx):
        return [self.buf_name]

class _CyStringArg(_CyArg):

    def _update(self):
        super(_CyStringArg, self)._update()
        self.intern_name = 'fw_%s' % self.cy_name
        self.intern_len_name = '%s_len' % self.intern_name
        self.intern_buf_name = '%s_buf' % self.intern_name

    def _get_cy_dtype_name(self):
        return "bytes"

    def _get_py_dtype_name(self):
        from fwrap.gen_config import py_type_name_from_type
        return py_type_name_from_type(self.ktp)

    def extern_declarations(self):
        #TODO: This seems like the result of a refactoring error?
        if self.intent in ('in', 'inout', None):
            return [("%s %s" % (self.cy_dtype_name, self.cy_name), None)]
        elif self.is_assumed_size():
            return [('%s %s' % (self.cy_dtype_name, self.cy_name), None)]
        return []

    def intern_declarations(self, ctx, extern_decl_made):
        # TODO: Check extern_decl_made here?
        ret = [(self.cy_dtype_name, self.intern_name),
               ('fw_shape_t', self.intern_len_name)]
        if self.intent in ('out', 'inout', None):
            ret.append(('char', '*%s' % self.intern_buf_name))
        return ret

    def get_len(self):
        return self.dtype.len

    def is_assumed_size(self):
        return self.get_len() == '*'

    def _len_str(self):
        if self.is_assumed_size():
            len_str = 'len(%s)' % self.cy_name
        else:
            len_str = self.get_len()
        return len_str

    def _in_pre_call_code(self):
        return ['%s = len(%s)' % (self.intern_len_name, self.cy_name),
                '%s = %s' % (self.intern_name, self.cy_name)]

    def _out_pre_call_code(self):
        len_str = self._len_str()
        return ['%s = %s' % (self.intern_len_name, len_str),
               self._fromstringandsize_call(),
               '%s = <char*>%s' % (self.intern_buf_name, self.intern_name),]

    def _inout_pre_call_code(self):
       ret = self._out_pre_call_code()
       ret += ['memcpy(%s, <char*>%s, %s+1)' %
               (self.intern_buf_name, self.cy_name, self.intern_len_name)]
       return ret

    def pre_call_code(self, ctx):
        if self.intent == 'in':
            return self._in_pre_call_code()
        elif self.intent == 'out':
            return self._out_pre_call_code()
        elif self.intent in ('inout', None):
            return self._inout_pre_call_code()

    def _fromstringandsize_call(self):
        return '%s = PyBytes_FromStringAndSize(NULL, %s)' % \
                    (self.intern_name, self.intern_len_name)

    def call_arg_list(self, ctx):
        args = []
        if not ctx.cfg.f77binding:
            # See f77_wrap.py
            args.append('&%s' % self.intern_len_name)
        if self.intent == 'in':
            args.append('<char*>%s' % self.intern_name)
        else:
            args.append(self.intern_buf_name)
        return args

    def trailing_call_arg_list(self, ctx):
        if ctx.cfg.f77binding:
            # See f77_wrap.py
            return [self.intern_len_name]
        else:
            return []

    def return_tuple_list(self, ctx):
        if self.intent in ('out', 'inout', None):
            return [self.intern_name]
        return []

    def _gen_dstring(self):
        dstring = ["%s : bytes" % self.cy_name]
        dstring.append("len %s" % self.get_len())
        if self.intent is not None:
            dstring.append("intent %s" % (self.intent))
        return [", ".join(dstring)]

    def in_dstring(self):
        if self.is_assumed_size():
            return self._gen_dstring()
        else:
            return super(_CyStringArg, self).in_dstring()


class _CyErrStrArg(_CyArgBase):
    is_array = False

    def get_len(self):
        return self.dtype.len

    def extern_declarations(self):
        return []

    def intern_declarations(self, ctx, extern_decl_made):
        return [('fw_character_t', '%s[%s]' %
                 (self.cy_name, constants.ERRSTR_LEN))]

    def call_arg_list(self, ctx):
        return [self.cy_name]

    def return_tuple_list(self, ctx):
        return []

    def pre_call_code(self, ctx):
        return []

    def post_call_code(self, ctx):
        return []

    def docstring_extern_arg_list(self):
        return []

    def docstring_return_tuple_list(self):
        return []

    def in_dstring(self):
        return []

    def out_dstring(self):
        return []


class _CyCmplxArg(_CyArg):
    pass
##     # TODO Is this class needed?
##     def _update(self):
##         super(_CyCmplxArg, self)._update()
##         self.intern_name = 'fw_%s' % self.cy_name

##     def intern_declarations(self, ctx, extern_decl_made):
##         return super(_CyCmplxArg, self).intern_declarations(ctx)

##     def call_arg_list(self, ctx):
##         return ['&%s' % self.cy_name]



class _CyArrayArg(_CyArgBase):
    mandatory = _CyArgBase.mandatory + ('dimension', 'ndims')

    # Optional
    mem_offset_code = None
    cy_explicit_shape_expressions = None
    truncation_allowed = True # arr(n) : can n < arr.shape[0]?

    # Set from deduplicator
    npy_enum = None

    # Internal:
    is_array = True

    def _update(self):
        from fwrap.gen_config import py_type_name_from_type
        self.intern_name = '%s_' % self.cy_name
        self.shape_name = '%s_shape' % self.cy_name

        # In the special case of explicit-shape intent(out) arrays,
        # find the expressions for constructing the output argument
        self.is_explicit_shape = all(dim.is_explicit_shape
                                     for dim in self.dimension)
        if self.pyf_optional and not self.is_explicit_shape:
            raise RuntimeError('Cannot have an optional array without explicit shape')
        # Note: The following are set to something else in
        # deduplicator.TemplatedCyArrayArg
        self.py_type_name = py_type_name_from_type(self.ktp)
        if self.npy_enum is None:
            self.npy_enum = self.dtype.npy_enum

        if self.pyf_hide and self.cy_default_value is None:
            self.cy_default_value = CythonExpression('0', [], '0')

        self._shape_expressions = self.cy_explicit_shape_expressions
        if self._shape_expressions is None:
            self._shape_expressions = []
            # If Fortran statements have not been parsed and
            # translated, we only support the simplest cases.
            # TODO: Fix this up (compile Fortran-side function to
            # give resulting shape?)
            for i, expr in enumerate([dim.sizeexpr for dim in self.dimension]):
                m = None if expr is None else plain_sizeexpr_re.match(expr)
                if m is not None:
                    expr = m.group(1)
                    if literal_re.match(expr):
                        # a literal
                        exprobj = CythonExpression(expr, [], expr)
                    else:
                        exprobj = CythonExpression('%%(%s)s' % expr,
                                                   [expr],
                                                   '%%(%s)s' % expr)
                else:
                    exprobj = None
                self._shape_expressions.append(exprobj)

    def is_optional(self):
        return (self.pyf_optional or (self.is_explicit_shape and 
                (self.intent == 'out' or
                 self.cy_default_value is not None)))

    def set_extern_name(self, name):
        self.extern_name = name
        self.intern_name = '%s_' % name

    def get_extern_name(self):
        return self.extern_name

    def extern_declarations(self):
        if self.is_optional():
            default = 'None'
        else:
            default = None
        return [('object %s' % self.cy_name, default)]

    def intern_declarations(self, ctx, extern_decl_made):
        decls = [('np.ndarray', self.intern_name),
                 ('np.npy_intp', '%s[%d]' % (self.shape_name, self.ndims))]
        return decls            

    def _get_py_dtype_name(self):
        return self.py_type_name

    def call_arg_list(self, ctx):
        if self.mem_offset_code is not None:
            offset_code = ' + %s' % self.mem_offset_code
        else:
            offset_code = ''
        if ctx.cfg.f77binding:
            shape_args = []
        else:
            shape_args = [self.shape_name]
        return shape_args + [
            '<%s*>np.PyArray_DATA(%s)%s' %
            (self.ktp, self.intern_name, offset_code)]

    def get_code_snippets(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name,
                          is_in_arg, is_return_arg):
        d = {'intern' : self.intern_name,
             'extern' : self.cy_name,
             'dtenum' : self.npy_enum,
             'ndim' : self.ndims,
             'alignstr' : '' if self.pyf_align is None else ', %d' % self.pyf_align,
             'shapevar' : self.shape_name}
        # Can we allocate the out-array ourselves? Currently this
        # involves trying to parse the size expression to see if it
        # is simple enough.
        # TODO: Move parsing of shapes to _fc.
            
        if self.cy_default_value is not None:
            try:
                literal = self.cy_default_value.as_literal()
            except ValueError:
                literal = ''
            if default_array_value_re.match(literal) is None:
                # Has default value that is not 0, manual intervention
                # needed (with f2py this could be a loop body)
                cs = CodeSnippet(('init', self.intern_name))
                cs.putln('##TODO %s = %s' %
                         (self.intern_name,
                          self.cy_default_value.substitute(fc_name_to_intern_name,
                                                           fc_name_to_cy_name)[0]))
                yield cs
        
        can_allocate = self.is_optional()
        if can_allocate and None in self._shape_expressions:
            warn(
                'Cannot automatically allocate explicit-shape intent(out) array '
                'as expression is too complicated: %s' %
                self.dimension.dims[expr.index(None)].sizeexpr)
            can_allocate = False

        requires = set()
        shape_info = [] # of tuple (expr, requires, doc)
        for exprobj in self._shape_expressions:
            if exprobj is not None:
                expr, dimrequires, doc = exprobj.substitute(fc_name_to_intern_name,
                                                            fc_name_to_cy_name)
                shape_info.append((expr, dimrequires, doc))
                if can_allocate:
                    requires.update(dimrequires)
            else:
                shape_info.append(None)

        # Figure out the copy flag
        if self.pyf_overwrite_flag:
            # Simply use overwrite_X argument
            d['copy'] = 'not %s' % self.overwrite_flag_cy_name
        else:
            # Intents:
            # In the case of "out" the array is presumably provided as a buffer.
            # In the case of "in", the called proc promises not to touch it,
            # so we do not need a copy.
            # In the case of "inout", there's explicit permission by user to
            # touch buffer
            d['copy'] = 'False'

        # Generate call to convert or allocate array
        if ctx.cfg.should_emulate_f2py():
            ctx.use_utility_code(as_fortran_array_f2pystyle_utility_code)
        else:
            ctx.use_utility_code(as_fortran_array_utility_code)
        cs = CodeSnippet(('init', self.intern_name),
                         [('init', r) for r in requires])

        if can_allocate and self.pyf_hide:
            d['extern'] = 'None'
        d['create'] = bool(can_allocate)
        if can_allocate:
            cs.putln('; '.join('%s[%d] = %s' % (self.shape_name, idx, expr)
                               for idx, (expr, _, _) in enumerate(shape_info)))
        cs.putln('%(intern)s = fw_asfortranarray(%(extern)s, %(dtenum)s, '
                 '%(ndim)d, %(shapevar)s, %(copy)s, %(create)s%(alignstr)s)' % d)
        yield cs

        #
        # Code for checking explicit shapes in f77binding mode.
        # Not needed when the array is a buffer we allocated ourselves.
        #
        if ctx.cfg.f77binding and not (can_allocate and self.pyf_hide):
            cs = CodeSnippet(('check', self.intern_name),
                             [('init', self.intern_name)])
            for idx, info in enumerate(shape_info):
                if info is None:
                    continue
                expr, req, doc = info
                d.update(idx=idx, expr=expr, doc=doc,
                         mem_offset_code=('' if self.mem_offset_code is None
                                          else ' - ' + self.mem_offset_code))
                cs.add_requires(('init', r) for r in req)
                if self.truncation_allowed and idx == len(shape_info) - 1:
                    # last dimension, can truncate
                    cs.put(
                        '''\
    if not (0 <= %(expr)s <= %(shapevar)s[%(idx)d]%(mem_offset_code)s):
        raise ValueError("(0 <= %(doc)s <= %(extern)s.shape[%(idx)d]%(mem_offset_code)s) not satisifed")
                    ''' % d)
                else:
                    cs.put(
                        '''\
    if %(expr)s != %(shapevar)s[%(idx)d]:
        raise ValueError("(%(doc)s == %(extern)s.shape[%(idx)d]) not satisifed")
                    ''' % d)
            yield cs

    def pre_call_code(self, ctx):
        return []

    def post_call_code(self, ctx):
        return []

    def return_tuple_list(self, ctx):
        if self.intent in ('out', 'inout', None):
            # fw_asfortranarray returns tuple with internal and external view,
            # and we return the external one
            return [self.intern_name]
        return []

    def _gen_dstring(self):
        dims = self.dimension
        ndims = len(dims)
        dstring = ("%s : %s, %dD array, %s" %
                        (self.cy_name,
                         self._get_py_dtype_name(),
                         ndims,
                         dims.attrspec))
        if self.intent is not None:
            dstring += ", intent %s" % (self.intent)
        return [dstring]

    def in_dstring(self):
        return self._gen_dstring()

    def out_dstring(self):
        if self.intent not in ("out", "inout", None):
            return []
        return self._gen_dstring()

    def docstring_extern_arg_list(self):
        return [self.cy_name]

    def docstring_return_tuple_list(self):
        if self.intent in ('out', 'inout', None):
            return [self.cy_name]
        return []


class CyCharArrayArg(_CyArrayArg):

    def _update(self):
        super(CyCharArrayArg, self)._update()
        self.odtype_name = "%s_odtype" % self.intern_name
        self.shape_name = "%s_shape" % self.intern_name

    def intern_declarations(self, ctx, extern_decl_made):
        ret = super(CyCharArrayArg, self).intern_declarations(ctx, extern_decl_made)
        return ret + [('fw_shape_t', '%s[%d]' %
                       (self.shape_name, self.ndims+1))]

    def pre_call_code(self, ctx):
        tmpl = ("%(odtype)s = %(name)s.dtype\n"
                "for i in range(%(ndim)d): "
                    "%(shape)s[i+1] = %(name)s.shape[i]\n"
                "%(name)s.dtype = 'b'\n"
                "%(intern)s = %(name)s\n"
                "%(shape)s[0] = <fw_shape_t>"
                    "(%(name)s.shape[0]/%(shape)s[1])")
        D = {"odtype" : self.odtype_name,
             "ndim" : self.ndims,
             "name" : self.extern_name,
             "intern" : self.intern_name,
             "shape" : self.shape_name}

        return (tmpl  % D).splitlines()

    def post_call_code(self, ctx):
        return ["%s.dtype = %s" % (self.extern_name, self.odtype_name)]

    def call_arg_list(self, ctx):
        shapes = ["&%s[%d]" % (self.shape_name, i)
                    for i in range(self.ndims+1)]
        data = ["<%s*>%s.data" % (self.ktp, self.intern_name)]
        return shapes + data

    def _gen_dstring(self):
        dims = self.dimension
        ndims = len(dims)
        dtype_len = self.dtype.len
        dstring = ["%s : %s" %
                    (self.extern_name, self._get_py_dtype_name())]
        dstring.append("len %s" % dtype_len)
        dstring.append("%dD array" % ndims)
        dstring.append(dims.attrspec)
        if self.intent is not None:
            dstring.append("intent %s" % self.intent)
        return [", ".join(dstring)]

class CyCallbackArg(_CyArg):
    callback_wrapper_basename = None

    def _update(self):
        super(CyCallbackArg, self)._update()
        self.callback_core_name = '%swrapper_core' % self.callback_wrapper_basename
        self.callback_wrapper_name = '%swrapper' % self.callback_wrapper_basename
        self.callback_info_name = '%sinfo' % self.callback_wrapper_basename

    def call_arg_list(self, ctx):
        return ['&%s' % self.callback_wrapper_name]

    def _get_cy_dtype_name(self):
        return 'object'

    def _get_py_dtype_name(self):
        return 'object'

    def generate_callback_wrapper(self, ctx, buf):
        ctx.use_utility_code(callback_utility_code)
        arg_names = ['arg%d' % idx for idx in range(len(self.dtype.arg_dtypes))]
        arg_decls = ['%s %s' % (t.c_declaration(), name)
                     for t, name in zip(self.dtype.arg_dtypes, arg_names)]
        for arg_dtype in self.dtype.arg_dtypes:
            print arg_dtype.__dict__
        has_arrays = any(arg_dtype.dimension is not None
                         for arg_dtype in self.dtype.arg_dtypes)
##         for arg_dtype in self.dtype.arg_dtypes:
##             if arg_dtype.dimension is not None:
##                 ndim = arg.
##             array_creation.append(
##                 'np.PyArray_New(&np.PyArray_Type, %(ndim)d, '
##             PyArrayObject *tmp_arr = (PyArrayObject *)PyArray_New(&PyArray_Type,1,x_Dims,PyArray_DOUBLE,NULL,(char*)x,0,NPY_FARRAY,NULL); /*XXX: Hmm, what will destroy this array??? */
            
        d.update(arg_decls=', '.join(arg_decls),
                 arg_names=', '.join(arg_names),
                 global_info=self.callback_info_name,
                 wrapper_core=self.callback_core_name,
                 wrapper=self.callback_wrapper_name)
        buf.put('''
        cdef fw_CallbackInfo %(global_info)s
        cdef int %(wrapper_core)(%(arg_decls)s):
            global %(global_info)s;
            cdef fw_CallbackInfo info
        ''' % d)
        buf.indent()
        if has_arrays:
            buf.putln('cdef np.npy_intp shape[np.NPY_MAXDIMS]')
        buf.put('''
            info = %(global_info)s;
            try:
            ''')
        buf.indent()
        for arg_dtype in self.dtype.arg_dtypes:
            dimension = arg_dtype.dimension
            if dimension is not None:
                print dimension()
        buf.put('''
                        if info.extra_args is None:
                    info.callback()
                ''')
        buf.dedent()
        buf.dedent()
        buf.put('''
        cdef void %(wrapper)(%(arg_decls)s):
            if %(wrapper_core)(%(arg_names)s) != 0:
                longjmp(%(global_info).jmp, 1)
        ''' % d)

        

class CyArgManager(object):

    def __init__(self, in_args, out_args, call_args, aux_args):
        self.in_args = in_args
        self.out_args = out_args
        self.call_args = call_args
        self.aux_args = aux_args
        self.needs_init_args = (self.in_args +
                                [arg for arg in self.aux_args
                                 if arg not in self.in_args] +
                                [arg for arg in self.call_args if
                                 arg not in self.in_args and
                                 arg not in self.aux_args] +
                                [arg for arg in self.out_args if
                                 arg not in self.in_args and
                                 arg not in self.aux_args and
                                 arg not in self.call_args])

    def call_arg_list(self, ctx):
        cal = []
        for arg in self.call_args:
            cal.extend(arg.call_arg_list(ctx))
        for arg in self.call_args:
            cal.extend(arg.trailing_call_arg_list(ctx))
        return cal

    def arg_declarations(self):
        decls = []
        for arg in self.in_args:
            x = arg.extern_declarations()
            assert len(x) == 1, "assumed in arg_is_optional"
            decls.extend(x)
        return decls

    def arg_is_optional(self):
        is_optional = []
        for arg in self.in_args:
            is_optional.append(arg.is_optional())
        # Remove non-trailing optional arguments
        for i in range(len(is_optional) - 1, -1, -1):
            if not is_optional[i]:
                for j in range(i):
                    is_optional[j] = False
                break
        return is_optional

    def intern_declarations(self, ctx):
        decls = []
        for arg in self.needs_init_args:
            decls.extend(arg.intern_declarations(ctx, arg in self.in_args))
        return decls

    def return_tuple_list(self, ctx):
        rtl = []
        for arg in self.out_args:
            rtl.extend(arg.return_tuple_list(ctx))
        return rtl

    def pre_call_code(self, ctx):
        pcc = []
        for arg in self.call_args:
            pcc.extend(arg.pre_call_code(ctx))
        return pcc

    def post_call_code(self, ctx):
        pcc = []
        for arg in self.call_args:
            pcc.extend(arg.post_call_code(ctx))
        return pcc

    def docstring_return_tuple_list(self):
        decls = []
        for arg in self.out_args:
            decls.extend(arg.docstring_return_tuple_list())
        return decls

    def docstring_in_descrs(self):
        descrs = []
        for arg in self.in_args:
            descrs.extend(arg.in_dstring())
        return descrs

    def docstring_out_descrs(self):
        descrs = []
        for arg in self.out_args:
            descrs.extend(arg.out_dstring())
        return descrs
    
class CyProcedure(AstNode):
    # The argument lists often contain the same argument nodes, but
    # may appear in only one of them, e.g., be automatically inferred
    # (only present in call_args) or have the contents participate in
    # a cy_default_value expression (only present in in_args), or
    # be purely present for temporary purposes (aux_args).
    
    mandatory = ('name', 'cy_name', 'fc_name', 'in_args',
                 'out_args', 'call_args', 'all_dtypes_list',
                 'language', 'kind')
    pyf_callstatement = None
    pyf_wraps_c = False
    language = 'fortran'
    aux_args = ()
    checks = ()
    pyf_pre_call_code = None
    pyf_post_call_code = None
    pyf_fortranname = None

    # Only used in f77binding (otherwise the function is wrapped
    # to become a subprocedure instead). The return_arg should
    # also be part of out_args (but not call_args). I.e. the logic
    # is:
    #
    # [$return_arg =,] fc.function(*$call_args)
    # return $out_args
    return_arg = None

    def _update(self):
        self.arg_mgr = CyArgManager(self.in_args, self.out_args, self.call_args,
                                    self.aux_args)
        
    def get_names(self):
        # A template proc can provide more than one name
        return [self.cy_name]

    def all_dtypes(self):
        return self.all_dtypes_list # TODO: Generate this instead

    def cy_prototype(self, cfg, in_pxd=True):
        api = '' if cfg.f77binding else 'api '
        template = "cpdef %sobject %%(proc_name)s(%%(arg_list)s)" % api
        # Need to use default values only for trailing arguments
        # Currently, no reordering is done, one simply allows
        # trailing arguments that have defaults (explicit-shape,
        # intent(out) arrays)
        arg_decls = self.arg_mgr.arg_declarations()
        arg_optional_flags = self.arg_mgr.arg_is_optional()
        decls_with_defaults = ['%s=%s' % (decl, (default if not in_pxd else '*'))
                               if is_opt else decl
                               for (decl, default), is_opt in zip(arg_decls, arg_optional_flags)]
        arg_list = ', '.join(decls_with_defaults)
        sdict = dict(proc_name=self.cy_name,
                     arg_list=arg_list)
        return template % sdict

    def proc_declaration(self, ctx):
        return "%s:" % self.cy_prototype(ctx.cfg, in_pxd=False)

    def proc_call(self, ctx):
        if self.return_arg is None:
            return_assign = ''
        else:
            return_assign = '%s = ' % self.return_arg.intern_name
            
        proc_call = "%(return_assign)sfc.%(call_name)s(%(call_arg_list)s)" % dict(
            call_name=self.fc_name,
            call_arg_list=', '.join(self.arg_mgr.call_arg_list(ctx)),
            return_assign=return_assign)
                                        
        return proc_call

    def temp_declarations(self, buf, ctx):
        decls_by_type = {}
        for typepart, namepart in self.arg_mgr.intern_declarations(ctx):
            decls_by_type.setdefault(typepart, []).append(namepart)
        for typepart, nameparts in decls_by_type.iteritems():
            buf.putln('cdef %s %s' % (typepart, ', '.join(nameparts)))

    def return_tuple(self, ctx):
        ret_arg_list = []
        ret_arg_list.extend(self.arg_mgr.return_tuple_list(ctx))
        if len(ret_arg_list) > 1:
            return "return (%s,)" % ", ".join(ret_arg_list)
        elif len(ret_arg_list) == 1:
            return "return %s" % ret_arg_list[0]
        else:
            return ''

    def pre_call_code(self, ctx, buf):
        for line in self.arg_mgr.pre_call_code(ctx):
            buf.putln(line)
        if self.pyf_pre_call_code is not None:
            buf.putln('#TODO: %s' % self.pyf_pre_call_code)

    def post_call_code(self, ctx, buf):
        for line in self.arg_mgr.post_call_code(ctx):
            buf.putln(line)

    def check_error(self, ctx, buf):
        if not ctx.cfg.f77binding:
            ck_err = ('if fw_iserr__ != FW_NO_ERR__:\n'
                      '    raise RuntimeError(\"an error was encountered '
                      'when calling the \'%s\' wrapper.")') % self.cy_name
            buf.putlines(ck_err)

    def post_try_finally(self, ctx, buf):
        post_cc = CodeBuffer()
        self.post_call_code(ctx, post_cc)

        use_try = post_cc.getvalue()

        if use_try:
            buf.putln("try:")
            buf.indent()

        self.check_error(ctx, buf)

        if use_try:
            buf.dedent()
            buf.putln("finally:")
            buf.indent()

        buf.putlines(post_cc.getvalue())

        if use_try:
            buf.dedent()

        if self.pyf_post_call_code is not None:
            buf.putln('#TODO: %s' % self.pyf_post_call_code)


    def get_checks_code(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name):
        for check in self.checks:
            execute_expr, requires, doc = check.substitute(fc_name_to_intern_name,
                                                           fc_name_to_cy_name)
            cs = CodeSnippet(provides=('check', None),
                             requires=[('init', r) for r in requires])
            cs.put('''\
                if not (%(ex)s):
                    raise ValueError('Condition on arguments not satisfied: %(doc)s')''',
                   ex=execute_expr, doc=doc)
            yield cs

    def generate_callback_wrappers(self, ctx, buf):
        for arg in self.call_args:
            if isinstance(arg, CyCallbackArg):
                arg.generate_callback_wrapper(ctx, buf)

    def generate_wrapper(self, ctx, buf):
        self.generate_callback_wrappers(ctx, buf)
        buf.putln(self.proc_declaration(ctx))
        buf.indent()
        self.put_docstring(buf)
        self.temp_declarations(buf, ctx)

        # TODO: Refactor args lists
        args = self.in_args + self.call_args + self.aux_args + self.out_args

        # Map Fortran argument names to names used in Cython wrapper
        fc_name_to_intern_name = dict((arg.name, arg.intern_name) for arg in args)
        fc_name_to_cy_name = dict((arg.name, arg.cy_name) for arg in args)

        snippets = []
        snippets.extend(self.get_checks_code(ctx, fc_name_to_intern_name,
                                             fc_name_to_cy_name))
        
        visited_args = [] # TODO: Immutable nodes would make us able to make set
        # Fetch all code snippets
        for arg in args:
            if arg in visited_args:
                continue
            visited_args.append(arg)
            snippets.extend(arg.get_code_snippets(ctx, fc_name_to_intern_name,
                                                  fc_name_to_cy_name,
                                                  arg in self.in_args,
                                                  arg == self.return_arg))
        # Now sort snippets by phase (for stylistic reasons -- all
        # orderings will yield correctly executing results)
        phases = ['init', 'check']
        snippets.sort(key=lambda cs: phases.index(cs.provides[0]))
        # Do a stable topological sort and emit code
        code.emit_code_snippets(snippets, buf)
        
        self.pre_call_code(ctx, buf)
        buf.putln(self.proc_call(ctx))
        self.post_try_finally(ctx, buf)
        rt = self.return_tuple(ctx)
        if rt: buf.putln(rt)
        buf.dedent()

    def put_docstring(self, buf):
        dstring = self.docstring()
        buf.putln('"""' + dstring[0])
        buf.putlines(dstring[1:])
        buf.putempty()
        buf.putln('"""')

    def dstring_signature(self):
        idx = 0
        try:
            idx = list(self.arg_mgr.arg_is_optional()).index(True)
        except ValueError:
            mandatory = self.in_args
            optional = []
        else:
            mandatory = self.in_args[:idx]
            optional = self.in_args[idx:]
        in_arg_str = ", ".join([x.cy_name for x in mandatory])
        if len(optional) > 0:
            in_arg_str += "[, %s]" % ", ".join([x.cy_name for x in optional])
        dstring = "%s(%s)" % (self.cy_name, in_arg_str)
        doc_ret_vars = self.arg_mgr.docstring_return_tuple_list()
        out_args = ", ".join(doc_ret_vars)
        if len(doc_ret_vars) > 1:
            dstring = '%s -> (%s)' % (dstring, out_args)
        elif len(doc_ret_vars) == 1:
            dstring = '%s -> %s' % (dstring, out_args)

        return [dstring]

    def docstring(self):
        dstring = []
        dstring += self.dstring_signature()
        descrs = self.arg_mgr.docstring_in_descrs()
        dstring += [""]
        dstring += ["Parameters",
                    "----------"]
        if descrs:
            dstring.extend(descrs)
        else:
            dstring += ["None"]
        descrs = self.arg_mgr.docstring_out_descrs()
        if descrs:
            dstring += [""]
            dstring += ["Returns",
                        "-------"]
            dstring.extend(descrs)

        return dstring

    def get_fortran_name(self):
        if self.pyf_fortranname is not None:
            return self.pyf_fortranname
        else:
            return self.name

class CythonExpression(object):
    """
    Object used to store cy_default_value. Consists of a template
    expression of the form "%(x)s + %(by)s", where the names correspond
    to variable names used in Fortran; and a
    list of dependencies (variables used in the expression).  To use,
    call substitute with a map from Fortran name of
    arguments/variables to the equivalent in generated Cython code.
    """
    def __init__(self, template, requires, doc='', is_literal=None):
        self.template = template
        self.requires = requires
        self.doc = doc
        self._is_literal = is_literal

    def substitute(self, variable_map, doc_variable_map=None):
        if doc_variable_map is None:
            doc_variable_map = variable_map
        return (self.template % variable_map,
                [variable_map[x] for x in self.requires],
                self.doc % doc_variable_map)

    def is_literal(self):
        if self._is_literal is None:
            try:
                self.as_literal()
            except ValueError:
                return False
            else:
                return True
        else:
            return self._is_literal

    def as_literal(self):
        try:
            expr, requires, doc = self.substitute({})
        except KeyError:
            raise ValueError('Is not a literal')
        if len(requires) != 0:
            raise ValueError('Is not a literal')
        return expr

    def __eq__(self, other):
        if self is other: return True
        return (type(self) == type(other) and
                self.template == other.template and
                self.requires == other.requires and
                self.doc == other.doc)

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "<CythonExpression %r (depends: %r)>" % (self.template, self.requires)


as_fortran_array_utility_code = u"""
cdef np.ndarray fw_asfortranarray(object value, int typenum, int ndim,
                                  np.intp_t * shape, bint copy,
                                  bint create, int alignment=1):
    cdef int flags = np.NPY_F_CONTIGUOUS
    cdef int i
    cdef np.npy_intp *result_shape
    cdef np.ndarray result
    if value is None:
        if create:
            result = np.PyArray_ZEROS(ndim, shape, typenum, 1)
        else:
            raise TypeError('Expected array but None provided')
    else:
        if ndim <= 1:
            # See http://projects.scipy.org/numpy/ticket/1691 for why this is needed
            flags |= np.NPY_C_CONTIGUOUS
        if (not copy and alignment > 1 and np.PyArray_Check(value) and
            (<Py_ssize_t>np.PyArray_DATA(value) & (alignment - 1) != 0)):
            # mis-aligned array
            copy = True    
        if copy:
            flags |= np.NPY_ENSURECOPY
        result = np.PyArray_FROMANY(value, typenum, ndim, ndim, flags)
        result_shape = np.PyArray_DIMS(result)
        for i in range(ndim):
            shape[i] = result_shape[i]
    return result
"""

as_fortran_array_f2pystyle_utility_code = u"""
cdef np.ndarray fw_asfortranarray(object value, int typenum, int ndim,
                                  np.intp_t * coerced_shape,
                                  bint copy, bint create, int alignment=1):
    cdef int flags = np.NPY_F_CONTIGUOUS | np.NPY_FORCECAST
    cdef np.ndarray result
    cdef np.npy_intp * in_shape
    cdef int in_ndim
    cdef int i
    if value is None:
        if create:
            result = np.PyArray_ZEROS(ndim, coerced_shape, typenum, 1)
        else:
            raise TypeError('Expected array but None provided')
    else:
        if ndim <= 1:
            # See http://projects.scipy.org/numpy/ticket/1691 for why this is needed
            flags |= np.NPY_C_CONTIGUOUS
        if (not copy and alignment > 1 and np.PyArray_Check(value) and
            (<Py_ssize_t>np.PyArray_DATA(value) & (alignment - 1) != 0)):
            # mis-aligned array
            copy = True
        if copy:
            flags |= np.NPY_ENSURECOPY
        result = np.PyArray_FROMANY(value, typenum, 0, 0, flags)
    in_ndim = np.PyArray_NDIM(result)
    if in_ndim > ndim:
        raise ValueError("Dimension of array must be <= %d" % ndim)
    in_shape = np.PyArray_DIMS(result)
    for i in range(in_ndim):
        coerced_shape[i] = in_shape[i]
    for i in range(in_ndim, ndim):
        # Pad shape with ones on right side if necessarry
        coerced_shape[i] = 1
    return result
"""


##     if result.ndim != ndim:
##         # TODO: Optimize

##         # Emulate f2py array handling.
##         # First, ignore any 1-length dimension
##         new_shape = [x for x in result.shape if x > 1]
##         if len(new_shape) > ndim:
##             # Flatten extra trailing dimensions
##             lastdim = 1
##             for d in new_shape[ndim - 1:]:
##                 lastdim *= d
##             new_shape = new_shape[:ndim - 1] + [lastdim]
##         else:
##             # Append 1-length dimensions
##             new_shape += [1 if (result.size > 0) else 0] * (ndim - len(new_shape))
## #        import sys
## #        sys.stderr.write(str(new_shape))
## #        sys.stderr.write(str(result.ndim))
## #        sys.stderr.write('\\n')
##         #sys.stderr.write(repr(result.reshape(new_shape).flags))
## #        a, b = result.reshape(new_shape, order='F'), result
## #        sys.stderr.write('%s %s <---\\n' % (a.strides, b.strides))

#        return a, b
#    return result, result

as_char_utility_code = u"""
cdef char fw_aschar(object s):
    cdef char* buf
    try:
        return <char>s # int
    except TypeError:
        pass
    try:
        buf = <char*>s # bytes
    except TypeError:
        s = s.encode('ASCII')
        buf = <char*>s # unicode
    if buf[0] == 0:
        return 0
    elif buf[1] != 0:
        return 0
    else:
        return buf[0]
"""

callback_utility_code = u"""
cdef extern from "setjmp.h":
    ctypedef struct jmp_buf:
        pass    
    int setjmp(jmp_buf env)
    void longjmp(jmp_buf env, int val)

cdef class fw_CallbackInfo(object):
    # Callable object to call
    cdef object callback
    # Pass *extra_args to callback (can be None)
    cdef object extra_args
    # If an exception is raised by callback it is stored here
    cdef object exc
    # Some times, one may want to communicate objects directly that are
    # simply passed through in Fortran (in particular NumPy arrays)
    cdef object arg0, arg1, arg2, arg3, arg4, arg5, arg6, arg7, arg8, arg9
    # For use by longjmp
    cdef jmp_buf jmp
"""

## explicit_shape_array_utility_code = u"""
## cdef object fw_explicitarray(object value, int typenum, int ndim,
##                              np.intp_t *shape, bint copy, bint allow_larger):
##     cdef np.ndarray result = fw_asfortranarray(value, typenum, ndim, copy)
##     cdef int i
##     cdef Py_ssize_t *result_shape = PyArray_DIMS(result)
##     if ndim == 0:
##         return result
##     for i in range(0, ndim - 1):
##         if result_shape[i] != shape[i]
##             and not (allow_larger and result_shape[i] > shape[i])): 
##             raise ValueError("array has wrong shape")
##     if (result_shape[ndim - 1] < shape[ndim - 1] or
##         (not allow_larger and result_shape[ndim - 1] > shape[ndim - 1]):
##         raise ValueError("array has wrong shape")
##     return result
## """
