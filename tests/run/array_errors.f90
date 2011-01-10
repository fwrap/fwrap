
        subroutine func(im, ex, n, m)
            implicit none
            real, dimension(:,:), intent(inout) :: im
            real, dimension(n,m), intent(inout) :: ex
            integer, intent(in) :: n, m
        end subroutine func
