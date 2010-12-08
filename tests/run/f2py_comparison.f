C configure-flags: --f77binding
C configure-flags: --f77binding --f2py-comparison

      subroutine func(n, m, x)
      integer x(n, m)
      integer n, m, i, j
      do j = 1, m
         do i = 1, n
            x(i, j) = (i-1) * m + j
         enddo
      enddo
      end subroutine
