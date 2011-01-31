C configure-flags: --f77binding

      subroutine caller(cb, a, b, n)
      implicit none
      integer a
      real*8 b(n, n)
      integer n
      external cb
      call cb(a, b, n)
      end subroutine caller


      subroutine callsnoargs(f)
      external f
      call f()
      end subroutine

      subroutine multi(f, g)
      external f
      external g
      call f()
      call g()
      end subroutine
