C configure-flags: --f77binding

       subroutine foo(callback, x)
       external callback
       integer x
       call callback(x, x)
       end subroutine

       subroutine array2d(callback2darr, x, n, m)
       external callback2darr
       real*8 x(n, m)
       integer n, m
       call callback2darr(x, n, m, x)
       end subroutine
