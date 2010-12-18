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
        args.append(cy_arg_factory(fw_arg, fw_arg.is_array))

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

def cy_arg_factory(arg, is_array):
    import fc_wrap
    attrs = {}
    attrs['cy_name'] = _py_kw_mangler(arg.name)
    if is_array:
        if arg.dtype.type == 'character':
            cls = CyCharArrayArg
        else:
            cls = _CyArrayArg
        attrs['dimension'] = arg.orig_arg.dimension
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
                not isinstance(arg, _CyErrStrArg))]

def get_aux_args(args):
    return [arg for arg in args if arg.pyf_hide]

def generate_cy_pxd(ast, fc_pxd_name, buf):
    buf.putln('cimport numpy as np')
    buf.putln("from %s cimport *" % fc_pxd_name)
    buf.putln('')
    for proc in ast:
        buf.putln(proc.cy_prototype())

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
    put_cymod_docstring(ast, name, buf)
    buf.putln("np.import_array()")
    buf.putln("include 'fwrap_ktp.pxi'")
    gen_cimport_decls(buf)
    gen_cdef_extern_decls(buf)
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

def put_cymod_docstring(ast, modname, buf):
    dstring = get_cymod_docstring(ast, modname)
    buf.putln('"""' + dstring[0])
    buf.putlines(dstring[1:])
    buf.putempty()
    buf.putln('"""')

# XXX:  Put this in a cymodule class?
def get_cymod_docstring(ast, modname):
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

    dstring += [""]

    dstring += ["Data Types",
                "----------"]
    # Datatypes
    dts = all_dtypes(ast)
    names = sorted([dt.py_type_name() for dt in dts])
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

    def is_optional(self):
        return (self.cy_default_value is not None or self.pyf_default_value is not None)

    def get_code_snippets(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name):
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
            return ["cdef %s %s" % (typedecl, self.intern_name)]
        else:
            return []

    def call_arg_list(self, ctx):
        return ["&%s" % self.intern_name]

    def post_call_code(self, ctx):
        return []

    def pre_call_code(self, ctx):
        return []
    
    def get_code_snippets(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name):
        # Initialization code
        initcs = CodeSnippet(('init', self.intern_name))
        if (self.dtype is not None and self.dtype.type == 'logical' and
            self.intent in ('in', 'inout', None)):
            # emulates PyObject_IsTrue used by f2py:
            initcs.put('%s = 1 if %s else 0' % (self.intern_name, self.cy_name))
        if self.cy_default_value is not None:
            value, requires, doc = self.cy_default_value.substitute(fc_name_to_intern_name,
                                                                    fc_name_to_cy_name)
            initcs.add_requires(('init', r) for r in requires)
            if self.pyf_hide:
                initcs.putln("%s = %s", self.intern_name, value)
            elif self.defer_init_to_body:
                initcs.putln("%s = %s if (%s is not None) else %s",
                             self.intern_name, self.cy_name, self.cy_name,
                             value)
            else:
                pass
        return [initcs]

    def return_tuple_list(self, ctx):
        assert self.cy_name != constants.ERR_NAME
        assert self.intent in ('out', 'inout', None)
        return [self.intern_name]

    def docstring_return_tuple_list(self):
        return _CyArg.return_tuple_list(self, ctx=None)

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
        return ['cdef char *%s = [0, 0]' % self.buf_name]

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

    def return_tuple_list(self, ctx):
        return [self.buf_name]

class _CyStringArg(_CyArg):

    def _update(self):
        super(_CyStringArg, self)._update()
        self.intern_name = 'fw_%s' % self.cy_name
        self.intern_len_name = '%s_len' % self.intern_name
        self.intern_buf_name = '%s_buf' % self.intern_name

    def _get_cy_dtype_name(self):
        return "fw_bytes"

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
        ret = ['cdef %s %s' % (self.cy_dtype_name, self.intern_name),
                'cdef fw_shape_t %s' % self.intern_len_name]
        if self.intent in ('out', 'inout', None):
            ret.append('cdef char *%s' % self.intern_buf_name)
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
        if self.intent == 'in':
            return ['&%s' % self.intern_len_name,
                    '<char*>%s' % self.intern_name]
        else:
            return ['&%s' % self.intern_len_name, self.intern_buf_name]

    def return_tuple_list(self, ctx):
        if self.intent in ('out', 'inout', None):
            return [self.intern_name]
        return []

    def _gen_dstring(self):
        dstring = ["%s : %s" %
                    (self.cy_name, self._get_py_dtype_name())]
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
        return ['cdef fw_character_t %s[%s]' %
                    (self.cy_name, constants.ERRSTR_LEN)]

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
        self.shape_var_name = '%s_shape_' % self.cy_name

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
            
        if self.cy_default_value is not None:
            literal = self.cy_default_value.as_literal()
            if default_array_value_re.match(literal) is None:
                raise NotImplementedError(
                    'Only support zero default array values for now, not: %s' %
                    self.cy_default_value)

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
        decls = ["cdef np.ndarray %s" % self.intern_name]
        if ctx.cfg.f77binding or self.mem_offset_code is not None:
            decls.append("cdef fw_shape_t %s[%d]" %
                         (self.shape_var_name,
                          self.ndims))
        return decls            

    def _get_py_dtype_name(self):
        return self.py_type_name

    def call_arg_list(self, ctx):
        if self.mem_offset_code is not None:
            offset_code = ' + %s' % self.mem_offset_code
        else:
            offset_code = ''
        if ctx.cfg.f77binding or self.mem_offset_code is not None:
            shape_expr = self.shape_var_name
        else:
            shape_expr = 'np.PyArray_DIMS(%s)' % self.intern_name
        return [shape_expr,
                '<%s*>np.PyArray_DATA(%s)%s' %
                (self.ktp, self.intern_name, offset_code)]

    def get_code_snippets(self, ctx, fc_name_to_intern_name, fc_name_to_cy_name):
        d = {'intern' : self.intern_name,
             'extern' : self.cy_name,
             'dtenum' : self.npy_enum,
             'ndim' : self.ndims}
        # Can we allocate the out-array ourselves? Currently this
        # involves trying to parse the size expression to see if it
        # is simple enough.
        # TODO: Move parsing of shapes to _fc.

        
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
        if can_allocate:
            d['shape'] = ', '.join(expr for expr, _, _ in shape_info)

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

        if can_allocate:
            if self.pyf_hide:
                d['from'] = 'None'
            else:
                d['from'] = self.cy_name
            ctx.use_utility_code(explicit_shape_array_utility_code)
            cs.putln('%(intern)s, %(extern)s = fw_explicitshapearray(%(from)s, %(dtenum)s, '
                     '%(ndim)d, [%(shape)s], %(copy)s)' % d)
        else:
            cs.putln('%(intern)s, %(extern)s = fw_asfortranarray(%(extern)s, %(dtenum)s, '
                     '%(ndim)d, %(copy)s)' % d)

        #
        # May need to copy shape into new array as well
        #
        if ctx.cfg.f77binding or self.mem_offset_code is not None:
            ctx.use_utility_code(copy_shape_utility_code)
            cs.putln('fw_copyshape(%s, np.PyArray_DIMS(%s), %d)',
                     self.shape_var_name, self.intern_name, self.ndims)
            arr_shape_expr = self.shape_var_name
        else:
            arr_shape_expr = 'np.PyArray_DIMS(%s)' % self.intern_name
            
        if self.mem_offset_code is not None:
            if self.ndims != 1:
                raise NotImplementedError()
            cs.putln('%s[0] -= %s', self.shape_var_name, self.mem_offset_code)

        yield cs

        #
        # Code for checking explicit shapes in f77binding mode
        #
        if ctx.cfg.f77binding:
            cs = CodeSnippet(('check', self.intern_name),
                             [('init', self.intern_name)])
            d.update(arr_shape_expr=arr_shape_expr)
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
                        if not (0 <= %(expr)s <= %(arr_shape_expr)s[%(idx)d]):
                            raise ValueError("(0 <= %(doc)s <= %(extern)s.shape[%(idx)d]%(mem_offset_code)s) not satisifed")
                    ''' % d)
                else:
                    cs.put(
                        '''\
                        if %(expr)s != %(arr_shape_expr)s[%(idx)d]:
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
            return [self.cy_name]
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
        return ret + ["cdef fw_shape_t %s[%d]" %
                (self.shape_name, self.ndims+1)]

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
                                 arg not in self.aux_args])

    def call_arg_list(self, ctx):
        cal = []
        for arg in self.call_args:
            cal.extend(arg.call_arg_list(ctx))
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
    language = 'fortran'
    aux_args = ()
    checks = ()
    pyf_pre_call_code = None
    pyf_post_call_code = None

    def _update(self):
        self.arg_mgr = CyArgManager(self.in_args, self.out_args, self.call_args,
                                    self.aux_args)
        
    def get_names(self):
        # A template proc can provide more than one name
        return [self.cy_name]

    def all_dtypes(self):
        return self.all_dtypes_list # TODO: Generate this instead

    def cy_prototype(self, in_pxd=True):
        template = "cpdef api object %(proc_name)s(%(arg_list)s)"
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

    def proc_declaration(self):
        return "%s:" % self.cy_prototype(in_pxd=False)

    def proc_call(self, ctx):
        proc_call = "%(call_name)s(%(call_arg_list)s)" % {
                'call_name' : self.fc_name,
                'call_arg_list' : ', '.join(self.arg_mgr.call_arg_list(ctx))}
        return proc_call

    def temp_declarations(self, buf, ctx):
        decls = self.arg_mgr.intern_declarations(ctx)
        for line in decls:
            buf.putln(line)

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
        if self.pyf_post_call_code is not None:
            buf.putln('#TODO: %s' % self.pyf_post_call_code)

    def check_error(self, buf):
        ck_err = ('if fw_iserr__ != FW_NO_ERR__:\n'
                  '    raise RuntimeError(\"an error was encountered '
                           "when calling the '%s' wrapper.\")") % self.cy_name
        buf.putlines(ck_err)

    def post_try_finally(self, ctx, buf):
        post_cc = CodeBuffer()
        self.post_call_code(ctx, post_cc)

        use_try = post_cc.getvalue()

        if use_try:
            buf.putln("try:")
            buf.indent()

        self.check_error(buf)

        if use_try:
            buf.dedent()
            buf.putln("finally:")
            buf.indent()

        buf.putlines(post_cc.getvalue())

        if use_try:
            buf.dedent()


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

    def generate_wrapper(self, ctx, buf):
        buf.putln(self.proc_declaration())
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
                                                  fc_name_to_cy_name))
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
            idx = None
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


class CythonExpression(object):
    """
    Object used to store cy_default_value. Consists of a template
    expression of the form "%(x)s + %(by)s", where the names correspond
    to variable names used in Fortran; and a
    list of dependencies (variables used in the expression).  To use,
    call substitute with a map from Fortran name of
    arguments/variables to the equivalent in generated Cython code.
    """
    def __init__(self, template, requires, doc=''):
        self.template = template
        self.requires = requires
        self.doc = doc

    def substitute(self, variable_map, doc_variable_map=None):
        if doc_variable_map is None:
            doc_variable_map = variable_map
        return (self.template % variable_map,
                [variable_map[x] for x in self.requires],
                self.doc % doc_variable_map)

    def is_literal(self):
        try:
            self.as_literal()
        except ValueError:
            return False
        else:
            return True

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


copy_shape_utility_code = u"""
cdef void fw_copyshape(fw_shape_t *target, np.intp_t *source, int ndim):
    # In f77binding mode, we do not always have fw_shape_t and np.npy_intp
    # as the same type, so must make a copy
    cdef int i
    for i in range(ndim):
        target[i] = source[i]
"""

explicit_shape_array_utility_code = u"""
cdef object fw_explicitshapearray(object value, int typenum, int ndim,
                                  np.intp_t *shape, bint copy):
    if value is None:
        result = np.PyArray_ZEROS(ndim, shape, typenum, 1)
        return result, result
    else:
        return fw_asfortranarray(value, typenum, ndim, copy)
"""

as_fortran_array_utility_code = u"""
cdef object fw_asfortranarray(object value, int typenum, int ndim, bint copy):
    cdef int flags = np.NPY_F_CONTIGUOUS
    if ndim <= 1:
        # See http://projects.scipy.org/numpy/ticket/1691 for why this is needed
        flags |= np.NPY_C_CONTIGUOUS
    if copy:
        flags |= np.NPY_ENSURECOPY
    result = np.PyArray_FROMANY(value, typenum, ndim, ndim, flags)
    return result, result
"""

as_fortran_array_f2pystyle_utility_code = u"""
cdef object fw_asfortranarray(object value, int typenum, int ndim, bint copy):
    cdef int flags = np.NPY_F_CONTIGUOUS | np.NPY_FORCECAST
    if ndim <= 1:
        # See http://projects.scipy.org/numpy/ticket/1691 for why this is needed
        flags |= np.NPY_C_CONTIGUOUS
    if copy:
        flags |= np.NPY_ENSURECOPY
    result = np.PyArray_FROMANY(value, typenum, 0, 0, flags)

    if ndim == result.ndim:
        return result, result
    else:
        to_shape = [None] * ndim
        fw_f2py_shape_coercion(ndim, to_shape, result.ndim, result.shape,
                               result.size)
        return result.reshape(to_shape, order='F'), result

cdef object fw_f2py_shape_coercion(int to_ndim, object to_shape,
                                   int from_ndim, object from_shape,
                                   Py_ssize_t from_size):
    # Logic ported from check_and_fix_dimensions in fortranobject.c
    # Todo: optimize
    if to_ndim > from_ndim:
        to_size = 1
        free_ax = -1
        for i in range(from_ndim):
            d = from_shape[i]
            if d == 0:
                d = 1
            to_shape[i] = d
            to_size *= d
        for i in range(from_ndim, to_ndim):
            if free_ax < 0:
                free_ax = i
            else:
                to_shape[i] = 1
        if free_ax >= 0:
            to_shape[free_ax] = from_size // to_size
    elif to_ndim < from_ndim:
        j = 0
        for i in range(from_ndim):
            while j < from_ndim and from_shape[j] < 2:
                j += 1
            if j >= from_ndim:
                d = 1
            else:
                d = from_shape[j]
                j += 1
            if i < to_ndim:
                to_shape[i] = d
            else:
                to_shape[to_ndim - 1] *= d
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
