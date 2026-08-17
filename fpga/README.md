# Unicorn CSA DE2-115 FPGA 工程

本目录是面向 Terasic DE2-115 开发板的 Quartus Prime 工程，用于向外部 DUT 提供 1 MHz 时钟、由拨码开关控制的同步信号以及上电复位信号，并通过板载 LED 显示工作状态。

## 工程信息

| 项目 | 内容 |
| --- | --- |
| Quartus 工程/Revision | `Unicorn_CSA_DE2_115` |
| 顶层模块 | `Unicorn_CAS_DE2_115` |
| 顶层源文件 | `src/Unicorn_CAS_DE2_115.v` |
| FPGA | Intel/Altera Cyclone IV E `EP4CE115F29C7` |
| 开发板 | Terasic DE2-115 |
| 编译工具 | Quartus Prime 18.1.0 Standard Edition |
| PLL 输入/输出 | 50 MHz / 1 MHz |
| I/O 电平标准 | 3.3-V LVTTL |

> 注意：工程名中的缩写是 `CSA`，顶层模块和 Verilog 文件名中的缩写是 `CAS`。这是当前工程的实际命名，不要因二者不同而误选顶层模块或烧录文件。

## 功能说明

板载 `CLOCK3_50` 为 PLL 提供 50 MHz 时钟，PLL 分频后在 `clk_DUT` 输出 1 MHz 时钟。`KEY[0]` 是低有效复位键，`SW[0]` 用于设置 `clk_div_DUT` 的逻辑电平。

在每个 `clk_DUT` 上升沿：

- 将 `SW[0]` 的状态采样到 `clk_div_DUT`，并同步显示到 `LEDR[0]`；
- 将复位释放状态采样到 `por_div_DUT`，并同步显示到 `LEDG[0]`。

按住 `KEY[0]` 时，`rst_n=0`，PLL 复位，`clk_div_DUT` 和 `por_div_DUT` 均被异步清零。松开 `KEY[0]` 后，PLL 重新锁定；`LEDG[1]` 点亮表示 PLL 已锁定，`por_div_DUT` 在有效的 1 MHz 上升沿后变高。

## Pin 对照表

下表中的 `GPIO[n]` 是 DE2-115 原理图/官方引脚表中的 GPIO 信号编号，不是连接器的物理针脚序号。三个 DUT 信号没有按编号连续排列，接线时应以表中的 FPGA Pin 和 `GPIO[n]` 为准。

| 顶层信号 | 方向（相对 FPGA） | FPGA Pin | DE2-115 板载资源 | 作用 |
| --- | --- | --- | --- | --- |
| `clk_50M` | 输入 | `PIN_AG15` | `CLOCK3_50` | 板载 50 MHz PLL 参考时钟 |
| `rst_n` | 输入 | `PIN_M23` | `KEY[0]` | 全局低有效复位，按下为 `0` |
| `key_clk_div` | 输入 | `PIN_AB28` | `SW[0]` | 待同步到 DUT 的开关电平 |
| `clk_DUT` | 输出 | `PIN_AC15` | `GPIO[1]` | PLL 产生的 1 MHz DUT 时钟 |
| `clk_div_DUT` | 输出 | `PIN_Y17` | `GPIO[3]` | `SW[0]` 经 1 MHz 时钟同步后的输出 |
| `por_div_DUT` | 输出 | `PIN_AB22` | `GPIO[0]` | DUT 上电复位释放指示，复位时为低 |
| `LED_clk_div` | 输出 | `PIN_G19` | `LEDR[0]` | 显示已同步的 `clk_div_DUT` 状态 |
| `LED_pll_ready` | 输出 | `PIN_E22` | `LEDG[1]` | PLL 锁定指示 |
| `LED_por_ready` | 输出 | `PIN_E21` | `LEDG[0]` | 显示 `por_div_DUT` 状态 |

### DUT 接线速查

| DUT 信号 | 连接到 DE2-115 | FPGA Pin |
| --- | --- | --- |
| 1 MHz 时钟 | `GPIO[1]` | `AC15` |
| 开关控制信号 | `GPIO[3]` | `Y17` |
| POR/复位释放信号 | `GPIO[0]` | `AB22` |
| 地 | GPIO 排针上的 `GND` | - |

FPGA GPIO 为 3.3-V LVTTL。连接外部 DUT 前，应确认 DUT 输入能够承受 3.3 V，并确保 DE2-115 与 DUT 共地。不要把外部电源或其他输出信号直接连接到上述 FPGA 输出 Pin。

## 板上操作与状态

| 操作/状态 | 预期结果 |
| --- | --- |
| 按住 `KEY[0]` | 系统保持复位，`LEDR[0]` 和 `LEDG[0]` 熄灭，PLL 被复位 |
| 松开 `KEY[0]` | PLL 开始工作；锁定后 `LEDG[1]` 点亮，`GPIO[1]` 输出 1 MHz |
| `SW[0]` 拨到 `0` | 下一个 1 MHz 上升沿后，`GPIO[3]` 为低且 `LEDR[0]` 熄灭 |
| `SW[0]` 拨到 `1` | 下一个 1 MHz 上升沿后，`GPIO[3]` 为高且 `LEDR[0]` 点亮 |
| `LEDG[0]` 点亮 | `por_div_DUT` 已为高，DUT 复位已释放 |

## 烧录文件

本工程交付使用的 SRAM 配置文件为：

```text
output_files/Unicorn_CSA_DE2_115_20260817.sof
```

| 属性 | 值 |
| --- | --- |
| 文件名 | `Unicorn_CSA_DE2_115_20260817.sof` |
| 生成时间 | 2026-08-17 13:41:30 |
| 文件大小 | 3,541,772 bytes |
| SHA-256 | `43CA61DB7DF343817D0F950E871C5ED33C93A1B4CD08DBC5190E9371BE8B261E` |

该 `.sof` 文件用于通过 JTAG 临时配置 FPGA。开发板断电后配置会丢失，再次上电需要重新烧录。

### Quartus Programmer 烧录步骤

1. 给 DE2-115 上电，并使用 USB-Blaster 连接开发板和电脑。
2. 打开 Quartus Prime，选择 `Tools -> Programmer`。
3. 点击 `Hardware Setup...`，选择可用的 `USB-Blaster`。
4. 将 Programming Mode 设为 `JTAG`。
5. 点击 `Add File...`，选择 `output_files/Unicorn_CSA_DE2_115_20260817.sof`。
6. 勾选该文件对应的 `Program/Configure`。
7. 点击 `Start`，等待 Progress 显示 `100% (Successful)`。
8. 烧录完成后松开 `KEY[0]`，检查 `LEDG[1]`、`LEDG[0]` 和 `LEDR[0]` 的状态。

## 重新编译

使用 Quartus Prime 18.1 打开 `Unicorn_CSA_DE2_115.qpf`，执行 `Processing -> Start Compilation`。当前 Pin 约束已经写入 `Unicorn_CSA_DE2_115.qsf`；`pin_assigment.tcl` 保存了同一组约束，便于查阅或重新导入。

Quartus 生成的普通输出名是 `output_files/Unicorn_CSA_DE2_115.sof`。对外使用或归档时，应使用本 README 指定的带日期版本 `Unicorn_CSA_DE2_115_20260817.sof`，以免与后续重新编译的文件混淆。

> 当前工程没有 `.sdc` 时序约束文件。已有编译流程成功生成 `.sof`，但 Quartus Timing Analyzer 会报告缺少 SDC 的 Critical Warning；修改时钟或同步逻辑后，应补充相应时序约束并重新检查时序。
