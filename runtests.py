#!/usr/bin/python

import os, sys, re, shutil, unittest, doctest, contextlib
from glob import glob
from StringIO import StringIO

WITH_CYTHON = True

TEST_DIRS = ['compile', 'errors', 'run', 'pyregr']
TEST_RUN_DIRS = ['run', 'pyregr']

flags_re = re.compile(r'^(!|C)\s+configure-flags:(.*)$', re.MULTILINE)

def parse_testcase_flag_sets(filename):
    with file(filename) as f:
        contents = f.read()
    result = []
    for m in flags_re.finditer(contents):
        result.append(m.group(2).split())
    return result

@contextlib.contextmanager
def process_args_as(argv):
    # For calling f2py...
    old = sys.argv
    try:
        sys.argv = sys.argv[0:1] + argv
        yield
    finally:
        sys.argv = old

@contextlib.contextmanager
def working_directory(path):
    old = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(old)

class FwrapTestBuilder(object):
    def __init__(self, rootdir, workdir, selectors, exclude_selectors,
                 cleanup_workdir, cleanup_sharedlibs, verbosity=0,
                 configure_flags=()):
        self.rootdir = rootdir
        self.workdir = workdir
        self.selectors = selectors
        self.exclude_selectors = exclude_selectors
        self.cleanup_workdir = cleanup_workdir
        self.cleanup_sharedlibs = cleanup_sharedlibs
        self.verbosity = verbosity
        self.configure_flags = configure_flags

    def build_suite(self):
        suite = unittest.TestSuite()
        test_dirs = TEST_DIRS
        filenames = os.listdir(self.rootdir)
        filenames.sort()
        for filename in filenames:
            path = os.path.join(self.rootdir, filename)
            if os.path.isdir(path) and filename in test_dirs:
                suite.addTest(
                        self.handle_directory(path, filename))
        return suite

    def handle_directory(self, path, context):
        workdir = os.path.join(self.workdir, context)
        if not os.path.exists(workdir):
            os.makedirs(workdir)

        suite = unittest.TestSuite()
        filenames = os.listdir(path)
        for filename in filenames:
            is_subdir = os.path.isdir(os.path.join(path, filename))
            if (not is_subdir and
                (os.path.splitext(filename)[1].lower() not in (".f", ".f77", ".f90", ".f95") or
                 filename.startswith('.'))):
                continue
            basename = os.path.splitext(filename)[0]
            fqbasename = "%s.%s" % (context, basename)
            if not [1 for match in self.selectors if match(fqbasename)]:
                continue
            if self.exclude_selectors:
                if [1 for match in self.exclude_selectors if match(fqbasename)]:
                    continue
            if context in TEST_RUN_DIRS:
                test_class = FwrapRunTestCase
            else:
                test_class = FwrapCompileTestCase
            target_path = os.path.join(path, filename)
            if not is_subdir:
                flag_sets = parse_testcase_flag_sets(target_path)
            else:
                flag_sets = []
                for x in os.listdir(target_path):
                    flag_sets.extend(parse_testcase_flag_sets(os.path.join(target_path, x)))
            if len(flag_sets) == 0:
                flag_sets = [[]]
            for extra_flags in flag_sets:
                use_f2py = '--f2py-comparison' in extra_flags
                if use_f2py:
                    extra_flags = [x for x in extra_flags if x != '--f2py-comparison']
                suite.addTest(self.build_test(test_class, path, workdir, filename, extra_flags,
                                              use_f2py=use_f2py))
        return suite

    def build_test(self, test_class, path, workdir, filename, extra_flags, use_f2py):
        return test_class(path, workdir, filename,
                          cleanup_workdir=self.cleanup_workdir,
                          cleanup_sharedlibs=self.cleanup_sharedlibs,
                          verbosity=self.verbosity,
                          configure_flags=self.configure_flags + extra_flags,
                          use_f2py=use_f2py)

class _devnull(object):

    def flush(self): pass
    def write(self, s): pass

    def read(self): return ''


class FwrapCompileTestCase(unittest.TestCase):
    def __init__(self, directory, workdir, filename,
            cleanup_workdir=True, cleanup_sharedlibs=True,
            verbosity=0, configure_flags=(), use_f2py=False):
        self.directory = directory
        self.workdir = workdir
        self.filename = filename
        self.cleanup_workdir = cleanup_workdir
        self.cleanup_sharedlibs = cleanup_sharedlibs
        self.verbosity = verbosity
        self.configure_flags = configure_flags
        self.use_f2py = use_f2py
        self.is_dir = os.path.isdir(os.path.join(directory, filename))
        unittest.TestCase.__init__(self)

    def shortDescription(self):
        return "wrapping %s" % self.filename

    def setUp(self):
        if self.workdir not in sys.path:
            sys.path.insert(0, self.workdir)

    def tearDown(self):
        try:
            sys.path.remove(self.workdir)
        except ValueError:
            pass
        if os.path.exists(self.workdir):
            if self.cleanup_workdir:
                for rmfile in os.listdir(self.workdir):
                    try:
                        rmfile = os.path.join(self.workdir, rmfile)
                        if os.path.isdir(rmfile):
                            shutil.rmtree(rmfile, ignore_errors=True)
                        else:
                            os.remove(rmfile)
                    except IOError:
                        pass
        else:
            os.makedirs(self.workdirs)

    def runTest(self):
        base = os.path.splitext(self.filename)[0]
        self.projname = base + '_fwrap'
        self.projdir = os.path.join(self.workdir, base + ('_f2py' if self.use_f2py else '_fwrap'))
        fq_fname = os.path.join(os.path.abspath(self.directory), self.filename)
        if self.is_dir:
            source_files = glob(os.path.join(fq_fname, '*.f90'))
            pyf_file = None
        else:
            pyf_file = '%s.pyf' % os.path.splitext(fq_fname)[0]
            if not os.path.exists(pyf_file):
                pyf_file = None
            source_files = [fq_fname]
        if self.use_f2py:
            self.compile_f2py(source_files, pyf_file)
        else:
            self.compile_fwrap(source_files, pyf_file)

    def compile_fwrap(self, source_files, pyf_file):
        if '--package' in self.configure_flags:            
            assert pyf_file is None
            from fwrap.fwrapcmd import fwrap_main
            from subprocess import check_call
            # Create Cython wrapper
            flags = [x for x in self.configure_flags if x != '--package']
            fwrap_main(['createpackage', '--copy-sources', '-o', self.projdir] + flags +
                       [self.projname] + source_files)
            py_exe = sys.executable
            cwd = os.getcwd()
            try:
                os.chdir(self.projdir)
                check_call([py_exe, 'waf',
                            'configure', '--inplace',
                            'build', 'install'])
            finally:
                os.chdir(cwd)
        else:
            from fwrap.fwrapc import fwrapc
            # fwrapc.py configure build fsrc...
            conf_flags = self.configure_flags
            if pyf_file is not None:
                conf_flags.append('--pyf=%s' % pyf_file)
            argv = ['configure', 'build'] + conf_flags + [
                    '--inplace',
                    '--name=%s' % self.projname,
                    '--outdir=%s' % self.projdir]
            argv += source_files
            argv += ['install']
            fwrapc(argv=argv)

    def compile_f2py(self, source_files, pyf_file):
        from numpy.f2py.f2py2e import main as f2pymain
        assert pyf_file is not None
        assert len(source_files) == 1
        f_file = source_files[0]
        os.makedirs(self.projdir)
        shutil.copy(f_file, self.projdir)
        shutil.copy(pyf_file, self.projdir)
        print 'Calling f2py... (see runtests.py for getting hold of output)'
        oldpipes = sys.stdout, sys.stderr
        try:
            sys.stdout = StringIO()
            sys.stderr = StringIO()
            opts = ['--no-wrap-functions']
            with working_directory(self.projdir):
                # Invoke just to create C file, for inspection
                with process_args_as(opts + [pyf_file]):
                    f2pymain()
                # Compile all the way to .so
                with process_args_as(opts + ['-c', pyf_file, f_file]):
                    f2pymain()
        finally:
            sys.stdout, sys.stderr = oldpipes

    def compile(self, directory, filename, workdir, incdir):
        self.run_wrapper(directory, filename, workdir, incdir)

    def run_wrapper(self, directory, filename, workdir, incdir):
        wrap(filename, directory, workdir)


class FwrapRunTestCase(FwrapCompileTestCase):
    def shortDescription(self):
        result = "compiling and running %s" % self.filename
        if self.use_f2py:
            result += " (f2py mode)"
        return result

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()
        result.startTest(self)
        try:
            self.setUp()
            self.runTest()
            if self.projdir not in sys.path:
                sys.path.insert(0, self.projdir)
            if self.is_dir:
                doctest_mod_fqpath = os.path.join(self.directory, self.filename,
                                                  self.filename + '_doctest.py')
            else:
                doctest_mod_base = self.projname+'_doctest'
                doctest_mod_fqpath = os.path.join(self.directory, doctest_mod_base+'.py')
            testname = self.projname + '_doctest' + ('_f2py' if self.use_f2py else '')
            assert os.path.isdir(self.projdir)
            shutil.copyfile(doctest_mod_fqpath, os.path.join(self.projdir, testname) + '.py')

            try:
                os.environ['F2PY'] = str(int(self.use_f2py))
                doctest.DocTestSuite(testname).run(result) #??
            finally:
                del os.environ['F2PY']
                
        except Exception:
            result.addError(self, sys.exc_info())
            result.stopTest(self)
        try:
            self.tearDown()
        except Exception:
            pass


class FileListExcluder:

    def __init__(self, list_file):
        self.excludes = {}
        for line in open(list_file).readlines():
            line = line.strip()
            if line and line[0] != '#':
                self.excludes[line.split()[0]] = True

    def __call__(self, testname):
        return testname.split('.')[-1] in self.excludes

if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option("--no-cleanup", dest="cleanup_workdir",
                      action="store_false", default=True,
                      help="do not delete the generated C files (allows passing --no-cython on next run)")
    parser.add_option("--no-cleanup-sharedlibs", dest="cleanup_sharedlibs",
                      action="store_false", default=True,
                      help="do not delete the generated shared libary files (allows manual module experimentation)")
    parser.add_option("-x", "--exclude", dest="exclude",
                      action="append", metavar="PATTERN",
                      help="exclude tests matching the PATTERN")
    parser.add_option("-v", "--verbose", dest="verbosity",
                      action="count",
                      default=0,
                      help="display test progress, more v's for more output")
    parser.add_option("-T", "--ticket", dest="tickets",
                      action="append",
                      help="a bug ticket number to run the respective test in 'tests/bugs'")
    parser.add_option("-C", metavar="CONFIGUREFLAG", action="append",
                      dest="configure_flags", default=[],
                      help="passes flag on to the waf configure command "
                      "(example: -Cf77binding)")

    options, cmd_args = parser.parse_args()


    # RUN ALL TESTS!
    ROOTDIR = os.path.join(os.getcwd(), os.path.dirname(sys.argv[0]), 'tests')
    WORKDIR = os.path.join(os.getcwd(), 'BUILD')
    if os.path.exists(WORKDIR):
        for path in os.listdir(WORKDIR):
            if path in ("support",): continue
            shutil.rmtree(os.path.join(WORKDIR, path), ignore_errors=True)
    if not os.path.exists(WORKDIR):
        os.makedirs(WORKDIR)

    sys.stderr.write("Python %s\n" % sys.version)
    sys.stderr.write("\n")

    # insert cython.py/Cython source directory into sys.path
    cython_dir = os.path.abspath(os.path.join(os.path.pardir, os.path.pardir))
    sys.path.insert(0, cython_dir)

    test_bugs = False
    if options.tickets:
        for ticket_number in options.tickets:
            test_bugs = True
            cmd_args.append('.*T%s$' % ticket_number)
    if not test_bugs:
        for selector in cmd_args:
            if selector.startswith('bugs'):
                test_bugs = True

    selectors = [ re.compile(r, re.I|re.U).search for r in cmd_args ]
    if not selectors:
        selectors = [ lambda x:True ]

    # Check which external modules are not present and exclude tests
    # which depends on them (by prefix)

    exclude_selectors = []

    if options.exclude:
        exclude_selectors += [ re.compile(r, re.I|re.U).search for r in options.exclude ]

    if not test_bugs:
        exclude_selectors += [ FileListExcluder("tests/bugs.txt") ]

    test_suite = unittest.TestSuite()

    configure_flags = ['--%s' % x for x in options.configure_flags]

    filetests = FwrapTestBuilder(ROOTDIR, WORKDIR, selectors, exclude_selectors,
                                 options.cleanup_workdir, options.cleanup_sharedlibs,
                                 options.verbosity,
                                 configure_flags=configure_flags)
    test_suite.addTest(filetests.build_suite())

    unittest.TextTestRunner(verbosity=options.verbosity).run(test_suite)
