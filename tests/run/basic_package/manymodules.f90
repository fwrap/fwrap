! configure-flags: --package
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

module barmod
  private

  public :: sub2

contains
  subroutine i_am_private()
  end subroutine i_am_private


  subroutine sub2(x)
    integer, intent(out) :: x
    x = 2
  end subroutine sub2
end module
