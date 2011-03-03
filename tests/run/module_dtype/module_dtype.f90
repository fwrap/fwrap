subroutine foo(x, y)
  use mytypes
  implicit none
  real(dp), intent(out) :: x
  integer(i4b), dimension(:), intent(out) :: y
  x = 2.3_dp
  y = 4_i4b
end subroutine
