#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

# encoding: utf-8

import os
from optparse import OptionParser

from fwrap import constants
from fwrap import gen_config as gc
from fwrap import fc_wrap
from fwrap import cy_wrap
from fwrap.code import CodeBuffer, CodeBufferFixedForm, reflow_fort
from fwrap import configuration
from fwrap.constants import (TYPE_SPECS_SRC, CY_PXD_TMPL, CY_PYX_TMPL,
                             CY_PYX_IN_TMPL, FC_PXD_TMPL, FC_F_TMPL,
                             FC_F_TMPL_F77, FC_HDR_TMPL)


PROJNAME = 'fwproj'

def wrap(sources, name, cfg, output_directory=None, pyf_to_merge=None,
         include_dirs=None):
    r"""Generate wrappers for sources.

    The core wrapping routine for fwrap.  Generates wrappers for the sources
    list.  Compilation of the wrappers is left to external utilities, whether
    distutils or waf.

    :Input:
     - *sources* - (id) Path to source or a list of paths to source to be
       wrapped.
     - *name* - (string) Name of the project and the name of the resulting
       python module
     - *cfg* - (fwrap.configuration.Configuration)
     - *output_directory* - (string) Output files to this directory. The
                            generated contents is not changed
    """

    # validate name
    name = name.strip()
    name = name.replace(' ', '_')

    # Check to see if each source exists and expand to full paths
    source_files = []
    def check(s):
        return os.path.exists(s)
    if isinstance(sources, basestring):
        if check(sources):
            source_files = [sources]
    elif isinstance(sources, (list, tuple)):
        for src in sources:
            if check(src):
                source_files.append(src)
    if not source_files:
        raise ValueError("Invalid source list. %r" % (sources))

    # Parse fortran using fparser, get fortran ast.
    f_ast = parse(source_files, cfg, include_dirs=include_dirs)

    # Generate wrapper files
    created_files = generate(f_ast, name, cfg, output_directory,
                             pyf_to_merge=pyf_to_merge,
                             update_self_sha=True,
                             only_pyf=(len(source_files) == 1 and
                                       source_files[0].endswith('.pyf')))
    return created_files
    

def filter_ast(ast, cfg):
    return [routine for routine in ast if cfg.is_routine_included(routine.name)]

def parse(source_files, cfg, include_dirs=None):
    r"""Parse fortran code returning parse tree

    :Input:
     - *source_files* - (list) List of valid source files
    """
    from fwrap import fwrap_parse, pyf_iface
    ast = fwrap_parse.generate_ast(source_files, include_dirs=None)
    pyf_iface.check_tree(ast, cfg)
    return ast

def generate(fort_ast, name, cfg, output_directory=None,
             pyf_to_merge=None, c_ast=None, cython_ast=None,
             update_self_sha=True, update_pyf_sha=False,
             only_pyf=False):
    r"""Given a fortran abstract syntax tree ast, generate wrapper files

    :Input:
     - *fort_ast* - (`fparser.ProgramBlock`) Abstract syntax tree from parser
     - *name* - (string) Name of the library module
     - *output_directory* - (string) Output files to this directory. The
                            generated contents is not changed

     Raises `Exception.IOError` if writing the generated code fails.
    """
    if output_directory is None:
        output_directory = os.getcwd()

    # Generate wrapping abstract syntax trees
    # logger.info("Generating abstract syntax tress for c and cython.")
    fort_ast = filter_ast(fort_ast, cfg)
    routine_names = [sub.name for sub in fort_ast]
    if cython_ast is None:
        if cfg.f77binding:
            import f77_wrap
            cython_ast = f77_wrap.fortran_ast_to_cython_ast(fort_ast)
        else:
            if c_ast is None:
                c_ast = fc_wrap.wrap_pyf_iface(fort_ast)
            cython_ast = cy_wrap.wrap_fc(c_ast)

    if pyf_to_merge is not None:
        # TODO: refactor
        assert cfg.f77binding
        import f77_wrap, mergepyf
        pyf_f_ast = parse([pyf_to_merge], cfg)
        pyf_ast = f77_wrap.fortran_ast_to_cython_ast(pyf_f_ast)
        cython_ast = mergepyf.mergepyf_ast(cython_ast, pyf_ast)
    elif only_pyf:
        import mergepyf
        mergepyf.create_from_pyf_postprocess(cython_ast)

    # Generate files and write them out
    generators = [ 
                   (generate_cy_pyx,(cython_ast, name, cfg, update_self_sha, update_pyf_sha),
                    (CY_PYX_IN_TMPL if cfg.detect_templates else CY_PYX_TMPL) % name) ]
    if not cfg.no_cpdef:
        generators.append((generate_cy_pxd,(cython_ast, name, cfg), CY_PXD_TMPL % name))
        
    if not cfg.f77binding:
        generators.append((generate_fc_f, (c_ast, name, cfg),
                           (FC_F_TMPL_F77 if cfg.f77binding else FC_F_TMPL) % name ))
        generators.append((generate_type_specs, (c_ast,name), constants.TYPE_SPECS_SRC))
        generators.append((generate_fc_h, (c_ast, name, cfg), FC_HDR_TMPL % name))
        generators.append((generate_fc_pxd,(c_ast, name), FC_PXD_TMPL % name))
    if cfg.f77binding:
        generators.append((generate_f77_h, (fort_ast, name, cfg), FC_HDR_TMPL % name))
        generators.append((generate_f77_pxd, (fort_ast, name, cfg), FC_PXD_TMPL % name))

    created_files = [file_name
                     for generator, args, file_name in generators]
    created_files.sort()
    cfg.auxiliary[:] = [(f, {}) for f in created_files if f != (CY_PYX_TMPL % name)]

    created_files = []
    for (generator, args, file_name) in generators:
        buf = generator(*args)
        write_to_dir(output_directory, file_name, buf)
        created_files.append(file_name)

    return created_files, routine_names

def find_routine_names(source_files, cfg):
    r"""Returns subroutines/functions available in the given source files

    Routines excluded by the given configuration is not included
    in the list.
    """
    from fwrap import fwrap_parse, pyf_iface
    fort_ast = fwrap_parse.generate_ast(source_files)
    return [routine.name for routine in fort_ast]

def write_to_dir(dir, file_name, buf):
    fh = open(os.path.join(dir, file_name), 'w')
    try:
        if isinstance(buf, basestring):
            fh.write(buf)
        else:
            fh.write(buf.getvalue())
    finally:
        fh.close()

def generate_type_specs(f_ast, name):
    buf = CodeBuffer()
    gc.generate_type_specs(f_ast, buf)
    return buf

def generate_cy_pxd(cy_ast, name, cfg):
    buf = CodeBuffer()
    fc_pxd_name = (constants.FC_PXD_TMPL % name).split('.')[0]
    cy_wrap.generate_cy_pxd(cy_ast, fc_pxd_name, buf, cfg)
    return buf

def generate_cy_pyx(cy_ast, name, cfg, update_self_sha, update_pyf_sha):
    buf = CodeBuffer()
    fc_pxd_name = (constants.FC_PXD_TMPL % name).split('.')[0]
    cy_wrap.generate_cy_pyx(cy_ast, name, fc_pxd_name, buf, cfg)
    # Add sha1 to file
    s = buf.getvalue()
    if update_self_sha or update_pyf_sha:
        sha1 = configuration.get_self_sha1(s)
        if update_self_sha:
            cfg.update_self_sha1(sha1)
            s = configuration.update_self_sha1_in_string(s, sha1)
        if update_pyf_sha:
            cfg.update_pyf_sha1(sha1)
            s = configuration.update_self_sha1_in_string(s, sha1, 'pyf')
    return s

def generate_fc_pxd(fc_ast, name):
    buf = CodeBuffer()
    fc_header_name = constants.FC_HDR_TMPL % name
    fc_wrap.generate_fc_pxd(fc_ast, fc_header_name, buf)
    return buf

def generate_fc_f(fc_ast, name, cfg):
    buf = CodeBuffer() if not cfg.f77binding else CodeBufferFixedForm()        
    for proc in fc_ast:
        proc.generate_wrapper(buf, cfg)
        
    if not cfg.f77binding:
        ret_buf = CodeBuffer()
        ret_buf.putlines(reflow_fort(buf.getvalue()))
    else:
        ret_buf = buf

    return ret_buf

def generate_fc_h(fc_ast, name, cfg):
    buf = CodeBuffer()
    fc_wrap.generate_fc_h(fc_ast, constants.KTP_HEADER_SRC, buf, cfg)
    return buf

def generate_f77_h(fort_ast, name, cfg):
    buf = CodeBuffer()
    import f77_wrap
    f77_wrap.generate_fc_h(fort_ast, constants.KTP_HEADER_SRC, buf, cfg)
    return buf

def generate_f77_pxd(fort_ast, name, cfg):
    buf = CodeBuffer()
    import f77_wrap
    fc_header_name = constants.FC_HDR_TMPL % name
    f77_wrap.generate_fc_pxd(fort_ast, fc_header_name, buf, cfg)
    return buf
