#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

import re
import sys
from contextlib import contextmanager
from fwrap import pyf_iface as pyf
from fwrap import fort_expr
from fparser import api
from fparser import typedecl_statements


@contextmanager
def max_recursion_depth(n):
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(n)
        yield
    finally:
        sys.setrecursionlimit(old)

def generate_ast(fsrcs):
    ast = []
    for src in fsrcs:
        with max_recursion_depth(5000):
            block = api.parse(src, analyze=True)
        if src.endswith('.pyf'):
            ast.extend(_process_pyf(block))
        else:
            ast.extend(_process_fortran(block))
    return ast

def _process_pyf(block):
    callback_modules = {} # name : [proc]
    regular_procs = []
    for module in block.content:
        if module.blocktype !=  'pythonmodule':
            raise ValueError('not a pythonmodule')
        ifacelst = module.content
        if len(ifacelst) != 2 or ifacelst[0].blocktype != 'interface':
            # 2: There's an EndPythonModule
            raise ValueError('not an inface')
        procs = [proc for proc in ifacelst[0].content
                 if proc.blocktype in ('function', 'subroutine')]
        if '__user__' in module.name:
            # Callback specs
            callback_modules[module.name] = procs
        else:
            regular_procs.extend(procs)
    return [_process_proc(proc, 'pyf', callback_modules)
            for proc in procs]

def _process_fortran(block):
    return [_process_proc(proc, 'fortran', None)
            for proc in block.content]

def _process_proc(proc, language, pyf_callback_modules):
    from fparser.statements import Use
    if not is_proc(proc):
        raise ValueError('not a proc')
    pyf_use = {}
    kw = {}
    if language == 'pyf':
        kw.update(_get_pyf_proc_annotations(proc))
        for statement in proc.content:
            if isinstance(statement, Use):
                pyf_use[statement.name] = pyf_callback_modules[statement.name]
    args = _get_args(proc, language, pyf_use)
    params = _get_params(proc, language)
    kw.update(name=proc.name,
              args=args,
              params=params,
              language=language)
    if proc.blocktype == 'subroutine':
        return pyf.Subroutine(**kw)
    elif proc.blocktype == 'function':
        return pyf.Function(return_arg=_get_ret_arg(proc, language, pyf_use),
                            **kw)

def is_proc(proc):
    return proc.blocktype in ('subroutine', 'function')

def _get_ret_arg(proc, language, pyf_use):
    ret_var = proc.get_variable(proc.result)
    ret_arg = _get_arg(ret_var, language, pyf_use)
    ret_arg.intent = None
    return ret_arg

def _get_param(p_param, language):
    if not p_param.is_parameter():
        raise ValueError("argument %r is not a parameter" % p_param)
    if not p_param.init:
        raise ValueError("parameter %r does not have an initialization "
                         "expression." % p_param)
    p_typedecl = p_param.get_typedecl()
    dtype = _get_dtype(p_typedecl, language)
    name = p_param.name
    intent = _get_intent(p_param, language)
    if not p_param.is_scalar():
        raise RuntimeError("do not support array or derived-type "
                           "parameters at the moment...")
    return pyf.Parameter(name=name, dtype=dtype, expr=p_param.init)

def _get_arg(p_arg, language, pyf_use):

    if not p_arg.is_scalar() and not p_arg.is_array():
        raise RuntimeError(
                "argument %s is neither "
                    "a scalar or an array (derived type?)" % p_arg)

    if p_arg.is_external():
        if language == 'pyf':
            return pyf_callback_arg(p_arg, pyf_use)
        else:
            return callback_arg(p_arg)

    p_typedecl = p_arg.get_typedecl()
    dtype = _get_dtype(p_typedecl, language)
    name = p_arg.name
    if language == 'pyf':
        intent, pyf_annotations = _get_pyf_arg_annotations(p_arg)
    else:
        intent = _get_intent(p_arg, language)
        pyf_annotations = {}

    if p_arg.is_array():
        p_dims = p_arg.get_array_spec()
        dimspec = pyf.Dimension(p_dims)
    else:
        dimspec = None

    return pyf.Argument(name=name,
                        dtype=dtype,
                        intent=intent,
                        dimension=dimspec,
                        **pyf_annotations)

def pyf_callback_arg(p_arg, use):
    for procs in use.values():
        for proc in procs:
            if p_arg.name == proc.name:
                break
        else:
            proc = None
        if proc is not None:
            break
    else:
        raise ValueError() # no proc

    cbproc = _process_proc(proc, 'pyf', use)
    arg = pyf.Argument(name=p_arg.name,
                        callback_procedure=cbproc,
                        dtype=pyf.CallbackType(),
                        intent='in')
    return arg

def callback_arg(p_arg):
    parent_proc = None
    for p in reversed(p_arg.parents):
        try:
            bt = p.blocktype
        except AttributeError:
            continue
        if bt in ('subroutine', 'function'):
            parent_proc = p

    # Subroutine call -- test for 'designator' attribute
    for stmt in parent_proc.content:
        try:
            cb_name = stmt.designator
        except AttributeError:
            pass
        else:
            if cb_name == p_arg.name:
                cbproc = _get_callback_proc(parent_proc, p_arg, cb_name, stmt.items,
                                            is_function=False)
                return pyf.Argument(name=p_arg.name,
                                    callback_procedure=cbproc,
                                    dtype=pyf.CallbackType(),
                                    intent='in')

    # Function call -- find where in procedure body func is called
    func_call_matcher = re.compile(r'\b%s\s*\(' % p_arg.name).search
    for stmt in parent_proc.content:
        if isinstance(stmt, typedecl_statements.TypeDeclarationStatement):
            continue
        source_line = stmt.item.get_line()
        if func_call_matcher(source_line):
            assert len(stmt.item.strlinemap) == 1
            cb_name = p_arg.name
            arg_lst = stmt.item.strlinemap.values()[0]
            cbproc = _get_callback_proc(parent_proc, p_arg, cb_name, arg_lst,
                                        is_function=True)
            return pyf.Argument(name=p_arg.name, dtype=pyf.CallbackType(),
                                callback_procedure=cbproc,
                                intent='in')

    raise ValueError('Found no call of %s' % p_arg.name)

def _get_callback_proc(parent_proc, p_arg, proc_name, arg_lst, is_function):
    from fort_expr import parse, ExpressionType, NameNode
    if isinstance(arg_lst, list):
        arg_lst = ', '.join(arg_lst)
    proc_call = '%s(%s)' % (proc_name, arg_lst)
    proc_ref = parse(proc_call)
    args = proc_ref.arg_spec_list
    type_ctx = {}
    bounds = {}
    for vname in parent_proc.a.variables:
        if vname == proc_name:
            continue
        v = parent_proc.a.variables[vname]
        bounds[vname] = v.bounds
        type_ctx[vname] = v.get_typedecl()
    type_visitor = ExpressionType(type_ctx)

    kw = {}
    cb_args = []
    arg_dtypes = []
    arg_dims = []
    arg_names = []
    for arg in args:
        if isinstance(arg.arg, fort_expr.EmptyNode):
            continue
        arg_dt = _get_dtype(type_visitor.visit(arg), 'fortran')
        if isinstance(arg.arg, NameNode) and arg.arg.name in type_ctx:
            # If call argument is a simple name node, we record the
            # name to make manual modification of wrapper a bit easier.
            # Also, record array bound information.
            name = arg.arg.name
            bound = bounds[name]
            dimspec = None if bound is None else pyf.Dimension(bound)
        else:
            dimspec = None
            name = None
        cb_args.append(pyf.Argument(name=name, dtype=arg_dt, dimension=dimspec))
        
    kw.update(name=p_arg.name,
              args=cb_args,
              params=[],
              language='fortran')
    if is_function:
        assert False, 'not implemented yet'
        kw.update()# ret_arg
    else:
        cls = pyf.Subroutine
        
    return cls(**kw)
        
def _get_args(proc, language, pyf_use):
    args = []
    for argname in proc.args:
        p_arg = proc.get_variable(argname)
        args.append(_get_arg(p_arg, language, pyf_use))
    return args

def _get_params(proc, language):
    params = []
    for varname in proc.a.variables:
        var = proc.a.variables[varname]
        if var.is_parameter():
            params.append(_get_param(var, language))
    return params

def _get_intent(arg, language):
    assert language != 'pyf'
    intents = []
    if not arg.intent:
        intents.append("inout")
    else:
        if arg.is_intent_in():
            intents.append("in")
        if arg.is_intent_inout():
            intents.append("inout")
        if arg.is_intent_out():
            intents.append("out")
    if not intents:
        raise RuntimeError("argument has no intent specified, '%s'" % arg)
    if len(intents) > 1:
        raise RuntimeError(
                "argument has multiple "
                    "intents specified, '%s', %s" % (arg, intents))
    return intents[0]

def _get_pyf_proc_annotations(proc):
    from fparser.statements import Intent, CallStatement, FortranName
    pyf_wraps_c = False
    pyf_callstatement = None
    pyf_fortranname = None
    for line in proc.content:
        if isinstance(line, Intent) and 'C' in line.specs:
            pyf_wraps_c = True
        elif isinstance(line, CallStatement):
            pyf_callstatement = line.expr
        elif isinstance(line, FortranName):
            pyf_fortranname = line.value

    return dict(pyf_wraps_c=pyf_wraps_c,
                pyf_callstatement=pyf_callstatement,
                pyf_fortranname=pyf_fortranname)

def _get_pyf_arg_annotations(arg):
    # Parse Fwrap-compatible intents
    pyf_no_return = False
    if arg.is_intent_inout():
        intent = "inout"
        pyf_no_return = True
    elif arg.is_intent_in() and arg.is_intent_out():
        # The "in,out" feature of f2py corresponds to fwrap's inout
        intent = "inout"
    elif arg.is_intent_in():
        intent = "in"
    elif arg.is_intent_out():
        intent = "out"
    elif arg.is_intent_hide():
        intent = None
    else:
        intent = "inout"

    # Parse intents that are not in Fortran (custom annotations)
    hide = arg.is_intent_hide() and not arg.is_intent_out()

    if arg.is_intent_copy() and arg.is_intent_overwrite():
        raise RuntimeError('intent(copy) conflicts with intent(overwrite)')
    elif arg.is_intent_copy():
        overwrite_flag = True
        overwrite_flag_default = False
    elif arg.is_intent_overwrite():
        overwrite_flag = True
        overwrite_flag_default = True
    else:
        overwrite_flag = False
        overwrite_flag_default = None

    align = None
    if arg.intent is not None:
        if 'ALIGNED4' in arg.intent:
            align = 4
        elif 'ALIGNED8' in arg.intent:
            align = 8
        elif 'ALIGNED16' in arg.intent:
            align = 16

    pyf_by_value = (arg.intent is not None) and ('C' in arg.intent)
        
    annotations = dict(pyf_hide=hide,
                       pyf_default_value=arg.init,
                       pyf_check=arg.check,
                       pyf_overwrite_flag=overwrite_flag,
                       pyf_overwrite_flag_default=overwrite_flag_default,
                       # optional fills a rather different role in pyf files
                       # compared to in F90 files, so we use a seperate flag
                       pyf_optional=arg.is_optional(),
                       pyf_depend=arg.depend,
                       pyf_align=align,
                       pyf_by_value=pyf_by_value,
                       pyf_no_return=pyf_no_return
                       )

    return intent, annotations

name2default = {
        'integer' : pyf.default_integer,
        'real'    : pyf.default_real,
        'doubleprecision' : pyf.default_dbl,
        'complex' : pyf.default_complex,
        'doublecomplex' : pyf.default_double_complex,
        'character' : pyf.default_character,
        'logical' : pyf.default_logical,
        }

name2type = {
        'integer' : pyf.IntegerType,
        'real' : pyf.RealType,
        'complex' : pyf.ComplexType,
        'character' : pyf.CharacterType,
        'logical' : pyf.LogicalType,
        }

def _get_dtype(typedecl, language):
    if not typedecl.is_intrinsic():
        raise RuntimeError(
                "only intrinsic types supported ATM... [%s]" % str(typedecl))
    length, kind = typedecl.selector
    return create_dtype(typedecl.name, length, kind)

def create_dtype(name, length, kind):
    if not kind and not length:
        return name2default[name]
    if length and kind and name != 'character':
        raise RuntimeError("both length and kind specified for "
                               "non-character intrinsic type: "
                               "length: %s kind: %s" % (length, kind))
    if name == 'character':
        if length == '*':
            fw_ktp = '%s_xX' % (name)
        else:
            fw_ktp = '%s_x%s' % (name, length)
        return pyf.CharacterType(fw_ktp=fw_ktp,
                        len=length, kind=kind)
    if length and not kind:
        return name2type[name](fw_ktp="%s_x%s" %
                (name, length),
                length=length)
    try:
        int(kind)
    except ValueError:
        raise RuntimeError(
                "only integer constant kind "
                    "parameters supported ATM, given '%s'" % kind)
    if name == 'doubleprecision':
        return pyf.default_dbl
    return name2type[name](fw_ktp="%s_%s" %
            (name, kind), kind=kind)
