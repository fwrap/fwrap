module mytypes

  INTEGER, PARAMETER, public :: i4b = SELECTED_INT_KIND(9)
  INTEGER, PARAMETER, public :: sp  = SELECTED_REAL_KIND(5,30)
  INTEGER, PARAMETER, public :: dp  = SELECTED_REAL_KIND(12,200)
  INTEGER, PARAMETER, public :: lgt = KIND(.TRUE.)
  INTEGER, PARAMETER, public :: spc = KIND((1.0_sp, 1.0_sp))
  INTEGER, PARAMETER, public :: dpc = KIND((1.0_dp, 1.0_dp))

end module
