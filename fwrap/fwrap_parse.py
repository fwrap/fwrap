#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

import re
import sys
import os
import tempfile
from fwrap.git import execproc
from contextlib import contextmanager
from fwrap import pyf_iface as pyf
from fwrap import fort_expr
from fparser import api
import fparser
from fparser import typedecl_statements
from fparser.parsefortran import FortranParser


@contextmanager
def max_recursion_depth(n):
    old = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(n)
        yield
    finally:
        sys.setrecursionlimit(old)

def parse_files(fsrcs, include_dirs):
    # Turns a list of source files into a list of
    # fparser...BeginSource
    result = []
    for src in fsrcs:
        reader = fparser.api.get_reader(src, include_dirs=include_dirs,
                                        ignore_comments=True)
        parser = FortranParser(reader, ignore_comments=True)
        with max_recursion_depth(5000):
            parser.parse()
        result.append(parser.block)
    return result

def sort_modules(blocks):
    # Turns a list of BeginSource into
    # [nodes in root namespace], { modulename: Module-instance }
    from fparser.block_statements import Module, EndModule
    modules = {}
    root_nodes = []
    for begsource in blocks:
        for node in begsource.content:
            if isinstance(node, Module):
                modules[node.name] = node
            elif isinstance(node, EndModule):
                pass
            else:
                root_nodes.append(node)
    return root_nodes, modules

def analyze_modules(root_nodes, modules):
    import fparser.statements
    analyzed = set()

    def lookup_module(name):
        try:
            mod = modules[name]
        except KeyError:
            return # module not available
        if name not in analyzed:
            mod.analyze()
            analyzed.add(name)
        return mod
        
    # Horrible hack...TODO: fix fparser
    fparser.statements.Use_lookup_module_callback = lookup_module
    
    for name in modules.keys():
        lookup_module(name)

    for node in root_nodes:
        node.analyze()

def parse_modules(fsrcs, include_dirs=None):
    temporaries = []
    def preprocess(filename):
        if not filename.endswith('.F90'):
            return filename
        path = os.path.split(os.path.realpath(filename))[0]
        base, ext = os.path.splitext(os.path.basename(filename))
        fd, tmp = tempfile.mkstemp('.f90', prefix='fw-%s-' % base, dir=path)
        temporaries.append(tmp)
        os.close(fd)
        execproc(['gcc', '-E', '-P', '-o', tmp, x])
        return tmp
    
    try:
        fsrcs = [preprocess(x) for x in fsrcs]
        blocks = parse_files(fsrcs, include_dirs)
    finally:
        for t in temporaries:
            if os.path.exists(t):
                os.unlink(t)
        
    root_nodes, modules = sort_modules(blocks)

    module_iface_trees = {}
    analyze_modules(root_nodes, modules)
    for name, module in modules.iteritems():
        iface_tree = FParserToIfaceTransform('fortran').process(module)
        module_iface_trees[name] = iface_tree
    root = FParserToIfaceTransform('fortran').process(root_nodes)
    if len(root) > 0:
        module_iface_trees[None] = root
    return module_iface_trees

def generate_ast(fsrcs, include_dirs=None):
    ast = []
    for src in fsrcs:
        with max_recursion_depth(5000):
            block = api.parse(src, analyze=True, include_dirs=include_dirs)
        transform = FParserToIfaceTransform('pyf' if src.endswith('.pyf') else 'fortran')
        ast.extend(transform.process(block))
    return ast

class FParserToIfaceTransform(object):

    def __init__(self, language):
        self.language = language

    def process(self, nodes):
        self.module = None
        if self.language == 'pyf':
            return self.process_pyf(nodes)
        elif self.language == 'fortran':
            return self.process_fortran(nodes)
        else:
            raise ValueError()

    def process_pyf(self, nodes):
        from fparser.block_statements import ProgramBlock
        callback_modules = {} # name : [proc]
        regular_procs = []
        if isinstance(nodes, ProgramBlock):
            nodes = nodes.content
        for module in nodes:
            if module.blocktype !=  'pythonmodule':
                raise ValueError('not a pythonmodule')
            procs = []
            for iface in module.content:
                if iface.blocktype != 'interface':
                    if iface.blocktype == 'pythonmodule': # end marker
                        continue
                    raise ValueError('not an interface:' + iface.blocktype)
                procs.extend(proc for proc in iface.content
                             if proc.blocktype in ('function', 'subroutine'))
            if '__user__' in module.name:
                # Callback specs
                callback_modules[module.name] = procs
            else:
                regular_procs.extend(procs)
        return [self._process_proc(proc, callback_modules)
                for proc in procs]

    def process_fortran(self, block):
        from fparser.statements import Use, Access, Contains
        from fparser.typedecl_statements import Implicit, TypeDeclarationStatement
        from fparser.block_statements import (Function, Subroutine, Interface, Module,
                                              EndModule, BeginSource)
                                              
        self.language = 'fortran'
        # Assume that all use clauses come before routine definitions
        if isinstance(block, BeginSource):
            if len(block.content) >= 1 and isinstance(block.content[0], Module):
                if len(block.content) > 1:
                    raise NotImplementedError(
                        'Please use "fwrap createpackage" to wrap multiple modules')
                return self.process_fortran(block.content[0].content)
            else:
                self.module_uses = []
                self.module = None
                return self.process_fortran(block.content)
        elif isinstance(block, Module):
            self.module_uses = []
            self.module = block
            res = self.process_fortran(block.content)
            self.module = None
            self.module_uses = []
            return res
        elif isinstance(block, list):
            ast = []
            for node in block:
                if isinstance(node, Use):
                    self.module_uses.append(node.name)
                elif isinstance(node, (Function, Subroutine)):
                    if self.module is not None and self.module.check_private(node.name):
                        # Private proc
                        continue
                    else:
                        ast.append(self._process_proc(node, None))
                elif isinstance(node, (Implicit, TypeDeclarationStatement,
                                       Interface, Access, Contains, EndModule)):
                    continue # ignore
                else:
                    raise NotImplementedError("Node type %r" % type(node))
            return ast
        else:
            assert False
    
    def _process_proc(self, proc, pyf_callback_modules):
        from fparser.statements import Use
        if not is_proc(proc):
            raise ValueError('not a proc')
        pyf_use = {}
        kw = {}
        self.proc_uses = []
        language = self.language
        if language == 'pyf':
            kw.update(_get_pyf_proc_annotations(proc))
        for statement in proc.content:
            if isinstance(statement, Use):
                if language == 'pyf':
                    pyf_use[statement.name] = pyf_callback_modules[statement.name]
                else:
                    self.proc_uses.append(statement.name)
        args = self._get_args(proc, pyf_use)
        params = self._get_params(proc)
        kw.update(name=proc.name,
                  args=args,
                  params=params,
                  module_name=None if self.module is None else self.module.name,
                  language=language)
        if proc.blocktype == 'subroutine':
            r = pyf.Subroutine(**kw)
        elif proc.blocktype == 'function':
            r = pyf.Function(return_arg=self._get_ret_arg(proc, pyf_use),
                             **kw)
        del self.proc_uses
        return r

    def _get_args(self, proc, pyf_use):
        args = []
        for argname in proc.args:
            p_arg = proc.get_variable(argname)
            args.append(self._get_arg(p_arg, pyf_use))
        return args

    def _get_params(self, proc):
        params = []
        for varname in proc.a.variables:
            var = proc.a.variables[varname]
            if var.is_parameter():
                params.append(self._get_param(var))
        return params

    def _get_intent(self, arg):
        assert self.language != 'pyf'
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

    def _get_ret_arg(self, proc, pyf_use):
        ret_var = proc.get_variable(proc.result)
        ret_arg = self._get_arg(ret_var, pyf_use)
        ret_arg.intent = None
        return ret_arg


    def _get_param(self, p_param):
        if not p_param.is_parameter():
            raise ValueError("argument %r is not a parameter" % p_param)
        if not p_param.init:
            raise ValueError("parameter %r does not have an initialization "
                             "expression." % p_param)
        p_typedecl = p_param.get_typedecl()
        dtype = self._get_dtype(p_typedecl)
        name = p_param.name
        intent = self._get_intent(p_param)
        if not p_param.is_scalar():
            raise RuntimeError("do not support array or derived-type "
                               "parameters at the moment...")
        return pyf.Parameter(name=name, dtype=dtype, expr=p_param.init)

    def _get_arg(self, p_arg, pyf_use):

        if not p_arg.is_scalar() and not p_arg.is_array():
            raise RuntimeError(
                    "argument %s is neither "
                        "a scalar or an array (derived type?)" % p_arg)

        if p_arg.is_external():
            if self.language == 'pyf':
                return pyf_callback_arg(p_arg, pyf_use)
            else:
                return callback_arg(p_arg)

        p_typedecl = p_arg.get_typedecl()
        dtype = self._get_dtype(p_typedecl)
        name = p_arg.name
        if self.language == 'pyf':
            intent, pyf_annotations = self._get_pyf_arg_annotations(p_arg)
        else:
            intent = self._get_intent(p_arg)
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

    def pyf_callback_arg(self, p_arg, use):
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

        cbproc = self._process_proc(proc, use)
        arg = pyf.Argument(name=p_arg.name,
                            callback_procedure=cbproc,
                            dtype=pyf.CallbackType(),
                            intent='in')
        return arg

    def _get_dtype(self, typedecl):
        if not typedecl.is_intrinsic():
            raise RuntimeError(
                "only intrinsic types supported ATM... [%s]" % str(typedecl))
        length, kind = typedecl.selector
        return create_dtype(typedecl.name, length, kind,
                            possible_modules=self._get_current_modules())

    def _get_current_modules(self):
        return set(self.module_uses) | set(self.proc_uses)


def is_proc(proc):
    return proc.blocktype in ('subroutine', 'function')


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

    # Probably passed on to another function. Horrible fallback,
    # but useful when later merging in pyf information.
    cbproc = pyf.Subroutine(name=p_arg.name,
                            args=[],
                            params=[],
                            language='fortran')

    return pyf.Argument(name=p_arg.name, dtype=pyf.CallbackType(),
                        callback_procedure=cbproc)
    

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
    for idx, arg in enumerate(args):
        if isinstance(arg.arg, fort_expr.EmptyNode):
            continue
        typespec = type_visitor.visit(arg)
        if typespec is None:
            arg_dt = pyf.default_real # Horrible fallback...
        else:
            arg_dt = _get_dtype(typespec, 'fortran')
        if isinstance(arg.arg, NameNode) and arg.arg.name in type_ctx:
            # If call argument is a simple name node, we record the
            # name to make manual modification of wrapper a bit easier.
            # Also, record array bound information.
            name = arg.arg.name
            bound = bounds[name]
            dimspec = None if bound is None else pyf.Dimension(bound)
        else:
            dimspec = None
            name = 'arg%d' % idx
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

def create_dtype(name, length, kind, possible_modules):
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
        pass # hope it is in possible_modules
    else:
        possible_modules = () # no need to carry along these
    if name == 'doubleprecision':
        return pyf.default_dbl
    return name2type[name](fw_ktp="%s_%s" %
            (name, kind), kind=kind, possible_modules=possible_modules)
