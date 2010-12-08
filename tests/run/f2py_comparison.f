C configure-flags: --f77binding --emulate-f2py
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

      subroutine out_arr(n, m, x)
      integer x(n, m)
      integer n, m, i, j
      do j = 1, m
         do i = 1, n
            x(i, j) = (i-1) * m + j
         enddo
      enddo
      end subroutine

