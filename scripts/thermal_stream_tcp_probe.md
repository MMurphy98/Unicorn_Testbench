# 热流仪 TCP 连接测试

完整的控制能力、地址表、报文格式和未验证项目见
[热流仪 TCP 接口能力与接入说明](../docs/instruments/thermal_stream_tcp.md)。本文只说明探测脚本的运行方法。

`thermal_stream_tcp_probe.py` 仅使用 Python 标准库，默认连接本机实测成功的
`192.168.1.50:3000`，Unit ID 为 `0`。厂家文档中的 `.55` 是示例 IP，实际设备面板
显示通讯 IP 为 `.50`、PLC IP 为 `.100`；PC 应连接通讯 IP。只发送功能码 `03` 和 `01`，依次读取
空气温度、产品/表面温度和运行状态，不包含设备写入命令。

在项目根目录运行：

```powershell
python .\scripts\thermal_stream_tcp_probe.py
```

可选参数：

```powershell
python .\scripts\thermal_stream_tcp_probe.py --host 192.168.1.50 --port 3000 --unit-id 0 --timeout 3
```

如果需要指定 PC 网卡，追加 `--source-ip <该网卡的IPv4地址>`。
程序会显示实际使用的本地地址，并把每次测试的时间、收发十六进制报文、
解码结果或错误保存到 `results/thermal_stream/tcp_probe_<UTC时间>.json`。
也可以通过 `--output <文件路径>` 指定报告位置。

退出码：`0` 为 TCP 和三项读取均成功；`1` 为连接失败；`2` 为 TCP 已连接但读取失败。
读取成功验证的是协议连通性，不验证设备实际制冷、制热能力或传感器精度。

## 网络条件

若 PC 通过网线直连设备，应将对应有线网卡配置为与设备相同的子网。
例如设备为 `192.168.1.50/24` 时，PC 可以使用未占用的 `192.168.1.200/24`；
直连网卡不需要配置默认网关或 DNS。设备的实际 IP、掩码仍应以其面板设置为准。

`169.254.x.x` 通常表示该网卡未获得 DHCP 地址，不能据此直接访问上述设备地址。
配置地址需要 Windows 管理员权限；本 Python 脚本不会修改网卡配置。

### 当前 PC 的临时网卡配置

2026-09-11 已确认本 PC 的“以太网 2”是接口 `5`，MAC 为
`08-26-AE-32-33-8C`，设备网卡当前临时地址为 `192.168.1.200/24`。
通讯 IP `192.168.1.50` 和 PLC IP `192.168.1.100` 均已被设备使用，不应分配给 PC。
接口编号可能因更换 USB 网卡等操作而变化，重新运行前需核对。

配置辅助脚本 `configure_thermal_stream_ethernet.ps1` 校验接口 MAC、链路和原有配置；
仅允许从无默认网关、启用 DHCP 且只有 `169.254.*` 地址的状态进行设置。
它使用 `ActiveStore` 临时设置地址，遇到地址冲突或地址未就绪会恢复 DHCP。
在管理员 PowerShell 中，可从项目根目录运行：

```powershell
New-Item -ItemType Directory -Force .\results\thermal_stream | Out-Null
.\scripts\configure_thermal_stream_ethernet.ps1 -IPv4Address 192.168.1.200 -ReportPath .\results\thermal_stream\ethernet_setup.json
```

恢复这块网卡的临时 DHCP 配置，同样需要管理员 PowerShell：

```powershell
netsh interface ipv4 set address name=5 source=dhcp store=active
```

需要明确绑定当前 USB 网卡时，运行：

```powershell
python .\scripts\thermal_stream_tcp_probe.py --host 192.168.1.50 --port 3000 --source-ip 192.168.1.200
```

## 协议依据

- `docs/reference/热流仪TCP通讯协议 .docx`：示例 IP、端口、服务器角色和请求报文。
- 2026-09-11 实测确认实际通讯 IP 为 `192.168.1.50`、TCP 端口为 `3000`，Unit ID `0`。
- `docs/reference/热流仪485通讯样例.docx`：温度及运行状态读取示例。
- 温度按 16 位有符号整数除以 10 解码；运行状态使用返回字节的最低位。
- TCP 报文使用 MBAP 头，不追加 RTU CRC；发送二进制字节，不发送十六进制文本。
- 请求严格串行，沿用厂家示例的事务号 `0`。脚本检查事务号、协议号、Unit ID、
  长度、功能码和字节数，并处理 TCP 分段收包。
