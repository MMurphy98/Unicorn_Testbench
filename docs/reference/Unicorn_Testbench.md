# Unicorn\_Testbench

> 原始测试需求与方案资料。任务执行状态以 `docs/TODO.md` 为准。

## 测试需求

待测目标：TI OPAx189；自研 Unicorn\_CSA（高压 Chopper-Stabilization Amplifier)

测试指标：

*   等效输入噪声谱密度 $V\_{in,n}^2$

*   输入失调电压以及失调漂移 $V\_{os}, \frac{d~V\_{os}}{d~T}$


## 测试方案

###  噪声测试

**测试 0.1Hz -> 10MHz 噪声谱密度PSD**

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952NXQ9mzlap/img/c6dbb6cd-a299-430b-b4c9-cfc25cc437d0.png)

#### 测试基本原理

由于运放的带宽会受到反馈网络而限制，且不存在 flicker noise 在 1Hz 小于咱们DUT而带宽又很大的商用运放，因此在全频段噪声的测量主要分为 **0.1Hz->0.1kHz，0.1kHz-> 10kHz 和 10kHz -> 10MHz 三个频段**进行测量。

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952NXQ9mzlap/img/d0f8b1c5-b799-42a3-b4af-840be9da1d12.png "TI Precision Lab 噪声谱拼接")

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952NXQ9mzlap/img/2cff4aa3-3cc6-4eb3-98b0-275b70f46356.png "测试方案细节")

| **Frequency** | **0.1Hz -> 100Hz** | **100Hz -> 10kHz** | **10kHz -> 10MHz** |
| --- | --- | --- | --- |
| **DUT Config** | Gain = 1001 | Gain = 101 | Gain = 1 |
| **Post-Amp** | / | / | OPA847, Gain = 101 |
| **Instrument** | PXI-5922 | PXI-5922 | MSO54 or FSW |

*   0.1Hz -> 100Hz： 用 DUT 自增益 Gain= 1001 放大，由 PXI-5922 采样；

*   100Hz -> 10kHz： 用 DUT 自增益 Gain=101 放大，由 PXI-5922 采样，底噪由测试项目 1 验证，读数噪声至少为设备底噪的 10 倍；

*   10kHz-10MHz：DUT 结为 Gain=1 的 buffer 形式，由后续放大电路提供增益，**OPA847 10kHz 处底噪约为 0.9nV/rtHz，GBW 有 3.9GHz**，在 Gain= 101 时仍有 38MHz 带宽，符合测试要求；


![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952NXQ9mzlap/img/b520568d-4615-49be-96bc-39d042d191c9.png "Tektronix MSO54")

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952NXQ9mzlap/img/47f664a5-221c-4809-9a5f-2755f2d0e6e4.png "RS MXO4")

以最差的 MSO54 噪声按照白噪声去估计，底噪约为 20nV/rtHz，DUT 放大后底噪约为 5nV\*50.5-> 250nV/rtHz，至少为设备底噪的 10 倍；

#### 仿真结果

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/8oLl952NXQ9mzlap/img/a5306dbc-668c-40a5-bb4b-d38f3296d17c.png)

按照之前的测试方案仿真验证，在不考虑设备底噪的情况下，以 OPA189 作为 DUT 仿真验证，测量误差基本上小于 1%；

由 OPA847 放大的高频处噪声略大一点，但是通过标定底噪的方法应该可以消除；

:::
**辅助运放已改成 OPA892；**
:::

### 失调测试

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/QvjnA3jyboBz8OXo/img/45a47158-d93f-4d73-91aa-41167ff641eb.png "Offset Testbench")

$V\_{os} = V\_{test} / 1001$

整个测试几乎没有风险点，唯一的风险点在电阻的温漂上，精密电阻选择；

**比较麻烦的是温漂测试；**

## 需要你做的内容

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/ABmOoWbNxXWMVOaw/img/dfc69c85-2f6c-46a8-b882-ea462c9eb377.png "PCB demo示意图（实际结构为3层板）")

1.  理解 PCB 结构，“母板+子板+chiplet” 三层结构：

    1.  母版：功能非常复杂，我们只用其中一部分，提供正负高低压供电，数字信号，偏置电流；

    2.  子板：local feedback，也是测试方案中实现的方法；

    3.  chiplet：可更换 DUT

2.  看懂测试原理，明白指标含义；

3.  利用 OPAx189 的指标，交叉验证测试方案；

    1.  用测试 PCB 对 OPAx189 进行测试，指标与 datasheet 进行对比；

4.  用测试 PCB 对 DUT 进行测试，记录指标；


*   **Quartus 18**

*   **MATLAB  1MPoints 数据 -> CSV 格式，MATLAB 读数据 画频谱图；**
