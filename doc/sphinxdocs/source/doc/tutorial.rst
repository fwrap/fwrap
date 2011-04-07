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
