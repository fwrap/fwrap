#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------
import re
from fwrap import constants
from fwrap.pyf_iface import _py_kw_mangler, py_kw_mangle_expression
from fwrap.cy_wrap import _CyArg, CythonExpression
import pyparsing as prs
from warnings import warn

TODO_PLACEHOLDER = '##TODO (watch any dependencies that may be further down!) %s'
prs.ParserElement.enablePackrat()

class CouldNotMergeError(Exception):
    pass


def translate_default_value(arg, func_name):
    if arg.pyf_default_value is not None:
        defval = arg.pyf_default_value
        cy_default_value = c_to_cython_warn(defval, func_name)
        defer = not cy_default_value.is_literal()
        arg.update(cy_default_value=cy_default_value,
                   pyf_default_value=None,
                   defer_init_to_body=defer)
    
def translate_checks(args, func_name):
    # Note: Removes pyf_check on each arg
    checks = []
    visited = []
    for arg in args:
        if arg in visited:
            continue
        visited.append(arg)
        if arg.pyf_check is not None:
            checks.extend([c_to_cython_warn(c, func_name)
                           for c in arg.pyf_check])
            arg.update(pyf_check=[])
    return checks

def create_from_pyf_postprocess(cython_ast):
    # Called on "fwrap create" command if source is a pyf file.  Does
    # a smaller subset of the parsing that mergepyf_ast does (in
    # particular, reordering of arguments due to callstatement's are
    # not supported, since we don't have access to underlying C or
    # Fortran source).
    #
    # Tree is processed in-place.
    #
    for proc in cython_ast:
        for arg in proc.in_args + proc.aux_args:
            translate_default_value(arg, proc.name)
        checks = translate_checks(proc.in_args + proc.aux_args +
                                  proc.out_args + proc.call_args,
                                  proc.name)
        proc.update(in_args=process_in_args(proc.in_args),
                    checks=checks)
            
def mergepyf_ast(cython_ast, cython_ast_from_pyf):
    # Called on "fwrap mergepyf" command
    # Primarily just copy ast, but merge in select detected manual
    # modifications to the pyf file present in pyf_ast

    # Many pyf procedures can wrap the same function differently...
    pyf_proc_map = {}
    for pyf_proc in cython_ast_from_pyf:
        pyf_proc_map.setdefault(pyf_proc.get_fortran_name(), []).append(pyf_proc)
    result = []
    for proc in cython_ast:
        try:
            pyf_procs = pyf_proc_map.get(proc.name, ())
            for pyf_proc in pyf_procs:
                result.append(mergepyf_proc(proc, pyf_proc))
        except CouldNotMergeError, e:
            warn('Could not import procedure "%s" from .pyf, '
                 'please modify manually: %s' % (proc.name, e))
            result.append(proc.copy())
    return result

_callstatement_re = re.compile(r'^[\s{]*(.*)\(\*f2py_func\)\s*\(([^;]*)\)[\s;]*(.*?)[;}\s]*$')

def parse_callstatement(s):
    m = _callstatement_re.match(s)
    if m is None:
        raise CouldNotMergeError('Unable to parse callstatement! Have a look at '
                                 'callstatement_re:' + s)
    pre_call_code = m.group(1)
    post_call_code = m.group(3)
    arg_exprs = m.group(2)
    if pre_call_code == '':
        pre_call_code = None
    if post_call_code == '':
        post_call_code = None
    return pre_call_code, post_call_code, arg_exprs

def mergepyf_proc(f_proc, pyf_proc):
    #merge_comments = []
    # There are three argument lists to merge:
    # call_args: "proc" definitely has the right one, however we
    #            may want to rename arguments
    # in_args: pyf_proc has the right one
    # out_args: pyf_proc has the right one
    #
    # Try to parse call_statement to figure out as much as
    # possible, and leave the rest to the user.
    func_name = pyf_proc.name
    callstat = pyf_proc.pyf_callstatement
    return_arg = None

    if callstat is None:
        # We can simply use the pyf argument list and be satisfied
        if len(f_proc.call_args) != len(pyf_proc.call_args):
            raise CouldNotMergeError('pyf and f description of function is different')
        # TODO: Verify that types match as well
        call_args = [arg.copy() for arg in pyf_proc.call_args]
        pre_call_code = post_call_code = None
        if f_proc.kind == 'function':
            if (pyf_proc.kind != 'function' or
                f_proc.return_arg != pyf_proc.return_arg):
                raise CouldNotMergeError('return arg differns in pyf and f description')
            return_arg = f_proc.return_arg.copy()
    else:
        # Do NOT trust the name or order in pyf_proc.call_args,
        # but match arguments by their position in the callstatement
        pyf_args = pyf_proc.call_args + pyf_proc.aux_args
        call_args = []

        pre_call_code, post_call_code, arg_exprs = parse_callstatement(callstat)
        arg_exprs = arg_exprs.split(',')

        # Treat return argument as first call_args argument
        fortran_args = f_proc.call_args #[:-2]
        if f_proc.kind == 'function':
            fortran_args.insert(0, f_proc.return_arg)

        if len(fortran_args) != len(arg_exprs):
            raise CouldNotMergeError(
                '"%s": pyf and f disagrees, '
                'len(fortran_args) != len(arg_exprs)' % pyf_proc.name)
        # Build call_args from the strings present in the callstatement
        for idx, (f_arg, expr) in enumerate(zip(fortran_args, arg_exprs)):
            if idx == 0 and f_proc.kind == 'function':
                if pyf_proc.kind == 'subroutine':
                    return_arg = parse_callstatement_arg(expr, f_arg, pyf_args)
                else:
                    return_arg = f_proc.return_arg.copy()
            else:
                arg = parse_callstatement_arg(expr, f_arg, pyf_args)
                call_args.append(arg)



    # Make sure our three lists (in/out/callargs) contain the same
    # argument objects
    arg_by_name = dict((arg.name, arg) for arg in call_args)
    def copy_or_get(arg):
        # Also translate default values
        result = arg_by_name.get(arg.name, None)
        if result is None:
            result = arg.copy()
        return result

    in_args = [copy_or_get(arg) for arg in pyf_proc.in_args]
    out_args = [copy_or_get(arg) for arg in pyf_proc.out_args]
    in_args = process_in_args(in_args)
    aux_args = ([copy_or_get(arg) for arg in pyf_proc.aux_args])

    # Translate C expressions to Cython.
    # The check directives on arguments are moved to the procedure
    # (they often contain more than one argument...)

    checks = translate_checks(in_args + out_args + aux_args + call_args,
                              func_name)
    
    visited = [] # since arguments cannot be hashed
    for arg in in_args + out_args + aux_args + call_args:
        if arg in visited:
            continue
        visited.append(arg)

        if arg.pyf_default_value is None and not arg.is_array:
            for dep in arg.pyf_depend:
                # If one lists an *explicit* depends on a 1-dim array,
                # set default value to len(arr). TODO: Implicit depends.
                dep_arg = arg_by_name[dep]
                if dep_arg.is_array and len(dep_arg.dimension.dims) == 1:
                    if arg.pyf_default_value is not None:
                        raise RuntimeError('depends on multiple array')
                    arg.pyf_default_value = 'len(%s)' % dep

        if arg.is_array and arg.is_explicit_shape:
            dimexprs = [c_to_cython_warn(dim.sizeexpr, func_name)
                        for dim in arg.dimension]
            arg.update(cy_explicit_shape_expressions=dimexprs)

        if arg.is_array:
            # f2py semantics oddity: If one *explicitly* depends the array
            # on the shape scalar, disable truncation
            last_dim_deps = arg.dimension.dims[-1].depnames
            if len(last_dim_deps.intersection(arg.pyf_depend)) > 0:
                arg.update(truncation_allowed=False)
                
        translate_default_value(arg, func_name)

    result = f_proc.copy_and_set(call_args=call_args,
                                 in_args=in_args,
                                 out_args=out_args,
                                 aux_args=aux_args,
                                 checks=checks,
                                 language='pyf',
                                 pyf_pre_call_code=pre_call_code,
                                 pyf_post_call_code=post_call_code,
                                 return_arg=return_arg,
                                 cy_name=pyf_proc.cy_name)
    return result

callstatement_arg_re = re.compile(r'^\s*(&)?\s*([a-zA-Z0-9_]+)(\s*\+\s*([a-zA-Z0-9_]+))?\s*$')
nested_ternary_re = re.compile(r'^\(?(\s*\(\) .*)\?(.*):(.*)\)?$')

def parse_callstatement_arg(arg_expr, f_arg, pyf_args):
    # Parse arg_expr, and return a suitable new argument based on pyf_args
    # Returns None for unparseable/too complex expression
    m = callstatement_arg_re.match(arg_expr)
    if m is not None:
        ampersand, var_name, offset = m.group(1), m.group(2), m.group(4)
        if offset is not None and ampersand is not None:
            raise CouldNotMergeError('Arithmetic on scalar pointer?')
        pyf_arg = [arg for arg in pyf_args if arg.name == var_name]
        if len(pyf_arg) >= 1:
            result = pyf_arg[0].copy()
            if offset is not None:
                if not result.is_array:
                    raise CouldNotMergeError('Passing scalar without taking address?')
                result.update(mem_offset_code=_py_kw_mangler(offset))
            return result
        else:
            return manual_arg(f_arg, arg_expr)
    else:
        try:
            cy_expr = c_to_cython(arg_expr)
        except ValueError:
            return manual_arg(f_arg, arg_expr)
        else:
            return auxiliary_arg(f_arg, cy_expr)

def manual_arg(f_arg, expr):
    # OK, we do not understand the C code in the callstatement in this
    # argument position, but at least introduce a temporary variable
    # and put in a placeholder for user intervention
    return auxiliary_arg(f_arg, CythonExpression(TODO_PLACEHOLDER % expr, ()))

def auxiliary_arg(f_arg, expr):
    assert isinstance(expr, CythonExpression)
    arg = f_arg.copy_and_set(
        cy_name='%s_f' % f_arg.name,
        name='%s_f' % f_arg.name,
        intent=None,
        pyf_hide=True,
        cy_default_value=expr)
    return arg

def process_in_args(in_args):
    # Arguments must be changed as follows:
    # a) Reorder so that arguments with defaults come last
    # b) Parse the default_value into something usable by Cython.
    mandatory = [arg for arg in in_args
                 if not arg.is_optional() and arg.intent != 'out']
    optional = [arg for arg in in_args
                if arg.is_optional() and arg.intent != 'out']
    out_args = [arg for arg in in_args if arg.intent == 'out']
    
    # Process intent(copy) and intent(overwrite). f2py behaviour is to
    # add overwrite_X to the very end of the argument list, so insert
    # new argument nodes.
    overwrite_args = []
    for arg in mandatory + optional:
        if arg.pyf_overwrite_flag:
            flagname = 'overwrite_%s' % arg.cy_name
            arg.overwrite_flag_cy_name = flagname
            overwrite_args.append(
                _CyArg(name=flagname,
                       cy_name=flagname,
                       ktp='bint',
                       intent='in',
                       dtype=None,
                       cy_default_value=CythonExpression(
                           repr(arg.pyf_overwrite_flag_default), ())))

    # Return new set of in_args
    in_args = mandatory + optional + overwrite_args + out_args
    return in_args


class CToCython(object):
    def __init__(self, doc=False):

        def handle_var(s, loc, tok):
            v = tok[0]
            if v.endswith('_capi'):
                raise prs.ParseException('References f2py-specific variable "%s"' % v)
            self.encountered.add(v)
            return '%%(%s)s' % v

        # FollowedBy(NotAny): make sure variables and
        # function calls are not confused
        variables = prs.Regex(r'[a-zA-Z_][a-zA-Z0-9_]*') + prs.FollowedBy(prs.NotAny('('))
        variables.setParseAction(handle_var)

        var_or_literal = variables | prs.Regex('-?[0-9.e\-]+') | prs.quotedString

        def handle_ternary(s, loc, tok):
            tok = tok[0]
            return '(%s if %s else %s)' % (tok[2], tok[0], tok[4])

        def passthrough_op(s, loc, tok):
            return '(%s)' % ' '.join(tok[0])

        # Translate operators. The result string is a template, so % -> %%
        _c_to_cython_bool = {'&&' : 'and', '||' : 'or', '/' : '//', '*' : '*',
                             '%' : '%%'}
        def translate_op(s, loc, tok):
            tok = tok[0]
            translated = [x if idx % 2 == 0 else _c_to_cython_bool[x]
                          for idx, x in enumerate(tok)]
            return '(%s)' % (' '.join(translated))

        def handle_not(s, loc, tok):
            return 'not %s' % tok[0][1]

        def handle_cast(s, loc, tok):
            return '<%s>%s' % (tok[0][0], tok[0][1])

        def handle_func(s, loc, tok):
            func, args = tok[0], tok[1:]
            func = func.lower()
            if func == 'len':
                if doc:
                    return '%s.shape[0]' % args[0]
                else:
                    return '%sshape[0]' % args[0] # FIXME: Depends on name mangling in cy_wrap
            elif func in ('shape', 'old_shape'):
                if doc:
                    r = '%s.shape[%s]' % (args[0], args[1])
                else:
                    r = '%sshape[%s]' % (args[0], args[1]) # FIXME: Depends on name mangling in cy_wrap
                if func.startswith('old'):
                    r = '##TODO Get shape before broadcasting: %s' % r
                return r
            elif func == 'size':
                if doc:
                    return '%s.size' % args[0]
                else:
                    return 'np.PyArray_SIZE(%s)' % args[0]
            elif func in ('abs', 'min', 'max'):
                return '%s(%s)' % (func, ', '.join(args))
            elif func in ('rank', 'old_rank'):
                if doc:
                    r = '%s.ndim' % args[0]
                else:
                    r = 'np.PyArray_NDIM(%s)' % args[0]                
                if func.startswith('old'):
                    r = '##TODO Get ndim before broadcasting: %s' % r
                return r
            else:
                raise prs.ParseException("Unkown function")
            
        expr = prs.Forward()

        func_call = (prs.Word(prs.alphas + '_') + prs.Suppress('(') + expr +
                     prs.ZeroOrMore(prs.Suppress(',') + expr) + prs.Suppress(')'))
        func_call.setParseAction(handle_func)
        cast = prs.Suppress('(') + prs.oneOf('int float') + prs.Suppress(')')

        expr << prs.operatorPrecedence(var_or_literal | func_call, [
            ('!', 1, prs.opAssoc.RIGHT, handle_not),
            (cast, 1, prs.opAssoc.RIGHT, handle_cast),
            (prs.oneOf('* / %'), 2, prs.opAssoc.LEFT, translate_op),
            (prs.oneOf('+ -'), 2, prs.opAssoc.LEFT, passthrough_op),
            (prs.oneOf('== != <= >= < >'), 2, prs.opAssoc.LEFT, passthrough_op),
            (prs.oneOf('|| &&'), 2, prs.opAssoc.LEFT, translate_op),
            (('?', ':'), 3, prs.opAssoc.RIGHT, handle_ternary),
            ]) 

        self.translator = expr + prs.StringEnd()


    zero_re = re.compile(r'^[()0.,\s]+$') # variations of zero...
    literal_re = re.compile(r'^-?[()0-9.,\se\-]+$') # close enough; also matches e.g. (0, 0.)
    complex_literal_re = re.compile(r'^\s*\((-?[0-9.,\s]+),(-?[0-9.,\s]+)\)\s*$')

    def translate(self, s):
        self.encountered = set()
        m = self.complex_literal_re.match(s)
        if m is not None:
            real, imag = m.group(1), m.group(2)
            if self.zero_re.match(imag):
                r = real
            else:
                r = '%s + %s*1j' % (real, imag)
        else:
            try:
                r = self.translator.parseString(s)[0]
            except prs.ParseException, e:
                raise ValueError('Could not auto-translate: %s (%s)' % (s, e))            
            if r[0] == '(' and r[-1] == ')':
                r = r[1:-1]
        return r, self.encountered

_translator_cython = CToCython(doc=False)
_translator_doc = CToCython(doc=True)

def c_to_cython(s):
    r, encountered = _translator_cython.translate(s)
    r_doc, _ = _translator_doc.translate(s)
    return CythonExpression(r, encountered, r_doc)

def c_to_cython_warn(s, func_name):
    try:
        return c_to_cython(s)
    except ValueError, e:
        warn('Problem in %s: %s' % (func_name, e))
        return CythonExpression(TODO_PLACEHOLDER % s, [], s,
                                is_literal=False)
