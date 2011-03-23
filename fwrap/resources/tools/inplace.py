"""
waf tool for supporting in-place install, in particular useful for
Python projects.

By passing --inplace to 'waf configure', the behaviour of 'waf install'
is changed:

 - Python extensions are dropped directly to the source
   tree.
 - Other shared libraries are put in a 'lib' directory in the project dir
 - rpath is set up for all shared libraries to contain the 'lib' directory
   in the project dir, using the ${ORIGIN} feature of modern ld.so.

BUGS:

This may only work on Linux? Should probe for success of ${ORIGIN} in
rpath and use an absolute path otherwise. And I have no idea about
Windows.
"""

import os
from waflib.Configure import conf
from waflib.TaskGen import after_method, before_method, feature, taskgen_method, extension

def _find_extension_dir_node(sources):
    srcpath = None
    for x in sources:
        if x.is_src() and (x.name.endswith('.pyx') or x.name.endswith('.c')):
            srcpath = x.parent
    return srcpath

@feature('cshlib', 'fcshlib', 'pyext')
@before_method('propagate_uselib_vars', 'apply_link', 'init_pyext')
def apply_inplace_install_path(self):
    if self.env['INPLACE_INSTALL'] and not getattr(self, 'install_path', None):
        if 'pyext' in self.features:
            # Scan sources for likely position of extension source
            srcpath = _find_extension_dir_node(self.source)
            if srcpath is None:
                print self.source
                print AssertionError("Python extension does not have an associated C file...")
                return
            self.install_path = os.path.join(self.bld.srcnode.abspath(), srcpath.srcpath())
        else:
            self.install_path = self.bld.srcnode.make_node('lib').abspath()

@feature('cshlib', 'fcshlib', 'pyext')
@before_method('propagate_uselib_vars', 'apply_link', 'init_pyext')
def apply_inplace_rpath(self):
    if self.env['INPLACE_INSTALL'] and not getattr(self, 'rpath', None):
        if 'pyext' in self.features:
            srcpath = _find_extension_dir_node(self.source)
            if srcpath is None:
                print self.source
                print AssertionError("Python extension does not have an associated C file...")
                return
            lib_path  = self.bld.srcnode.make_node('lib')
            self.rpath = os.path.join('${ORIGIN}', lib_path.path_from(srcpath))
        else:
            self.rpath = '${ORIGIN}'

def options(self):
    self.add_option('--inplace', action='store_true',
                    help='"install" command installs to the project directory')

def configure(self):
    if self.options.inplace:
        self.env['INPLACE_INSTALL'] = True

