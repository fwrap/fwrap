#------------------------------------------------------------------------------
# Copyright (c) 2010, Dag Sverre Seljebotn
# All rights reserved. See LICENSE.txt.
#------------------------------------------------------------------------------

from fwrap import code

from nose.tools import (ok_, eq_, set_trace, raises, assert_raises,
                        assert_false, assert_true)
import sys
from pprint import pprint
from textwrap import dedent
from fwrap.configuration import *
from StringIO import StringIO

def test_parser():
    code = dedent("""
    Not included
    foo
    # Fwrap: wraps source_a.f90    
    # Fwrap:     sha1 346e
    # Fwrap: self-sha1 1872
    bar
    # Fwrap: wraps source_a.f90
    # Fwrap: has-no-value
    yey!
    """)

    obj = parse_inline_configuration(code)
    eq_(obj, [
        ('wraps', 'source_a.f90', [
            ('sha1', '346e', [])
            ]),
        ('self-sha1', '1872', []),
        ('wraps', 'source_a.f90', []),
        ('has-no-value', '', [])
        ])
        

    assert_raises(ValueError, parse_inline_configuration,
                  "# Fwrap:self-sha1 342d") # need leading space
    assert_raises(ValueError, parse_inline_configuration,
                  dedent("""
                  # Fwrap: foo value
                  # Fwrap:     child1
                  # Fwrap:    child2
                  """)) # inconsistent indentation


def test_apply_dom():

    def filter_tree(x):
        # Remove top-level keys we don't use in the test
        return dict((key, value)
                    for key, value in x.iteritems()
                    if key in ('self-sha1', 'wraps', 'f77binding'))
    
    parse_tree = [
        ('self-sha1', '1872', []),
        ('wraps', 'source_a.f90', [
            ('sha1', '346e', [])
            ]),
        ('wraps', 'source_b.f90', []),
        ('f77binding', 'True', []),
        ]
    try:
        typed_tree = filter_tree(apply_dom(parse_tree))
    except ValidationError:
        ok_(False)

    eq_(typed_tree, {
        'self-sha1' : '1872',
        'wraps' : [
            ('source_a.f90', {'sha1': '346e'}),
            ('source_b.f90', {'sha1': None})
            ],
        'f77binding' : True
        })

    parse_tree[0] = ('git-head', 'not-a-sha', [])
    assert_raises(ValidationError, apply_dom, parse_tree)

    assert_raises(ValidationError, apply_dom,
                  [('unknown', 'asdf', [])])
    assert_raises(ValidationError, apply_dom,
                  [('self-sha1', '1', []),
                   ('self-sha1', '1', [])]) # repetead


def test_serialize():
    key_order = ['self-sha1', 'wraps', 'f77binding']
    doc = {
        'self-sha1' : '1872',
        'wraps' : [
            ('source_a.f90', {'sha1': '346e'}),
            ('source_b.f90', {})
            ],
        'f77binding' : False
        }
    parse_tree = document_to_parse_tree(doc, key_order)
    eq_(parse_tree, [
        ('self-sha1', '1872', []),
        ('wraps', 'source_a.f90', [
            ('sha1', '346e', [])
            ]),
        ('wraps', 'source_b.f90', []),
        ('f77binding', 'False', [])
        ])

    buf = StringIO()
    serialize_inline_configuration(parse_tree, buf)
    eq_(buf.getvalue(), dedent("""\
        # Fwrap: self-sha1 1872
        # Fwrap: wraps source_a.f90
        # Fwrap:     sha1 346e
        # Fwrap: wraps source_b.f90
        # Fwrap: f77binding False
        """))

    
def test_self_sha1():
    a = dedent('''
    Some contents
    # Fwrap: self-sha1 234323asdfxcvasdf
    foo
    ''')
    sha = get_self_sha1(a)
    eq_(sha, get_self_sha1(a.replace('234323asdfxcvasdf', 'bar')))
    eq_(update_self_sha1(a), dedent('''
    Some contents
    # Fwrap: self-sha1 39bcc5090f077fd6180567ed17f2a149c91f36fb
    foo
    '''))
