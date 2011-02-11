#------------------------------------------------------------------------------
# Copyright (c) 2010, Kurt W. Smith, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

#
# Utilities to do some preprocessing before handing files off to merge
#

import re
from fwrap.version import get_version

_re_version_1 = re.compile('Fwrap v([0-9a-fv._]+)\.')
_re_version_2 = re.compile('version ([0-9a-fv._]+)')
def premerge_version(work, base, generated):
    ver = get_version()
    rep1 = 'Fwrap v%s.' % ver
    work = [_re_version_1.subn(rep1, x)[0] for x in work]
    rep2 = 'version %s' % ver
    work = [_re_version_2.subn(rep2, x)[0] for x in work]
    return work

_re_pyfhash = re.compile('^# Fwrap: pyf-sha1 [0-9a-f]+$')
_re_selfhash = re.compile('^# Fwrap: self-sha1 [0-9a-f]+$')
def premerge_hashes(work, base, generated):
    for x in generated:
        if _re_pyfhash.match(x):
            pyf_line = x
        elif _re_selfhash.match(x):
            self_line = x
    result = []
    for x in work:
        if _re_pyfhash.match(x):
            x = pyf_line
        elif _re_selfhash.match(x):
            x = self_line
        result.append(x)
    return result

premerger_list = [premerge_version, premerge_hashes]

def premerge(work_file, base_file, generated_file):
    with file(work_file) as f:
        work = f.readlines()
    with file(base_file) as f:
        base = f.readlines()
    with file(generated_file) as f:
        generated = f.readlines()

    for premerger in premerger_list:
        work = premerger(work, base, generated)
        
    with file(work_file, 'w') as f:
        f.write(''.join(work))
