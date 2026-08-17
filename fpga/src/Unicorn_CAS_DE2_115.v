module Unicorn_CAS_DE2_115(
    input   clk_50M,
    input   rst_n,

// to DUT
    output  wire    clk_DUT,
    output  wire    clk_div_DUT,
    output  wire    por_div_DUT,

// from FPGA Board
    input   key_clk_div,
    output  wire    LED_clk_div,
    output  wire    LED_pll_ready,
    output  wire    LED_por_ready
);



pll Inst_pll (
    .areset     (~rst_n),
    .inclk0     (clk_50M),      // Fin = 50MHz
    .c0         (clk_DUT),      // Fout = 1MHz
    .locked     (LED_pll_ready)
);

reg clk_div_dut_reg;
reg por_div_dut_reg;


// capture signal from key
always @(posedge clk_DUT or negedge rst_n) begin
    if (rst_n == 1'b0) begin
        clk_div_dut_reg <= 1'd0;
        por_div_dut_reg <= 1'd0;
    end
    else begin
        clk_div_dut_reg <= key_clk_div;
        por_div_dut_reg <= rst_n;
    end
end

// assign output
assign clk_div_DUT = clk_div_dut_reg;
assign LED_clk_div = clk_div_dut_reg;
assign LED_por_ready = por_div_dut_reg;




endmodule