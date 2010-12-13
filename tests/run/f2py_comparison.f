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

      subroutine array_given_n(arr, n)
      integer arr(n)
      integer n, i
      do i = 1, n
         arr(i) = i
      enddo
      end subroutine

      subroutine array_given_n_argrev(n, arr)
      integer arr(n)
      integer n, i
      do i = 1, n
         arr(i) = i
      enddo
      end subroutine

      subroutine n_given_array(arr, n)
      integer arr(n)
      integer n, i
      do i = 1, n
         arr(i) = i
      enddo
      end subroutine

      subroutine n_given_array_argrev(n, arr)
      integer arr(n)
      integer n, i
      do i = 1, n
         arr(i) = i
      enddo
      end subroutine
      
c$$$      subroutine tricky_case(n, arr)
c$$$      integer arr(n)
c$$$      integer n, i
c$$$      do i = 1, n
c$$$         arr(i) = i
c$$$      enddo
c$$$      end subroutine
c$$$      
