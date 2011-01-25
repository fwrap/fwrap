C configure-flags: --f77binding

       subroutine foo(callback, x)
       external callback
       integer x
       call callback(x, x)
       end subroutine foo
