Fwrap Tutorial
==============

Introduction
------------

Fwrap generates Cython wrappers for Fortran 90/95 code, and will work with
`"sane" Fortran 77 <../index.html#sane-def>`_ as well. 
Fwrap uses the Fortran parser ``fparser`` written by Pearu Peterson for 
`the f2py project <http://cens.ioc.ee/projects/f2py2e/>`_.
`Cython <http://cython.org>`_ will be used to compile the resulting ``.pyx``
files and generate ``.c`` files, that can be compiled into ``.so`` files by a C
compiler.  The ``.so`` shared objects can be imported directly by Python.

Therefore fwrap provides wrapping of Fortran code in C, Cython and Python
automatically.

Examples
--------

There are several ways to generate ``.pyx`` and ``so`` files for Fortran code
using fwrap.  This tutorial describes shortly three use cases and provides an
introduction to the basic commands.

Use Case 1
~~~~~~~~~~

This use case describes how to compile an existing Fortran code
using ``fwrap compile``. First create an empty directory by typing: ::

        mkdir project4py
        cd project4py

The ``init`` command dumps the ``waf``, ``wscript`` and ``tools`` subdirectories in
the current directory. ::

        fwrap init
        fwrap createpackage project /path/to/project/src/f90/*.f90
        find
        project/project_types.pyx
        project/__init__.py
        ./waf configure --with-project=/my/compiled/project
        wscript

Finally run the ``compile`` command to build the Cython ``.pyx`` files. ::

        fwrap compile ...
        myproject-1.3.4/myproject/__init__.py
        myproject-1.3.4/myproject/somefuncs.py
        myproject-1.3.4/myproject/otherfuncs.f90


