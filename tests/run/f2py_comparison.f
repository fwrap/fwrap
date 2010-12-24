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

      subroutine out_arr(x, n, m)
      integer x(n, m)
      integer n, m, i, j
      do j = 1, m
         do i = 1, n
            x(i, j) = (i-1) * m + j
         enddo
      enddo
      end subroutine

      subroutine out_and_overwrite(xinout, xout, n, m)
      integer xout(n, m)
      integer xinout(n, m)
      integer n, m, i, j
      do j = 1, m
         do i = 1, n
            xout(i, j) = 2 * (i-1) * m + j
            xinout(i, j) = (i-1) * m + j
         enddo
      enddo
      end subroutine

      subroutine nodeps(arr, n)
      integer arr(n)
      integer n, i
      do i = 1, n
         arr(i) = i
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

      subroutine swilk(x,n,a,n2)
        real x(n), a(n2)
        integer n, n2, i
        write (*,*) n2
        do i = 1, n2
           a(i) = x(i) + x(2 * i) + a(i)
        enddo
      end subroutine swilk

      
c$$$      subroutine tricky_case(n, arr)
c$$$      integer arr(n)
c$$$      integer n, i
c$$$      do i = 1, n
c$$$         arr(i) = i
c$$$      enddo
c$$$      end subroutine
c$$$      
