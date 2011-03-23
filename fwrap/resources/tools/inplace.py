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

# Note: Python extensions will have their install_path set twice,
# but we use after_method to make sure the pyext setting prevails

@feature('cshlib', 'fcshlib')
@before_method('propagate_uselib_vars', 'apply_link')
def apply_install_path_shlib(self):
    if self.env['INPLACE_INSTALL']:
        self.install_path = self.bld.srcnode.make_node('lib').abspath()
        self.rpath = '${ORIGIN}'

@feature('pyext')
@before_method('propagate_uselib_vars', 'apply_link')
@after_method('apply_install_path_shlib')
def apply_install_path_pyext(self):
    if self.env['INPLACE_INSTALL']:
        # Scan sources for likely position of extension source
        srcpath = None
        for x in self.source:
            if x.is_src() and (x.name.endswith('.pyx') or x.name.endswith('.c')):
                srcpath = x.parent
        if srcpath is None:
            raise AssertionError("Python extension does not have an associated C file...")
        self.install_path = os.path.join(self.bld.srcnode.abspath(), srcpath.srcpath())

        # Set rpath
        lib_path  = self.bld.srcnode.make_node('lib')
        self.rpath = os.path.join('${ORIGIN}', lib_path.path_from(srcpath))

def options(self):
    self.add_option('--inplace', action='store_true',
                    help='"install" command installs to the project directory')

def configure(self):
    if self.options.inplace:
        self.env['INPLACE_INSTALL'] = True

