module foomod

  private :: i_am_private
  public :: sub1
contains
  subroutine i_am_private()
  end subroutine i_am_private


  subroutine sub1(x)
    integer, intent(out) :: x
    x = 1
  end subroutine sub1
end module

