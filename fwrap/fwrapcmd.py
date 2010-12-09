#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

# encoding: utf-8

import os, sys
import argparse
import logging
import textwrap
from glob import glob
import tempfile
import shutil
import re
from warnings import warn
from textwrap import dedent
from fwrap import fwrapper
from fwrap import configuration
from fwrap import git
from fwrap import fc_wrap, cy_wrap, mergepyf
from fwrap.configuration import Configuration

BRANCH_PREFIX = '_fwrap'
BRANCH = '_fwrap'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

record_update_re = re.compile(r'.*head record update.*', re.IGNORECASE)

def check_in_directory_of(mainfile):
    path, base = os.path.split(mainfile)
    if os.path.realpath(path) != os.getcwd():
        raise NotImplementedError('Please change to the directory of %s' % mainfile)

def get_head_record_update_commit(rev):
    # Try to base on the following head record update commit,
    # otherwise use the commit itself
    children = git.children_of_commit(rev)
    if len(children) == 1:
        # TODO: Speed up by only querying up to parents of
        # wanted commit (i.e. git show --raw --format=format:%P rev,
        # then git rev-list --children HEAD ^parent1 ^parent2
        child_rev = children[0]
        if record_update_re.match(git.get_commit_title(child_rev)):
            return child_rev
        
    warn('Using rev %s directly, not child' % rev)
    return rev
    

def commit_wrapper(cfg, message, skip_head_commit=False):
    pyx_basename = cfg.get_pyx_basename()
    auxiliary_basenames = cfg.get_auxiliary_files()
    message = 'FWRAP %s' % message
    to_add = [pyx_basename] + auxiliary_basenames
    git.add(to_add)
    if len(git.status(to_add)) == 0:
        print 'No changes made to wrapper, no need to commit anything'
    else:
        print 'Making git commit'
        git.commit(message)

def check_ok_to_write(opts):
    try:
        is_vcs_clean = git.clean_index_and_workdir()
    except RuntimeError:
        use_git = False
        if os.path.exists(opts.wrapper_pyx) and not opts.force:
            raise ValueError('File exists (use "create -f" to create wrapper anyway): %s' %
                             opts.wrapper_pyx)
    else:
        use_git = not opts.nocommit
        if not is_vcs_clean and not (opts.force and opts.nocommit):
            raise RuntimeError('git state not clean (use "create -f --nocommit" to create '
                               'wrapper anyway')
    return use_git

def create_cmd(opts):
    use_git = check_ok_to_write(opts)
    check_in_directory_of(opts.wrapper_pyx)    
    cfg = Configuration(opts.wrapper_pyx, cmdline_options=opts)
    cfg.update_version()
    # Add wrapped files to configurtion
    for filename in opts.fortranfiles:
        cfg.add_wrapped_file(filename)
    # Create wrapper
    fwrapper.wrap(cfg.get_source_files(), cfg.wrapper_name, cfg)
    # Commit
    if use_git:
        message = opts.message
        if message is None:
            message = '(do not squash) Created wrapper %s' % opts.wrapper_pyx
        message = ('%s\n\nFiles wrapped:\n%s' %
                   (message, '\n'.join(opts.fortranfiles)))
        commit_wrapper(cfg, message)
    return 0

def update_cmd(opts):
    use_git = check_ok_to_write(opts)
    if not use_git:
        raise RuntimeError('update command can only be used with git; you may as well use create')
    if not git.is_tracked(opts.wrapper_pyx):
        raise RuntimeError('Not tracked by VCS: %s' % opts.wrapper_pyx)
    cfg = Configuration.create_from_file(opts.wrapper_pyx)
    wanted_checksum = cfg.self_sha1

    # Load Fortran AST into memory from Fortran sources before switching branch
    f_source_files = cfg.get_source_files()
    f_ast = fwrapper.parse(f_source_files, cfg)

    start_branch = git.current_branch()
    try:
        git.checkout(BRANCH)
    except RuntimeError:
        # Branch does not exist, so create it
        blame_rev = get_last_update_rev(cfg)
        print 'Last automatic change to %s done in revision %s' % (cfg.get_pyx_filename(),
                                                                   blame_rev)
        print 'Creating "%s" branch from this revision' % BRANCH
        git.create_branch(BRANCH, blame_rev)
        git.checkout(BRANCH)

    # Check that file in branch matches wanted checksum
    checksum_in_branch = configuration.get_self_sha1_of_pyx(opts.wrapper_pyx)
    if wanted_checksum != checksum_in_branch:
        raise RuntimeError('%s in "%s" branch has wrong checksum' %
                           (opts.wrapper_pyx, BRANCH))
        
    # Create wrapper form AST loaded before the branch switch
    fwrapper.generate(f_ast, cfg.wrapper_name, cfg)

    # Commit, switch branch again, and display help text
    message = opts.message
    if message is None:
        message = '(do not squash) Updated wrapper %s' % opts.wrapper_pyx
    commit_wrapper(cfg, message)

    git.checkout(start_branch)
    print dedent('''
    The updated wrapper can be found in the "%(BRANCH)s" branch,
    please pull it in manually with:

        git merge %(BRANCH)s

    The "%(BRANCH)s" branch can either be left until next time
    or removed, at your option. If removed, it will be recreated
    the next time you do "fwrap update".
    ''' % dict(BRANCH=BRANCH))



def mergepyf_cmd(opts):
    use_git = check_ok_to_write(opts)
    if use_git and not git.is_tracked(opts.wrapper_pyx):
        raise RuntimeError('Not tracked by VCS: %s' % opts.wrapper_pyx)
    for f in [opts.wrapper_pyx, opts.pyf]:
        if not os.path.exists(f):
            raise ValueError('No such file: %s' % f)
    orig_cfg = Configuration.create_from_file(opts.wrapper_pyx)
    start_branch = git.current_branch()
    cfg = orig_cfg.copy()
    cfg.update_version()

    if not git.is_tracked(cfg.get_pyx_filename()):
        raise RuntimeError('Not tracked by VCS, aborting: %s' % cfg.get_pyx_basename())
    if not git.clean_index_and_workdir():
        raise RuntimeError('VCS state not clean, aborting')

    # pyf-merging is based on primarily wrapping the Fortran files,
    # but incorporate any changes in pyf files (see mergepyf.py).
    
    # Load Fortran AST from Fortran and pyf sources
    f_source_files = cfg.get_source_files()
    f_ast = fwrapper.parse(f_source_files, cfg)
    pyf_f_ast = fwrapper.parse([opts.pyf], cfg)

    # Find routine names present in Fortran files that are not
    # present in pyf file, and set them as manually excluded.
    # Below we commit removal of this functions as a seperate commit,
    # to keep the history much cleaner.
    routines_in_fortran = [routine.name for routine in f_ast]
    routines_in_pyf = [routine.name for routine in pyf_f_ast]
    excluded_by_pyf = set(routines_in_fortran) - set(routines_in_pyf)
    cfg.exclude_routines(excluded_by_pyf)
    
    f_ast = fwrapper.filter_ast(f_ast, cfg) # remove excluded routines from ast

    # Continue pipeline for both Fortran and pyf
    c_ast = fc_wrap.wrap_pyf_iface(f_ast)
    cython_ast = cy_wrap.wrap_fc(c_ast)
    
    pyf_c_ast = fc_wrap.wrap_pyf_iface(pyf_f_ast)
    pyf_cython_ast = cy_wrap.wrap_fc(pyf_c_ast)

    # Do the merge of Cython ast
    merged_cython_ast = mergepyf.mergepyf_ast(cython_ast, pyf_cython_ast)

    # Loaded what we need of HEAD to memory, time to branch
    orig_branch = git.current_branch()
    temp_branch = checkout_new_branch_from_last_fwrap(cfg)
    
    # If we are removing any routines, generate a seperate changeset for that,
    # based on Fortran sources (with changed configuration/exclusion) only
    if len(excluded_by_pyf) > 0:
        fwrapper.generate(f_ast, cfg.wrapper_name, cfg,
                          c_ast=c_ast, cython_ast=cython_ast)
        commit_wrapper(cfg,
                       message='Removing routines not present in %s' % opts.pyf,
                       skip_head_commit=True)
    # Now, we generate the wrapper using the merged cython AST
    # (This regenerates the _fc-files if the if-test above hits;
    # TODO: break this up some, but overhead is negligible)
    fwrapper.generate(f_ast, cfg.wrapper_name, cfg,
                      c_ast=c_ast, cython_ast=merged_cython_ast)
    message = opts.message
    if message is None:
        message = 'Creating wrapper based on pyf file: %s' % opts.pyf
    commit_wrapper(cfg, message)
    print_help_after_update(orig_branch, temp_branch)
    return 0


def get_last_update_rev(cfg):
    # Find the commit that takes the blame for the self_sha1
    regex = '%s self-sha1 %s' % (configuration.CFG_LINE_HEAD,
                                     cfg.self_sha1)
    blame_rev = git.blame_for_regex(cfg.get_pyx_filename(), regex)
    return blame_rev

def checkout_new_branch_from_last_fwrap(cfg):
    rev = cfg.git_head()
    rev = get_head_record_update_commit(rev)
    temp_branch = git.create_temporary_branch(rev, BRANCH_PREFIX)
    git.checkout(temp_branch)
    return temp_branch

def print_file_status(filename):
    file_cfg = Configuration.create_from_file(filename)
    if file_cfg.version in (None, ''):
        return # not an Fwrapped file
    
    def status_label(has_changed):
        return 
    status_report = file_cfg.wrapped_files_status()
    any_changed = any(needs_update for f, needs_update in status_report)
    print '%s (%s):' % (filename,
                        'needs update, please run "fwrap update %s"' % filename
                        if any_changed else 'up to date')
    for wrapped_file, needs_update in status_report:
        print '    %s%s' % (wrapped_file,
                            ' (changed)' if needs_update else '')
    return any_changed

def status_cmd(opts):
    print 'TODO: Not yet .pyx.in-aware'
    if len(opts.paths) == 0:
        if opts.recursive:
            opts.paths = ['.']
        else:
            opts.paths = glob('*.pyx')
    for path in opts.paths:
        if not os.path.exists(path):
            raise ValueError('No such file or directory: %s' % path)
        if not opts.recursive and not os.path.isfile(path):
            raise ValueError('Please specify --recursive to query a directory')
    needs_update = False
    if opts.recursive:
        for path in opts.paths:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    if filename.endswith('.pyx'):
                        needs_update = needs_update or print_file_status(filename)
    else:
        for filename in opts.paths:
            if os.path.isfile(filename) and filename.endswith('.pyx'):
                needs_update = needs_update or print_file_status(filename)
    return 1 if needs_update else 0
def print_help_after_update(orig_branch, temp_branch):
    # Print help text
    print dedent('''\
       Branch "{temp_branch}" created and wrapper updated. Please:

         a) Merge in any manual changes to the wrapper, e.g.,
         
                git merge {orig_branch}

            PS! Please do not rebase at this step. Otherwise you may
            make it impossible to do "fwrap update" in the future.
            
         b) Once everything is working, merge back and delete the
            temporary branch. 
            
                git checkout {orig_branch}
                git merge {temp_branch}
                git branch -d {temp_branch}
    '''.format(**locals()))
    
def no_project_response(opts):
    print textwrap.fill('Please run "fwrap init"; can not find project '
                        'file %s in this directory or any parent directory.' %
                        PROJECT_FILE)
    return 1

def create_argument_parser():
    parser = argparse.ArgumentParser(prog='fwrap',
                                     description='fwrap command line tool')
    subparsers = parser.add_subparsers(title='commands')

    #
    # create command
    #
    create = subparsers.add_parser('create')
    create.set_defaults(func=create_cmd)
    create.add_argument('-f', '--force', action='store_true',
                        help=('overwrite existing wrapper'))    
    create.add_argument('--nocommit', action='store_true',
                        help=('do not commit resulting wrapper to git'))    
    create.add_argument('-m', '--message',
                        help=('commit log message'))
    configuration.add_cmdline_options(create.add_argument)
    create.add_argument('wrapper_pyx')
    create.add_argument('fortranfiles', metavar='fortranfile', nargs='+')
    
    #
    # update command
    #
    update = subparsers.add_parser('update')
    update.set_defaults(func=update_cmd, nocommit=False, force=False)
    update.add_argument('-m', '--message',
                        help=('commit log message'))
    update.add_argument('wrapper_pyx')

    #
    # mergepyf command
    #
    mergepyf = subparsers.add_parser('mergepyf')
    mergepyf.set_defaults(func=mergepyf_cmd)
    mergepyf.add_argument('wrapper_pyx')
    mergepyf.add_argument('-m', '--message',
                          help=('commit log message'))
    mergepyf.add_argument('pyf')

    #
    # status command
    #

    status = subparsers.add_parser('status')
    status.set_defaults(func=status_cmd)
    status.add_argument('-r', '--recursive', action='store_true',
                        help='Recurse subdirectories')
    status.add_argument('paths', metavar='path', nargs='*')

    return parser
    
def fwrap_main(args):
    argparser = create_argument_parser()
    opts = argparser.parse_args(args)
    if hasattr(opts, 'wrapper_pyx'):
        if (not opts.wrapper_pyx.endswith('.pyx') and
            not opts.wrapper_pyx.endswith('.pyx.in')):
            raise ValueError('Cython wrapper file name must end in .pyx or .pyx.in')
        check_in_directory_of(opts.wrapper_pyx)
        opts.wrapper_pyx = os.path.basename(opts.wrapper_pyx)

    return opts.func(opts)

