set_location_assignment PIN_AG15 -to clk_50M
set_location_assignment PIN_M23  -to rst_n
# to DUT
set_location_assignment PIN_AC15 -to clk_DUT        
set_location_assignment PIN_Y17  -to clk_div_DUT
set_location_assignment PIN_AB22 -to por_div_DUT  
# clk_dut -> GPIO1
# clk_div_DUT -> GPIO3
# por_div_DUT -> GPIO0

set_location_assignment PIN_AB28 -to key_clk_div        
set_location_assignment PIN_G19  -to LED_clk_div        
set_location_assignment PIN_E22  -to LED_pll_ready      
set_location_assignment PIN_E21  -to LED_por_ready                  
# key_clk_div -> SW0
# LED_clk_div -> LEDR0
# LED_pll_ready -> LEDG1
# LED_por_ready -> LEDG0

set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to clk_50M
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to rst_n
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to clk_DUT  
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to clk_div_DUT
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to por_div_DUT
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to key_clk_div  
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to LED_clk_div
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to LED_pll_ready
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to LED_por_ready         

set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to clk_50M
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to rst_n
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to clk_DUT  
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to clk_div_DUT
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to por_div_DUT
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to key_clk_div  
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to LED_clk_div
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to LED_pll_ready
set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT"      -to LED_por_ready  